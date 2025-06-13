"""
SQLAlchemy Models for Trading System

These models provide:
- Type safety for ML feature engineering
- Sophisticated autogenerate capabilities
- IDE support and static analysis
- Relationship management
- Data validation integration
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Boolean, Text, 
    ForeignKey, Index, CheckConstraint, UniqueConstraint,
    TIMESTAMP, DECIMAL, VARCHAR, BIGINT
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

Base = declarative_base()

# Set schema for all models
Base.metadata.schema = "prop_trading_model"


class RawMetricsAlltime(Base):
    """All-time metrics for trading accounts."""
    __tablename__ = "raw_metrics_alltime"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    balance = Column(DECIMAL(15, 2), nullable=True)
    equity = Column(DECIMAL(15, 2), nullable=True)
    margin = Column(DECIMAL(15, 2), nullable=True)
    free_margin = Column(DECIMAL(15, 2), nullable=True)
    margin_level = Column(DECIMAL(8, 2), nullable=True)
    profit = Column(DECIMAL(15, 2), nullable=True)
    credit = Column(DECIMAL(15, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    leverage = Column(Integer, nullable=True)
    trades_count = Column(Integer, nullable=True)
    success_rate = Column(DECIMAL(5, 2), nullable=True)
    profit_factor = Column(DECIMAL(8, 4), nullable=True)
    expected_payoff = Column(DECIMAL(15, 2), nullable=True)
    sharpe_ratio = Column(DECIMAL(8, 4), nullable=True)
    recovery_factor = Column(DECIMAL(8, 4), nullable=True)
    max_drawdown = Column(DECIMAL(15, 2), nullable=True)
    max_drawdown_percent = Column(DECIMAL(5, 2), nullable=True)
    average_win = Column(DECIMAL(15, 2), nullable=True)
    average_loss = Column(DECIMAL(15, 2), nullable=True)
    largest_win = Column(DECIMAL(15, 2), nullable=True)
    largest_loss = Column(DECIMAL(15, 2), nullable=True)
    consecutive_wins = Column(Integer, nullable=True)
    consecutive_losses = Column(Integer, nullable=True)
    max_consecutive_wins = Column(Integer, nullable=True)
    max_consecutive_losses = Column(Integer, nullable=True)
    total_trades = Column(Integer, nullable=True)
    winning_trades = Column(Integer, nullable=True)
    losing_trades = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        CheckConstraint('balance >= 0', name='chk_balance_positive'),
        CheckConstraint('success_rate >= 0 AND success_rate <= 100', name='chk_success_rate_range'),
        CheckConstraint('leverage > 0', name='chk_leverage_positive'),
        Index('idx_raw_metrics_alltime_last_updated', 'last_updated'),
        Index('idx_raw_metrics_alltime_balance', 'balance'),
    )


class RawMetricsDaily(Base):
    """Daily metrics for trading accounts."""
    __tablename__ = "raw_metrics_daily"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    date = Column(DateTime, primary_key=True, nullable=False)
    balance = Column(DECIMAL(15, 2), nullable=True)
    equity = Column(DECIMAL(15, 2), nullable=True)
    margin = Column(DECIMAL(15, 2), nullable=True)
    free_margin = Column(DECIMAL(15, 2), nullable=True)
    margin_level = Column(DECIMAL(8, 2), nullable=True)
    profit = Column(DECIMAL(15, 2), nullable=True)
    daily_profit = Column(DECIMAL(15, 2), nullable=True)
    daily_profit_percent = Column(DECIMAL(8, 4), nullable=True)
    trades_count = Column(Integer, nullable=True)
    open_positions = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint('balance >= 0', name='chk_daily_balance_positive'),
        CheckConstraint('open_positions >= 0', name='chk_open_positions_non_negative'),
        Index('idx_raw_metrics_daily_date', 'date'),
        Index('idx_raw_metrics_daily_account_date', 'account_id', 'date'),
        Index('idx_raw_metrics_daily_last_updated', 'last_updated'),
    )


class RawMetricsHourly(Base):
    """Hourly metrics for trading accounts."""
    __tablename__ = "raw_metrics_hourly"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    datetime = Column(TIMESTAMP(timezone=True), primary_key=True, nullable=False)
    balance = Column(DECIMAL(15, 2), nullable=True)
    equity = Column(DECIMAL(15, 2), nullable=True)
    margin = Column(DECIMAL(15, 2), nullable=True)
    free_margin = Column(DECIMAL(15, 2), nullable=True)
    margin_level = Column(DECIMAL(8, 2), nullable=True)
    profit = Column(DECIMAL(15, 2), nullable=True)
    hourly_profit = Column(DECIMAL(15, 2), nullable=True)
    hourly_profit_percent = Column(DECIMAL(8, 4), nullable=True)
    trades_count = Column(Integer, nullable=True)
    open_positions = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Primary key
    __table_args__ = (
        {'primary_key': [account_id, datetime]},
        CheckConstraint('balance >= 0', name='chk_hourly_balance_positive'),
        CheckConstraint('open_positions >= 0', name='chk_hourly_open_positions_non_negative'),
        Index('idx_raw_metrics_hourly_datetime', 'datetime'),
        Index('idx_raw_metrics_hourly_account_datetime', 'account_id', 'datetime'),
        Index('idx_raw_metrics_hourly_last_updated', 'last_updated'),
    )


class RawTradesClosed(Base):
    """Closed trades data."""
    __tablename__ = "raw_trades_closed"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    ticket = Column(BIGINT, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=True)
    type = Column(String(10), nullable=True)
    volume = Column(DECIMAL(10, 2), nullable=True)
    open_time = Column(TIMESTAMP(timezone=True), nullable=True)
    close_time = Column(TIMESTAMP(timezone=True), nullable=True)
    open_price = Column(DECIMAL(10, 5), nullable=True)
    close_price = Column(DECIMAL(10, 5), nullable=True)
    profit = Column(DECIMAL(15, 2), nullable=True)
    commission = Column(DECIMAL(15, 2), nullable=True)
    swap = Column(DECIMAL(15, 2), nullable=True)
    comment = Column(Text, nullable=True)
    magic_number = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint('volume > 0', name='chk_volume_positive'),
        CheckConstraint('open_time <= close_time', name='chk_time_order'),
        Index('idx_raw_trades_closed_symbol', 'symbol'),
        Index('idx_raw_trades_closed_close_time', 'close_time'),
        Index('idx_raw_trades_closed_account_close_time', 'account_id', 'close_time'),
        Index('idx_raw_trades_closed_profit', 'profit'),
    )


class RawTradesOpen(Base):
    """Open trades data."""
    __tablename__ = "raw_trades_open"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    ticket = Column(BIGINT, primary_key=True, nullable=False)
    symbol = Column(String(20), nullable=True)
    type = Column(String(10), nullable=True)
    volume = Column(DECIMAL(10, 2), nullable=True)
    open_time = Column(TIMESTAMP(timezone=True), nullable=True)
    open_price = Column(DECIMAL(10, 5), nullable=True)
    current_price = Column(DECIMAL(10, 5), nullable=True)
    profit = Column(DECIMAL(15, 2), nullable=True)
    commission = Column(DECIMAL(15, 2), nullable=True)
    swap = Column(DECIMAL(15, 2), nullable=True)
    comment = Column(Text, nullable=True)
    magic_number = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint('volume > 0', name='chk_open_volume_positive'),
        Index('idx_raw_trades_open_symbol', 'symbol'),
        Index('idx_raw_trades_open_open_time', 'open_time'),
        Index('idx_raw_trades_open_account_open_time', 'account_id', 'open_time'),
        Index('idx_raw_trades_open_profit', 'profit'),
    )


class MarketRegimes(Base):
    """Market regime data for ML features."""
    __tablename__ = "market_regimes"
    
    date = Column(DateTime, primary_key=True, nullable=False)
    regime_type = Column(String(20), nullable=True)
    volatility_regime = Column(String(20), nullable=True)
    trend_strength = Column(DECIMAL(5, 4), nullable=True)
    market_stress = Column(DECIMAL(5, 4), nullable=True)
    correlation_regime = Column(String(20), nullable=True)
    regime_confidence = Column(DECIMAL(5, 4), nullable=True)
    regime_features = Column(JSONB, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('trend_strength >= 0 AND trend_strength <= 1', name='chk_trend_strength_range'),
        CheckConstraint('market_stress >= 0 AND market_stress <= 1', name='chk_market_stress_range'),
        CheckConstraint('regime_confidence >= 0 AND regime_confidence <= 1', name='chk_regime_confidence_range'),
        Index('idx_market_regimes_regime_type', 'regime_type'),
        Index('idx_market_regimes_date', 'date'),
    )


class TradingPlans(Base):
    """Trading plans and strategies."""
    __tablename__ = "trading_plans"
    
    plan_id = Column(String(50), primary_key=True, nullable=False)
    plan_name = Column(String(100), nullable=False)
    strategy_type = Column(String(50), nullable=True)
    risk_level = Column(String(20), nullable=True)
    max_drawdown_limit = Column(DECIMAL(5, 2), nullable=True)
    target_return = Column(DECIMAL(5, 2), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_date = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('max_drawdown_limit >= 0 AND max_drawdown_limit <= 100', name='chk_max_drawdown_range'),
        CheckConstraint('target_return >= 0', name='chk_target_return_positive'),
        Index('idx_trading_plans_active', 'active'),
        Index('idx_trading_plans_strategy_type', 'strategy_type'),
    )


class FeaturesEngineered(Base):
    """Engineered features for ML models."""
    __tablename__ = "features_engineered"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    feature_date = Column(DateTime, primary_key=True, nullable=False)
    feature_version = Column(String(20), primary_key=True, nullable=False, default='v1.0')
    
    # Performance features
    rolling_return_7d = Column(DECIMAL(8, 4), nullable=True)
    rolling_return_30d = Column(DECIMAL(8, 4), nullable=True)
    rolling_volatility_7d = Column(DECIMAL(8, 4), nullable=True)
    rolling_volatility_30d = Column(DECIMAL(8, 4), nullable=True)
    sharpe_ratio_30d = Column(DECIMAL(8, 4), nullable=True)
    max_drawdown_30d = Column(DECIMAL(8, 4), nullable=True)
    
    # Risk features
    var_95_7d = Column(DECIMAL(15, 2), nullable=True)
    var_99_7d = Column(DECIMAL(15, 2), nullable=True)
    expected_shortfall_95_7d = Column(DECIMAL(15, 2), nullable=True)
    
    # Behavioral features
    avg_trade_duration_hours = Column(DECIMAL(8, 2), nullable=True)
    trade_frequency_daily = Column(DECIMAL(6, 2), nullable=True)
    win_loss_ratio = Column(DECIMAL(8, 4), nullable=True)
    profit_factor_30d = Column(DECIMAL(8, 4), nullable=True)
    
    # Market regime interaction
    regime_performance_bull = Column(DECIMAL(8, 4), nullable=True)
    regime_performance_bear = Column(DECIMAL(8, 4), nullable=True)
    regime_performance_sideways = Column(DECIMAL(8, 4), nullable=True)
    
    # Time-based features
    hour_of_day = Column(Integer, nullable=True)
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    month_of_year = Column(Integer, nullable=True)
    
    # Target variables (for ML)
    target_return_1d = Column(DECIMAL(8, 4), nullable=True)
    target_return_7d = Column(DECIMAL(8, 4), nullable=True)
    target_return_30d = Column(DECIMAL(8, 4), nullable=True)
    target_risk_adjusted_return_7d = Column(DECIMAL(8, 4), nullable=True)
    
    # Metadata
    feature_hash = Column(String(64), nullable=True)  # For version control
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint('hour_of_day >= 0 AND hour_of_day <= 23', name='chk_hour_range'),
        CheckConstraint('day_of_week >= 1 AND day_of_week <= 7', name='chk_day_of_week_range'),
        CheckConstraint('day_of_month >= 1 AND day_of_month <= 31', name='chk_day_of_month_range'),
        CheckConstraint('month_of_year >= 1 AND month_of_year <= 12', name='chk_month_range'),
        Index('idx_features_engineered_feature_date', 'feature_date'),
        Index('idx_features_engineered_account_date', 'account_id', 'feature_date'),
        Index('idx_features_engineered_version', 'feature_version'),
        Index('idx_features_engineered_hash', 'feature_hash'),
    )


class ModelPredictions(Base):
    """ML model predictions storage."""
    __tablename__ = "model_predictions"
    
    prediction_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(20), nullable=False)
    prediction_date = Column(TIMESTAMP(timezone=True), nullable=False)
    feature_date = Column(DateTime, nullable=False)
    
    # Predictions
    predicted_return_1d = Column(DECIMAL(8, 4), nullable=True)
    predicted_return_7d = Column(DECIMAL(8, 4), nullable=True)
    predicted_return_30d = Column(DECIMAL(8, 4), nullable=True)
    predicted_risk_score = Column(DECIMAL(5, 4), nullable=True)
    prediction_confidence = Column(DECIMAL(5, 4), nullable=True)
    
    # Model metadata
    feature_importance = Column(JSONB, nullable=True)
    model_metrics = Column(JSONB, nullable=True)
    
    # Validation
    actual_return_1d = Column(DECIMAL(8, 4), nullable=True)
    actual_return_7d = Column(DECIMAL(8, 4), nullable=True)
    actual_return_30d = Column(DECIMAL(8, 4), nullable=True)
    prediction_error_1d = Column(DECIMAL(8, 4), nullable=True)
    prediction_error_7d = Column(DECIMAL(8, 4), nullable=True)
    prediction_error_30d = Column(DECIMAL(8, 4), nullable=True)
    
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('predicted_risk_score >= 0 AND predicted_risk_score <= 1', name='chk_risk_score_range'),
        CheckConstraint('prediction_confidence >= 0 AND prediction_confidence <= 1', name='chk_confidence_range'),
        Index('idx_model_predictions_account_id', 'account_id'),
        Index('idx_model_predictions_model', 'model_name', 'model_version'),
        Index('idx_model_predictions_prediction_date', 'prediction_date'),
        Index('idx_model_predictions_feature_date', 'feature_date'),
    )


# Relationships (for ORM usage)
# Note: These are optional but useful for complex queries

# Add foreign key relationships if needed
# Example:
# RawMetricsDaily.account = relationship("RawMetricsAlltime", 
#                                       foreign_keys=[RawMetricsDaily.account_id],
#                                       primaryjoin="RawMetricsDaily.account_id == RawMetricsAlltime.account_id")


# Materialized views (represented as tables for SQLAlchemy)
class AccountPerformanceSummary(Base):
    """Materialized view for account performance summary."""
    __tablename__ = "account_performance_summary"
    
    account_id = Column(String(50), primary_key=True, nullable=False)
    total_trades = Column(Integer, nullable=True)
    total_profit = Column(DECIMAL(15, 2), nullable=True)
    success_rate = Column(DECIMAL(5, 2), nullable=True)
    avg_monthly_return = Column(DECIMAL(8, 4), nullable=True)
    max_drawdown = Column(DECIMAL(15, 2), nullable=True)
    sharpe_ratio = Column(DECIMAL(8, 4), nullable=True)
    profit_factor = Column(DECIMAL(8, 4), nullable=True)
    last_trade_date = Column(DateTime, nullable=True)
    account_age_days = Column(Integer, nullable=True)
    risk_score = Column(DECIMAL(5, 4), nullable=True)
    performance_rank = Column(Integer, nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_account_performance_summary_success_rate', 'success_rate'),
        Index('idx_account_performance_summary_sharpe_ratio', 'sharpe_ratio'),
        Index('idx_account_performance_summary_performance_rank', 'performance_rank'),
    )


class DailyMarketSummary(Base):
    """Materialized view for daily market summary."""
    __tablename__ = "daily_market_summary"
    
    date = Column(DateTime, primary_key=True, nullable=False)
    total_accounts = Column(Integer, nullable=True)
    active_accounts = Column(Integer, nullable=True)
    total_trades = Column(Integer, nullable=True)
    total_volume = Column(DECIMAL(15, 2), nullable=True)
    avg_daily_return = Column(DECIMAL(8, 4), nullable=True)
    market_volatility = Column(DECIMAL(8, 4), nullable=True)
    top_performing_accounts = Column(Integer, nullable=True)
    worst_performing_accounts = Column(Integer, nullable=True)
    regime_type = Column(String(20), nullable=True)
    last_updated = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_daily_market_summary_date', 'date'),
        Index('idx_daily_market_summary_regime_type', 'regime_type'),
    ) 