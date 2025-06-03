#!/bin/bash

export PYTHONPATH=$(pwd)
echo "🚀 Starting FastAPI on http://localhost:8000"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000