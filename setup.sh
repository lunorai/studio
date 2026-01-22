#!/bin/bash
# Master setup script - runs all important commands automatically
# Usage: ./setup.sh [dev|prod|both]

set -e

ENV_MODE=${1:-both}

echo "=========================================="
echo "Lunor Studio Multi-Environment Setup"
echo "=========================================="

# Step 1: Check if .env file exists
if [ -f .env ]; then
    echo "✓ Loading .env file..."
    set -a
    source .env
    set +a
else
    echo "⚠ Warning: .env file not found. Make sure environment variables are set."
fi

# Step 2: Create Docker network if it doesn't exist
echo "✓ Checking Docker network..."
if ! docker network inspect studio-ipv6 >/dev/null 2>&1; then
    echo "  Creating studio-ipv6 network..."
    docker network create studio-ipv6
else
    echo "  Network studio-ipv6 already exists"
fi

# Step 3: Start Traefik Gateway
echo "✓ Starting Traefik Gateway..."
docker-compose -f docker-compose.gateway.yml up -d
sleep 2
echo "  Gateway started"

# Step 4: Build images (if needed)
echo "✓ Building Docker images..."
docker-compose build

# Step 5: Start instances based on mode
if [ "$ENV_MODE" = "dev" ] || [ "$ENV_MODE" = "both" ]; then
    echo ""
    echo "=========================================="
    echo "Starting DEV Instance"
    echo "=========================================="
    ./run-dev.sh
fi

if [ "$ENV_MODE" = "prod" ] || [ "$ENV_MODE" = "both" ]; then
    echo ""
    echo "=========================================="
    echo "Starting PROD Instance"
    echo "=========================================="
    ./run-prod.sh
fi

# Step 6: Show status
echo ""
echo "=========================================="
echo "Setup Complete! Status:"
echo "=========================================="
echo ""
echo "Gateway:"
docker-compose -f docker-compose.gateway.yml ps
echo ""
if [ "$ENV_MODE" = "dev" ] || [ "$ENV_MODE" = "both" ]; then
    echo "DEV Instance:"
    docker-compose -p dev ps
    echo ""
fi
if [ "$ENV_MODE" = "prod" ] || [ "$ENV_MODE" = "both" ]; then
    echo "PROD Instance:"
    docker-compose -p prod ps
    echo ""
fi

echo "=========================================="
echo "Useful Commands:"
echo "=========================================="
echo "View DEV logs:    docker-compose -p dev logs -f"
echo "View PROD logs:   docker-compose -p prod logs -f"
echo "View Gateway:     docker-compose -f docker-compose.gateway.yml logs -f"
echo "Stop DEV:         docker-compose -p dev down"
echo "Stop PROD:        docker-compose -p prod down"
echo "Stop Gateway:     docker-compose -f docker-compose.gateway.yml down"
echo ""

