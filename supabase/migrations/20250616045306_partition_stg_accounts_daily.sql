-- Partition stg_accounts_daily_snapshots by range (snapshot_date)
BEGIN;

-- Drop the existing non-partitioned table if it exists (it should be empty)
DROP TABLE IF EXISTS prop_trading_model.stg_accounts_daily_snapshots CASCADE;

-- Re-create the parent table with the exact same structure but partitioned
CREATE TABLE prop_trading_model.stg_accounts_daily_snapshots (
    account_id VARCHAR(255) NOT NULL,
    snapshot_date DATE NOT NULL,
    login VARCHAR(255) NOT NULL,
    plan_id VARCHAR(255),
    trader_id VARCHAR(255),
    status INTEGER CHECK (status IN (1, 2, 3)),
    type INTEGER,
    phase INTEGER CHECK (phase IN (1, 2, 3, 4)),
    broker INTEGER,
    platform INTEGER,
    country VARCHAR(2),
    starting_balance DECIMAL(18, 2),
    balance DECIMAL(18, 2),
    equity DECIMAL(18, 2),
    profit_target DECIMAL(18, 2),
    profit_target_pct DECIMAL(5, 2),
    max_daily_drawdown DECIMAL(18, 2),
    max_daily_drawdown_pct DECIMAL(5, 2),
    max_drawdown DECIMAL(18, 2),
    max_drawdown_pct DECIMAL(5, 2),
    max_leverage DECIMAL(10, 2),
    is_drawdown_relative BOOLEAN,
    distance_to_profit_target DECIMAL(18, 2),
    distance_to_max_drawdown DECIMAL(18, 2),
    liquidate_friday BOOLEAN DEFAULT FALSE,
    inactivity_period INTEGER,
    daily_drawdown_by_balance_equity BOOLEAN DEFAULT FALSE,
    enable_consistency BOOLEAN DEFAULT FALSE,
    days_active INTEGER,
    days_since_last_trade INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, snapshot_date)
) PARTITION BY RANGE (snapshot_date);

-- Useful indexes on the parent (will cascade to partitions where possible)
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_account_date ON prop_trading_model.stg_accounts_daily_snapshots(account_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_date ON prop_trading_model.stg_accounts_daily_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_stg_accounts_daily_status ON prop_trading_model.stg_accounts_daily_snapshots(status) WHERE status = 1;

-- Create monthly partitions for the past 3 years and 3 months into the future
DO $$
DECLARE
    start_date date := '2024-01-01';
    partition_date date;
    partition_name text;
BEGIN
    FOR partition_date IN
        SELECT generate_series(
            start_date,
            CURRENT_DATE + interval '3 months',
            interval '1 month'
        )::date
    LOOP
        partition_name := 'stg_accounts_daily_snapshots_' || to_char(partition_date, 'YYYY_MM');

        EXECUTE format('
            CREATE TABLE IF NOT EXISTS prop_trading_model.%I PARTITION OF prop_trading_model.stg_accounts_daily_snapshots
            FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + interval '1 month'
        );
    END LOOP;
END $$;

COMMIT;
