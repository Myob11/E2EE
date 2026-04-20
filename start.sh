#!/bin/bash

# E2EE Chat App - Startup Script
# Usage: ./start.sh

set -e

echo "🚀 Starting E2EE Chat App..."

# Remove old containers to avoid compose bugs
echo "Cleaning up old containers..."
sudo docker-compose -f docker-compose.yml down --remove-orphans 2>/dev/null || true

echo "Removing stale E2EE containers if present..."
sudo docker ps -a --filter "name=^/e2ee_" --format '{{.ID}}' | xargs -r sudo docker rm -f 2>/dev/null || true

# Build and start
echo "Building and starting services..."
sudo docker-compose -f docker-compose.yml up -d

echo ""
echo "✅ All services are running!"
echo ""
echo "📍 Service URLs:"
echo "   API Gateway:  http://localhost:8000"
echo "   NGINX:        http://localhost"
echo "   Auth:         http://localhost:8001"
echo "   Chat:         http://localhost:8002"
echo "   Message:      http://localhost:8003"
echo "   Media:        http://localhost:8004"
echo "   MinIO:        http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "🌐 External URLs:"
echo "   HTTPS:        https://secra.top"
echo "   HTTP:         http://secra.top"
echo ""
echo "📝 Test API:"
echo "   curl https://secra.top/health"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop:      docker-compose down"