#!/bin/bash

# E2EE Chat App - Stop Script
# Usage: ./stop.sh
#
# IMPORTANT: This script PRESERVES all database volumes.
# Data in PostgreSQL, Redis, MongoDB, and MinIO will persist and be available after restart.
# To completely remove volumes (wipe data), use: docker compose down -v

set -euo pipefail

COMPOSE_CMD=(docker compose -f docker-compose.yml)

if ! docker compose version >/dev/null 2>&1; then
	echo "docker compose (v2) is required but not available"
	exit 1
fi

sudo -v

echo "⛔ Stopping E2EE Chat App..."
echo "ℹ️  Database volumes are PRESERVED (data will persist across restarts)"

# Stop containers WITHOUT removing volumes
# Use 'stop' instead of 'down' to preserve named volumes
sudo "${COMPOSE_CMD[@]}" stop

# Remove orphaned containers
sudo docker ps -a --filter "name=^/e2ee_" --format '{{.ID}}' | xargs -r sudo docker rm -f 2>/dev/null || true

echo "✅ All services stopped"
echo "ℹ️  To start services again and restore data, run: ./start.sh"
echo "⚠️  To WIPE all data and volumes, run: sudo docker compose down -v"