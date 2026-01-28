#!/bin/bash

# Deploy Production Setup
# Usage: ./deploy-prod.sh

set -e

echo "=== Production Deployment ==="
echo "Building and starting production environment..."

# Load production environment
if [ ! -f .env ]; then
  echo "Error: .env not found"
  echo "Please copy .env.prod.example to .env and configure values"
  exit 1
fi

# Source environment variables
export $(cat .env | grep -v '^#' | xargs)

# Build and start
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d

echo "✓ Production deployment complete"
echo "Access at: $LABEL_STUDIO_HOST"
