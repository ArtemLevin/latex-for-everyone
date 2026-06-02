#!/bin/bash
# scripts/deploy.sh

set -e

echo "🚀 Deploying Latexed Backend..."

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
