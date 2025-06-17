import featuretools as ft
from woodwork.logical_types import Categorical, CountryCode, Boolean
import pandas as pd
import xxhash
import joblib, pathlib

from utils.database import execute_query_df

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_daily_id(account_series: pd.Series, date_series: pd.Series) -> pd.Series:
    """Return a deterministic 64-bit hash of *account_id + YYYY-MM-DD*.

    The function generates a collision-resistant surrogate key that is
    compatible with Featuretools (single-column, integer) and compact in
    memory (uint64 → 8 bytes/row).
    """

    # Ensure consistent date string, avoid tz / hh:mm leakage; explicit format avoids
    # Woodwork's fallback to `dateutil` which triggers warnings.
    date_parsed = pd.to_datetime(date_series, format="%Y-%m-%d", errors="coerce")
    date_str = date_parsed.dt.strftime("%Y-%m-%d")
    concat = account_series.astype(str) + "_" + date_str
    # xxhash is ~5× faster than hashlib.md5 and returns 64-bit ints directly
    return concat.map(xxhash.xxh64_intdigest).astype("uint64")

def make_hash_id(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Return a uint64 hash of the concatenated string representations of *cols*."""

    concat = df[cols[0]].astype(str)
    for c in cols[1:]:
        concat = concat + "_" + df[c].astype(str)
    return concat.map(xxhash.xxh64_intdigest).astype("uint64")

# ---------------------------------------------------------------------------
# Schema helpers (explicit logical types & columns to drop)
# ---------------------------------------------------------------------------

LOGICAL_TYPE_MAP = {
    # Universal identifiers / enums
    "account_id": Categorical,
    "login": Categorical,
    "plan_id": Categorical,
    "trader_id": Categorical,
    "plan_name": Categorical,
    "plan_type": Categorical,
    "broker": Categorical,
    "platform": Categorical,
    "manager": Categorical,
    "status": Categorical,
    "type": Categorical,
    "phase": Categorical,
    "price_stream": Categorical,
    "side": Categorical,
    "std_symbol": Categorical,
    "country": CountryCode,
    # Regimes
    "volatility_regime": Categorical,
    "liquidity_state": Categorical,
    "yield_curve_shape": Categorical,
    "sentiment_very_bullish": Boolean,
    "has_anomalies": Boolean,
    # Plan flags
    "is_drawdown_relative": Boolean,
    "liquidate_friday": Boolean,
    "daily_drawdown_by_balance_and_equity": Boolean,
    "enable_consistency": Boolean,
}

# Columns that add no predictive value or break uniqueness – drop per table
DROP_COLS = {
    "trades_open": [
        "source_api_endpoint",
        "ingestion_timestamp",
        "updated_at",
        "created_at",
    ],
    "trades_closed": [
        "source_api_endpoint",
        "ingestion_timestamp",
        "updated_at",
        "created_at",
    ],
    "daily_metrics": [
        "source_api_endpoint",
        "updated_at",
        "created_at",
        "ingestion_timestamp",
        "updated_date",
    ],
    "alltime_metrics": [
        "source_api_endpoint",
        "updated_at",
        "created_at",
        "ingestion_timestamp",
    ],
    "hourly_metrics": [
        "source_api_endpoint",
        "updated_at",
        "created_at",
        "ingestion_timestamp",
    ],
    "plans": [
        "source_api_endpoint",
        "updated_at",
        "created_at",
        "ingestion_timestamp",
    ],
    "regimes_daily": [
        "source_api_endpoint",
        "updated_at",
        "created_at",
        "mv_refreshed_at",
    ],
}

def _prepare_dataframe(df_name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return cleaned dataframe and corresponding logical_types mapping."""

    df_clean = df.drop(columns=DROP_COLS.get(df_name, []), errors="ignore").copy()

    # Build logical types dict for columns present in df
    logical_types = {
        col: ltype for col, ltype in LOGICAL_TYPE_MAP.items() if col in df_clean.columns
    }

    # Convert common date/time columns to datetime with explicit format to silence
    # Woodwork's fallback warnings. Extend mapping as needed.
    datetime_format_map = {
        "date": "%Y-%m-%d",
        "trade_date": "%Y-%m-%d",
        "open_time": "%Y-%m-%d %H:%M:%S",
        "close_time": "%Y-%m-%d %H:%M:%S",
        "datetime": "%Y-%m-%d %H:%M:%S",
    }
    for col, fmt in datetime_format_map.items():
        if col in df_clean.columns and df_clean[col].dtype == "object":
            df_clean[col] = pd.to_datetime(df_clean[col], format=fmt, errors="coerce")

            # Tell Woodwork explicitly
            if col not in logical_types:
                from woodwork.logical_types import Datetime
                logical_types[col] = Datetime

    return df_clean, logical_types

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

# ---------------------------------------------------------------------------
# Ensure consistent dtypes for keys
# ---------------------------------------------------------------------------

for _df in (
    daily_metrics_df,
    alltime_metrics_df,
    hourly_metrics_df,
    trades_closed_df,
    trades_open_df,
):
    if "account_id" in _df.columns:
        _df["account_id"] = _df["account_id"].astype(str)

# ---------------------------------------------------------------------------
# Surrogate / foreign keys
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Unique trade identifiers (surrogate keys)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Build EntitySet
# ---------------------------------------------------------------------------

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

es = ft.EntitySet(id="daily_profit_model")

# Add dataframes with cleaning and explicit logical types
for name, args in dataframes.items():
    df_raw, index_col, *maybe_time_index = args

    df_clean, logical_types = _prepare_dataframe(name, df_raw)

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

AGG_PRIMITIVES = ["sum", "mean", "count", "max", "min", "skew", "kurtosis", "percent_true"]
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

pathlib.Path("artefacts").mkdir(exist_ok=True)
joblib.dump(daily_feature_defs, "artefacts/daily_feature_defs_v1.joblib")