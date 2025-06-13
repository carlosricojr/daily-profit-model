#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Airflow deployment...${NC}"

# Check if parent .env file exists
if [ ! -f ../.env ]; then
    echo -e "${RED}ERROR: Parent .env file not found!${NC}"
    echo "Please ensure ../.env exists with your database credentials."
    exit 1
fi

# Load environment variables from parent .env
set -a
source ../.env
set +a

# Get current user ID
CURRENT_UID=$(id -u)
echo -e "${YELLOW}Setting AIRFLOW_UID to ${CURRENT_UID}${NC}"
export AIRFLOW_UID=${CURRENT_UID}

# Create local .env if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating local .env file...${NC}"
    echo "AIRFLOW_UID=${CURRENT_UID}" > .env
else
    # Update .env with correct UID if needed
    sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=${CURRENT_UID}/" .env
fi

# Initialize the database (only needed first time)
echo -e "${GREEN}Initializing Airflow database...${NC}"
docker compose up airflow-init

# Start all services
echo -e "${GREEN}Starting Airflow services...${NC}"
docker compose up -d

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to become healthy...${NC}"
sleep 10

# Check service status
docker compose ps

echo -e "${GREEN}Airflow is starting up!${NC}"
echo -e "Web UI will be available at: ${YELLOW}http://localhost:8080${NC}"
echo -e "Default credentials: ${YELLOW}admin/admin${NC}"
echo ""
echo -e "${GREEN}Useful commands:${NC}"
echo "  View logs:        docker compose logs -f"
echo "  Stop services:    docker compose down"
echo "  Restart services: docker compose restart"
echo "  Run CLI command:  docker compose run --rm airflow-cli <command>"