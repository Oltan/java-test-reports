#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting both servers..."

# Start FastAPI server on port 8000
echo "Starting FastAPI on http://localhost:8000..."
cd "$PROJECT_DIR/fastapi-server"
uvicorn server:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Start Javalin server on port 8080
echo "Starting Javalin on http://localhost:8080..."
cd "$PROJECT_DIR/javalin-server"
mvn compile exec:java -Dexec.mainClass="com.testreports.javalin.JavalinServer" &
JAVALIN_PID=$!

# Wait for both servers
sleep 5

echo "FastAPI PID: $FASTAPI_PID"
echo "Javalin PID: $JAVALIN_PID"
echo ""
echo "Both servers started!"
echo "  - FastAPI: http://localhost:8000"
echo "  - Javalin: http://localhost:8080"
echo ""
echo "To stop servers: kill $FASTAPI_PID $JAVALIN_PID"