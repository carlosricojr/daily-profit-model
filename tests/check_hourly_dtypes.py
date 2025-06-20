import pandas as pd
import pyarrow.parquet as pq

# Check the raw hourly metrics dtypes
raw_file = "/home/carlos/trading/daily-profit-model/raw-data/raw_metrics_hourly.parquet"
print("Checking raw hourly metrics data types...")

# Read a small sample
pf = pq.ParquetFile(raw_file)
df = pf.read_row_group(0).to_pandas()

# Import the optimize_dtypes function
import sys
sys.path.append('/home/carlos/trading/daily-profit-model/src/feature_engineering')
from dtype_utils import optimize_dtypes

# Optimize the sample
print("\nBefore optimization:")
print(df.dtypes.value_counts())

optimized_df = optimize_dtypes(df)
print("\nAfter optimization:")
print(optimized_df.dtypes.value_counts())

# Check which activity columns became categorical
from prepare_data_streaming import ACTIVITY_COLS

print("\nActivity columns that became categorical:")
for col in ACTIVITY_COLS:
    if col in optimized_df.columns:
        if optimized_df[col].dtype.name == 'category':
            print(f"  {col}: {optimized_df[col].dtype}")
            print(f"    Categories: {optimized_df[col].cat.categories.tolist()[:10]}...")
            print(f"    Has 0: {0 in optimized_df[col].cat.categories}")