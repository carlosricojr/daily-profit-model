#!/usr/bin/env python
"""Build train/val/test feature matrices using the pre-saved
`daily_feature_defs_v1.joblib` artefact.

Usage
-----
uv run --env-file .env.local -- python -m src.feature_engineering.ft_build_feature_matrix

The script:
1. Loads raw tables from the (local) replica of Supabase PostgreSQL.
2. Re-creates an EntitySet identical to the one used when the feature
   definitions were generated.
3. Splits the data chronologically (train → val → test) and materialises
   the feature matrix for each split with `ft.calculate_feature_matrix`.
4. Writes each matrix to `artefacts/{split}_matrix.parquet`.

Heavy calculations are done with chunked pandas with optional date chunking to save memory through the . ; you can later swap in
Dask by editing the `USE_DASK` flag.
"""

from __future__ import annotations

import pathlib
import joblib
import pandas as pd
import featuretools as ft
from datetime import timedelta
from utils.database import execute_query_df
from typing import Any  # needed for typed dicts inside main()
import gc
import xxhash
import traceback
from .utils import prepare_dataframe, make_daily_id, make_hash_id, split_date_range_into_chunks
from .dtype_utils import optimize_dtypes
import psutil

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Resolve repository root (two levels up from current file: src/feature_engineering/)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
# Use an absolute artefacts directory at the project root
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
# Ensure the directory exists
ARTEFACT_DIR.mkdir(exist_ok=True)

FEATURE_DEF_PATH = ARTEFACT_DIR / "daily_feature_defs_v1.joblib"

# Choose whether to use Dask for very large dataframes. With 11GB EntitySet and 128GB total RAM, we don't need to use Dask.
# General rule: if the EntitySet > 50% of total RAM, use Dask.
USE_DASK = False

# Default pandas chunk size; still applies when Dask is off.
# Reduced for better memory efficiency
CHUNK_SIZE = 100_000

# Date chunk size for training data (in days)
# Note: With 7 days, we get ~70 chunks for 487 days of data
# Consider increasing to 15-30 days for faster processing
DATE_CHUNK_DAYS = 7

# Train/validation/test split configuration
# Use proportions of the full historical span so that the script adapts
# automatically when more data become available.
TRAIN_SPAN_DAYS: int | None = None  # None == use everything up to validation split

# Fraction of available days to allocate to validation and test sets.
VAL_FRAC: float = 0.05   # 5 % validation window
TEST_FRAC: float = 0.05  # 5 % hold-out window

TESTING = False

# ---------------------------------------------------------------------------
# Lazy Dask cluster initialisation helpers (moved out of top-level execution)
# ---------------------------------------------------------------------------

def _init_dask_cluster():
    """Create and return a local Dask cluster when USE_DASK is True.

    Returns
    -------
    dict
        Keyword arguments to pass into Featuretools (`dask_kwargs`). An empty
        dict is returned when Dask is disabled. The cluster object is kept
        alive by holding a reference in this dictionary.
    """
    if not USE_DASK:
        return {}

    # Import locally to avoid the cost and side-effects when Dask is unused.
    from dask.distributed import LocalCluster

    print("Starting local Dask cluster …")
    # With 11GB EntitySet and 128GB total RAM
    cluster = LocalCluster(
        n_workers=4,  
        threads_per_worker=4,  
        memory_limit="25GB",  
    )
    return {
        "cluster": cluster,
        'diagnostics_port': 8787,
        }

# ---------------------------------------------------------------------------
# Main execution entry-point
# ---------------------------------------------------------------------------

def main() -> None:  
    """Orchestrate the building of train/val/test feature matrices.

    The function encapsulates all heavy work so that importing this module in
    subprocesses (e.g. Dask workers) has no side-effects.
    """
    # Lazily create the Dask cluster (if requested) **inside** the protected
    # scope so that worker processes merely importing this file do *not*
    # attempt to spawn further children.
    dask_kwargs = _init_dask_cluster()

    # -----------------------------------------------------------------------
    # Load data from cleaned parquet files
    # -----------------------------------------------------------------------
    print("Loading cleaned data from parquet files...")
    
    # Resolve paths
    CLEANED_DATA_DIR = PROJECT_ROOT / "artefacts" / "cleaned_data"
    
    # Load all dataframes
    DAILY_METRICS = pd.read_parquet(CLEANED_DATA_DIR / "daily_metrics_df.parquet")
    ALLTIME_METRICS = pd.read_parquet(CLEANED_DATA_DIR / "alltime_metrics_df.parquet")
    HOURLY_METRICS = pd.read_parquet(CLEANED_DATA_DIR / "hourly_metrics_df.parquet")
    TRADES_CLOSED = pd.read_parquet(CLEANED_DATA_DIR / "trades_closed_df.parquet")
    TRADES_OPEN = pd.read_parquet(CLEANED_DATA_DIR / "trades_open_df.parquet")
    PLANS = pd.read_parquet(CLEANED_DATA_DIR / "plans_df.parquet")
    REGIMES_DAILY = pd.read_parquet(CLEANED_DATA_DIR / "regimes_daily_df.parquet")
    
    print(f"Loaded data shapes:")
    print(f"  daily_metrics: {DAILY_METRICS.shape}")
    print(f"  alltime_metrics: {ALLTIME_METRICS.shape}")
    print(f"  hourly_metrics: {HOURLY_METRICS.shape}")
    print(f"  trades_closed: {TRADES_CLOSED.shape}")
    print(f"  trades_open: {TRADES_OPEN.shape}")
    print(f"  plans: {PLANS.shape}")
    print(f"  regimes_daily: {REGIMES_DAILY.shape}")
    
    # Apply testing filters if needed
    if TESTING == True:
        testing_filters = {
            'start': pd.Timestamp('2025-01-01'),
            'end': pd.Timestamp('2025-01-31'),
        }
        
        print(f"Applying testing filters: {testing_filters['start']} to {testing_filters['end']}")
        
        # Filter date-based dataframes
        DAILY_METRICS = DAILY_METRICS[
            (DAILY_METRICS['date'] >= testing_filters['start']) & 
            (DAILY_METRICS['date'] <= testing_filters['end'])
        ].copy()
        
        HOURLY_METRICS = HOURLY_METRICS[
            (HOURLY_METRICS['date'] >= testing_filters['start']) & 
            (HOURLY_METRICS['date'] <= testing_filters['end'])
        ].copy()
        
        TRADES_CLOSED = TRADES_CLOSED[
            (pd.to_datetime(TRADES_CLOSED['close_time']) >= testing_filters['start']) & 
            (pd.to_datetime(TRADES_CLOSED['close_time']) <= testing_filters['end'])
        ].copy()
        
        TRADES_OPEN = TRADES_OPEN[
            (pd.to_datetime(TRADES_OPEN['open_time']) >= testing_filters['start']) & 
            (pd.to_datetime(TRADES_OPEN['open_time']) <= testing_filters['end'])
        ].copy()
        
        print(f"Filtered data shapes:")
        print(f"  daily_metrics: {DAILY_METRICS.shape}")
        print(f"  hourly_metrics: {HOURLY_METRICS.shape}")
        print(f"  trades_closed: {TRADES_CLOSED.shape}")
        print(f"  trades_open: {TRADES_OPEN.shape}")

    # -------------------------------------------------------------------
    # Exclude data that belongs to trader_ids present in the exclusion list
    # -------------------------------------------------------------------

    try:
        excluded_df = execute_query_df(
            "SELECT trader_id FROM prop_trading_model.excluded_traders",
            timeout_seconds=_NO_TIMEOUT,
        )
        EXCLUDED_TRADER_IDS = set(excluded_df["trader_id"].astype(str))
    except Exception as exc:  # DB connectivity issues should not abort the run
        print(
            f"WARNING: could not fetch excluded_traders list – proceeding without exclusions (" \
            f"{type(exc).__name__}: {exc})"
        )
        EXCLUDED_TRADER_IDS = set()

    if EXCLUDED_TRADER_IDS:
        print(f"Applying exclusion filter for {len(EXCLUDED_TRADER_IDS):,} trader_id(s)…")

        def _exclude(df: pd.DataFrame, name: str) -> pd.DataFrame:
            """Return *df* with rows dropped where trader_id is in the exclusion list."""
            if "trader_id" not in df.columns:
                return df

            before = len(df)
            df = df[~df["trader_id"].astype(str).isin(EXCLUDED_TRADER_IDS)].copy()
            dropped = before - len(df)
            if dropped:
                print(f"  {name}: removed {dropped:,} rows (trader exclusion)")
            return df

        DAILY_METRICS   = _exclude(DAILY_METRICS, "DAILY_METRICS")
        ALLTIME_METRICS = _exclude(ALLTIME_METRICS, "ALLTIME_METRICS")
        HOURLY_METRICS  = _exclude(HOURLY_METRICS, "HOURLY_METRICS")
    # -------------------------------------------------------------------

    # Note: dtypes should already be optimized from the cleaned parquet files
    # The prepare_data.py pipeline already applies optimize_dtypes before saving
    # If needed for safety after exclusions, uncomment the lines below:
    # DAILY_METRICS = optimize_dtypes(DAILY_METRICS)
    # ALLTIME_METRICS = optimize_dtypes(ALLTIME_METRICS)
    # HOURLY_METRICS = optimize_dtypes(HOURLY_METRICS)
    # TRADES_CLOSED = optimize_dtypes(TRADES_CLOSED)
    # TRADES_OPEN = optimize_dtypes(TRADES_OPEN)
    # PLANS = optimize_dtypes(PLANS)
    # REGIMES_DAILY = optimize_dtypes(REGIMES_DAILY)

    # -----------------------------------------------------------------------
    # Key engineering
    # -----------------------------------------------------------------------
    print("Engineering surrogate keys …")

    for _df in (DAILY_METRICS, ALLTIME_METRICS, HOURLY_METRICS, TRADES_CLOSED, TRADES_OPEN):
        if "account_id" in _df.columns:
            _df["account_id"] = _df["account_id"].astype(str)

    DAILY_METRICS["daily_id"]  = make_daily_id(DAILY_METRICS["account_id"],  DAILY_METRICS["date"])
    HOURLY_METRICS["daily_id"] = make_daily_id(HOURLY_METRICS["account_id"], HOURLY_METRICS["date"])
    TRADES_CLOSED["daily_id"]  = make_daily_id(TRADES_CLOSED["account_id"],  TRADES_CLOSED["trade_date"])
    TRADES_OPEN["daily_id"]    = make_daily_id(TRADES_OPEN["account_id"],    TRADES_OPEN["trade_date"])

    HOURLY_METRICS["hourly_id"] = (
        HOURLY_METRICS["account_id"].astype(str) + 
        "_" 
        + HOURLY_METRICS["datetime"].astype(str)
    ).map(xxhash.xxh64_intdigest).astype("uint64")

    REGIMES_DAILY = REGIMES_DAILY.sort_values("date").drop_duplicates("date", keep="last")
    REGIMES_DAILY["regime_daily_id"] = pd.to_datetime(REGIMES_DAILY["date"]).dt.strftime("%Y-%m-%d").map(xxhash.xxh64_intdigest).astype("uint64")
    DAILY_METRICS["regime_daily_id"] = pd.to_datetime(DAILY_METRICS["date"]).dt.strftime("%Y-%m-%d").map(xxhash.xxh64_intdigest).astype("uint64")

    TRADES_CLOSED["trade_id"] = make_hash_id(
        TRADES_CLOSED, ["ticket", "login", "open_time", "close_time", "platform"]
    )
    TRADES_OPEN["trade_id"] = make_hash_id(
        TRADES_OPEN, ["ticket", "login", "open_time", "platform", "trade_date"]
    )

    # -----------------------------------------------------------------------
    # Build EntitySet
    # -----------------------------------------------------------------------
    print("Building EntitySet …")
    ES = ft.EntitySet(id="daily_profit_model")

    DATAFRAMES = {
        "daily_metrics":   (DAILY_METRICS, "daily_id", "date"),
        "alltime_metrics": (ALLTIME_METRICS, "account_id"),
        "plans":           (PLANS, "plan_id"),
        "regimes_daily":   (REGIMES_DAILY, "regime_daily_id", "date"),
        "hourly_metrics":  (HOURLY_METRICS, "hourly_id", "datetime"),
        "trades_closed":   (TRADES_CLOSED, "trade_id", "close_time"),
        "trades_open":     (TRADES_OPEN, "trade_id", "open_time"),
    }

    for name, args in DATAFRAMES.items():
        df_raw, index_col, *maybe_time_index = args

        df_clean, logical_types = prepare_dataframe(name, df_raw)

        add_df_kwargs = {
            "dataframe_name": name,
            "dataframe": df_clean,
            "index": index_col,
        }
        if maybe_time_index:
            add_df_kwargs["time_index"] = maybe_time_index[0]
        if logical_types:
            add_df_kwargs["logical_types"] = logical_types

        ES = ES.add_dataframe(**add_df_kwargs)

    RELATIONSHIPS = [
        ("alltime_metrics", "account_id", "daily_metrics", "account_id"),
        ("plans", "plan_id", "daily_metrics", "plan_id"),
        ("regimes_daily", "regime_daily_id", "daily_metrics", "regime_daily_id"),
        ("daily_metrics", "daily_id", "hourly_metrics", "daily_id"),
        ("daily_metrics", "daily_id", "trades_closed", "daily_id"),
        ("daily_metrics", "daily_id", "trades_open", "daily_id"),
    ]
    for p_df, p_col, c_df, c_col in RELATIONSHIPS:
        ES = ES.add_relationship(p_df, p_col, c_df, c_col)

    # Debug: Check EntitySet size
    es_size_bytes = ES.__sizeof__()
    es_size_gb = es_size_bytes / (1024**3)
    print(f"EntitySet size: {es_size_gb:.2f} GB ({es_size_bytes:,} bytes)")

    # Also check individual dataframe sizes
    for df_name in ES.dataframe_dict:
        df = ES[df_name]
        df_memory = df.memory_usage(deep=True).sum()
        print(f"  {df_name}: {df_memory / (1024**2):.2f} MB, shape: {df.shape}")

    # -----------------------------------------------------------------------
    # Load feature definitions
    # -----------------------------------------------------------------------
    print("Loading feature definitions …")
    FEATURE_DEFS = joblib.load(FEATURE_DEF_PATH)

    # -----------------------------------------------------------------------
    # Determine date splits
    # -----------------------------------------------------------------------
    print("Creating cutoff tables …")
    max_date = DAILY_METRICS["date"].max()
    min_date = DAILY_METRICS["date"].min()

    total_days = (max_date - min_date).days + 1  # inclusive span
    test_days = max(1, int(total_days * TEST_FRAC))
    val_days  = max(1, int(total_days * VAL_FRAC))

    # Ensure we never allocate more days than available
    if test_days + val_days >= total_days:
        # Fallback to fixed minimum of 1 day each
        test_days = max(1, int(total_days * 0.2))
        val_days  = max(1, int(total_days * 0.15))

    test_start = max_date - timedelta(days=test_days)
    val_start  = test_start - timedelta(days=val_days)

    # CRITICAL: To predict profit for day D, we use features from day D-1
    # This prevents lookahead bias. The cutoff time is the END of day D-1.
    cutoffs = {}
    
    # Filter out the first day since we can't predict it (no D-1 data)
    min_predictable_date = min_date + timedelta(days=1)
    
    # Test set: predict profits for dates >= test_start using data up to previous day
    test_df = DAILY_METRICS.loc[
        (DAILY_METRICS["date"] >= test_start) & (DAILY_METRICS["date"] > min_date),
        ["daily_id", "date"]
    ].copy()
    test_df["cutoff_time"] = test_df["date"] - timedelta(days=1)
    test_df["target_date"] = test_df["date"]  # Keep original date for clarity
    cutoffs["test"] = test_df[["daily_id", "cutoff_time", "target_date"]]
    
    # Validation set
    val_df = DAILY_METRICS.loc[
        (DAILY_METRICS["date"] >= val_start) & (DAILY_METRICS["date"] < test_start) & (DAILY_METRICS["date"] > min_date), 
        ["daily_id", "date"]
    ].copy()
    val_df["cutoff_time"] = val_df["date"] - timedelta(days=1)
    val_df["target_date"] = val_df["date"]
    cutoffs["val"] = val_df[["daily_id", "cutoff_time", "target_date"]]
    
    # Training set (exclude first day)
    train_df = DAILY_METRICS.loc[
        (DAILY_METRICS["date"] < val_start) & (DAILY_METRICS["date"] >= min_predictable_date), 
        ["daily_id", "date"]
    ].copy()
    train_df["cutoff_time"] = train_df["date"] - timedelta(days=1)
    train_df["target_date"] = train_df["date"]
    cutoffs["train"] = train_df[["daily_id", "cutoff_time", "target_date"]]
    
    # Log split information
    for split_name, df in cutoffs.items():
        if not df.empty:
            print(f"{split_name}: {len(df)} instances, "
                  f"cutoff dates from {df['cutoff_time'].min()} to {df['cutoff_time'].max()}, "
                  f"predicting for {df['target_date'].min()} to {df['target_date'].max()}")
    
    # Rename columns for Featuretools (keep target_date for reference)
    for df in cutoffs.values():
        df.rename(columns={"daily_id": "instance_id", "cutoff_time": "time"}, inplace=True)

    # -----------------------------------------------------------------------
    # Materialise matrices
    # -----------------------------------------------------------------------
    print("Materialising feature matrices …")
    
    # Process test and validation sets normally (they're small)
    for split_name in ["test", "val"]:
        if split_name not in cutoffs or cutoffs[split_name].empty:
            print(f"{split_name}: no rows, skipping")
            continue
            
        cutoff_df = cutoffs[split_name]
        print(f"\nProcessing {split_name} set...")
        
        calc_kwargs: dict[str, Any] = dict(
            features=FEATURE_DEFS,
            entityset=ES,
            cutoff_time=cutoff_df,
            cutoff_time_in_index=True,
            chunk_size=CHUNK_SIZE,
            verbose=True
        )
        if dask_kwargs:
            calc_kwargs["dask_kwargs"] = dask_kwargs

        matrix = ft.calculate_feature_matrix(**calc_kwargs)
        
        # Extract multiple target values for multi-model approach
        # The matrix index contains daily_ids for the target dates
        target_daily_ids = matrix.index
        
        # Define target columns for different models
        # These are the key metrics we want to predict for day D
        target_columns = [
            "net_profit",            # Primary target: daily PnL
            "gross_profit",          # Revenue before costs
            "gross_loss",            # Total losses for the day
            "trades_placed",         # Number of trades (activity level)
            "win_rate",              # Daily win percentage
            "lots",                  # Total volume traded
            "risk_adj_ret",          # Risk Adjusted Return 
            "max_drawdown",          # Risk metric
            "most_traded_symbol",    # Most Traded Symbol 
            "mean_firm_margin"       # Estimated Average Margin Usage 
        ]
        
        # Extract all available target columns
        available_targets = [col for col in target_columns if col in DAILY_METRICS.columns]
        targets = DAILY_METRICS.loc[
            DAILY_METRICS["daily_id"].isin(target_daily_ids), 
            ["daily_id"] + available_targets
        ].set_index("daily_id")
        
        # Align targets with matrix and add as columns with "target_" prefix
        # Use concat to avoid fragmentation warning
        target_columns_dict = {f"target_{col}": targets[col] for col in available_targets}
        target_df = pd.DataFrame(target_columns_dict, index=matrix.index)
        matrix = pd.concat([matrix, target_df], axis=1)
        
        if "target_net_profit" in matrix.columns:
            # Binary classification targets
            matrix["target_is_profitable"] = (matrix["target_net_profit"] > 0).astype(int)
            matrix["target_is_highly_profitable"] = (matrix["target_net_profit"] > matrix["target_net_profit"].quantile(0.9)).astype(int)
        
        # Save the complete dataset (features + target)
        path = ARTEFACT_DIR / f"{split_name}_matrix.parquet"
        matrix.to_parquet(path, engine="pyarrow")
        print(f"{split_name}: {matrix.shape} → {path}")
        if 'target_net_profit' in matrix.columns:
            print(f"  Target stats: mean={matrix['target_net_profit'].mean():.2f}, "
                  f"std={matrix['target_net_profit'].std():.2f}, "
                  f"nulls={matrix['target_net_profit'].isna().sum()}")
        proc_mem_gb = psutil.Process().memory_info().rss / (1024**3)
        print(f"  Memory usage before: {proc_mem_gb:.2f} GB")

        del matrix
        gc.collect()

    # Clean up memory
    del DAILY_METRICS, ALLTIME_METRICS, HOURLY_METRICS, TRADES_CLOSED, TRADES_OPEN, PLANS, REGIMES_DAILY
    gc.collect()
        
    # -----------------------------------------------------------------------
    # Process training set in chunks (memory-efficient)
    # -----------------------------------------------------------------------
    if "train" in cutoffs and not cutoffs["train"].empty:
        print("\nProcessing training set in chunks...")
        train_cutoff_df = cutoffs["train"]
        
        # Get date range for training data
        train_dates = train_cutoff_df["target_date"].sort_values()
        train_start = train_dates.min()
        train_end = train_dates.max()
        
        # Split into date chunks
        date_chunks = split_date_range_into_chunks(train_start, train_end, chunk_days=DATE_CHUNK_DAYS)
        print(f"Training data spans {train_start} to {train_end}")
        print(f"Split into {len(date_chunks)} chunks of {DATE_CHUNK_DAYS} days each")
        
        train_matrices = []
        
        for i, (chunk_start, chunk_end) in enumerate(date_chunks):
            print(f"\nProcessing chunk {i+1}/{len(date_chunks)}: {chunk_start} to {chunk_end}")
            
            try:
                # Filter cutoff times for this chunk
                chunk_mask = (train_cutoff_df["target_date"] >= chunk_start) & (train_cutoff_df["target_date"] < chunk_end)
                chunk_cutoff_df = train_cutoff_df[chunk_mask].copy()
                
                if chunk_cutoff_df.empty:
                    print(f"  Chunk {i+1} is empty, skipping...")
                    continue
                    
                print(f"  Chunk has {len(chunk_cutoff_df)} instances")
                
                # Calculate features for this chunk
                calc_kwargs: dict[str, Any] = dict(
                    features=FEATURE_DEFS,
                    entityset=ES,
                    cutoff_time=chunk_cutoff_df[["instance_id", "time"]],  # Only pass required columns
                    cutoff_time_in_index=True,
                    chunk_size=CHUNK_SIZE,
                    verbose=True
                )
                if dask_kwargs:
                    calc_kwargs["dask_kwargs"] = dask_kwargs
                
                proc = psutil.Process()
                mem_before_gb = proc.memory_info().rss / (1024**3)
                print(f"  Starting feature calculation (mem: {mem_before_gb:.2f} GB)...")

                chunk_matrix = ft.calculate_feature_matrix(**calc_kwargs)

                mem_after_gb = proc.memory_info().rss / (1024**3)
                delta = mem_after_gb - mem_before_gb
                print(
                    f"  Feature calculation complete. Matrix shape: {chunk_matrix.shape}\n"
                    f"  Memory usage: {mem_before_gb:.2f} → {mem_after_gb:.2f} GB (Δ {delta:+.2f} GB)"
                )
            
                # For training chunks, save features only (targets will be added later)
                chunk_path = ARTEFACT_DIR / f"train_chunk_{i}_features.parquet"
                chunk_matrix.to_parquet(chunk_path, engine="pyarrow")
                print(f"  Saved features: {chunk_matrix.shape} → {chunk_path}")
                
                train_matrices.append(chunk_path)
                
                # Clear memory
                del chunk_matrix
                gc.collect()
                
            except Exception as e:
                print(f"  ERROR in chunk {i+1}: {type(e).__name__}: {str(e)}")
                traceback.print_exc()
                
                # Try to save what we have if features were calculated
                if 'chunk_matrix' in locals():
                    error_path = ARTEFACT_DIR / f"train_chunk_{i}_error.parquet"
                    try:
                        chunk_matrix.to_parquet(error_path, engine="pyarrow")
                        print(f"  Saved partial results to {error_path}")
                    except:
                        pass
                
                # Clean up and continue with next chunk
                if 'chunk_matrix' in locals():
                    del chunk_matrix
                gc.collect()
                continue
        
        # Skip combining chunks here - will be done after adding targets
        if train_matrices:
            print(f"\nSuccessfully created {len(train_matrices)} training feature chunks.")
            print("Targets will be added in a separate pass to avoid memory issues.")
        else:
            print("\nWARNING: No training chunks were successfully processed!")
    
    print("\nFinished building feature matrices.")


if __name__ == "__main__":
    main()
