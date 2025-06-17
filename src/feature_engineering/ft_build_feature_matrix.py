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

Heavy calculations are done with chunked pandas; you can later swap in
Dask by editing the `USE_DASK` flag.
"""

from __future__ import annotations

import pathlib
import joblib
import pandas as pd
import featuretools as ft
from datetime import timedelta
from utils.database import execute_query_df

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ARTEFACT_DIR = pathlib.Path("artefacts")
ARTEFACT_DIR.mkdir(exist_ok=True)

FEATURE_DEF_PATH = ARTEFACT_DIR / "daily_feature_defs_v1.joblib"

# Choose whether to use Dask for very large dataframes.
USE_DASK = False  # flip to True after you install dask and distributed

# Default pandas chunk size; still applies when Dask is off.
CHUNK_SIZE = 100_000

# If Dask is requested, spin up a local cluster and prepare kwargs.
if USE_DASK:
    from dask.distributed import LocalCluster

    print("Starting local Dask cluster …")
    _cluster = LocalCluster(n_workers=8, threads_per_worker=2, memory_limit="10GB")
    DASK_KWARGS = {"cluster": _cluster}
else:
    DASK_KWARGS = {}

TRAIN_SPAN_DAYS = None  # None == use everything up to validation split
VAL_DAYS = 15          # validation window length
TEST_DAYS = 30         # hold-out window length

# ---------------------------------------------------------------------------
# Minimal helpers (copied from ft_feature_engineering without heavy imports)
# ---------------------------------------------------------------------------
import xxhash
from woodwork.logical_types import Categorical, CountryCode, Boolean, Datetime

def make_daily_id(account_series: pd.Series, date_series: pd.Series) -> pd.Series:
    date_parsed = pd.to_datetime(date_series, format="%Y-%m-%d", errors="coerce")
    concat = account_series.astype(str) + "_" + date_parsed.dt.strftime("%Y-%m-%d")
    return concat.map(xxhash.xxh64_intdigest).astype("uint64")

def make_hash_id(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    concat = df[cols[0]].astype(str)
    for c in cols[1:]:
        concat = concat + "_" + df[c].astype(str)
    return concat.map(xxhash.xxh64_intdigest).astype("uint64")

LOGICAL_TYPE_MAP = {
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
    # regimes
    "volatility_regime": Categorical,
    "liquidity_state": Categorical,
    "yield_curve_shape": Categorical,
    "sentiment_very_bullish": Boolean,
    "has_anomalies": Boolean,
    # plan flags
    "is_drawdown_relative": Boolean,
    "liquidate_friday": Boolean,
    "daily_drawdown_by_balance_and_equity": Boolean,
    "enable_consistency": Boolean,
}

DROP_COLS = {
    "daily_metrics": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at", "updated_date"],
    "alltime_metrics": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at"],
    "hourly_metrics": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at"],
    "trades_closed": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at"],
    "trades_open": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at"],
    "plans": ["source_api_endpoint", "ingestion_timestamp", "updated_at", "created_at"],
    "regimes_daily": ["source_api_endpoint", "updated_at", "created_at", "mv_refreshed_at"],
}

DATETIME_FORMATS = {
    "date": "%Y-%m-%d",
    "trade_date": "%Y-%m-%d",
    "open_time": "%Y-%m-%d %H:%M:%S",
    "close_time": "%Y-%m-%d %H:%M:%S",
    "datetime": "%Y-%m-%d %H:%M:%S",
}

def _prepare_dataframe(df_name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.drop(columns=DROP_COLS.get(df_name, []), errors="ignore").copy()
    logical = {c: t for c, t in LOGICAL_TYPE_MAP.items() if c in df.columns}
    for col, fmt in DATETIME_FORMATS.items():
        if col in df.columns and df[col].dtype == "object":
            df[col] = pd.to_datetime(df[col], format=fmt, errors="coerce")
            logical.setdefault(col, Datetime)
    return df, logical

# ---------------------------------------------------------------------------
# Load data from the database (no LIMIT now)
# ---------------------------------------------------------------------------
print("Loading raw tables …")
DAILY_METRICS  = execute_query_df("SELECT * FROM raw_metrics_daily LIMIT 100000")
ALLTIME_METRICS = execute_query_df("SELECT * FROM raw_metrics_alltime LIMIT 100000")
HOURLY_METRICS  = execute_query_df("SELECT * FROM raw_metrics_hourly LIMIT 100000")
TRADES_CLOSED   = execute_query_df("SELECT * FROM raw_trades_closed LIMIT 100000")
TRADES_OPEN     = execute_query_df("SELECT * FROM raw_trades_open LIMIT 100000")
PLANS           = execute_query_df("SELECT * FROM raw_plans_data LIMIT 100000")
REGIMES_DAILY   = execute_query_df("SELECT * FROM prop_trading_model.mv_regime_daily_features LIMIT 100000")

# ---------------------------------------------------------------------------
# Key engineering (same logic as ft_feature_engineering.py)
# ---------------------------------------------------------------------------
print("Engineering surrogate keys …")

for _df in (DAILY_METRICS, ALLTIME_METRICS, HOURLY_METRICS, TRADES_CLOSED, TRADES_OPEN):
    if "account_id" in _df.columns:
        _df["account_id"] = _df["account_id"].astype(str)

DAILY_METRICS["daily_id"]  = make_daily_id(DAILY_METRICS["account_id"],  DAILY_METRICS["date"])
HOURLY_METRICS["daily_id"] = make_daily_id(HOURLY_METRICS["account_id"], HOURLY_METRICS["date"])
TRADES_CLOSED["daily_id"]  = make_daily_id(TRADES_CLOSED["account_id"],  TRADES_CLOSED["trade_date"])
TRADES_OPEN["daily_id"]    = make_daily_id(TRADES_OPEN["account_id"],    TRADES_OPEN["trade_date"])

HOURLY_METRICS["hourly_id"] = (HOURLY_METRICS["account_id"].astype(str) + "_" + HOURLY_METRICS["datetime"].astype(str))\
    .map(xxhash.xxh64_intdigest).astype("uint64")

REGIMES_DAILY = REGIMES_DAILY.sort_values("date").drop_duplicates("date", keep="last")
REGIMES_DAILY["regime_daily_id"] = pd.to_datetime(REGIMES_DAILY["date"]).dt.strftime("%Y-%m-%d")\
    .map(xxhash.xxh64_intdigest).astype("uint64")
DAILY_METRICS["regime_daily_id"] = pd.to_datetime(DAILY_METRICS["date"]).dt.strftime("%Y-%m-%d")\
    .map(xxhash.xxh64_intdigest).astype("uint64")

TRADES_CLOSED["trade_id"] = make_hash_id(TRADES_CLOSED,
    ["ticket", "login", "open_time", "close_time", "platform"])
TRADES_OPEN["trade_id"]   = make_hash_id(TRADES_OPEN,
    ["ticket", "login", "open_time", "platform", "trade_date"])

# ---------------------------------------------------------------------------
# Build EntitySet
# ---------------------------------------------------------------------------
print("Building EntitySet …")
ES = ft.EntitySet(id="daily_profit_model_full")

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
    df_raw, index_col, *maybe_time = args
    df_clean, logical = _prepare_dataframe(name, df_raw)
    kwargs = dict(dataframe_name=name, dataframe=df_clean, index=index_col)
    if maybe_time:
        kwargs["time_index"] = maybe_time[0]
    if logical:
        kwargs["logical_types"] = logical
    ES = ES.add_dataframe(**kwargs)

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

# ---------------------------------------------------------------------------
# Load feature definitions
# ---------------------------------------------------------------------------
print("Loading feature definitions …")
FEATURE_DEFS = joblib.load(FEATURE_DEF_PATH)

# ---------------------------------------------------------------------------
# Determine date splits
# ---------------------------------------------------------------------------
print("Creating cutoff tables …")
max_date = DAILY_METRICS["date"].max()
test_start = max_date - timedelta(days=TEST_DAYS)
val_start  = test_start - timedelta(days=VAL_DAYS)

cutoffs = {}
cutoffs["test"] = DAILY_METRICS.loc[DAILY_METRICS["date"] >= test_start, ["daily_id", "date"]]
cutoffs["val"]  = DAILY_METRICS.loc[(DAILY_METRICS["date"] >= val_start) & (DAILY_METRICS["date"] < test_start), ["daily_id", "date"]]
cutoffs["train"] = DAILY_METRICS.loc[DAILY_METRICS["date"] < val_start, ["daily_id", "date"]]

for k, df in cutoffs.items():
    df.rename(columns={"daily_id": "instance_id", "date": "time"}, inplace=True)

# ---------------------------------------------------------------------------
# Materialise matrices
# ---------------------------------------------------------------------------
print("Materialising feature matrices …")
for split_name, cutoff_df in cutoffs.items():
    if cutoff_df.empty:
        print(f"{split_name}: no rows, skipping")
        continue
    calc_kwargs = dict(
        features=FEATURE_DEFS,
        entityset=ES,
        cutoff_time=cutoff_df,
        cutoff_time_in_index=True,
        n_jobs=-1,
        chunk_size=CHUNK_SIZE,
    )
    # Only include dask_kwargs when we actually have them
    if DASK_KWARGS:
        calc_kwargs["dask_kwargs"] = DASK_KWARGS

    matrix = ft.calculate_feature_matrix(**calc_kwargs)
    path = ARTEFACT_DIR / f"{split_name}_matrix.parquet"
    matrix.to_parquet(path, engine="pyarrow")
    print(f"{split_name}: {matrix.shape} → {path}")

print("Finished building feature matrices.")