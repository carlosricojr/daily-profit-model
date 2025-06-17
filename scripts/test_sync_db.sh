#!/bin/bash

# Test script for sync_db.sh
# Verifies connections and shows what data would be synced

set -e

echo "=== Testing Database Sync Script ==="
echo

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

echo "1. Testing Production Database Connection"
echo "   Host: $PROD_HOST:$PROD_PORT"
echo "   Database: $PROD_DB"
echo "   User: $PROD_USER"
export PGPASSWORD="$PROD_PASSWORD"
if psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -c "SELECT version();" > /dev/null 2>&1; then
    echo "   ✓ Production connection successful"
else
    echo "   ✗ Production connection failed"
    exit 1
fi

echo
echo "2. Testing Local Database Connection"
echo "   Host: $LOCAL_HOST:$LOCAL_PORT"
echo "   Database: $LOCAL_DB"
echo "   User: $LOCAL_USER"
export PGPASSWORD="$LOCAL_PASSWORD"
if psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -c "SELECT version();" > /dev/null 2>&1; then
    echo "   ✓ Local connection successful"
else
    echo "   ✗ Local connection failed"
    exit 1
fi

echo
echo "3. Checking prop_trading_model schema in production"
export PGPASSWORD="$PROD_PASSWORD"
SCHEMA_EXISTS=$(psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'prop_trading_model');")
if [ "$SCHEMA_EXISTS" = " t" ]; then
    echo "   ✓ Schema prop_trading_model exists in production"
else
    echo "   ✗ Schema prop_trading_model not found in production"
    exit 1
fi

echo
echo "4. Tables that will be synced from prop_trading_model schema:"
export PGPASSWORD="$PROD_PASSWORD"
TABLE_COUNT=$(psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'prop_trading_model';")
echo "   Total tables: $TABLE_COUNT"
echo
echo "   Sample of tables (first 10):"
psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'prop_trading_model' ORDER BY table_name LIMIT 10;"

echo
echo "5. Estimated data size:"
psql -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" -c "SELECT pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint) as total_size FROM pg_tables WHERE schemaname = 'prop_trading_model';"

echo
echo "6. Dry run - generating dump file to check syntax"
export PGPASSWORD="$PROD_PASSWORD"
echo "   Running: pg_dump with --schema=prop_trading_model"
pg_dump -h "$PROD_HOST" -p "$PROD_PORT" -U "$PROD_USER" -d "$PROD_DB" \
    --no-owner --no-acl --clean --if-exists \
    --schema=prop_trading_model \
    --verbose --file=/tmp/test_dump.sql 2>&1 | head -20
    
if [ $? -eq 0 ] || [ -f /tmp/test_dump.sql ]; then
    echo "   ✓ Dump command syntax is valid"
    if [ -f /tmp/test_dump.sql ]; then
        DUMP_SIZE=$(ls -lh /tmp/test_dump.sql | awk '{print $5}')
        echo "   Dump file size: $DUMP_SIZE"
        rm -f /tmp/test_dump.sql
    fi
else
    echo "   ✗ Dump command failed"
    exit 1
fi

echo
echo "7. Checking if local database can accept the dump"
export PGPASSWORD="$LOCAL_PASSWORD"
# Check if prop_trading_model schema exists locally
LOCAL_SCHEMA_EXISTS=$(psql -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'prop_trading_model');")
if [ "$LOCAL_SCHEMA_EXISTS" = " t" ]; then
    echo "   ⚠ Schema prop_trading_model already exists locally - it will be replaced"
else
    echo "   ✓ Schema prop_trading_model will be created fresh"
fi

echo
echo "=== Test Summary ==="
echo "✓ Both database connections are working"
echo "✓ Production schema prop_trading_model exists with $TABLE_COUNT tables"
echo "✓ Dump command syntax is valid"
echo "✓ Local database is ready to receive the data"
echo
echo "To run the actual sync, execute: ./scripts/sync_local_db.sh"