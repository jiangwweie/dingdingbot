#!/usr/bin/env bash
set -euo pipefail
workspace_dir="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$workspace_dir"
"$workspace_dir/.venv/bin/python" scripts/local/check_manual_workspace.py
export COMPOSE_PROJECT_NAME=brc-manual-local
export BRC_TEST_POSTGRES_CONTAINER_NAME=brc-manual-pg
export BRC_TEST_POSTGRES_ADMIN_URL=postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:55434/postgres
exec "$workspace_dir/.venv/bin/python" -m pytest "$@"
