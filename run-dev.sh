#!/bin/bash
# Script to run DEV instance
# Reads DEV_* prefixed environment variables and runs docker-compose

set -e

# Export DEV_* variables without prefix
for var in $(env | grep "^DEV_" | cut -d= -f1); do
    export_name=$(echo $var | sed 's/^DEV_//')
    export $export_name="${!var}"
done

# Set project-specific variables
export COMPOSE_PROJECT_NAME=dev
export DATA_DIR=${DATA_DIR:-./mydata-dev}
export TRAEFIK_ENABLE=true
export TRAEFIK_ROUTER_NAME=studio-dev
export TRAEFIK_HOST=${DEV_TRAEFIK_HOST:-${TRAEFIK_HOST:-dev.example.com}}

# Build and start
echo "Building DEV images..."
docker-compose build

echo "Starting DEV containers..."
docker-compose up -d

# Wait a moment for containers to start
sleep 3

# Show status
echo ""
echo "✓ DEV instance started with project name: dev"
echo "  Data directory: $DATA_DIR"
echo "  Domain: $TRAEFIK_HOST"
echo ""
echo "Container status:"
docker-compose -p dev ps
echo ""
echo "To view logs: docker-compose -p dev logs -f"
echo "To stop: docker-compose -p dev down"

