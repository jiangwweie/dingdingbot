"""Local disposable PostgreSQL helpers for Trading Kernel tests only."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_POSTGRES_ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_TEST_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


def async_database_url(database_name: str) -> str:
    if SAFE_TEST_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    return (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
    )


def run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
