#!/bin/bash
# Script to run PROD instance
# Reads PROD_* prefixed environment variables and runs docker-compose

set -e

# Export PROD_* variables without prefix
for var in $(env | grep "^PROD_" | cut -d= -f1); do
    export_name=$(echo $var | sed 's/^PROD_//')
    export $export_name="${!var}"
done

# Set project-specific variables
export COMPOSE_PROJECT_NAME=prod
export DATA_DIR=${DATA_DIR:-./mydata-prod}
export TRAEFIK_ENABLE=true
export TRAEFIK_ROUTER_NAME=studio-prod
export TRAEFIK_HOST=${PROD_TRAEFIK_HOST:-${TRAEFIK_HOST:-prod.example.com}}

# Build and start
echo "Building PROD images..."
docker-compose build

echo "Starting PROD containers..."
docker-compose up -d

# Wait a moment for containers to start
sleep 3

# Show status
echo ""
echo "✓ PROD instance started with project name: prod"
echo "  Data directory: $DATA_DIR"
echo "  Domain: $TRAEFIK_HOST"
echo ""
echo "Container status:"
docker-compose -p prod ps
echo ""
echo "To view logs: docker-compose -p prod logs -f"
echo "To stop: docker-compose -p prod down"

