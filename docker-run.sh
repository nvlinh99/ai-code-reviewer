#!/bin/bash

set -e

echo "🚀 Starting AI Review Dashboard with Docker Compose..."

# Build Docker images
docker compose -f infra/docker-compose.yml build

# Run containers in detached mode
docker compose -f infra/docker-compose.yml up -d

# Wait for services to be ready (optional but helpful)
echo "⏳ Waiting for PostgreSQL to initialize..."
sleep 5

# Optional: create initial table if needed
echo "🛠️ Running DB migrations (if any)..."
docker compose exec backend python scripts/init_db.py

echo "✅ Dashboard running at: http://localhost:8000/dashboard"
