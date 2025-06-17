import featuretools as ft
import pandas as pd
import xxhash

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

    # Ensure consistent date string, avoid tz / hh:mm leakage
    date_str = pd.to_datetime(date_series).dt.strftime("%Y-%m-%d")
    concat = account_series.astype(str) + "_" + date_str
    # xxhash is ~5× faster than hashlib.md5 and returns 64-bit ints directly
    return concat.map(xxhash.xxh64_intdigest).astype("uint64")

# ---------------------------------------------------------------------------
# Load data (sample limited here; switch to full Dask load in production)
# ---------------------------------------------------------------------------

daily_metrics_df = execute_query_df("SELECT * FROM raw_metrics_daily LIMIT 1000")
alltime_metrics_df = execute_query_df("SELECT * FROM raw_metrics_alltime LIMIT 1000")
hourly_metrics_df = execute_query_df("SELECT * FROM raw_metrics_hourly LIMIT 1000")
trades_closed_df = execute_query_df("SELECT * FROM raw_trades_closed LIMIT 1000")
trades_open_df = execute_query_df("SELECT * FROM raw_trades_open LIMIT 1000")
plans_df = execute_query_df("SELECT * FROM raw_plans_data LIMIT 1000")
regimes_daily_df = execute_query_df("SELECT * FROM mv_regimes_daily_features LIMIT 1000")

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

# Closed trades – derive trading day from *close_time*
trades_closed_df["trade_day"] = pd.to_datetime(trades_closed_df["close_time"]).dt.normalize()
trades_closed_df["daily_id"] = make_daily_id(
    trades_closed_df["account_id"], trades_closed_df["trade_day"]
)

# Open trades – derive trading day from *open_time*
trades_open_df["trade_day"] = pd.to_datetime(trades_open_df["open_time"]).dt.normalize()
trades_open_df["daily_id"] = make_daily_id(
    trades_open_df["account_id"], trades_open_df["trade_day"]
)

# Unique indices for children where none exist

hourly_metrics_df["hourly_id"] = (
    hourly_metrics_df["account_id"].astype(str)
    + "_"
    + hourly_metrics_df["datetime"].astype(str)
).map(xxhash.xxh64_intdigest).astype("uint64")

# Tickets are already unique ids for trades; no extra column needed

# Regime table should have exactly one row per date
regimes_daily_df = (
    regimes_daily_df.sort_values("date").drop_duplicates("date", keep="last")
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
    "regimes_daily": (regimes_daily_df, "date", "date"),  # index == time_index

    # children
    "hourly_metrics": (hourly_metrics_df, "hourly_id", "datetime"),
    "trades_closed": (trades_closed_df, "ticket", "close_time"),
    "trades_open": (trades_open_df, "ticket", "open_time"),
}

relationships = [
    # Parent → child relationships (one-to-many)
    ("alltime_metrics", "account_id", "daily_metrics", "account_id"),
    ("plans", "plan_id", "daily_metrics", "plan_id"),
    ("regimes_daily", "date", "daily_metrics", "date"),

    ("daily_metrics", "daily_id", "hourly_metrics", "daily_id"),
    ("daily_metrics", "daily_id", "trades_closed", "daily_id"),
    ("daily_metrics", "daily_id", "trades_open", "daily_id"),
]

es = ft.EntitySet(id="daily_profit_model")

# Add dataframes
for name, args in dataframes.items():
    # Unpack (df, index, *rest)
    es = es.add_dataframe(dataframe_name=name, dataframe=args[0], index=args[1], *args[2:])

# Add relationships
for parent, parent_col, child, child_col in relationships:
    es = es.add_relationship(parent_dataframe_name=parent,
                              parent_column_name=parent_col,
                              child_dataframe_name=child,
                              child_column_name=child_col)

# EntitySet is now ready for DFS
