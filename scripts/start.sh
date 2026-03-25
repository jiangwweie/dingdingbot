#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"
ENV_FILE="$ROOT_DIR/.env"

# Default ports
FRONTEND_PORT=5173
BACKEND_PORT=8000

# Load from .env if it exists
if [ -f "$ENV_FILE" ]; then
    # Load env variables safely
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^\s*$' | xargs)
fi

echo "========================================="
echo "Stopping existing services..."
"$DIR/stop.sh" || true # Do not fail if stop script fails

echo "========================================="
echo "Starting Backend on port $BACKEND_PORT..."
cd "$ROOT_DIR"
export BACKEND_PORT=$BACKEND_PORT
nohup python3 -m src.main > "$ROOT_DIR/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/.backend.pid"

echo "Starting Frontend on port $FRONTEND_PORT..."
cd "$ROOT_DIR/web-front"
export FRONTEND_PORT=$FRONTEND_PORT
export BACKEND_PORT=$BACKEND_PORT
nohup npm run dev -- --port $FRONTEND_PORT > "$ROOT_DIR/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/.frontend.pid"

echo "========================================="
echo "Services started successfully."
echo "Frontend Dashboard: http://localhost:$FRONTEND_PORT"
echo "Backend API Health: http://localhost:$BACKEND_PORT/api/health"
echo "========================================="
