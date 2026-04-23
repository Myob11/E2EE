#!/bin/bash

# E2EE Chat App - Stop Script
# Usage: ./stop.sh

set -euo pipefail

COMPOSE_CMD=(docker compose -f docker-compose.yml)

if ! docker compose version >/dev/null 2>&1; then
	echo "docker compose (v2) is required but not available"
	exit 1
fi

sudo -v

echo "⛔ Stopping E2EE Chat App..."
sudo "${COMPOSE_CMD[@]}" down --remove-orphans

remaining="$(sudo "${COMPOSE_CMD[@]}" ps -q)"
if [[ -n "$remaining" ]]; then
	echo "❌ Some services are still running after shutdown:"
	sudo "${COMPOSE_CMD[@]}" ps
	exit 1
fi

echo "✅ All services stopped"