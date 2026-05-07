#!/bin/bash

# E2EE Chat App - Stop Script
# Usage: ./stop.sh
#
# IMPORTANT: This script PRESERVES all database volumes.
# Data in PostgreSQL, MongoDB, and MinIO will persist and be available after restart.
# To completely remove volumes (wipe data), use: docker compose down -v

set -euo pipefail

COMPOSE_CMD=(docker compose -f docker-compose.yml)

# If the user is in the docker group, avoid sudo
if groups "$(whoami)" | grep -q '\bdocker\b'; then
	SUDO=""
else
	SUDO="sudo"
fi

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

	${SUDO} -v || true

echo "⛔ Stopping E2EE Chat App..."
echo "ℹ️  Database volumes are PRESERVED (data will persist across restarts)"

# Show database status before stopping
echo ""
echo "📊 Current Database Status (before stopping):"
${SUDO} "${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-postgres}" -d auth_db -c "SELECT 'Users' as table_name, count(*) as count FROM users UNION ALL SELECT 'Friends', count(*) FROM friends UNION ALL SELECT 'Devices', count(*) FROM devices;" 2>/dev/null || echo "   (Database not accessible)"
echo ""

# Stop containers WITHOUT removing volumes
# Use 'stop' instead of 'down' to preserve named volumes
${SUDO} "${COMPOSE_CMD[@]}" stop

# Remove orphaned containers
sudo docker ps -a --filter "name=^/e2ee_" --format '{{.ID}}' | xargs -r sudo docker rm -f 2>/dev/null || true

echo "✅ All services stopped"
echo "ℹ️  To start services again and restore data, run: ./start.sh"
echo "⚠️  To WIPE all data and volumes, run: sudo docker compose down -v"
echo ""
echo "💾 Data Persistence (named volumes):"
${SUDO} docker volume ls --format '  - {{.Name}}' || true
echo ""