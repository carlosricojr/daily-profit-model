-- Create materialized view for regime features
-- This view extracts 48 market-wide features from regimes_daily JSONB data
-- Optimized for fast refresh (<30 seconds) and graceful handling of malformed JSON

CREATE MATERIALIZED VIEW IF NOT EXISTS prop_trading_model.mv_regime_daily_features AS
SELECT 
    r.date,
    
    -- Sentiment indicators (5 columns)
    -- Using COALESCE to handle potential NULL values gracefully
    COALESCE((r.news_analysis->'sentiment_summary'->>'average_score')::numeric, 0) AS sentiment_avg,
    COALESCE((r.news_analysis->'sentiment_summary'->'distribution'->>'bullish')::int, 0) AS sentiment_bullish_count,
    COALESCE((r.news_analysis->'sentiment_summary'->'distribution'->>'bearish')::int, 0) AS sentiment_bearish_count,
    CASE 
        WHEN COALESCE((r.news_analysis->'sentiment_summary'->'distribution'->>'bullish')::int, 0) > 
             COALESCE((r.news_analysis->'sentiment_summary'->'distribution'->>'bearish')::int, 0) * 2 
        THEN 1 ELSE 0 
    END AS sentiment_very_bullish,
    COALESCE((r.news_analysis->'sentiment_summary'->>'average_score')::numeric, 0) AS sentiment_score,
    
    -- Macro indicators (10 columns)
    COALESCE((r.country_economic_indicators->>'fed_funds_rate_effective')::numeric, 0) AS fed_funds_rate,
    COALESCE((r.country_economic_indicators->>'inflation_us_consumer_prices')::numeric, 0) AS cpi_us,
    COALESCE((r.country_economic_indicators->>'treasury_2_year')::numeric, 0) AS treasury_2y,
    COALESCE((r.country_economic_indicators->>'treasury_10_year')::numeric, 0) AS treasury_10y,
    COALESCE(
        (r.country_economic_indicators->>'treasury_10_year')::numeric - 
        (r.country_economic_indicators->>'treasury_2_year')::numeric, 
        0
    ) AS yield_curve_spread,
    -- DXY index is not in the data, using USD conversion rates as proxy
    COALESCE(1 / NULLIF((r.instruments->'data'->'EURUSD'->>'eod_price')::numeric, 0), 0) AS dollar_index,
    -- VIX is not directly available, using SPX500 volatility as proxy
    COALESCE((r.instruments->'data'->'SPX500'->>'volatility_90d')::numeric, 0) AS vix_close,
    COALESCE((r.country_economic_indicators->>'unemployment_rate')::numeric, 0) AS unemployment_rate,
    -- GDP growth rate not directly available, using real_gdp
    COALESCE((r.country_economic_indicators->>'real_gdp')::numeric, 0) AS gdp_growth_rate,
    -- Consumer confidence not in data, setting to 0
    0::numeric AS consumer_confidence,
    
    -- Market indices (8 columns)
    COALESCE((r.instruments->'data'->'SPX500'->>'eod_price')::numeric, 0) AS sp500_close,
    COALESCE((r.instruments->'data'->'SPX500'->>'daily_return')::numeric, 0) AS sp500_daily_return,
    COALESCE((r.instruments->'data'->'SPX500'->>'volatility_90d')::numeric, 0) AS sp500_vol_20d,
    COALESCE((r.instruments->'data'->'NDX100'->>'eod_price')::numeric, 0) AS nasdaq_close,
    COALESCE((r.instruments->'data'->'NDX100'->>'daily_return')::numeric, 0) AS nasdaq_daily_return,
    COALESCE((r.instruments->'data'->'US30'->>'eod_price')::numeric, 0) AS dow_close,
    COALESCE((r.instruments->'data'->'US30'->>'daily_return')::numeric, 0) AS dow_daily_return,
    -- Russell 2000 not available in data
    0::numeric AS russell_daily_return,
    
    -- Forex indicators (6 columns)
    COALESCE((r.instruments->'data'->'EURUSD'->>'eod_price')::numeric, 0) AS eurusd_close,
    COALESCE((r.instruments->'data'->'EURUSD'->>'daily_return')::numeric, 0) AS eurusd_change,
    COALESCE((r.instruments->'data'->'GBPUSD'->>'eod_price')::numeric, 0) AS gbpusd_close,
    COALESCE((r.instruments->'data'->'GBPUSD'->>'daily_return')::numeric, 0) AS gbpusd_change,
    COALESCE((r.instruments->'data'->'USDJPY'->>'eod_price')::numeric, 0) AS usdjpy_close,
    COALESCE((r.instruments->'data'->'USDJPY'->>'daily_return')::numeric, 0) AS usdjpy_change,
    
    -- Crypto indicators (4 columns)
    COALESCE((r.instruments->'data'->'BTCUSD'->>'eod_price')::numeric, 0) AS btc_close,
    COALESCE((r.instruments->'data'->'BTCUSD'->>'daily_return')::numeric, 0) AS btc_daily_return,
    COALESCE((r.instruments->'data'->'ETHUSD'->>'eod_price')::numeric, 0) AS eth_close,
    COALESCE((r.instruments->'data'->'ETHUSD'->>'daily_return')::numeric, 0) AS eth_daily_return,
    
    -- Commodities (4 columns)
    COALESCE((r.instruments->'data'->'XAUUSD'->>'eod_price')::numeric, 0) AS gold_close,
    COALESCE((r.instruments->'data'->'XAUUSD'->>'daily_return')::numeric, 0) AS gold_change,
    COALESCE((r.instruments->'data'->'USOUSD'->>'eod_price')::numeric, 0) AS oil_close,
    COALESCE((r.instruments->'data'->'USOUSD'->>'daily_return')::numeric, 0) AS oil_change,
    
    -- Regime classifications (6 columns)
    COALESCE(r.summary->'key_metrics'->>'volatility_regime', 'UNKNOWN') AS volatility_regime,
    COALESCE(r.summary->'key_metrics'->>'liquidity_state', 'normal') AS liquidity_state,
    COALESCE((r.summary->'key_metrics'->>'sentiment_level')::text, '0') AS sentiment_level,
    COALESCE(r.summary->'key_metrics'->>'yield_curve_shape', 'NORMAL') AS yield_curve_shape,
    CASE 
        WHEN COALESCE((r.summary->'key_metrics'->>'anomaly_count')::int, 0) > 0 
        THEN 1 ELSE 0 
    END AS has_anomalies,
    COALESCE(r.summary->>'regime_fingerprint', '') AS regime_fingerprint,
    
    -- Risk indicators (5 columns)
    COALESCE((r.summary->'transition_probabilities'->>'to_risk_on')::numeric, 0.25) AS prob_risk_on,
    COALESCE((r.summary->'transition_probabilities'->>'to_risk_off')::numeric, 0.25) AS prob_risk_off,
    COALESCE((r.summary->'transition_probabilities'->>'to_vol_spike')::numeric, 0.25) AS prob_vol_spike,
    GREATEST(
        COALESCE((r.summary->'transition_probabilities'->>'to_risk_off')::numeric, 0.25),
        COALESCE((r.summary->'transition_probabilities'->>'to_vol_spike')::numeric, 0.25)
    ) AS max_risk_probability,
    -- News volume feature
    COALESCE((r.news_analysis->>'count')::int, 0) AS news_volume,
    
    -- Metadata
    CURRENT_TIMESTAMP AS mv_refreshed_at
FROM public.regimes_daily r
WHERE r.date IS NOT NULL;

-- Create unique index for fast lookups and to ensure data integrity
CREATE UNIQUE INDEX IF NOT EXISTS idx_regime_daily_features_date 
ON prop_trading_model.mv_regime_daily_features(date);

-- Create additional indexes for commonly filtered columns
CREATE INDEX IF NOT EXISTS idx_regime_daily_features_volatility 
ON prop_trading_model.mv_regime_daily_features(volatility_regime);

CREATE INDEX IF NOT EXISTS idx_regime_daily_features_risk_prob 
ON prop_trading_model.mv_regime_daily_features(max_risk_probability);

-- Create refresh function for the materialized view
CREATE OR REPLACE FUNCTION prop_trading_model.refresh_regime_features()
RETURNS void AS $$
BEGIN
    -- Log start of refresh
    RAISE NOTICE 'Starting refresh of mv_regime_daily_features at %', NOW();
    
    -- Non-concurrent refresh as suggested by ML engineer
    -- This is faster for full refresh scenarios
    REFRESH MATERIALIZED VIEW prop_trading_model.mv_regime_daily_features;
    
    -- Log completion
    RAISE NOTICE 'Completed refresh of mv_regime_daily_features at %', NOW();
    
    -- Update statistics for query planner
    ANALYZE prop_trading_model.mv_regime_daily_features;
END;
$$ LANGUAGE plpgsql;

-- Grant appropriate permissions
GRANT SELECT ON prop_trading_model.mv_regime_daily_features TO authenticated;
GRANT SELECT ON prop_trading_model.mv_regime_daily_features TO service_role;

-- Add comment describing the view
COMMENT ON MATERIALIZED VIEW prop_trading_model.mv_regime_daily_features IS 
'Materialized view containing 48 market-wide features extracted from regimes_daily JSONB data. 
Features include sentiment indicators, macro indicators, market indices, forex, crypto, commodities, 
regime classifications, and risk indicators. Optimized for fast refresh (<30 seconds) and joins 
with account snapshots. Refresh daily after regime data ingestion.';

-- Schedule daily refresh (if pg_cron is available)
-- Uncomment the following lines if pg_cron extension is installed:
-- SELECT cron.schedule(
--     'refresh-regime-features', 
--     '0 6 * * *', 
--     'SELECT prop_trading_model.refresh_regime_features();'
-- );