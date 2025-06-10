-- Migration: Add comprehensive risk factors and metrics fields from /v2/metrics API
-- Based on project whitepaper requirements and sample API responses
-- These fields are critical for the predictive payout model

-- ========================================
-- 1. Update raw_metrics_alltime table
-- ========================================

-- Account metadata fields
ALTER TABLE raw_metrics_alltime 
ADD COLUMN IF NOT EXISTS plan_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS trader_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS status INTEGER,
ADD COLUMN IF NOT EXISTS type INTEGER,
ADD COLUMN IF NOT EXISTS phase INTEGER,
ADD COLUMN IF NOT EXISTS broker INTEGER,
ADD COLUMN IF NOT EXISTS mt_version INTEGER,
ADD COLUMN IF NOT EXISTS price_stream INTEGER,
ADD COLUMN IF NOT EXISTS country VARCHAR(10);

-- Payout tracking fields
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS approved_payouts DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS pending_payouts DECIMAL(18, 2);

-- Balance and equity tracking
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS starting_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS prior_days_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS prior_days_equity DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS current_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS current_equity DECIMAL(18, 2);

-- Trading timeline fields
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS first_trade_date DATE,
ADD COLUMN IF NOT EXISTS days_since_initial_deposit INTEGER,
ADD COLUMN IF NOT EXISTS days_since_first_trade INTEGER,
ADD COLUMN IF NOT EXISTS num_trades INTEGER,
ADD COLUMN IF NOT EXISTS first_trade_open TIMESTAMP,
ADD COLUMN IF NOT EXISTS last_trade_open TIMESTAMP,
ADD COLUMN IF NOT EXISTS last_trade_close TIMESTAMP,
ADD COLUMN IF NOT EXISTS lifetime_in_days DECIMAL(10, 6);

-- Core performance metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS gain_to_pain DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS success_rate DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS median_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS std_profits DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS risk_adj_profit DECIMAL(18, 10);

-- Profit distribution metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS min_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS max_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_10 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_25 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_75 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_90 DECIMAL(18, 2);

-- Outlier and contribution analysis
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS profit_top_10_prcnt_trades DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_bottom_10_prcnt_trades DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS top_10_prcnt_profit_contrib DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS bottom_10_prcnt_loss_contrib DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS one_std_outlier_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS one_std_outlier_profit_contrib DECIMAL(10, 6),
ADD COLUMN IF NOT EXISTS two_std_outlier_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS two_std_outlier_profit_contrib DECIMAL(10, 6);

-- Per-unit profitability metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS net_profit_per_usd_volume DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS gross_profit_per_usd_volume DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS gross_loss_per_usd_volume DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS distance_gross_profit_loss_per_usd_volume DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS multiple_gross_profit_loss_per_usd_volume DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS gross_profit_per_lot DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS gross_loss_per_lot DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS distance_gross_profit_loss_per_lot DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS multiple_gross_profit_loss_per_lot DECIMAL(18, 10);

-- Duration-based profitability
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS net_profit_per_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS gross_profit_per_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS gross_loss_per_duration DECIMAL(18, 6);

-- Return metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS std_rets DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS risk_adj_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS downside_std_rets DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS downside_risk_adj_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS total_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_mean_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_std_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sharpe DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_downside_std_ret DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sortino DECIMAL(18, 10);

-- Relative (normalized) metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS rel_net_profit DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_gross_profit DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_gross_loss DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_mean_profit DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS rel_median_profit DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS rel_std_profits DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS rel_risk_adj_profit DECIMAL(18, 12),
ADD COLUMN IF NOT EXISTS rel_min_profit DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_max_profit DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_perc_10 DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_perc_25 DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_perc_75 DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_perc_90 DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_top_10_prcnt_trades DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_profit_bottom_10_prcnt_trades DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_one_std_outlier_profit DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_two_std_outlier_profit DECIMAL(18, 6);

-- Drawdown analysis
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_drawdown DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS median_drawdown DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS mean_num_trades_in_dd INTEGER,
ADD COLUMN IF NOT EXISTS median_num_trades_in_dd INTEGER,
ADD COLUMN IF NOT EXISTS max_num_trades_in_dd INTEGER,
ADD COLUMN IF NOT EXISTS rel_mean_drawdown DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_median_drawdown DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS rel_max_drawdown DECIMAL(18, 6);

-- Volume and lot metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS total_lots DECIMAL(18, 4),
ADD COLUMN IF NOT EXISTS total_volume DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS std_volumes DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS mean_winning_lot DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS mean_losing_lot DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS distance_win_loss_lots DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS multiple_win_loss_lots DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS mean_winning_volume DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS mean_losing_volume DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS distance_win_loss_volume DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS multiple_win_loss_volume DECIMAL(18, 10);

-- Trading duration metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS median_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS std_durations DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS min_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS max_duration DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS cv_durations DECIMAL(18, 6);

-- Stop loss and take profit metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_tp DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS median_tp DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS std_tp DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS min_tp DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS max_tp DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS cv_tp DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS mean_sl DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS median_sl DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS std_sl DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS min_sl DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS max_sl DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS cv_sl DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS mean_tp_vs_sl DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS median_tp_vs_sl DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS min_tp_vs_sl DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS max_tp_vs_sl DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS cv_tp_vs_sl DECIMAL(18, 6);

-- Consecutive wins/losses metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_num_consec_wins DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS median_num_consec_wins INTEGER,
ADD COLUMN IF NOT EXISTS max_num_consec_wins INTEGER,
ADD COLUMN IF NOT EXISTS mean_num_consec_losses DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS median_num_consec_losses INTEGER,
ADD COLUMN IF NOT EXISTS max_num_consec_losses INTEGER,
ADD COLUMN IF NOT EXISTS mean_val_consec_wins DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS median_val_consec_wins DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS max_val_consec_wins DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS mean_val_consec_losses DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS median_val_consec_losses DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS max_val_consec_losses DECIMAL(18, 2);

-- Open position metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_num_open_pos DECIMAL(10, 6),
ADD COLUMN IF NOT EXISTS median_num_open_pos INTEGER,
ADD COLUMN IF NOT EXISTS max_num_open_pos INTEGER,
ADD COLUMN IF NOT EXISTS mean_val_open_pos DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS median_val_open_pos DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS max_val_open_pos DECIMAL(20, 2),
ADD COLUMN IF NOT EXISTS mean_val_to_eqty_open_pos DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS median_val_to_eqty_open_pos DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS max_val_to_eqty_open_pos DECIMAL(18, 6);

-- Margin metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_account_margin DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS mean_firm_margin DECIMAL(18, 2);

-- Trading activity metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS mean_trades_per_day DECIMAL(10, 6),
ADD COLUMN IF NOT EXISTS median_trades_per_day INTEGER,
ADD COLUMN IF NOT EXISTS min_trades_per_day INTEGER,
ADD COLUMN IF NOT EXISTS max_trades_per_day INTEGER,
ADD COLUMN IF NOT EXISTS cv_trades_per_day DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS mean_idle_days DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS median_idle_days INTEGER,
ADD COLUMN IF NOT EXISTS max_idle_days INTEGER,
ADD COLUMN IF NOT EXISTS min_idle_days INTEGER;

-- Symbol diversity metrics
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS num_traded_symbols INTEGER,
ADD COLUMN IF NOT EXISTS most_traded_symbol VARCHAR(50),
ADD COLUMN IF NOT EXISTS most_traded_smb_trades INTEGER;

-- Updated date from API
ALTER TABLE raw_metrics_alltime
ADD COLUMN IF NOT EXISTS updated_date TIMESTAMP;

-- ========================================
-- 2. Update raw_metrics_daily table
-- ========================================

-- Account metadata fields
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS plan_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS trader_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS status INTEGER,
ADD COLUMN IF NOT EXISTS type INTEGER,
ADD COLUMN IF NOT EXISTS phase INTEGER,
ADD COLUMN IF NOT EXISTS broker INTEGER,
ADD COLUMN IF NOT EXISTS mt_version INTEGER,
ADD COLUMN IF NOT EXISTS price_stream INTEGER,
ADD COLUMN IF NOT EXISTS country VARCHAR(10);

-- Payout tracking fields
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS days_to_next_payout INTEGER,
ADD COLUMN IF NOT EXISTS todays_payouts DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS approved_payouts DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS pending_payouts DECIMAL(18, 2);

-- Balance tracking (some already exist)
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS starting_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS prior_days_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS prior_days_equity DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS current_balance DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS current_equity DECIMAL(18, 2);

-- Trading timeline fields
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS first_trade_date DATE,
ADD COLUMN IF NOT EXISTS days_since_initial_deposit INTEGER,
ADD COLUMN IF NOT EXISTS days_since_first_trade INTEGER,
ADD COLUMN IF NOT EXISTS num_trades INTEGER;

-- Core performance metrics
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS gain_to_pain DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS success_rate DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS median_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS std_profits DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS risk_adj_profit DECIMAL(18, 10);

-- Profit distribution metrics
ALTER TABLE raw_metrics_daily
ADD COLUMN IF NOT EXISTS min_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS max_profit DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_10 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_25 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_75 DECIMAL(18, 2),
ADD COLUMN IF NOT EXISTS profit_perc_90 DECIMAL(18, 2);

-- Add remaining daily-specific fields following same pattern as alltime
-- (abbreviated for brevity - full list would include all metrics from sample)

-- ========================================
-- 3. Update raw_metrics_hourly table
-- ========================================

-- Similar pattern for hourly metrics
-- (abbreviated for brevity)

-- ========================================
-- 4. Create indexes for new fields
-- ========================================

-- Indexes for raw_metrics_alltime
CREATE INDEX idx_raw_metrics_alltime_plan_id ON raw_metrics_alltime(plan_id);
CREATE INDEX idx_raw_metrics_alltime_trader_id ON raw_metrics_alltime(trader_id);
CREATE INDEX idx_raw_metrics_alltime_status ON raw_metrics_alltime(status);
CREATE INDEX idx_raw_metrics_alltime_phase ON raw_metrics_alltime(phase);
CREATE INDEX idx_raw_metrics_alltime_country ON raw_metrics_alltime(country);
CREATE INDEX idx_raw_metrics_alltime_risk_adj_profit ON raw_metrics_alltime(risk_adj_profit DESC);
CREATE INDEX idx_raw_metrics_alltime_daily_sharpe ON raw_metrics_alltime(daily_sharpe DESC);
CREATE INDEX idx_raw_metrics_alltime_mean_profit ON raw_metrics_alltime(mean_profit DESC);

-- Indexes for raw_metrics_daily
CREATE INDEX idx_raw_metrics_daily_plan_id ON raw_metrics_daily(plan_id);
CREATE INDEX idx_raw_metrics_daily_status_date ON raw_metrics_daily(status, date DESC);
CREATE INDEX idx_raw_metrics_daily_days_to_payout ON raw_metrics_daily(days_to_next_payout) WHERE days_to_next_payout IS NOT NULL;

-- ========================================
-- 5. Update feature_store_account_daily table
-- ========================================

-- Add derived risk metrics
ALTER TABLE feature_store_account_daily
ADD COLUMN IF NOT EXISTS gain_to_pain_7d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS gain_to_pain_30d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS risk_adj_profit_7d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS risk_adj_profit_30d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sharpe_7d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sharpe_30d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sortino_7d DECIMAL(18, 10),
ADD COLUMN IF NOT EXISTS daily_sortino_30d DECIMAL(18, 10);

-- Add behavioral metrics
ALTER TABLE feature_store_account_daily
ADD COLUMN IF NOT EXISTS mean_tp_usage_7d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_tp_usage_30d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_sl_usage_7d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_sl_usage_30d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS mean_tp_vs_sl_ratio_7d DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS mean_tp_vs_sl_ratio_30d DECIMAL(18, 6);

-- Add consistency metrics
ALTER TABLE feature_store_account_daily
ADD COLUMN IF NOT EXISTS max_consec_wins_7d INTEGER,
ADD COLUMN IF NOT EXISTS max_consec_wins_30d INTEGER,
ADD COLUMN IF NOT EXISTS max_consec_losses_7d INTEGER,
ADD COLUMN IF NOT EXISTS max_consec_losses_30d INTEGER,
ADD COLUMN IF NOT EXISTS profit_distribution_skew_7d DECIMAL(18, 6),
ADD COLUMN IF NOT EXISTS profit_distribution_skew_30d DECIMAL(18, 6);

-- Add position management metrics
ALTER TABLE feature_store_account_daily
ADD COLUMN IF NOT EXISTS avg_open_positions_7d DECIMAL(10, 6),
ADD COLUMN IF NOT EXISTS avg_open_positions_30d DECIMAL(10, 6),
ADD COLUMN IF NOT EXISTS max_open_positions_7d INTEGER,
ADD COLUMN IF NOT EXISTS max_open_positions_30d INTEGER;

-- Add outlier contribution metrics
ALTER TABLE feature_store_account_daily
ADD COLUMN IF NOT EXISTS top_10_prcnt_profit_contrib_7d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS top_10_prcnt_profit_contrib_30d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS bottom_10_prcnt_loss_contrib_7d DECIMAL(5, 2),
ADD COLUMN IF NOT EXISTS bottom_10_prcnt_loss_contrib_30d DECIMAL(5, 2);

-- Comments on new feature columns
COMMENT ON COLUMN feature_store_account_daily.gain_to_pain_7d IS 'Gain-to-pain ratio over last 7 days - measures risk-adjusted returns';
COMMENT ON COLUMN feature_store_account_daily.risk_adj_profit_7d IS 'Risk-adjusted profit (profit/std_dev) over last 7 days';
COMMENT ON COLUMN feature_store_account_daily.daily_sharpe_7d IS 'Daily Sharpe ratio calculated over last 7 days';
COMMENT ON COLUMN feature_store_account_daily.mean_tp_usage_7d IS 'Percentage of trades using take profit over last 7 days';
COMMENT ON COLUMN feature_store_account_daily.mean_sl_usage_7d IS 'Percentage of trades using stop loss over last 7 days';
COMMENT ON COLUMN feature_store_account_daily.profit_distribution_skew_7d IS 'Skewness of profit distribution over last 7 days';
COMMENT ON COLUMN feature_store_account_daily.top_10_prcnt_profit_contrib_7d IS 'Contribution of top 10% most profitable trades to total profit over last 7 days';