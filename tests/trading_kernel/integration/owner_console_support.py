from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from ipaddress import ip_address, ip_interface
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


class UnsafeDisposablePostgresTarget(RuntimeError):
    pass


_CleanupAction = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _OwnerReadCleanupActions:
    close_database_connection: _CleanupAction | None = None
    terminate_database_sessions: _CleanupAction | None = None
    drop_database: _CleanupAction | None = None
    drop_role: _CleanupAction | None = None
    close_admin: _CleanupAction | None = None


async def _run_owner_read_cleanup(
    actions: _OwnerReadCleanupActions,
    *,
    primary_error: BaseException | None,
) -> None:
    failures: list[tuple[str, BaseException]] = []
    steps = (
        ("close_database_connection", actions.close_database_connection),
        ("terminate_database_sessions", actions.terminate_database_sessions),
        ("drop_database", actions.drop_database),
        ("drop_role", actions.drop_role),
        ("close_admin", actions.close_admin),
    )
    for name, action in steps:
        if action is None:
            continue
        try:
            await action()
        except BaseException as error:  # noqa: BLE001 - all cleanup must run
            failures.append((name, error))

    if not failures:
        return
    if primary_error is not None:
        for name, error in failures:
            primary_error.add_note(
                f"owner read cleanup {name} failed: {error!r}"
            )
        return
    first_name, first_error = failures[0]
    first_error.add_note(f"owner read cleanup first failed step: {first_name}")
    for name, error in failures[1:]:
        first_error.add_note(f"owner read cleanup {name} also failed: {error!r}")
    raise first_error


async def _connect_verified_disposable_admin(
    admin_dsn: str,
) -> asyncpg.Connection:
    _require_local_admin_dsn(admin_dsn)
    admin = await asyncpg.connect(admin_dsn)
    try:
        identity = await admin.fetchrow(
            "SELECT current_database() AS database_name, "
            "inet_server_addr()::text AS server_address"
        )
        _require_local_server_identity(
            database_name=identity["database_name"],
            server_address=identity["server_address"],
        )
    except BaseException as error:
        try:
            await admin.close()
        except BaseException as close_error:  # noqa: BLE001 - preserve primary
            error.add_note(f"admin close after preflight failure: {close_error!r}")
        raise
    return admin


def _require_local_admin_dsn(admin_dsn: str) -> None:
    url = make_url(admin_dsn)
    if url.database != "postgres":
        raise UnsafeDisposablePostgresTarget(
            "disposable PostgreSQL admin database must be postgres"
        )

    endpoint = url.host or url.query.get("host")
    if endpoint is None:
        return
    if not isinstance(endpoint, str):
        raise UnsafeDisposablePostgresTarget(
            "disposable PostgreSQL admin endpoint is ambiguous"
        )
    if endpoint.startswith("/") or endpoint.lower() == "localhost":
        return
    try:
        local = ip_address(endpoint).is_loopback
    except ValueError:
        local = False
    if not local:
        raise UnsafeDisposablePostgresTarget(
            "disposable PostgreSQL admin endpoint must be local"
        )


def _require_local_server_identity(
    *,
    database_name: str,
    server_address: str | None,
) -> None:
    if database_name != "postgres":
        raise UnsafeDisposablePostgresTarget(
            "disposable PostgreSQL server database must be postgres"
        )
    if server_address is None:
        return
    try:
        server_ip = ip_interface(server_address).ip
        local = server_ip.is_loopback or server_ip.is_private
    except ValueError:
        local = False
    if not local:
        raise UnsafeDisposablePostgresTarget(
            "disposable PostgreSQL server address must be local"
        )


@pytest_asyncio.fixture
async def owner_read_dsn() -> AsyncGenerator[str, None]:
    identity = uuid4().hex[:12]
    database_name = f"brc_owner_console_test_{identity}"
    role_name = f"brc_owner_read_test_{identity}"
    password = uuid4().hex
    assert SAFE_DATABASE.fullmatch(database_name)
    assert SAFE_ROLE.fullmatch(role_name)

    admin: asyncpg.Connection | None = None
    database_connection: asyncpg.Connection | None = None
    database_created = False
    role_created = False
    primary_error: BaseException | None = None
    try:
        admin = await _connect_verified_disposable_admin(ADMIN_DSN)
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_created = True
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        await admin.execute(
            f'REVOKE ALL ON DATABASE "{database_name}" FROM PUBLIC'
        )

        await admin.execute(
            f'CREATE ROLE "{role_name}" LOGIN PASSWORD \'{password}\' '
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            "NOREPLICATION NOBYPASSRLS"
        )
        role_created = True
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
            "REVOKE ALL ON SCHEMA public FROM PUBLIC"
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
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_admin = admin
        await _run_owner_read_cleanup(
            _OwnerReadCleanupActions(
                close_database_connection=(
                    database_connection.close
                    if database_connection is not None
                    else None
                ),
                terminate_database_sessions=(
                    (
                        lambda: _terminate_database_sessions(
                            cleanup_admin,
                            database_name,
                        )
                    )
                    if cleanup_admin is not None and database_created
                    else None
                ),
                drop_database=(
                    (lambda: _drop_database(cleanup_admin, database_name))
                    if cleanup_admin is not None and database_created
                    else None
                ),
                drop_role=(
                    (lambda: _drop_role(cleanup_admin, role_name))
                    if cleanup_admin is not None and role_created
                    else None
                ),
                close_admin=(
                    cleanup_admin.close if cleanup_admin is not None else None
                ),
            ),
            primary_error=primary_error,
        )


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


async def _terminate_database_sessions(
    admin: asyncpg.Connection,
    database_name: str,
) -> None:
    await admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = $1 AND pid <> pg_backend_pid()",
        database_name,
    )


async def _drop_database(admin: asyncpg.Connection, database_name: str) -> None:
    await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


async def _drop_role(admin: asyncpg.Connection, role_name: str) -> None:
    await admin.execute(f'DROP ROLE IF EXISTS "{role_name}"')
