# PowerShell script to run DEV instance
# Reads DEV_* prefixed environment variables and runs docker-compose

$ErrorActionPreference = "Stop"

# Export DEV_* variables without prefix
Get-ChildItem Env: | Where-Object { $_.Name -like "DEV_*" } | ForEach-Object {
    $varName = $_.Name
    $varValue = $_.Value
    $exportName = $varName -replace "^DEV_", ""
    [Environment]::SetEnvironmentVariable($exportName, $varValue, "Process")
}

# Set project-specific variables
$env:COMPOSE_PROJECT_NAME = "dev"
if (-not $env:DATA_DIR) {
    $env:DATA_DIR = "./mydata-dev"
}
$env:TRAEFIK_ENABLE = "true"
$env:TRAEFIK_ROUTER_NAME = "studio-dev"
if ($env:DEV_TRAEFIK_HOST) {
    $env:TRAEFIK_HOST = $env:DEV_TRAEFIK_HOST
} elseif (-not $env:TRAEFIK_HOST) {
    # Set to your DEV domain (hostname only), e.g. dev.example.com
    $env:TRAEFIK_HOST = "dev.example.com"
}

# Build and start
Write-Host "Building DEV images..."
docker-compose build

Write-Host "Starting DEV containers..."
docker-compose up -d

# Wait a moment for containers to start
Start-Sleep -Seconds 3

# Show status
Write-Host ""
Write-Host "✓ DEV instance started with project name: dev"
Write-Host "  Data directory: $env:DATA_DIR"
Write-Host "  Domain: $env:TRAEFIK_HOST"
Write-Host ""
Write-Host "Container status:"
docker-compose -p dev ps
Write-Host ""
Write-Host "To view logs: docker-compose -p dev logs -f"
Write-Host "To stop: docker-compose -p dev down"

