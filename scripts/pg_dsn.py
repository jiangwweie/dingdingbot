"""Script-facing PostgreSQL DSN helpers."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.sync_pg_dsn import (  # noqa: E402,F401
    is_sync_postgres_dsn,
    normalize_libpq_postgres_dsn,
    normalize_sync_postgres_dsn,
)
