# PowerShell master setup script
# Usage: .\setup.ps1 [dev|prod|both]

param(
    [string]$Mode = "both"
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================="
Write-Host "Lunor Studio Multi-Environment Setup"
Write-Host "=========================================="

# Step 1: Load .env file if exists
if (Test-Path .env) {
    Write-Host "✓ Loading .env file..."
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} else {
    Write-Host "⚠ Warning: .env file not found. Make sure environment variables are set."
}

# Step 2: Create Docker network
Write-Host "✓ Checking Docker network..."
$networkCheck = docker network inspect studio-ipv6 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Creating studio-ipv6 network..."
    docker network create studio-ipv6
} else {
    Write-Host "  Network studio-ipv6 already exists"
}

# Step 3: Start Gateway
Write-Host "✓ Starting Traefik Gateway..."
docker-compose -f docker-compose.gateway.yml up -d
Start-Sleep -Seconds 2
Write-Host "  Gateway started"

# Step 4: Build images
Write-Host "✓ Building Docker images..."
docker-compose build

# Step 5: Start instances
if ($Mode -eq "dev" -or $Mode -eq "both") {
    Write-Host ""
    Write-Host "=========================================="
    Write-Host "Starting DEV Instance"
    Write-Host "=========================================="
    .\run-dev.ps1
}

if ($Mode -eq "prod" -or $Mode -eq "both") {
    Write-Host ""
    Write-Host "=========================================="
    Write-Host "Starting PROD Instance"
    Write-Host "=========================================="
    .\run-prod.ps1
}

# Step 6: Show status
Write-Host ""
Write-Host "=========================================="
Write-Host "Setup Complete! Status:"
Write-Host "=========================================="
Write-Host ""
Write-Host "Gateway:"
docker-compose -f docker-compose.gateway.yml ps
Write-Host ""
if ($Mode -eq "dev" -or $Mode -eq "both") {
    Write-Host "DEV Instance:"
    docker-compose -p dev ps
    Write-Host ""
}
if ($Mode -eq "prod" -or $Mode -eq "both") {
    Write-Host "PROD Instance:"
    docker-compose -p prod ps
    Write-Host ""
}

Write-Host "=========================================="
Write-Host "Useful Commands:"
Write-Host "=========================================="
Write-Host "View DEV logs:    docker-compose -p dev logs -f"
Write-Host "View PROD logs:   docker-compose -p prod logs -f"
Write-Host "View Gateway:     docker-compose -f docker-compose.gateway.yml logs -f"
Write-Host "Stop DEV:         docker-compose -p dev down"
Write-Host "Stop PROD:        docker-compose -p prod down"
Write-Host "Stop Gateway:     docker-compose -f docker-compose.gateway.yml down"
Write-Host ""

