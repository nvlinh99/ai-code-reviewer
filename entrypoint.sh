#!/bin/sh

echo "⏳ Waiting for PostgreSQL to initialize..."
sleep 5

echo "🛠️ Running DB migrations (if any)..."
alembic upgrade head --config alembic.ini

echo "🚀 Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000