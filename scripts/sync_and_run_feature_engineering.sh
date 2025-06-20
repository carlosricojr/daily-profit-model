#!/bin/bash

# Script to sync local database and then run feature engineering
# Usage: ./scripts/sync_and_run_feature_engineering.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🔄 Database Sync & Feature Engineering Pipeline"
echo "=============================================="
echo

# Step 1: Run database sync
echo "Step 1: Syncing database from production..."
echo "==========================================="
./scripts/sync_local_db.sh

if [ $? -ne 0 ]; then
    echo "❌ Database sync failed. Exiting."
    exit 1
fi

echo
echo "✅ Database sync completed successfully!"
echo

# Step 2: Run feature engineering orchestration
echo "Step 2: Running feature engineering pipeline..."
echo "=============================================="
uv run --env-file .env.local -- python -m src.feature_engineering.orchestrate_feature_engineering

if [ $? -ne 0 ]; then
    echo "❌ Feature engineering pipeline failed. Exiting."
    exit 1
fi

echo
echo "✅ Complete! Database synced and feature engineering pipeline finished successfully."