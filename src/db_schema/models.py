from typing import Optional

from sqlalchemy import ARRAY, Boolean, CheckConstraint, Date, DateTime, Double, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import datetime
import decimal

class Base(DeclarativeBase):
    pass


class FeatureStoreAccountDaily(Base):
    __tablename__ = 'feature_store_account_daily'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='feature_store_account_daily_pkey'),
        UniqueConstraint('account_id', 'feature_date', name='feature_store_account_daily_account_id_feature_date_key'),
        Index('idx_feature_store_account_date', 'account_id', 'feature_date'),
        Index('idx_feature_store_date', 'feature_date'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(255))
    login: Mapped[str] = mapped_column(String(255))
    feature_date: Mapped[datetime.date] = mapped_column(Date)
    days_active: Mapped[Optional[int]] = mapped_column(Integer)
    current_phase: Mapped[Optional[str]] = mapped_column(String(50))
    account_age_days: Mapped[Optional[int]] = mapped_column(Integer)
    trades_today: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    trades_last_7d: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    trades_last_30d: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    trading_days_last_7d: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    trading_days_last_30d: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    avg_trades_per_day_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    avg_trades_per_day_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    profit_today: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_last_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_last_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    roi_today: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    roi_last_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    roi_last_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    win_rate_today: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    win_rate_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    win_rate_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_factor_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    profit_factor_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    max_drawdown_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    avg_trade_size_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    avg_trade_size_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    avg_holding_time_hours_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    avg_holding_time_hours_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    unique_symbols_7d: Mapped[Optional[int]] = mapped_column(Integer)
    unique_symbols_30d: Mapped[Optional[int]] = mapped_column(Integer)
    symbol_concentration_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    symbol_concentration_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    pct_trades_market_hours_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    pct_trades_market_hours_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    favorite_trading_hour_7d: Mapped[Optional[int]] = mapped_column(Integer)
    favorite_trading_hour_30d: Mapped[Optional[int]] = mapped_column(Integer)
    daily_profit_volatility_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    daily_profit_volatility_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profitable_days_pct_7d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profitable_days_pct_30d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    distance_to_profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_to_profit_target_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    distance_to_drawdown_limit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_to_drawdown_limit_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    days_until_deadline: Mapped[Optional[int]] = mapped_column(Integer)
    market_volatility_regime: Mapped[Optional[str]] = mapped_column(String(50))
    market_trend_regime: Mapped[Optional[str]] = mapped_column(String(50))
    next_day_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class ModelPredictions(Base):
    __tablename__ = 'model_predictions'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='model_predictions_pkey'),
        UniqueConstraint('model_version', 'prediction_date', 'account_id', name='model_predictions_model_version_prediction_date_account_id_key'),
        Index('idx_model_predictions_account', 'account_id', 'prediction_date'),
        Index('idx_model_predictions_date', 'prediction_date'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(100))
    prediction_date: Mapped[datetime.date] = mapped_column(Date)
    account_id: Mapped[str] = mapped_column(String(255))
    predicted_profit_probability: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4))
    predicted_profit_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSONB)
    prediction_confidence: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4))
    actual_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class ModelRegistry(Base):
    __tablename__ = 'model_registry'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='model_registry_pkey'),
        UniqueConstraint('model_version', name='model_registry_model_version_key'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(100))
    model_type: Mapped[str] = mapped_column(String(50))
    training_completed_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    model_path: Mapped[Optional[str]] = mapped_column(String(500))
    git_commit_hash: Mapped[Optional[str]] = mapped_column(String(100))
    performance_metrics: Mapped[Optional[dict]] = mapped_column(JSONB)
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    deployed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    deprecated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class ModelTrainingInput(Base):
    __tablename__ = 'model_training_input'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='model_training_input_pkey'),
        UniqueConstraint('account_id', 'prediction_date', name='model_training_input_account_id_prediction_date_key'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(255))
    login: Mapped[str] = mapped_column(String(255))
    prediction_date: Mapped[datetime.date] = mapped_column(Date)
    feature_date: Mapped[datetime.date] = mapped_column(Date)
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_daily_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_target_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_leverage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    is_drawdown_relative: Mapped[Optional[bool]] = mapped_column(Boolean)
    current_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    days_since_first_trade: Mapped[Optional[int]] = mapped_column(Integer)
    active_trading_days_count: Mapped[Optional[int]] = mapped_column(Integer)
    distance_to_profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_to_max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    open_pnl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    open_positions_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_sum_1d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_avg_1d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_std_1d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_sum_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_avg_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_std_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_min_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_max_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    win_rate_3d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    rolling_pnl_sum_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_avg_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_std_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_min_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_max_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    win_rate_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_factor_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    sharpe_ratio_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    rolling_pnl_sum_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_avg_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_std_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_min_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_max_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    win_rate_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_factor_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    sharpe_ratio_10d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    rolling_pnl_sum_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_avg_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    rolling_pnl_std_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    win_rate_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_factor_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    sharpe_ratio_20d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    trades_count_5d: Mapped[Optional[int]] = mapped_column(Integer)
    avg_trade_duration_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    avg_lots_per_trade_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    avg_volume_per_trade_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    stop_loss_usage_rate_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    take_profit_usage_rate_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    buy_sell_ratio_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    top_symbol_concentration_5d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    market_sentiment_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    market_volatility_regime: Mapped[Optional[str]] = mapped_column(String(50))
    market_liquidity_state: Mapped[Optional[str]] = mapped_column(String(50))
    vix_level: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    dxy_level: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    sp500_daily_return: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    btc_volatility_90d: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 4))
    fed_funds_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)
    week_of_month: Mapped[Optional[int]] = mapped_column(Integer)
    month: Mapped[Optional[int]] = mapped_column(Integer)
    quarter: Mapped[Optional[int]] = mapped_column(Integer)
    day_of_year: Mapped[Optional[int]] = mapped_column(Integer)
    is_month_start: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_month_end: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_quarter_start: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_quarter_end: Mapped[Optional[bool]] = mapped_column(Boolean)
    target_net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class PipelineExecutionLog(Base):
    __tablename__ = 'pipeline_execution_log'
    __table_args__ = (
        CheckConstraint("status::text = ANY (ARRAY['running'::character varying, 'success'::character varying, 'failed'::character varying, 'warning'::character varying]::text[])", name='pipeline_execution_log_status_check'),
        PrimaryKeyConstraint('id', name='pipeline_execution_log_pkey'),
        Index('idx_pipeline_execution_stage_date', 'pipeline_stage', 'execution_date'),
        Index('idx_pipeline_execution_status', 'status', 'created_at'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_stage: Mapped[str] = mapped_column(String(100))
    execution_date: Mapped[datetime.date] = mapped_column(Date)
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime)
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    records_processed: Mapped[Optional[int]] = mapped_column(Integer)
    records_failed: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    execution_details: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class QueryPerformanceLog(Base):
    __tablename__ = 'query_performance_log'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='query_performance_log_pkey'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_hash: Mapped[Optional[str]] = mapped_column(String(64))
    query_template: Mapped[Optional[str]] = mapped_column(Text)
    execution_time_ms: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    rows_returned: Mapped[Optional[int]] = mapped_column(Integer)
    table_names: Mapped[Optional[list]] = mapped_column(ARRAY(Text()))
    index_used: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class RawMetricsAlltime(Base):
    __tablename__ = 'raw_metrics_alltime'
    __table_args__ = (
        CheckConstraint('gross_loss <= 0::numeric', name='raw_metrics_alltime_gross_loss_check'),
        CheckConstraint('gross_profit >= 0::numeric', name='raw_metrics_alltime_gross_profit_check'),
        CheckConstraint('num_trades >= 0', name='raw_metrics_alltime_num_trades_check'),
        CheckConstraint('phase = ANY (ARRAY[1, 2, 3, 4])', name='raw_metrics_alltime_phase_check'),
        CheckConstraint('profit_factor >= 0::numeric', name='raw_metrics_alltime_profit_factor_check'),
        CheckConstraint('status = ANY (ARRAY[1, 2, 3])', name='raw_metrics_alltime_status_check'),
        CheckConstraint('success_rate >= 0::numeric AND success_rate <= 100::numeric', name='raw_metrics_alltime_success_rate_check'),
        PrimaryKeyConstraint('account_id', name='raw_metrics_alltime_pkey'),
        Index('idx_raw_metrics_alltime_account_id', 'account_id'),
        Index('idx_raw_metrics_alltime_login', 'login'),
        Index('idx_raw_metrics_alltime_login_platform_broker', 'login', 'platform', 'broker'),
        Index('idx_raw_metrics_alltime_plan_id', 'plan_id'),
        Index('idx_raw_metrics_alltime_trader_id', 'trader_id'),
        {'schema': 'prop_trading_model'}
    )

    login: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String(255))
    trader_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[int]] = mapped_column(Integer)
    type: Mapped[Optional[int]] = mapped_column(Integer)
    phase: Mapped[Optional[int]] = mapped_column(Integer)
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    platform: Mapped[Optional[int]] = mapped_column(Integer)
    price_stream: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    approved_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    pending_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    first_trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    days_since_initial_deposit: Mapped[Optional[int]] = mapped_column(Integer)
    days_since_first_trade: Mapped[Optional[int]] = mapped_column(Integer)
    num_trades: Mapped[Optional[int]] = mapped_column(Integer)
    first_trade_open: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_trade_open: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_trade_close: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    lifetime_in_days: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gain_to_pain: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    profit_factor: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    success_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    expectancy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    top_10_prcnt_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    bottom_10_prcnt_loss_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    one_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    two_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    net_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    distance_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    multiple_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_gross_profit_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_gross_profit_loss_per_lot: Mapped[Optional[float]] = mapped_column(Double(53))
    net_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    total_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_mean_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_std_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_sharpe: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_downside_std_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_sortino: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_num_trades_in_dd: Mapped[Optional[int]] = mapped_column(Integer)
    rel_mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_volumes: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_winning_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_losing_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_winning_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_losing_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    multiple_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    min_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    cv_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_num_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    mean_num_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_account_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_firm_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    num_traded_symbols: Mapped[Optional[int]] = mapped_column(Integer)
    most_traded_symbol: Mapped[Optional[str]] = mapped_column(String(50))
    most_traded_smb_trades: Mapped[Optional[int]] = mapped_column(Integer)
    updated_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawMetricsDaily(Base):
    __tablename__ = 'raw_metrics_daily'
    __table_args__ = (
        CheckConstraint('gross_loss <= 0::numeric', name='raw_metrics_daily_gross_loss_check'),
        CheckConstraint('gross_profit >= 0::numeric', name='raw_metrics_daily_gross_profit_check'),
        CheckConstraint('num_trades >= 0', name='raw_metrics_daily_num_trades_check'),
        CheckConstraint('profit_factor >= 0::numeric', name='raw_metrics_daily_profit_factor_check'),
        CheckConstraint('status = ANY (ARRAY[1, 2, 3])', name='raw_metrics_daily_status_check'),
        CheckConstraint('success_rate >= 0::numeric AND success_rate <= 100::numeric', name='raw_metrics_daily_success_rate_check'),
        PrimaryKeyConstraint('account_id', 'date', name='raw_metrics_daily_pkey'),
        Index('idx_raw_metrics_daily_account_date', 'account_id', 'date'),
        Index('idx_raw_metrics_daily_date', 'date'),
        Index('idx_raw_metrics_daily_login', 'login'),
        Index('idx_raw_metrics_daily_profit', 'date', 'net_profit'),
        {'schema': 'prop_trading_model'}
    )

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    login: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String(255))
    trader_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[int]] = mapped_column(Integer)
    type: Mapped[Optional[int]] = mapped_column(Integer)
    phase: Mapped[Optional[int]] = mapped_column(Integer)
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    platform: Mapped[Optional[int]] = mapped_column(Integer)
    price_stream: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    days_to_next_payout: Mapped[Optional[int]] = mapped_column(Integer)
    todays_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    approved_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    pending_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    first_trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    days_since_initial_deposit: Mapped[Optional[int]] = mapped_column(Integer)
    days_since_first_trade: Mapped[Optional[int]] = mapped_column(Integer)
    num_trades: Mapped[Optional[int]] = mapped_column(Integer)
    net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gain_to_pain: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    profit_factor: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    success_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    expectancy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    top_10_prcnt_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    bottom_10_prcnt_loss_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    one_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    two_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    net_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    distance_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    multiple_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_gross_profit_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_gross_profit_loss_per_lot: Mapped[Optional[float]] = mapped_column(Double(53))
    net_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    total_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_mean_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_std_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_sharpe: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_downside_std_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    daily_sortino: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_num_trades_in_dd: Mapped[Optional[int]] = mapped_column(Integer)
    rel_mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_volumes: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_winning_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_losing_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_winning_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_losing_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    multiple_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    min_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    cv_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_num_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    mean_num_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_account_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_firm_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    num_traded_symbols: Mapped[Optional[int]] = mapped_column(Integer)
    most_traded_symbol: Mapped[Optional[str]] = mapped_column(String(50))
    most_traded_smb_trades: Mapped[Optional[int]] = mapped_column(Integer)
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawMetricsHourly(Base):
    __tablename__ = 'raw_metrics_hourly'
    __table_args__ = (
        CheckConstraint('gross_loss <= 0::numeric', name='raw_metrics_hourly_gross_loss_check'),
        CheckConstraint('gross_profit >= 0::numeric', name='raw_metrics_hourly_gross_profit_check'),
        CheckConstraint('num_trades >= 0', name='raw_metrics_hourly_num_trades_check'),
        CheckConstraint('profit_factor >= 0::numeric', name='raw_metrics_hourly_profit_factor_check'),
        CheckConstraint('status = ANY (ARRAY[1, 2, 3])', name='raw_metrics_hourly_status_check'),
        CheckConstraint('success_rate >= 0::numeric AND success_rate <= 100::numeric', name='raw_metrics_hourly_success_rate_check'),
        PrimaryKeyConstraint('account_id', 'date', 'hour', name='raw_metrics_hourly_pkey1'),
        Index('raw_metrics_hourly_account_id_date_hour_idx', 'account_id', 'date', 'hour'),
        Index('raw_metrics_hourly_date_hour_idx', 'date', 'hour'),
        Index('raw_metrics_hourly_date_hour_net_profit_idx', 'date', 'hour', 'net_profit'),
        Index('raw_metrics_hourly_plan_id_idx', 'plan_id'),
        Index('raw_metrics_hourly_status_date_hour_idx', 'status', 'date', 'hour'),
        {'schema': 'prop_trading_model'}
    )

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    datetime: Mapped[datetime.datetime] = mapped_column(DateTime)
    hour: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String(255))
    trader_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[int]] = mapped_column(Integer)
    type: Mapped[Optional[int]] = mapped_column(Integer)
    phase: Mapped[Optional[int]] = mapped_column(Integer)
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    platform: Mapped[Optional[int]] = mapped_column(Integer)
    price_stream: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    days_to_next_payout: Mapped[Optional[int]] = mapped_column(Integer)
    todays_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    approved_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    pending_payouts: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    prior_days_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    current_equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    first_trade_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    days_since_initial_deposit: Mapped[Optional[int]] = mapped_column(Integer)
    days_since_first_trade: Mapped[Optional[int]] = mapped_column(Integer)
    num_trades: Mapped[Optional[int]] = mapped_column(Integer)
    net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    gain_to_pain: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    profit_factor: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    success_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    expectancy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    top_10_prcnt_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    bottom_10_prcnt_loss_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    one_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    two_std_outlier_profit_contrib: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    net_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    distance_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    multiple_gross_profit_loss_per_usd_volume: Mapped[Optional[float]] = mapped_column(Double(53))
    gross_profit_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_gross_profit_loss_per_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_gross_profit_loss_per_lot: Mapped[Optional[float]] = mapped_column(Double(53))
    net_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_profit_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    gross_loss_per_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_std_rets: Mapped[Optional[float]] = mapped_column(Double(53))
    downside_risk_adj_ret: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_net_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_gross_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_mean_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_std_profits: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_risk_adj_profit: Mapped[Optional[float]] = mapped_column(Double(53))
    rel_min_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_10: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_25: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_75: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_perc_90: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_top_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_profit_bottom_10_prcnt_trades: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_one_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_two_std_outlier_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_num_trades_in_dd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_num_trades_in_dd: Mapped[Optional[int]] = mapped_column(Integer)
    rel_mean_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_median_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    rel_max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    total_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    std_volumes: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_winning_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    mean_losing_lot: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    distance_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    multiple_win_loss_lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_winning_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_losing_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    multiple_win_loss_volume: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_durations: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_tp: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    median_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    std_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    min_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    max_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    cv_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    min_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    cv_tp_vs_sl: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_num_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_wins: Mapped[Optional[int]] = mapped_column(Integer)
    mean_num_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_consec_losses: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_wins: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_consec_losses: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_num_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    median_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    max_num_open_pos: Mapped[Optional[int]] = mapped_column(Integer)
    mean_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    median_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_val_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    median_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    max_val_to_eqty_open_pos: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 6))
    mean_account_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    mean_firm_margin: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    num_traded_symbols: Mapped[Optional[int]] = mapped_column(Integer)
    most_traded_symbol: Mapped[Optional[str]] = mapped_column(String(50))
    most_traded_smb_trades: Mapped[Optional[int]] = mapped_column(Integer)
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawPlansData(Base):
    __tablename__ = 'raw_plans_data'
    __table_args__ = (
        CheckConstraint('inactivity_period >= 0', name='raw_plans_data_inactivity_period_check'),
        CheckConstraint('max_daily_drawdown_pct >= 0::numeric AND max_daily_drawdown_pct <= 100::numeric', name='raw_plans_data_max_daily_drawdown_pct_check'),
        CheckConstraint('max_drawdown_pct >= 0::numeric AND max_drawdown_pct <= 100::numeric', name='raw_plans_data_max_drawdown_pct_check'),
        CheckConstraint('max_leverage > 0::numeric', name='raw_plans_data_max_leverage_check'),
        CheckConstraint('max_trading_days >= 0', name='raw_plans_data_max_trading_days_check'),
        CheckConstraint('min_trading_days >= 0', name='raw_plans_data_min_trading_days_check'),
        CheckConstraint('profit_share_pct >= 0::numeric AND profit_share_pct <= 100::numeric', name='raw_plans_data_profit_share_pct_check'),
        CheckConstraint('profit_target_pct >= 0::numeric AND profit_target_pct <= 100::numeric', name='raw_plans_data_profit_target_pct_check'),
        CheckConstraint('starting_balance > 0::numeric', name='raw_plans_data_starting_balance_check'),
        PrimaryKeyConstraint('plan_id', name='raw_plans_data_pkey'),
        Index('idx_raw_plans_name', 'plan_name'),
        Index('idx_raw_plans_plan_id', 'plan_id'),
        {'schema': 'prop_trading_model'}
    )

    plan_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    plan_name: Mapped[str] = mapped_column(String(255))
    plan_type: Mapped[Optional[str]] = mapped_column(String(100))
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_target_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_daily_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_daily_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    profit_share_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_leverage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    min_trading_days: Mapped[Optional[int]] = mapped_column(Integer)
    max_trading_days: Mapped[Optional[int]] = mapped_column(Integer)
    is_drawdown_relative: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    liquidate_friday: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='Whether account can hold positions over the weekend (TRUE = must liquidate, FALSE = can hold)')
    inactivity_period: Mapped[Optional[int]] = mapped_column(Integer, comment='Number of days an account can go without placing a trade before breach')
    daily_drawdown_by_balance_equity: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='How daily drawdown is calculated (TRUE = from previous day balance or equity whichever is higher, FALSE = from previous day balance only)')
    enable_consistency: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'), comment='Whether consistency rules are applied to the account')
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawRegimesDaily(Base):
    __tablename__ = 'raw_regimes_daily'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='raw_regimes_daily_pkey'),
        UniqueConstraint('date', name='raw_regimes_daily_date_key'),
        Index('idx_raw_regimes_date', 'date'),
        Index('idx_raw_regimes_summary', 'summary'),
        {'schema': 'prop_trading_model'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date)
    regime_name: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[Optional[dict]] = mapped_column(JSONB)
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawTradesClosed(Base):
    __tablename__ = 'raw_trades_closed'
    __table_args__ = (
        CheckConstraint("side::text = ANY (ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying]::text[])", name='raw_trades_closed_side_check'),
        PrimaryKeyConstraint('platform', 'position', 'trade_date', name='raw_trades_closed_pkey'),
        UniqueConstraint('position', 'login', 'platform', 'broker', 'trade_date', name='raw_trades_closed_position_login_platform_broker_trade_date_key'),
        Index('idx_raw_trades_closed_account_id', 'account_id', 'trade_date'),
        Index('idx_raw_trades_closed_login_platform_broker', 'login', 'platform', 'broker'),
        Index('idx_raw_trades_closed_profit', 'profit', 'trade_date'),
        Index('idx_raw_trades_closed_symbol', 'std_symbol', 'trade_date'),
        {'schema': 'prop_trading_model'}
    )

    trade_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    platform: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[str] = mapped_column(String(255), primary_key=True)
    login: Mapped[str] = mapped_column(String(255))
    std_symbol: Mapped[str] = mapped_column(String(50))
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    manager: Mapped[Optional[int]] = mapped_column(Integer)
    ticket: Mapped[Optional[str]] = mapped_column(String(255))
    account_id: Mapped[Optional[str]] = mapped_column(String(255), comment='Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented')
    side: Mapped[Optional[str]] = mapped_column(String(10))
    lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    contract_size: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    qty_in_base_ccy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    volume_usd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    stop_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    open_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    open_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    close_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    close_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    commission: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    swap: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class RawTradesOpen(Base):
    __tablename__ = 'raw_trades_open'
    __table_args__ = (
        CheckConstraint("side::text = ANY (ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying]::text[])", name='raw_trades_open_side_check'),
        PrimaryKeyConstraint('platform', 'position', 'trade_date', name='raw_trades_open_pkey'),
        UniqueConstraint('position', 'login', 'platform', 'broker', 'trade_date', name='raw_trades_open_position_login_platform_broker_trade_date_key'),
        Index('idx_raw_trades_open_account_id', 'account_id', 'trade_date'),
        Index('idx_raw_trades_open_login_platform_broker', 'login', 'platform', 'broker'),
        Index('idx_raw_trades_open_profit', 'unrealized_profit', 'trade_date'),
        Index('idx_raw_trades_open_symbol', 'std_symbol', 'trade_date'),
        {'schema': 'prop_trading_model'}
    )

    trade_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    platform: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[str] = mapped_column(String(255), primary_key=True)
    login: Mapped[str] = mapped_column(String(255))
    std_symbol: Mapped[str] = mapped_column(String(50))
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    manager: Mapped[Optional[int]] = mapped_column(Integer)
    ticket: Mapped[Optional[str]] = mapped_column(String(255), comment='Keep as VARCHAR since API can send string or integer')
    account_id: Mapped[Optional[str]] = mapped_column(String(255), comment='Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented')
    side: Mapped[Optional[str]] = mapped_column(String(10))
    lots: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    contract_size: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    qty_in_base_ccy: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    volume_usd: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 4))
    stop_loss: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    take_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    open_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    open_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 6))
    duration: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    unrealized_profit: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    commission: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    swap: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    comment: Mapped[Optional[str]] = mapped_column(String(255))
    ingestion_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    source_api_endpoint: Mapped[Optional[str]] = mapped_column(String(500))


class SchemaMigrations(Base):
    __tablename__ = 'schema_migrations'
    __table_args__ = (
        PrimaryKeyConstraint('migration_name', name='schema_migrations_pkey'),
        {'comment': 'Tracks applied database migrations',
     'schema': 'prop_trading_model'}
    )

    migration_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    applied_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    applied_by: Mapped[Optional[str]] = mapped_column(String(100), server_default=text('CURRENT_USER'))
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class SchemaVersion(Base):
    __tablename__ = 'schema_version'
    __table_args__ = (
        CheckConstraint("status::text = ANY (ARRAY['applied'::character varying, 'rolled_back'::character varying, 'failed'::character varying]::text[])", name='schema_version_status_check'),
        PrimaryKeyConstraint('version_id', name='schema_version_pkey'),
        UniqueConstraint('version_hash', name='schema_version_version_hash_key'),
        Index('idx_schema_version_applied_at', 'applied_at'),
        {'schema': 'prop_trading_model'}
    )

    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_hash: Mapped[str] = mapped_column(String(32))
    applied_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    applied_by: Mapped[Optional[str]] = mapped_column(String(100), server_default=text('CURRENT_USER'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    migration_script: Mapped[Optional[str]] = mapped_column(Text)
    rollback_script: Mapped[Optional[str]] = mapped_column(Text)
    objects_affected: Mapped[Optional[dict]] = mapped_column(JSONB)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'applied'::character varying"))


class StgAccountsDailySnapshots(Base):
    __tablename__ = 'stg_accounts_daily_snapshots'
    __table_args__ = (
        CheckConstraint('phase = ANY (ARRAY[1, 2, 3, 4])', name='stg_accounts_daily_snapshots_phase_check'),
        CheckConstraint('status = ANY (ARRAY[1, 2, 3])', name='stg_accounts_daily_snapshots_status_check'),
        PrimaryKeyConstraint('account_id', 'snapshot_date', name='stg_accounts_daily_snapshots_pkey'),
        Index('idx_stg_accounts_daily_account_date', 'account_id', 'snapshot_date'),
        Index('idx_stg_accounts_daily_date', 'snapshot_date'),
        Index('idx_stg_accounts_daily_status', 'status'),
        {'schema': 'prop_trading_model'}
    )

    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    snapshot_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    login: Mapped[str] = mapped_column(String(255))
    plan_id: Mapped[Optional[str]] = mapped_column(String(255))
    trader_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[int]] = mapped_column(Integer)
    type: Mapped[Optional[int]] = mapped_column(Integer)
    phase: Mapped[Optional[int]] = mapped_column(Integer)
    broker: Mapped[Optional[int]] = mapped_column(Integer)
    platform: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    starting_balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    balance: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    equity: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    profit_target_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_daily_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_daily_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    max_drawdown_pct: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    max_leverage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    is_drawdown_relative: Mapped[Optional[bool]] = mapped_column(Boolean)
    distance_to_profit_target: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    distance_to_max_drawdown: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(18, 2))
    liquidate_friday: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    inactivity_period: Mapped[Optional[int]] = mapped_column(Integer)
    daily_drawdown_by_balance_equity: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    enable_consistency: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    days_active: Mapped[Optional[int]] = mapped_column(Integer)
    days_since_last_trade: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))


class TradeRecon(Base):
    """ORM mapping for prop_trading_model.trade_recon (reconciliation metadata)."""
    __tablename__ = 'trade_recon'
    __table_args__ = (
        PrimaryKeyConstraint('account_id', name='trade_recon_pkey'),
        Index('idx_trade_recon_checksum', 'trades_recon_checksum'),
        Index('idx_trade_recon_last_checked', 'last_checked'),
        {'schema': 'prop_trading_model'}
    )

    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    has_alltime: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    num_trades_alltime: Mapped[Optional[int]] = mapped_column(Integer)
    has_daily: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    num_trades_daily: Mapped[Optional[int]] = mapped_column(Integer)
    has_hourly: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    num_trades_hourly: Mapped[Optional[int]] = mapped_column(Integer)
    has_raw_closed: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    num_trades_raw_closed: Mapped[Optional[int]] = mapped_column(Integer)
    trades_recon_checksum: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    issues: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_checked: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    last_reconciled: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    failed_attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    last_failed_attempt: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
