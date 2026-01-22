# PowerShell script to run PROD instance
# Reads PROD_* prefixed environment variables and runs docker-compose

$ErrorActionPreference = "Stop"

# Export PROD_* variables without prefix
Get-ChildItem Env: | Where-Object { $_.Name -like "PROD_*" } | ForEach-Object {
    $varName = $_.Name
    $varValue = $_.Value
    $exportName = $varName -replace "^PROD_", ""
    [Environment]::SetEnvironmentVariable($exportName, $varValue, "Process")
}

# Set project-specific variables
$env:COMPOSE_PROJECT_NAME = "prod"
if (-not $env:DATA_DIR) {
    $env:DATA_DIR = "./mydata-prod"
}
$env:TRAEFIK_ENABLE = "true"
$env:TRAEFIK_ROUTER_NAME = "studio-prod"
if ($env:PROD_TRAEFIK_HOST) {
    $env:TRAEFIK_HOST = $env:PROD_TRAEFIK_HOST
} elseif (-not $env:TRAEFIK_HOST) {
    # Set to your PROD domain (hostname only), e.g. prod.example.com
    $env:TRAEFIK_HOST = "prod.example.com"
}

# Build and start
Write-Host "Building PROD images..."
docker-compose build

Write-Host "Starting PROD containers..."
docker-compose up -d

# Wait a moment for containers to start
Start-Sleep -Seconds 3

# Show status
Write-Host ""
Write-Host "✓ PROD instance started with project name: prod"
Write-Host "  Data directory: $env:DATA_DIR"
Write-Host "  Domain: $env:TRAEFIK_HOST"
Write-Host ""
Write-Host "Container status:"
docker-compose -p prod ps
Write-Host ""
Write-Host "To view logs: docker-compose -p prod logs -f"
Write-Host "To stop: docker-compose -p prod down"

