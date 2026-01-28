#!/bin/bash

# Deploy Development Setup
# Usage: ./deploy-dev.sh

set -e

echo "=== Development Deployment ==="
echo "Building and starting development environment..."

# Load development environment
if [ ! -f .env ]; then
  echo "Error: .env not found"
  echo "Please copy .env.dev.example to .env and configure values"
  exit 1
fi

# Source environment variables
export $(cat .env | grep -v '^#' | xargs)

# Build and start
docker-compose -f docker-compose.dev.yml build
docker-compose -f docker-compose.dev.yml up -d

echo "✓ Development deployment complete"
echo "Access at: $LABEL_STUDIO_HOST"
