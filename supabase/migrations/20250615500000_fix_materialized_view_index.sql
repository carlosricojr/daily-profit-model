-- Migration: Fix materialized view to support concurrent refresh
-- Created: 2025-06-15
-- Purpose: Add unique index to materialized view to enable CONCURRENTLY refresh
-- ------------------------------------------------------------

-- Drop the existing non-unique index if it exists
DROP INDEX IF EXISTS prop_trading_model.idx_mv_all_account_ids;

-- Create a UNIQUE index on the materialized view
-- This is required for REFRESH MATERIALIZED VIEW CONCURRENTLY to work
CREATE UNIQUE INDEX idx_mv_all_account_ids_unique 
ON prop_trading_model.mv_all_account_ids (account_id);

-- Also create a regular index for performance (if needed for non-unique lookups)
-- But the unique index above should be sufficient for most queries
COMMENT ON INDEX prop_trading_model.idx_mv_all_account_ids_unique IS 'Unique index required for concurrent refresh of materialized view';

-- Verify the materialized view can now be refreshed concurrently
-- This will be a no-op if the view is already up to date
REFRESH MATERIALIZED VIEW CONCURRENTLY prop_trading_model.mv_all_account_ids;

-- Add a comment to document the requirement
COMMENT ON MATERIALIZED VIEW prop_trading_model.mv_all_account_ids IS 
'Materialized view of all unique account_ids across all tables. 
Requires unique index on account_id for concurrent refresh support.';