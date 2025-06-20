import pandas as pd
import numpy as np
import pathlib
import os
import gc
import psutil
import warnings
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from functools import partial
import pyarrow as pa
import pyarrow.parquet as pq
from .dtype_utils import optimize_dtypes
from utils.database import execute_query_df
from typing import Dict, List, Optional, Tuple
import argparse

warnings.filterwarnings('ignore')

# Activity columns are filled with 0 when missing (representing no activity)
ACTIVITY_COLS = [
    # Core trading counts and amounts
    'num_trades',
    'net_profit',
    'gross_profit', 
    'gross_loss',
    'total_lots',
    'total_volume',
    
    # Payout amounts
    'todays_payouts',
    'approved_payouts', 
    'pending_payouts',
    
    # Consecutive counts
    'max_num_consec_wins',
    'max_num_consec_losses',
    
    # Maximum values
    'max_profit',
    'min_profit',
    'max_drawdown',
    'max_num_trades_in_dd',
    'max_num_open_pos',
    'max_val_consec_wins',
    'max_val_consec_losses',
    'max_val_open_pos',
    'max_val_to_eqty_open_pos',
    
    # Min/max duration and TP/SL
    'min_duration',
    'max_duration',
    'min_tp',
    'max_tp',
    'min_sl',
    'max_sl',
    'min_tp_vs_sl',
    'max_tp_vs_sl',
    
    # Absolute and relative profit metrics
    'rel_net_profit',
    'rel_gross_profit',
    'rel_gross_loss',
    'rel_min_profit',
    'rel_max_profit',
    'rel_max_drawdown',
    
    # Trade symbols
    'num_traded_symbols',
    'most_traded_smb_trades',
    
    # Other absolute metrics
    'one_std_outlier_profit',
    'two_std_outlier_profit',
    'rel_one_std_outlier_profit',
    'rel_two_std_outlier_profit',
    'one_std_outlier_profit_contrib',
    'two_std_outlier_profit_contrib',
    'top_10_prcnt_profit_contrib',
    'bottom_10_prcnt_loss_contrib'
]

# Categorical columns are forward-filled
CATEGORICAL_COLS = [
    # Identifiers
    'login',
    'account_id',
    'plan_id',
    'trader_id',
    
    # Status fields
    'status',
    'type',
    'phase',
    'broker',
    'platform',
    'price_stream',
    'country',
    
    # Account balances (persist even without trading)
    'starting_balance',
    'prior_days_balance',
    'prior_days_equity',
    'current_balance',
    'current_equity',
    
    # Date fields
    'first_trade_date',
    
    # Symbol info
    'most_traded_symbol'
]

# Derived metrics that should remain null when there's no trading activity
DERIVED_COLS = [
    # Rates and ratios (undefined when denominator is 0)
    'profit_factor',
    'gain_to_pain',
    'success_rate',
    'risk_adj_ret',
    'risk_adj_profit',
    'downside_risk_adj_ret',
    
    # Per-trade and per-unit metrics
    'expectancy',
    'net_profit_per_usd_volume',
    'gross_profit_per_usd_volume',
    'gross_loss_per_usd_volume',
    'distance_gross_profit_loss_per_usd_volume',
    'multiple_gross_profit_loss_per_usd_volume',
    'gross_profit_per_lot',
    'gross_loss_per_lot',
    'distance_gross_profit_loss_per_lot',
    'multiple_gross_profit_loss_per_lot',
    'net_profit_per_duration',
    'gross_profit_per_duration',
    'gross_loss_per_duration',
    
    # Statistical metrics (mean, median, std)
    'mean_profit',
    'median_profit',
    'std_profits',
    'mean_ret',
    'std_rets',
    'downside_std_rets',
    'mean_drawdown',
    'median_drawdown',
    'mean_num_trades_in_dd',
    'median_num_trades_in_dd',
    'std_volumes',
    'mean_winning_lot',
    'mean_losing_lot',
    'distance_win_loss_lots',
    'multiple_win_loss_lots',
    'mean_winning_volume',
    'mean_losing_volume',
    'distance_win_loss_volume',
    'multiple_win_loss_volume',
    'mean_duration',
    'median_duration',
    'std_durations',
    'cv_durations',
    'mean_tp',
    'median_tp',
    'std_tp',
    'cv_tp',
    'mean_sl',
    'median_sl',
    'std_sl',
    'cv_sl',
    'mean_tp_vs_sl',
    'median_tp_vs_sl',
    'cv_tp_vs_sl',
    'mean_num_consec_wins',
    'median_num_consec_wins',
    'mean_num_consec_losses',
    'median_num_consec_losses',
    'mean_val_consec_wins',
    'median_val_consec_wins',
    'mean_val_consec_losses',
    'median_val_consec_losses',
    'mean_num_open_pos',
    'median_num_open_pos',
    'mean_val_open_pos',
    'median_val_open_pos',
    'mean_val_to_eqty_open_pos',
    'median_val_to_eqty_open_pos',
    'mean_account_margin',
    'mean_firm_margin',
    
    # Relative statistical metrics
    'rel_mean_profit',
    'rel_median_profit',
    'rel_std_profits',
    'rel_risk_adj_profit',
    'rel_mean_drawdown',
    'rel_median_drawdown',
    
    # Percentile metrics
    'profit_perc_10',
    'profit_perc_25',
    'profit_perc_75',
    'profit_perc_90',
    'rel_profit_perc_10',
    'rel_profit_perc_25',
    'rel_profit_perc_75',
    'rel_profit_perc_90',
    
    # Top/bottom percentage trades
    'profit_top_10_prcnt_trades',
    'profit_bottom_10_prcnt_trades',
    'rel_profit_top_10_prcnt_trades',
    'rel_profit_bottom_10_prcnt_trades'
]

# Special columns with custom handling
COUNTDOWN_COLS = [
    'days_to_next_payout'
]

COUNTUP_COLS = [
    'days_since_initial_deposit',
    'days_since_first_trade'
]

def get_optimal_chunk_size(n_accounts: int, n_dates: int, n_cols: int, hour_col: bool = False) -> int:
    """Calculate optimal chunk size based on available memory and CPU cores."""
    # Get available memory and CPU count
    available_memory = psutil.virtual_memory().available
    cpu_count = mp.cpu_count()
    
    # Estimate memory per row (8 bytes per float64 * n_cols * overhead factor)
    # Using 2.5x overhead for pandas operations
    bytes_per_row = n_cols * 8 * 2.5
    
    # Calculate rows per account
    rows_per_account = n_dates * (24 if hour_col else 1)
    
    # Memory per account
    memory_per_account = rows_per_account * bytes_per_row
    
    # With many workers, each uses a fraction of memory
    # Use only 20% of available memory total (very conservative for streaming)
    memory_per_worker = (available_memory * 0.2) / 16
    
    # Calculate chunk size based on memory per worker
    chunk_size = int(memory_per_worker / memory_per_account)
    
    # Also consider creating enough chunks for good parallelization
    # Aim for at least 2-3x more chunks than workers for load balancing
    target_chunks = cpu_count * 3
    chunk_size_by_parallelization = max(n_accounts // target_chunks, 1)
    
    # Use the smaller of the two to ensure both memory and parallelization constraints
    chunk_size = min(chunk_size, chunk_size_by_parallelization)
    
    # Bound between reasonable limits - smaller chunks for streaming
    chunk_size = max(100, min(chunk_size, 5000))
    
    print(f"    Calculated optimal chunk size: {chunk_size:,} accounts")
    print(f"    (Available memory: {available_memory / 1024**3:.1f} GB, CPUs: {cpu_count}, Est. memory per account: {memory_per_account / 1024**2:.1f} MB)")
    
    return chunk_size

def process_chunk_to_table(
    chunk_df: pd.DataFrame,
    id_col: str,
    date_col: str,
    hour_col: Optional[str],
    activity_cols: List[str],
    categorical_cols: List[str],
    countdown_cols: List[str],
    countup_cols: List[str]
) -> pa.Table:
    """
    Process a chunk by expanding each account to its own min/max date range.
    This version correctly handles per-account lifetimes and categorical grouping.
    """
    if chunk_df.empty:
        return pa.Table.from_pandas(chunk_df, preserve_index=False)

    processed_accounts = []
    
    # Group by account ID to process each one individually
    for account_id, account_df in chunk_df.groupby(id_col, observed=True):
        # 1. Determine the individual date range for this specific account
        min_date = account_df[date_col].min()
        max_date = account_df[date_col].max()
        account_specific_dates = pd.date_range(start=min_date, end=max_date, freq='D')
        
        # 2. Create the complete index for ONLY this account
        if hour_col:
            # For hourly data
            full_index = pd.MultiIndex.from_product(
                [[account_id], account_specific_dates, range(24)],
                names=[id_col, date_col, hour_col]
            )
            indexed_account_df = account_df.set_index([id_col, date_col, hour_col])
        else:
            # For daily data
            full_index = pd.MultiIndex.from_product(
                [[account_id], account_specific_dates],
                names=[id_col, date_col]
            )
            indexed_account_df = account_df.set_index([id_col, date_col])

        # 3. Reindex this single account to its own complete date range
        filled_df = indexed_account_df.reindex(full_index).reset_index()

        # 4. Apply the filling logic as before, but only on this account's data
        # This is much safer and more efficient than grouping the whole chunk.
        
        # Categorical columns - forward fill
        if categorical_cols:
            cat_cols = [c for c in categorical_cols if c in filled_df.columns]
            if cat_cols:
                filled_df[cat_cols] = filled_df[cat_cols].ffill().bfill()
        
        # Activity columns - fill with 0
        if activity_cols:
            act_cols = [c for c in activity_cols if c in filled_df.columns]
            if act_cols:
                filled_df[act_cols] = filled_df[act_cols].fillna(0)

        # Countdown and Countup columns
        for col in countdown_cols + countup_cols:
            if col in filled_df.columns:
                # Store original non-null locations
                original_non_null = filled_df[col].notna()

                # 1. Create fill groups based on last known value
                # The cumsum of notna() creates a unique ID for each block of consecutive NaNs
                fill_group_id = original_non_null.cumsum()

                # 2. Forward-fill the column to propagate the last known value into gaps
                ffilled_col = filled_df[col].ffill()

                # 3. Calculate the number of days elapsed since the start of each fill group
                # 'transform' applies the 'first' function to each group and broadcasts the result
                # back to the original shape, which is highly efficient.
                date_of_group_start = filled_df.groupby(fill_group_id)[date_col].transform('first')
                days_since_start = (filled_df[date_col] - date_of_group_start).dt.days

                # 4. Apply the correct logic based on column type
                if col in countup_cols:
                    # Add the number of elapsed days to the forward-filled value
                    new_values = ffilled_col + days_since_start
                elif col in countdown_cols:
                    # Subtract the number of elapsed days and clip at 0
                    new_values = (ffilled_col - days_since_start).clip(lower=0)

                # 5. Only update the values that were originally NaN (i.e., the gaps)
                # This preserves the original data points and only modifies the filled gaps.
                filled_df[col] = filled_df[col].where(original_non_null, new_values)

                # Handle any NaNs at the very beginning of the series if necessary
                filled_df[col] = filled_df[col].fillna(0)
                
        processed_accounts.append(filled_df)

    # 5. Combine all processed accounts in the chunk back into one DataFrame
    final_chunk_df = pd.concat(processed_accounts, ignore_index=True)
    
    return pa.Table.from_pandas(final_chunk_df, preserve_index=False)

def process_and_write_chunk(
    chunk_idx: int,
    chunk_df: pd.DataFrame,
    output_path: str,
    id_col: str,
    date_col: str,
    hour_col: Optional[str],
    activity_cols: List[str],
    categorical_cols: List[str],
    countdown_cols: List[str],
    countup_cols: List[str]
) -> Tuple[int, bool]:
    """Process a chunk and write it to a temporary parquet file."""
    
    try:
        # Process the chunk using the new per-account logic
        table = process_chunk_to_table(
            chunk_df, 
            id_col, 
            date_col, 
            hour_col,
            activity_cols, 
            categorical_cols, 
            countdown_cols, 
            countup_cols
        )
        
        # Write to a temporary file for this chunk
        # Use a different naming pattern to avoid conflicts with the final file
        base_path = output_path.replace('.parquet', '')
        chunk_file = f"{base_path}_chunk_{chunk_idx:04d}.parquet"
        pq.write_table(table, chunk_file)
        
        return chunk_idx, True
    except Exception as e:
        print(f"\n      Error processing chunk {chunk_idx}: {e}")
        return chunk_idx, False

def fill_missing_timeseries_data_streaming(df: pd.DataFrame,
                                          output_path: str,
                                          date_col: str = 'date',
                                          id_col: str = 'account_id',
                                          hour_col: Optional[str] = None,
                                          activity_cols: Optional[List[str]] = None,
                                          categorical_cols: Optional[List[str]] = None,
                                          countdown_cols: Optional[List[str]] = None,
                                          countup_cols: Optional[List[str]] = None,
                                          derived_cols: Optional[List[str]] = None,
                                          use_parallel: bool = True,
                                          n_workers: Optional[int] = None) -> None:
    """
    Fill missing dates with appropriate values and stream results to disk.
    
    This version processes chunks in parallel and writes them to temporary files,
    then combines them into a single output file without loading everything into memory.
    """
    # Use global defaults if not provided
    if activity_cols is None:
        activity_cols = ACTIVITY_COLS
    if categorical_cols is None:
        categorical_cols = CATEGORICAL_COLS
    if countdown_cols is None:
        countdown_cols = COUNTDOWN_COLS
    if countup_cols is None:
        countup_cols = COUNTUP_COLS
    if derived_cols is None:
        derived_cols = DERIVED_COLS
    
    # Set number of workers
    if n_workers is None:
        # Use physical cores for CPU-intensive work
        n_workers = min(mp.cpu_count() // 2, 16)
    
    # Ensure date column is datetime
    df[date_col] = pd.to_datetime(df[date_col])
    
    print(f"    Using streaming approach with {'parallel' if use_parallel else 'sequential'} processing...")
    print(f"    Original shape: {df.shape}")
    print(f"    Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    
    # Get accounts
    unique_accounts = df[id_col].unique()
    n_accounts = len(unique_accounts)

    # NOTE: The get_optimal_chunk_size may be less accurate now, but it's a non-critical heuristic.
    # We can pass an average lifetime if needed, but for now this is fine.
    avg_lifetime = (df[date_col].max() - df[date_col].min()).days
    chunk_size = get_optimal_chunk_size(
        n_accounts, avg_lifetime, len(df.columns), hour_col is not None
    )
    
    # Create chunks
    chunks = []
    for i in range(0, n_accounts, chunk_size):
        chunk_accounts = unique_accounts[i:i + chunk_size]
        chunk_df = df[df[id_col].isin(chunk_accounts)]
        chunks.append(chunk_df)
    
    print(f"    Created {len(chunks)} chunks for processing...")
    print(f"    Output will be written to: {output_path}")
    
    # Process chunks and write to temporary files
    temp_files = []
    
    if use_parallel and len(chunks) > 1:
        print(f"    Using {n_workers} parallel workers...")
        
        # Create partial function with fixed parameters
        process_func = partial(
            process_and_write_chunk,
            output_path=output_path,
            id_col=id_col,
            date_col=date_col,
            hour_col=hour_col,
            activity_cols=activity_cols,
            categorical_cols=categorical_cols,
            countdown_cols=countdown_cols,
            countup_cols=countup_cols
        )
        
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(process_func, i, chunk): i 
                      for i, chunk in enumerate(chunks)}
            
            # Process completed tasks
            completed = 0
            for future in as_completed(futures):
                chunk_idx = futures[future]
                try:
                    idx, success = future.result()
                    if success:
                        base_path = output_path.replace('.parquet', '')
                        temp_files.append(f"{base_path}_chunk_{idx:04d}.parquet")
                        completed += 1
                        if completed % 10 == 0:
                            print(f"      Completed {completed}/{len(chunks)} chunks...")
                except Exception as e:
                    print(f"      Error with chunk {chunk_idx}: {e}")
                    raise
        
        print(f"      All {len(chunks)} chunks processed successfully!")
        
    else:
        # Sequential processing
        for i, chunk_df in enumerate(chunks):
            print(f"      Processing chunk {i+1}/{len(chunks)}...")
            idx, success = process_and_write_chunk(
                i, chunk_df, output_path, id_col, date_col, hour_col,
                activity_cols, categorical_cols, countdown_cols, countup_cols
            )
            if success:
                base_path = output_path.replace('.parquet', '')
                temp_files.append(f"{base_path}_chunk_{idx:04d}.parquet")
    
    # Sort temp files to maintain order
    temp_files.sort()
    
    # Combine temporary files into final output
    print(f"    Combining {len(temp_files)} temporary files into final output...")
    
    # Read the schema from the first file
    first_table = pq.read_table(temp_files[0])
    schema = first_table.schema
    
    # Create the final parquet writer
    with pq.ParquetWriter(output_path, schema) as writer:
        # Write the first table
        writer.write_table(first_table)
        del first_table
        gc.collect()
        
        # Process remaining files
        for i, temp_file in enumerate(temp_files[1:], 1):
            if i % 50 == 0:
                print(f"      Combined {i+1}/{len(temp_files)} files...")
            
            table = pq.read_table(temp_file)
            writer.write_table(table)
            del table
            gc.collect()
    
    # Clean up temporary files
    print(f"    Cleaning up temporary files...")
    for temp_file in temp_files:
        try:
            os.remove(temp_file)
        except Exception as e:
            print(f"      Warning: Could not remove {temp_file}: {e}")
    
    # Report final statistics
    final_file = pq.ParquetFile(output_path)
    num_rows = final_file.metadata.num_rows
    num_cols = len(final_file.schema)
    file_size = os.path.getsize(output_path) / (1024**3)  # GB
    
    print(f"    Successfully created: {output_path}")
    print(f"    Final shape: ({num_rows:,} rows, {num_cols} columns)")
    print(f"    File size: {file_size:.2f} GB")
    
    # Calculate expansion
    expansion_factor = num_rows / len(df) if len(df) > 0 else 0
    print(f"    Data expansion: {len(df):,} → {num_rows:,} rows ({expansion_factor:.2f}x)")

def load_data():
    """
    Load data from parquet files if they exist, otherwise load from database.
    
    Returns:
        dict: Dictionary containing all loaded dataframes
    """
    # Resolve paths relative to this script
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    RAW_DATA_DIR = PROJECT_ROOT / "raw-data"
    print(f"RAW_DATA_DIR: {RAW_DATA_DIR}")
    
    # Define file mappings
    file_mappings = {
        'daily_metrics': 'raw_metrics_daily.parquet',
        'alltime_metrics': 'raw_metrics_alltime.parquet',
        'hourly_metrics': 'raw_metrics_hourly.parquet',
        'trades_closed': 'raw_trades_closed.parquet',
        'trades_open': 'raw_trades_open.parquet',
        'plans': 'raw_plans_data.parquet',
        'regimes_daily': 'raw_mv_regime_daily_features.parquet'
    }

    db_table_mappings = {
        'daily_metrics': 'raw_metrics_daily',
        'alltime_metrics': 'raw_metrics_alltime',
        'hourly_metrics': 'raw_metrics_hourly',
        'trades_closed': 'raw_trades_closed',
        'trades_open': 'raw_trades_open',
        'plans': 'raw_plans_data',
        'regimes_daily': 'prop_trading_model.mv_regime_daily_features'
    }
    
    dataframes = {}
    
    # Check if all files exist in raw-data directory
    print(f"Checking if all files exist in {RAW_DATA_DIR}...")
    all_files_exist = all((RAW_DATA_DIR / filename).exists() for filename in file_mappings.values())
    if not all_files_exist:
        missing_files = [filename for filename in file_mappings.values() if not (RAW_DATA_DIR / filename).exists()]
        print(f"Missing files: {missing_files}")
    print(f"all_files_exist: {all_files_exist}")
    
    if all_files_exist:
        print("Loading data from parquet files...")
        for df_name, filename in file_mappings.items():
            filepath = RAW_DATA_DIR / filename
            print(f"  Loading {filename}...")
            dataframes[df_name] = pd.read_parquet(filepath)
    else:
        print("Loading data from database...")
        _NO_TIMEOUT = 0  # PostgreSQL interprets 0 as "never timeout"
        
        # Iterate over the unified mapping to ensure consistent keys
        for df_name, table_name in db_table_mappings.items():
            print(f"  Loading {df_name} (from table: {table_name}) from database...")

            query = f"SELECT * FROM {table_name}"

            # Use the logical `df_name` as the key for the dictionary
            df = execute_query_df(query, timeout_seconds=_NO_TIMEOUT)
            dataframes[df_name] = df

            # Use the coresponding filename from file_mappings to save the parquet file
            output_filename = file_mappings[df_name]
            output_path = RAW_DATA_DIR / output_filename
            print(f"  Saving {df_name} to {output_path}")
            df.to_parquet(output_path)

    return dataframes

def process_dataframes_streaming(dataframes: Dict[str, pd.DataFrame], metrics_to_process: str = 'all') -> None:
    """
    Process all dataframes using streaming approach for memory efficiency.
    
    Parameters:
        dataframes (dict): Dictionary of dataframes to process
    """
    # Resolve paths
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
    CLEANED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Define which dataframes need time series processing
    timeseries_dfs = {'daily_metrics', 'hourly_metrics'}
    
    # Output filename mappings
    output_mappings = {
        'daily_metrics': 'daily_metrics_df.parquet',
        'alltime_metrics': 'alltime_metrics_df.parquet',
        'hourly_metrics': 'hourly_metrics_df.parquet',
        'trades_closed': 'trades_closed_df.parquet',
        'trades_open': 'trades_open_df.parquet',
        'plans': 'plans_df.parquet',
        'regimes_daily': 'regimes_daily_df.parquet'
    }
    
    print("\nProcessing non-timeseries dataframes...")
    # First, process and save non-timeseries dataframes to free memory
    non_timeseries_keys = [df_name for df_name in dataframes.keys() if df_name not in timeseries_dfs]
    
    for df_name in non_timeseries_keys:
        if df_name in dataframes:
            print(f"  Optimizing and saving {df_name}...")
            optimized_df = optimize_dtypes(dataframes[df_name])
            
            # Save immediately
            if df_name in output_mappings:
                filepath = CLEANED_DATA_DIR / output_mappings[df_name]
                optimized_df.to_parquet(filepath, engine='pyarrow')
                print(f"    Saved to {filepath}")
            
            # Clear original dataframe from memory
            del dataframes[df_name]
            del optimized_df
            gc.collect()
    
    # Now process timeseries dataframes using streaming
    print("\nProcessing timeseries dataframes with streaming...")
    
    # Process daily metrics
    if metrics_to_process in ['all', 'daily'] and 'daily_metrics' in dataframes:
        print("  Processing daily_metrics...")
        print(f"    Original shape: {dataframes['daily_metrics'].shape}")
        print(f"    Memory usage: {dataframes['daily_metrics'].memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        print("  Optimizing daily_metrics dtypes...")
        daily_df = optimize_dtypes(dataframes['daily_metrics'])
        print(f"    Optimized memory usage: {daily_df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        # Clear original from memory
        del dataframes['daily_metrics']
        gc.collect()
        
        print(f"  Filling missing time series data for daily_metrics...")
        
        # Use streaming function
        output_path = CLEANED_DATA_DIR / output_mappings['daily_metrics']
        fill_missing_timeseries_data_streaming(
            daily_df,
            output_path=str(output_path),
            date_col='date',
            id_col='account_id',
            hour_col=None,
            use_parallel=True
        )
        
        del daily_df
        gc.collect()
        print("  Daily metrics processing complete!")
    
    # Process hourly metrics
    if metrics_to_process in ['all', 'hourly'] and 'hourly_metrics' in dataframes:
        print("\n  Processing hourly_metrics...")
        print(f"    Original shape: {dataframes['hourly_metrics'].shape}")
        print(f"    Memory usage: {dataframes['hourly_metrics'].memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        print("  Optimizing hourly_metrics dtypes...")
        hourly_df = optimize_dtypes(dataframes['hourly_metrics'], exclude_from_categorical=['max_val_to_eqty_open_pos'])
        print(f"    Optimized memory usage: {hourly_df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        # Clear original from memory
        del dataframes['hourly_metrics']
        gc.collect()
        
        print(f"  Filling missing time series data for hourly_metrics...")
        
        # Use streaming function
        output_path = CLEANED_DATA_DIR / output_mappings['hourly_metrics']
        fill_missing_timeseries_data_streaming(
            hourly_df,
            output_path=str(output_path),
            date_col='date',
            id_col='account_id',
            hour_col='hour',
            use_parallel=True
        )
        
        del hourly_df
        gc.collect()
        print("  Hourly metrics processing complete!")
    
    print("\nAll dataframes processed successfully!")

def main() -> None:
    """
    Main function to orchestrate data preparation pipeline with streaming.
    """

    parser = argparse.ArgumentParser(description="Data preparation pipeline with streaming.")
    parser.add_argument(
        '--metrics-type',
        type=str,
        choices=['all', 'daily', 'hourly'],
        default='all',
        help="Specify which time-series metrics to process. Default is 'all'."
    )
    args = parser.parse_args()
    print(f"Starting data preparation pipeline (processing: {args.metrics_type})...")

    # Step 1: Load data
    dataframes = load_data()
    print(f"\nLoaded {len(dataframes)} dataframes")
    
    # Step 2: Process dataframes with streaming approach
    process_dataframes_streaming(dataframes, metrics_to_process=args.metrics_type)
    
    print("\nData preparation complete!")
    
    # Print summary statistics
    print("\nSummary of processed dataframes:")
    PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
    CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
    
    output_mappings = {
        'daily_metrics': 'daily_metrics_df.parquet',
        'alltime_metrics': 'alltime_metrics_df.parquet',
        'hourly_metrics': 'hourly_metrics_df.parquet',
        'trades_closed': 'trades_closed_df.parquet',
        'trades_open': 'trades_open_df.parquet',
        'plans': 'plans_df.parquet',
        'regimes_daily': 'regimes_daily_df.parquet'
    }
    
    for df_name, filename in output_mappings.items():
        filepath = CLEANED_DATA_DIR / filename
        if filepath.exists():
            # Get shape efficiently using parquet metadata
            parquet_file = pq.ParquetFile(filepath)
            num_rows = parquet_file.metadata.num_rows
            num_cols = len(parquet_file.schema)
            file_size = os.path.getsize(filepath) / (1024**3)  # GB
            print(f"  {df_name}: {num_rows:,} rows × {num_cols} columns ({file_size:.2f} GB)")


# Example usage
if __name__ == "__main__":
    main()