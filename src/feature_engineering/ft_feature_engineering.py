import featuretools as ft
import pandas as pd
import xxhash
import joblib, pathlib
from utils.database import execute_query_df
from .utils import prepare_dataframe, make_daily_id, make_hash_id
from .dtype_utils import convert_to_float32


# ---------------------------------------------------------------------------
# Load data (sample limited here; switch to full Dask load in production)
# ---------------------------------------------------------------------------

daily_metrics_df = execute_query_df("SELECT * FROM raw_metrics_daily LIMIT 1000")
alltime_metrics_df = execute_query_df("SELECT * FROM raw_metrics_alltime LIMIT 1000")
hourly_metrics_df = execute_query_df("SELECT * FROM raw_metrics_hourly LIMIT 1000")
trades_closed_df = execute_query_df("SELECT * FROM raw_trades_closed LIMIT 1000")
trades_open_df = execute_query_df("SELECT * FROM raw_trades_open LIMIT 1000")
plans_df = execute_query_df("SELECT * FROM raw_plans_data LIMIT 1000")
regimes_daily_df = execute_query_df("SELECT * FROM prop_trading_model.mv_regime_daily_features LIMIT 1000")

# Convert to float32
daily_metrics_df = convert_to_float32(daily_metrics_df)
alltime_metrics_df = convert_to_float32(alltime_metrics_df)
hourly_metrics_df = convert_to_float32(hourly_metrics_df)
trades_closed_df = convert_to_float32(trades_closed_df)
trades_open_df = convert_to_float32(trades_open_df)
plans_df = convert_to_float32(plans_df)
regimes_daily_df = convert_to_float32(regimes_daily_df)

# ---------------------------------------------------------------------------
# Key engineering
# ---------------------------------------------------------------------------

print("Engineering surrogate keys …")

for _df in (
    daily_metrics_df,
    alltime_metrics_df,
    hourly_metrics_df,
    trades_closed_df,
    trades_open_df,
):
    if "account_id" in _df.columns:
        _df["account_id"] = _df["account_id"].astype(str)

        

# Parent key for one-row-per-(account, date)
daily_metrics_df["daily_id"] = make_daily_id(
    daily_metrics_df["account_id"], daily_metrics_df["date"]
)

# Propagate the same key down to child tables
hourly_metrics_df["daily_id"] = make_daily_id(
    hourly_metrics_df["account_id"], hourly_metrics_df["date"]
)

# Use existing trade_date column for mapping to daily snapshots
trades_closed_df["daily_id"] = make_daily_id(
    trades_closed_df["account_id"], trades_closed_df["trade_date"]
)

trades_open_df["daily_id"] = make_daily_id(
    trades_open_df["account_id"], trades_open_df["trade_date"]
)

# Unique indices for children where none exist

hourly_metrics_df["hourly_id"] = (
    hourly_metrics_df["account_id"].astype(str)
    + "_"
    + hourly_metrics_df["datetime"].astype(str)
).map(xxhash.xxh64_intdigest).astype("uint64")

# Regime table should have exactly one row per date
regimes_daily_df = (
    regimes_daily_df.sort_values("date").drop_duplicates("date", keep="last")
)

# Add surrogate index for regimes_daily to separate index and time_index
regimes_daily_df["regime_daily_id"] = pd.to_datetime(regimes_daily_df["date"]).dt.strftime("%Y-%m-%d").map(xxhash.xxh64_intdigest).astype("uint64")

# Add matching foreign key on daily_metrics for regime join
daily_metrics_df["regime_daily_id"] = pd.to_datetime(daily_metrics_df["date"]).dt.strftime("%Y-%m-%d").map(xxhash.xxh64_intdigest).astype("uint64")

# Unique key for CLOSED trades: ticket + login + open_time + close_time (+platform for safety)
trades_closed_df["trade_id"] = make_hash_id(
    trades_closed_df,
    ["ticket", "login", "open_time", "close_time", "platform"]
)

# Unique key for OPEN trades: ticket + login + open_time + platform + trade_date
trades_open_df["trade_id"] = make_hash_id(
    trades_open_df,
    ["ticket", "login", "open_time", "platform", "trade_date"]
)

print(daily_metrics_df["daily_id"].head(3))
print(alltime_metrics_df["account_id"].head(3))
print(hourly_metrics_df["hourly_id"].head(3))
print(trades_closed_df["daily_id"].head(3))
print(trades_closed_df["trade_id"].head(3))
print(trades_open_df["daily_id"].head(3))
print(trades_open_df["trade_id"].head(3))
print(plans_df["plan_id"].head(3))
print(regimes_daily_df["regime_daily_id"].head(3))

# ---------------------------------------------------------------------------
# Build EntitySet
# ---------------------------------------------------------------------------
print("Building EntitySet …")
es = ft.EntitySet(id="daily_profit_model")

dataframes = {
    # target dataframe
    "daily_metrics": (daily_metrics_df, "daily_id", "date"),

    # parents
    "alltime_metrics": (alltime_metrics_df, "account_id"),
    "plans": (plans_df, "plan_id"),
    "regimes_daily": (regimes_daily_df, "regime_daily_id", "date"),  # separate index and time_index

    # children
    "hourly_metrics": (hourly_metrics_df, "hourly_id", "datetime"),
    "trades_closed": (trades_closed_df, "trade_id", "close_time"),
    "trades_open": (trades_open_df, "trade_id", "open_time"),
}

relationships = [
    # Parent → child relationships (one-to-many)
    ("alltime_metrics", "account_id", "daily_metrics", "account_id"),
    ("plans", "plan_id", "daily_metrics", "plan_id"),
    ("regimes_daily", "regime_daily_id", "daily_metrics", "regime_daily_id"),

    ("daily_metrics", "daily_id", "hourly_metrics", "daily_id"),
    ("daily_metrics", "daily_id", "trades_closed", "daily_id"),
    ("daily_metrics", "daily_id", "trades_open", "daily_id"),
]

# Add dataframes with cleaning and explicit logical types
for name, args in dataframes.items():
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

    es = es.add_dataframe(**add_df_kwargs)

# Add relationships
for parent, parent_col, child, child_col in relationships:
    es = es.add_relationship(parent_dataframe_name=parent,
                              parent_column_name=parent_col,
                              child_dataframe_name=child,
                              child_column_name=child_col)

AGG_PRIMITIVES = ["sum", "mean", "count", "max", "min", "std", "percent_true"]
TRANS_PRIMITIVES = ["year", "month", "day", "weekday", "is_weekend"]

# EntitySet is now ready for DFS
daily_feature_defs = ft.dfs(
    entityset=es,
    target_dataframe_name="daily_metrics",
    agg_primitives=AGG_PRIMITIVES,
    trans_primitives=TRANS_PRIMITIVES,
    max_depth=2,
    features_only=True,
    cutoff_time="date",
    n_jobs=-1,
)
print(f"Generated {len(daily_feature_defs)} features")

# Save feature definitions to the project-level artefacts directory
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTEFACT_DIR = PROJECT_ROOT / "artefacts"
ARTEFACT_DIR.mkdir(exist_ok=True)
joblib.dump(daily_feature_defs, ARTEFACT_DIR / "daily_feature_defs_v1.joblib")