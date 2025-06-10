-- Auto-generated migration 2025-06-10T00:29:25.161894
-- Preserve data: True
BEGIN;

DROP INDEX IF EXISTS prop_trading_model.alembic_version_pkc CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_daily_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_daily_account_id_date_ingestion_timestamp_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_trades_closed_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_hourly_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_hourly_account_id_date_hour_ingestion_timestamp_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_hourly_account_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_trades_open_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_trade_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_regimes_daily_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_regimes_daily_date_ingestion_timestamp_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_regimes_daily_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_regimes_daily_ingestion CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_training_input_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_training_input_login_prediction_date_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_training_login CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_training_prediction_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_training_feature_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_predictions_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_predictions_login_prediction_date_model_version_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_predictions_login CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_predictions_login_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_registry_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.model_registry_model_version_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.pipeline_execution_log_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_pipeline_log_stage CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_pipeline_log_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_pipeline_log_status CASCADE;
DROP INDEX IF EXISTS prop_trading_model.query_performance_log_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_query_performance_fingerprint CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_query_performance_logged_at CASCADE;
DROP INDEX IF EXISTS prop_trading_model.scheduled_jobs_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.scheduled_jobs_job_name_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_plans_data_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_plans_data_plan_id_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_accounts_data_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_accounts_data_account_id_ingestion_timestamp_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.schema_migrations_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_trades_closed_pkey1 CASCADE;
DROP INDEX IF EXISTS prop_trading_model.stg_accounts_daily_snapshots_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.stg_accounts_daily_snapshots_account_id_date_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_account_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_alltime_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_alltime_account_id_ingestion_timestamp_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_plan_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_trader_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_status CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_phase CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_country CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_risk_adj_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_daily_sharpe CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_mean_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_daily_pkey1 CASCADE;
DROP INDEX IF EXISTS prop_trading_model.raw_metrics_daily_account_id_date_ingestion_timestamp_key1 CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_plan_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_status_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_days_to_payout CASCADE;
DROP INDEX IF EXISTS prop_trading_model.feature_store_account_daily_pkey CASCADE;
DROP INDEX IF EXISTS prop_trading_model.feature_store_account_daily_account_id_feature_date_key CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_account_id CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_tstz_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_tstz_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_tstz_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_ts_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_timetz_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_timetz_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_time_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_date_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_decompress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_intv_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_cash_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bpchar_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bpchar_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_text_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bytea_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_numeric_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bit_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_inet_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_uuid_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_macad8_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_enum_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey2_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey2_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_bool_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.update_updated_at_column CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.update_table_statistics CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.vacuum_tables CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.analyze_partitions CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey4_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey4_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey8_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey8_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey16_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey16_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey32_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey32_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey_var_in CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbtreekey_var_out CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.cash_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.date_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.float4_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.float8_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.int2_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.int4_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.int8_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.interval_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.oid_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.time_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.ts_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.tstz_dist CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_decompress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_var_decompress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_var_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_oid_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int2_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int4_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_int8_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_distance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_compress CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_fetch CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_penalty CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_picksplit CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_union CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float4_same CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_consistent CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.gbt_float8_distance CASCADE;
-- Preserving table alembic_version
ALTER TABLE prop_trading_model.alembic_version RENAME TO alembic_version_archived_20250610_002925;
-- Preserving table raw_metrics_daily_old
ALTER TABLE prop_trading_model.raw_metrics_daily_old RENAME TO raw_metrics_daily_old_archived_20250610_002925;
-- Preserving table raw_trades_closed_old
ALTER TABLE prop_trading_model.raw_trades_closed_old RENAME TO raw_trades_closed_old_archived_20250610_002925;
-- Preserving table schema_migrations
ALTER TABLE prop_trading_model.schema_migrations RENAME TO schema_migrations_archived_20250610_002925;
-- TODO: Manually review alterations for table raw_accounts_data
-- Current definition: CREATE TABLE prop_trading_model.raw_accounts_data (--columns not available--);...
-- Desired definition: CREATE TABLE raw_accounts_data (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255) NOT NULL,   ...
-- TODO: Manually review alterations for table raw_metrics_alltime
-- Current definition: CREATE TABLE prop_trading_model.raw_metrics_alltime (--columns not available--);...
-- Desired definition: CREATE TABLE raw_metrics_alltime (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255) NOT NULL, ...
-- TODO: Manually review alterations for table raw_metrics_daily
-- Current definition: CREATE TABLE prop_trading_model.raw_metrics_daily (--columns not available--);...
-- Desired definition: CREATE TABLE raw_metrics_daily (     id BIGSERIAL,     account_id VARCHAR(255) NOT NULL,     login V...
-- TODO: Manually review alterations for table raw_metrics_hourly
-- Current definition: CREATE TABLE prop_trading_model.raw_metrics_hourly (--columns not available--);...
-- Desired definition: CREATE TABLE raw_metrics_hourly (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255) NOT NULL,  ...
-- TODO: Manually review alterations for table raw_trades_closed
-- Current definition: CREATE TABLE prop_trading_model.raw_trades_closed (--columns not available--);...
-- Desired definition: CREATE TABLE raw_trades_closed (     id BIGSERIAL,     account_id VARCHAR(255),      login VARCHAR(2...
-- TODO: Manually review alterations for table raw_trades_open
-- Current definition: CREATE TABLE prop_trading_model.raw_trades_open (--columns not available--);...
-- Desired definition: CREATE TABLE raw_trades_open (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255),      login VA...
-- TODO: Manually review alterations for table raw_plans_data
-- Current definition: CREATE TABLE prop_trading_model.raw_plans_data (--columns not available--);...
-- Desired definition: CREATE TABLE raw_plans_data (     id SERIAL PRIMARY KEY,     plan_id VARCHAR(255) NOT NULL,     plan...
-- TODO: Manually review alterations for table raw_regimes_daily
-- Current definition: CREATE TABLE prop_trading_model.raw_regimes_daily (--columns not available--);...
-- Desired definition: CREATE TABLE raw_regimes_daily (     id SERIAL PRIMARY KEY,     date DATE NOT NULL,     regime_name ...
-- TODO: Manually review alterations for table stg_accounts_daily_snapshots
-- Current definition: CREATE TABLE prop_trading_model.stg_accounts_daily_snapshots (--columns not available--);...
-- Desired definition: CREATE TABLE stg_accounts_daily_snapshots (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255) N...
-- TODO: Manually review alterations for table feature_store_account_daily
-- Current definition: CREATE TABLE prop_trading_model.feature_store_account_daily (--columns not available--);...
-- Desired definition: CREATE TABLE feature_store_account_daily (     id SERIAL PRIMARY KEY,     account_id VARCHAR(255) NO...
-- TODO: Manually review alterations for table model_training_input
-- Current definition: CREATE TABLE prop_trading_model.model_training_input (--columns not available--);...
-- Desired definition: CREATE TABLE model_training_input (     id SERIAL PRIMARY KEY,     model_version VARCHAR(100) NOT NU...
-- TODO: Manually review alterations for table model_predictions
-- Current definition: CREATE TABLE prop_trading_model.model_predictions (--columns not available--);...
-- Desired definition: CREATE TABLE model_predictions (     id SERIAL PRIMARY KEY,     model_version VARCHAR(100) NOT NULL,...
-- TODO: Manually review alterations for table model_registry
-- Current definition: CREATE TABLE prop_trading_model.model_registry (--columns not available--);...
-- Desired definition: CREATE TABLE model_registry (     id SERIAL PRIMARY KEY,     model_version VARCHAR(100) NOT NULL UNI...
-- TODO: Manually review alterations for table pipeline_execution_log
-- Current definition: CREATE TABLE prop_trading_model.pipeline_execution_log (--columns not available--);...
-- Desired definition: CREATE TABLE pipeline_execution_log (     id SERIAL PRIMARY KEY,     pipeline_stage VARCHAR(100) NOT...
-- TODO: Manually review alterations for table query_performance_log
-- Current definition: CREATE TABLE prop_trading_model.query_performance_log (--columns not available--);...
-- Desired definition: CREATE TABLE query_performance_log (     id SERIAL PRIMARY KEY,     query_hash VARCHAR(64),     quer...
-- TODO: Manually review alterations for table scheduled_jobs
-- Current definition: CREATE TABLE prop_trading_model.scheduled_jobs (--columns not available--);...
-- Desired definition: CREATE TABLE scheduled_jobs (     job_name VARCHAR(100) PRIMARY KEY,     schedule VARCHAR(100) NOT N...
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_account_id CASCADE;
CREATE INDEX idx_raw_accounts_account_id ON raw_accounts_data(account_id);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_login CASCADE;
CREATE INDEX idx_raw_accounts_login ON raw_accounts_data(login);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_trader_id CASCADE;
CREATE INDEX idx_raw_accounts_trader_id ON raw_accounts_data(trader_id) WHERE trader_id IS NOT NULL;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_plan_id CASCADE;
CREATE INDEX idx_raw_accounts_plan_id ON raw_accounts_data(plan_id) WHERE plan_id IS NOT NULL;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_ingestion CASCADE;
CREATE INDEX idx_raw_accounts_ingestion ON raw_accounts_data(ingestion_timestamp DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_status CASCADE;
CREATE INDEX idx_raw_accounts_status ON raw_accounts_data(status) WHERE status = 'Active';
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_phase CASCADE;
CREATE INDEX idx_raw_accounts_phase ON raw_accounts_data(phase);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_updated CASCADE;
CREATE INDEX idx_raw_accounts_updated ON raw_accounts_data(updated_at DESC) WHERE updated_at IS NOT NULL;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_account_id CASCADE;
CREATE INDEX idx_raw_metrics_alltime_account_id ON raw_metrics_alltime(account_id);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_login CASCADE;
CREATE INDEX idx_raw_metrics_alltime_login ON raw_metrics_alltime(login);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_hourly_date_hour CASCADE;
CREATE INDEX idx_raw_metrics_hourly_date_hour ON raw_metrics_hourly(date DESC, hour);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_login CASCADE;
CREATE INDEX idx_raw_trades_closed_login ON raw_trades_closed(login);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_account_id CASCADE;
CREATE INDEX idx_raw_trades_open_account_id ON raw_trades_open(account_id);
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_login CASCADE;
CREATE INDEX idx_raw_trades_open_login ON raw_trades_open(login);
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_account_date CASCADE;
CREATE INDEX idx_stg_accounts_daily_account_date ON stg_accounts_daily_snapshots(account_id, snapshot_date DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_date CASCADE;
CREATE INDEX idx_stg_accounts_daily_date ON stg_accounts_daily_snapshots(snapshot_date DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_account_date CASCADE;
CREATE INDEX idx_feature_store_account_date ON feature_store_account_daily(account_id, feature_date DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_date CASCADE;
CREATE INDEX idx_feature_store_date ON feature_store_account_daily(feature_date DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_model_predictions_date CASCADE;
CREATE INDEX idx_model_predictions_date ON model_predictions(prediction_date DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_account_id CASCADE;
CREATE UNIQUE INDEX idx_mv_account_performance_account_id ON mv_account_performance_summary(account_id);
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_status CASCADE;
CREATE INDEX idx_mv_account_performance_status ON mv_account_performance_summary(status) WHERE status = 'Active';
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_profit CASCADE;
CREATE INDEX idx_mv_account_performance_profit ON mv_account_performance_summary(lifetime_profit DESC);
DROP INDEX IF EXISTS prop_trading_model.idx_mv_daily_stats_date CASCADE;
CREATE UNIQUE INDEX idx_mv_daily_stats_date ON mv_daily_trading_stats(date);
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_symbol CASCADE;
CREATE UNIQUE INDEX idx_mv_symbol_performance_symbol ON mv_symbol_performance(std_symbol);
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_profit CASCADE;
CREATE INDEX idx_mv_symbol_performance_profit ON mv_symbol_performance(total_profit DESC);
DROP FUNCTION IF EXISTS prop_trading_model.refresh_materialized_views CASCADE;
CREATE OR REPLACE FUNCTION refresh_materialized_views() RETURNS void AS $$
BEGIN
    
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_performance_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_trading_patterns;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_market_regime_performance;
    
    
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        execution_details
    ) VALUES (
        'materialized_view_refresh',
        CURRENT_DATE,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        'success',
        jsonb_build_object(
            'views_refreshed', ARRAY[
                'mv_daily_trading_stats', 
                'mv_symbol_performance', 
                'mv_account_performance_summary',
                'mv_account_trading_patterns',
                'mv_market_regime_performance'
            ]
        )
    );
END;
$$ LANGUAGE plpgsql;
DROP FUNCTION IF EXISTS prop_trading_model.create_monthly_partitions CASCADE;
CREATE OR REPLACE FUNCTION create_monthly_partitions(
    table_name text,
    start_date date,
    end_date date
) RETURNS void AS $$
DECLARE
    partition_date date;
    partition_name text;
    date_column text;
BEGIN
    
    IF table_name = 'raw_metrics_daily' THEN
        date_column := 'date';
    ELSIF table_name = 'raw_trades_closed' THEN
        date_column := 'trade_date';
    ELSE
        RAISE EXCEPTION 'Unknown table for partitioning: %', table_name;
    END IF;
    
    
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            end_date,
            interval '1 month'
        )::date
    LOOP
        partition_name := table_name || '_' || to_char(partition_date, 'YYYY_MM');
        
        
        IF NOT EXISTS (
            SELECT 1 FROM pg_tables 
            WHERE schemaname = 'prop_trading_model' 
            AND tablename = partition_name
        ) THEN
            EXECUTE format('
                CREATE TABLE %I PARTITION OF %I
                FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                table_name,
                partition_date,
                partition_date + interval '1 month'
            );
            
            RAISE NOTICE 'Created partition: %', partition_name;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_account_performance_summary CASCADE;
CREATE MATERIALIZED VIEW mv_account_performance_summary AS
SELECT 
    a.account_id,
    a.login,
    a.trader_id,
    a.plan_id,
    a.phase,
    a.status,
    a.starting_balance,
    a.current_balance,
    a.current_equity,
    p.plan_name,
    p.profit_target_pct,
    p.max_drawdown_pct,
    p.max_daily_drawdown_pct,
    p.max_leverage,
    p.min_trading_days,
    p.max_trading_days,
    
    COALESCE(m.total_trades, 0) as lifetime_trades,
    COALESCE(m.net_profit, 0) as lifetime_profit,
    COALESCE(m.gross_profit, 0) as lifetime_gross_profit,
    COALESCE(m.gross_loss, 0) as lifetime_gross_loss,
    COALESCE(m.win_rate, 0) as lifetime_win_rate,
    COALESCE(m.profit_factor, 0) as lifetime_profit_factor,
    COALESCE(m.sharpe_ratio, 0) as lifetime_sharpe_ratio,
    COALESCE(m.sortino_ratio, 0) as lifetime_sortino_ratio,
    COALESCE(m.max_drawdown_pct, 0) as lifetime_max_drawdown_pct,
    
    COALESCE(daily.trades_last_30d, 0) as trades_last_30d,
    COALESCE(daily.profit_last_30d, 0) as profit_last_30d,
    COALESCE(daily.win_rate_last_30d, 0) as win_rate_last_30d,
    COALESCE(daily.trading_days_last_30d, 0) as trading_days_last_30d,
    
    COALESCE(weekly.trades_last_7d, 0) as trades_last_7d,
    COALESCE(weekly.profit_last_7d, 0) as profit_last_7d,
    COALESCE(weekly.win_rate_last_7d, 0) as win_rate_last_7d,
    
    CASE 
        WHEN a.starting_balance > 0 
        THEN ((a.current_balance - a.starting_balance) / a.starting_balance * 100)
        ELSE 0 
    END as total_return_pct,
    CASE 
        WHEN p.profit_target > 0 
        THEN ((p.profit_target - (a.current_balance - a.starting_balance)) / p.profit_target * 100)
        ELSE 0 
    END as distance_to_target_pct,
    a.updated_at as last_updated,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM (
    SELECT DISTINCT ON (account_id) *
    FROM raw_accounts_data
    ORDER BY account_id, ingestion_timestamp DESC
) a
LEFT JOIN raw_plans_data p ON a.plan_id = p.plan_id
LEFT JOIN (
    SELECT DISTINCT ON (account_id) *
    FROM raw_metrics_alltime
    ORDER BY account_id, ingestion_timestamp DESC
) m ON a.account_id = m.account_id
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(total_trades) as trades_last_30d,
        SUM(net_profit) as profit_last_30d,
        COUNT(DISTINCT date) as trading_days_last_30d,
        CASE 
            WHEN SUM(total_trades) > 0 
            THEN SUM(winning_trades)::DECIMAL / SUM(total_trades) * 100
            ELSE 0 
        END as win_rate_last_30d
    FROM raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY account_id
) daily ON true
LEFT JOIN LATERAL (
    SELECT 
        account_id,
        SUM(total_trades) as trades_last_7d,
        SUM(net_profit) as profit_last_7d,
        CASE 
            WHEN SUM(total_trades) > 0 
            THEN SUM(winning_trades)::DECIMAL / SUM(total_trades) * 100
            ELSE 0 
        END as win_rate_last_7d
    FROM raw_metrics_daily
    WHERE account_id = a.account_id
        AND date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY account_id
) weekly ON true
WITH DATA;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_daily_trading_stats CASCADE;
CREATE MATERIALIZED VIEW mv_daily_trading_stats AS
SELECT 
    date,
    COUNT(DISTINCT account_id) as active_accounts,
    COUNT(DISTINCT CASE WHEN net_profit > 0 THEN account_id END) as profitable_accounts,
    COUNT(DISTINCT CASE WHEN net_profit < 0 THEN account_id END) as losing_accounts,
    SUM(total_trades) as total_trades,
    SUM(winning_trades) as total_winning_trades,
    SUM(losing_trades) as total_losing_trades,
    SUM(net_profit) as total_profit,
    SUM(gross_profit) as total_gross_profit,
    SUM(gross_loss) as total_gross_loss,
    AVG(net_profit) as avg_profit,
    STDDEV(net_profit) as profit_stddev,
    SUM(volume_traded) as total_volume,
    SUM(lots_traded) as total_lots,
    AVG(win_rate) as avg_win_rate,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_profit) as median_profit,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY net_profit) as profit_q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY net_profit) as profit_q3,
    MAX(net_profit) as max_profit,
    MIN(net_profit) as min_profit,
    
    EXTRACT(DOW FROM date)::INTEGER as day_of_week,
    EXTRACT(WEEK FROM date)::INTEGER as week_number,
    EXTRACT(MONTH FROM date)::INTEGER as month,
    EXTRACT(YEAR FROM date)::INTEGER as year,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM raw_metrics_daily
WHERE date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY date
WITH DATA;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_symbol_performance CASCADE;
CREATE MATERIALIZED VIEW mv_symbol_performance AS
WITH symbol_stats AS (
    SELECT 
        std_symbol,
        COUNT(DISTINCT account_id) as traders_count,
        COUNT(*) as total_trades,
        SUM(profit) as total_profit,
        AVG(profit) as avg_profit,
        STDDEV(profit) as profit_stddev,
        SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losing_trades,
        SUM(CASE WHEN profit > 0 THEN profit ELSE 0 END) as gross_profit,
        SUM(CASE WHEN profit < 0 THEN profit ELSE 0 END) as gross_loss,
        SUM(volume_usd) as total_volume,
        SUM(lots) as total_lots,
        MAX(profit) as max_profit,
        MIN(profit) as min_profit,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit) as median_profit,
        AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600) as avg_trade_duration_hours
    FROM raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days'
        AND std_symbol IS NOT NULL
    GROUP BY std_symbol
    HAVING COUNT(*) > 100  
)
SELECT 
    std_symbol,
    traders_count,
    total_trades,
    total_profit,
    avg_profit,
    profit_stddev,
    winning_trades,
    losing_trades,
    gross_profit,
    gross_loss,
    CASE 
        WHEN total_trades > 0 
        THEN winning_trades::DECIMAL / total_trades * 100 
        ELSE 0 
    END as win_rate,
    CASE 
        WHEN gross_loss < 0 
        THEN ABS(gross_profit / gross_loss)
        ELSE 0 
    END as profit_factor,
    total_volume,
    total_lots,
    max_profit,
    min_profit,
    median_profit,
    avg_trade_duration_hours,
    CASE 
        WHEN profit_stddev > 0 
        THEN avg_profit / profit_stddev 
        ELSE 0 
    END as sharpe_approximation,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM symbol_stats
WITH DATA;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE MATERIALIZED VIEW mv_account_trading_patterns AS
WITH recent_trades AS (
    SELECT 
        account_id,
        login,
        std_symbol,
        side,
        EXTRACT(HOUR FROM open_time) as trade_hour,
        EXTRACT(DOW FROM trade_date) as trade_dow,
        profit,
        lots,
        volume_usd,
        CASE WHEN stop_loss IS NOT NULL THEN 1 ELSE 0 END as has_sl,
        CASE WHEN take_profit IS NOT NULL THEN 1 ELSE 0 END as has_tp
    FROM raw_trades_closed
    WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'
)
SELECT 
    account_id,
    login,
    COUNT(*) as total_trades_30d,
    
    COUNT(DISTINCT std_symbol) as unique_symbols,
    MODE() WITHIN GROUP (ORDER BY std_symbol) as favorite_symbol,
    MAX(symbol_trades.symbol_count)::DECIMAL / COUNT(*) * 100 as top_symbol_concentration_pct,
    
    MODE() WITHIN GROUP (ORDER BY trade_hour) as favorite_hour,
    MODE() WITHIN GROUP (ORDER BY trade_dow) as favorite_day_of_week,
    
    AVG(lots) as avg_lot_size,
    STDDEV(lots) as lot_size_stddev,
    AVG(volume_usd) as avg_trade_volume,
    SUM(CASE WHEN side IN ('buy', 'BUY') THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) * 100 as buy_ratio,
    
    AVG(has_sl) * 100 as sl_usage_rate,
    AVG(has_tp) * 100 as tp_usage_rate,
    
    AVG(CASE WHEN trade_hour BETWEEN 8 AND 16 THEN profit END) as avg_profit_market_hours,
    AVG(CASE WHEN trade_hour NOT BETWEEN 8 AND 16 THEN profit END) as avg_profit_off_hours,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM recent_trades
LEFT JOIN LATERAL (
    SELECT std_symbol, COUNT(*) as symbol_count
    FROM recent_trades rt2
    WHERE rt2.account_id = recent_trades.account_id
    GROUP BY std_symbol
    ORDER BY COUNT(*) DESC
    LIMIT 1
) symbol_trades ON true
GROUP BY account_id, login
WITH DATA;
CREATE MATERIALIZED VIEW mv_market_regime_performance AS
SELECT 
    r.date,
    r.summary->>'market_sentiment' as market_sentiment,
    r.summary->>'volatility_regime' as volatility_regime,
    r.summary->>'liquidity_state' as liquidity_state,
    COUNT(DISTINCT m.account_id) as active_accounts,
    SUM(m.total_trades) as total_trades,
    SUM(m.net_profit) as total_profit,
    AVG(m.net_profit) as avg_profit,
    STDDEV(m.net_profit) as profit_stddev,
    AVG(m.win_rate) as avg_win_rate,
    SUM(m.volume_traded) as total_volume,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.net_profit) as median_profit,
    COUNT(DISTINCT CASE WHEN m.net_profit > 0 THEN m.account_id END) as profitable_accounts,
    CURRENT_TIMESTAMP as mv_refreshed_at
FROM raw_regimes_daily r
INNER JOIN raw_metrics_daily m ON r.date = m.date
WHERE r.date >= CURRENT_DATE - INTERVAL '180 days'
    AND r.summary IS NOT NULL
GROUP BY r.date, r.summary
WITH DATA;
CREATE OR REPLACE FUNCTION drop_old_partitions(
    table_name text,
    retention_months integer DEFAULT 36
) RETURNS void AS $$
DECLARE
    partition_record record;
    cutoff_date date;
BEGIN
    cutoff_date := CURRENT_DATE - (retention_months || ' months')::interval;
    
    FOR partition_record IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model' 
        AND tablename LIKE table_name || '_%'
        AND tablename ~ '\d{4}_\d{2}$'
    LOOP
        
        IF to_date(right(partition_record.tablename, 7), 'YYYY_MM') < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I.%I', 'prop_trading_model', partition_record.tablename);
            RAISE NOTICE 'Dropped old partition: %', partition_record.tablename;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
CREATE INDEX idx_raw_metrics_alltime_ingestion ON raw_metrics_alltime(ingestion_timestamp DESC);
CREATE INDEX idx_raw_metrics_alltime_profit ON raw_metrics_alltime(net_profit DESC) WHERE net_profit IS NOT NULL;
CREATE INDEX idx_raw_metrics_daily_account_date ON raw_metrics_daily(account_id, date DESC);
CREATE INDEX idx_raw_metrics_daily_date ON raw_metrics_daily(date DESC);
CREATE INDEX idx_raw_metrics_daily_login ON raw_metrics_daily(login);
CREATE INDEX idx_raw_metrics_daily_profit ON raw_metrics_daily(date DESC, net_profit DESC) WHERE net_profit IS NOT NULL;
CREATE INDEX idx_raw_metrics_hourly_account_date ON raw_metrics_hourly(account_id, date DESC, hour);
CREATE INDEX idx_raw_trades_closed_account_date ON raw_trades_closed(account_id, trade_date DESC);
CREATE INDEX idx_raw_trades_closed_symbol ON raw_trades_closed(std_symbol, trade_date DESC) WHERE std_symbol IS NOT NULL;
CREATE INDEX idx_raw_trades_closed_profit ON raw_trades_closed(profit DESC, trade_date DESC);
CREATE INDEX idx_raw_trades_closed_trade_id ON raw_trades_closed(trade_id);
CREATE INDEX idx_raw_trades_open_trade_id ON raw_trades_open(trade_id);
CREATE INDEX idx_raw_trades_open_symbol ON raw_trades_open(std_symbol) WHERE std_symbol IS NOT NULL;
CREATE INDEX idx_raw_trades_open_ingestion ON raw_trades_open(ingestion_timestamp DESC);
CREATE INDEX idx_raw_plans_plan_id ON raw_plans_data(plan_id);
CREATE INDEX idx_raw_plans_name ON raw_plans_data(plan_name);
CREATE INDEX idx_raw_regimes_date ON raw_regimes_daily(date DESC);
CREATE INDEX idx_raw_regimes_summary ON raw_regimes_daily USING gin(summary);
CREATE INDEX idx_stg_accounts_daily_status ON stg_accounts_daily_snapshots(status) WHERE status = 'Active';
CREATE INDEX idx_feature_store_profit_target ON feature_store_account_daily(will_profit_next_day, feature_date DESC);
CREATE INDEX idx_model_predictions_account ON model_predictions(account_id, prediction_date DESC);
CREATE INDEX idx_pipeline_execution_stage_date ON pipeline_execution_log(pipeline_stage, execution_date DESC);
CREATE INDEX idx_pipeline_execution_status ON pipeline_execution_log(status, created_at DESC);
CREATE INDEX idx_mv_account_performance_phase ON mv_account_performance_summary(phase);
CREATE INDEX idx_mv_account_performance_recent_profit ON mv_account_performance_summary(profit_last_30d DESC);
CREATE INDEX idx_mv_daily_stats_year_month ON mv_daily_trading_stats(year, month);
CREATE INDEX idx_mv_daily_stats_dow ON mv_daily_trading_stats(day_of_week);
CREATE INDEX idx_mv_symbol_performance_trades ON mv_symbol_performance(total_trades DESC);
CREATE INDEX idx_mv_symbol_performance_win_rate ON mv_symbol_performance(win_rate DESC);
CREATE UNIQUE INDEX idx_mv_trading_patterns_account_id ON mv_account_trading_patterns(account_id);
CREATE INDEX idx_mv_trading_patterns_login ON mv_account_trading_patterns(login);
CREATE INDEX idx_mv_regime_performance_date ON mv_market_regime_performance(date DESC);
CREATE INDEX idx_mv_regime_performance_sentiment ON mv_market_regime_performance(market_sentiment);

COMMIT;