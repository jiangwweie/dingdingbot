from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
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
SAFE_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_SYSTEM_IDENTIFIER = re.compile(r"^[0-9]+$")
SAFE_COMPOSE_CONFIG_HASH = re.compile(r"^[a-f0-9]{64}$")
POSTGRES_CONTAINER_NAME = os.getenv(
    "BRC_TEST_POSTGRES_CONTAINER_NAME",
    "dingdingbot-pg",
)
DOCKER_TIMEOUT_SECONDS = 3
EXPECTED_POSTGRES_IMAGE = "postgres:16-alpine"
EXPECTED_COMPOSE_FILE = "docker-compose.pg.yml"
EXPECTED_COMPOSE_LABELS = {
    "com.docker.compose.service": "postgres",
    "com.docker.compose.project": "final",
    "com.docker.compose.container-number": "1",
    "com.docker.compose.oneoff": "False",
    "com.docker.compose.depends_on": "",
}


class UnsafeDisposablePostgresTarget(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _CandidatePostgresIdentity:
    database_name: str
    server_address: str | None
    system_identifier: str


@dataclass(frozen=True, slots=True)
class _DockerPostgresContainerIdentity:
    name: str
    image: str
    running: bool
    labels: Mapping[str, str]


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


async def _run_local_container_attested_ddl(
    *,
    admin_dsn: str,
    admin: asyncpg.Connection,
    container_name: str,
    ddl: _CleanupAction,
) -> None:
    candidate = await _read_candidate_postgres_identity(admin)
    attested_system_identifier = _attest_local_docker_postgres(container_name)
    await _run_attested_admin_ddl(
        admin_dsn=admin_dsn,
        candidate=candidate,
        attested_system_identifier=attested_system_identifier,
        ddl=ddl,
    )


async def _run_attested_admin_ddl(
    *,
    admin_dsn: str,
    candidate: _CandidatePostgresIdentity,
    attested_system_identifier: str,
    ddl: _CleanupAction,
) -> None:
    _require_local_admin_dsn(admin_dsn)
    _require_local_server_identity(
        database_name=candidate.database_name,
        server_address=candidate.server_address,
    )
    if not SAFE_SYSTEM_IDENTIFIER.fullmatch(candidate.system_identifier):
        raise UnsafeDisposablePostgresTarget(
            "candidate PostgreSQL system identifier is invalid"
        )
    if not SAFE_SYSTEM_IDENTIFIER.fullmatch(attested_system_identifier):
        raise UnsafeDisposablePostgresTarget(
            "attested PostgreSQL system identifier is invalid"
        )
    if candidate.system_identifier != attested_system_identifier:
        raise UnsafeDisposablePostgresTarget(
            "candidate PostgreSQL cluster differs from local Docker cluster"
        )
    await ddl()


async def _read_candidate_postgres_identity(
    admin: asyncpg.Connection,
) -> _CandidatePostgresIdentity:
    identity = await admin.fetchrow(
        "SELECT current_database() AS database_name, "
        "inet_server_addr()::text AS server_address, "
        "system_identifier::text AS system_identifier "
        "FROM pg_control_system()"
    )
    return _CandidatePostgresIdentity(
        database_name=identity["database_name"],
        server_address=identity["server_address"],
        system_identifier=identity["system_identifier"],
    )


def _attest_local_docker_postgres(container_name: str) -> str:
    identity = _inspect_docker_postgres_container(container_name)
    _require_expected_docker_postgres_container(
        identity,
        container_name=container_name,
    )
    result = _run_docker(
        [
            "exec",
            container_name,
            "psql",
            "--username",
            "dingdingbot",
            "--dbname",
            "postgres",
            "--tuples-only",
            "--no-align",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            "SELECT system_identifier::text FROM pg_control_system()",
        ]
    )
    system_identifier = result.stdout.strip()
    if not SAFE_SYSTEM_IDENTIFIER.fullmatch(system_identifier):
        raise UnsafeDisposablePostgresTarget(
            "local Docker PostgreSQL system identifier is invalid"
        )
    return system_identifier


def _inspect_docker_postgres_container(
    container_name: str,
) -> _DockerPostgresContainerIdentity:
    if not SAFE_CONTAINER.fullmatch(container_name):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container name is invalid"
        )
    result = _run_docker(
        [
            "inspect",
            "--type",
            "container",
            "--format",
            (
                "{{json .Name}}\t{{json .Config.Image}}\t"
                "{{json .State.Running}}\t{{json .Config.Labels}}"
            ),
            container_name,
        ]
    )
    try:
        raw_name, raw_image, raw_running, raw_labels = result.stdout.strip().split(
            "\t",
            3,
        )
        name = json.loads(raw_name)
        image = json.loads(raw_image)
        running = json.loads(raw_running)
        labels = json.loads(raw_labels)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container inspect output is invalid"
        ) from None
    if not isinstance(name, str) or not isinstance(image, str):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container identity is invalid"
        )
    if not isinstance(running, bool) or not isinstance(labels, dict):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container state is invalid"
        )
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in labels.items()
    ):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container labels are invalid"
        )
    return _DockerPostgresContainerIdentity(
        name=name,
        image=image,
        running=running,
        labels=labels,
    )


def _require_expected_docker_postgres_container(
    identity: _DockerPostgresContainerIdentity,
    *,
    container_name: str,
) -> None:
    if identity.name != f"/{container_name}":
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container name differs from expected identity"
        )
    if identity.image != EXPECTED_POSTGRES_IMAGE or not identity.running:
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container image or state is invalid"
        )
    for key, expected in EXPECTED_COMPOSE_LABELS.items():
        if identity.labels.get(key) != expected:
            raise UnsafeDisposablePostgresTarget(
                "local PostgreSQL container Compose labels are invalid"
            )

    config_hash = identity.labels.get("com.docker.compose.config-hash")
    if config_hash is None or not SAFE_COMPOSE_CONFIG_HASH.fullmatch(config_hash):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container Compose config hash is invalid"
        )
    config_file_value = identity.labels.get(
        "com.docker.compose.project.config_files"
    )
    working_dir_value = identity.labels.get(
        "com.docker.compose.project.working_dir"
    )
    if config_file_value is None or working_dir_value is None:
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container Compose source labels are missing"
        )
    config_file = Path(config_file_value)
    if (
        not config_file.is_absolute()
        or config_file.name != EXPECTED_COMPOSE_FILE
        or str(config_file.parent) != working_dir_value
    ):
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container Compose source labels are invalid"
        )
    try:
        source_matches = config_file.read_bytes() == (
            REPO_ROOT / EXPECTED_COMPOSE_FILE
        ).read_bytes()
    except OSError:
        source_matches = False
    if not source_matches:
        raise UnsafeDisposablePostgresTarget(
            "local PostgreSQL container Compose source differs from repository"
        )


def _run_docker(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        raise UnsafeDisposablePostgresTarget(
            "local Docker PostgreSQL attestation failed"
        ) from None


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
        await _run_local_container_attested_ddl(
            admin_dsn=ADMIN_DSN,
            admin=admin,
            container_name=POSTGRES_CONTAINER_NAME,
            ddl=lambda: admin.execute(f'CREATE DATABASE "{database_name}"'),
        )
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
