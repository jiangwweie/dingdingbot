"""Local disposable PostgreSQL helpers for Trading Kernel tests only."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg

from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_POSTGRES_ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_TEST_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
HEAD_TEMPLATE_DATABASE = "brc_kernel_template_head"


def async_database_url(database_name: str) -> str:
    if SAFE_TEST_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    return (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
    )


def _head_template_database_url() -> str:
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    return (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/"
        f"{HEAD_TEMPLATE_DATABASE}"
    )


def _head_template_admin_dsn() -> str:
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base}/{HEAD_TEMPLATE_DATABASE}"


def run_alembic(database_url: str, *args: str) -> None:
    resolved_args = args or ("upgrade", "head")
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *resolved_args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]


async def drop_database(admin: asyncpg.Connection, database_name: str) -> None:
    if SAFE_TEST_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    await admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = $1 AND pid <> pg_backend_pid()",
        database_name,
    )
    await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


class HeadTemplateCloneHarness:
    """Create one isolated current-head clone for each non-migration test."""

    async def create_clone(self) -> tuple[str, str]:
        admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
        try:
            await self._ensure_template(admin)
            database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
            assert SAFE_TEST_DATABASE.fullmatch(database_name)
            await admin.execute(
                f'CREATE DATABASE "{database_name}" TEMPLATE "{HEAD_TEMPLATE_DATABASE}"'
            )
            return database_name, async_database_url(database_name)
        finally:
            await admin.close()

    async def drop_clone(self, database_name: str) -> None:
        admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
        try:
            await drop_database(admin, database_name)
        finally:
            await admin.close()

    async def _ensure_template(self, admin: asyncpg.Connection) -> None:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            HEAD_TEMPLATE_DATABASE,
        )
        if exists:
            template = await asyncpg.connect(_head_template_admin_dsn())
            try:
                revision = await template.fetchval(
                    "SELECT version_num FROM alembic_version"
                )
            finally:
                await template.close()
            if revision == CURRENT_SCHEMA_REVISION:
                return
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                HEAD_TEMPLATE_DATABASE,
            )
            await admin.execute(f'DROP DATABASE "{HEAD_TEMPLATE_DATABASE}"')
        await admin.execute(f'CREATE DATABASE "{HEAD_TEMPLATE_DATABASE}"')
        run_alembic(_head_template_database_url(), "upgrade", "head")
