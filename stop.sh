#!/bin/bash

# E2EE Chat App - Stop Script
# Usage: ./stop.sh

echo "⛔ Stopping E2EE Chat App..."
sudo docker-compose -f docker-compose.prod.yml down
echo "✅ All services stopped"