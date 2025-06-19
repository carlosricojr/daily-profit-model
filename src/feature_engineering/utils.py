from woodwork.logical_types import Categorical, Boolean, CountryCode, Datetime
import pandas as pd
import xxhash
from datetime import timedelta

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
    # Trade identifiers - these should not be used for numerical aggregations
    "ticket": Categorical,
    "position": Categorical,
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
    "daily_metrics": ["source_api_endpoint", "ingestion_timestamp"],
    "alltime_metrics": ["updated_date", "ingestion_timestamp", "source_api_endpoint"],
    "hourly_metrics": ["ingestion_timestamp", "source_api_endpoint"],
    "trades_closed": ["ingestion_timestamp", "source_api_endpoint"],
    "trades_open": ["ingestion_timestamp", "source_api_endpoint"],
    "plans": ["ingestion_timestamp", "source_api_endpoint", "updated_at"],
    "regimes_daily": ["mv_refreshed_at"],
}

DATETIME_FORMATS = {
    "date": "%Y-%m-%d",
    "trade_date": "%Y-%m-%d",
    "open_time": "%Y-%m-%d %H:%M:%S",
    "close_time": "%Y-%m-%d %H:%M:%S",
    "datetime": "%Y-%m-%d %H:%M:%S",
}

def prepare_dataframe(df_name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.drop(columns=DROP_COLS.get(df_name, []), errors="ignore").copy()
    logical = {c: t for c, t in LOGICAL_TYPE_MAP.items() if c in df.columns}
    for col, fmt in DATETIME_FORMATS.items():
        if col in df.columns and df[col].dtype == "object":
            df[col] = pd.to_datetime(df[col], format=fmt, errors="coerce")
            logical.setdefault(col, Datetime)
    return df, logical

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

def split_date_range_into_chunks(start_date, end_date, chunk_days=30):
    """Split a date range into smaller chunks."""
    chunks = []
    current_start = start_date
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)
        chunks.append((current_start, current_end))
        current_start = current_end
        
    return chunks