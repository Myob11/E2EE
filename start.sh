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

# Start postgres first and ensure auth database exists.
echo "Starting PostgreSQL first..."
sudo docker-compose -f docker-compose.yml up -d postgres

echo "Waiting for PostgreSQL to become ready..."
for i in {1..30}; do
	if sudo docker-compose -f docker-compose.yml exec -T postgres pg_isready -U postgres -d postgres >/dev/null 2>&1; then
		break
	fi

	if [ "$i" -eq 30 ]; then
		echo "❌ PostgreSQL did not become ready in time"
		exit 1
	fi

	sleep 2
done

echo "Ensuring auth_db exists (idempotent)..."
printf "%s\n" \
	"SELECT 'CREATE DATABASE auth_db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth_db');" \
	"\\gexec" | sudo docker-compose -f docker-compose.yml exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1

# Build and start the rest.
echo "Building and starting remaining services..."
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