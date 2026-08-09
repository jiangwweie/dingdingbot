#!/usr/bin/env python3
"""Restore a verified Owner Console DML snapshot into a guarded local database."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from ipaddress import ip_interface
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy.engine import URL, make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADMIN_DSN = (
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres"
)
_SAFE_DATABASE = re.compile(r"^brc_owner_console_test_[a-f0-9]{12}$")
_SAFE_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REVISION = re.compile(r"^[A-Za-z0-9_]{1,128}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_READ_ROLE = "brc_owner_console"
_DEFAULT_POSTGRES_CONTAINER = "dingdingbot-pg"
_PARITY_KEYS = (
    "brc_signal_events",
    "brc_trade_tickets",
    "brc_trade_aggregates",
    "brc_trade_reviews",
    "open_brc_runtime_incidents",
)
_METADATA_KEYS = frozenset(
    {
        "captured_at_utc",
        "ssh_host",
        "database_name",
        "postgresql_version",
        "alembic_revision",
        "compressed_bytes",
        "sha256",
        "parity_counts",
    }
)


def validate_local_target(*, host: str, database_name: str) -> None:
    """Permit destructive restore work only on a scoped localhost database."""

    if host not in _LOCAL_HOSTS and not host.startswith("/"):
        raise ValueError("restore host must be localhost or a local Unix Socket")
    if _SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("restore database name is outside the disposable scope")


def verify_snapshot_metadata(
    *,
    snapshot_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    """Validate metadata shape, compressed size, and SHA before PostgreSQL use."""

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("snapshot metadata is unavailable or invalid") from error
    if not isinstance(payload, dict) or set(payload) != _METADATA_KEYS:
        raise ValueError("snapshot metadata keys differ from the allowed set")
    if not snapshot_path.is_file():
        raise ValueError("snapshot artifact is unavailable")
    if payload["compressed_bytes"] != snapshot_path.stat().st_size:
        raise ValueError("snapshot compressed byte size differs")
    expected_sha = payload["sha256"]
    if not isinstance(expected_sha, str) or _SHA256.fullmatch(expected_sha) is None:
        raise ValueError("snapshot SHA-256 metadata is invalid")
    if _sha256(snapshot_path) != expected_sha:
        raise ValueError("snapshot SHA-256 does not match the artifact")
    revision = payload["alembic_revision"]
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        raise ValueError("snapshot Alembic revision is invalid")
    for key in (
        "captured_at_utc",
        "ssh_host",
        "database_name",
        "postgresql_version",
    ):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError(f"snapshot metadata field is invalid: {key}")
    counts = payload["parity_counts"]
    if not isinstance(counts, dict) or set(counts) != set(_PARITY_KEYS):
        raise ValueError("snapshot parity counts are invalid")
    for key in _PARITY_KEYS:
        value = counts[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"snapshot parity count is invalid: {key}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _admin_url(raw_dsn: str) -> URL:
    try:
        url = make_url(raw_dsn)
    except Exception as error:
        raise ValueError("local PostgreSQL admin DSN is invalid") from error
    if url.drivername not in {"postgresql", "postgresql+asyncpg"}:
        raise ValueError("local PostgreSQL admin DSN must use PostgreSQL")
    host = url.host or str(url.query.get("host", ""))
    validate_local_target(
        host=host,
        database_name="brc_owner_console_test_000000000000",
    )
    if url.database != "postgres":
        raise ValueError("local PostgreSQL admin DSN must target postgres")
    if not url.username:
        raise ValueError("local PostgreSQL admin DSN requires a username")
    return url


def _render_url(url: URL, *, drivername: str) -> str:
    return url.set(drivername=drivername).render_as_string(hide_password=False)


def _database_url(admin_url: URL, *, database_name: str, drivername: str) -> str:
    return _render_url(
        admin_url.set(database=database_name),
        drivername=drivername,
    )


async def _connect_verified_admin(admin_url: URL) -> asyncpg.Connection:
    connection = await asyncpg.connect(_render_url(admin_url, drivername="postgresql"))
    address = await connection.fetchval("SELECT inet_server_addr()::text")
    if address is not None:
        server_address = ip_interface(str(address)).ip
        if not (server_address.is_loopback or server_address.is_private):
            await connection.close()
            raise ValueError("PostgreSQL server identity is not local or private")
    return connection


async def _create_fresh_database(
    admin: asyncpg.Connection,
    *,
    database_name: str,
) -> None:
    exists = await admin.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)",
        database_name,
    )
    if exists:
        raise ValueError("disposable restore database already exists")
    await admin.execute(f'CREATE DATABASE "{database_name}"')


def _run_bootstrap(database_url: str) -> None:
    environment = os.environ.copy()
    environment["TRADING_KERNEL_DATABASE_URL"] = database_url
    completed = subprocess.run(
        (sys.executable, "scripts/trading_kernel/bootstrap_schema.py"),
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "local schema bootstrap failed: " + completed.stderr.strip()[-2_000:]
        )


async def _truncate_public_data(connection: asyncpg.Connection) -> None:
    table_names = await connection.fetch(
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
        "ORDER BY tablename"
    )
    identifiers = tuple(str(row["tablename"]) for row in table_names)
    if not identifiers:
        raise RuntimeError("local schema contains no restorable public tables")
    quoted = ", ".join(f'"{identifier}"' for identifier in identifiers)
    async with connection.transaction():
        await connection.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")


def _run_psql_restore(
    *,
    admin_url: URL,
    database_name: str,
    snapshot_path: Path,
    postgres_container: str,
) -> None:
    if _SAFE_CONTAINER.fullmatch(postgres_container) is None:
        raise ValueError("local PostgreSQL container name is invalid")
    command = [
        "docker",
        "exec",
        "--interactive",
        postgres_container,
        "psql",
        "--no-psqlrc",
        "--set",
        "ON_ERROR_STOP=1",
        "--single-transaction",
        "--username",
        str(admin_url.username),
        "--dbname",
        database_name,
    ]
    with gzip.open(snapshot_path, "rb") as source:
        dml = (
            b"SET session_replication_role = replica;\n"
            + source.read()
            + b"\nSET session_replication_role = origin;\n"
        )
        completed = subprocess.run(
            command,
            input=dml,
            check=False,
            capture_output=True,
            timeout=300,
        )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError("local DML restore failed: " + stderr.strip()[-2_000:])


async def _read_revision(connection: asyncpg.Connection) -> str:
    revision = await connection.fetchval("SELECT version_num FROM alembic_version")
    if not isinstance(revision, str):
        raise TypeError("local Alembic revision is unavailable")
    return revision


async def _read_parity_counts(connection: asyncpg.Connection) -> dict[str, int]:
    row = await connection.fetchrow(
        "SELECT "
        "(SELECT count(*) FROM brc_signal_events) AS brc_signal_events, "
        "(SELECT count(*) FROM brc_trade_tickets) AS brc_trade_tickets, "
        "(SELECT count(*) FROM brc_trade_aggregates) AS brc_trade_aggregates, "
        "(SELECT count(*) FROM brc_trade_reviews) AS brc_trade_reviews, "
        "(SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open') "
        "AS open_brc_runtime_incidents"
    )
    if row is None:
        raise RuntimeError("local parity counts are unavailable")
    return {key: int(row[key]) for key in _PARITY_KEYS}


async def _create_or_refresh_read_role(
    *,
    admin: asyncpg.Connection,
    target: asyncpg.Connection,
    database_name: str,
    password: str,
) -> None:
    exists = await admin.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = $1)",
        _READ_ROLE,
    )
    role_options = (
        "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
        f"PASSWORD '{password}'"
    )
    if exists:
        await admin.execute(f"ALTER ROLE {_READ_ROLE} WITH {role_options}")
    else:
        await admin.execute(f"CREATE ROLE {_READ_ROLE} WITH {role_options}")
    await admin.execute(
        f"ALTER ROLE {_READ_ROLE} SET default_transaction_read_only = on"
    )
    await admin.execute(f"ALTER ROLE {_READ_ROLE} SET statement_timeout = '3s'")
    await admin.execute(
        f"ALTER ROLE {_READ_ROLE} SET application_name = 'brc_owner_console'"
    )
    await target.execute(f"REVOKE ALL ON DATABASE \"{database_name}\" FROM {_READ_ROLE}")
    await target.execute(f"REVOKE ALL ON SCHEMA public FROM {_READ_ROLE}")
    await target.execute(
        f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {_READ_ROLE}"
    )
    await target.execute(f"GRANT CONNECT ON DATABASE \"{database_name}\" TO {_READ_ROLE}")
    await target.execute(f"GRANT USAGE ON SCHEMA public TO {_READ_ROLE}")
    await target.execute(
        f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {_READ_ROLE}"
    )


def _write_read_dsn(path: Path, dsn: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(dsn)
            output.write("\n")
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


async def _prove_read_role(read_dsn: str) -> None:
    connection = await asyncpg.connect(
        read_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    try:
        transaction_read_only = await connection.fetchval(
            "SHOW transaction_read_only"
        )
        current_user = await connection.fetchval("SELECT current_user")
        if transaction_read_only != "on" or current_user != _READ_ROLE:
            raise RuntimeError("local Owner Console role is not read-only")
    finally:
        await connection.close()


def _cleanup_command(
    admin_url: URL,
    *,
    database_name: str,
    postgres_container: str,
) -> str:
    if _SAFE_CONTAINER.fullmatch(postgres_container) is None:
        raise ValueError("local PostgreSQL container name is invalid")
    command = [
        "docker",
        "exec",
        postgres_container,
        "dropdb",
        "--username",
        str(admin_url.username),
    ]
    command.append(database_name)
    return shlex.join(command)


async def restore_snapshot(
    *,
    snapshot_path: Path,
    metadata_path: Path,
    database_name: str,
    admin_dsn: str,
    postgres_container: str = _DEFAULT_POSTGRES_CONTAINER,
) -> tuple[Path, str, Mapping[str, int]]:
    metadata = verify_snapshot_metadata(
        snapshot_path=snapshot_path,
        metadata_path=metadata_path,
    )
    admin_url = _admin_url(admin_dsn)
    host = admin_url.host or str(admin_url.query.get("host", ""))
    validate_local_target(host=host, database_name=database_name)
    cleanup = _cleanup_command(
        admin_url,
        database_name=database_name,
        postgres_container=postgres_container,
    )
    admin = await _connect_verified_admin(admin_url)
    target: asyncpg.Connection | None = None
    database_created = False
    try:
        await _create_fresh_database(admin, database_name=database_name)
        database_created = True
        async_database_url = _database_url(
            admin_url,
            database_name=database_name,
            drivername="postgresql+asyncpg",
        )
        _run_bootstrap(async_database_url)
        target = await asyncpg.connect(
            _database_url(
                admin_url,
                database_name=database_name,
                drivername="postgresql",
            )
        )
        expected_revision = str(metadata["alembic_revision"])
        if await _read_revision(target) != expected_revision:
            raise RuntimeError("local schema revision differs from snapshot")
        await _truncate_public_data(target)
        await target.close()
        target = None
        _run_psql_restore(
            admin_url=admin_url,
            database_name=database_name,
            snapshot_path=snapshot_path,
            postgres_container=postgres_container,
        )
        target = await asyncpg.connect(
            _database_url(
                admin_url,
                database_name=database_name,
                drivername="postgresql",
            )
        )
        if await _read_revision(target) != expected_revision:
            raise RuntimeError("restored Alembic revision differs from snapshot")
        counts = await _read_parity_counts(target)
        if counts != metadata["parity_counts"]:
            raise RuntimeError("restored table parity counts differ from Tokyo")
        read_password = secrets.token_urlsafe(32)
        await _create_or_refresh_read_role(
            admin=admin,
            target=target,
            database_name=database_name,
            password=read_password,
        )
        read_dsn = _database_url(
            admin_url.set(username=_READ_ROLE, password=read_password),
            database_name=database_name,
            drivername="postgresql+asyncpg",
        )
        credential_path = metadata_path.parent / f"{database_name}.read-dsn"
        _write_read_dsn(credential_path, read_dsn)
        await _prove_read_role(read_dsn)
    except BaseException as error:
        if database_created:
            error.add_note(f"disposable database cleanup: {cleanup}")
        raise
    finally:
        if target is not None:
            await target.close()
        await admin.close()
    return credential_path, cleanup, counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--database-name", required=True)
    parser.add_argument(
        "--postgres-container",
        default=os.getenv(
            "BRC_TEST_POSTGRES_CONTAINER_NAME",
            _DEFAULT_POSTGRES_CONTAINER,
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    admin_dsn = os.getenv("BRC_TEST_POSTGRES_ADMIN_URL", DEFAULT_ADMIN_DSN)
    credential_path, cleanup, counts = asyncio.run(
        restore_snapshot(
            snapshot_path=args.snapshot,
            metadata_path=args.metadata,
            database_name=args.database_name,
            admin_dsn=admin_dsn,
            postgres_container=args.postgres_container,
        )
    )
    print(
        json.dumps(
            {
                "database_name": args.database_name,
                "read_dsn_file": str(credential_path),
                "parity_counts": counts,
                "cleanup_command": cleanup,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
