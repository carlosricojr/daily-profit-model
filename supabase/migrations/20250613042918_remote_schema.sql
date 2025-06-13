

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "prop_trading_model";


ALTER SCHEMA "prop_trading_model" OWNER TO "postgres";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "btree_gist" WITH SCHEMA "prop_trading_model";






CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "prop_trading_model"."create_monthly_partitions"("table_name" "text", "start_date" "date", "end_date" "date") RETURNS "void"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
    partition_date date;
    partition_name text;
    date_column text;
BEGIN
    -- Determine date column based on table
    IF table_name = 'raw_metrics_daily' THEN
        date_column := 'date';
    ELSIF table_name = 'raw_metrics_hourly' THEN
        date_column := 'date';
    ELSIF table_name = 'raw_trades_closed' THEN
        date_column := 'trade_date';
    ELSIF table_name = 'raw_trades_open' THEN
        date_column := 'trade_date';
    ELSE
        RAISE EXCEPTION 'Unknown table for partitioning: %', table_name;
    END IF;
    
    -- Create partitions for each month
    FOR partition_date IN 
        SELECT generate_series(
            start_date,
            end_date,
            interval '1 month'
        )::date
    LOOP
        partition_name := table_name || '_' || to_char(partition_date, 'YYYY_MM');
        
        -- Check if partition exists
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
$$;


ALTER FUNCTION "prop_trading_model"."create_monthly_partitions"("table_name" "text", "start_date" "date", "end_date" "date") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "prop_trading_model"."drop_old_partitions"("table_name" "text", "retention_months" integer DEFAULT 36) RETURNS "void"
    LANGUAGE "plpgsql"
    AS $_$
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
        -- Extract date from partition name
        IF to_date(right(partition_record.tablename, 7), 'YYYY_MM') < cutoff_date THEN
            EXECUTE format('DROP TABLE IF EXISTS %I.%I', 'prop_trading_model', partition_record.tablename);
            RAISE NOTICE 'Dropped old partition: %', partition_record.tablename;
        END IF;
    END LOOP;
END;
$_$;


ALTER FUNCTION "prop_trading_model"."drop_old_partitions"("table_name" "text", "retention_months" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "prop_trading_model"."refresh_materialized_views"() RETURNS "void"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    -- Refresh views in dependency order
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_trading_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_symbol_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_performance_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_trading_patterns;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_market_regime_performance;
    
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
$$;


ALTER FUNCTION "prop_trading_model"."refresh_materialized_views"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."analyze_account_evolution"("target_account_id" character varying, "days_back" integer DEFAULT 7) RETURNS "jsonb"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  result jsonb;
  daily_vector_length int;
  hourly_vector_length int;
BEGIN
  SELECT 
    array_length(vector_daily, 1),
    array_length(vector_hourly, 1)
  INTO daily_vector_length, hourly_vector_length
  FROM accounts
  WHERE account_id = target_account_id;

  SELECT jsonb_build_object(
    'account_id', account_id,
    'daily_evolution', CASE 
      WHEN daily_vector_length >= 2 THEN
        jsonb_build_object(
          'total_days', daily_vector_length,
          'recent_days_analyzed', LEAST(daily_vector_length, days_back),
          'similarity_trend', 
            (SELECT jsonb_agg(
              jsonb_build_object(
                'day_index', idx,
                'similarity_to_latest', 1 - (vector_daily[idx] operator(extensions.<#>) vector_daily[daily_vector_length])
              ) ORDER BY idx DESC
            )
            FROM generate_series(
              GREATEST(1, daily_vector_length - days_back + 1), 
              daily_vector_length - 1
            ) AS idx)
        )
      ELSE NULL
    END,
    'hourly_evolution', CASE
      WHEN hourly_vector_length >= 24 THEN
        jsonb_build_object(
          'total_hours', hourly_vector_length,
          'last_24h_pattern', 
            (SELECT jsonb_agg(
              jsonb_build_object(
                'hour_index', idx,
                'hour_ago', hourly_vector_length - idx,
                'similarity_to_latest', 1 - (vector_hourly[idx] operator(extensions.<#>) vector_hourly[hourly_vector_length])
              ) ORDER BY idx DESC
            )
            FROM generate_series(
              GREATEST(1, hourly_vector_length - 23), 
              hourly_vector_length - 1
            ) AS idx)
        )
      ELSE NULL
    END
  ) INTO result
  FROM accounts
  WHERE account_id = target_account_id;

  RETURN result;
END;
$$;


ALTER FUNCTION "public"."analyze_account_evolution"("target_account_id" character varying, "days_back" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_accounts_adaptive"("query_embedding" "extensions"."vector", "match_count" integer DEFAULT 10, "filter" "jsonb" DEFAULT '{}'::"jsonb") RETURNS TABLE("id" bigint, "content" "text", "metadata" "jsonb", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $_$
DECLARE
  vector_type text;
  match_threshold float;
  lookback_days int;
  lookback_hours int;
  shortlist_multiplier int := 8;
BEGIN
  -- Extract parameters from filter
  vector_type := COALESCE(filter->>'vector_type', 'alltime');
  match_threshold := COALESCE((filter->>'match_threshold')::float, 0.0);
  lookback_days := COALESCE((filter->>'lookback_days')::int, 7);
  lookback_hours := COALESCE((filter->>'lookback_hours')::int, 24);
  
  -- Validate vector_type parameter
  IF vector_type NOT IN ('alltime', 'daily', 'hourly', 'daily_evolution', 'hourly_evolution') THEN
    RAISE EXCEPTION 'Invalid vector_type. Must be alltime, daily, hourly, daily_evolution, or hourly_evolution';
  END IF;

  -- Handle alltime vector with adaptive retrieval
  IF vector_type = 'alltime' THEN
    RETURN QUERY
    WITH shortlist AS (
      SELECT *
      FROM accounts a
      WHERE 
        -- Apply filters in first pass
        (filter->>'status' IS NULL OR a.status = (filter->>'status')::varchar) AND
        (filter->>'phase' IS NULL OR a.phase = (filter->>'phase')::integer) AND
        (filter->>'type' IS NULL OR a.type = (filter->>'type')::varchar) AND
        (filter->>'country' IS NULL OR a.country = (filter->>'country')::varchar) AND
        (filter->>'min_approved_payouts' IS NULL OR a.approved_payouts >= (filter->>'min_approved_payouts')::numeric) AND
        (filter->>'max_approved_payouts' IS NULL OR a.approved_payouts <= (filter->>'max_approved_payouts')::numeric) AND
        a.vector_alltime IS NOT NULL
      ORDER BY
        public.sub_vector(a.vector_alltime, 512)::extensions.vector(512) operator(extensions.<#>) (
          SELECT public.sub_vector(query_embedding, 512)::extensions.vector(512)
        ) ASC
      LIMIT match_count * shortlist_multiplier
    )
    SELECT 
      s.account_id::bigint AS id,
      format(
        'Account %s | Trader: %s | Status: %s | Phase: %s | Type: %s | Country: %s | Approved: $%s | Pending: $%s | Score: %s',
        s.account_id,
        COALESCE(s.trader, 'N/A'),
        CASE s.status 
          WHEN '1' THEN 'Active'
          WHEN '2' THEN 'Breached'
          WHEN '3' THEN 'Passed'
          ELSE s.status
        END,
        CASE s.phase
          WHEN 1 THEN 'Challenge 1'
          WHEN 2 THEN 'Challenge 2'
          WHEN 3 THEN 'Challenge 3'
          WHEN 4 THEN 'Funded'
          ELSE 'Phase ' || s.phase::text
        END,
        CASE s.type
          WHEN '1' THEN 'Standard'
          WHEN '2' THEN 'Rapid'
          WHEN '3' THEN 'Royal'
          WHEN '4' THEN 'Knight'
          WHEN '5' THEN 'Dragon'
          WHEN '6' THEN 'Knight Pro'
          WHEN '7' THEN 'Royal Pro'
          WHEN '8' THEN 'Relaunch'
          ELSE COALESCE(s.type, 'N/A')
        END,
        COALESCE(s.country, 'N/A'),
        COALESCE(s.approved_payouts::text, '0'),
        COALESCE(s.pending_payouts::text, '0'),
        COALESCE(s.score::text, 'N/A')
      ) AS content,
      jsonb_build_object(
        'account_id', s.account_id,
        'trader', s.trader,
        'status', s.status,
        'status_label', CASE s.status 
          WHEN '1' THEN 'Active'
          WHEN '2' THEN 'Breached'
          WHEN '3' THEN 'Passed'
        END,
        'type', s.type,
        'type_label', CASE s.type
          WHEN '1' THEN 'Standard'
          WHEN '2' THEN 'Rapid'
          WHEN '3' THEN 'Royal'
          WHEN '4' THEN 'Knight'
          WHEN '5' THEN 'Dragon'
          WHEN '6' THEN 'Knight Pro'
          WHEN '7' THEN 'Royal Pro'
          WHEN '8' THEN 'Relaunch'
        END,
        'phase', s.phase,
        'phase_label', CASE s.phase
          WHEN 1 THEN 'Challenge 1'
          WHEN 2 THEN 'Challenge 2'
          WHEN 3 THEN 'Challenge 3'
          WHEN 4 THEN 'Funded'
        END,
        'country', s.country,
        'approved_payouts', s.approved_payouts,
        'pending_payouts', s.pending_payouts,
        'score', s.score,
        'created_at', s.created_at,
        'updated_at', s.updated_at,
        'status_changed_at', s.status_changed_at
      ) AS metadata,
      1 - (s.vector_alltime operator(extensions.<#>) query_embedding) AS similarity
    FROM shortlist s
    WHERE 1 - (s.vector_alltime operator(extensions.<#>) query_embedding) > match_threshold
    ORDER BY s.vector_alltime operator(extensions.<#>) query_embedding ASC
    LIMIT least(match_count, 200);

  ELSIF vector_type = 'daily' THEN
    -- For daily vectors, use alltime for first pass, then search within daily arrays
    RETURN QUERY
    WITH shortlist AS (
      SELECT *
      FROM accounts a
      WHERE 
        (filter->>'status' IS NULL OR a.status = (filter->>'status')::varchar) AND
        (filter->>'phase' IS NULL OR a.phase = (filter->>'phase')::integer) AND
        array_length(a.vector_daily, 1) > 0 AND
        a.vector_alltime IS NOT NULL
      ORDER BY
        public.sub_vector(a.vector_alltime, 512)::extensions.vector(512) operator(extensions.<#>) (
          SELECT public.sub_vector(query_embedding, 512)::extensions.vector(512)
        ) ASC
      LIMIT match_count * shortlist_multiplier
    ),
    daily_matches AS (
      SELECT 
        s.*,
        MIN(elem operator(extensions.<#>) query_embedding) AS min_distance,
        array_position(s.vector_daily, 
          (SELECT elem FROM unnest(s.vector_daily) elem 
           ORDER BY elem operator(extensions.<#>) query_embedding LIMIT 1)
        ) as best_day_index
      FROM shortlist s,
      LATERAL unnest(s.vector_daily) AS elem
      GROUP BY s.account_id, s.trader, s.status, s.type, s.phase, s.country, 
               s.approved_payouts, s.pending_payouts, s.score, s.vector_daily,
               s.login, s.created_at, s.updated_at, s.status_changed_at, s.vector_alltime, s.vector_hourly
    )
    SELECT 
      dm.account_id::bigint AS id,
      format(
        'Account %s | Best Day: %s | Status: %s | Phase: %s | Approved: $%s',
        dm.account_id,
        dm.best_day_index::text,
        CASE dm.status WHEN '1' THEN 'Active' WHEN '2' THEN 'Breached' WHEN '3' THEN 'Passed' END,
        'Phase ' || dm.phase::text,
        COALESCE(dm.approved_payouts::text, '0')
      ) AS content,
      jsonb_build_object(
        'account_id', dm.account_id,
        'trader', dm.trader,
        'status', dm.status,
        'type', dm.type,
        'phase', dm.phase,
        'country', dm.country,
        'approved_payouts', dm.approved_payouts,
        'pending_payouts', dm.pending_payouts,
        'score', dm.score,
        'trend_info', jsonb_build_object('best_matching_day_index', dm.best_day_index)
      ) AS metadata,
      1 - dm.min_distance AS similarity
    FROM daily_matches dm
    WHERE 1 - dm.min_distance > match_threshold
    ORDER BY dm.min_distance ASC
    LIMIT least(match_count, 200);

  ELSIF vector_type = 'daily_evolution' THEN
    -- Use adaptive approach with evolution analysis
    RETURN QUERY
    WITH shortlist AS (
      SELECT *
      FROM accounts a
      WHERE 
        (filter->>'status' IS NULL OR a.status = (filter->>'status')::varchar) AND
        (filter->>'phase' IS NULL OR a.phase = (filter->>'phase')::integer) AND
        array_length(a.vector_daily, 1) > 0 AND
        a.vector_alltime IS NOT NULL
      ORDER BY
        public.sub_vector(a.vector_alltime, 512)::extensions.vector(512) operator(extensions.<#>) (
          SELECT public.sub_vector(query_embedding, 512)::extensions.vector(512)
        ) ASC
      LIMIT match_count * shortlist_multiplier
    ),
    daily_evolution AS (
      SELECT 
        s.*,
        -- Calculate similarity for recent days using inner product
        CASE 
          WHEN array_length(s.vector_daily, 1) >= lookback_days THEN
            (SELECT AVG(1 - (elem operator(extensions.<#>) query_embedding))
             FROM unnest(s.vector_daily[array_length(s.vector_daily, 1) - lookback_days + 1:array_length(s.vector_daily, 1)]) AS elem)
          ELSE
            (SELECT AVG(1 - (elem operator(extensions.<#>) query_embedding))
             FROM unnest(s.vector_daily) AS elem)
        END AS avg_similarity,
        -- Calculate trend info
        CASE 
          WHEN array_length(s.vector_daily, 1) >= 2 THEN
            jsonb_build_object(
              'days_analyzed', LEAST(array_length(s.vector_daily, 1), lookback_days),
              'latest_similarity', 1 - (s.vector_daily[array_length(s.vector_daily, 1)] operator(extensions.<#>) query_embedding),
              'oldest_similarity', 1 - (s.vector_daily[GREATEST(1, array_length(s.vector_daily, 1) - lookback_days + 1)] operator(extensions.<#>) query_embedding),
              'trend_direction', 
                CASE 
                  WHEN (1 - (s.vector_daily[array_length(s.vector_daily, 1)] operator(extensions.<#>) query_embedding)) > 
                       (1 - (s.vector_daily[GREATEST(1, array_length(s.vector_daily, 1) - lookback_days + 1)] operator(extensions.<#>) query_embedding))
                  THEN 'improving'
                  ELSE 'deteriorating'
                END
            )
          ELSE NULL
        END AS trend_data
      FROM shortlist s
    )
    SELECT 
      de.account_id::bigint AS id,
      format(
        'Account %s | Evolution: %s | Avg Similarity: %.3f | Status: %s | Phase: %s | Approved: $%s',
        de.account_id,
        COALESCE(de.trend_data->>'trend_direction', 'N/A'),
        de.avg_similarity,
        CASE de.status WHEN '1' THEN 'Active' WHEN '2' THEN 'Breached' WHEN '3' THEN 'Passed' END,
        'Phase ' || de.phase::text,
        COALESCE(de.approved_payouts::text, '0')
      ) AS content,
      jsonb_build_object(
        'account_id', de.account_id,
        'trader', de.trader,
        'status', de.status,
        'type', de.type,
        'phase', de.phase,
        'country', de.country,
        'approved_payouts', de.approved_payouts,
        'pending_payouts', de.pending_payouts,
        'score', de.score,
        'trend_info', de.trend_data
      ) AS metadata,
      de.avg_similarity AS similarity
    FROM daily_evolution de
    WHERE de.avg_similarity > match_threshold
    ORDER BY de.avg_similarity DESC
    LIMIT least(match_count, 200);

  ELSE -- hourly or hourly_evolution
    -- For now, return simplified hourly results
    RETURN QUERY
    WITH shortlist AS (
      SELECT *
      FROM accounts a
      WHERE 
        (filter->>'status' IS NULL OR a.status = (filter->>'status')::varchar) AND
        (filter->>'phase' IS NULL OR a.phase = (filter->>'phase')::integer) AND
        a.vector_alltime IS NOT NULL
      ORDER BY
        public.sub_vector(a.vector_alltime, 512)::extensions.vector(512) operator(extensions.<#>) (
          SELECT public.sub_vector(query_embedding, 512)::extensions.vector(512)
        ) ASC
      LIMIT match_count
    )
    SELECT 
      s.account_id::bigint AS id,
      format('Account %s | Hourly Analysis', s.account_id) AS content,
      jsonb_build_object(
        'account_id', s.account_id,
        'message', 'Hourly analysis types not fully implemented'
      ) AS metadata,
      0.5::float AS similarity
    FROM shortlist s
    LIMIT match_count;
  END IF;
END;
$_$;


ALTER FUNCTION "public"."match_accounts_adaptive"("query_embedding" "extensions"."vector", "match_count" integer, "filter" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_regimes_adaptive"("query_embedding" "extensions"."vector", "match_count" integer DEFAULT 10, "filter" "jsonb" DEFAULT '{}'::"jsonb") RETURNS TABLE("id" bigint, "content" "text", "metadata" "jsonb", "similarity" double precision)
    LANGUAGE "plpgsql"
    AS $$DECLARE
  match_threshold float;
  lookback_days int;
  shortlist_multiplier int := 8;
  start_date date;
  end_date date;
BEGIN
  match_threshold := COALESCE((filter->>'match_threshold')::float, 0.0);
  lookback_days := COALESCE((filter->>'lookback_days')::int, 7);
  start_date := (filter->>'start_date')::date;
  end_date := (filter->>'end_date')::date;
  
  RETURN QUERY
  WITH shortlist AS (
    SELECT *
    FROM regimes_daily r
    WHERE 
      -- date range filters
      (start_date IS NULL OR r.date >= start_date) AND 
      (end_date IS NULL OR r.date <= end_date) and
      -- specific date filter
      (filter->>'date' IS NULL OR r.date = (filter->>'date')::date) AND 
      -- ensure vector exists
      r.vector_daily_regime IS NOT NULL
    ORDER BY
      public.sub_vector(r.vector_daily_regime, 512)::extensions.vector(512) operator(extensions.<#>) (
        SELECT public.sub_vector(query_embedding, 512)::extensions.vector(512)
      ) ASC
    LIMIT match_count * shortlist_multiplier
  ),
  processed AS (
    SELECT 
      s.*,
      -- Extract key regime metrics from summary (without 'g' flag)
      (regexp_match(s.summary::text, 'SENTIMENT_LEVEL=(-?\d+\.?\d*)'))[1] AS sentiment_level,
      (regexp_match(s.summary::text, 'VOL_MEAN=(\d+\.?\d*)'))[1] AS vol_mean,
      (regexp_match(s.summary::text, 'P_RISK_ON=(\d+\.?\d*)'))[1] AS risk_on_prob,
      (regexp_match(s.summary::text, 'ANOMALY_COUNT=(\d+)'))[1] AS anomaly_count,
      -- Extract regime narrative
      (regexp_match(s.summary::text, '§REGIME_NARRATIVE§\s*([^§]+)'))[1] AS regime_narrative
    FROM shortlist s
  )
  SELECT 
    -- Use date as id (converted to bigint format YYYYMMDD)
    to_char(p.date, 'YYYYMMDD')::bigint AS id,
    -- Create concise descriptive content
    CASE 
      WHEN p.regime_narrative IS NOT NULL THEN
        format('Date: %s | %s',
          to_char(p.date, 'YYYY-MM-DD'),
          -- Extract just the first sentence of regime narrative
          split_part(p.regime_narrative, '.', 1) || '.'
        )
      ELSE
        format('Date: %s | %s | Vol: %s | Sentiment: %s',
          to_char(p.date, 'YYYY-MM-DD'),
          -- Regime type
          CASE 
            WHEN p.risk_on_prob IS NOT NULL AND p.risk_on_prob::float > 0.6 THEN 'Risk-On'
            WHEN p.risk_on_prob IS NOT NULL AND p.risk_on_prob::float < 0.4 THEN 'Risk-Off'
            ELSE 'Neutral'
          END,
          -- Volatility level
          CASE 
            WHEN p.vol_mean IS NOT NULL AND p.vol_mean::float > 2.0 THEN 'High'
            WHEN p.vol_mean IS NOT NULL AND p.vol_mean::float < 1.0 THEN 'Low'
            ELSE 'Normal'
          END,
          -- Sentiment
          CASE 
            WHEN p.sentiment_level IS NOT NULL AND p.sentiment_level::float > 0.2 THEN 'Bullish'
            WHEN p.sentiment_level IS NOT NULL AND p.sentiment_level::float < -0.2 THEN 'Bearish'
            ELSE 'Neutral'
          END
        )
    END AS content,
    -- Build streamlined metadata
    jsonb_build_object(
      'date', p.date,
      'day_of_week', trim(to_char(p.date, 'Day')),
      -- Instead of full news content, provide counts and snippets
      'market_news_summary', jsonb_build_object(
        'article_count', 
          CASE 
            WHEN p.market_news IS NOT NULL AND length(p.market_news::text) > 0 THEN 
              array_length(string_to_array(p.market_news::text, E'\n'), 1)
            ELSE 0
          END,
        'first_headline', 
          CASE 
            WHEN p.market_news IS NOT NULL AND length(p.market_news::text) > 0 THEN 
              left(split_part(p.market_news::text, E'\n', 1), 100)
            ELSE NULL
          END
      ),
      -- Instrument list without full details
      'instruments_mentioned', 
        CASE 
          WHEN p.instruments IS NOT NULL AND length(p.instruments::text) > 0 THEN
            array_to_json(regexp_split_to_array(left(p.instruments::text, 200), E'[,\\s]+'))::jsonb
          ELSE NULL
        END,
      -- Economic indicators summary (safer handling)
      'economic_indicators_count',
        CASE 
          WHEN p.country_economic_indicators IS NOT NULL THEN
            CASE 
              WHEN jsonb_typeof(p.country_economic_indicators::jsonb) = 'array' THEN
                jsonb_array_length(p.country_economic_indicators::jsonb)
              WHEN jsonb_typeof(p.country_economic_indicators::jsonb) = 'object' THEN
                1
              ELSE 
                0
            END
          ELSE 0
        END,
      -- Key regime metrics extracted from summary
      'regime_metrics', jsonb_build_object(
        'sentiment_level', 
          CASE WHEN p.sentiment_level IS NOT NULL THEN p.sentiment_level::float ELSE NULL END,
        'volatility_mean', 
          CASE WHEN p.vol_mean IS NOT NULL THEN p.vol_mean::float ELSE NULL END,
        'risk_on_probability', 
          CASE WHEN p.risk_on_prob IS NOT NULL THEN p.risk_on_prob::float ELSE NULL END,
        'anomaly_count', 
          CASE WHEN p.anomaly_count IS NOT NULL THEN p.anomaly_count::int ELSE NULL END
      ),
      -- Regime classification
      'regime_type', 
        CASE 
          WHEN p.summary::text ILIKE '%risk_on%' THEN 'risk_on'
          WHEN p.summary::text ILIKE '%risk_off%' THEN 'risk_off'
          WHEN p.summary::text ILIKE '%vol_spike%' THEN 'volatility_spike'
          WHEN p.summary::text ILIKE '%stable%' THEN 'stable'
          ELSE 'mixed'
        END,
      -- Opportunities if mentioned (using simpler extraction)
      'opportunities',
        CASE 
          WHEN p.summary::text LIKE '%OPPORTUNITY_SCAN%' THEN
            substring(p.summary::text from '\[([^\]]+)\]')
          ELSE NULL
        END,
      -- Compact regime narrative
      'regime_summary',
        CASE 
          WHEN p.regime_narrative IS NOT NULL THEN 
            left(p.regime_narrative, 500)
          ELSE 
            'No regime narrative available'
        END
    ) AS metadata,
    1 - (p.vector_daily_regime operator(extensions.<#>) query_embedding) AS similarity
  FROM processed p
  WHERE 1 - (p.vector_daily_regime operator(extensions.<#>) query_embedding) > match_threshold
  ORDER BY p.vector_daily_regime operator(extensions.<#>) query_embedding ASC
  LIMIT least(match_count, 200);
END;$$;


ALTER FUNCTION "public"."match_regimes_adaptive"("query_embedding" "extensions"."vector", "match_count" integer, "filter" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."sub_vector"("v" "extensions"."vector", "dimensions" integer) RETURNS "extensions"."vector"
    LANGUAGE "plpgsql" IMMUTABLE
    SET "search_path" TO ''
    AS $$
begin
  if dimensions > extensions.vector_dims(v) then
    raise exception 'dimensions must be less than or equal to the vector size';
  end if;

  return (
    with unnormed(elem) as (
      select x from unnest(v::float4[]) with ordinality v(x, ix)
      where ix <= dimensions
    ),
    norm(factor) as (
      select
        sqrt(sum(pow(elem, 2)))
      from
        unnormed
    )
    select
      array_agg(u.elem / r.factor)::extensions.vector
    from
      norm r, unnormed u
  );
end;
$$;


ALTER FUNCTION "public"."sub_vector"("v" "extensions"."vector", "dimensions" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_status_changed_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    SET "search_path" TO ''
    AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.status_changed_at := NOW();
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_status_changed_at"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."feature_store_account_daily" (
    "id" integer NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "feature_date" "date" NOT NULL,
    "days_active" integer,
    "current_phase" character varying(50),
    "account_age_days" integer,
    "trades_today" integer DEFAULT 0,
    "trades_last_7d" integer DEFAULT 0,
    "trades_last_30d" integer DEFAULT 0,
    "trading_days_last_7d" integer DEFAULT 0,
    "trading_days_last_30d" integer DEFAULT 0,
    "avg_trades_per_day_7d" numeric(10,4),
    "avg_trades_per_day_30d" numeric(10,4),
    "profit_today" numeric(18,2),
    "profit_last_7d" numeric(18,2),
    "profit_last_30d" numeric(18,2),
    "roi_today" numeric(10,4),
    "roi_last_7d" numeric(10,4),
    "roi_last_30d" numeric(10,4),
    "win_rate_today" numeric(5,2),
    "win_rate_7d" numeric(5,2),
    "win_rate_30d" numeric(5,2),
    "profit_factor_7d" numeric(10,2),
    "profit_factor_30d" numeric(10,2),
    "max_drawdown_7d" numeric(18,2),
    "max_drawdown_30d" numeric(18,2),
    "current_drawdown" numeric(18,2),
    "current_drawdown_pct" numeric(5,2),
    "avg_trade_size_7d" numeric(18,4),
    "avg_trade_size_30d" numeric(18,4),
    "avg_holding_time_hours_7d" numeric(10,2),
    "avg_holding_time_hours_30d" numeric(10,2),
    "unique_symbols_7d" integer,
    "unique_symbols_30d" integer,
    "symbol_concentration_7d" numeric(5,2),
    "symbol_concentration_30d" numeric(5,2),
    "pct_trades_market_hours_7d" numeric(5,2),
    "pct_trades_market_hours_30d" numeric(5,2),
    "favorite_trading_hour_7d" integer,
    "favorite_trading_hour_30d" integer,
    "daily_profit_volatility_7d" numeric(18,2),
    "daily_profit_volatility_30d" numeric(18,2),
    "profitable_days_pct_7d" numeric(5,2),
    "profitable_days_pct_30d" numeric(5,2),
    "distance_to_profit_target" numeric(18,2),
    "distance_to_profit_target_pct" numeric(5,2),
    "distance_to_drawdown_limit" numeric(18,2),
    "distance_to_drawdown_limit_pct" numeric(5,2),
    "days_until_deadline" integer,
    "market_volatility_regime" character varying(50),
    "market_trend_regime" character varying(50),
    "next_day_profit" numeric(18,2),
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."feature_store_account_daily" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."feature_store_account_daily_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."feature_store_account_daily_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."feature_store_account_daily_id_seq" OWNED BY "prop_trading_model"."feature_store_account_daily"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."model_predictions" (
    "id" integer NOT NULL,
    "model_version" character varying(100) NOT NULL,
    "prediction_date" "date" NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "predicted_profit_probability" numeric(5,4),
    "predicted_profit_amount" numeric(18,2),
    "feature_importance" "jsonb",
    "prediction_confidence" numeric(5,4),
    "actual_profit" numeric(18,2),
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."model_predictions" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."model_predictions_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."model_predictions_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."model_predictions_id_seq" OWNED BY "prop_trading_model"."model_predictions"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."model_registry" (
    "id" integer NOT NULL,
    "model_version" character varying(100) NOT NULL,
    "model_type" character varying(50) NOT NULL,
    "training_completed_at" timestamp without time zone NOT NULL,
    "model_path" character varying(500),
    "git_commit_hash" character varying(100),
    "performance_metrics" "jsonb",
    "feature_importance" "jsonb",
    "is_active" boolean DEFAULT false,
    "deployed_at" timestamp without time zone,
    "deprecated_at" timestamp without time zone,
    "notes" "text",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."model_registry" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."model_registry_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."model_registry_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."model_registry_id_seq" OWNED BY "prop_trading_model"."model_registry"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."model_training_input" (
    "id" integer NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "prediction_date" "date" NOT NULL,
    "feature_date" "date" NOT NULL,
    "starting_balance" numeric(18,2),
    "max_daily_drawdown_pct" numeric(5,2),
    "max_drawdown_pct" numeric(5,2),
    "profit_target_pct" numeric(5,2),
    "max_leverage" numeric(10,2),
    "is_drawdown_relative" boolean,
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "days_since_first_trade" integer,
    "active_trading_days_count" integer,
    "distance_to_profit_target" numeric(18,2),
    "distance_to_max_drawdown" numeric(18,2),
    "open_pnl" numeric(18,2),
    "open_positions_volume" numeric(18,2),
    "rolling_pnl_sum_1d" numeric(18,2),
    "rolling_pnl_avg_1d" numeric(18,2),
    "rolling_pnl_std_1d" numeric(18,2),
    "rolling_pnl_sum_3d" numeric(18,2),
    "rolling_pnl_avg_3d" numeric(18,2),
    "rolling_pnl_std_3d" numeric(18,2),
    "rolling_pnl_min_3d" numeric(18,2),
    "rolling_pnl_max_3d" numeric(18,2),
    "win_rate_3d" numeric(5,2),
    "rolling_pnl_sum_5d" numeric(18,2),
    "rolling_pnl_avg_5d" numeric(18,2),
    "rolling_pnl_std_5d" numeric(18,2),
    "rolling_pnl_min_5d" numeric(18,2),
    "rolling_pnl_max_5d" numeric(18,2),
    "win_rate_5d" numeric(5,2),
    "profit_factor_5d" numeric(10,4),
    "sharpe_ratio_5d" numeric(10,4),
    "rolling_pnl_sum_10d" numeric(18,2),
    "rolling_pnl_avg_10d" numeric(18,2),
    "rolling_pnl_std_10d" numeric(18,2),
    "rolling_pnl_min_10d" numeric(18,2),
    "rolling_pnl_max_10d" numeric(18,2),
    "win_rate_10d" numeric(5,2),
    "profit_factor_10d" numeric(10,4),
    "sharpe_ratio_10d" numeric(10,4),
    "rolling_pnl_sum_20d" numeric(18,2),
    "rolling_pnl_avg_20d" numeric(18,2),
    "rolling_pnl_std_20d" numeric(18,2),
    "win_rate_20d" numeric(5,2),
    "profit_factor_20d" numeric(10,4),
    "sharpe_ratio_20d" numeric(10,4),
    "trades_count_5d" integer,
    "avg_trade_duration_5d" numeric(10,2),
    "avg_lots_per_trade_5d" numeric(10,4),
    "avg_volume_per_trade_5d" numeric(18,2),
    "stop_loss_usage_rate_5d" numeric(5,2),
    "take_profit_usage_rate_5d" numeric(5,2),
    "buy_sell_ratio_5d" numeric(10,4),
    "top_symbol_concentration_5d" numeric(5,2),
    "market_sentiment_score" numeric(10,4),
    "market_volatility_regime" character varying(50),
    "market_liquidity_state" character varying(50),
    "vix_level" numeric(10,2),
    "dxy_level" numeric(10,2),
    "sp500_daily_return" numeric(10,4),
    "btc_volatility_90d" numeric(10,4),
    "fed_funds_rate" numeric(5,2),
    "day_of_week" integer,
    "week_of_month" integer,
    "month" integer,
    "quarter" integer,
    "day_of_year" integer,
    "is_month_start" boolean,
    "is_month_end" boolean,
    "is_quarter_start" boolean,
    "is_quarter_end" boolean,
    "target_net_profit" numeric(18,2),
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."model_training_input" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."model_training_input_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."model_training_input_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."model_training_input_id_seq" OWNED BY "prop_trading_model"."model_training_input"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_alltime" (
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "first_trade_open" timestamp without time zone,
    "last_trade_open" timestamp without time zone,
    "last_trade_close" timestamp without time zone,
    "lifetime_in_days" numeric(10,6),
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "mean_trades_per_day" numeric(10,2),
    "median_trades_per_day" integer,
    "min_trades_per_day" integer,
    "max_trades_per_day" integer,
    "cv_trades_per_day" numeric(10,6),
    "mean_idle_days" numeric(10,2),
    "median_idle_days" integer,
    "max_idle_days" integer,
    "min_idle_days" integer,
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "updated_date" timestamp without time zone,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_alltime_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_alltime_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_alltime_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_alltime_phase_check" CHECK (("phase" = ANY (ARRAY[1, 2, 3, 4]))),
    CONSTRAINT "raw_metrics_alltime_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_alltime_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_alltime_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_alltime" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
)
PARTITION BY RANGE ("date");


ALTER TABLE "prop_trading_model"."raw_metrics_daily" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_plans_data" (
    "plan_id" character varying(255) NOT NULL,
    "plan_name" character varying(255) NOT NULL,
    "plan_type" character varying(100),
    "starting_balance" numeric(18,2),
    "profit_target" numeric(18,2),
    "profit_target_pct" numeric(5,2),
    "max_drawdown" numeric(18,2),
    "max_drawdown_pct" numeric(5,2),
    "max_daily_drawdown" numeric(18,2),
    "max_daily_drawdown_pct" numeric(5,2),
    "profit_share_pct" numeric(5,2),
    "max_leverage" numeric(10,2),
    "min_trading_days" integer,
    "max_trading_days" integer,
    "is_drawdown_relative" boolean DEFAULT false,
    "liquidate_friday" boolean DEFAULT false,
    "inactivity_period" integer,
    "daily_drawdown_by_balance_equity" boolean DEFAULT false,
    "enable_consistency" boolean DEFAULT false,
    "created_at" timestamp without time zone,
    "updated_at" timestamp without time zone,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_plans_data_inactivity_period_check" CHECK (("inactivity_period" >= 0)),
    CONSTRAINT "raw_plans_data_max_daily_drawdown_pct_check" CHECK ((("max_daily_drawdown_pct" >= (0)::numeric) AND ("max_daily_drawdown_pct" <= (100)::numeric))),
    CONSTRAINT "raw_plans_data_max_drawdown_pct_check" CHECK ((("max_drawdown_pct" >= (0)::numeric) AND ("max_drawdown_pct" <= (100)::numeric))),
    CONSTRAINT "raw_plans_data_max_leverage_check" CHECK (("max_leverage" > (0)::numeric)),
    CONSTRAINT "raw_plans_data_max_trading_days_check" CHECK (("max_trading_days" >= 0)),
    CONSTRAINT "raw_plans_data_min_trading_days_check" CHECK (("min_trading_days" >= 0)),
    CONSTRAINT "raw_plans_data_profit_share_pct_check" CHECK ((("profit_share_pct" >= (0)::numeric) AND ("profit_share_pct" <= (100)::numeric))),
    CONSTRAINT "raw_plans_data_profit_target_pct_check" CHECK ((("profit_target_pct" >= (0)::numeric) AND ("profit_target_pct" <= (100)::numeric))),
    CONSTRAINT "raw_plans_data_starting_balance_check" CHECK (("starting_balance" > (0)::numeric))
);


ALTER TABLE "prop_trading_model"."raw_plans_data" OWNER TO "postgres";


COMMENT ON COLUMN "prop_trading_model"."raw_plans_data"."liquidate_friday" IS 'Whether account can hold positions over the weekend (TRUE = must liquidate, FALSE = can hold)';



COMMENT ON COLUMN "prop_trading_model"."raw_plans_data"."inactivity_period" IS 'Number of days an account can go without placing a trade before breach';



COMMENT ON COLUMN "prop_trading_model"."raw_plans_data"."daily_drawdown_by_balance_equity" IS 'How daily drawdown is calculated (TRUE = from previous day balance or equity whichever is higher, FALSE = from previous day balance only)';



COMMENT ON COLUMN "prop_trading_model"."raw_plans_data"."enable_consistency" IS 'Whether consistency rules are applied to the account';



CREATE MATERIALIZED VIEW "prop_trading_model"."mv_account_performance_summary" AS
 SELECT "a"."account_id",
    "a"."login",
    "a"."trader_id",
    "a"."plan_id",
    "a"."phase",
    "a"."status",
    "a"."starting_balance",
    "a"."current_balance",
    "a"."current_equity",
    "p"."plan_name",
    "p"."profit_target_pct",
    "p"."max_drawdown_pct",
    "p"."max_daily_drawdown_pct",
    "p"."max_leverage",
    "p"."min_trading_days",
    "p"."max_trading_days",
    COALESCE("m"."num_trades", 0) AS "lifetime_trades",
    COALESCE("m"."net_profit", (0)::numeric) AS "lifetime_profit",
    COALESCE("m"."gross_profit", (0)::numeric) AS "lifetime_gross_profit",
    COALESCE("m"."gross_loss", (0)::numeric) AS "lifetime_gross_loss",
    COALESCE("m"."success_rate", (0)::numeric) AS "lifetime_win_rate",
    COALESCE("m"."profit_factor", (0)::numeric) AS "lifetime_profit_factor",
    COALESCE("m"."daily_sharpe", (0)::double precision) AS "lifetime_sharpe_ratio",
    COALESCE("m"."daily_sortino", (0)::double precision) AS "lifetime_sortino_ratio",
    COALESCE("m"."rel_max_drawdown", (0)::numeric) AS "lifetime_max_drawdown_pct",
    COALESCE("daily"."trades_last_30d", (0)::bigint) AS "trades_last_30d",
    COALESCE("daily"."profit_last_30d", (0)::numeric) AS "profit_last_30d",
    COALESCE("daily"."win_rate_last_30d", (0)::numeric) AS "win_rate_last_30d",
    COALESCE("daily"."trading_days_last_30d", (0)::bigint) AS "trading_days_last_30d",
    COALESCE("weekly"."trades_last_7d", (0)::bigint) AS "trades_last_7d",
    COALESCE("weekly"."profit_last_7d", (0)::numeric) AS "profit_last_7d",
    COALESCE("weekly"."win_rate_last_7d", (0)::numeric) AS "win_rate_last_7d",
        CASE
            WHEN ("a"."starting_balance" > (0)::numeric) THEN ((("a"."current_balance" - "a"."starting_balance") / "a"."starting_balance") * (100)::numeric)
            ELSE (0)::numeric
        END AS "total_return_pct",
        CASE
            WHEN ("p"."profit_target" > (0)::numeric) THEN ((("p"."profit_target" - ("a"."current_balance" - "a"."starting_balance")) / "p"."profit_target") * (100)::numeric)
            ELSE (0)::numeric
        END AS "distance_to_target_pct",
    "a"."updated_date" AS "last_updated",
    CURRENT_TIMESTAMP AS "mv_refreshed_at"
   FROM ((((( SELECT DISTINCT ON ("raw_metrics_alltime"."account_id") "raw_metrics_alltime"."login",
            "raw_metrics_alltime"."account_id",
            "raw_metrics_alltime"."plan_id",
            "raw_metrics_alltime"."trader_id",
            "raw_metrics_alltime"."status",
            "raw_metrics_alltime"."type",
            "raw_metrics_alltime"."phase",
            "raw_metrics_alltime"."broker",
            "raw_metrics_alltime"."platform",
            "raw_metrics_alltime"."price_stream",
            "raw_metrics_alltime"."country",
            "raw_metrics_alltime"."approved_payouts",
            "raw_metrics_alltime"."pending_payouts",
            "raw_metrics_alltime"."starting_balance",
            "raw_metrics_alltime"."prior_days_balance",
            "raw_metrics_alltime"."prior_days_equity",
            "raw_metrics_alltime"."current_balance",
            "raw_metrics_alltime"."current_equity",
            "raw_metrics_alltime"."first_trade_date",
            "raw_metrics_alltime"."days_since_initial_deposit",
            "raw_metrics_alltime"."days_since_first_trade",
            "raw_metrics_alltime"."num_trades",
            "raw_metrics_alltime"."first_trade_open",
            "raw_metrics_alltime"."last_trade_open",
            "raw_metrics_alltime"."last_trade_close",
            "raw_metrics_alltime"."lifetime_in_days",
            "raw_metrics_alltime"."net_profit",
            "raw_metrics_alltime"."gross_profit",
            "raw_metrics_alltime"."gross_loss",
            "raw_metrics_alltime"."gain_to_pain",
            "raw_metrics_alltime"."profit_factor",
            "raw_metrics_alltime"."success_rate",
            "raw_metrics_alltime"."expectancy",
            "raw_metrics_alltime"."mean_profit",
            "raw_metrics_alltime"."median_profit",
            "raw_metrics_alltime"."std_profits",
            "raw_metrics_alltime"."risk_adj_profit",
            "raw_metrics_alltime"."min_profit",
            "raw_metrics_alltime"."max_profit",
            "raw_metrics_alltime"."profit_perc_10",
            "raw_metrics_alltime"."profit_perc_25",
            "raw_metrics_alltime"."profit_perc_75",
            "raw_metrics_alltime"."profit_perc_90",
            "raw_metrics_alltime"."profit_top_10_prcnt_trades",
            "raw_metrics_alltime"."profit_bottom_10_prcnt_trades",
            "raw_metrics_alltime"."top_10_prcnt_profit_contrib",
            "raw_metrics_alltime"."bottom_10_prcnt_loss_contrib",
            "raw_metrics_alltime"."one_std_outlier_profit",
            "raw_metrics_alltime"."one_std_outlier_profit_contrib",
            "raw_metrics_alltime"."two_std_outlier_profit",
            "raw_metrics_alltime"."two_std_outlier_profit_contrib",
            "raw_metrics_alltime"."net_profit_per_usd_volume",
            "raw_metrics_alltime"."gross_profit_per_usd_volume",
            "raw_metrics_alltime"."gross_loss_per_usd_volume",
            "raw_metrics_alltime"."distance_gross_profit_loss_per_usd_volume",
            "raw_metrics_alltime"."multiple_gross_profit_loss_per_usd_volume",
            "raw_metrics_alltime"."gross_profit_per_lot",
            "raw_metrics_alltime"."gross_loss_per_lot",
            "raw_metrics_alltime"."distance_gross_profit_loss_per_lot",
            "raw_metrics_alltime"."multiple_gross_profit_loss_per_lot",
            "raw_metrics_alltime"."net_profit_per_duration",
            "raw_metrics_alltime"."gross_profit_per_duration",
            "raw_metrics_alltime"."gross_loss_per_duration",
            "raw_metrics_alltime"."mean_ret",
            "raw_metrics_alltime"."std_rets",
            "raw_metrics_alltime"."risk_adj_ret",
            "raw_metrics_alltime"."downside_std_rets",
            "raw_metrics_alltime"."downside_risk_adj_ret",
            "raw_metrics_alltime"."total_ret",
            "raw_metrics_alltime"."daily_mean_ret",
            "raw_metrics_alltime"."daily_std_ret",
            "raw_metrics_alltime"."daily_sharpe",
            "raw_metrics_alltime"."daily_downside_std_ret",
            "raw_metrics_alltime"."daily_sortino",
            "raw_metrics_alltime"."rel_net_profit",
            "raw_metrics_alltime"."rel_gross_profit",
            "raw_metrics_alltime"."rel_gross_loss",
            "raw_metrics_alltime"."rel_mean_profit",
            "raw_metrics_alltime"."rel_median_profit",
            "raw_metrics_alltime"."rel_std_profits",
            "raw_metrics_alltime"."rel_risk_adj_profit",
            "raw_metrics_alltime"."rel_min_profit",
            "raw_metrics_alltime"."rel_max_profit",
            "raw_metrics_alltime"."rel_profit_perc_10",
            "raw_metrics_alltime"."rel_profit_perc_25",
            "raw_metrics_alltime"."rel_profit_perc_75",
            "raw_metrics_alltime"."rel_profit_perc_90",
            "raw_metrics_alltime"."rel_profit_top_10_prcnt_trades",
            "raw_metrics_alltime"."rel_profit_bottom_10_prcnt_trades",
            "raw_metrics_alltime"."rel_one_std_outlier_profit",
            "raw_metrics_alltime"."rel_two_std_outlier_profit",
            "raw_metrics_alltime"."mean_drawdown",
            "raw_metrics_alltime"."median_drawdown",
            "raw_metrics_alltime"."max_drawdown",
            "raw_metrics_alltime"."mean_num_trades_in_dd",
            "raw_metrics_alltime"."median_num_trades_in_dd",
            "raw_metrics_alltime"."max_num_trades_in_dd",
            "raw_metrics_alltime"."rel_mean_drawdown",
            "raw_metrics_alltime"."rel_median_drawdown",
            "raw_metrics_alltime"."rel_max_drawdown",
            "raw_metrics_alltime"."total_lots",
            "raw_metrics_alltime"."total_volume",
            "raw_metrics_alltime"."std_volumes",
            "raw_metrics_alltime"."mean_winning_lot",
            "raw_metrics_alltime"."mean_losing_lot",
            "raw_metrics_alltime"."distance_win_loss_lots",
            "raw_metrics_alltime"."multiple_win_loss_lots",
            "raw_metrics_alltime"."mean_winning_volume",
            "raw_metrics_alltime"."mean_losing_volume",
            "raw_metrics_alltime"."distance_win_loss_volume",
            "raw_metrics_alltime"."multiple_win_loss_volume",
            "raw_metrics_alltime"."mean_duration",
            "raw_metrics_alltime"."median_duration",
            "raw_metrics_alltime"."std_durations",
            "raw_metrics_alltime"."min_duration",
            "raw_metrics_alltime"."max_duration",
            "raw_metrics_alltime"."cv_durations",
            "raw_metrics_alltime"."mean_tp",
            "raw_metrics_alltime"."median_tp",
            "raw_metrics_alltime"."std_tp",
            "raw_metrics_alltime"."min_tp",
            "raw_metrics_alltime"."max_tp",
            "raw_metrics_alltime"."cv_tp",
            "raw_metrics_alltime"."mean_sl",
            "raw_metrics_alltime"."median_sl",
            "raw_metrics_alltime"."std_sl",
            "raw_metrics_alltime"."min_sl",
            "raw_metrics_alltime"."max_sl",
            "raw_metrics_alltime"."cv_sl",
            "raw_metrics_alltime"."mean_tp_vs_sl",
            "raw_metrics_alltime"."median_tp_vs_sl",
            "raw_metrics_alltime"."min_tp_vs_sl",
            "raw_metrics_alltime"."max_tp_vs_sl",
            "raw_metrics_alltime"."cv_tp_vs_sl",
            "raw_metrics_alltime"."mean_num_consec_wins",
            "raw_metrics_alltime"."median_num_consec_wins",
            "raw_metrics_alltime"."max_num_consec_wins",
            "raw_metrics_alltime"."mean_num_consec_losses",
            "raw_metrics_alltime"."median_num_consec_losses",
            "raw_metrics_alltime"."max_num_consec_losses",
            "raw_metrics_alltime"."mean_val_consec_wins",
            "raw_metrics_alltime"."median_val_consec_wins",
            "raw_metrics_alltime"."max_val_consec_wins",
            "raw_metrics_alltime"."mean_val_consec_losses",
            "raw_metrics_alltime"."median_val_consec_losses",
            "raw_metrics_alltime"."max_val_consec_losses",
            "raw_metrics_alltime"."mean_num_open_pos",
            "raw_metrics_alltime"."median_num_open_pos",
            "raw_metrics_alltime"."max_num_open_pos",
            "raw_metrics_alltime"."mean_val_open_pos",
            "raw_metrics_alltime"."median_val_open_pos",
            "raw_metrics_alltime"."max_val_open_pos",
            "raw_metrics_alltime"."mean_val_to_eqty_open_pos",
            "raw_metrics_alltime"."median_val_to_eqty_open_pos",
            "raw_metrics_alltime"."max_val_to_eqty_open_pos",
            "raw_metrics_alltime"."mean_account_margin",
            "raw_metrics_alltime"."mean_firm_margin",
            "raw_metrics_alltime"."mean_trades_per_day",
            "raw_metrics_alltime"."median_trades_per_day",
            "raw_metrics_alltime"."min_trades_per_day",
            "raw_metrics_alltime"."max_trades_per_day",
            "raw_metrics_alltime"."cv_trades_per_day",
            "raw_metrics_alltime"."mean_idle_days",
            "raw_metrics_alltime"."median_idle_days",
            "raw_metrics_alltime"."max_idle_days",
            "raw_metrics_alltime"."min_idle_days",
            "raw_metrics_alltime"."num_traded_symbols",
            "raw_metrics_alltime"."most_traded_symbol",
            "raw_metrics_alltime"."most_traded_smb_trades",
            "raw_metrics_alltime"."updated_date",
            "raw_metrics_alltime"."ingestion_timestamp",
            "raw_metrics_alltime"."source_api_endpoint"
           FROM "prop_trading_model"."raw_metrics_alltime"
          ORDER BY "raw_metrics_alltime"."account_id", "raw_metrics_alltime"."ingestion_timestamp" DESC) "a"
     LEFT JOIN "prop_trading_model"."raw_plans_data" "p" ON ((("a"."plan_id")::"text" = ("p"."plan_id")::"text")))
     LEFT JOIN ( SELECT DISTINCT ON ("raw_metrics_alltime"."account_id") "raw_metrics_alltime"."login",
            "raw_metrics_alltime"."account_id",
            "raw_metrics_alltime"."plan_id",
            "raw_metrics_alltime"."trader_id",
            "raw_metrics_alltime"."status",
            "raw_metrics_alltime"."type",
            "raw_metrics_alltime"."phase",
            "raw_metrics_alltime"."broker",
            "raw_metrics_alltime"."platform",
            "raw_metrics_alltime"."price_stream",
            "raw_metrics_alltime"."country",
            "raw_metrics_alltime"."approved_payouts",
            "raw_metrics_alltime"."pending_payouts",
            "raw_metrics_alltime"."starting_balance",
            "raw_metrics_alltime"."prior_days_balance",
            "raw_metrics_alltime"."prior_days_equity",
            "raw_metrics_alltime"."current_balance",
            "raw_metrics_alltime"."current_equity",
            "raw_metrics_alltime"."first_trade_date",
            "raw_metrics_alltime"."days_since_initial_deposit",
            "raw_metrics_alltime"."days_since_first_trade",
            "raw_metrics_alltime"."num_trades",
            "raw_metrics_alltime"."first_trade_open",
            "raw_metrics_alltime"."last_trade_open",
            "raw_metrics_alltime"."last_trade_close",
            "raw_metrics_alltime"."lifetime_in_days",
            "raw_metrics_alltime"."net_profit",
            "raw_metrics_alltime"."gross_profit",
            "raw_metrics_alltime"."gross_loss",
            "raw_metrics_alltime"."gain_to_pain",
            "raw_metrics_alltime"."profit_factor",
            "raw_metrics_alltime"."success_rate",
            "raw_metrics_alltime"."expectancy",
            "raw_metrics_alltime"."mean_profit",
            "raw_metrics_alltime"."median_profit",
            "raw_metrics_alltime"."std_profits",
            "raw_metrics_alltime"."risk_adj_profit",
            "raw_metrics_alltime"."min_profit",
            "raw_metrics_alltime"."max_profit",
            "raw_metrics_alltime"."profit_perc_10",
            "raw_metrics_alltime"."profit_perc_25",
            "raw_metrics_alltime"."profit_perc_75",
            "raw_metrics_alltime"."profit_perc_90",
            "raw_metrics_alltime"."profit_top_10_prcnt_trades",
            "raw_metrics_alltime"."profit_bottom_10_prcnt_trades",
            "raw_metrics_alltime"."top_10_prcnt_profit_contrib",
            "raw_metrics_alltime"."bottom_10_prcnt_loss_contrib",
            "raw_metrics_alltime"."one_std_outlier_profit",
            "raw_metrics_alltime"."one_std_outlier_profit_contrib",
            "raw_metrics_alltime"."two_std_outlier_profit",
            "raw_metrics_alltime"."two_std_outlier_profit_contrib",
            "raw_metrics_alltime"."net_profit_per_usd_volume",
            "raw_metrics_alltime"."gross_profit_per_usd_volume",
            "raw_metrics_alltime"."gross_loss_per_usd_volume",
            "raw_metrics_alltime"."distance_gross_profit_loss_per_usd_volume",
            "raw_metrics_alltime"."multiple_gross_profit_loss_per_usd_volume",
            "raw_metrics_alltime"."gross_profit_per_lot",
            "raw_metrics_alltime"."gross_loss_per_lot",
            "raw_metrics_alltime"."distance_gross_profit_loss_per_lot",
            "raw_metrics_alltime"."multiple_gross_profit_loss_per_lot",
            "raw_metrics_alltime"."net_profit_per_duration",
            "raw_metrics_alltime"."gross_profit_per_duration",
            "raw_metrics_alltime"."gross_loss_per_duration",
            "raw_metrics_alltime"."mean_ret",
            "raw_metrics_alltime"."std_rets",
            "raw_metrics_alltime"."risk_adj_ret",
            "raw_metrics_alltime"."downside_std_rets",
            "raw_metrics_alltime"."downside_risk_adj_ret",
            "raw_metrics_alltime"."total_ret",
            "raw_metrics_alltime"."daily_mean_ret",
            "raw_metrics_alltime"."daily_std_ret",
            "raw_metrics_alltime"."daily_sharpe",
            "raw_metrics_alltime"."daily_downside_std_ret",
            "raw_metrics_alltime"."daily_sortino",
            "raw_metrics_alltime"."rel_net_profit",
            "raw_metrics_alltime"."rel_gross_profit",
            "raw_metrics_alltime"."rel_gross_loss",
            "raw_metrics_alltime"."rel_mean_profit",
            "raw_metrics_alltime"."rel_median_profit",
            "raw_metrics_alltime"."rel_std_profits",
            "raw_metrics_alltime"."rel_risk_adj_profit",
            "raw_metrics_alltime"."rel_min_profit",
            "raw_metrics_alltime"."rel_max_profit",
            "raw_metrics_alltime"."rel_profit_perc_10",
            "raw_metrics_alltime"."rel_profit_perc_25",
            "raw_metrics_alltime"."rel_profit_perc_75",
            "raw_metrics_alltime"."rel_profit_perc_90",
            "raw_metrics_alltime"."rel_profit_top_10_prcnt_trades",
            "raw_metrics_alltime"."rel_profit_bottom_10_prcnt_trades",
            "raw_metrics_alltime"."rel_one_std_outlier_profit",
            "raw_metrics_alltime"."rel_two_std_outlier_profit",
            "raw_metrics_alltime"."mean_drawdown",
            "raw_metrics_alltime"."median_drawdown",
            "raw_metrics_alltime"."max_drawdown",
            "raw_metrics_alltime"."mean_num_trades_in_dd",
            "raw_metrics_alltime"."median_num_trades_in_dd",
            "raw_metrics_alltime"."max_num_trades_in_dd",
            "raw_metrics_alltime"."rel_mean_drawdown",
            "raw_metrics_alltime"."rel_median_drawdown",
            "raw_metrics_alltime"."rel_max_drawdown",
            "raw_metrics_alltime"."total_lots",
            "raw_metrics_alltime"."total_volume",
            "raw_metrics_alltime"."std_volumes",
            "raw_metrics_alltime"."mean_winning_lot",
            "raw_metrics_alltime"."mean_losing_lot",
            "raw_metrics_alltime"."distance_win_loss_lots",
            "raw_metrics_alltime"."multiple_win_loss_lots",
            "raw_metrics_alltime"."mean_winning_volume",
            "raw_metrics_alltime"."mean_losing_volume",
            "raw_metrics_alltime"."distance_win_loss_volume",
            "raw_metrics_alltime"."multiple_win_loss_volume",
            "raw_metrics_alltime"."mean_duration",
            "raw_metrics_alltime"."median_duration",
            "raw_metrics_alltime"."std_durations",
            "raw_metrics_alltime"."min_duration",
            "raw_metrics_alltime"."max_duration",
            "raw_metrics_alltime"."cv_durations",
            "raw_metrics_alltime"."mean_tp",
            "raw_metrics_alltime"."median_tp",
            "raw_metrics_alltime"."std_tp",
            "raw_metrics_alltime"."min_tp",
            "raw_metrics_alltime"."max_tp",
            "raw_metrics_alltime"."cv_tp",
            "raw_metrics_alltime"."mean_sl",
            "raw_metrics_alltime"."median_sl",
            "raw_metrics_alltime"."std_sl",
            "raw_metrics_alltime"."min_sl",
            "raw_metrics_alltime"."max_sl",
            "raw_metrics_alltime"."cv_sl",
            "raw_metrics_alltime"."mean_tp_vs_sl",
            "raw_metrics_alltime"."median_tp_vs_sl",
            "raw_metrics_alltime"."min_tp_vs_sl",
            "raw_metrics_alltime"."max_tp_vs_sl",
            "raw_metrics_alltime"."cv_tp_vs_sl",
            "raw_metrics_alltime"."mean_num_consec_wins",
            "raw_metrics_alltime"."median_num_consec_wins",
            "raw_metrics_alltime"."max_num_consec_wins",
            "raw_metrics_alltime"."mean_num_consec_losses",
            "raw_metrics_alltime"."median_num_consec_losses",
            "raw_metrics_alltime"."max_num_consec_losses",
            "raw_metrics_alltime"."mean_val_consec_wins",
            "raw_metrics_alltime"."median_val_consec_wins",
            "raw_metrics_alltime"."max_val_consec_wins",
            "raw_metrics_alltime"."mean_val_consec_losses",
            "raw_metrics_alltime"."median_val_consec_losses",
            "raw_metrics_alltime"."max_val_consec_losses",
            "raw_metrics_alltime"."mean_num_open_pos",
            "raw_metrics_alltime"."median_num_open_pos",
            "raw_metrics_alltime"."max_num_open_pos",
            "raw_metrics_alltime"."mean_val_open_pos",
            "raw_metrics_alltime"."median_val_open_pos",
            "raw_metrics_alltime"."max_val_open_pos",
            "raw_metrics_alltime"."mean_val_to_eqty_open_pos",
            "raw_metrics_alltime"."median_val_to_eqty_open_pos",
            "raw_metrics_alltime"."max_val_to_eqty_open_pos",
            "raw_metrics_alltime"."mean_account_margin",
            "raw_metrics_alltime"."mean_firm_margin",
            "raw_metrics_alltime"."mean_trades_per_day",
            "raw_metrics_alltime"."median_trades_per_day",
            "raw_metrics_alltime"."min_trades_per_day",
            "raw_metrics_alltime"."max_trades_per_day",
            "raw_metrics_alltime"."cv_trades_per_day",
            "raw_metrics_alltime"."mean_idle_days",
            "raw_metrics_alltime"."median_idle_days",
            "raw_metrics_alltime"."max_idle_days",
            "raw_metrics_alltime"."min_idle_days",
            "raw_metrics_alltime"."num_traded_symbols",
            "raw_metrics_alltime"."most_traded_symbol",
            "raw_metrics_alltime"."most_traded_smb_trades",
            "raw_metrics_alltime"."updated_date",
            "raw_metrics_alltime"."ingestion_timestamp",
            "raw_metrics_alltime"."source_api_endpoint"
           FROM "prop_trading_model"."raw_metrics_alltime"
          ORDER BY "raw_metrics_alltime"."account_id", "raw_metrics_alltime"."ingestion_timestamp" DESC) "m" ON ((("a"."account_id")::"text" = ("m"."account_id")::"text")))
     LEFT JOIN LATERAL ( SELECT "raw_metrics_daily"."account_id",
            "sum"("raw_metrics_daily"."num_trades") AS "trades_last_30d",
            "sum"("raw_metrics_daily"."net_profit") AS "profit_last_30d",
            "count"(DISTINCT "raw_metrics_daily"."date") AS "trading_days_last_30d",
                CASE
                    WHEN ("sum"("raw_metrics_daily"."num_trades") > 0) THEN (("sum"(((("raw_metrics_daily"."num_trades")::numeric * "raw_metrics_daily"."success_rate") / (100)::numeric)) / ("sum"("raw_metrics_daily"."num_trades"))::numeric) * (100)::numeric)
                    ELSE (0)::numeric
                END AS "win_rate_last_30d"
           FROM "prop_trading_model"."raw_metrics_daily"
          WHERE ((("raw_metrics_daily"."account_id")::"text" = ("a"."account_id")::"text") AND ("raw_metrics_daily"."date" >= (CURRENT_DATE - '30 days'::interval)))
          GROUP BY "raw_metrics_daily"."account_id") "daily" ON (true))
     LEFT JOIN LATERAL ( SELECT "raw_metrics_daily"."account_id",
            "sum"("raw_metrics_daily"."num_trades") AS "trades_last_7d",
            "sum"("raw_metrics_daily"."net_profit") AS "profit_last_7d",
                CASE
                    WHEN ("sum"("raw_metrics_daily"."num_trades") > 0) THEN (("sum"(((("raw_metrics_daily"."num_trades")::numeric * "raw_metrics_daily"."success_rate") / (100)::numeric)) / ("sum"("raw_metrics_daily"."num_trades"))::numeric) * (100)::numeric)
                    ELSE (0)::numeric
                END AS "win_rate_last_7d"
           FROM "prop_trading_model"."raw_metrics_daily"
          WHERE ((("raw_metrics_daily"."account_id")::"text" = ("a"."account_id")::"text") AND ("raw_metrics_daily"."date" >= (CURRENT_DATE - '7 days'::interval)))
          GROUP BY "raw_metrics_daily"."account_id") "weekly" ON (true))
  WITH NO DATA;


ALTER TABLE "prop_trading_model"."mv_account_performance_summary" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
)
PARTITION BY RANGE ("trade_date");


ALTER TABLE "prop_trading_model"."raw_trades_closed" OWNER TO "postgres";


COMMENT ON COLUMN "prop_trading_model"."raw_trades_closed"."account_id" IS 'Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented';



CREATE MATERIALIZED VIEW "prop_trading_model"."mv_account_trading_patterns" AS
 WITH "recent_trades" AS (
         SELECT "raw_trades_closed"."account_id",
            "raw_trades_closed"."login",
            "raw_trades_closed"."std_symbol",
            "raw_trades_closed"."side",
            EXTRACT(hour FROM "raw_trades_closed"."open_time") AS "trade_hour",
            EXTRACT(dow FROM "raw_trades_closed"."trade_date") AS "trade_dow",
            "raw_trades_closed"."profit",
            "raw_trades_closed"."lots",
            "raw_trades_closed"."volume_usd",
                CASE
                    WHEN ("raw_trades_closed"."stop_loss" IS NOT NULL) THEN 1
                    ELSE 0
                END AS "has_sl",
                CASE
                    WHEN ("raw_trades_closed"."take_profit" IS NOT NULL) THEN 1
                    ELSE 0
                END AS "has_tp"
           FROM "prop_trading_model"."raw_trades_closed"
          WHERE ("raw_trades_closed"."trade_date" >= (CURRENT_DATE - '30 days'::interval))
        )
 SELECT "recent_trades"."account_id",
    "recent_trades"."login",
    "count"(*) AS "num_trades_30d",
    "count"(DISTINCT "recent_trades"."std_symbol") AS "unique_symbols",
    "mode"() WITHIN GROUP (ORDER BY "recent_trades"."std_symbol") AS "favorite_symbol",
    ((("max"("symbol_trades"."symbol_count"))::numeric / ("count"(*))::numeric) * (100)::numeric) AS "top_symbol_concentration_pct",
    "mode"() WITHIN GROUP (ORDER BY "recent_trades"."trade_hour") AS "favorite_hour",
    "mode"() WITHIN GROUP (ORDER BY "recent_trades"."trade_dow") AS "favorite_day_of_week",
    "avg"("recent_trades"."lots") AS "avg_lot_size",
    "stddev"("recent_trades"."lots") AS "lot_size_stddev",
    "avg"("recent_trades"."volume_usd") AS "avg_trade_volume",
    ((("sum"(
        CASE
            WHEN (("recent_trades"."side")::"text" = ANY ((ARRAY['buy'::character varying, 'BUY'::character varying])::"text"[])) THEN 1
            ELSE 0
        END))::numeric / ("count"(*))::numeric) * (100)::numeric) AS "buy_ratio",
    ("avg"("recent_trades"."has_sl") * (100)::numeric) AS "sl_usage_rate",
    ("avg"("recent_trades"."has_tp") * (100)::numeric) AS "tp_usage_rate",
    "avg"(
        CASE
            WHEN (("recent_trades"."trade_hour" >= (8)::numeric) AND ("recent_trades"."trade_hour" <= (16)::numeric)) THEN "recent_trades"."profit"
            ELSE NULL::numeric
        END) AS "avg_profit_market_hours",
    "avg"(
        CASE
            WHEN (("recent_trades"."trade_hour" < (8)::numeric) OR ("recent_trades"."trade_hour" > (16)::numeric)) THEN "recent_trades"."profit"
            ELSE NULL::numeric
        END) AS "avg_profit_off_hours",
    CURRENT_TIMESTAMP AS "mv_refreshed_at"
   FROM ("recent_trades"
     LEFT JOIN LATERAL ( SELECT "rt2"."std_symbol",
            "count"(*) AS "symbol_count"
           FROM "recent_trades" "rt2"
          WHERE (("rt2"."account_id")::"text" = ("recent_trades"."account_id")::"text")
          GROUP BY "rt2"."std_symbol"
          ORDER BY ("count"(*)) DESC
         LIMIT 1) "symbol_trades" ON (true))
  GROUP BY "recent_trades"."account_id", "recent_trades"."login"
  WITH NO DATA;


ALTER TABLE "prop_trading_model"."mv_account_trading_patterns" OWNER TO "postgres";


CREATE MATERIALIZED VIEW "prop_trading_model"."mv_daily_trading_stats" AS
 SELECT "raw_metrics_daily"."date",
    "count"(DISTINCT "raw_metrics_daily"."account_id") AS "active_accounts",
    "count"(DISTINCT
        CASE
            WHEN ("raw_metrics_daily"."net_profit" > (0)::numeric) THEN "raw_metrics_daily"."account_id"
            ELSE NULL::character varying
        END) AS "profitable_accounts",
    "count"(DISTINCT
        CASE
            WHEN ("raw_metrics_daily"."net_profit" < (0)::numeric) THEN "raw_metrics_daily"."account_id"
            ELSE NULL::character varying
        END) AS "losing_accounts",
    "sum"("raw_metrics_daily"."num_trades") AS "num_trades",
    "sum"(((("raw_metrics_daily"."num_trades")::numeric * "raw_metrics_daily"."success_rate") / (100)::numeric)) AS "total_winning_trades",
    "sum"(((("raw_metrics_daily"."num_trades")::numeric * ((100)::numeric - "raw_metrics_daily"."success_rate")) / (100)::numeric)) AS "total_losing_trades",
    "sum"("raw_metrics_daily"."net_profit") AS "total_profit",
    "sum"("raw_metrics_daily"."gross_profit") AS "total_gross_profit",
    "sum"("raw_metrics_daily"."gross_loss") AS "total_gross_loss",
    "avg"("raw_metrics_daily"."net_profit") AS "avg_profit",
    "stddev"("raw_metrics_daily"."net_profit") AS "profit_stddev",
    "sum"("raw_metrics_daily"."total_volume") AS "total_volume",
    "sum"("raw_metrics_daily"."total_lots") AS "total_lots",
    "avg"("raw_metrics_daily"."success_rate") AS "avg_win_rate",
    "percentile_cont"((0.5)::double precision) WITHIN GROUP (ORDER BY (("raw_metrics_daily"."net_profit")::double precision)) AS "median_profit",
    "percentile_cont"((0.25)::double precision) WITHIN GROUP (ORDER BY (("raw_metrics_daily"."net_profit")::double precision)) AS "profit_q1",
    "percentile_cont"((0.75)::double precision) WITHIN GROUP (ORDER BY (("raw_metrics_daily"."net_profit")::double precision)) AS "profit_q3",
    "max"("raw_metrics_daily"."net_profit") AS "max_profit",
    "min"("raw_metrics_daily"."net_profit") AS "min_profit",
    (EXTRACT(dow FROM "raw_metrics_daily"."date"))::integer AS "day_of_week",
    (EXTRACT(week FROM "raw_metrics_daily"."date"))::integer AS "week_number",
    (EXTRACT(month FROM "raw_metrics_daily"."date"))::integer AS "month",
    (EXTRACT(year FROM "raw_metrics_daily"."date"))::integer AS "year",
    CURRENT_TIMESTAMP AS "mv_refreshed_at"
   FROM "prop_trading_model"."raw_metrics_daily"
  WHERE ("raw_metrics_daily"."date" >= (CURRENT_DATE - '365 days'::interval))
  GROUP BY "raw_metrics_daily"."date"
  WITH NO DATA;


ALTER TABLE "prop_trading_model"."mv_daily_trading_stats" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_regimes_daily" (
    "id" integer NOT NULL,
    "date" "date" NOT NULL,
    "regime_name" character varying(100),
    "summary" "jsonb",
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500)
);


ALTER TABLE "prop_trading_model"."raw_regimes_daily" OWNER TO "postgres";


CREATE MATERIALIZED VIEW "prop_trading_model"."mv_market_regime_performance" AS
 SELECT "r"."date",
    ("r"."summary" ->> 'market_sentiment'::"text") AS "market_sentiment",
    ("r"."summary" ->> 'volatility_regime'::"text") AS "volatility_regime",
    ("r"."summary" ->> 'liquidity_state'::"text") AS "liquidity_state",
    "count"(DISTINCT "m"."account_id") AS "active_accounts",
    "sum"("m"."num_trades") AS "num_trades",
    "sum"("m"."net_profit") AS "total_profit",
    "avg"("m"."net_profit") AS "avg_profit",
    "stddev"("m"."net_profit") AS "profit_stddev",
    "avg"("m"."success_rate") AS "avg_win_rate",
    "sum"("m"."total_volume") AS "total_volume",
    "percentile_cont"((0.5)::double precision) WITHIN GROUP (ORDER BY (("m"."net_profit")::double precision)) AS "median_profit",
    "count"(DISTINCT
        CASE
            WHEN ("m"."net_profit" > (0)::numeric) THEN "m"."account_id"
            ELSE NULL::character varying
        END) AS "profitable_accounts",
    CURRENT_TIMESTAMP AS "mv_refreshed_at"
   FROM ("prop_trading_model"."raw_regimes_daily" "r"
     JOIN "prop_trading_model"."raw_metrics_daily" "m" ON (("r"."date" = "m"."date")))
  WHERE (("r"."date" >= (CURRENT_DATE - '180 days'::interval)) AND ("r"."summary" IS NOT NULL))
  GROUP BY "r"."date", "r"."summary"
  WITH NO DATA;


ALTER TABLE "prop_trading_model"."mv_market_regime_performance" OWNER TO "postgres";


CREATE MATERIALIZED VIEW "prop_trading_model"."mv_symbol_performance" AS
 WITH "symbol_stats" AS (
         SELECT "raw_trades_closed"."std_symbol",
            "count"(DISTINCT "raw_trades_closed"."account_id") AS "traders_count",
            "count"(*) AS "num_trades",
            "sum"("raw_trades_closed"."profit") AS "total_profit",
            "avg"("raw_trades_closed"."profit") AS "avg_profit",
            "stddev"("raw_trades_closed"."profit") AS "profit_stddev",
            "sum"(
                CASE
                    WHEN ("raw_trades_closed"."profit" > (0)::numeric) THEN 1
                    ELSE 0
                END) AS "winning_trades",
            "sum"(
                CASE
                    WHEN ("raw_trades_closed"."profit" < (0)::numeric) THEN 1
                    ELSE 0
                END) AS "losing_trades",
            "sum"(
                CASE
                    WHEN ("raw_trades_closed"."profit" > (0)::numeric) THEN "raw_trades_closed"."profit"
                    ELSE (0)::numeric
                END) AS "gross_profit",
            "sum"(
                CASE
                    WHEN ("raw_trades_closed"."profit" < (0)::numeric) THEN "raw_trades_closed"."profit"
                    ELSE (0)::numeric
                END) AS "gross_loss",
            "sum"("raw_trades_closed"."volume_usd") AS "total_volume",
            "sum"("raw_trades_closed"."lots") AS "total_lots",
            "max"("raw_trades_closed"."profit") AS "max_profit",
            "min"("raw_trades_closed"."profit") AS "min_profit",
            "percentile_cont"((0.5)::double precision) WITHIN GROUP (ORDER BY (("raw_trades_closed"."profit")::double precision)) AS "median_profit",
            "avg"((EXTRACT(epoch FROM ("raw_trades_closed"."close_time" - "raw_trades_closed"."open_time")) / (3600)::numeric)) AS "avg_trade_duration_hours"
           FROM "prop_trading_model"."raw_trades_closed"
          WHERE (("raw_trades_closed"."trade_date" >= (CURRENT_DATE - '90 days'::interval)) AND ("raw_trades_closed"."std_symbol" IS NOT NULL))
          GROUP BY "raw_trades_closed"."std_symbol"
         HAVING ("count"(*) > 100)
        )
 SELECT "symbol_stats"."std_symbol",
    "symbol_stats"."traders_count",
    "symbol_stats"."num_trades",
    "symbol_stats"."total_profit",
    "symbol_stats"."avg_profit",
    "symbol_stats"."profit_stddev",
    "symbol_stats"."winning_trades",
    "symbol_stats"."losing_trades",
    "symbol_stats"."gross_profit",
    "symbol_stats"."gross_loss",
        CASE
            WHEN ("symbol_stats"."num_trades" > 0) THEN ((("symbol_stats"."winning_trades")::numeric / ("symbol_stats"."num_trades")::numeric) * (100)::numeric)
            ELSE (0)::numeric
        END AS "win_rate",
        CASE
            WHEN ("symbol_stats"."gross_loss" < (0)::numeric) THEN "abs"(("symbol_stats"."gross_profit" / "symbol_stats"."gross_loss"))
            ELSE (0)::numeric
        END AS "profit_factor",
    "symbol_stats"."total_volume",
    "symbol_stats"."total_lots",
    "symbol_stats"."max_profit",
    "symbol_stats"."min_profit",
    "symbol_stats"."median_profit",
    "symbol_stats"."avg_trade_duration_hours",
        CASE
            WHEN ("symbol_stats"."profit_stddev" > (0)::numeric) THEN ("symbol_stats"."avg_profit" / "symbol_stats"."profit_stddev")
            ELSE (0)::numeric
        END AS "sharpe_approximation",
    CURRENT_TIMESTAMP AS "mv_refreshed_at"
   FROM "symbol_stats"
  WITH NO DATA;


ALTER TABLE "prop_trading_model"."mv_symbol_performance" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."pipeline_execution_log" (
    "id" integer NOT NULL,
    "pipeline_stage" character varying(100) NOT NULL,
    "execution_date" "date" NOT NULL,
    "start_time" timestamp without time zone NOT NULL,
    "end_time" timestamp without time zone,
    "status" character varying(50),
    "records_processed" integer,
    "records_failed" integer,
    "error_message" "text",
    "execution_details" "jsonb",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "pipeline_execution_log_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['running'::character varying, 'success'::character varying, 'failed'::character varying, 'warning'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."pipeline_execution_log" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."pipeline_execution_log_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."pipeline_execution_log_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."pipeline_execution_log_id_seq" OWNED BY "prop_trading_model"."pipeline_execution_log"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."query_performance_log" (
    "id" integer NOT NULL,
    "query_hash" character varying(64),
    "query_template" "text",
    "execution_time_ms" numeric(10,2),
    "rows_returned" integer,
    "table_names" "text"[],
    "index_used" boolean,
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."query_performance_log" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."query_performance_log_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."query_performance_log_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."query_performance_log_id_seq" OWNED BY "prop_trading_model"."query_performance_log"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_01" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_02" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_03" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_04" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_05" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_06" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_07" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_08" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_09" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_10" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_11" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2022_12" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2022_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_01" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_02" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_03" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_04" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_05" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_06" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_07" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_08" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_09" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_10" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_11" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2023_12" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2023_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_01" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_02" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_03" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_04" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_05" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_06" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_07" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_08" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_09" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_10" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_11" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2024_12" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2024_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_01" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_02" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_03" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_04" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_05" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_06" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_07" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_08" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_daily_2025_09" (
    "date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "total_ret" double precision,
    "daily_mean_ret" double precision,
    "daily_std_ret" double precision,
    "daily_sharpe" double precision,
    "daily_downside_std_ret" double precision,
    "daily_sortino" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_daily_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_daily_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_daily_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_daily_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_daily_2025_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_metrics_hourly" (
    "date" "date" NOT NULL,
    "datetime" timestamp without time zone NOT NULL,
    "hour" integer NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "price_stream" integer,
    "country" character varying(2),
    "days_to_next_payout" integer,
    "todays_payouts" numeric(18,2),
    "approved_payouts" numeric(18,2),
    "pending_payouts" numeric(18,2),
    "starting_balance" numeric(18,2),
    "prior_days_balance" numeric(18,2),
    "prior_days_equity" numeric(18,2),
    "current_balance" numeric(18,2),
    "current_equity" numeric(18,2),
    "first_trade_date" "date",
    "days_since_initial_deposit" integer,
    "days_since_first_trade" integer,
    "num_trades" integer,
    "net_profit" numeric(18,2),
    "gross_profit" numeric(18,2),
    "gross_loss" numeric(18,2),
    "gain_to_pain" numeric(10,2),
    "profit_factor" numeric(10,2),
    "success_rate" numeric(5,2),
    "expectancy" numeric(18,2),
    "mean_profit" numeric(18,2),
    "median_profit" numeric(18,2),
    "std_profits" numeric(18,2),
    "risk_adj_profit" double precision,
    "min_profit" numeric(18,2),
    "max_profit" numeric(18,2),
    "profit_perc_10" numeric(18,2),
    "profit_perc_25" numeric(18,2),
    "profit_perc_75" numeric(18,2),
    "profit_perc_90" numeric(18,2),
    "profit_top_10_prcnt_trades" numeric(18,2),
    "profit_bottom_10_prcnt_trades" numeric(18,2),
    "top_10_prcnt_profit_contrib" numeric(5,2),
    "bottom_10_prcnt_loss_contrib" numeric(5,2),
    "one_std_outlier_profit" numeric(18,2),
    "one_std_outlier_profit_contrib" numeric(10,6),
    "two_std_outlier_profit" numeric(18,2),
    "two_std_outlier_profit_contrib" numeric(10,6),
    "net_profit_per_usd_volume" double precision,
    "gross_profit_per_usd_volume" double precision,
    "gross_loss_per_usd_volume" double precision,
    "distance_gross_profit_loss_per_usd_volume" double precision,
    "multiple_gross_profit_loss_per_usd_volume" double precision,
    "gross_profit_per_lot" numeric(18,6),
    "gross_loss_per_lot" numeric(18,6),
    "distance_gross_profit_loss_per_lot" numeric(18,6),
    "multiple_gross_profit_loss_per_lot" double precision,
    "net_profit_per_duration" numeric(18,6),
    "gross_profit_per_duration" numeric(18,6),
    "gross_loss_per_duration" numeric(18,6),
    "mean_ret" double precision,
    "std_rets" double precision,
    "risk_adj_ret" double precision,
    "downside_std_rets" double precision,
    "downside_risk_adj_ret" double precision,
    "rel_net_profit" numeric(18,6),
    "rel_gross_profit" numeric(18,6),
    "rel_gross_loss" numeric(18,6),
    "rel_mean_profit" numeric(18,6),
    "rel_median_profit" numeric(18,6),
    "rel_std_profits" numeric(18,6),
    "rel_risk_adj_profit" double precision,
    "rel_min_profit" numeric(18,6),
    "rel_max_profit" numeric(18,6),
    "rel_profit_perc_10" numeric(18,6),
    "rel_profit_perc_25" numeric(18,6),
    "rel_profit_perc_75" numeric(18,6),
    "rel_profit_perc_90" numeric(18,6),
    "rel_profit_top_10_prcnt_trades" numeric(18,6),
    "rel_profit_bottom_10_prcnt_trades" numeric(18,6),
    "rel_one_std_outlier_profit" numeric(18,6),
    "rel_two_std_outlier_profit" numeric(18,6),
    "mean_drawdown" numeric(18,2),
    "median_drawdown" numeric(18,2),
    "max_drawdown" numeric(18,2),
    "mean_num_trades_in_dd" numeric(18,2),
    "median_num_trades_in_dd" numeric(18,2),
    "max_num_trades_in_dd" integer,
    "rel_mean_drawdown" numeric(18,6),
    "rel_median_drawdown" numeric(18,6),
    "rel_max_drawdown" numeric(18,6),
    "total_lots" numeric(18,6),
    "total_volume" numeric(18,2),
    "std_volumes" numeric(18,2),
    "mean_winning_lot" numeric(18,6),
    "mean_losing_lot" numeric(18,6),
    "distance_win_loss_lots" numeric(18,6),
    "multiple_win_loss_lots" numeric(10,6),
    "mean_winning_volume" numeric(18,2),
    "mean_losing_volume" numeric(18,2),
    "distance_win_loss_volume" numeric(18,2),
    "multiple_win_loss_volume" numeric(10,6),
    "mean_duration" numeric(18,6),
    "median_duration" numeric(18,6),
    "std_durations" numeric(18,6),
    "min_duration" numeric(18,6),
    "max_duration" numeric(18,6),
    "cv_durations" numeric(10,6),
    "mean_tp" numeric(18,6),
    "median_tp" numeric(18,6),
    "std_tp" numeric(18,6),
    "min_tp" numeric(18,6),
    "max_tp" numeric(18,6),
    "cv_tp" numeric(10,6),
    "mean_sl" numeric(18,6),
    "median_sl" numeric(18,6),
    "std_sl" numeric(18,6),
    "min_sl" numeric(18,6),
    "max_sl" numeric(18,6),
    "cv_sl" numeric(10,6),
    "mean_tp_vs_sl" numeric(10,6),
    "median_tp_vs_sl" numeric(10,6),
    "min_tp_vs_sl" numeric(10,6),
    "max_tp_vs_sl" numeric(10,6),
    "cv_tp_vs_sl" numeric(10,6),
    "mean_num_consec_wins" numeric(10,2),
    "median_num_consec_wins" integer,
    "max_num_consec_wins" integer,
    "mean_num_consec_losses" numeric(10,2),
    "median_num_consec_losses" integer,
    "max_num_consec_losses" integer,
    "mean_val_consec_wins" numeric(18,2),
    "median_val_consec_wins" numeric(18,2),
    "max_val_consec_wins" numeric(18,2),
    "mean_val_consec_losses" numeric(18,2),
    "median_val_consec_losses" numeric(18,2),
    "max_val_consec_losses" numeric(18,2),
    "mean_num_open_pos" numeric(10,2),
    "median_num_open_pos" integer,
    "max_num_open_pos" integer,
    "mean_val_open_pos" numeric(18,2),
    "median_val_open_pos" numeric(18,2),
    "max_val_open_pos" numeric(18,2),
    "mean_val_to_eqty_open_pos" numeric(10,6),
    "median_val_to_eqty_open_pos" numeric(10,6),
    "max_val_to_eqty_open_pos" numeric(10,6),
    "mean_account_margin" numeric(18,2),
    "mean_firm_margin" numeric(18,2),
    "num_traded_symbols" integer,
    "most_traded_symbol" character varying(50),
    "most_traded_smb_trades" integer,
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_metrics_hourly_gross_loss_check" CHECK (("gross_loss" <= (0)::numeric)),
    CONSTRAINT "raw_metrics_hourly_gross_profit_check" CHECK (("gross_profit" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_hourly_num_trades_check" CHECK (("num_trades" >= 0)),
    CONSTRAINT "raw_metrics_hourly_profit_factor_check" CHECK (("profit_factor" >= (0)::numeric)),
    CONSTRAINT "raw_metrics_hourly_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT "raw_metrics_hourly_success_rate_check" CHECK ((("success_rate" >= (0)::numeric) AND ("success_rate" <= (100)::numeric)))
);


ALTER TABLE "prop_trading_model"."raw_metrics_hourly" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."raw_regimes_daily_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."raw_regimes_daily_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."raw_regimes_daily_id_seq" OWNED BY "prop_trading_model"."raw_regimes_daily"."id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_01" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_02" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_03" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_04" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_05" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_06" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_07" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_08" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_09" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_10" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_11" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2022_12" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2022_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_01" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_02" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_03" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_04" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_05" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_06" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_07" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_08" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_09" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_10" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_11" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2023_12" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2023_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_01" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_02" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_03" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_04" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_05" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_06" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_07" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_08" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_09" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_10" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_11" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2024_12" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2024_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_01" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_02" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_03" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_04" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_05" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_06" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_07" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_08" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_closed_2025_09" (
    "trade_date" "date" NOT NULL,
    "broker" integer,
    "manager" integer,
    "platform" integer NOT NULL,
    "ticket" integer,
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "close_time" timestamp without time zone,
    "close_price" numeric(18,6),
    "duration" numeric(18,2),
    "profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_closed_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_closed_2025_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
)
PARTITION BY RANGE ("trade_date");


ALTER TABLE "prop_trading_model"."raw_trades_open" OWNER TO "postgres";


COMMENT ON COLUMN "prop_trading_model"."raw_trades_open"."account_id" IS 'Account ID - may be temporarily set to login value until proper resolution with platform/mt_version is implemented';



CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_01" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_02" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_03" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_04" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_05" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_06" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_07" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_08" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_09" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_10" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_11" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2022_12" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2022_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_01" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_02" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_03" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_04" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_05" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_06" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_07" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_08" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_09" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_10" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_11" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2023_12" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2023_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_01" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_02" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_03" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_04" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_05" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_06" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_07" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_08" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_09" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_10" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_11" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2024_12" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2024_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_01" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_01" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_02" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_02" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_03" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_03" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_04" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_04" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_05" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_05" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_06" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_06" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_07" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_07" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_08" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_08" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_09" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_09" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_10" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_10" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_11" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_11" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."raw_trades_open_2025_12" (
    "trade_date" "date" NOT NULL,
    "broker" character varying(255),
    "manager" character varying(255),
    "platform" character varying(255) NOT NULL,
    "ticket" character varying(255),
    "position" character varying(255) NOT NULL,
    "login" character varying(255) NOT NULL,
    "account_id" character varying(255),
    "std_symbol" character varying(50) NOT NULL,
    "side" character varying(10),
    "lots" numeric(18,4),
    "contract_size" numeric(18,4),
    "qty_in_base_ccy" numeric(18,4),
    "volume_usd" numeric(18,4),
    "stop_loss" numeric(18,6),
    "take_profit" numeric(18,6),
    "open_time" timestamp without time zone,
    "open_price" numeric(18,6),
    "duration" numeric(18,2),
    "unrealized_profit" numeric(18,2),
    "commission" numeric(18,2),
    "fee" numeric(18,2),
    "swap" numeric(18,2),
    "comment" character varying(255),
    "ingestion_timestamp" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "source_api_endpoint" character varying(500),
    CONSTRAINT "raw_trades_open_side_check" CHECK ((("side")::"text" = ANY ((ARRAY['buy'::character varying, 'sell'::character varying, 'BUY'::character varying, 'SELL'::character varying, 'Buy'::character varying, 'Sell'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."raw_trades_open_2025_12" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."scheduled_jobs" (
    "job_name" character varying(100) NOT NULL,
    "schedule" character varying(100) NOT NULL,
    "last_run" timestamp without time zone,
    "next_run" timestamp without time zone,
    "status" character varying(50),
    "error_count" integer DEFAULT 0,
    "command" "text",
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "prop_trading_model"."scheduled_jobs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "prop_trading_model"."schema_migrations" (
    "migration_name" character varying(255) NOT NULL,
    "checksum" character varying(64) NOT NULL,
    "applied_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "applied_by" character varying(100) DEFAULT CURRENT_USER,
    "execution_time_ms" integer,
    "success" boolean DEFAULT true,
    "error_message" "text"
);


ALTER TABLE "prop_trading_model"."schema_migrations" OWNER TO "postgres";


COMMENT ON TABLE "prop_trading_model"."schema_migrations" IS 'Tracks applied database migrations';



CREATE TABLE IF NOT EXISTS "prop_trading_model"."schema_version" (
    "version_id" integer NOT NULL,
    "version_hash" character varying(32) NOT NULL,
    "applied_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "applied_by" character varying(100) DEFAULT CURRENT_USER,
    "description" "text",
    "migration_script" "text",
    "rollback_script" "text",
    "objects_affected" "jsonb",
    "execution_time_ms" integer,
    "status" character varying(20) DEFAULT 'applied'::character varying,
    CONSTRAINT "schema_version_status_check" CHECK ((("status")::"text" = ANY ((ARRAY['applied'::character varying, 'rolled_back'::character varying, 'failed'::character varying])::"text"[])))
);


ALTER TABLE "prop_trading_model"."schema_version" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "prop_trading_model"."schema_version_version_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE "prop_trading_model"."schema_version_version_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "prop_trading_model"."schema_version_version_id_seq" OWNED BY "prop_trading_model"."schema_version"."version_id";



CREATE TABLE IF NOT EXISTS "prop_trading_model"."stg_accounts_daily_snapshots" (
    "account_id" character varying(255) NOT NULL,
    "snapshot_date" "date" NOT NULL,
    "login" character varying(255) NOT NULL,
    "plan_id" character varying(255),
    "trader_id" character varying(255),
    "status" integer,
    "type" integer,
    "phase" integer,
    "broker" integer,
    "platform" integer,
    "country" character varying(2),
    "starting_balance" numeric(18,2),
    "balance" numeric(18,2),
    "equity" numeric(18,2),
    "profit_target" numeric(18,2),
    "profit_target_pct" numeric(5,2),
    "max_daily_drawdown" numeric(18,2),
    "max_daily_drawdown_pct" numeric(5,2),
    "max_drawdown" numeric(18,2),
    "max_drawdown_pct" numeric(5,2),
    "max_leverage" numeric(10,2),
    "is_drawdown_relative" boolean,
    "distance_to_profit_target" numeric(18,2),
    "distance_to_max_drawdown" numeric(18,2),
    "liquidate_friday" boolean DEFAULT false,
    "inactivity_period" integer,
    "daily_drawdown_by_balance_equity" boolean DEFAULT false,
    "enable_consistency" boolean DEFAULT false,
    "days_active" integer,
    "days_since_last_trade" integer,
    "created_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "stg_accounts_daily_snapshots_phase_check" CHECK (("phase" = ANY (ARRAY[1, 2, 3, 4]))),
    CONSTRAINT "stg_accounts_daily_snapshots_status_check" CHECK (("status" = ANY (ARRAY[1, 2, 3])))
);


ALTER TABLE "prop_trading_model"."stg_accounts_daily_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."accounts" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "account_id" character varying(50) NOT NULL,
    "score" numeric DEFAULT 0,
    "login" character varying(50),
    "trader" character varying(50),
    "status" character varying(20) NOT NULL,
    "type" character varying(20) NOT NULL,
    "phase" integer NOT NULL,
    "country" character varying(2),
    "approved_payouts" numeric DEFAULT 0,
    "pending_payouts" numeric DEFAULT 0,
    "vector_alltime" "extensions"."vector"(3072),
    "vector_daily" "extensions"."vector"(3072)[],
    "vector_hourly" "extensions"."vector"(3072)[],
    "status_changed_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "chk_score_range" CHECK ((("score" >= '-1.0'::numeric) AND ("score" <= 1.0)))
);


ALTER TABLE "public"."accounts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."regimes_daily" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "date" "date" DEFAULT CURRENT_DATE NOT NULL,
    "market_news" "jsonb",
    "instruments" "jsonb",
    "country_economic_indicators" "jsonb",
    "vector_daily_regime" "extensions"."vector"(3072),
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "news_analysis" "jsonb",
    "summary" "jsonb"
);


ALTER TABLE "public"."regimes_daily" OWNER TO "postgres";


ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01" FOR VALUES FROM ('2022-01-01') TO ('2022-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02" FOR VALUES FROM ('2022-02-01') TO ('2022-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03" FOR VALUES FROM ('2022-03-01') TO ('2022-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04" FOR VALUES FROM ('2022-04-01') TO ('2022-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05" FOR VALUES FROM ('2022-05-01') TO ('2022-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06" FOR VALUES FROM ('2022-06-01') TO ('2022-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07" FOR VALUES FROM ('2022-07-01') TO ('2022-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08" FOR VALUES FROM ('2022-08-01') TO ('2022-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09" FOR VALUES FROM ('2022-09-01') TO ('2022-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10" FOR VALUES FROM ('2022-10-01') TO ('2022-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11" FOR VALUES FROM ('2022-11-01') TO ('2022-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12" FOR VALUES FROM ('2022-12-01') TO ('2023-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01" FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02" FOR VALUES FROM ('2023-02-01') TO ('2023-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03" FOR VALUES FROM ('2023-03-01') TO ('2023-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04" FOR VALUES FROM ('2023-04-01') TO ('2023-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05" FOR VALUES FROM ('2023-05-01') TO ('2023-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06" FOR VALUES FROM ('2023-06-01') TO ('2023-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07" FOR VALUES FROM ('2023-07-01') TO ('2023-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08" FOR VALUES FROM ('2023-08-01') TO ('2023-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09" FOR VALUES FROM ('2023-09-01') TO ('2023-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10" FOR VALUES FROM ('2023-10-01') TO ('2023-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11" FOR VALUES FROM ('2023-11-01') TO ('2023-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12" FOR VALUES FROM ('2023-12-01') TO ('2024-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01" FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02" FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03" FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04" FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05" FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06" FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07" FOR VALUES FROM ('2024-07-01') TO ('2024-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08" FOR VALUES FROM ('2024-08-01') TO ('2024-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09" FOR VALUES FROM ('2024-09-01') TO ('2024-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10" FOR VALUES FROM ('2024-10-01') TO ('2024-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11" FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12" FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01" FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02" FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03" FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04" FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05" FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06" FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07" FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08" FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09" FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01" FOR VALUES FROM ('2022-01-01') TO ('2022-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02" FOR VALUES FROM ('2022-02-01') TO ('2022-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03" FOR VALUES FROM ('2022-03-01') TO ('2022-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04" FOR VALUES FROM ('2022-04-01') TO ('2022-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05" FOR VALUES FROM ('2022-05-01') TO ('2022-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06" FOR VALUES FROM ('2022-06-01') TO ('2022-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07" FOR VALUES FROM ('2022-07-01') TO ('2022-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08" FOR VALUES FROM ('2022-08-01') TO ('2022-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09" FOR VALUES FROM ('2022-09-01') TO ('2022-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10" FOR VALUES FROM ('2022-10-01') TO ('2022-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11" FOR VALUES FROM ('2022-11-01') TO ('2022-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12" FOR VALUES FROM ('2022-12-01') TO ('2023-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01" FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02" FOR VALUES FROM ('2023-02-01') TO ('2023-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03" FOR VALUES FROM ('2023-03-01') TO ('2023-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04" FOR VALUES FROM ('2023-04-01') TO ('2023-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05" FOR VALUES FROM ('2023-05-01') TO ('2023-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06" FOR VALUES FROM ('2023-06-01') TO ('2023-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07" FOR VALUES FROM ('2023-07-01') TO ('2023-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08" FOR VALUES FROM ('2023-08-01') TO ('2023-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09" FOR VALUES FROM ('2023-09-01') TO ('2023-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10" FOR VALUES FROM ('2023-10-01') TO ('2023-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11" FOR VALUES FROM ('2023-11-01') TO ('2023-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12" FOR VALUES FROM ('2023-12-01') TO ('2024-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01" FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02" FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03" FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04" FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05" FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06" FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07" FOR VALUES FROM ('2024-07-01') TO ('2024-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08" FOR VALUES FROM ('2024-08-01') TO ('2024-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09" FOR VALUES FROM ('2024-09-01') TO ('2024-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10" FOR VALUES FROM ('2024-10-01') TO ('2024-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11" FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12" FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01" FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02" FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03" FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04" FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05" FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06" FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07" FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08" FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09" FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01" FOR VALUES FROM ('2022-01-01') TO ('2022-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02" FOR VALUES FROM ('2022-02-01') TO ('2022-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03" FOR VALUES FROM ('2022-03-01') TO ('2022-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04" FOR VALUES FROM ('2022-04-01') TO ('2022-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05" FOR VALUES FROM ('2022-05-01') TO ('2022-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06" FOR VALUES FROM ('2022-06-01') TO ('2022-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07" FOR VALUES FROM ('2022-07-01') TO ('2022-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08" FOR VALUES FROM ('2022-08-01') TO ('2022-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09" FOR VALUES FROM ('2022-09-01') TO ('2022-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10" FOR VALUES FROM ('2022-10-01') TO ('2022-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11" FOR VALUES FROM ('2022-11-01') TO ('2022-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12" FOR VALUES FROM ('2022-12-01') TO ('2023-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01" FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02" FOR VALUES FROM ('2023-02-01') TO ('2023-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03" FOR VALUES FROM ('2023-03-01') TO ('2023-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04" FOR VALUES FROM ('2023-04-01') TO ('2023-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05" FOR VALUES FROM ('2023-05-01') TO ('2023-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06" FOR VALUES FROM ('2023-06-01') TO ('2023-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07" FOR VALUES FROM ('2023-07-01') TO ('2023-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08" FOR VALUES FROM ('2023-08-01') TO ('2023-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09" FOR VALUES FROM ('2023-09-01') TO ('2023-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10" FOR VALUES FROM ('2023-10-01') TO ('2023-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11" FOR VALUES FROM ('2023-11-01') TO ('2023-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12" FOR VALUES FROM ('2023-12-01') TO ('2024-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01" FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02" FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03" FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04" FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05" FOR VALUES FROM ('2024-05-01') TO ('2024-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06" FOR VALUES FROM ('2024-06-01') TO ('2024-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07" FOR VALUES FROM ('2024-07-01') TO ('2024-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08" FOR VALUES FROM ('2024-08-01') TO ('2024-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09" FOR VALUES FROM ('2024-09-01') TO ('2024-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10" FOR VALUES FROM ('2024-10-01') TO ('2024-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11" FOR VALUES FROM ('2024-11-01') TO ('2024-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12" FOR VALUES FROM ('2024-12-01') TO ('2025-01-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01" FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02" FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03" FOR VALUES FROM ('2025-03-01') TO ('2025-04-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04" FOR VALUES FROM ('2025-04-01') TO ('2025-05-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05" FOR VALUES FROM ('2025-05-01') TO ('2025-06-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06" FOR VALUES FROM ('2025-06-01') TO ('2025-07-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07" FOR VALUES FROM ('2025-07-01') TO ('2025-08-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08" FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09" FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10" FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11" FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12" FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');



ALTER TABLE ONLY "prop_trading_model"."feature_store_account_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."feature_store_account_daily_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."model_predictions" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."model_predictions_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."model_registry" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."model_registry_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."model_training_input" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."model_training_input_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."pipeline_execution_log" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."pipeline_execution_log_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."query_performance_log" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."query_performance_log_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."raw_regimes_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('"prop_trading_model"."raw_regimes_daily_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."schema_version" ALTER COLUMN "version_id" SET DEFAULT "nextval"('"prop_trading_model"."schema_version_version_id_seq"'::"regclass");



ALTER TABLE ONLY "prop_trading_model"."feature_store_account_daily"
    ADD CONSTRAINT "feature_store_account_daily_account_id_feature_date_key" UNIQUE ("account_id", "feature_date");



ALTER TABLE ONLY "prop_trading_model"."feature_store_account_daily"
    ADD CONSTRAINT "feature_store_account_daily_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."model_predictions"
    ADD CONSTRAINT "model_predictions_model_version_prediction_date_account_id_key" UNIQUE ("model_version", "prediction_date", "account_id");



ALTER TABLE ONLY "prop_trading_model"."model_predictions"
    ADD CONSTRAINT "model_predictions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."model_registry"
    ADD CONSTRAINT "model_registry_model_version_key" UNIQUE ("model_version");



ALTER TABLE ONLY "prop_trading_model"."model_registry"
    ADD CONSTRAINT "model_registry_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."model_training_input"
    ADD CONSTRAINT "model_training_input_account_id_prediction_date_key" UNIQUE ("account_id", "prediction_date");



ALTER TABLE ONLY "prop_trading_model"."model_training_input"
    ADD CONSTRAINT "model_training_input_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."pipeline_execution_log"
    ADD CONSTRAINT "pipeline_execution_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."query_performance_log"
    ADD CONSTRAINT "query_performance_log_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_alltime"
    ADD CONSTRAINT "raw_metrics_alltime_pkey" PRIMARY KEY ("account_id");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily"
    ADD CONSTRAINT "raw_metrics_daily_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_01"
    ADD CONSTRAINT "raw_metrics_daily_2022_01_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_02"
    ADD CONSTRAINT "raw_metrics_daily_2022_02_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_03"
    ADD CONSTRAINT "raw_metrics_daily_2022_03_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_04"
    ADD CONSTRAINT "raw_metrics_daily_2022_04_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_05"
    ADD CONSTRAINT "raw_metrics_daily_2022_05_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_06"
    ADD CONSTRAINT "raw_metrics_daily_2022_06_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_07"
    ADD CONSTRAINT "raw_metrics_daily_2022_07_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_08"
    ADD CONSTRAINT "raw_metrics_daily_2022_08_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_09"
    ADD CONSTRAINT "raw_metrics_daily_2022_09_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_10"
    ADD CONSTRAINT "raw_metrics_daily_2022_10_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_11"
    ADD CONSTRAINT "raw_metrics_daily_2022_11_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2022_12"
    ADD CONSTRAINT "raw_metrics_daily_2022_12_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_01"
    ADD CONSTRAINT "raw_metrics_daily_2023_01_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_02"
    ADD CONSTRAINT "raw_metrics_daily_2023_02_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_03"
    ADD CONSTRAINT "raw_metrics_daily_2023_03_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_04"
    ADD CONSTRAINT "raw_metrics_daily_2023_04_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_05"
    ADD CONSTRAINT "raw_metrics_daily_2023_05_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_06"
    ADD CONSTRAINT "raw_metrics_daily_2023_06_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_07"
    ADD CONSTRAINT "raw_metrics_daily_2023_07_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_08"
    ADD CONSTRAINT "raw_metrics_daily_2023_08_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_09"
    ADD CONSTRAINT "raw_metrics_daily_2023_09_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_10"
    ADD CONSTRAINT "raw_metrics_daily_2023_10_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_11"
    ADD CONSTRAINT "raw_metrics_daily_2023_11_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2023_12"
    ADD CONSTRAINT "raw_metrics_daily_2023_12_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_01"
    ADD CONSTRAINT "raw_metrics_daily_2024_01_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_02"
    ADD CONSTRAINT "raw_metrics_daily_2024_02_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_03"
    ADD CONSTRAINT "raw_metrics_daily_2024_03_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_04"
    ADD CONSTRAINT "raw_metrics_daily_2024_04_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_05"
    ADD CONSTRAINT "raw_metrics_daily_2024_05_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_06"
    ADD CONSTRAINT "raw_metrics_daily_2024_06_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_07"
    ADD CONSTRAINT "raw_metrics_daily_2024_07_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_08"
    ADD CONSTRAINT "raw_metrics_daily_2024_08_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_09"
    ADD CONSTRAINT "raw_metrics_daily_2024_09_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_10"
    ADD CONSTRAINT "raw_metrics_daily_2024_10_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_11"
    ADD CONSTRAINT "raw_metrics_daily_2024_11_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2024_12"
    ADD CONSTRAINT "raw_metrics_daily_2024_12_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_01"
    ADD CONSTRAINT "raw_metrics_daily_2025_01_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_02"
    ADD CONSTRAINT "raw_metrics_daily_2025_02_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_03"
    ADD CONSTRAINT "raw_metrics_daily_2025_03_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_04"
    ADD CONSTRAINT "raw_metrics_daily_2025_04_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_05"
    ADD CONSTRAINT "raw_metrics_daily_2025_05_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_06"
    ADD CONSTRAINT "raw_metrics_daily_2025_06_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_07"
    ADD CONSTRAINT "raw_metrics_daily_2025_07_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_08"
    ADD CONSTRAINT "raw_metrics_daily_2025_08_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_daily_2025_09"
    ADD CONSTRAINT "raw_metrics_daily_2025_09_pkey" PRIMARY KEY ("account_id", "date");



ALTER TABLE ONLY "prop_trading_model"."raw_metrics_hourly"
    ADD CONSTRAINT "raw_metrics_hourly_pkey" PRIMARY KEY ("account_id", "date", "hour");



ALTER TABLE ONLY "prop_trading_model"."raw_plans_data"
    ADD CONSTRAINT "raw_plans_data_pkey" PRIMARY KEY ("plan_id");



ALTER TABLE ONLY "prop_trading_model"."raw_regimes_daily"
    ADD CONSTRAINT "raw_regimes_daily_date_key" UNIQUE ("date");



ALTER TABLE ONLY "prop_trading_model"."raw_regimes_daily"
    ADD CONSTRAINT "raw_regimes_daily_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed"
    ADD CONSTRAINT "raw_trades_closed_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_01"
    ADD CONSTRAINT "raw_trades_closed_2022_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed"
    ADD CONSTRAINT "raw_trades_closed_position_login_platform_broker_trade_date_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_01"
    ADD CONSTRAINT "raw_trades_closed_2022_01_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_02"
    ADD CONSTRAINT "raw_trades_closed_2022_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_02"
    ADD CONSTRAINT "raw_trades_closed_2022_02_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_03"
    ADD CONSTRAINT "raw_trades_closed_2022_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_03"
    ADD CONSTRAINT "raw_trades_closed_2022_03_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_04"
    ADD CONSTRAINT "raw_trades_closed_2022_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_04"
    ADD CONSTRAINT "raw_trades_closed_2022_04_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_05"
    ADD CONSTRAINT "raw_trades_closed_2022_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_05"
    ADD CONSTRAINT "raw_trades_closed_2022_05_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_06"
    ADD CONSTRAINT "raw_trades_closed_2022_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_06"
    ADD CONSTRAINT "raw_trades_closed_2022_06_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_07"
    ADD CONSTRAINT "raw_trades_closed_2022_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_07"
    ADD CONSTRAINT "raw_trades_closed_2022_07_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_08"
    ADD CONSTRAINT "raw_trades_closed_2022_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_08"
    ADD CONSTRAINT "raw_trades_closed_2022_08_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_09"
    ADD CONSTRAINT "raw_trades_closed_2022_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_09"
    ADD CONSTRAINT "raw_trades_closed_2022_09_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_10"
    ADD CONSTRAINT "raw_trades_closed_2022_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_10"
    ADD CONSTRAINT "raw_trades_closed_2022_10_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_11"
    ADD CONSTRAINT "raw_trades_closed_2022_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_11"
    ADD CONSTRAINT "raw_trades_closed_2022_11_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_12"
    ADD CONSTRAINT "raw_trades_closed_2022_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2022_12"
    ADD CONSTRAINT "raw_trades_closed_2022_12_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_01"
    ADD CONSTRAINT "raw_trades_closed_2023_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_01"
    ADD CONSTRAINT "raw_trades_closed_2023_01_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_02"
    ADD CONSTRAINT "raw_trades_closed_2023_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_02"
    ADD CONSTRAINT "raw_trades_closed_2023_02_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_03"
    ADD CONSTRAINT "raw_trades_closed_2023_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_03"
    ADD CONSTRAINT "raw_trades_closed_2023_03_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_04"
    ADD CONSTRAINT "raw_trades_closed_2023_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_04"
    ADD CONSTRAINT "raw_trades_closed_2023_04_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_05"
    ADD CONSTRAINT "raw_trades_closed_2023_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_05"
    ADD CONSTRAINT "raw_trades_closed_2023_05_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_06"
    ADD CONSTRAINT "raw_trades_closed_2023_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_06"
    ADD CONSTRAINT "raw_trades_closed_2023_06_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_07"
    ADD CONSTRAINT "raw_trades_closed_2023_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_07"
    ADD CONSTRAINT "raw_trades_closed_2023_07_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_08"
    ADD CONSTRAINT "raw_trades_closed_2023_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_08"
    ADD CONSTRAINT "raw_trades_closed_2023_08_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_09"
    ADD CONSTRAINT "raw_trades_closed_2023_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_09"
    ADD CONSTRAINT "raw_trades_closed_2023_09_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_10"
    ADD CONSTRAINT "raw_trades_closed_2023_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_10"
    ADD CONSTRAINT "raw_trades_closed_2023_10_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_11"
    ADD CONSTRAINT "raw_trades_closed_2023_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_11"
    ADD CONSTRAINT "raw_trades_closed_2023_11_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_12"
    ADD CONSTRAINT "raw_trades_closed_2023_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2023_12"
    ADD CONSTRAINT "raw_trades_closed_2023_12_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_01"
    ADD CONSTRAINT "raw_trades_closed_2024_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_01"
    ADD CONSTRAINT "raw_trades_closed_2024_01_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_02"
    ADD CONSTRAINT "raw_trades_closed_2024_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_02"
    ADD CONSTRAINT "raw_trades_closed_2024_02_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_03"
    ADD CONSTRAINT "raw_trades_closed_2024_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_03"
    ADD CONSTRAINT "raw_trades_closed_2024_03_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_04"
    ADD CONSTRAINT "raw_trades_closed_2024_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_04"
    ADD CONSTRAINT "raw_trades_closed_2024_04_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_05"
    ADD CONSTRAINT "raw_trades_closed_2024_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_05"
    ADD CONSTRAINT "raw_trades_closed_2024_05_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_06"
    ADD CONSTRAINT "raw_trades_closed_2024_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_06"
    ADD CONSTRAINT "raw_trades_closed_2024_06_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_07"
    ADD CONSTRAINT "raw_trades_closed_2024_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_07"
    ADD CONSTRAINT "raw_trades_closed_2024_07_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_08"
    ADD CONSTRAINT "raw_trades_closed_2024_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_08"
    ADD CONSTRAINT "raw_trades_closed_2024_08_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_09"
    ADD CONSTRAINT "raw_trades_closed_2024_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_09"
    ADD CONSTRAINT "raw_trades_closed_2024_09_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_10"
    ADD CONSTRAINT "raw_trades_closed_2024_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_10"
    ADD CONSTRAINT "raw_trades_closed_2024_10_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_11"
    ADD CONSTRAINT "raw_trades_closed_2024_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_11"
    ADD CONSTRAINT "raw_trades_closed_2024_11_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_12"
    ADD CONSTRAINT "raw_trades_closed_2024_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2024_12"
    ADD CONSTRAINT "raw_trades_closed_2024_12_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_01"
    ADD CONSTRAINT "raw_trades_closed_2025_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_01"
    ADD CONSTRAINT "raw_trades_closed_2025_01_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_02"
    ADD CONSTRAINT "raw_trades_closed_2025_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_02"
    ADD CONSTRAINT "raw_trades_closed_2025_02_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_03"
    ADD CONSTRAINT "raw_trades_closed_2025_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_03"
    ADD CONSTRAINT "raw_trades_closed_2025_03_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_04"
    ADD CONSTRAINT "raw_trades_closed_2025_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_04"
    ADD CONSTRAINT "raw_trades_closed_2025_04_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_05"
    ADD CONSTRAINT "raw_trades_closed_2025_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_05"
    ADD CONSTRAINT "raw_trades_closed_2025_05_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_06"
    ADD CONSTRAINT "raw_trades_closed_2025_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_06"
    ADD CONSTRAINT "raw_trades_closed_2025_06_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_07"
    ADD CONSTRAINT "raw_trades_closed_2025_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_07"
    ADD CONSTRAINT "raw_trades_closed_2025_07_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_08"
    ADD CONSTRAINT "raw_trades_closed_2025_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_08"
    ADD CONSTRAINT "raw_trades_closed_2025_08_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_09"
    ADD CONSTRAINT "raw_trades_closed_2025_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_closed_2025_09"
    ADD CONSTRAINT "raw_trades_closed_2025_09_position_login_platform_broker_tr_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open"
    ADD CONSTRAINT "raw_trades_open_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_01"
    ADD CONSTRAINT "raw_trades_open_2022_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open"
    ADD CONSTRAINT "raw_trades_open_position_login_platform_broker_trade_date_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_01"
    ADD CONSTRAINT "raw_trades_open_2022_01_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_02"
    ADD CONSTRAINT "raw_trades_open_2022_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_02"
    ADD CONSTRAINT "raw_trades_open_2022_02_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_03"
    ADD CONSTRAINT "raw_trades_open_2022_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_03"
    ADD CONSTRAINT "raw_trades_open_2022_03_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_04"
    ADD CONSTRAINT "raw_trades_open_2022_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_04"
    ADD CONSTRAINT "raw_trades_open_2022_04_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_05"
    ADD CONSTRAINT "raw_trades_open_2022_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_05"
    ADD CONSTRAINT "raw_trades_open_2022_05_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_06"
    ADD CONSTRAINT "raw_trades_open_2022_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_06"
    ADD CONSTRAINT "raw_trades_open_2022_06_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_07"
    ADD CONSTRAINT "raw_trades_open_2022_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_07"
    ADD CONSTRAINT "raw_trades_open_2022_07_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_08"
    ADD CONSTRAINT "raw_trades_open_2022_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_08"
    ADD CONSTRAINT "raw_trades_open_2022_08_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_09"
    ADD CONSTRAINT "raw_trades_open_2022_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_09"
    ADD CONSTRAINT "raw_trades_open_2022_09_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_10"
    ADD CONSTRAINT "raw_trades_open_2022_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_10"
    ADD CONSTRAINT "raw_trades_open_2022_10_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_11"
    ADD CONSTRAINT "raw_trades_open_2022_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_11"
    ADD CONSTRAINT "raw_trades_open_2022_11_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_12"
    ADD CONSTRAINT "raw_trades_open_2022_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2022_12"
    ADD CONSTRAINT "raw_trades_open_2022_12_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_01"
    ADD CONSTRAINT "raw_trades_open_2023_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_01"
    ADD CONSTRAINT "raw_trades_open_2023_01_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_02"
    ADD CONSTRAINT "raw_trades_open_2023_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_02"
    ADD CONSTRAINT "raw_trades_open_2023_02_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_03"
    ADD CONSTRAINT "raw_trades_open_2023_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_03"
    ADD CONSTRAINT "raw_trades_open_2023_03_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_04"
    ADD CONSTRAINT "raw_trades_open_2023_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_04"
    ADD CONSTRAINT "raw_trades_open_2023_04_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_05"
    ADD CONSTRAINT "raw_trades_open_2023_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_05"
    ADD CONSTRAINT "raw_trades_open_2023_05_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_06"
    ADD CONSTRAINT "raw_trades_open_2023_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_06"
    ADD CONSTRAINT "raw_trades_open_2023_06_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_07"
    ADD CONSTRAINT "raw_trades_open_2023_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_07"
    ADD CONSTRAINT "raw_trades_open_2023_07_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_08"
    ADD CONSTRAINT "raw_trades_open_2023_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_08"
    ADD CONSTRAINT "raw_trades_open_2023_08_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_09"
    ADD CONSTRAINT "raw_trades_open_2023_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_09"
    ADD CONSTRAINT "raw_trades_open_2023_09_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_10"
    ADD CONSTRAINT "raw_trades_open_2023_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_10"
    ADD CONSTRAINT "raw_trades_open_2023_10_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_11"
    ADD CONSTRAINT "raw_trades_open_2023_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_11"
    ADD CONSTRAINT "raw_trades_open_2023_11_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_12"
    ADD CONSTRAINT "raw_trades_open_2023_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2023_12"
    ADD CONSTRAINT "raw_trades_open_2023_12_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_01"
    ADD CONSTRAINT "raw_trades_open_2024_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_01"
    ADD CONSTRAINT "raw_trades_open_2024_01_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_02"
    ADD CONSTRAINT "raw_trades_open_2024_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_02"
    ADD CONSTRAINT "raw_trades_open_2024_02_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_03"
    ADD CONSTRAINT "raw_trades_open_2024_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_03"
    ADD CONSTRAINT "raw_trades_open_2024_03_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_04"
    ADD CONSTRAINT "raw_trades_open_2024_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_04"
    ADD CONSTRAINT "raw_trades_open_2024_04_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_05"
    ADD CONSTRAINT "raw_trades_open_2024_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_05"
    ADD CONSTRAINT "raw_trades_open_2024_05_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_06"
    ADD CONSTRAINT "raw_trades_open_2024_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_06"
    ADD CONSTRAINT "raw_trades_open_2024_06_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_07"
    ADD CONSTRAINT "raw_trades_open_2024_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_07"
    ADD CONSTRAINT "raw_trades_open_2024_07_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_08"
    ADD CONSTRAINT "raw_trades_open_2024_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_08"
    ADD CONSTRAINT "raw_trades_open_2024_08_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_09"
    ADD CONSTRAINT "raw_trades_open_2024_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_09"
    ADD CONSTRAINT "raw_trades_open_2024_09_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_10"
    ADD CONSTRAINT "raw_trades_open_2024_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_10"
    ADD CONSTRAINT "raw_trades_open_2024_10_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_11"
    ADD CONSTRAINT "raw_trades_open_2024_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_11"
    ADD CONSTRAINT "raw_trades_open_2024_11_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_12"
    ADD CONSTRAINT "raw_trades_open_2024_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2024_12"
    ADD CONSTRAINT "raw_trades_open_2024_12_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_01"
    ADD CONSTRAINT "raw_trades_open_2025_01_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_01"
    ADD CONSTRAINT "raw_trades_open_2025_01_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_02"
    ADD CONSTRAINT "raw_trades_open_2025_02_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_02"
    ADD CONSTRAINT "raw_trades_open_2025_02_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_03"
    ADD CONSTRAINT "raw_trades_open_2025_03_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_03"
    ADD CONSTRAINT "raw_trades_open_2025_03_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_04"
    ADD CONSTRAINT "raw_trades_open_2025_04_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_04"
    ADD CONSTRAINT "raw_trades_open_2025_04_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_05"
    ADD CONSTRAINT "raw_trades_open_2025_05_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_05"
    ADD CONSTRAINT "raw_trades_open_2025_05_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_06"
    ADD CONSTRAINT "raw_trades_open_2025_06_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_06"
    ADD CONSTRAINT "raw_trades_open_2025_06_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_07"
    ADD CONSTRAINT "raw_trades_open_2025_07_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_07"
    ADD CONSTRAINT "raw_trades_open_2025_07_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_08"
    ADD CONSTRAINT "raw_trades_open_2025_08_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_08"
    ADD CONSTRAINT "raw_trades_open_2025_08_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_09"
    ADD CONSTRAINT "raw_trades_open_2025_09_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_09"
    ADD CONSTRAINT "raw_trades_open_2025_09_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_10"
    ADD CONSTRAINT "raw_trades_open_2025_10_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_10"
    ADD CONSTRAINT "raw_trades_open_2025_10_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_11"
    ADD CONSTRAINT "raw_trades_open_2025_11_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_11"
    ADD CONSTRAINT "raw_trades_open_2025_11_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_12"
    ADD CONSTRAINT "raw_trades_open_2025_12_pkey" PRIMARY KEY ("platform", "position", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."raw_trades_open_2025_12"
    ADD CONSTRAINT "raw_trades_open_2025_12_position_login_platform_broker_trad_key" UNIQUE ("position", "login", "platform", "broker", "trade_date");



ALTER TABLE ONLY "prop_trading_model"."scheduled_jobs"
    ADD CONSTRAINT "scheduled_jobs_pkey" PRIMARY KEY ("job_name");



ALTER TABLE ONLY "prop_trading_model"."schema_migrations"
    ADD CONSTRAINT "schema_migrations_pkey" PRIMARY KEY ("migration_name");



ALTER TABLE ONLY "prop_trading_model"."schema_version"
    ADD CONSTRAINT "schema_version_pkey" PRIMARY KEY ("version_id");



ALTER TABLE ONLY "prop_trading_model"."schema_version"
    ADD CONSTRAINT "schema_version_version_hash_key" UNIQUE ("version_hash");



ALTER TABLE ONLY "prop_trading_model"."stg_accounts_daily_snapshots"
    ADD CONSTRAINT "stg_accounts_daily_snapshots_pkey" PRIMARY KEY ("account_id", "snapshot_date");



ALTER TABLE ONLY "public"."accounts"
    ADD CONSTRAINT "accounts_account_id_key" UNIQUE ("account_id");



ALTER TABLE ONLY "public"."accounts"
    ADD CONSTRAINT "accounts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."regimes_daily"
    ADD CONSTRAINT "regimes_daily_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_feature_store_account_date" ON "prop_trading_model"."feature_store_account_daily" USING "btree" ("account_id", "feature_date" DESC);



CREATE INDEX "idx_feature_store_date" ON "prop_trading_model"."feature_store_account_daily" USING "btree" ("feature_date" DESC);



CREATE INDEX "idx_model_predictions_account" ON "prop_trading_model"."model_predictions" USING "btree" ("account_id", "prediction_date" DESC);



CREATE INDEX "idx_model_predictions_date" ON "prop_trading_model"."model_predictions" USING "btree" ("prediction_date" DESC);



CREATE UNIQUE INDEX "idx_mv_account_performance_account_id" ON "prop_trading_model"."mv_account_performance_summary" USING "btree" ("account_id");



CREATE INDEX "idx_mv_account_performance_phase" ON "prop_trading_model"."mv_account_performance_summary" USING "btree" ("phase");



CREATE INDEX "idx_mv_account_performance_profit" ON "prop_trading_model"."mv_account_performance_summary" USING "btree" ("lifetime_profit" DESC);



CREATE INDEX "idx_mv_account_performance_recent_profit" ON "prop_trading_model"."mv_account_performance_summary" USING "btree" ("profit_last_30d" DESC);



CREATE INDEX "idx_mv_account_performance_status" ON "prop_trading_model"."mv_account_performance_summary" USING "btree" ("status") WHERE ("status" = 1);



CREATE UNIQUE INDEX "idx_mv_daily_stats_date" ON "prop_trading_model"."mv_daily_trading_stats" USING "btree" ("date");



CREATE INDEX "idx_mv_daily_stats_dow" ON "prop_trading_model"."mv_daily_trading_stats" USING "btree" ("day_of_week");



CREATE INDEX "idx_mv_daily_stats_year_month" ON "prop_trading_model"."mv_daily_trading_stats" USING "btree" ("year", "month");



CREATE INDEX "idx_mv_regime_performance_date" ON "prop_trading_model"."mv_market_regime_performance" USING "btree" ("date" DESC);



CREATE INDEX "idx_mv_regime_performance_sentiment" ON "prop_trading_model"."mv_market_regime_performance" USING "btree" ("market_sentiment");



CREATE INDEX "idx_mv_symbol_performance_profit" ON "prop_trading_model"."mv_symbol_performance" USING "btree" ("total_profit" DESC);



CREATE UNIQUE INDEX "idx_mv_symbol_performance_symbol" ON "prop_trading_model"."mv_symbol_performance" USING "btree" ("std_symbol");



CREATE INDEX "idx_mv_symbol_performance_trades" ON "prop_trading_model"."mv_symbol_performance" USING "btree" ("num_trades" DESC);



CREATE INDEX "idx_mv_symbol_performance_win_rate" ON "prop_trading_model"."mv_symbol_performance" USING "btree" ("win_rate" DESC);



CREATE UNIQUE INDEX "idx_mv_trading_patterns_account_id" ON "prop_trading_model"."mv_account_trading_patterns" USING "btree" ("account_id");



CREATE INDEX "idx_mv_trading_patterns_login" ON "prop_trading_model"."mv_account_trading_patterns" USING "btree" ("login");



CREATE INDEX "idx_pipeline_execution_stage_date" ON "prop_trading_model"."pipeline_execution_log" USING "btree" ("pipeline_stage", "execution_date" DESC);



CREATE INDEX "idx_pipeline_execution_status" ON "prop_trading_model"."pipeline_execution_log" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "idx_raw_metrics_alltime_account_id" ON "prop_trading_model"."raw_metrics_alltime" USING "btree" ("account_id");



CREATE INDEX "idx_raw_metrics_alltime_login" ON "prop_trading_model"."raw_metrics_alltime" USING "btree" ("login");



CREATE INDEX "idx_raw_metrics_alltime_login_platform_broker" ON "prop_trading_model"."raw_metrics_alltime" USING "btree" ("login", "platform", "broker");



CREATE INDEX "idx_raw_metrics_alltime_plan_id" ON "prop_trading_model"."raw_metrics_alltime" USING "btree" ("plan_id");



CREATE INDEX "idx_raw_metrics_alltime_trader_id" ON "prop_trading_model"."raw_metrics_alltime" USING "btree" ("trader_id");



CREATE INDEX "idx_raw_metrics_daily_account_date" ON ONLY "prop_trading_model"."raw_metrics_daily" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "idx_raw_metrics_daily_date" ON ONLY "prop_trading_model"."raw_metrics_daily" USING "btree" ("date" DESC);



CREATE INDEX "idx_raw_metrics_daily_login" ON ONLY "prop_trading_model"."raw_metrics_daily" USING "btree" ("login");



CREATE INDEX "idx_raw_metrics_daily_profit" ON ONLY "prop_trading_model"."raw_metrics_daily" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "idx_raw_metrics_hourly_account_date" ON "prop_trading_model"."raw_metrics_hourly" USING "btree" ("account_id", "date" DESC, "hour");



CREATE INDEX "idx_raw_metrics_hourly_date_hour" ON "prop_trading_model"."raw_metrics_hourly" USING "btree" ("date" DESC, "hour");



CREATE INDEX "idx_raw_metrics_hourly_plan_id" ON "prop_trading_model"."raw_metrics_hourly" USING "btree" ("plan_id");



CREATE INDEX "idx_raw_metrics_hourly_profit" ON "prop_trading_model"."raw_metrics_hourly" USING "btree" ("date" DESC, "hour", "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "idx_raw_metrics_hourly_status_date" ON "prop_trading_model"."raw_metrics_hourly" USING "btree" ("status", "date" DESC, "hour");



CREATE INDEX "idx_raw_plans_name" ON "prop_trading_model"."raw_plans_data" USING "btree" ("plan_name");



CREATE INDEX "idx_raw_plans_plan_id" ON "prop_trading_model"."raw_plans_data" USING "btree" ("plan_id");



CREATE INDEX "idx_raw_regimes_date" ON "prop_trading_model"."raw_regimes_daily" USING "btree" ("date" DESC);



CREATE INDEX "idx_raw_regimes_summary" ON "prop_trading_model"."raw_regimes_daily" USING "gin" ("summary");



CREATE INDEX "idx_raw_trades_closed_account_id" ON ONLY "prop_trading_model"."raw_trades_closed" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "idx_raw_trades_closed_login_platform_broker" ON ONLY "prop_trading_model"."raw_trades_closed" USING "btree" ("login", "platform", "broker");



CREATE INDEX "idx_raw_trades_closed_profit" ON ONLY "prop_trading_model"."raw_trades_closed" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "idx_raw_trades_closed_symbol" ON ONLY "prop_trading_model"."raw_trades_closed" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "idx_raw_trades_open_account_id" ON ONLY "prop_trading_model"."raw_trades_open" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "idx_raw_trades_open_login_platform_broker" ON ONLY "prop_trading_model"."raw_trades_open" USING "btree" ("login", "platform", "broker");



CREATE INDEX "idx_raw_trades_open_profit" ON ONLY "prop_trading_model"."raw_trades_open" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "idx_raw_trades_open_symbol" ON ONLY "prop_trading_model"."raw_trades_open" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "idx_schema_version_applied_at" ON "prop_trading_model"."schema_version" USING "btree" ("applied_at" DESC);



CREATE INDEX "idx_stg_accounts_daily_account_date" ON "prop_trading_model"."stg_accounts_daily_snapshots" USING "btree" ("account_id", "snapshot_date" DESC);



CREATE INDEX "idx_stg_accounts_daily_date" ON "prop_trading_model"."stg_accounts_daily_snapshots" USING "btree" ("snapshot_date" DESC);



CREATE INDEX "idx_stg_accounts_daily_status" ON "prop_trading_model"."stg_accounts_daily_snapshots" USING "btree" ("status") WHERE ("status" = 1);



CREATE INDEX "raw_metrics_daily_2022_01_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_01" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_01_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_01" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_01_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_01" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_01_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_01" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_02_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_02" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_02_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_02" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_02_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_02" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_02_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_02" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_03_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_03" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_03_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_03" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_03_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_03" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_03_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_03" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_04_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_04" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_04_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_04" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_04_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_04" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_04_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_04" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_05_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_05" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_05_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_05" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_05_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_05" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_05_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_05" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_06_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_06" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_06_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_06" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_06_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_06" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_06_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_06" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_07_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_07" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_07_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_07" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_07_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_07" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_07_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_07" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_08_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_08" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_08_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_08" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_08_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_08" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_08_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_08" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_09_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_09" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_09_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_09" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_09_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_09" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_09_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_09" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_10_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_10" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_10_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_10" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_10_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_10" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_10_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_10" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_11_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_11" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_11_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_11" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_11_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_11" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_11_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_11" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2022_12_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_12" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2022_12_date_idx" ON "prop_trading_model"."raw_metrics_daily_2022_12" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2022_12_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2022_12" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2022_12_login_idx" ON "prop_trading_model"."raw_metrics_daily_2022_12" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_01_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_01" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_01_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_01" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_01_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_01" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_01_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_01" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_02_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_02" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_02_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_02" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_02_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_02" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_02_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_02" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_03_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_03" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_03_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_03" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_03_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_03" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_03_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_03" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_04_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_04" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_04_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_04" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_04_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_04" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_04_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_04" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_05_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_05" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_05_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_05" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_05_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_05" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_05_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_05" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_06_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_06" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_06_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_06" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_06_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_06" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_06_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_06" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_07_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_07" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_07_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_07" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_07_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_07" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_07_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_07" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_08_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_08" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_08_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_08" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_08_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_08" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_08_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_08" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_09_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_09" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_09_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_09" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_09_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_09" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_09_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_09" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_10_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_10" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_10_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_10" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_10_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_10" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_10_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_10" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_11_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_11" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_11_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_11" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_11_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_11" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_11_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_11" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2023_12_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_12" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2023_12_date_idx" ON "prop_trading_model"."raw_metrics_daily_2023_12" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2023_12_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2023_12" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2023_12_login_idx" ON "prop_trading_model"."raw_metrics_daily_2023_12" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_01_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_01" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_01_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_01" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_01_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_01" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_01_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_01" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_02_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_02" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_02_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_02" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_02_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_02" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_02_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_02" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_03_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_03" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_03_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_03" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_03_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_03" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_03_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_03" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_04_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_04" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_04_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_04" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_04_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_04" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_04_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_04" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_05_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_05" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_05_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_05" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_05_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_05" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_05_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_05" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_06_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_06" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_06_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_06" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_06_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_06" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_06_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_06" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_07_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_07" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_07_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_07" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_07_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_07" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_07_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_07" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_08_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_08" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_08_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_08" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_08_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_08" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_08_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_08" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_09_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_09" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_09_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_09" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_09_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_09" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_09_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_09" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_10_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_10" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_10_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_10" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_10_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_10" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_10_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_10" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_11_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_11" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_11_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_11" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_11_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_11" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_11_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_11" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2024_12_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_12" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2024_12_date_idx" ON "prop_trading_model"."raw_metrics_daily_2024_12" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2024_12_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2024_12" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2024_12_login_idx" ON "prop_trading_model"."raw_metrics_daily_2024_12" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_01_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_01" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_01_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_01" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_01_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_01" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_01_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_01" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_02_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_02" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_02_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_02" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_02_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_02" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_02_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_02" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_03_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_03" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_03_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_03" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_03_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_03" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_03_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_03" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_04_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_04" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_04_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_04" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_04_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_04" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_04_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_04" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_05_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_05" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_05_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_05" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_05_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_05" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_05_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_05" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_06_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_06" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_06_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_06" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_06_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_06" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_06_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_06" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_07_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_07" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_07_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_07" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_07_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_07" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_07_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_07" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_08_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_08" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_08_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_08" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_08_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_08" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_08_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_08" USING "btree" ("login");



CREATE INDEX "raw_metrics_daily_2025_09_account_id_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_09" USING "btree" ("account_id", "date" DESC);



CREATE INDEX "raw_metrics_daily_2025_09_date_idx" ON "prop_trading_model"."raw_metrics_daily_2025_09" USING "btree" ("date" DESC);



CREATE INDEX "raw_metrics_daily_2025_09_date_net_profit_idx" ON "prop_trading_model"."raw_metrics_daily_2025_09" USING "btree" ("date" DESC, "net_profit" DESC) WHERE ("net_profit" IS NOT NULL);



CREATE INDEX "raw_metrics_daily_2025_09_login_idx" ON "prop_trading_model"."raw_metrics_daily_2025_09" USING "btree" ("login");



CREATE INDEX "raw_trades_closed_2022_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_01_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_01" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_02_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_02" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_03_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_03" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_04_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_04" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_05_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_05" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_06_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_06" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_07_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_07" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_08_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_08" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_09_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_09" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_10_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_10" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_11_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_11" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2022_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2022_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2022_12_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_12" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2022_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2022_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_01_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_01" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_02_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_02" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_03_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_03" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_04_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_04" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_05_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_05" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_06_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_06" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_07_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_07" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_08_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_08" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_09_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_09" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_10_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_10" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_11_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_11" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2023_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2023_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2023_12_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_12" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2023_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2023_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_01_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_01" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_02_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_02" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_03_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_03" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_04_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_04" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_05_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_05" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_06_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_06" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_07_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_07" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_08_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_08" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_09_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_09" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_10_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_10" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_11_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_11" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2024_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2024_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2024_12_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_12" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2024_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2024_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_01_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_01" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_02_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_02" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_03_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_03" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_04_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_04" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_05_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_05" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_06_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_06" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_07_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_07" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_08_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_08" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_closed_2025_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_closed_2025_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_closed_2025_09_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_09" USING "btree" ("profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_closed_2025_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_closed_2025_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_01_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_01" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_02_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_02" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_03_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_03" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_04_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_04" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_05_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_05" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_06_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_06" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_07_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_07" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_08_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_08" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_09_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_09" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_10_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_10" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_11_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_11" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2022_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2022_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2022_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2022_12_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2022_12" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_01_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_01" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_02_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_02" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_03_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_03" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_04_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_04" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_05_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_05" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_06_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_06" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_07_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_07" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_08_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_08" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_09_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_09" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_10_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_10" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_11_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_11" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2023_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2023_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2023_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2023_12_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2023_12" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_01_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_01" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_02_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_02" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_03_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_03" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_04_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_04" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_05_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_05" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_06_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_06" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_07_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_07" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_08_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_08" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_09_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_09" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_10_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_10" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_11_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_11" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2024_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2024_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2024_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2024_12_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2024_12" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_01_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_01" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_01_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_01" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_01_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_01" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_01_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_01" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_02_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_02" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_02_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_02" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_02_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_02" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_02_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_02" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_03_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_03" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_03_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_03" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_03_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_03" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_03_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_03" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_04_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_04" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_04_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_04" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_04_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_04" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_04_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_04" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_05_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_05" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_05_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_05" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_05_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_05" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_05_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_05" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_06_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_06" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_06_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_06" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_06_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_06" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_06_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_06" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_07_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_07" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_07_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_07" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_07_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_07" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_07_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_07" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_08_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_08" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_08_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_08" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_08_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_08" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_08_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_08" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_09_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_09" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_09_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_09" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_09_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_09" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_09_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_09" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_10_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_10" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_10_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_10" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_10_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_10" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_10_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_10" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_11_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_11" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_11_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_11" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_11_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_11" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_11_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_11" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_12_account_id_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_12" USING "btree" ("account_id", "trade_date" DESC);



CREATE INDEX "raw_trades_open_2025_12_login_platform_broker_idx" ON "prop_trading_model"."raw_trades_open_2025_12" USING "btree" ("login", "platform", "broker");



CREATE INDEX "raw_trades_open_2025_12_std_symbol_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_12" USING "btree" ("std_symbol", "trade_date" DESC) WHERE ("std_symbol" IS NOT NULL);



CREATE INDEX "raw_trades_open_2025_12_unrealized_profit_trade_date_idx" ON "prop_trading_model"."raw_trades_open_2025_12" USING "btree" ("unrealized_profit" DESC, "trade_date" DESC);



CREATE INDEX "accounts_sub_vector_idx" ON "public"."accounts" USING "hnsw" ((("public"."sub_vector"("vector_alltime", 512))::"extensions"."vector"(512)) "extensions"."vector_ip_ops") WITH ("m"='32', "ef_construction"='400');



CREATE INDEX "idx_accounts_country_type" ON "public"."accounts" USING "btree" ("country", "type");



CREATE INDEX "idx_accounts_payouts" ON "public"."accounts" USING "btree" ("approved_payouts", "pending_payouts");



CREATE INDEX "idx_accounts_status_phase" ON "public"."accounts" USING "btree" ("status", "phase");



CREATE INDEX "idx_accounts_updated" ON "public"."accounts" USING "btree" ("updated_at" DESC);



CREATE INDEX "idx_daily_regimes_date" ON "public"."regimes_daily" USING "btree" ("date" DESC);



CREATE INDEX "idx_daily_regimes_vector_subvec" ON "public"."regimes_daily" USING "hnsw" ((("public"."sub_vector"("vector_daily_regime", 512))::"extensions"."vector"(512)) "extensions"."vector_ip_ops") WITH ("m"='32', "ef_construction"='200');



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_01_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_02_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_03_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_04_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_05_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_06_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_07_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_08_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_09_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_10_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_11_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2022_12_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_01_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_02_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_03_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_04_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_05_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_06_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_07_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_08_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_09_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_10_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_11_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2023_12_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_01_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_02_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_03_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_04_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_05_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_06_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_07_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_08_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_09_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_10_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_11_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2024_12_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_01_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_02_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_03_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_04_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_05_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_06_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_07_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_08_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_account_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09_account_id_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_date" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_profit" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09_date_net_profit_idx";



ALTER INDEX "prop_trading_model"."idx_raw_metrics_daily_login" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09_login_idx";



ALTER INDEX "prop_trading_model"."raw_metrics_daily_pkey" ATTACH PARTITION "prop_trading_model"."raw_metrics_daily_2025_09_pkey";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2022_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2023_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2024_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_closed_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_closed_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_position_login_platform_broker_tr_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_closed_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_closed_2025_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_01_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_02_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_03_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_04_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_05_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_06_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_07_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_08_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_09_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_10_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_11_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2022_12_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_01_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_02_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_03_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_04_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_05_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_06_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_07_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_08_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_09_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_10_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_11_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2023_12_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_01_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_02_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_03_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_04_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_05_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_06_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_07_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_08_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_09_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_10_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_11_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2024_12_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_01_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_02_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_03_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_04_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_05_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_06_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_07_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_08_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_09_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_10_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_11_unrealized_profit_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_account_id" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_account_id_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_login_platform_broker" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_login_platform_broker_idx";



ALTER INDEX "prop_trading_model"."raw_trades_open_pkey" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_pkey";



ALTER INDEX "prop_trading_model"."raw_trades_open_position_login_platform_broker_trade_date_key" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_position_login_platform_broker_trad_key";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_symbol" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_std_symbol_trade_date_idx";



ALTER INDEX "prop_trading_model"."idx_raw_trades_open_profit" ATTACH PARTITION "prop_trading_model"."raw_trades_open_2025_12_unrealized_profit_trade_date_idx";



CREATE OR REPLACE TRIGGER "trigger_update_status_changed_at" BEFORE UPDATE ON "public"."accounts" FOR EACH ROW EXECUTE FUNCTION "public"."update_status_changed_at"();





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "prop_trading_model" TO PUBLIC;



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";















































































































































































































































































































































































































































































































GRANT ALL ON FUNCTION "public"."analyze_account_evolution"("target_account_id" character varying, "days_back" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."analyze_account_evolution"("target_account_id" character varying, "days_back" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."analyze_account_evolution"("target_account_id" character varying, "days_back" integer) TO "service_role";












GRANT ALL ON FUNCTION "public"."update_status_changed_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_status_changed_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_status_changed_at"() TO "service_role";






























GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."feature_store_account_daily" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."feature_store_account_daily_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."model_predictions" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."model_predictions_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."model_registry" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."model_registry_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."model_training_input" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."model_training_input_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_alltime" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_plans_data" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."mv_account_performance_summary" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."mv_account_trading_patterns" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."mv_daily_trading_stats" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_regimes_daily" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."mv_market_regime_performance" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."mv_symbol_performance" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."pipeline_execution_log" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."pipeline_execution_log_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."query_performance_log" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."query_performance_log_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2022_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2023_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2024_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_daily_2025_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_metrics_hourly" TO PUBLIC;



GRANT SELECT,USAGE ON SEQUENCE "prop_trading_model"."raw_regimes_daily_id_seq" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2022_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2023_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_10" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_11" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2024_12" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_01" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_02" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_03" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_04" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_05" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_06" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_07" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_08" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_closed_2025_09" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."raw_trades_open" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."scheduled_jobs" TO PUBLIC;



GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE "prop_trading_model"."stg_accounts_daily_snapshots" TO PUBLIC;



GRANT ALL ON TABLE "public"."accounts" TO "anon";
GRANT ALL ON TABLE "public"."accounts" TO "authenticated";
GRANT ALL ON TABLE "public"."accounts" TO "service_role";



GRANT ALL ON TABLE "public"."regimes_daily" TO "anon";
GRANT ALL ON TABLE "public"."regimes_daily" TO "authenticated";
GRANT ALL ON TABLE "public"."regimes_daily" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "service_role";






























RESET ALL;
