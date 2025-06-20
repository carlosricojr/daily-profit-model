import pyarrow.parquet as pq
import pandas as pd
import os

# Path to the daily metrics file
file_path = "/home/carlos/trading/daily-profit-model/artefacts/cleaned_data/daily_metrics_df.parquet"

print("Quick verification of daily_metrics_df.parquet")
print("=" * 50)

# Check file exists and size
if os.path.exists(file_path):
    file_size = os.path.getsize(file_path) / (1024**3)  # GB
    print(f"✓ File exists: {file_size:.2f} GB")
else:
    print("✗ File not found!")
    exit(1)

# Open the parquet file
pf = pq.ParquetFile(file_path)

# Get metadata
metadata = pf.metadata
print(f"\n✓ Total rows: {metadata.num_rows:,}")
print(f"✓ Total columns: {len(pf.schema)}")
print(f"✓ Row groups: {metadata.num_row_groups}")

# Read a small sample to verify structure
print("\nReading small sample to verify structure...")
sample = pf.read_row_group(0, columns=['account_id', 'date']).to_pandas()

# Check unique accounts in sample
unique_accounts = sample['account_id'].nunique()
print(f"✓ Unique accounts in first row group: {unique_accounts:,}")

# Check date range in sample
sample['date'] = pd.to_datetime(sample['date'])
date_min = sample['date'].min()
date_max = sample['date'].max()
print(f"✓ Date range in sample: {date_min} to {date_max}")

# Check for duplicates in sample
duplicates = sample.duplicated(subset=['account_id', 'date']).sum()
print(f"✓ Duplicates in sample: {duplicates}")

# Check a single account for completeness
test_account = sample['account_id'].iloc[0]
account_data = sample[sample['account_id'] == test_account].sort_values('date')
print(f"\nChecking account {test_account}:")
print(f"  - Records: {len(account_data)}")
print(f"  - Date range: {account_data['date'].min()} to {account_data['date'].max()}")

# Calculate expected days
expected_days = (account_data['date'].max() - account_data['date'].min()).days + 1
print(f"  - Expected days: {expected_days}")
print(f"  - Missing days: {expected_days - len(account_data)}")

print("\n✓ Quick verification complete!")