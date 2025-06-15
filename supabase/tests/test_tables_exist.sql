BEGIN;
SELECT plan(10);

-- Verify that critical pipeline tables exist
SELECT has_table('prop_trading_model'::name, 'raw_metrics_alltime'::name);
SELECT has_table('prop_trading_model'::name, 'raw_metrics_daily'::name);
SELECT has_table('prop_trading_model'::name, 'raw_metrics_hourly'::name);
SELECT has_table('prop_trading_model'::name, 'raw_trades_closed'::name);
SELECT has_table('prop_trading_model'::name, 'raw_trades_open'::name);
SELECT has_table('prop_trading_model'::name, 'raw_regimes_daily'::name);
SELECT has_table('prop_trading_model'::name, 'stg_accounts_daily_snapshots'::name);
SELECT has_table('prop_trading_model'::name, 'feature_store_account_daily'::name);
SELECT has_table('prop_trading_model'::name, 'model_registry'::name);
SELECT has_table('prop_trading_model'::name, 'model_predictions'::name);

SELECT * FROM finish();
ROLLBACK; 