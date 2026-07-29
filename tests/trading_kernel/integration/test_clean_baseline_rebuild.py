from __future__ import annotations

import os
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.integration.test_schema_baseline import EXPECTED_TABLES

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
BASELINE_REVISION = "0001_trading_kernel_baseline_v2"


@pytest.mark.asyncio
async def test_empty_postgres_builds_only_the_v2_baseline() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        result = _run_alembic(database_url, "upgrade", "head")
        assert result.returncode == 0, result.stderr

        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                table_names = await connection.run_sync(
                    lambda sync: set(
                        __import__("sqlalchemy").inspect(sync).get_table_names()
                    )
                )
                revision = await connection.scalar(
                    __import__("sqlalchemy").text(
                        "SELECT version_num FROM alembic_version"
                    )
                )
            assert table_names == EXPECTED_TABLES | {"alembic_version"}
            assert revision == BASELINE_REVISION
        finally:
            await engine.dispose()

        result = _run_alembic(database_url, "downgrade", "base")
        assert result.returncode != 0
        assert "forward-only baseline" in result.stderr
    finally:
        await _drop_database(admin, database_name)
        await admin.close()


def _database_url(database_name: str) -> str:
    return (
        "postgresql+asyncpg://dingdingbot:dingdingbot_dev@127.0.0.1:5432/"
        f"{database_name}"
    )


def _run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url}
    return subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *arguments,
        ),
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


async def _drop_database(admin: asyncpg.Connection, database_name: str) -> None:
    with suppress(asyncpg.UndefinedObjectError):
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
    await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
