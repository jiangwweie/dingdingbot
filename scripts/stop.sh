#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

echo "Stopping Backend..."
if [ -f "$ROOT_DIR/.backend.pid" ]; then
    PID=$(cat "$ROOT_DIR/.backend.pid")
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo "Backend (PID $PID) stopped."
    else
        echo "Backend (PID $PID) is not running."
    fi
    rm "$ROOT_DIR/.backend.pid"
else
    # Fallback cleanup
    pkill -f "python3 -m src.main" || echo "No rogue backend process found."
fi

echo "Stopping Frontend..."
if [ -f "$ROOT_DIR/.frontend.pid" ]; then
    PID=$(cat "$ROOT_DIR/.frontend.pid")
    if kill -0 $PID 2>/dev/null; then
        # Use pkill -P to kill child processes of npm (node)
        pkill -P $PID || true
        kill $PID
        echo "Frontend (PID $PID) stopped."
    else
        echo "Frontend (PID $PID) is not running."
    fi
    rm "$ROOT_DIR/.frontend.pid"
else
    # Fallback cleanup
    pkill -f "vite|npm run dev" || echo "No rogue frontend process found."
fi

# Ensure ports are completely freed (kill any process bound to these ports)
echo "Cleaning up ports..."
for PORT in 8000 8080 5173; do
    PIDS=$(lsof -ti:$PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "Killing processes on port $PORT: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
    fi
done

# Also kill any remaining uvicorn processes
pkill -9 -f "uvicorn" 2>/dev/null || true

echo "Cleanup complete."
