#!/bin/bash
# scripts/deploy.sh

set -e

required_env() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "❌ $name is required for production deployment"
        exit 1
    fi
}

validate_security_env() {
    required_env SECRET_KEY
    required_env ALLOWED_HOSTS

    if [ "$SECRET_KEY" = "change-me-in-production-please" ]; then
        echo "❌ SECRET_KEY must be changed before production deployment"
        exit 1
    fi

    if [ "$ALLOWED_HOSTS" = '["*"]' ] || [ "$ALLOWED_HOSTS" = "*" ]; then
        echo "❌ ALLOWED_HOSTS must list exact production hostnames"
        exit 1
    fi

    local auth_mode="${AUTH_MODE:-trusted_proxy}"
    if [ "$auth_mode" = "trusted_proxy" ]; then
        required_env TRUSTED_PROXY_IPS
    elif [ "$auth_mode" = "local" ]; then
        if [ "${ALLOW_PRODUCTION_LOCAL_AUTH:-false}" != "true" ]; then
            echo "❌ AUTH_MODE=local in production requires ALLOW_PRODUCTION_LOCAL_AUTH=true"
            exit 1
        fi
    else
        echo "❌ AUTH_MODE must be local or trusted_proxy"
        exit 1
    fi
}

echo "🚀 Deploying Latexed Backend..."
validate_security_env

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is required but not installed"
    exit 1
fi

# Build
echo "🔨 Building Docker images..."
docker-compose -f docker-compose.prod.yml build --no-cache

# Start
echo "🏃 Starting services..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for health check
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check health
echo "🔍 Checking health..."
curl -f http://localhost:8000/api/health || {
    echo "❌ Health check failed!"
    docker-compose -f docker-compose.prod.yml logs
    exit 1
}

echo ""
echo "✅ Deployment complete!"
echo "🌐 API: http://localhost:8000"
echo "📖 Docs: http://localhost:8000/api/docs"
echo ""
echo "Useful commands:"
echo "  docker-compose -f docker-compose.prod.yml logs -f    # View logs"
echo "  docker-compose -f docker-compose.prod.yml down        # Stop services"
echo "  docker-compose -f docker-compose.prod.yml restart     # Restart services"
