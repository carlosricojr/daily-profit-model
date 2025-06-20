import os
import pandas as pd
import pyarrow.parquet as pq
import random
import numpy as np
import pathlib  # Ensure pathlib is imported
from typing import Set, List, Dict, Optional

# --- Configuration ---
# Number of accounts to randomly sample for the detailed "hole" check.
# This keeps memory usage low while providing a statistically significant validation.
SAMPLE_SIZE = 50
# If the number of accounts with holes exceeds this, stop reporting them to keep the log clean.
MAX_HOLES_TO_REPORT = 10


def review_column_datatypes(parquet_file: pq.ParquetFile) -> None:
    """
    Reads the schema from a Parquet file and prints a report of column data types,
    suggesting potential optimizations.

    Args:
        parquet_file: An opened PyArrow ParquetFile object.
    """
    print("\n--- 3. Column DataType Review ---")
    schema = parquet_file.schema

    optimizations = {
        "potential_int32": [],
        "potential_float32": [],
        "potential_categorical": []  # Note: PyArrow handles this well with dictionary encoding
    }

    print(f"{'Column Name':<40} {'Data Type':<20} {'Suggestion'}")
    print("-" * 80)

    for i in range(len(schema)):
        field = schema.field(i)
        col_name = field.name
        dtype = str(field.type)
        suggestion = ""

        if dtype == 'int64':
            suggestion = "Consider int32 if values are within ±2.1 billion"
            optimizations["potential_int32"].append(col_name)
        elif dtype == 'double':  # float64 in pyarrow
            suggestion = "Consider float32 (float) for ~7 decimal precision"
            optimizations["potential_float32"].append(col_name)
        elif 'string' in dtype and col_name not in ['account_id', 'trader_id', 'login']:
            # High cardinality strings are fine, but low cardinality ones are candidates for categorical
            suggestion = "Consider 'category' dtype in pandas if cardinality is low"
            optimizations["potential_categorical"].append(col_name)

        print(f"{col_name:<40} {dtype:<20} {suggestion}")

    print("\n[Summary of Optimization Suggestions]")
    if optimizations["potential_int32"]:
        print(f"  - {len(optimizations['potential_int32'])} columns are int64. Check if int32 is sufficient.")
    if optimizations["potential_float32"]:
        print(f"  - {len(optimizations['potential_float32'])} columns are float64 (double). Check if float32 is sufficient.")
    if optimizations["potential_categorical"]:
        print(f"  - {len(optimizations['potential_categorical'])} string columns could potentially be categorical in pandas.")
    print("  Note: The `prepare_data_streaming.py` script already runs `optimize_dtypes`,")
    print("        so these types are likely already optimized based on data ranges.")


def get_unique_accounts_streaming(parquet_file: pq.ParquetFile) -> Set[str]:
    """
    Streams through a Parquet file to find all unique account_id values
    without loading the entire file into memory.

    Args:
        parquet_file: An opened PyArrow ParquetFile object.

    Returns:
        A set containing all unique account_id strings.
    """
    print("\n--- 1. Unique Account ID Count ---")
    print("Streaming file to count unique accounts...")

    unique_ids = set()
    for batch in parquet_file.iter_batches(columns=['account_id']):
        unique_ids.update(batch.to_pandas()['account_id'].unique())

    print(f"Found {len(unique_ids):,} unique account_id values.")
    return unique_ids


def check_data_gaps_sampled(
    file_path: str,
    parquet_file: pq.ParquetFile,
    unique_ids: Set[str],
    metric_type: str
) -> None:
    """
    Checks for missing data points ("holes") for a random sample of accounts.

    Args:
        file_path: Path to the Parquet file.
        parquet_file: An opened PyArrow ParquetFile object.
        unique_ids: A set of all unique account IDs.
        metric_type: Either 'daily' or 'hourly'.
    """
    print(f"\n--- 2. Data Gap ('Holes') Analysis ({metric_type.capitalize()}) ---")

    if not unique_ids:
        print("No accounts found to sample. Skipping gap check.")
        return

    # Take a random sample of accounts
    num_to_sample = min(SAMPLE_SIZE, len(unique_ids))
    sampled_ids = random.sample(list(unique_ids), num_to_sample)
    print(f"Randomly selected {num_to_sample} accounts (out of {len(unique_ids):,}) for a detailed check.")

    # Efficiently read data only for the sampled accounts
    print("Loading data for sampled accounts...")
    try:
        data = pq.read_table(
            file_path,
            filters=[('account_id', 'in', sampled_ids)],
            columns=['account_id', 'date', 'hour'] if metric_type == 'hourly' else ['account_id', 'date']
        ).to_pandas()
        data['date'] = pd.to_datetime(data['date'])
    except Exception as e:
        print(f"Error reading sampled data: {e}")
        return

    accounts_with_holes = {}

    print("Analyzing for gaps...")
    grouped = data.groupby('account_id')

    for account_id, df in grouped:
        if metric_type == 'daily':
            min_date, max_date = df['date'].min(), df['date'].max()
            expected_dates = pd.date_range(start=min_date, end=max_date, freq='D')

            if len(df) != len(expected_dates):
                missing_dates = sorted(list(set(expected_dates) - set(df['date'])))
                accounts_with_holes[account_id] = f"Missing {len(missing_dates)} days. Examples: {missing_dates[:3]}"

        elif metric_type == 'hourly':
            # Group by date to check hours within each day
            for date, date_df in df.groupby('date'):
                if len(date_df) < 24:
                    present_hours = set(date_df['hour'])
                    missing_hours = sorted(list(set(range(24)) - present_hours))
                    key = f"{account_id} on {date.date()}"
                    accounts_with_holes[key] = f"Missing {len(missing_hours)} hours. Examples: {missing_hours[:3]}"

        if len(accounts_with_holes) >= MAX_HOLES_TO_REPORT:
            break

    # --- Report Findings ---
    if not accounts_with_holes:
        print("\n[Result] PASSED: No data gaps found in the sampled accounts.")
    else:
        print(f"\n[Result] FAILED: Found data gaps in {len(accounts_with_holes)} of the {num_to_sample} sampled accounts.")
        print("This may indicate an issue in the `fill_missing_timeseries_data_streaming` logic.")
        print("--- Accounts with Detected Holes (Up to 10 examples) ---")
        for i, (account, issue) in enumerate(accounts_with_holes.items()):
            if i >= MAX_HOLES_TO_REPORT:
                print(f"  ...and {len(accounts_with_holes) - MAX_HOLES_TO_REPORT} more.")
                break
            print(f"  - Account/Date: {account:<50} Issue: {issue}")


def analyze_file(file_path: str, metric_type: str):
    """
    Main analysis function to run all checks on a given Parquet file.

    Args:
        file_path: The full path to the Parquet file.
        metric_type: Either 'daily' or 'hourly'.
    """
    if not os.path.exists(file_path):
        print(f"\nERROR: File not found at '{file_path}'. Skipping analysis.")
        return

    print(f"\n{'='*30} Analyzing {os.path.basename(file_path)} {'='*30}")

    try:
        parquet_file = pq.ParquetFile(file_path)

        # 1. Get unique account IDs (streams the file)
        unique_ids = get_unique_accounts_streaming(parquet_file)

        # 2. Check for data gaps on a sample of accounts
        check_data_gaps_sampled(str(file_path), parquet_file, unique_ids, metric_type)

        # 3. Review column data types from the schema
        review_column_datatypes(parquet_file)

    except Exception as e:
        print(f"\nAn unexpected error occurred while analyzing {file_path}: {e}")

    print(f"\n{'='*28} Analysis Complete for {os.path.basename(file_path)} {'='*28}")


def main():
    """
    Main entry point for the test script.
    Dynamically finds the project root directory.
    """
    # =================== START: REFACTORED CODE ===================
    # Dynamically determine the project root directory.
    # Assumes this script is in `your_project_root/tests/`.
    try:
        PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
    except NameError:
        # Fallback for interactive environments where __file__ is not defined
        PROJECT_ROOT = pathlib.Path('.').resolve().parent

    print(f"Project root identified as: {PROJECT_ROOT}")

    # Construct file paths
    cleaned_data_dir = PROJECT_ROOT / "artefacts" / "cleaned_data"
    daily_file = cleaned_data_dir / "daily_metrics_df.parquet"
    hourly_file = cleaned_data_dir / "hourly_metrics_df.parquet"
    # ==================== END: REFACTORED CODE ====================


    # Analyze both files
    analyze_file(daily_file, 'daily')
    analyze_file(hourly_file, 'hourly')


if __name__ == "__main__":
    main()