from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
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


@pytest.mark.asyncio
async def test_bootstrap_schema_creates_only_the_clean_kernel_baseline() -> None:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/trading_kernel/bootstrap_schema.py",
                "--database-url",
                database_url,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr[-4000:]

        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: set(
                        __import__("sqlalchemy").inspect(sync_conn).get_table_names()
                    )
                )
                exposure_columns = await conn.run_sync(
                    lambda sync_conn: {
                        column["name"]
                        for column in __import__("sqlalchemy")
                        .inspect(sync_conn)
                        .get_columns("brc_account_exposure_current")
                    }
                )
                exposure_primary_key = await conn.run_sync(
                    lambda sync_conn: set(
                        __import__("sqlalchemy")
                        .inspect(sync_conn)
                        .get_pk_constraint("brc_account_exposure_current")[
                            "constrained_columns"
                        ]
                    )
                )
            assert tables == EXPECTED_TABLES | {"alembic_version"}
            assert {"venue_id", "account_id"}.issubset(exposure_columns)
            assert exposure_primary_key == {"venue_id", "account_id"}
        finally:
            await engine.dispose()
    finally:
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
