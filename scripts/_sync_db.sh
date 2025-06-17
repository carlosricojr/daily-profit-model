#!/bin/bash

# Internal database sync script - copies production data to local dev database
# DO NOT RUN DIRECTLY - Use ./scripts/sync_local_db.sh instead

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Store production values before loading .env.local
PROD_DB_HOST="${DB_HOST}"
PROD_DB_PORT="${DB_PORT}"
PROD_DB_NAME="${DB_NAME}"
PROD_DB_USER="${DB_USER}"
PROD_DB_PASSWORD="${DB_PASSWORD}"

if [ -f .env.local ]; then
    set -a
    source .env.local
    set +a
fi

# Production database connection (use saved values from .env)
PROD_HOST="${PROD_DB_HOST}"
PROD_PORT="${PROD_DB_PORT}"
PROD_DB="${PROD_DB_NAME}"
PROD_USER="${PROD_DB_USER}"
PROD_PASSWORD="${PROD_DB_PASSWORD}"

# Local dev database connection (from .env.local)
LOCAL_HOST="${POSTGRES_HOST}"
LOCAL_PORT="${POSTGRES_PORT}"
LOCAL_DB="${POSTGRES_DB}"
LOCAL_USER="${POSTGRES_USER}"
LOCAL_PASSWORD="${POSTGRES_PASSWORD}"

# Export production password for pg_dump
export PGPASSWORD="$PROD_PASSWORD"

echo "Starting database sync from production to local..."

DUMP_FILE="/tmp/prod_dump.custom"

# Dump production database (custom compressed format)
echo "Dumping production database to $DUMP_FILE (custom format)..."
pg_dump -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" \
    --table=public.regimes_daily \
    --schema=prop_trading_model \
    -Fc \
    -f "$DUMP_FILE"

if [ $? -ne 0 ]; then
    echo "Error: Failed to dump production database"
    exit 1
fi

# Export local password for pg_restore
export PGPASSWORD="$LOCAL_PASSWORD"

# Restore to local database in parallel
echo "Restoring to local database using pg_restore (8 parallel jobs)..."

# 1. Drop dependent materialized view to avoid DROP TABLE failures
psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -c \
  "DROP MATERIALIZED VIEW IF EXISTS prop_trading_model.mv_regime_daily_features CASCADE;"

# 2. Run pg_restore. We expect "SET transaction_timeout" warnings when local
#    Postgres is older than production. These are safe to ignore, so we
#    capture pg_restore's exit code and consider it a success if the only
#    failures were those specific SET commands.

RESTORE_LOG="/tmp/pg_restore_$(date +%s).log"

set +e  # Temporarily disable exit-on-error to inspect return status
pg_restore -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" \
    --no-owner --no-acl --clean --if-exists \
    --jobs=8 \
    "$DUMP_FILE" 2>&1 | tee "$RESTORE_LOG"
PG_RESTORE_EXIT=$?
set -e

# Allow pg_restore to report errors for unknown GUCs like transaction_timeout
# but fail for any other errors. We detect this by grepping the log.
if [ $PG_RESTORE_EXIT -ne 0 ]; then
    if grep -q "unrecognized configuration parameter \"transaction_timeout\"" "$RESTORE_LOG" && \
       ! grep -q "ERROR:  " "$RESTORE_LOG" | grep -v "unrecognized configuration parameter \"transaction_timeout\""; then
        echo "Ignoring transaction_timeout warnings – restore completed with non-fatal issues."
    else
        echo "Error: Failed to restore to local database"
        exit 1
    fi
fi

# Clean up restore log
rm -f "$RESTORE_LOG"

# Clean up
rm "$DUMP_FILE"

echo "Database sync completed successfully!"