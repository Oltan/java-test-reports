#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting FastAPI server..."

# Start FastAPI server on port 8000
echo "Starting FastAPI on http://localhost:8000..."
cd "$PROJECT_DIR/fastapi-server"
uvicorn server:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Wait for server
sleep 5

echo "FastAPI PID: $FASTAPI_PID"
echo ""
echo "FastAPI server started!"
echo "  - FastAPI: http://localhost:8000"
echo ""
echo "To stop server: kill $FASTAPI_PID"
