from __future__ import annotations

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
    owner_read_transaction,
)
from tests.trading_kernel.integration.owner_console_support import (
    UnsafeDisposablePostgresTarget,
    _CandidatePostgresIdentity,
    _connect_verified_disposable_admin,
    _DockerPostgresContainerIdentity,
    _OwnerReadCleanupActions,
    _require_expected_docker_postgres_container,
    _require_local_server_identity,
    _run_attested_admin_ddl,
    _run_owner_read_cleanup,
    owner_read_dsn,
)

__all__ = ["owner_read_dsn"]


@pytest.mark.parametrize(
    "admin_dsn",
    (
        "postgresql://production_admin@203.0.113.10:5432/postgres",
        "postgresql://production_admin@127.0.0.1:5432/brc_production",
    ),
)
async def test_disposable_admin_rejects_production_shaped_dsn_before_connect(
    admin_dsn: str,
) -> None:
    with pytest.raises(UnsafeDisposablePostgresTarget):
        await _connect_verified_disposable_admin(admin_dsn)


@pytest.mark.parametrize(
    ("database_name", "server_address"),
    (
        ("brc_production", "127.0.0.1"),
        ("postgres", "8.8.8.8"),
    ),
)
def test_disposable_admin_rejects_nonlocal_server_identity(
    database_name: str,
    server_address: str,
) -> None:
    with pytest.raises(UnsafeDisposablePostgresTarget):
        _require_local_server_identity(
            database_name=database_name,
            server_address=server_address,
        )


async def test_ssh_tunnel_identifier_mismatch_is_rejected_before_ddl() -> None:
    ddl_calls: list[str] = []

    async def forbidden_ddl() -> None:
        ddl_calls.append("called")

    with pytest.raises(UnsafeDisposablePostgresTarget):
        await _run_attested_admin_ddl(
            admin_dsn=(
                "postgresql://production_admin@127.0.0.1:5432/postgres"
            ),
            candidate=_CandidatePostgresIdentity(
                database_name="postgres",
                server_address="172.18.0.99/32",
                system_identifier="1111111111111111111",
            ),
            attested_system_identifier="2222222222222222222",
            ddl=forbidden_ddl,
        )

    assert ddl_calls == []


def test_docker_attestation_rejects_mismatched_compose_service_label() -> None:
    identity = _DockerPostgresContainerIdentity(
        name="/dingdingbot-pg",
        image="postgres:16-alpine",
        running=True,
        labels={
            "com.docker.compose.service": "production-postgres",
            "com.docker.compose.project": "final",
            "com.docker.compose.project.config_files": (
                "/Users/jiangwei/Documents/final/docker-compose.pg.yml"
            ),
            "com.docker.compose.project.working_dir": (
                "/Users/jiangwei/Documents/final"
            ),
            "com.docker.compose.container-number": "1",
            "com.docker.compose.oneoff": "False",
        },
    )

    with pytest.raises(UnsafeDisposablePostgresTarget):
        _require_expected_docker_postgres_container(
            identity,
            container_name="dingdingbot-pg",
        )


async def test_cleanup_attempts_every_step_without_overriding_primary_failure() -> None:
    calls: list[str] = []

    def action(name: str, *, error: BaseException | None = None):
        async def run() -> None:
            calls.append(name)
            if error is not None:
                raise error

        return run

    primary_error = RuntimeError("primary setup failure")
    actions = _OwnerReadCleanupActions(
        close_database_connection=action(
            "close database connection",
            error=OSError("close failed"),
        ),
        terminate_database_sessions=action("terminate database sessions"),
        drop_database=action("drop database"),
        drop_role=action("drop role"),
        close_admin=action("close admin"),
    )

    await _run_owner_read_cleanup(actions, primary_error=primary_error)

    assert calls == [
        "close database connection",
        "terminate database sessions",
        "drop database",
        "drop role",
        "close admin",
    ]
    assert primary_error.__notes__ == [
        (
            "owner read cleanup close_database_connection failed: "
            "OSError('close failed')"
        )
    ]


async def test_owner_read_transaction_is_repeatable_read_and_read_only(
    owner_read_dsn: str,
) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            read_only = await connection.scalar(
                sa.text("SHOW transaction_read_only")
            )
            isolation = await connection.scalar(
                sa.text("SHOW transaction_isolation")
            )
            timeout = await connection.scalar(sa.text("SHOW statement_timeout"))
        assert read_only == "on"
        assert isolation == "repeatable read"
        assert timeout == "3s"
    finally:
        await engine.dispose()


async def test_owner_read_role_cannot_insert(owner_read_dsn: str) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        with pytest.raises(DBAPIError):
            async with owner_read_transaction(engine) as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO brc_monitor_current "
                        "(monitor_key, owner_status, summary, intervention, "
                        "updated_at_ms, projection_version) "
                        "VALUES ('forbidden', 'running', 'x', 'x', 1, 1)"
                    )
                )
    finally:
        await engine.dispose()


async def test_owner_read_role_defaults_and_permanent_write_denial_are_direct(
    owner_read_dsn: str,
) -> None:
    connection = await asyncpg.connect(_asyncpg_dsn(owner_read_dsn))
    try:
        assert await connection.fetchval("SHOW default_transaction_read_only") == "on"
        assert await connection.fetchval("SHOW statement_timeout") == "3s"
        assert await connection.fetchval("SHOW application_name") == (
            "brc_owner_console"
        )

        await connection.execute("SET default_transaction_read_only = off")
        assert await connection.fetchval("SHOW transaction_read_only") == "off"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "INSERT INTO brc_monitor_current "
                "(monitor_key, owner_status, summary, intervention, "
                "updated_at_ms, projection_version) "
                "VALUES ('direct-forbidden', 'running', 'x', 'x', 1, 1)"
            )
    finally:
        await connection.close()


async def test_owner_read_role_cannot_use_public_object_creation_capabilities(
    owner_read_dsn: str,
) -> None:
    connection = await asyncpg.connect(_asyncpg_dsn(owner_read_dsn))
    try:
        await connection.execute("SET default_transaction_read_only = off")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "CREATE TEMPORARY TABLE owner_forbidden_temp (value integer)"
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                "CREATE TABLE public.owner_forbidden_permanent (value integer)"
            )
    finally:
        await connection.close()


def _asyncpg_dsn(dsn: str) -> str:
    return (
        make_url(dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
