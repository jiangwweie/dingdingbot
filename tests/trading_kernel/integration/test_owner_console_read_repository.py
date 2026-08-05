from __future__ import annotations

import json
from decimal import Decimal

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
    _review_metrics,
    create_owner_read_engine,
    owner_read_transaction,
)
from tests.trading_kernel.integration.owner_console_support import (
    ADMIN_DSN,
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


def test_overview_review_metrics_never_accept_decoded_json_floats() -> None:
    net_pnl, net_r, gap, _evidence = _review_metrics(  # type: ignore[arg-type]
        [
            {
                "review_id": "review:float",
                "created_at_ms": 1_800_000_000_000,
                "economics_completeness": "complete",
                "net_pnl_quote": 0.1,
                "planned_r_multiple": 0.2,
            }
        ]
    )

    assert net_pnl.value is None
    assert net_r.value is None
    assert gap == "incomplete_review_economics"


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


async def test_overview_reads_seven_bounded_selects_in_supplied_transaction(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    engine = create_owner_read_engine(owner_read_dsn)
    statements: list[str] = []

    def capture_statement(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        async with owner_read_transaction(engine) as connection:
            statements.clear()
            transaction = connection.get_transaction()
            repository = PostgresOwnerReadRepository(connection)

            facts = await repository.read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

            assert connection.get_transaction() is transaction
            assert await connection.scalar(
                sa.text("SELECT count(*) FROM brc_owner_policy_current")
            ) == 1
        overview_selects = [
            statement
            for statement in statements
            if statement.startswith("select")
            and "count(*) from brc_owner_policy_current" not in statement
        ]
        assert len(overview_selects) == 7
        assert "brc_owner_policy_current" in overview_selects[0]
        assert "limit" in overview_selects[0]
        assert "brc_capacity_claims" in overview_selects[1]
        assert "order by brc_capacity_claims.created_at_ms desc" in overview_selects[1]
        assert "limit" in overview_selects[1]
        assert "brc_runtime_incidents" in overview_selects[2]
        assert "limit" in overview_selects[2]
        assert "brc_monitor_current" in overview_selects[3]
        assert "limit" in overview_selects[3]
        assert "brc_trade_tickets" in overview_selects[4]
        assert "brc_trade_aggregates" in overview_selects[4]
        assert "limit" in overview_selects[4]
        assert "brc_signal_events" in overview_selects[5]
        assert "brc_admission_decisions" in overview_selects[5]
        assert "occurred_at_ms" in overview_selects[5]
        assert "decided_at_ms" in overview_selects[5]
        assert "brc_trade_reviews" in overview_selects[6]
        assert "brc_trade_aggregates.review_id = brc_trade_reviews.review_id" in (
            overview_selects[6]
        )
        assert "limit" in overview_selects[6]

        assert facts.max_concurrent_tickets == 3
        assert facts.active_ticket_count == 0
        assert facts.runtime_freshness.value == "fresh"
        assert facts.latest_wallet_balance_at_claim is None
        assert facts.latest_available_margin_at_claim is None
        assert facts.execution_incident_count == 1
        assert facts.open_owner_incident_id is None
        assert facts.attention_incident_ids == ("incident:auto-retry",)
        assert facts.monitor_statuses == ("temporarily_unavailable", "running")
        assert facts.active_ticket_ids == ()
        assert facts.today_signal_count == 0
        assert facts.admitted_signal_count == 0
        assert facts.rejected_signal_count == 0
        assert facts.today_net_pnl.value == Decimal(0)
        assert facts.today_net_r.value == Decimal(0)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def _seed_overview_authority(dsn: str, *, now_ms: int) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO brc_runtime_profiles (
                    runtime_profile_id, venue_id, account_id, environment,
                    position_mode, status, updated_at_ms
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                "profile:owner-console",
                "binance-usdm",
                "owner-console-account",
                "live",
                "independent_sides",
                "active",
                now_ms - 10_000,
            )
            await connection.execute(
                """
                INSERT INTO brc_owner_policy_current (
                    owner_policy_id, policy_version, enabled,
                    new_entry_submit_enabled, priority_rank,
                    max_concurrent_tickets,
                    max_strategy_group_concurrent_tickets,
                    family_ticket_limits,
                    max_ticket_stop_risk_fraction,
                    max_gross_stop_risk_fraction,
                    max_ticket_initial_margin_fraction,
                    max_gross_initial_margin_utilization,
                    directional_stop_risk_limit_fraction,
                    min_materialization_ratio, max_leverage,
                    supported_margin_mode, post_stop_stress_multiple,
                    max_post_fill_stop_risk_overrun_fraction,
                    scope, updated_at_ms
                ) VALUES (
                    $1, 1, true, true, 100, 3, NULL, $2::jsonb,
                    0.02, 0.06, 0.30, 0.90, 0.04, 0.50, 10,
                    'cross', 2.0, 0.10, $3::jsonb, $4
                )
                """,
                "policy:owner-console",
                json.dumps(
                    {
                        "long_continuation": 1,
                        "opening_range": 2,
                        "rally_failure_short": 1,
                    }
                ),
                json.dumps(
                    {
                        "runtime_profile_id": "profile:owner-console",
                        "allowed_event_spec_ids": [],
                    }
                ),
                now_ms - 10_000,
            )
            await connection.execute(
                """
                INSERT INTO brc_account_exposure_current (
                    venue_id, account_id, gross_notional, gross_risk_at_stop,
                    current_reserved_margin, active_ticket_count,
                    projection_version, updated_at_ms
                ) VALUES ($1, $2, 0, 0, 0, 0, 1, $3)
                """,
                "binance-usdm",
                "owner-console-account",
                now_ms - 10_000,
            )
            await connection.execute(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    $1, NULL, $2, 'open', $2, 'account_capacity', $3,
                    '{}'::jsonb, $4, NULL
                )
                """,
                "incident:auto-retry",
                "post_fill_risk_facts_unavailable",
                "binance-usdm:owner-console-account",
                now_ms - 8_000,
            )
            await connection.execute(
                """
                INSERT INTO brc_monitor_current (
                    monitor_key, owner_status, summary, intervention,
                    ticket_id, incident_id, updated_at_ms, projection_version
                ) VALUES ($1, $2, $3, $4, NULL, NULL, $5, 1)
                """,
                "monitor:owner-console",
                "running",
                "runtime healthy",
                "no action",
                now_ms - 10_000,
            )
            await connection.execute(
                """
                INSERT INTO brc_monitor_current (
                    monitor_key, owner_status, summary, intervention,
                    ticket_id, incident_id, updated_at_ms, projection_version
                ) VALUES ($1, $2, $3, $4, NULL, $5, $6, 1)
                """,
                "monitor:auto-retry",
                "temporarily_unavailable",
                "automatic retry pending",
                "automatic retry",
                "incident:auto-retry",
                now_ms - 8_000,
            )
    finally:
        await connection.close()


def _asyncpg_dsn(dsn: str) -> str:
    return (
        make_url(dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
