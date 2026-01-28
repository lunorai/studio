# Separate Dev & Prod Deployment Guide

## Overview
This setup allows independent deployment of dev and prod environments from separate clones.

## Directory Structure

### Option 1: Separate Clones (Recommended)

```
/lunor_studio_prod/       # Production clone
├── docker-compose.prod.yml
├── .env.prod
├── deploy/
├── label_studio/
└── ... (full repo)

/lunor_studio_dev/        # Development clone
├── docker-compose.dev.yml
├── .env.dev
├── deploy/
├── label_studio/
└── ... (full repo)
```

## Deployment Instructions

### Production Deployment (Separate Clone)

1. Clone in production directory:
```bash
git clone <repo> /path/to/lunor_studio_prod
cd /path/to/lunor_studio_prod
```

2. Configure environment:
```bash
cp .env.prod.example .env.prod
# Edit .env.prod with production values
nano .env.prod
```

3. Deploy:
```bash
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

### Development Deployment (Separate Clone)

1. Clone in development directory:
```bash
git clone <repo> /path/to/lunor_studio_dev
cd /path/to/lunor_studio_dev
```

2. Configure environment:
```bash
cp .env.dev.example .env.dev
# Edit .env.dev with development values
nano .env.dev
```

3. Deploy:
```bash
docker-compose -f docker-compose.dev.yml build
docker-compose -f docker-compose.dev.yml up -d
```

## Key Differences

| Aspect | Development | Production |
|--------|-------------|-----------|
| **Compose File** | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
| **Environment** | `.env.dev` | `.env.prod` |
| **Container Names** | `studio_proxy_dev`, `studio_app_dev` | `studio_proxy_prod`, `studio_app_prod` |
| **Proxy Ports** | 8080:80, 8443:443 | 80:80, 443:443 |
| **Network** | `studio-dev` | `studio-prod` |
| **Image Tag** | `ghcr.io/lunorai/studio:dev` | `ghcr.io/lunorai/studio:main` |

## Managing Deployments

### View logs (from respective directory):
```bash
# Production
docker-compose -f docker-compose.prod.yml logs -f app

# Development
docker-compose -f docker-compose.dev.yml logs -f app
```

### Stop deployment:
```bash
# Production
docker-compose -f docker-compose.prod.yml down

# Development
docker-compose -f docker-compose.dev.yml down
```

### Restart service:
```bash
# Production
docker-compose -f docker-compose.prod.yml restart app

# Development
docker-compose -f docker-compose.dev.yml restart app
```

## Notes

- Each clone is independent with its own `.env` file and data directory
- Separate container names prevent conflicts
- Separate networks (`studio-dev` and `studio-prod`) ensure isolation
- Ports are different (8080 for dev, 80 for prod) to avoid conflicts if run on same server
- Update the environment files with your actual configuration values before deploying

