from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest_asyncio
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_owner_console_test_[a-f0-9]{12}$")
SAFE_ROLE = re.compile(r"^brc_owner_read_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def owner_read_dsn() -> AsyncGenerator[str, None]:
    identity = uuid4().hex[:12]
    database_name = f"brc_owner_console_test_{identity}"
    role_name = f"brc_owner_read_test_{identity}"
    password = uuid4().hex
    assert SAFE_DATABASE.fullmatch(database_name)
    assert SAFE_ROLE.fullmatch(role_name)

    admin = await asyncpg.connect(ADMIN_DSN)
    database_connection: asyncpg.Connection | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")

        await admin.execute(
            f'CREATE ROLE "{role_name}" LOGIN PASSWORD \'{password}\' '
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            "NOREPLICATION NOBYPASSRLS"
        )
        await admin.execute(
            f'ALTER ROLE "{role_name}" SET default_transaction_read_only = on'
        )
        await admin.execute(
            f'ALTER ROLE "{role_name}" SET statement_timeout = \'3000ms\''
        )
        await admin.execute(
            f'ALTER ROLE "{role_name}" SET application_name = \'brc_owner_console\''
        )
        await admin.execute(
            f'GRANT CONNECT ON DATABASE "{database_name}" TO "{role_name}"'
        )

        database_connection = await asyncpg.connect(
            make_url(database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        await database_connection.execute(
            f'GRANT USAGE ON SCHEMA public TO "{role_name}"'
        )
        await database_connection.execute(
            f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{role_name}"'
        )
        await database_connection.close()
        database_connection = None

        yield _owner_read_url(
            database_name=database_name,
            role_name=role_name,
            password=password,
        )
    finally:
        if database_connection is not None:
            await database_connection.close()
        await _drop_database(admin, database_name)
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(f'DROP ROLE IF EXISTS "{role_name}"')
        await admin.close()


def _database_url(database_name: str) -> str:
    return (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql+asyncpg", database=database_name)
        .render_as_string(hide_password=False)
    )


def _owner_read_url(*, database_name: str, role_name: str, password: str) -> str:
    return (
        make_url(ADMIN_DSN)
        .set(
            drivername="postgresql+asyncpg",
            username=role_name,
            password=password,
            database=database_name,
        )
        .render_as_string(hide_password=False)
    )


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url}
    subprocess.run(
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
        check=True,
    )


async def _drop_database(admin: asyncpg.Connection, database_name: str) -> None:
    with suppress(asyncpg.UndefinedObjectError):
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
    await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
