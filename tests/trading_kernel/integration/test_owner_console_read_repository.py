from __future__ import annotations

import json
from decimal import Decimal

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.application.owner_console.models import (
    SignalListQuery,
    TradeListQuery,
)
from src.trading_kernel.application.owner_console.overview import (
    build_owner_overview,
)
from src.trading_kernel.application.owner_console.signals import (
    SignalFactsContradiction,
    SignalNotFound,
    build_signal_detail,
    build_signal_page,
)
from src.trading_kernel.application.owner_console.trades import build_trade_page
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


async def test_signal_cursor_is_stable_across_same_timestamp_page_boundary(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_signals(owner_read_dsn)
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
            transaction = connection.get_transaction()
            repository = PostgresOwnerReadRepository(connection)
            first = build_signal_page(
                await repository.read_signal_page_facts(
                    SignalListQuery(
                        from_ms=1_799_999_700_000,
                        to_ms=1_800_000_100_000,
                        limit=2,
                    )
                )
            )
            assert first.next_cursor is not None
            second = build_signal_page(
                await repository.read_signal_page_facts(
                    SignalListQuery(
                        from_ms=1_799_999_700_000,
                        to_ms=1_800_000_100_000,
                        limit=2,
                        cursor=first.next_cursor,
                    )
                )
            )
            assert connection.get_transaction() is transaction

        assert [item.signal_event_id for item in first.items] == [
            "signal:z",
            "signal:y",
        ]
        assert [item.signal_event_id for item in second.items] == [
            "signal:x",
            "signal:w",
        ]
        assert first.next_cursor is not None
        assert second.next_cursor is None
        assert len(statements) == 3  # SET TRANSACTION plus two list SELECTs.
        list_selects = [item for item in statements if item.startswith("select")]
        assert len(list_selects) == 2
        assert "brc_signal_events" in list_selects[0]
        assert "brc_admission_decisions" in list_selects[0]
        assert "brc_shadow_outcomes_current" in list_selects[0]
        assert "occurred_at_ms >=" in list_selects[0]
        assert "occurred_at_ms <" in list_selects[0]
        assert "order by brc_signal_events.occurred_at_ms desc" in list_selects[0]
        assert "brc_signal_events.signal_event_id desc" in list_selects[0]
        assert "limit" in list_selects[0]
        assert "(brc_signal_events.occurred_at_ms, " in list_selects[1]
        assert "brc_signal_events.signal_event_id) <" in list_selects[1]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_signal_list_applies_exact_window_and_all_optional_filters(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_signals(owner_read_dsn)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            page = build_signal_page(
                await repository.read_signal_page_facts(
                    SignalListQuery(
                        from_ms=1_800_000_000_000,
                        to_ms=1_800_000_000_001,
                        strategy_group_id="strategy-group:alpha",
                        exchange_instrument_id="ETHUSDT",
                        position_side="short",
                        decision_status="rejected",
                    )
                )
            )
            admitted = build_signal_page(
                await repository.read_signal_page_facts(
                    SignalListQuery(
                        from_ms=1_799_999_700_000,
                        to_ms=1_800_000_100_000,
                        decision_status="admitted",
                    )
                )
            )
            upper_exclusive = build_signal_page(
                await repository.read_signal_page_facts(
                    SignalListQuery(
                        from_ms=1_799_999_700_000,
                        to_ms=1_800_000_000_000,
                    )
                )
            )

        assert [item.signal_event_id for item in page.items] == ["signal:y"]
        assert admitted.items == ()
        assert [item.signal_event_id for item in upper_exclusive.items] == [
            "signal:w"
        ]
    finally:
        await engine.dispose()


async def test_signal_detail_reads_exact_identity_bound_facts_and_decimal_shadow(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_signals(owner_read_dsn)
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
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_signal_detail_facts("signal:z")
            assert connection.get_transaction() is transaction

        detail = build_signal_detail(facts)
        assert detail.signal.signal_event_id == "signal:z"
        assert detail.why_no_ticket == "gross_stop_risk_capacity_exhausted"
        assert [fact.fact_definition_id for fact in detail.fact_snapshots] == [
            "fact:condition",
            "fact:reference",
        ]
        assert detail.shadow_summary is not None
        assert detail.shadow_summary.mfe_r == Decimal(
            "1.250000000000000001"
        )
        assert detail.shadow_summary.mae_r == Decimal(
            "-0.400000000000000001"
        )
        assert detail.shadow_summary.observed_through_ms == 1_800_000_900_000
        assert [ref.identity for ref in detail.evidence] == [
            "signal:z",
            "admission:z",
            "shadow:z",
            "signal-fact:signal:z:fact:condition",
            "signal-fact:signal:z:fact:reference",
        ]
        assert len(statements) == 4
        assert "brc_signal_events.signal_event_id =" in statements[0]
        assert "brc_admission_decisions.signal_event_id =" in statements[1]
        assert "brc_signal_fact_snapshots.signal_event_id =" in statements[2]
        assert "order by brc_signal_fact_snapshots.fact_definition_id" in (
            statements[2]
        )
        assert "limit" in statements[2]
        assert "brc_shadow_outcomes_current.admission_decision_id =" in (
            statements[3]
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_signal_detail_missing_identity_is_explicit(
    owner_read_dsn: str,
) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            with pytest.raises(SignalNotFound, match="signal:missing"):
                await PostgresOwnerReadRepository(
                    connection
                ).read_signal_detail_facts("signal:missing")
    finally:
        await engine.dispose()


async def test_signal_detail_rejects_persisted_identity_mismatch(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_signals(
        owner_read_dsn,
        admission_strategy_group_override="strategy-group:wrong",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            with pytest.raises(
                SignalFactsContradiction,
                match="signal and admission identity mismatch",
            ):
                await PostgresOwnerReadRepository(
                    connection
                ).read_signal_detail_facts("signal:z")
    finally:
        await engine.dispose()


async def test_signal_detail_rejects_more_than_256_fact_snapshots(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_signals(owner_read_dsn, fact_count=257)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            with pytest.raises(
                SignalFactsContradiction,
                match="more than 256 fact snapshots",
            ):
                await PostgresOwnerReadRepository(
                    connection
                ).read_signal_detail_facts("signal:z")
    finally:
        await engine.dispose()


async def test_trade_list_cursor_is_stable_for_active_and_terminal_mix(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
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
            transaction = connection.get_transaction()
            repository = PostgresOwnerReadRepository(connection)
            first = build_trade_page(
                await repository.read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_799_999_000_000,
                        to_ms=1_800_001_000_000,
                        limit=2,
                    )
                )
            )
            assert first.next_cursor is not None
            second = build_trade_page(
                await repository.read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_799_999_000_000,
                        to_ms=1_800_001_000_000,
                        limit=2,
                        cursor=first.next_cursor,
                    )
                )
            )
            assert connection.get_transaction() is transaction

        assert [item.ticket_id for item in first.items] == [
            "ticket:z",
            "ticket:y",
        ]
        assert [item.ticket_id for item in second.items] == [
            "ticket:x",
            "ticket:w",
        ]
        list_selects = [item for item in statements if item.startswith("select")]
        assert len(list_selects) == 2
        assert "brc_trade_tickets" in list_selects[0]
        assert "brc_trade_aggregates" in list_selects[0]
        assert "brc_trade_reviews" in list_selects[0]
        assert "brc_trade_reviews.review_id = brc_trade_aggregates.review_id" in (
            list_selects[0]
        )
        assert "brc_runtime_incidents" in list_selects[0]
        assert "brc_trade_events" in list_selects[0]
        assert "brc_runtime_incidents.ticket_id = brc_trade_tickets.ticket_id" in (
            list_selects[0]
        )
        assert "brc_runtime_incidents.status =" in list_selects[0]
        assert list_selects[0].count("limit") >= 4
        assert "count(" not in list_selects[0]
        assert "order by brc_trade_tickets.created_at_ms desc" in list_selects[0]
        assert "brc_trade_tickets.ticket_id desc" in list_selects[0]
        assert "(brc_trade_tickets.created_at_ms, " in list_selects[1]
        assert "brc_trade_tickets.ticket_id) <" in list_selects[1]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_trade_list_applies_window_and_all_exact_filters(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            filtered = build_trade_page(
                await repository.read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_800_000_000_000,
                        to_ms=1_800_000_000_001,
                        strategy_group_id="strategy-group:alpha",
                        exchange_instrument_id="BTCUSDT",
                        position_side="long",
                        aggregate_status="position_protected",
                    )
                )
            )
            terminal = build_trade_page(
                await repository.read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_799_999_000_000,
                        to_ms=1_800_001_000_000,
                        aggregate_status="terminal",
                    )
                )
            )
            upper_exclusive = build_trade_page(
                await repository.read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_799_999_000_000,
                        to_ms=1_800_000_000_000,
                    )
                )
            )

        assert [item.ticket_id for item in filtered.items] == ["ticket:z"]
        assert [item.ticket_id for item in terminal.items] == [
            "ticket:y",
            "ticket:x",
            "ticket:w",
            "ticket:v",
        ]
        assert [item.ticket_id for item in upper_exclusive.items] == [
            "ticket:w",
            "ticket:v",
        ]
    finally:
        await engine.dispose()


async def test_trade_list_uses_only_current_review_and_keeps_incident_bound(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            page = build_trade_page(
                await PostgresOwnerReadRepository(
                    connection
                ).read_trade_page_facts(
                    TradeListQuery(
                        from_ms=1_799_999_000_000,
                        to_ms=1_800_001_000_000,
                    )
                )
            )

        rows = {item.ticket_id: item for item in page.items}
        assert rows["ticket:y"].review_id == "review:y:v2"
        assert rows["ticket:y"].review_revision == 2
        assert rows["ticket:y"].net_pnl.value == Decimal("3.5100")
        assert rows["ticket:y"].exit_reason == "strategy_exit"
        assert rows["ticket:y"].exit_reason_unavailable_reason is None
        assert [
            ref.identity
            for ref in rows["ticket:y"].evidence
            if ref.kind == "review"
        ] == ["review:y:v2"]
        assert [
            ref.identity
            for ref in rows["ticket:y"].evidence
            if ref.kind == "event"
        ] == ["event:y:exit-requested"]
        assert rows["ticket:z"].lifecycle_stage == "protection"
        assert rows["ticket:z"].net_pnl.unavailable_reason == "ticket_active"
        assert rows["ticket:z"].attention_items == (
            "open_incident:incident:z:older-open",
        )
        assert [
            ref.identity
            for ref in rows["ticket:z"].evidence
            if ref.kind == "incident"
        ] == ["incident:z:older-open", "incident:z:resolved:21"]
        assert rows["ticket:x"].net_pnl.unavailable_reason == "review_missing"
        assert rows["ticket:w"].funding.unavailable_reason == (
            "funding_unavailable"
        )
        assert rows["ticket:w"].net_pnl.value is None
        assert rows["ticket:v"].net_pnl.unavailable_reason == (
            "incomplete_review_economics"
        )
        assert rows["ticket:v"].exit_reason is None
        assert rows["ticket:v"].exit_reason_unavailable_reason == (
            "exit_reason_evidence_missing"
        )
    finally:
        await engine.dispose()


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
            if statement.startswith(("select", "with"))
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
        assert "created_at_ms >=" in overview_selects[6]
        assert "sum(" in overview_selects[6]
        assert "count(*) over" not in " ".join(overview_selects)
        assert "count() over" not in " ".join(overview_selects)

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


async def test_overview_freshness_uses_stalest_required_projection(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    exposure_updated_at_ms = now_ms - 120_000
    await _seed_overview_authority(
        owner_read_dsn,
        now_ms=now_ms,
        exposure_updated_at_ms=exposure_updated_at_ms,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.runtime_freshness.value == "stale"
        assert facts.freshness_evidence_identity == (
            "account:binance-usdm:owner-console-account"
        )
        assert facts.freshness_evidence_at_ms == exposure_updated_at_ms
    finally:
        await engine.dispose()


async def test_overview_authority_ignores_disabled_policy_binding(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_additional_owner_policy(
        owner_read_dsn,
        now_ms=now_ms,
        owner_policy_id="policy:disabled",
        enabled=False,
        priority_rank=1,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.max_concurrent_tickets == 3
        assert "multiple_configured_owner_authorities" not in (
            facts.contradictory_fact_reasons
        )
        assert facts.attention_incident_ids == ("incident:auto-retry",)
    finally:
        await engine.dispose()


async def test_overview_ambiguous_authority_does_not_scope_account_queries(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_additional_owner_policy(
        owner_read_dsn,
        now_ms=now_ms,
        owner_policy_id="policy:also-enabled",
        enabled=True,
        priority_rank=101,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.max_concurrent_tickets is None
        assert facts.active_ticket_count is None
        assert facts.attention_incident_ids == ()
        assert facts.contradictory_fact_reasons == (
            "multiple_configured_owner_authorities",
        )
    finally:
        await engine.dispose()


async def test_overview_without_authority_keeps_runtime_global_incident(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_runtime_incident(
        owner_read_dsn,
        incident_id="incident:runtime-global",
        entry_block_scope="runtime",
        entry_block_key="global",
        opened_at_ms=now_ms - 5_000,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.open_owner_incident_id == "incident:runtime-global"
        assert facts.open_owner_incident_opened_at_ms == now_ms - 5_000
        assert facts.execution_incident_count == 1
    finally:
        await engine.dispose()


async def test_overview_incident_limit_keeps_older_owner_intervention(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_attention_incidents(
        owner_read_dsn,
        count=21,
        newest_opened_at_ms=now_ms - 1_000,
    )
    await _seed_runtime_incident(
        owner_read_dsn,
        incident_id="incident:older-intervention",
        entry_block_scope="runtime",
        entry_block_key="global",
        opened_at_ms=now_ms - 120_000,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.open_owner_incident_id == "incident:older-intervention"
        assert facts.open_owner_incident_opened_at_ms == now_ms - 120_000
        assert len(facts.attention_incident_ids) == 20
        assert "open_incident_limit_reached" in tuple(
            gap.reason for gap in facts.evidence_gaps
        )
    finally:
        await engine.dispose()


async def test_overview_monitor_limit_keeps_older_owner_intervention(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_normal_monitors(
        owner_read_dsn,
        count=101,
        newest_updated_at_ms=now_ms - 500,
    )
    await _seed_owner_intervention_monitor(
        owner_read_dsn,
        monitor_key="monitor:older-intervention",
        updated_at_ms=now_ms - 120_000,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=1_799_913_600_000,
                now_ms=now_ms,
            )

        assert facts.needs_intervention_monitor_key == (
            "monitor:older-intervention"
        )
        assert facts.needs_intervention_monitor_updated_at_ms == (
            now_ms - 120_000
        )
        assert len(facts.monitor_keys) == 100
        assert "monitor_limit_reached" in tuple(
            gap.reason for gap in facts.evidence_gaps
        )
        overview = build_owner_overview(facts, now_ms=now_ms)
        assert overview.conclusion.level == "intervention"
        assert overview.conclusion.evidence[0].identity == (
            "monitor:older-intervention"
        )
    finally:
        await engine.dispose()


async def test_overview_aggregates_all_current_reviews_beyond_one_hundred(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    day_start_ms = 1_799_913_600_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_current_reviews(
        owner_read_dsn,
        count=101,
        created_at_ms=day_start_ms + 1_000,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=day_start_ms,
                now_ms=now_ms,
            )

        assert facts.today_net_pnl.value == Decimal("126.25")
        assert facts.today_net_r.value == Decimal("50.5")
        assert "current_review_limit_reached" not in tuple(
            gap.reason for gap in facts.evidence_gaps
        )
    finally:
        await engine.dispose()


async def test_overview_missing_review_economics_key_is_unavailable(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    day_start_ms = 1_799_913_600_000
    malformed_review_id = "review:owner-console:2"
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    await _seed_current_reviews(
        owner_read_dsn,
        count=2,
        created_at_ms=day_start_ms + 1_000,
        malformed_review_number=2,
        missing_metric_key="planned_r_multiple",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_overview_facts(
                day_start_ms=day_start_ms,
                now_ms=now_ms,
            )

        assert facts.today_net_pnl.value is None
        assert facts.today_net_pnl.unavailable_reason == (
            "incomplete_review_economics"
        )
        assert facts.today_net_r.value is None
        assert facts.today_net_r.unavailable_reason == (
            "incomplete_review_economics"
        )
        assert facts.evidence_gaps[0].reason == (
            "incomplete_review_economics"
        )
        assert facts.evidence_gaps[0].evidence.identity == malformed_review_id
        assert facts.evidence_gaps[0].evidence.occurred_at_ms == (
            day_start_ms + 1_002
        )
    finally:
        await engine.dispose()


async def _seed_overview_authority(
    dsn: str,
    *,
    now_ms: int,
    exposure_updated_at_ms: int | None = None,
) -> None:
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
                exposure_updated_at_ms or now_ms - 10_000,
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


async def _seed_additional_owner_policy(
    dsn: str,
    *,
    now_ms: int,
    owner_policy_id: str,
    enabled: bool,
    priority_rank: int,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
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
                $1, 1, $2, true, $3, 3, NULL, '{}'::jsonb,
                0.02, 0.06, 0.30, 0.90, 0.04, 0.50, 10,
                'cross', 2.0, 0.10, $4::jsonb, $5
            )
            """,
            owner_policy_id,
            enabled,
            priority_rank,
            json.dumps(
                {
                    "runtime_profile_id": "profile:owner-console",
                    "allowed_event_spec_ids": [],
                }
            ),
            now_ms - 10_000,
        )
    finally:
        await connection.close()


async def _seed_runtime_incident(
    dsn: str,
    *,
    incident_id: str,
    entry_block_scope: str,
    entry_block_key: str,
    opened_at_ms: int,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(
            """
            INSERT INTO brc_runtime_incidents (
                incident_id, ticket_id, incident_kind, status,
                first_blocker, entry_block_scope, entry_block_key,
                details, opened_at_ms, resolved_at_ms
            ) VALUES (
                $1, NULL, 'runtime_fence', 'open', 'hard_safety_stop',
                $2, $3, '{}'::jsonb, $4, NULL
            )
            """,
            incident_id,
            entry_block_scope,
            entry_block_key,
            opened_at_ms,
        )
    finally:
        await connection.close()


async def _seed_attention_incidents(
    dsn: str,
    *,
    count: int,
    newest_opened_at_ms: int,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(
            """
            INSERT INTO brc_runtime_incidents (
                incident_id, ticket_id, incident_kind, status,
                first_blocker, entry_block_scope, entry_block_key,
                details, opened_at_ms, resolved_at_ms
            )
            SELECT
                'incident:attention:' || series::text,
                NULL,
                'post_fill_risk_facts_unavailable',
                'open',
                'post_fill_risk_facts_unavailable',
                'account_capacity',
                'binance-usdm:owner-console-account',
                '{}'::jsonb,
                $1::bigint - (series - 1) * 1000,
                NULL
            FROM generate_series(1, $2) AS series
            """,
            newest_opened_at_ms,
            count,
        )
    finally:
        await connection.close()


async def _seed_normal_monitors(
    dsn: str,
    *,
    count: int,
    newest_updated_at_ms: int,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(
            """
            INSERT INTO brc_monitor_current (
                monitor_key, owner_status, summary, intervention,
                ticket_id, incident_id, updated_at_ms, projection_version
            )
            SELECT
                'monitor:normal:' || series::text,
                'running',
                'runtime healthy',
                'no action',
                NULL,
                NULL,
                $1::bigint - (series - 1) * 1000,
                1
            FROM generate_series(1, $2) AS series
            """,
            newest_updated_at_ms,
            count,
        )
    finally:
        await connection.close()


async def _seed_owner_intervention_monitor(
    dsn: str,
    *,
    monitor_key: str,
    updated_at_ms: int,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        await connection.execute(
            """
            INSERT INTO brc_monitor_current (
                monitor_key, owner_status, summary, intervention,
                ticket_id, incident_id, updated_at_ms, projection_version
            ) VALUES (
                $1, 'needs_intervention', 'owner action required',
                'follow official recovery', NULL, NULL, $2, 1
            )
            """,
            monitor_key,
            updated_at_ms,
        )
    finally:
        await connection.close()


async def _seed_current_reviews(
    dsn: str,
    *,
    count: int,
    created_at_ms: int,
    malformed_review_number: int | None = None,
    missing_metric_key: str | None = None,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    digest = "sha256:" + "a" * 64
    try:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms,
                    abandoned_at_ms, abandon_reason_code
                ) VALUES (
                    'universe:owner-console', 'strategy-group:test',
                    'event-spec:test', 1, $1, 'active', $2, $2,
                    NULL, NULL, NULL
                )
                """,
                digest,
                created_at_ms,
            )
            await connection.execute(
                """
                INSERT INTO brc_trade_tickets (
                    ticket_id, exposure_episode_id, signal_event_id,
                    strategy_group_id, strategy_version_id, event_spec_id,
                    universe_version_id, universe_semantic_digest,
                    runtime_profile_id, owner_policy_id, owner_policy_version,
                    runtime_scope_id, runtime_scope_version, account_id,
                    venue_id, exchange_instrument_id, position_side,
                    netting_domain_key, active_netting_domain_key,
                    exposure_family, active_family_ticket_count_at_claim,
                    family_ticket_limit, directional_risk_at_stop_at_claim,
                    directional_stop_risk_limit_fraction,
                    min_materialization_ratio, minimum_stop_risk_budget,
                    exit_policy_id, exit_policy_semantic_hash,
                    entry_reference_price, quantity, notional,
                    capacity_claim_id, planned_stop_risk_budget,
                    post_fill_stop_risk_limit, selected_leverage,
                    leverage_change_required, reserved_margin,
                    risk_reservation_basis, margin_mode,
                    cross_margin_stress_model_id, post_stop_stress_multiple,
                    claim_stress_proof_digest, risk_at_stop,
                    entry_order_type, entry_limit_price, initial_stop_price,
                    pre_tp1_reclaim_price, exposure_session_end_ms,
                    take_profit_prices, take_profit_quantities, fact_digest,
                    decision_digest, status, created_at_ms, expires_at_ms,
                    terminal_at_ms
                )
                SELECT
                    'ticket:review:' || series::text,
                    'episode:review:' || series::text,
                    'signal:review:' || series::text,
                    'strategy-group:test', 'strategy-version:test',
                    'event-spec:test', 'universe:owner-console', $1,
                    'profile:owner-console', 'policy:owner-console', 1,
                    'runtime-scope:test', 1, 'owner-console-account',
                    'binance-usdm', 'BTCUSDT', 'long',
                    'binance-usdm:owner-console-account:BTCUSDT:long:'
                        || series::text,
                    NULL, 'opening_range', 0, 3, 0, 0.04, 0.5, 1,
                    'exit-policy:test', 'sha256:' || repeat('b', 64),
                    100, 1, 100, 'claim:test:' || series::text,
                    1, 1.1, 1, false, 100, 'stop_risk', 'cross',
                    'stress:test', 2, 'sha256:' || repeat('c', 64),
                    1, 'market', NULL, 99, NULL, NULL,
                    '[]'::jsonb, '[]'::jsonb,
                    'sha256:' || repeat('d', 64),
                    'sha256:' || repeat('e', 64),
                    'terminal', $2::bigint, $2::bigint + 60_000,
                    $2::bigint + 30_000
                FROM generate_series(1, $3) AS series
                """,
                digest,
                created_at_ms,
                count,
            )
            await connection.execute(
                """
                INSERT INTO brc_trade_aggregates (
                    ticket_id, status, version, last_event_sequence,
                    entry_lane_held, position_qty, average_fill_price,
                    actual_stop_risk, venue_reported_liquidation_price,
                    post_fill_risk_status, post_fill_disposition,
                    post_fill_stress_status, post_fill_stress_proof_digest,
                    protected_qty, entry_exchange_order_id,
                    initial_stop_exchange_order_id,
                    active_stop_exchange_order_id, active_stop_price,
                    tp1_exchange_order_id, tp1_target_qty, tp1_filled_qty,
                    break_even_floor_price,
                    pending_replaced_stop_exchange_order_id,
                    pending_stop_price, pending_stop_watermark_ms,
                    runner_stop_watermark_ms, pending_cancel_exchange_order_id,
                    exit_exchange_order_id, review_id, lifecycle_due_at_ms,
                    reconciliation_due_at_ms, updated_at_ms
                )
                SELECT
                    'ticket:review:' || series::text, 'terminal', 1, 1,
                    false, 0, 100, 1, NULL, 'within_limit', 'continue',
                    'within_limit', 'sha256:' || repeat('f', 64), 0,
                    'entry-order:' || series::text, NULL, NULL, NULL,
                    NULL, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL,
                    'exit-order:' || series::text,
                    'review:owner-console:' || series::text,
                    NULL, NULL, $1::bigint + 30_000
                FROM generate_series(1, $2) AS series
                """,
                created_at_ms,
                count,
            )
            await connection.execute(
                """
                INSERT INTO brc_trade_reviews (
                    review_id, ticket_id, revision, supersedes_review_id,
                    outcome, metrics, decision_impact, created_at_ms
                )
                SELECT
                    'review:owner-console:' || series::text,
                    'ticket:review:' || series::text,
                    1, NULL, 'complete',
                    CASE
                        WHEN series = $3::integer AND $4::text IS NOT NULL
                        THEN jsonb_build_object(
                            'economics_completeness', 'complete',
                            'net_pnl_quote', '1.25',
                            'planned_r_multiple', '0.5'
                        ) - $4::text
                        ELSE jsonb_build_object(
                            'economics_completeness', 'complete',
                            'net_pnl_quote', '1.25',
                            'planned_r_multiple', '0.5'
                        )
                    END,
                    '{}'::jsonb,
                    $1::bigint + series
                FROM generate_series(1, $2) AS series
                """,
                created_at_ms,
                count,
                malformed_review_number,
                missing_metric_key,
            )
    finally:
        await connection.close()


async def _seed_owner_console_trades(dsn: str) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    digest = "sha256:" + "a" * 64
    created_at_ms = 1_800_000_000_000
    tickets = (
        (
            "ticket:z",
            "strategy-group:alpha",
            "BTCUSDT",
            "long",
            "issued",
            created_at_ms,
            None,
            "active:ticket:z",
        ),
        (
            "ticket:y",
            "strategy-group:alpha",
            "ETHUSDT",
            "short",
            "terminal",
            created_at_ms,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:x",
            "strategy-group:beta",
            "BTCUSDT",
            "short",
            "terminal",
            created_at_ms,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:w",
            "strategy-group:beta",
            "SOLUSDT",
            "long",
            "terminal",
            created_at_ms - 100,
            created_at_ms + 30_000,
            None,
        ),
        (
            "ticket:v",
            "strategy-group:gamma",
            "BNBUSDT",
            "long",
            "terminal",
            created_at_ms - 200,
            created_at_ms + 30_000,
            None,
        ),
    )
    try:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms,
                    abandoned_at_ms, abandon_reason_code
                ) VALUES (
                    'universe:owner-console-trades', 'strategy-group:test',
                    'event-spec:test', 1, $1, 'active', $2, $2,
                    NULL, NULL, NULL
                )
                """,
                digest,
                created_at_ms,
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_tickets (
                    ticket_id, exposure_episode_id, signal_event_id,
                    strategy_group_id, strategy_version_id, event_spec_id,
                    universe_version_id, universe_semantic_digest,
                    runtime_profile_id, owner_policy_id, owner_policy_version,
                    runtime_scope_id, runtime_scope_version, account_id,
                    venue_id, exchange_instrument_id, position_side,
                    netting_domain_key, active_netting_domain_key,
                    exposure_family, active_family_ticket_count_at_claim,
                    family_ticket_limit, directional_risk_at_stop_at_claim,
                    directional_stop_risk_limit_fraction,
                    min_materialization_ratio, minimum_stop_risk_budget,
                    exit_policy_id, exit_policy_semantic_hash,
                    entry_reference_price, quantity, notional,
                    capacity_claim_id, planned_stop_risk_budget,
                    post_fill_stop_risk_limit, selected_leverage,
                    leverage_change_required, reserved_margin,
                    risk_reservation_basis, margin_mode,
                    cross_margin_stress_model_id, post_stop_stress_multiple,
                    claim_stress_proof_digest, risk_at_stop,
                    entry_order_type, entry_limit_price, initial_stop_price,
                    pre_tp1_reclaim_price, exposure_session_end_ms,
                    take_profit_prices, take_profit_quantities, fact_digest,
                    decision_digest, status, created_at_ms, expires_at_ms,
                    terminal_at_ms
                ) VALUES (
                    $1::varchar(160), 'episode:' || $1::varchar(160),
                    'signal:' || $1::varchar(160), $2::varchar(160),
                    'strategy-version:test', 'event-spec:test',
                    'universe:owner-console-trades', $9::text,
                    'profile:owner-console', 'policy:owner-console', 1,
                    'runtime-scope:test', 1, 'owner-console-account',
                    'binance-usdm', $3::varchar(160), $4::varchar(160),
                    'binance-usdm:owner-console-account:'
                        || $3::varchar(160) || ':' || $4::varchar(160),
                    $8::varchar(160), 'opening_range', 0, 3, 0, 0.04, 0.5, 1,
                    'exit-policy:test', 'sha256:' || repeat('b', 64),
                    100, 1, 100, 'claim:' || $1::varchar(160),
                    1, 1.1, 1, false, 100,
                    'stop_risk', 'cross', 'stress:test', 2,
                    'sha256:' || repeat('c', 64), 1, 'market', NULL, 99,
                    NULL, NULL, '[]'::jsonb, '[]'::jsonb,
                    'sha256:' || repeat('d', 64),
                    'sha256:' || repeat('e', 64), $5::varchar(160),
                    $6::bigint, $6::bigint + 60_000, $7::bigint
                )
                """,
                tuple((*ticket, digest) for ticket in tickets),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_aggregates (
                    ticket_id, status, version, last_event_sequence,
                    entry_lane_held, position_qty, average_fill_price,
                    actual_stop_risk, venue_reported_liquidation_price,
                    post_fill_risk_status, post_fill_disposition,
                    post_fill_stress_status, post_fill_stress_proof_digest,
                    protected_qty, entry_exchange_order_id,
                    initial_stop_exchange_order_id,
                    active_stop_exchange_order_id, active_stop_price,
                    tp1_exchange_order_id, tp1_target_qty, tp1_filled_qty,
                    break_even_floor_price,
                    pending_replaced_stop_exchange_order_id,
                    pending_stop_price, pending_stop_watermark_ms,
                    runner_stop_watermark_ms, pending_cancel_exchange_order_id,
                    exit_exchange_order_id, review_id, lifecycle_due_at_ms,
                    reconciliation_due_at_ms, updated_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160),
                    1, 1, false, 0, 100, 1, NULL,
                    'within_limit', 'continue', 'within_limit',
                    'sha256:' || repeat('f', 64), 0,
                    'entry:' || $1::varchar(160),
                    NULL, NULL, NULL, NULL, 0, 0, NULL, NULL, NULL,
                    NULL, NULL, NULL, 'exit:' || $1::varchar(160),
                    $3::varchar(160), NULL, NULL, $4::bigint
                )
                """,
                (
                    ("ticket:z", "position_protected", None, created_at_ms),
                    ("ticket:y", "terminal", "review:y:v2", created_at_ms),
                    ("ticket:x", "terminal", None, created_at_ms),
                    ("ticket:w", "terminal", "review:w:v1", created_at_ms),
                    ("ticket:v", "terminal", "review:v:v1", created_at_ms),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_reviews (
                    review_id, ticket_id, revision, supersedes_review_id,
                    outcome, metrics, decision_impact, created_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160), $3::bigint,
                    $4::varchar(160), 'terminal_flat', $5::jsonb, '{}',
                    $6::bigint
                )
                """,
                (
                    (
                        "review:y:v1",
                        "ticket:y",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "1000",
                                "trading_fees_quote": "1",
                                "funding_quote": "0",
                                "net_pnl_quote": "999",
                                "planned_r_multiple": "99",
                            }
                        ),
                        created_at_ms + 50_000,
                    ),
                    (
                        "review:y:v2",
                        "ticket:y",
                        2,
                        "review:y:v1",
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": "-0.0900",
                                "net_pnl_quote": "3.5100",
                                "planned_r_multiple": "0.4800",
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                    (
                        "review:w:v1",
                        "ticket:w",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "funding_unavailable",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": None,
                                "net_pnl_quote": None,
                                "planned_r_multiple": None,
                                "funding_unavailable_reason": (
                                    "overlapping_instrument_exposure"
                                ),
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                    (
                        "review:v:v1",
                        "ticket:v",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "4.0000",
                                "trading_fees_quote": "0.4000",
                                "funding_quote": "-0.0900",
                                "planned_r_multiple": "0.4800",
                            }
                        ),
                        created_at_ms + 40_000,
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    $1::varchar(160), 'ticket:y', $2::bigint,
                    'ExitRequested', $3::jsonb, $4::bigint
                )
                """,
                (
                    (
                        "event:y:exit-requested",
                        10,
                        json.dumps(
                            {
                                "event_id": "event:y:exit-requested",
                                "ticket_id": "ticket:y",
                                "sequence": 10,
                                "occurred_at_ms": created_at_ms + 20_000,
                                "reason": "strategy_exit",
                            }
                        ),
                        created_at_ms + 20_000,
                    ),
                    (
                        "event:y:exit-retry",
                        11,
                        json.dumps(
                            {
                                "event_id": "event:y:exit-retry",
                                "ticket_id": "ticket:y",
                                "sequence": 11,
                                "occurred_at_ms": created_at_ms + 21_000,
                                "reason": "recover_exit_rejection",
                            }
                        ),
                        created_at_ms + 21_000,
                    ),
                ),
            )
            await connection.execute(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    'incident:z:older-open', 'ticket:z', 'entry_outcome_unknown',
                    'open', 'exact recovery required', 'none', NULL, '{}',
                    $1, NULL
                )
                """,
                created_at_ms - 120_000,
            )
            await connection.executemany(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    'incident:z:resolved:' || $1::integer::text, 'ticket:z',
                    'recovered_incident', 'resolved', 'resolved', 'none', NULL,
                    '{}', $2::bigint, $2::bigint + 1
                )
                """,
                tuple(
                    (number, created_at_ms - 30_000 + number)
                    for number in range(1, 22)
                ),
            )
    finally:
        await connection.close()


async def _seed_owner_console_signals(
    dsn: str,
    *,
    admission_strategy_group_override: str | None = None,
    fact_count: int = 2,
) -> None:
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    digest = "sha256:" + "a" * 64
    signals = (
        (
            "signal:z",
            "episode:z",
            "scope:z",
            "strategy-group:alpha",
            "strategy-version:alpha",
            "BTCUSDT",
            "long",
            1_800_000_000_000,
        ),
        (
            "signal:y",
            "episode:y",
            "scope:y",
            "strategy-group:alpha",
            "strategy-version:alpha",
            "ETHUSDT",
            "short",
            1_800_000_000_000,
        ),
        (
            "signal:x",
            "episode:x",
            "scope:x",
            "strategy-group:beta",
            "strategy-version:beta",
            "BTCUSDT",
            "short",
            1_800_000_000_000,
        ),
        (
            "signal:w",
            "episode:w",
            "scope:w",
            "strategy-group:alpha",
            "strategy-version:alpha",
            "BTCUSDT",
            "long",
            1_799_999_800_000,
        ),
    )
    try:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO brc_strategy_universe_versions (
                    universe_version_id, strategy_group_id, event_spec_id,
                    universe_version, semantic_digest, lifecycle_state,
                    installed_at_ms, activated_at_ms, retired_at_ms,
                    abandoned_at_ms, abandon_reason_code
                ) VALUES (
                    'universe:owner-console-signals', 'strategy-group:alpha',
                    'event-spec:signal', 1, $1, 'active',
                    1799999700000, 1799999700000, NULL, NULL, NULL
                )
                """,
                digest,
            )
            await connection.executemany(
                """
                INSERT INTO brc_signal_events (
                    signal_event_id, exposure_episode_id, runtime_scope_id,
                    runtime_scope_version, strategy_group_id,
                    strategy_version_id, event_spec_id, universe_version_id,
                    universe_semantic_digest, exchange_instrument_id,
                    position_side, fact_digest, occurred_at_ms, observed_at_ms,
                    expires_at_ms
                ) VALUES (
                    $1, $2, $3, 1, $4, $5, 'event-spec:signal',
                    'universe:owner-console-signals', $9, $6, $7,
                    'sha256:' || repeat('b', 64), $8::bigint,
                    $8::bigint + 1000, $8::bigint + 60000
                )
                """,
                [(*signal, digest) for signal in signals],
            )
            await connection.executemany(
                """
                INSERT INTO brc_admission_decisions (
                    admission_decision_id, signal_event_id,
                    exposure_episode_id, strategy_group_id,
                    strategy_version_id, event_spec_id, universe_version_id,
                    universe_semantic_digest, runtime_profile_id,
                    runtime_scope_id, runtime_scope_version, owner_policy_id,
                    owner_policy_version, venue_id, account_id,
                    exchange_instrument_id, position_side, exposure_family,
                    candidate_rank, candidate_count, candidate_set_digest,
                    candidate_set_summary, portfolio_usage, decision_status,
                    first_blocker, binding_constraint, capacity_claim_id,
                    ticket_id, entry_admission_snapshot_digest,
                    decision_digest, decided_at_ms
                ) VALUES (
                    'admission:' || substring($1 from 8), $1, $2, $4, $5,
                    'event-spec:signal', 'universe:owner-console-signals', $9,
                    'profile:owner-console', $3, 1, 'policy:owner-console', 1,
                    'binance-usdm', 'owner-console-account', $6, $7,
                    'opening_range', 1, 1,
                    'sha256:' || repeat('c', 64), '{}'::jsonb, '{}'::jsonb,
                    'rejected', 'gross_stop_risk_capacity_exhausted',
                    'gross_stop_risk', NULL, NULL, NULL,
                    'sha256:' || repeat('d', 64), $8::bigint + 2000
                )
                """,
                [
                    (
                        signal_event_id,
                        exposure_episode_id,
                        runtime_scope_id,
                        (
                            admission_strategy_group_override
                            if signal_event_id == "signal:z"
                            and admission_strategy_group_override is not None
                            else strategy_group_id
                        ),
                        strategy_version_id,
                        exchange_instrument_id,
                        position_side,
                        occurred_at_ms,
                        digest,
                    )
                    for (
                        signal_event_id,
                        exposure_episode_id,
                        runtime_scope_id,
                        strategy_group_id,
                        strategy_version_id,
                        exchange_instrument_id,
                        position_side,
                        occurred_at_ms,
                    ) in signals
                ],
            )
            fact_rows = (
                [
                    (
                        "signal:z",
                        "fact:condition",
                        "condition",
                        "true",
                        True,
                    ),
                    (
                        "signal:z",
                        "fact:reference",
                        "protection_reference",
                        '"99.125000000000000001"',
                        True,
                    ),
                ]
                if fact_count == 2
                else [
                    (
                        "signal:z",
                        f"fact:{index:03d}",
                        "condition",
                        "true",
                        True,
                    )
                    for index in range(fact_count)
                ]
            )
            await connection.executemany(
                """
                INSERT INTO brc_signal_fact_snapshots (
                    signal_event_id, fact_definition_id, role, value,
                    satisfied, observed_at_ms, valid_until_ms,
                    projection_version
                ) VALUES (
                    $1, $2, $3, $4::jsonb, $5,
                    1800000001000, 1800000060000, 1
                )
                """,
                fact_rows,
            )
            await connection.execute(
                """
                INSERT INTO brc_shadow_outcomes_current (
                    shadow_outcome_id, admission_decision_id, status,
                    evaluation_kind, exchange_instrument_id, position_side,
                    timeframe, entry_reference_price, initial_stop_price,
                    initial_risk_per_unit, horizon_start_ms, horizon_end_ms,
                    claim_owner, claim_token, lease_until_ms,
                    max_favorable_price, max_adverse_price, mfe_r, mae_r,
                    observed_through_ms, completion_reason, projection_version,
                    created_at_ms, completed_at_ms
                ) VALUES (
                    'shadow:z', 'admission:z', 'completed',
                    'fixed_horizon_excursion_v1', 'BTCUSDT', 'long', '15m',
                    100.000000000000000001, 99.000000000000000001,
                    1.000000000000000000, 1800000000000, 1800000900000,
                    NULL, NULL, NULL, 101.250000000000000002,
                    99.599999999999999999, 1.250000000000000001,
                    -0.400000000000000001, 1800000900000,
                    'horizon_complete', 1, 1800000002000, 1800000900000
                )
                """
            )
    finally:
        await connection.close()


def _asyncpg_dsn(dsn: str) -> str:
    return (
        make_url(dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
