#!/bin/bash

# Convenient wrapper for syncing production data to local development database
# Usage: ./scripts/sync_local_db.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🔄 Database Sync Tool"
echo "===================="
echo
echo "This will sync the prop_trading_model schema from production to your local database."
echo "Data size: ~17 GB (this may take a while)"
echo
read -p "Do you want to continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Sync cancelled."
    exit 1
fi

echo
echo "Running sync..."
./scripts/_sync_db.sh

echo
echo "✅ Sync complete! Your local database now has the latest production data."