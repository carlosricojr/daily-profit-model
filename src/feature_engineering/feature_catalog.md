# Feature Catalog - Version 1.0.0

## Overview
This document catalogs all features used in the daily profit prediction model, including their definitions, calculations, and data quality considerations.

## Feature Categories

### 1. Static Features (Account & Plan Characteristics)
Features that remain constant or change infrequently.

| Feature Name | Type | Description | Source | Validation |
|-------------|------|-------------|--------|------------|
| `starting_balance` | DECIMAL | Initial account balance | stg_accounts_daily_snapshots | Must be > 0 |
| `max_daily_drawdown_pct` | DECIMAL | Maximum allowed daily drawdown percentage | stg_accounts_daily_snapshots | Range: 0-100 |
| `max_drawdown_pct` | DECIMAL | Maximum allowed total drawdown percentage | stg_accounts_daily_snapshots | Range: 0-100 |
| `profit_target_pct` | DECIMAL | Profit target percentage | stg_accounts_daily_snapshots | Range: 0-1000 |
| `max_leverage` | INTEGER | Maximum allowed leverage | stg_accounts_daily_snapshots | Range: 1-500 |
| `is_drawdown_relative` | INTEGER | Whether drawdown is calculated relative to peak (0/1) | stg_accounts_daily_snapshots | Binary: 0 or 1 |

### 2. Dynamic Features (Current Account State)
Features that represent the account state as of the feature_date.

| Feature Name | Type | Description | Source | Validation |
|-------------|------|-------------|--------|------------|
| `current_balance` | DECIMAL | Current account balance | stg_accounts_daily_snapshots | Must be >= 0 |
| `current_equity` | DECIMAL | Current account equity | stg_accounts_daily_snapshots | Must be >= 0 |
| `days_since_first_trade` | INTEGER | Number of days since first trade | stg_accounts_daily_snapshots | Must be >= 0 |
| `active_trading_days_count` | INTEGER | Number of days with trading activity | stg_accounts_daily_snapshots | Must be >= 0 |
| `distance_to_profit_target` | DECIMAL | Distance to profit target in USD | stg_accounts_daily_snapshots | Can be negative |
| `distance_to_max_drawdown` | DECIMAL | Distance to max drawdown in USD | stg_accounts_daily_snapshots | Can be negative |
| `open_pnl` | DECIMAL | Unrealized PnL from open positions | raw_trades_open | No limit |
| `open_positions_volume` | DECIMAL | Total volume of open positions in USD | raw_trades_open | Must be >= 0 |

### 3. Rolling Performance Features
Historical performance metrics calculated over rolling windows.

#### 1-Day Window
| Feature Name | Type | Description | Calculation |
|-------------|------|-------------|-------------|
| `rolling_pnl_sum_1d` | DECIMAL | Sum of PnL over 1 day | SUM(net_profit) for D |
| `rolling_pnl_avg_1d` | DECIMAL | Average PnL over 1 day | AVG(net_profit) for D |
| `rolling_pnl_std_1d` | DECIMAL | Standard deviation of PnL over 1 day | STDDEV(net_profit) for D |

#### 3-Day Window
| Feature Name | Type | Description | Calculation |
|-------------|------|-------------|-------------|
| `rolling_pnl_sum_3d` | DECIMAL | Sum of PnL over 3 days | SUM(net_profit) for D-2 to D |
| `rolling_pnl_avg_3d` | DECIMAL | Average PnL over 3 days | AVG(net_profit) for D-2 to D |
| `rolling_pnl_std_3d` | DECIMAL | Standard deviation of PnL over 3 days | STDDEV(net_profit) for D-2 to D |
| `rolling_pnl_min_3d` | DECIMAL | Minimum PnL over 3 days | MIN(net_profit) for D-2 to D |
| `rolling_pnl_max_3d` | DECIMAL | Maximum PnL over 3 days | MAX(net_profit) for D-2 to D |
| `win_rate_3d` | DECIMAL | Percentage of winning days over 3 days | COUNT(net_profit > 0) / 3 * 100 |

#### 5-Day Window
| Feature Name | Type | Description | Calculation |
|-------------|------|-------------|-------------|
| `rolling_pnl_sum_5d` | DECIMAL | Sum of PnL over 5 days | SUM(net_profit) for D-4 to D |
| `rolling_pnl_avg_5d` | DECIMAL | Average PnL over 5 days | AVG(net_profit) for D-4 to D |
| `rolling_pnl_std_5d` | DECIMAL | Standard deviation of PnL over 5 days | STDDEV(net_profit) for D-4 to D |
| `rolling_pnl_min_5d` | DECIMAL | Minimum PnL over 5 days | MIN(net_profit) for D-4 to D |
| `rolling_pnl_max_5d` | DECIMAL | Maximum PnL over 5 days | MAX(net_profit) for D-4 to D |
| `win_rate_5d` | DECIMAL | Percentage of winning days over 5 days | COUNT(net_profit > 0) / 5 * 100 |
| `profit_factor_5d` | DECIMAL | Ratio of gross profit to gross loss | SUM(profit) / ABS(SUM(loss)) |
| `sharpe_ratio_5d` | DECIMAL | Risk-adjusted return metric | (AVG(net_profit) / STDDEV(net_profit)) * SQRT(252) |

#### 10-Day Window
| Feature Name | Type | Description | Calculation |
|-------------|------|-------------|-------------|
| `rolling_pnl_sum_10d` | DECIMAL | Sum of PnL over 10 days | SUM(net_profit) for D-9 to D |
| `rolling_pnl_avg_10d` | DECIMAL | Average PnL over 10 days | AVG(net_profit) for D-9 to D |
| `rolling_pnl_std_10d` | DECIMAL | Standard deviation of PnL over 10 days | STDDEV(net_profit) for D-9 to D |
| `rolling_pnl_min_10d` | DECIMAL | Minimum PnL over 10 days | MIN(net_profit) for D-9 to D |
| `rolling_pnl_max_10d` | DECIMAL | Maximum PnL over 10 days | MAX(net_profit) for D-9 to D |
| `win_rate_10d` | DECIMAL | Percentage of winning days over 10 days | COUNT(net_profit > 0) / 10 * 100 |
| `profit_factor_10d` | DECIMAL | Ratio of gross profit to gross loss | SUM(profit) / ABS(SUM(loss)) |
| `sharpe_ratio_10d` | DECIMAL | Risk-adjusted return metric | (AVG(net_profit) / STDDEV(net_profit)) * SQRT(252) |

#### 20-Day Window
| Feature Name | Type | Description | Calculation |
|-------------|------|-------------|-------------|
| `rolling_pnl_sum_20d` | DECIMAL | Sum of PnL over 20 days | SUM(net_profit) for D-19 to D |
| `rolling_pnl_avg_20d` | DECIMAL | Average PnL over 20 days | AVG(net_profit) for D-19 to D |
| `rolling_pnl_std_20d` | DECIMAL | Standard deviation of PnL over 20 days | STDDEV(net_profit) for D-19 to D |
| `win_rate_20d` | DECIMAL | Percentage of winning days over 20 days | COUNT(net_profit > 0) / 20 * 100 |
| `profit_factor_20d` | DECIMAL | Ratio of gross profit to gross loss | SUM(profit) / ABS(SUM(loss)) |
| `sharpe_ratio_20d` | DECIMAL | Risk-adjusted return metric | (AVG(net_profit) / STDDEV(net_profit)) * SQRT(252) |

### 4. Behavioral Features
Trading behavior patterns calculated over a 5-day window.

| Feature Name | Type | Description | Source | Validation |
|-------------|------|-------------|--------|------------|
| `trades_count_5d` | INTEGER | Number of trades in last 5 days | raw_trades_closed | Must be >= 0 |
| `avg_trade_duration_5d` | DECIMAL | Average trade duration in hours | raw_trades_closed | Must be >= 0 |
| `avg_lots_per_trade_5d` | DECIMAL | Average lot size per trade | raw_trades_closed | Must be > 0 |
| `avg_volume_per_trade_5d` | DECIMAL | Average volume per trade in USD | raw_trades_closed | Must be > 0 |
| `stop_loss_usage_rate_5d` | DECIMAL | Percentage of trades with stop loss | raw_trades_closed | Range: 0-100 |
| `take_profit_usage_rate_5d` | DECIMAL | Percentage of trades with take profit | raw_trades_closed | Range: 0-100 |
| `buy_sell_ratio_5d` | DECIMAL | Ratio of buy trades to total trades | raw_trades_closed | Range: 0-1 |
| `top_symbol_concentration_5d` | DECIMAL | Percentage of trades in most traded symbol | raw_trades_closed | Range: 0-100 |

### 5. Market Regime Features
External market conditions and indicators.

| Feature Name | Type | Description | Source | Default |
|-------------|------|-------------|--------|---------|
| `market_sentiment_score` | DECIMAL | Average market sentiment score | raw_regimes_daily | 0.0 |
| `market_volatility_regime` | VARCHAR | Current volatility regime | raw_regimes_daily | 'normal' |
| `market_liquidity_state` | VARCHAR | Current liquidity state | raw_regimes_daily | 'normal' |
| `vix_level` | DECIMAL | VIX volatility index level | raw_regimes_daily | 15.0 |
| `dxy_level` | DECIMAL | US Dollar Index level | raw_regimes_daily | 100.0 |
| `sp500_daily_return` | DECIMAL | S&P 500 daily return percentage | raw_regimes_daily | 0.0 |
| `btc_volatility_90d` | DECIMAL | Bitcoin 90-day volatility | raw_regimes_daily | 0.5 |
| `fed_funds_rate` | DECIMAL | Federal funds effective rate | raw_regimes_daily | 5.0 |

### 6. Temporal Features
Date and time-based features.

| Feature Name | Type | Description | Calculation | Range |
|-------------|------|-------------|-------------|-------|
| `day_of_week` | INTEGER | Day of week (0=Monday) | feature_date.weekday() | 0-6 |
| `week_of_month` | INTEGER | Week of the month | (day - 1) // 7 + 1 | 1-5 |
| `month` | INTEGER | Month of the year | feature_date.month | 1-12 |
| `quarter` | INTEGER | Quarter of the year | (month - 1) // 3 + 1 | 1-4 |
| `day_of_year` | INTEGER | Day of the year | feature_date.timetuple().tm_yday | 1-366 |
| `is_month_start` | BOOLEAN | First 3 days of month | day <= 3 | true/false |
| `is_month_end` | BOOLEAN | Last 4 days of month | day >= 28 | true/false |
| `is_quarter_start` | BOOLEAN | First 3 days of quarter | month in [1,4,7,10] AND day <= 3 | true/false |
| `is_quarter_end` | BOOLEAN | Last 4 days of quarter | month in [3,6,9,12] AND day >= 28 | true/false |

## Target Variable

| Variable Name | Type | Description | Source | Alignment |
|--------------|------|-------------|--------|-----------|
| `target_net_profit` | DECIMAL | Net profit for prediction_date (D+1) | raw_metrics_daily | Features from D, target from D+1 |

## Data Quality Considerations

### 1. Lookahead Bias Prevention
- All features use data available as of feature_date (day D)
- Target variable uses data from prediction_date (day D+1)
- Rolling windows never include future data
- Market data is taken from feature_date, not prediction_date

### 2. Missing Data Handling
- Static features: Use NULL if account not found
- Dynamic features: Use 0 or NULL based on context
- Rolling features: Return 0 if insufficient history
- Market features: Use sensible defaults if data unavailable

### 3. Feature Validation Rules
- Percentages: Must be between 0 and 100
- Ratios: Must be between 0 and 1 (except profit factor)
- Counts: Must be non-negative integers
- Monetary values: Can be negative (for PnL)
- Sharpe ratio: Capped between -10 and 10 for stability

### 4. Version Control
- Current version: 1.0.0
- Feature changes tracked in feature_versions table
- Hash generated from sorted feature list for consistency

## Usage Notes

1. **Feature Engineering Pipeline**
   - Run daily after market close
   - Process accounts in batches for memory efficiency
   - Validate for lookahead bias before production use

2. **Training Data Creation**
   - Align features from D with targets from D+1
   - Filter for active accounts only
   - Create temporal train/test splits

3. **Model Training**
   - Use feature importance to identify key predictors
   - Monitor feature drift over time
   - Retrain when feature distributions change significantly