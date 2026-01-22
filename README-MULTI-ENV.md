# Running Multiple Instances (DEV and PROD)

This setup allows you to run both DEV and PROD instances simultaneously using the same `docker-compose.yml` file with environment variables prefixed with `DEV_` or `PROD_`.

## Prerequisites

- Docker and Docker Compose installed
- Environment variables set with `DEV_` or `PROD_` prefixes
- External network `studio-ipv6` created (automatically created by setup script)

## Quick Start (Automated Setup)

### Option 1: Automated Setup Script (Recommended)

**On Linux/Mac:**
```bash
# 1. Create .env file with your variables (see below)
nano .env

# 2. Make scripts executable
chmod +x setup.sh run-dev.sh run-prod.sh

# 3. Run automated setup (does everything!)
./setup.sh both

# Or start just one:
./setup.sh dev   # Only DEV
./setup.sh prod  # Only PROD
```

**On Windows (PowerShell):**
```powershell
# 1. Create .env file with your variables (see below)
# 2. Run automated setup
.\setup.ps1 both

# Or start just one:
.\setup.ps1 dev   # Only DEV
.\setup.ps1 prod  # Only PROD
```

The setup script automatically:
- ✅ Loads `.env` file
- ✅ Creates Docker network (`studio-ipv6`)
- ✅ Starts Traefik gateway
- ✅ Builds Docker images
- ✅ Starts DEV and/or PROD instances
- ✅ Shows container status

### Option 2: Manual Setup

#### 1. Create .env File

Create a `.env` file in the project root:

```bash
# DEV Environment Variables
DEV_LABEL_STUDIO_HOST=https://dev.yourdomain.com
DEV_POSTGRE_PASSWORD=dev_password
DEV_POSTGRE_HOST=dev_db_host
DEV_POSTGRE_PORT=5432
DEV_DJANGO_DB=default
DEV_LUNOR_JWT_SECRET=dev_jwt_secret
DEV_GRAPHQL_ENDPOINT=https://dev-graphql.yourdomain.com
DEV_LUNOR_QUEST_URL=https://dev-quest.yourdomain.com
DEV_TRAEFIK_HOST=dev.yourdomain.com

# PROD Environment Variables
PROD_LABEL_STUDIO_HOST=https://prod.yourdomain.com
PROD_POSTGRE_PASSWORD=prod_password
PROD_POSTGRE_HOST=prod_db_host
PROD_POSTGRE_PORT=5432
PROD_DJANGO_DB=default
PROD_LUNOR_JWT_SECRET=prod_jwt_secret
PROD_GRAPHQL_ENDPOINT=https://prod-graphql.yourdomain.com
PROD_LUNOR_QUEST_URL=https://prod-quest.yourdomain.com
PROD_TRAEFIK_HOST=prod.yourdomain.com
```

#### 2. Run Instances

**On Linux/Mac:**
```bash
# Make scripts executable
chmod +x run-dev.sh run-prod.sh

# Run DEV instance (automatically builds and starts)
./run-dev.sh

# Run PROD instance (automatically builds and starts)
./run-prod.sh
```

**On Windows (PowerShell):**
```powershell
# Run DEV instance (automatically builds and starts)
.\run-dev.ps1

# Run PROD instance (automatically builds and starts)
.\run-prod.ps1
```

### 3. Manual Method (Alternative)

If you prefer to run manually without scripts:

**For DEV:**
```bash
# Load .env file
set -a && source .env && set +a

# Export DEV_* variables without prefix
for var in $(env | grep "^DEV_" | cut -d= -f1); do
    export_name=$(echo $var | sed 's/^DEV_//')
    export $export_name="${!var}"
done

export COMPOSE_PROJECT_NAME=dev
export DATA_DIR=./mydata-dev
export TRAEFIK_ENABLE=true
export TRAEFIK_ROUTER_NAME=studio-dev
export TRAEFIK_HOST=dev.yourdomain.com

# Build and start
docker-compose build
docker-compose up -d
```

**For PROD:**
```bash
# Load .env file
set -a && source .env && set +a

# Export PROD_* variables without prefix
for var in $(env | grep "^PROD_" | cut -d= -f1); do
    export_name=$(echo $var | sed 's/^PROD_//')
    export $export_name="${!var}"
done

export COMPOSE_PROJECT_NAME=prod
export DATA_DIR=./mydata-prod
export TRAEFIK_ENABLE=true
export TRAEFIK_ROUTER_NAME=studio-prod
export TRAEFIK_HOST=prod.yourdomain.com

# Build and start
docker-compose build
docker-compose up -d
```

## Management Commands

### View Logs

```bash
# DEV logs
docker-compose -p dev logs -f

# PROD logs
docker-compose -p prod logs -f
```

### Stop Instances

```bash
# Stop DEV
docker-compose -p dev down

# Stop PROD
docker-compose -p prod down

# Stop both
docker-compose -p dev down && docker-compose -p prod down
```

### Restart Instances

```bash
# Restart DEV
docker-compose -p dev restart

# Restart PROD
docker-compose -p prod restart
```

### Check Status

```bash
# Check DEV status
docker-compose -p dev ps

# Check PROD status
docker-compose -p prod ps
```

## Important Notes

1. **Automated Setup**: The `setup.sh` / `setup.ps1` script handles everything automatically:
   - Network creation
   - Gateway startup
   - Image building
   - Container startup
   - Status display

2. **Auto-Build**: The `run-dev.sh` and `run-prod.sh` scripts automatically build images before starting containers.

3. **No Port Conflicts**: Port mappings are removed from the compose file. Both instances will be accessible via their respective domains through Traefik gateway.

4. **Separate Data Directories**: 
   - DEV uses: `./mydata-dev`
   - PROD uses: `./mydata-prod`
   - You can override by setting `DATA_DIR` environment variable

5. **Container Names**: 
   - DEV containers: `dev-nginx`, `dev-app`
   - PROD containers: `prod-nginx`, `prod-app`

6. **Network**: Both instances use the external `studio-ipv6` network (created automatically by setup script).

7. **SSL Certificates**: Place SSL certificates in:
   - `./deploy/nginx/certs/` (cert.pem and cert.key)
   
   If you need separate certificates, you can override the volume mapping per instance.

8. **Database Migrations**: Automatically run on container startup via entrypoint scripts - no manual migration needed!

## Reverse Proxy Configuration

Since both instances don't expose ports, you need **one reverse proxy on the VM** that binds `80/443` and routes traffic based on domains.

### Option A (recommended): Traefik gateway (included)

1) Start the gateway once:

```bash
docker-compose -f docker-compose.gateway.yml up -d
```

2) For each stack (DEV/PROD), set these env vars (the scripts already set defaults):

- `TRAEFIK_ENABLE=true`
- `TRAEFIK_ROUTER_NAME=studio-dev` (or `studio-prod`)
- `TRAEFIK_HOST=dev.yourdomain.com` (or `prod.yourdomain.com`)  **hostname only**

Traefik will route:
- `dev.yourdomain.com` → `dev-nginx:8085`
- `prod.yourdomain.com` → `prod-nginx:8085`

**Example Nginx Configuration:**
```nginx
# DEV instance
server {
    listen 80;
    server_name dev.yourdomain.com;
    
    location / {
        proxy_pass http://dev-nginx:8085;
        # ... other proxy settings
    }
}

# PROD instance
server {
    listen 80;
    server_name prod.yourdomain.com;
    
    location / {
        proxy_pass http://prod-nginx:8085;
        # ... other proxy settings
    }
}
```

## Troubleshooting

1. **Network not found**: Create the network: `docker network create studio-ipv6`

2. **Port conflicts**: Make sure no other services are using ports 80/443. The compose file doesn't expose ports, but check your reverse proxy.

3. **Container name conflicts**: Each instance uses different project names (`dev` and `prod`), so containers won't conflict.

4. **Data directory issues**: Ensure the data directories exist or Docker will create them automatically.

