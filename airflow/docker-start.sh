#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Building custom Airflow image…${NC}"
docker compose build airflow-webserver

echo -e "${GREEN}Starting Airflow & Postgres containers…${NC}"
docker compose up -d

echo -e "${YELLOW}Waiting for containers to be healthy…${NC}"
sleep 10
docker compose ps

echo -e "${GREEN}Airflow web UI →${NC} http://localhost:8080 (login: admin / admin)"