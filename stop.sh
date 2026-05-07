#!/bin/bash

# E2EE Chat App - Stop Script
# Usage: ./stop.sh
#
# IMPORTANT: This script PRESERVES all database volumes.
# Data in PostgreSQL, Redis, MongoDB, and MinIO will persist and be available after restart.
# To completely remove volumes (wipe data), use: docker compose down -v

set -euo pipefail

COMPOSE_CMD=(docker compose -f docker-compose.yml)

# Check prerequisites
if ! docker compose version >/dev/null 2>&1; then
	echo "❌ docker compose (v2) is required but not available"
	exit 1
fi

# Load environment variables to show which credentials are in use
if [ -f .env ]; then
	set -a
	source .env
	set +a
fi

sudo -v

echo "⛔ Stopping E2EE Chat App..."
echo "ℹ️  Database volumes are PRESERVED (data will persist across restarts)"

# Show database status before stopping
echo ""
echo "📊 Current Database Status (before stopping):"
sudo "${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-postgres}" -d auth_db -c "SELECT 'Users' as table_name, count(*) as count FROM users UNION ALL SELECT 'Friends', count(*) FROM friends UNION ALL SELECT 'Devices', count(*) FROM devices;" 2>/dev/null || echo "   (Database not accessible)"
echo ""

# Stop containers WITHOUT removing volumes
# Use 'stop' instead of 'down' to preserve named volumes
sudo "${COMPOSE_CMD[@]}" stop

# Remove orphaned containers
sudo docker ps -a --filter "name=^/e2ee_" --format '{{.ID}}' | xargs -r sudo docker rm -f 2>/dev/null || true

echo "✅ All services stopped"
echo "ℹ️  To start services again and restore data, run: ./start.sh"
echo "⚠️  To WIPE all data and volumes, run: sudo docker compose down -v"
echo ""
echo "💾 Data Persistence:"
echo "   - PostgreSQL data:    $(sudo docker volume ls | grep e2ee_postgres_data | awk '{print $2}')"
echo "   - Redis data:         $(sudo docker volume ls | grep e2ee_redis_data | awk '{print $2}')"
echo "   - MongoDB data:       $(sudo docker volume ls | grep e2ee_mongodb_data | awk '{print $2}')"
echo "   - MinIO data:         $(sudo docker volume ls | grep e2ee_minio_data | awk '{print $2}')"
echo ""