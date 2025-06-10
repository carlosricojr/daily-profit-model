-- Rollback script for migration 2025-06-10T00:29:25.161899
BEGIN;

CREATE UNIQUE INDEX alembic_version_pkc ON prop_trading_model.alembic_version USING btree (version_num)
CREATE UNIQUE INDEX raw_metrics_daily_pkey ON ONLY prop_trading_model.raw_metrics_daily_old USING btree (id, date)
CREATE UNIQUE INDEX raw_metrics_daily_account_id_date_ingestion_timestamp_key ON ONLY prop_trading_model.raw_metrics_daily_old USING btree (account_id, date, ingestion_timestamp)
CREATE UNIQUE INDEX raw_trades_closed_pkey ON ONLY prop_trading_model.raw_trades_closed_old USING btree (id, trade_date)
CREATE UNIQUE INDEX raw_metrics_hourly_pkey ON prop_trading_model.raw_metrics_hourly USING btree (id)
CREATE UNIQUE INDEX raw_metrics_hourly_account_id_date_hour_ingestion_timestamp_key ON prop_trading_model.raw_metrics_hourly USING btree (account_id, date, hour, ingestion_timestamp)
CREATE INDEX idx_raw_metrics_hourly_account_id ON prop_trading_model.raw_metrics_hourly USING btree (account_id)
CREATE UNIQUE INDEX raw_trades_open_pkey ON prop_trading_model.raw_trades_open USING btree (id)
CREATE INDEX idx_raw_trades_open_trade_date ON prop_trading_model.raw_trades_open USING btree (trade_date)
CREATE UNIQUE INDEX raw_regimes_daily_pkey ON prop_trading_model.raw_regimes_daily USING btree (id)
CREATE UNIQUE INDEX raw_regimes_daily_date_ingestion_timestamp_key ON prop_trading_model.raw_regimes_daily USING btree (date, ingestion_timestamp)
CREATE INDEX idx_raw_regimes_daily_date ON prop_trading_model.raw_regimes_daily USING btree (date)
CREATE INDEX idx_raw_regimes_daily_ingestion ON prop_trading_model.raw_regimes_daily USING btree (ingestion_timestamp)
CREATE UNIQUE INDEX model_training_input_pkey ON prop_trading_model.model_training_input USING btree (id)
CREATE UNIQUE INDEX model_training_input_login_prediction_date_key ON prop_trading_model.model_training_input USING btree (login, prediction_date)
CREATE INDEX idx_model_training_login ON prop_trading_model.model_training_input USING btree (login)
CREATE INDEX idx_model_training_prediction_date ON prop_trading_model.model_training_input USING btree (prediction_date)
CREATE INDEX idx_model_training_feature_date ON prop_trading_model.model_training_input USING btree (feature_date)
CREATE UNIQUE INDEX model_predictions_pkey ON prop_trading_model.model_predictions USING btree (id)
CREATE UNIQUE INDEX model_predictions_login_prediction_date_model_version_key ON prop_trading_model.model_predictions USING btree (login, prediction_date, model_version)
CREATE INDEX idx_model_predictions_login ON prop_trading_model.model_predictions USING btree (login)
CREATE INDEX idx_model_predictions_login_date ON prop_trading_model.model_predictions USING btree (login, prediction_date)
CREATE UNIQUE INDEX model_registry_pkey ON prop_trading_model.model_registry USING btree (id)
CREATE UNIQUE INDEX model_registry_model_version_key ON prop_trading_model.model_registry USING btree (model_version)
CREATE UNIQUE INDEX pipeline_execution_log_pkey ON prop_trading_model.pipeline_execution_log USING btree (id)
CREATE INDEX idx_pipeline_log_stage ON prop_trading_model.pipeline_execution_log USING btree (pipeline_stage)
CREATE INDEX idx_pipeline_log_date ON prop_trading_model.pipeline_execution_log USING btree (execution_date)
CREATE INDEX idx_pipeline_log_status ON prop_trading_model.pipeline_execution_log USING btree (status)
CREATE UNIQUE INDEX query_performance_log_pkey ON prop_trading_model.query_performance_log USING btree (id)
CREATE INDEX idx_query_performance_fingerprint ON prop_trading_model.query_performance_log USING btree (query_fingerprint)
CREATE INDEX idx_query_performance_logged_at ON prop_trading_model.query_performance_log USING btree (logged_at DESC)
CREATE UNIQUE INDEX scheduled_jobs_pkey ON prop_trading_model.scheduled_jobs USING btree (job_id)
CREATE UNIQUE INDEX scheduled_jobs_job_name_key ON prop_trading_model.scheduled_jobs USING btree (job_name)
CREATE UNIQUE INDEX raw_plans_data_pkey ON prop_trading_model.raw_plans_data USING btree (id)
CREATE UNIQUE INDEX raw_plans_data_plan_id_key ON prop_trading_model.raw_plans_data USING btree (plan_id)
CREATE UNIQUE INDEX raw_accounts_data_pkey ON prop_trading_model.raw_accounts_data USING btree (id)
CREATE UNIQUE INDEX raw_accounts_data_account_id_ingestion_timestamp_key ON prop_trading_model.raw_accounts_data USING btree (account_id, ingestion_timestamp)
CREATE UNIQUE INDEX schema_migrations_pkey ON prop_trading_model.schema_migrations USING btree (migration_name)
CREATE UNIQUE INDEX raw_trades_closed_pkey1 ON ONLY prop_trading_model.raw_trades_closed USING btree (id, trade_date)
CREATE UNIQUE INDEX stg_accounts_daily_snapshots_pkey ON prop_trading_model.stg_accounts_daily_snapshots USING btree (id)
CREATE UNIQUE INDEX stg_accounts_daily_snapshots_account_id_date_key ON prop_trading_model.stg_accounts_daily_snapshots USING btree (account_id, date)
CREATE INDEX idx_stg_accounts_daily_account_id ON prop_trading_model.stg_accounts_daily_snapshots USING btree (account_id)
CREATE UNIQUE INDEX raw_metrics_alltime_pkey ON prop_trading_model.raw_metrics_alltime USING btree (id)
CREATE UNIQUE INDEX raw_metrics_alltime_account_id_ingestion_timestamp_key ON prop_trading_model.raw_metrics_alltime USING btree (account_id, ingestion_timestamp)
CREATE INDEX idx_raw_metrics_alltime_plan_id ON prop_trading_model.raw_metrics_alltime USING btree (plan_id)
CREATE INDEX idx_raw_metrics_alltime_trader_id ON prop_trading_model.raw_metrics_alltime USING btree (trader_id)
CREATE INDEX idx_raw_metrics_alltime_status ON prop_trading_model.raw_metrics_alltime USING btree (status)
CREATE INDEX idx_raw_metrics_alltime_phase ON prop_trading_model.raw_metrics_alltime USING btree (phase)
CREATE INDEX idx_raw_metrics_alltime_country ON prop_trading_model.raw_metrics_alltime USING btree (country)
CREATE INDEX idx_raw_metrics_alltime_risk_adj_profit ON prop_trading_model.raw_metrics_alltime USING btree (risk_adj_profit DESC)
CREATE INDEX idx_raw_metrics_alltime_daily_sharpe ON prop_trading_model.raw_metrics_alltime USING btree (daily_sharpe DESC)
CREATE INDEX idx_raw_metrics_alltime_mean_profit ON prop_trading_model.raw_metrics_alltime USING btree (mean_profit DESC)
CREATE UNIQUE INDEX raw_metrics_daily_pkey1 ON ONLY prop_trading_model.raw_metrics_daily USING btree (id, date)
CREATE UNIQUE INDEX raw_metrics_daily_account_id_date_ingestion_timestamp_key1 ON ONLY prop_trading_model.raw_metrics_daily USING btree (account_id, date, ingestion_timestamp)
CREATE INDEX idx_raw_metrics_daily_plan_id ON ONLY prop_trading_model.raw_metrics_daily USING btree (plan_id)
CREATE INDEX idx_raw_metrics_daily_status_date ON ONLY prop_trading_model.raw_metrics_daily USING btree (status, date DESC)
CREATE INDEX idx_raw_metrics_daily_days_to_payout ON ONLY prop_trading_model.raw_metrics_daily USING btree (days_to_next_payout) WHERE (days_to_next_payout IS NOT NULL)
CREATE UNIQUE INDEX feature_store_account_daily_pkey ON prop_trading_model.feature_store_account_daily USING btree (id)
CREATE UNIQUE INDEX feature_store_account_daily_account_id_feature_date_key ON prop_trading_model.feature_store_account_daily USING btree (account_id, feature_date)
CREATE INDEX idx_feature_store_account_id ON prop_trading_model.feature_store_account_daily USING btree (account_id)
CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_consistent(internal, timestamp without time zone, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_distance(internal, timestamp without time zone, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_tstz_consistent(internal, timestamp with time zone, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_tstz_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_tstz_distance(internal, timestamp with time zone, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_tstz_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_tstz_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_tstz_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_ts_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_ts_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_consistent(internal, time without time zone, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_distance(internal, time without time zone, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_timetz_consistent(internal, time with time zone, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_timetz_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_timetz_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_timetz_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_time_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_time_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_consistent(internal, date, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_distance(internal, date, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_union(internal, internal)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_date_same(gbtreekey8, gbtreekey8, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_date_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_consistent(internal, interval, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_distance(internal, interval, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_decompress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_decompress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_union(internal, internal)
 RETURNS gbtreekey32
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_intv_same(gbtreekey32, gbtreekey32, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_intv_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_consistent(internal, money, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_distance(internal, money, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_cash_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_cash_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_consistent(internal, macaddr, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_consistent(internal, text, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bpchar_consistent(internal, character, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bpchar_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bpchar_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bpchar_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_union(internal, internal)
 RETURNS gbtreekey_var
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_text_same(gbtreekey_var, gbtreekey_var, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_text_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_consistent(internal, bytea, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_union(internal, internal)
 RETURNS gbtreekey_var
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bytea_same(gbtreekey_var, gbtreekey_var, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bytea_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_consistent(internal, numeric, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_union(internal, internal)
 RETURNS gbtreekey_var
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_numeric_same(gbtreekey_var, gbtreekey_var, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_numeric_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_consistent(internal, bit, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_union(internal, internal)
 RETURNS gbtreekey_var
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bit_same(gbtreekey_var, gbtreekey_var, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_bit_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_consistent(internal, inet, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_inet_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_inet_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_consistent(internal, uuid, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_union(internal, internal)
 RETURNS gbtreekey32
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_uuid_same(gbtreekey32, gbtreekey32, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_uuid_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_consistent(internal, macaddr8, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_macad8_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_macad8_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_consistent(internal, anyenum, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_union(internal, internal)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_enum_same(gbtreekey8, gbtreekey8, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_enum_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey2_in(cstring)
 RETURNS gbtreekey2
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey2_out(gbtreekey2)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_consistent(internal, boolean, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_union(internal, internal)
 RETURNS gbtreekey2
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_bool_same(gbtreekey2, gbtreekey2, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE STRICT
AS '$libdir/btree_gist', $function$gbt_bool_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.update_updated_at_column()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$function$

CREATE OR REPLACE FUNCTION prop_trading_model.update_table_statistics()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    table_rec RECORD;
    start_time TIMESTAMP;
    total_tables INTEGER := 0;
    successful_tables INTEGER := 0;
BEGIN
    start_time := CURRENT_TIMESTAMP;
    
    -- Analyze all tables in the prop_trading_model schema
    FOR table_rec IN 
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model'
        ORDER BY tablename
    LOOP
        total_tables := total_tables + 1;
        
        BEGIN
            EXECUTE format('ANALYZE prop_trading_model.%I;', table_rec.tablename);
            successful_tables := successful_tables + 1;
            RAISE NOTICE 'Analyzed table: %', table_rec.tablename;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to analyze table %: %', table_rec.tablename, SQLERRM;
        END;
    END LOOP;
    
    -- Log the operation
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        records_processed,
        execution_details
    ) VALUES (
        'update_table_statistics',
        CURRENT_DATE,
        start_time,
        CURRENT_TIMESTAMP,
        CASE WHEN successful_tables = total_tables THEN 'success' ELSE 'partial_success' END,
        successful_tables,
        jsonb_build_object(
            'total_tables', total_tables,
            'successful_tables', successful_tables,
            'duration_seconds', EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))
        )
    );
    
    RAISE NOTICE 'Statistics update complete: %/% tables analyzed', successful_tables, total_tables;
END;
$function$

CREATE OR REPLACE FUNCTION prop_trading_model.vacuum_tables()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    table_rec RECORD;
    partition_rec RECORD;
    start_time TIMESTAMP;
    total_operations INTEGER := 0;
    successful_operations INTEGER := 0;
    operation_type TEXT;
BEGIN
    start_time := CURRENT_TIMESTAMP;
    
    -- Vacuum all regular tables in the prop_trading_model schema
    FOR table_rec IN 
        SELECT 
            tablename,
            CASE 
                WHEN tablename LIKE 'raw_%' THEN 'VACUUM ANALYZE'
                WHEN tablename LIKE 'mv_%' THEN 'VACUUM'  -- Materialized views
                ELSE 'VACUUM ANALYZE'
            END as vacuum_command
        FROM pg_tables 
        WHERE schemaname = 'prop_trading_model'
        ORDER BY 
            CASE 
                WHEN tablename IN ('raw_trades_closed', 'raw_metrics_daily') THEN 1  -- Partitioned tables first
                WHEN tablename LIKE 'raw_%' THEN 2  -- Raw tables
                WHEN tablename LIKE 'stg_%' THEN 3  -- Staging tables
                WHEN tablename LIKE 'feature_%' THEN 4  -- Feature tables
                WHEN tablename LIKE 'model_%' THEN 5  -- Model tables
                ELSE 6  -- Everything else
            END,
            tablename
    LOOP
        total_operations := total_operations + 1;
        
        BEGIN
            -- Skip partitioned parent tables (they don't store data directly)
            IF table_rec.tablename IN ('raw_trades_closed', 'raw_metrics_daily') THEN
                RAISE NOTICE 'Skipping partitioned parent table: %', table_rec.tablename;
                successful_operations := successful_operations + 1;
                CONTINUE;
            END IF;
            
            EXECUTE format('%s prop_trading_model.%I;', table_rec.vacuum_command, table_rec.tablename);
            successful_operations := successful_operations + 1;
            RAISE NOTICE 'Vacuumed table: % (% command)', table_rec.tablename, table_rec.vacuum_command;
            
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to vacuum table %: %', table_rec.tablename, SQLERRM;
        END;
    END LOOP;
    
    -- Vacuum partitions of partitioned tables
    FOR partition_rec IN 
        SELECT 
            child.relname as partition_name,
            parent.relname as parent_table
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace n ON parent.relnamespace = n.oid
        WHERE n.nspname = 'prop_trading_model'
        ORDER BY parent.relname, child.relname
    LOOP
        total_operations := total_operations + 1;
        
        BEGIN
            EXECUTE format('VACUUM ANALYZE prop_trading_model.%I;', partition_rec.partition_name);
            successful_operations := successful_operations + 1;
            RAISE NOTICE 'Vacuumed partition: % (parent: %)', partition_rec.partition_name, partition_rec.parent_table;
            
        EXCEPTION
            WHEN OTHERS THEN
                RAISE WARNING 'Failed to vacuum partition %: %', partition_rec.partition_name, SQLERRM;
        END;
    END LOOP;
    
    -- Log the operation
    INSERT INTO pipeline_execution_log (
        pipeline_stage, 
        execution_date, 
        start_time, 
        end_time, 
        status, 
        records_processed,
        execution_details
    ) VALUES (
        'vacuum_tables',
        CURRENT_DATE,
        start_time,
        CURRENT_TIMESTAMP,
        CASE WHEN successful_operations = total_operations THEN 'success' ELSE 'partial_success' END,
        successful_operations,
        jsonb_build_object(
            'total_operations', total_operations,
            'successful_operations', successful_operations,
            'duration_seconds', EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))
        )
    );
    
    RAISE NOTICE 'Vacuum complete: %/% operations successful', successful_operations, total_operations;
END;
$function$

CREATE OR REPLACE FUNCTION prop_trading_model.analyze_partitions()
 RETURNS TABLE(table_name text, partition_name text, size_pretty text, row_count bigint)
 LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT 
        parent.relname::TEXT as table_name,
        child.relname::TEXT as partition_name,
        pg_size_pretty(pg_relation_size(child.oid)) as size_pretty,
        child.reltuples::BIGINT as row_count
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    WHERE parent.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    ORDER BY parent.relname, child.relname;
END;
$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey4_in(cstring)
 RETURNS gbtreekey4
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey4_out(gbtreekey4)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey8_in(cstring)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey8_out(gbtreekey8)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey16_in(cstring)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey16_out(gbtreekey16)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey32_in(cstring)
 RETURNS gbtreekey32
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey32_out(gbtreekey32)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey_var_in(cstring)
 RETURNS gbtreekey_var
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_in$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbtreekey_var_out(gbtreekey_var)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbtreekey_out$function$

CREATE OR REPLACE FUNCTION prop_trading_model.cash_dist(money, money)
 RETURNS money
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$cash_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.date_dist(date, date)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$date_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.float4_dist(real, real)
 RETURNS real
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$float4_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.float8_dist(double precision, double precision)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$float8_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.int2_dist(smallint, smallint)
 RETURNS smallint
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$int2_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.int4_dist(integer, integer)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$int4_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.int8_dist(bigint, bigint)
 RETURNS bigint
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$int8_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.interval_dist(interval, interval)
 RETURNS interval
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$interval_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.oid_dist(oid, oid)
 RETURNS oid
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$oid_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.time_dist(time without time zone, time without time zone)
 RETURNS interval
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$time_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.ts_dist(timestamp without time zone, timestamp without time zone)
 RETURNS interval
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$ts_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.tstz_dist(timestamp with time zone, timestamp with time zone)
 RETURNS interval
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$tstz_dist$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_consistent(internal, oid, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_distance(internal, oid, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_decompress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_decompress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_var_decompress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_var_decompress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_var_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_var_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_union(internal, internal)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_oid_same(gbtreekey8, gbtreekey8, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_oid_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_consistent(internal, smallint, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_distance(internal, smallint, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_union(internal, internal)
 RETURNS gbtreekey4
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int2_same(gbtreekey4, gbtreekey4, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int2_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_consistent(internal, integer, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_distance(internal, integer, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_union(internal, internal)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int4_same(gbtreekey8, gbtreekey8, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int4_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_consistent(internal, bigint, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_distance(internal, bigint, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_union(internal, internal)
 RETURNS gbtreekey16
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_int8_same(gbtreekey16, gbtreekey16, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_int8_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_consistent(internal, real, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_distance(internal, real, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_distance$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_compress(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_compress$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_fetch(internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_fetch$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_penalty(internal, internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_penalty$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_picksplit(internal, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_picksplit$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_union(internal, internal)
 RETURNS gbtreekey8
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_union$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float4_same(gbtreekey8, gbtreekey8, internal)
 RETURNS internal
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float4_same$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_consistent(internal, double precision, smallint, oid, internal)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_consistent$function$

CREATE OR REPLACE FUNCTION prop_trading_model.gbt_float8_distance(internal, double precision, smallint, oid, internal)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/btree_gist', $function$gbt_float8_distance$function$

ALTER TABLE prop_trading_model.alembic_version_archived_20250610_002925 RENAME TO alembic_version;
ALTER TABLE prop_trading_model.raw_metrics_daily_old_archived_20250610_002925 RENAME TO raw_metrics_daily_old;
ALTER TABLE prop_trading_model.raw_trades_closed_old_archived_20250610_002925 RENAME TO raw_trades_closed_old;
ALTER TABLE prop_trading_model.schema_migrations_archived_20250610_002925 RENAME TO schema_migrations;
-- TODO: Manually review rollback for table raw_accounts_data
-- TODO: Manually review rollback for table raw_metrics_alltime
-- TODO: Manually review rollback for table raw_metrics_daily
-- TODO: Manually review rollback for table raw_metrics_hourly
-- TODO: Manually review rollback for table raw_trades_closed
-- TODO: Manually review rollback for table raw_trades_open
-- TODO: Manually review rollback for table raw_plans_data
-- TODO: Manually review rollback for table raw_regimes_daily
-- TODO: Manually review rollback for table stg_accounts_daily_snapshots
-- TODO: Manually review rollback for table feature_store_account_daily
-- TODO: Manually review rollback for table model_training_input
-- TODO: Manually review rollback for table model_predictions
-- TODO: Manually review rollback for table model_registry
-- TODO: Manually review rollback for table pipeline_execution_log
-- TODO: Manually review rollback for table query_performance_log
-- TODO: Manually review rollback for table scheduled_jobs
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_account_id CASCADE;
CREATE INDEX idx_raw_accounts_account_id ON prop_trading_model.raw_accounts_data USING btree (account_id)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_login CASCADE;
CREATE INDEX idx_raw_accounts_login ON prop_trading_model.raw_accounts_data USING btree (login)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_trader_id CASCADE;
CREATE INDEX idx_raw_accounts_trader_id ON prop_trading_model.raw_accounts_data USING btree (trader_id) WHERE (trader_id IS NOT NULL)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_plan_id CASCADE;
CREATE INDEX idx_raw_accounts_plan_id ON prop_trading_model.raw_accounts_data USING btree (plan_id) WHERE (plan_id IS NOT NULL)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_ingestion CASCADE;
CREATE INDEX idx_raw_accounts_ingestion ON prop_trading_model.raw_accounts_data USING btree (ingestion_timestamp DESC)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_status CASCADE;
CREATE INDEX idx_raw_accounts_status ON prop_trading_model.raw_accounts_data USING btree (status) WHERE ((status)::text = 'Active'::text)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_phase CASCADE;
CREATE INDEX idx_raw_accounts_phase ON prop_trading_model.raw_accounts_data USING btree (phase)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_accounts_updated CASCADE;
CREATE INDEX idx_raw_accounts_updated ON prop_trading_model.raw_accounts_data USING btree (updated_at DESC) WHERE (updated_at IS NOT NULL)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_account_id CASCADE;
CREATE INDEX idx_raw_metrics_alltime_account_id ON prop_trading_model.raw_metrics_alltime USING btree (account_id)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_login CASCADE;
CREATE INDEX idx_raw_metrics_alltime_login ON prop_trading_model.raw_metrics_alltime USING btree (login)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_hourly_date_hour CASCADE;
CREATE INDEX idx_raw_metrics_hourly_date_hour ON prop_trading_model.raw_metrics_hourly USING btree (date, hour)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_login CASCADE;
CREATE INDEX idx_raw_trades_closed_login ON ONLY prop_trading_model.raw_trades_closed USING btree (login)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_account_id CASCADE;
CREATE INDEX idx_raw_trades_open_account_id ON prop_trading_model.raw_trades_open USING btree (account_id)
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_login CASCADE;
CREATE INDEX idx_raw_trades_open_login ON prop_trading_model.raw_trades_open USING btree (login)
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_account_date CASCADE;
CREATE INDEX idx_stg_accounts_daily_account_date ON prop_trading_model.stg_accounts_daily_snapshots USING btree (account_id, date)
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_date CASCADE;
CREATE INDEX idx_stg_accounts_daily_date ON prop_trading_model.stg_accounts_daily_snapshots USING btree (date)
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_account_date CASCADE;
CREATE INDEX idx_feature_store_account_date ON prop_trading_model.feature_store_account_daily USING btree (account_id, feature_date)
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_date CASCADE;
CREATE INDEX idx_feature_store_date ON prop_trading_model.feature_store_account_daily USING btree (feature_date)
DROP INDEX IF EXISTS prop_trading_model.idx_model_predictions_date CASCADE;
CREATE INDEX idx_model_predictions_date ON prop_trading_model.model_predictions USING btree (prediction_date)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_account_id CASCADE;
CREATE UNIQUE INDEX idx_mv_account_performance_account_id ON prop_trading_model.mv_account_performance_summary USING btree (account_id)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_status CASCADE;
CREATE INDEX idx_mv_account_performance_status ON prop_trading_model.mv_account_performance_summary USING btree (status)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_profit CASCADE;
CREATE INDEX idx_mv_account_performance_profit ON prop_trading_model.mv_account_performance_summary USING btree (lifetime_profit DESC)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_daily_stats_date CASCADE;
CREATE UNIQUE INDEX idx_mv_daily_stats_date ON prop_trading_model.mv_daily_trading_stats USING btree (date)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_symbol CASCADE;
CREATE UNIQUE INDEX idx_mv_symbol_performance_symbol ON prop_trading_model.mv_symbol_performance USING btree (std_symbol)
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_profit CASCADE;
CREATE INDEX idx_mv_symbol_performance_profit ON prop_trading_model.mv_symbol_performance USING btree (total_profit DESC)
DROP FUNCTION IF EXISTS prop_trading_model.refresh_materialized_views CASCADE;
CREATE OR REPLACE FUNCTION prop_trading_model.refresh_materialized_views()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Refresh views in dependency order
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_performance_summary;
    
    -- Log refresh
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
            'views_refreshed', ARRAY['mv_daily_trading_stats', 'mv_symbol_performance', 'mv_account_performance_summary']
        )
    );
END;
$function$

DROP FUNCTION IF EXISTS prop_trading_model.create_monthly_partitions CASCADE;
CREATE OR REPLACE FUNCTION prop_trading_model.create_monthly_partitions()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    next_month DATE;
    partition_name TEXT;
BEGIN
    -- Create partition for next month if it doesn't exist
    next_month := DATE_TRUNC('month', CURRENT_DATE + INTERVAL '1 month');
    partition_name := 'raw_trades_closed_' || to_char(next_month, 'YYYY_MM');
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_class 
        WHERE relname = partition_name 
        AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'prop_trading_model')
    ) THEN
        EXECUTE format('
            CREATE TABLE %I PARTITION OF raw_trades_closed
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            next_month,
            next_month + INTERVAL '1 month'
        );
        
        -- Create indexes on new partition
        EXECUTE format('
            CREATE INDEX %I ON %I (account_id);
            CREATE INDEX %I ON %I (trade_date);
            CREATE INDEX %I ON %I (account_id, trade_date);',
            'idx_' || partition_name || '_account_id', partition_name,
            'idx_' || partition_name || '_trade_date', partition_name,
            'idx_' || partition_name || '_account_date', partition_name
        );
        
        RAISE NOTICE 'Created partition: %', partition_name;
    END IF;
END;
$function$

DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_account_performance_summary CASCADE;
CREATE MATERIALIZED VIEW mv_account_performance_summary AS  SELECT a.account_id,
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
    COALESCE(m.total_trades, 0) AS lifetime_trades,
    COALESCE(m.net_profit, (0)::numeric) AS lifetime_profit,
    COALESCE(m.win_rate, (0)::numeric) AS lifetime_win_rate,
    COALESCE(m.profit_factor, (0)::numeric) AS lifetime_profit_factor,
    COALESCE(m.sharpe_ratio, (0)::numeric) AS lifetime_sharpe_ratio,
    COALESCE(daily.trades_last_30d, (0)::bigint) AS trades_last_30d,
    COALESCE(daily.profit_last_30d, (0)::numeric) AS profit_last_30d,
    COALESCE(daily.win_rate_last_30d, (0)::numeric) AS win_rate_last_30d,
    a.updated_at AS last_updated
   FROM (((( SELECT DISTINCT ON (raw_accounts_data.account_id) raw_accounts_data.id,
            raw_accounts_data.account_id,
            raw_accounts_data.login,
            raw_accounts_data.trader_id,
            raw_accounts_data.plan_id,
            raw_accounts_data.starting_balance,
            raw_accounts_data.current_balance,
            raw_accounts_data.current_equity,
            raw_accounts_data.profit_target_pct,
            raw_accounts_data.max_daily_drawdown_pct,
            raw_accounts_data.max_drawdown_pct,
            raw_accounts_data.max_leverage,
            raw_accounts_data.is_drawdown_relative,
            raw_accounts_data.breached,
            raw_accounts_data.is_upgraded,
            raw_accounts_data.phase,
            raw_accounts_data.status,
            raw_accounts_data.created_at,
            raw_accounts_data.updated_at,
            raw_accounts_data.ingestion_timestamp,
            raw_accounts_data.source_api_endpoint
           FROM raw_accounts_data
          ORDER BY raw_accounts_data.account_id, raw_accounts_data.ingestion_timestamp DESC) a
     LEFT JOIN raw_plans_data p ON (((a.plan_id)::text = (p.plan_id)::text)))
     LEFT JOIN ( SELECT DISTINCT ON (raw_metrics_alltime.account_id) raw_metrics_alltime.id,
            raw_metrics_alltime.account_id,
            raw_metrics_alltime.login,
            raw_metrics_alltime.net_profit,
            raw_metrics_alltime.gross_profit,
            raw_metrics_alltime.gross_loss,
            raw_metrics_alltime.total_trades,
            raw_metrics_alltime.winning_trades,
            raw_metrics_alltime.losing_trades,
            raw_metrics_alltime.win_rate,
            raw_metrics_alltime.profit_factor,
            raw_metrics_alltime.average_win,
            raw_metrics_alltime.average_loss,
            raw_metrics_alltime.average_rrr,
            raw_metrics_alltime.expectancy,
            raw_metrics_alltime.sharpe_ratio,
            raw_metrics_alltime.sortino_ratio,
            raw_metrics_alltime.max_drawdown,
            raw_metrics_alltime.max_drawdown_pct,
            raw_metrics_alltime.ingestion_timestamp,
            raw_metrics_alltime.source_api_endpoint
           FROM raw_metrics_alltime
          ORDER BY raw_metrics_alltime.account_id, raw_metrics_alltime.ingestion_timestamp DESC) m ON (((a.account_id)::text = (m.account_id)::text)))
     LEFT JOIN LATERAL ( SELECT raw_metrics_daily_old.account_id,
            sum(raw_metrics_daily_old.total_trades) AS trades_last_30d,
            sum(raw_metrics_daily_old.net_profit) AS profit_last_30d,
                CASE
                    WHEN (sum(raw_metrics_daily_old.total_trades) > 0) THEN (((sum(raw_metrics_daily_old.winning_trades))::numeric / (sum(raw_metrics_daily_old.total_trades))::numeric) * (100)::numeric)
                    ELSE (0)::numeric
                END AS win_rate_last_30d
           FROM raw_metrics_daily_old
          WHERE (((raw_metrics_daily_old.account_id)::text = (a.account_id)::text) AND (raw_metrics_daily_old.date >= (CURRENT_DATE - '30 days'::interval)))
          GROUP BY raw_metrics_daily_old.account_id) daily ON (true));
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_daily_trading_stats CASCADE;
CREATE MATERIALIZED VIEW mv_daily_trading_stats AS  SELECT raw_metrics_daily_old.date,
    count(DISTINCT raw_metrics_daily_old.account_id) AS active_accounts,
    sum(raw_metrics_daily_old.total_trades) AS total_trades,
    sum(raw_metrics_daily_old.net_profit) AS total_profit,
    avg(raw_metrics_daily_old.net_profit) AS avg_profit,
    stddev(raw_metrics_daily_old.net_profit) AS profit_stddev,
    sum(raw_metrics_daily_old.volume_traded) AS total_volume,
    avg(raw_metrics_daily_old.win_rate) AS avg_win_rate,
    percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY ((raw_metrics_daily_old.net_profit)::double precision)) AS median_profit,
    percentile_cont((0.25)::double precision) WITHIN GROUP (ORDER BY ((raw_metrics_daily_old.net_profit)::double precision)) AS profit_q1,
    percentile_cont((0.75)::double precision) WITHIN GROUP (ORDER BY ((raw_metrics_daily_old.net_profit)::double precision)) AS profit_q3
   FROM raw_metrics_daily_old
  WHERE (raw_metrics_daily_old.date >= (CURRENT_DATE - '365 days'::interval))
  GROUP BY raw_metrics_daily_old.date;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_symbol_performance CASCADE;
CREATE MATERIALIZED VIEW mv_symbol_performance AS  SELECT raw_trades_closed_old.std_symbol,
    count(DISTINCT raw_trades_closed_old.account_id) AS traders_count,
    count(*) AS total_trades,
    sum(raw_trades_closed_old.profit) AS total_profit,
    avg(raw_trades_closed_old.profit) AS avg_profit,
    (((sum(
        CASE
            WHEN (raw_trades_closed_old.profit > (0)::numeric) THEN 1
            ELSE 0
        END))::numeric / (count(*))::numeric) * (100)::numeric) AS win_rate,
    sum(raw_trades_closed_old.volume_usd) AS total_volume,
    stddev(raw_trades_closed_old.profit) AS profit_stddev,
    max(raw_trades_closed_old.profit) AS max_profit,
    min(raw_trades_closed_old.profit) AS min_profit
   FROM raw_trades_closed_old
  WHERE ((raw_trades_closed_old.trade_date >= (CURRENT_DATE - '90 days'::interval)) AND (raw_trades_closed_old.std_symbol IS NOT NULL))
  GROUP BY raw_trades_closed_old.std_symbol
 HAVING (count(*) > 100);
DROP EXTENSION IF EXISTS prop_trading_model.pg_stat_statements CASCADE;
DROP EXTENSION IF EXISTS prop_trading_model.btree_gist CASCADE;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_account_trading_patterns CASCADE;
DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_market_regime_performance CASCADE;
DROP FUNCTION IF EXISTS prop_trading_model.drop_old_partitions CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_ingestion CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_alltime_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_account_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_login CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_daily_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_metrics_hourly_account_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_account_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_symbol CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_closed_trade_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_trade_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_symbol CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_trades_open_ingestion CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_plans_plan_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_plans_name CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_regimes_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_raw_regimes_summary CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_stg_accounts_daily_status CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_feature_store_profit_target CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_model_predictions_account CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_pipeline_execution_stage_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_pipeline_execution_status CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_phase CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_account_performance_recent_profit CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_daily_stats_year_month CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_daily_stats_dow CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_trades CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_symbol_performance_win_rate CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_trading_patterns_account_id CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_trading_patterns_login CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_regime_performance_date CASCADE;
DROP INDEX IF EXISTS prop_trading_model.idx_mv_regime_performance_sentiment CASCADE;

COMMIT;