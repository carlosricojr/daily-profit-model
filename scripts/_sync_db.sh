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
LOCAL_HOST="${POSTGRES_HOST:-localhost}"
LOCAL_PORT="${POSTGRES_PORT:-5433}"
LOCAL_DB="${POSTGRES_DB:-postgres}"
LOCAL_USER="${POSTGRES_USER:-postgres}"
LOCAL_PASSWORD="${POSTGRES_PASSWORD:-dev}"

# Export production password for pg_dump
export PGPASSWORD="$PROD_PASSWORD"

echo "Starting database sync from production to local..."

# Dump production database (schema + data)
echo "Dumping production database..."
pg_dump -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" \
    --no-owner --no-acl --clean --if-exists \
    --schema=prop_trading_model \
    > /tmp/prod_dump.sql

if [ $? -ne 0 ]; then
    echo "Error: Failed to dump production database"
    exit 1
fi

# Export local password for psql
export PGPASSWORD="$LOCAL_PASSWORD"

# Restore to local database
echo "Restoring to local database..."
psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" < /tmp/prod_dump.sql

if [ $? -ne 0 ]; then
    echo "Error: Failed to restore to local database"
    exit 1
fi

# Clean up
rm /tmp/prod_dump.sql

echo "Database sync completed successfully!"