from __future__ import annotations

import json
from decimal import Decimal

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.application.owner_console.causality import (
    ContradictoryFacts,
    build_trade_causality,
)
from src.trading_kernel.application.owner_console.models import (
    ReviewListQuery,
    SignalListQuery,
    TradeListQuery,
)
from src.trading_kernel.application.owner_console.overview import (
    build_owner_overview,
)
from src.trading_kernel.application.owner_console.programmatic_review import (
    ProgrammaticReviewContradiction,
    build_programmatic_review,
    build_review_center,
)
from src.trading_kernel.application.owner_console.signals import (
    SignalFactsContradiction,
    SignalNotFound,
    build_signal_detail,
    build_signal_page,
)
from src.trading_kernel.application.owner_console.trades import (
    TradeFactsContradiction,
    build_trade_page,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.ticket import TicketStatus, TradeTicket
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

_REVIEW_FILTER_HARD_CAP = 512


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


async def test_causality_nonexistent_ticket_returns_none_with_one_exact_read(
    owner_read_dsn: str,
) -> None:
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
            ).read_trade_causality_facts("ticket:missing")
            assert connection.get_transaction() is transaction

        assert facts is None
        selects = [item for item in statements if item.startswith("select")]
        assert len(selects) == 1
        assert "brc_trade_tickets.ticket_id =" in selects[0]
        assert "brc_trade_aggregates" in selects[0]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_causality_reads_exact_bounded_histories_and_current_review(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_causality(owner_read_dsn)
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
            ).read_trade_causality_facts("ticket:causality")
            assert connection.get_transaction() is transaction

        assert facts is not None
        detail = build_trade_causality(facts)
        assert detail.exit_reason is not None
        assert detail.exit_reason.label == "Initial Stop"
        assert detail.annotations[-1].model_dump(mode="json") == {
            "kind": "exit",
            "occurred_at_ms": 1_800_000_090_000,
            "price": "103.00",
            "label": "Exit Fill",
            "evidence": [
                {
                    "kind": "review",
                    "identity": "review:causality:v2",
                    "occurred_at_ms": 1_800_000_100_000,
                },
                {
                    "kind": "command",
                    "identity": "command:exit:1",
                    "occurred_at_ms": 1_800_000_045_000,
                },
            ],
        }
        assert detail.raw_events[-1].event_type == "FutureLifecycleEvent"
        assert detail.raw_events[-1].classification == "unmapped"
        assert detail.raw_events[-1].stage == "review"
        assert [item.sequence for item in detail.raw_events] == list(range(1, 11))
        assert [item.command_id for item in detail.raw_commands] == [
            "command:entry:1",
            "command:exit:1",
        ]
        assert [item.incident_id for item in detail.raw_incidents] == [
            "incident:causality:1"
        ]

        selects = [item for item in statements if item.startswith("select")]
        assert len(selects) == 6
        assert "brc_trade_tickets.ticket_id =" in selects[0]
        assert "brc_signal_events.signal_event_id =" in selects[1]
        assert "brc_admission_decisions" in selects[1]
        assert "brc_trade_events.ticket_id =" in selects[2]
        assert "order by brc_trade_events.sequence asc" in selects[2]
        assert "limit" in selects[2]
        assert "brc_exchange_commands.ticket_id =" in selects[3]
        assert "brc_exchange_commands.created_at_ms asc" in selects[3]
        assert "brc_exchange_commands.command_id asc" in selects[3]
        assert "limit" in selects[3]
        assert "brc_runtime_incidents.ticket_id =" in selects[4]
        assert "brc_runtime_incidents.opened_at_ms asc" in selects[4]
        assert "limit" in selects[4]
        assert "brc_trade_reviews.review_id =" in selects[5]
        assert "brc_candles" not in " ".join(selects)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_causality_identity_mismatch_fails_closed(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_causality(
        owner_read_dsn,
        admission_strategy_group_id="strategy-group:contradictory",
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_trade_causality_facts("ticket:causality")

        assert facts is not None
        with pytest.raises(
            ContradictoryFacts,
            match="Ticket and AdmissionDecision identity mismatch",
        ):
            build_trade_causality(facts)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("fact_field", "seed_kwargs", "maximum"),
    (
        ("events", {"event_count": 512}, 512),
        ("commands", {"command_count": 128}, 128),
        ("incidents", {"incident_count": 64}, 64),
    ),
)
async def test_causality_history_exact_cap_succeeds(
    owner_read_dsn: str,
    fact_field: str,
    seed_kwargs: dict[str, int],
    maximum: int,
) -> None:
    await _seed_owner_console_causality(owner_read_dsn, **seed_kwargs)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            facts = await PostgresOwnerReadRepository(
                connection
            ).read_trade_causality_facts("ticket:causality")

        assert facts is not None
        assert len(getattr(facts, fact_field)) == maximum
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("seed_kwargs", "message"),
    (
        ({"event_count": 513}, "Trade Events exceed hard maximum 512"),
        ({"command_count": 129}, "Exchange Commands exceed hard maximum 128"),
        ({"incident_count": 65}, "Incidents exceed hard maximum 64"),
    ),
)
async def test_causality_history_cap_plus_one_fails_closed(
    owner_read_dsn: str,
    seed_kwargs: dict[str, int],
    message: str,
) -> None:
    await _seed_owner_console_causality(owner_read_dsn, **seed_kwargs)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            with pytest.raises(ContradictoryFacts, match=message):
                await PostgresOwnerReadRepository(
                    connection
                ).read_trade_causality_facts("ticket:causality")
    finally:
        await engine.dispose()


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


async def test_review_center_is_terminal_current_review_and_cursor_bounded(
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
            first_facts = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    limit=2,
                )
            )
            first = build_review_center(first_facts)
            assert first.next_cursor is not None
            second_facts = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    limit=2,
                    cursor=first.next_cursor,
                )
            )
            second = build_review_center(second_facts)
            assert connection.get_transaction() is transaction

        first_reviews = {
            item.review.ticket_id: build_programmatic_review(item.review)
            for item in first_facts.items[:2]
        }
        assert first_facts.items[0].review.current_review_id == "review:y:v2"
        assert first_reviews["ticket:y"].economic_summary.net_pnl.value == (
            Decimal("3.5100")
        )
        assert first_reviews["ticket:y"].execution_classification == (
            "recovered_incident"
        )
        assert [
            ref.identity
            for ref in first_reviews["ticket:y"].sentences[0].evidence
        ] == [
            "event:y:entry-filled",
            "event:y:initial-stop-confirmed",
            "event:y:exit-requested",
            "event:y:position-flat-confirmed",
            "event:y:reconciliation-matched",
            "event:y:budget-settled",
            "incident:y:resolved",
        ]
        assert first_facts.items[0].review.current_review_evidence is not None
        assert (
            first_facts.items[0].review.current_review_evidence.identity
            == "review:y:v2"
        )
        assert first_reviews["ticket:x"].execution_classification == (
            "waiting_review"
        )
        assert first.sample_count == 2
        assert first.net_pnl.value is None
        assert first.incomplete_review_count == 1
        assert first.strategy_group_samples[0].strategy_group_id == (
            "strategy-group:alpha"
        )
        assert second.sample_count == 2
        assert second.incomplete_review_count == 2
        second_reviews = {
            item.review.ticket_id: build_programmatic_review(item.review)
            for item in second_facts.items[:2]
        }
        assert second_reviews["ticket:w"].execution_classification == (
            "evidence_incomplete"
        )
        assert second_facts.items[0].review.incident_ids == (
            "incident:w:open",
        )
        selects = [
            statement
            for statement in statements
            if statement.startswith(("select", "with"))
        ]
        assert len(selects) == 4
        ticket_selects = [statement for statement in selects if "brc_trade_tickets" in statement]
        assert len(ticket_selects) == 2
        assert "brc_trade_aggregates.status =" in ticket_selects[0]
        assert "brc_trade_tickets.terminal_at_ms >=" in ticket_selects[0]
        assert "brc_trade_tickets.terminal_at_ms <" in ticket_selects[0]
        assert "brc_trade_reviews.review_id = brc_trade_aggregates.review_id" in (
            ticket_selects[0]
        )
        assert "order by brc_trade_tickets.terminal_at_ms desc" in ticket_selects[0]
        assert "brc_trade_tickets.ticket_id desc" in ticket_selects[0]
        assert ticket_selects[0].count("limit") >= 2
        assert "(brc_trade_tickets.terminal_at_ms, " in ticket_selects[1]
        assert "brc_trade_tickets.ticket_id) <" in ticket_selects[1]
        incident_selects = [
            statement
            for statement in selects
            if "brc_runtime_incidents" in statement
        ]
        assert len(incident_selects) == 2
        assert "row_number() over (partition by" in incident_selects[0]
        assert "<= " in incident_selects[0]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)
        await engine.dispose()


async def test_review_center_status_filters_use_built_review_semantics(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            complete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="complete",
                )
            )
            incomplete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="incomplete_evidence",
                )
            )
            waiting = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="waiting_for_review",
                )
            )

        assert [item.review.ticket_id for item in complete.items] == [
            "ticket:y"
        ]
        assert [item.review.ticket_id for item in incomplete.items] == [
            "ticket:w",
            "ticket:v",
        ]
        assert [item.review.ticket_id for item in waiting.items] == [
            "ticket:x"
        ]
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "event_type",
    (
        "EntryFilled",
        "InitialStopConfirmed",
        "ExitRequested",
        "PositionFlatConfirmed",
        "ReconciliationMatched",
        "BudgetSettled",
    ),
)
async def test_review_center_status_filter_uses_each_exact_positive_proof(
    owner_read_dsn: str,
    event_type: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        """
        DELETE FROM brc_trade_events
        WHERE ticket_id = 'ticket:y' AND event_type = $1
        """,
        event_type,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            complete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="complete",
                )
            )
            incomplete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="incomplete_evidence",
                )
            )

        assert "ticket:y" not in {
            item.review.ticket_id for item in complete.items
        }
        incomplete_y = next(
            item.review
            for item in incomplete.items
            if item.review.ticket_id == "ticket:y"
        )
        assert (
            build_programmatic_review(incomplete_y).execution_classification
            == "evidence_incomplete"
        )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "resolved_partial_fill_incident",
    (False, True),
    ids=("without_incident", "with_resolved_incident"),
)
async def test_partial_fill_never_satisfies_normal_entry_proof_filter(
    owner_read_dsn: str,
    resolved_partial_fill_incident: bool,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        """
        UPDATE brc_trade_events
        SET event_type = 'EntryPartiallyFilled'
        WHERE event_id = 'event:y:entry-filled'
        """,
    )
    if resolved_partial_fill_incident:
        await _execute_owner_console_admin(
            owner_read_dsn,
            """
            UPDATE brc_runtime_incidents
            SET incident_kind = 'unsupported_partial_entry_fill'
            WHERE incident_id = 'incident:y:resolved'
            """,
        )
    else:
        await _execute_owner_console_admin(
            owner_read_dsn,
            """
            DELETE FROM brc_runtime_incidents
            WHERE incident_id = 'incident:y:resolved'
            """,
        )

    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            complete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="complete",
                )
            )
            incomplete = await repository.read_review_center_facts(
                ReviewListQuery(
                    from_ms=1_800_000_000_000,
                    to_ms=1_800_001_000_000,
                    review_status="incomplete_evidence",
                )
            )

        assert "ticket:y" not in {
            item.review.ticket_id for item in complete.items
        }
        partial = next(
            item.review
            for item in incomplete.items
            if item.review.ticket_id == "ticket:y"
        )
        assert partial.entry_fill_evidence is None
        assert (
            build_programmatic_review(partial).execution_classification
            == "evidence_incomplete"
        )
    finally:
        await engine.dispose()


async def test_review_center_rejects_dangling_aggregate_review_pointer(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(owner_read_dsn)
    await _execute_owner_console_admin(
        owner_read_dsn,
        """
        UPDATE brc_trade_aggregates
        SET review_id = 'review:missing'
        WHERE ticket_id = 'ticket:y'
        """,
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            with pytest.raises(
                TradeFactsContradiction,
                match="Aggregate current Review pointer",
            ):
                await repository.read_review_center_facts(
                    ReviewListQuery(
                        from_ms=1_800_000_000_000,
                        to_ms=1_800_001_000_000,
                    )
                )
    finally:
        await engine.dispose()


async def test_sparse_review_filter_paginates_exact_matches_within_cap(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(
        owner_read_dsn,
        sparse_candidate_count=12,
        sparse_complete_ordinals=(2, 7, 11),
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        cursor = None
        ticket_ids: list[str] = []
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            for _page in range(3):
                facts = await repository.read_review_center_facts(
                    ReviewListQuery(
                        from_ms=1_800_000_000_000,
                        to_ms=1_800_001_000_000,
                        limit=1,
                        cursor=cursor,
                        review_status="complete",
                        strategy_group_id="strategy-group:sparse",
                    )
                )
                center = build_review_center(facts)
                ticket_ids.extend(
                    item.review.ticket_id for item in facts.items[:1]
                )
                cursor = center.next_cursor

        assert ticket_ids == [
            "ticket:sparse:0002",
            "ticket:sparse:0007",
            "ticket:sparse:0011",
        ]
        assert len(ticket_ids) == len(set(ticket_ids))
        assert cursor is None
    finally:
        await engine.dispose()


async def test_sparse_review_filter_fails_closed_beyond_candidate_cap(
    owner_read_dsn: str,
) -> None:
    await _seed_owner_console_trades(
        owner_read_dsn,
        sparse_candidate_count=_REVIEW_FILTER_HARD_CAP + 1,
        sparse_complete_ordinals=(_REVIEW_FILTER_HARD_CAP,),
    )
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            repository = PostgresOwnerReadRepository(connection)
            with pytest.raises(
                ProgrammaticReviewContradiction,
                match="candidate bound",
            ):
                await repository.read_review_center_facts(
                    ReviewListQuery(
                        from_ms=1_800_000_000_000,
                        to_ms=1_800_001_000_000,
                        limit=1,
                        review_status="complete",
                        strategy_group_id="strategy-group:sparse",
                    )
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


async def test_overview_freshness_does_not_treat_stable_policy_or_profile_as_runtime_data(
    owner_read_dsn: str,
) -> None:
    now_ms = 1_800_000_010_000
    await _seed_overview_authority(owner_read_dsn, now_ms=now_ms)
    stable_config_updated_at_ms = now_ms - 10 * 86_400_000
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_owner_policy_current SET updated_at_ms = $1",
        stable_config_updated_at_ms,
    )
    await _execute_owner_console_admin(
        owner_read_dsn,
        "UPDATE brc_runtime_profiles SET updated_at_ms = $1",
        stable_config_updated_at_ms,
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

        assert facts.runtime_freshness.value == "fresh"
        assert facts.freshness_evidence_identity == (
            "account:binance-usdm:owner-console-account"
        )
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


async def _execute_owner_console_admin(
    dsn: str,
    statement: str,
    *args: object,
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
        await connection.execute(statement, *args)
    finally:
        await connection.close()


async def _seed_owner_console_trades(
    dsn: str,
    *,
    sparse_candidate_count: int = 0,
    sparse_complete_ordinals: tuple[int, ...] = (),
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
    sparse_complete = set(sparse_complete_ordinals)
    sparse_ticket_ids = tuple(
        f"ticket:sparse:{ordinal:04d}"
        for ordinal in range(sparse_candidate_count)
    )
    tickets = (
        *tickets,
        *(
            (
                ticket_id,
                "strategy-group:sparse",
                f"SPARSE{ordinal:04d}USDT",
                "long",
                "terminal",
                created_at_ms - 1_000 - ordinal,
                created_at_ms + 20_000 - ordinal,
                None,
            )
            for ordinal, ticket_id in enumerate(sparse_ticket_ids)
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
                    *(
                        (
                            ticket_id,
                            "terminal",
                            f"review:sparse:{ordinal:04d}",
                            created_at_ms + 20_000 - ordinal,
                        )
                        for ordinal, ticket_id in enumerate(sparse_ticket_ids)
                    ),
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
                    *(
                        (
                            f"review:sparse:{ordinal:04d}",
                            ticket_id,
                            1,
                            None,
                            json.dumps(
                                {
                                    "economics_completeness": "complete",
                                    "gross_realized_pnl_quote": "4.0000",
                                    "trading_fees_quote": "0.4000",
                                    "funding_quote": "-0.0900",
                                    "net_pnl_quote": "3.5100",
                                    "planned_r_multiple": "0.4800",
                                }
                                if ordinal in sparse_complete
                                else {
                                    "economics_completeness": (
                                        "funding_unavailable"
                                    ),
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
                            created_at_ms + 40_000 - ordinal,
                        )
                        for ordinal, ticket_id in enumerate(sparse_ticket_ids)
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
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    $1::varchar(160), 'ticket:y', $2::bigint,
                    $3::varchar(160), $4::jsonb, $5::bigint
                )
                """,
                (
                    (
                        "event:y:entry-rejected",
                        1,
                        "EntryRejected",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 1_000,
                    ),
                    (
                        "event:y:entry-filled",
                        2,
                        "EntryFilled",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 2_000,
                    ),
                    (
                        "event:y:initial-stop-rejected",
                        3,
                        "InitialStopRejected",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 3_000,
                    ),
                    (
                        "event:y:initial-stop-confirmed",
                        4,
                        "InitialStopConfirmed",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 4_000,
                    ),
                    (
                        "event:y:position-flat-confirmed",
                        12,
                        "PositionFlatConfirmed",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 27_000,
                    ),
                    (
                        "event:y:reconciliation-matched",
                        13,
                        "ReconciliationMatched",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 28_000,
                    ),
                    (
                        "event:y:budget-settled",
                        14,
                        "BudgetSettled",
                        json.dumps({"ticket_id": "ticket:y"}),
                        created_at_ms + 29_000,
                    ),
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES (
                    'event:' || $1::varchar(160) || ':' || lower($3::text),
                    $1::varchar(160), $2::bigint, $3::varchar(160),
                    $4::jsonb, $5::bigint
                )
                """,
                tuple(
                    (
                        ticket_id,
                        sequence,
                        event_type,
                        json.dumps(
                            {
                                "event_id": (
                                    f"event:{ticket_id}:{event_type.lower()}"
                                ),
                                "ticket_id": ticket_id,
                                "sequence": sequence,
                                "occurred_at_ms": (
                                    created_at_ms + occurred_offset
                                ),
                                **(
                                    {"reason": "strategy_exit"}
                                    if event_type == "ExitRequested"
                                    else {}
                                ),
                            }
                        ),
                        created_at_ms + occurred_offset,
                    )
                    for ticket_id in (
                        "ticket:x",
                        "ticket:w",
                        "ticket:v",
                        *sparse_ticket_ids,
                    )
                    for sequence, event_type, occurred_offset in (
                        (1, "EntryFilled", 1_000),
                        (2, "InitialStopConfirmed", 2_000),
                        (3, "ExitRequested", 20_000),
                        (4, "PositionFlatConfirmed", 27_000),
                        (5, "ReconciliationMatched", 28_000),
                        (6, "BudgetSettled", 29_000),
                    )
                    if not (
                        ticket_id == "ticket:v"
                        and event_type == "ExitRequested"
                    )
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
            await connection.executemany(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    $1::varchar(160), $2::varchar(160), $3::varchar(160),
                    $4::varchar(160), $5::text, 'none', NULL, '{}',
                    $6::bigint, $7::bigint
                )
                """,
                (
                    (
                        "incident:y:resolved",
                        "ticket:y",
                        "exit_outcome_unknown",
                        "resolved",
                        "automatic recovery complete",
                        created_at_ms + 25_000,
                        created_at_ms + 26_000,
                    ),
                    (
                        "incident:w:open",
                        "ticket:w",
                        "funding_attribution_unavailable",
                        "open",
                        "exact evidence unavailable",
                        created_at_ms + 25_000,
                        None,
                    ),
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


def _owner_console_causality_ticket() -> TradeTicket:
    return TradeTicket(
        identity=TicketIdentity(
            ticket_id="ticket:causality",
            exposure_episode_id="episode:z",
            signal_event_id="signal:z",
            runtime=RuntimeIdentity(
                runtime_profile_id="profile:owner-console",
                strategy_group_id="strategy-group:alpha",
                strategy_version_id="strategy-version:alpha",
                event_spec_id="event-spec:signal",
            ),
            netting_domain=NettingDomain(
                venue_id="binance-usdm",
                account_id="owner-console-account",
                exchange_instrument_id="BTCUSDT",
                position_side="long",
            ),
        ),
        owner_policy_id="policy:owner-console",
        owner_policy_version=1,
        runtime_scope_id="scope:z",
        runtime_scope_version=1,
        universe_version_id="universe:owner-console-signals",
        universe_semantic_digest="sha256:" + "a" * 64,
        fact_digest="sha256:" + "d" * 64,
        exposure_family="opening_range",
        active_family_ticket_count_at_claim=0,
        family_ticket_limit=2,
        directional_risk_at_stop_at_claim=Decimal(0),
        directional_stop_risk_limit_fraction=Decimal("0.04"),
        min_materialization_ratio=Decimal("0.5"),
        minimum_stop_risk_budget=Decimal(1),
        exit_policy_id="exit-policy:test",
        exit_policy_semantic_hash="sha256:" + "b" * 64,
        capacity_claim_id="claim:causality",
        created_at_ms=1_800_000_003_000,
        expires_at_ms=1_800_000_060_000,
        entry_reference_price=Decimal("100.00"),
        quantity=Decimal(1),
        notional=Decimal(100),
        planned_stop_risk_budget=Decimal(1),
        post_fill_stop_risk_limit=Decimal("1.1"),
        selected_leverage=1,
        leverage_change_required=False,
        reserved_margin=Decimal(100),
        risk_reservation_basis="stop_risk",
        margin_mode="cross",
        cross_margin_stress_model_id="cross-margin-stop-stress-v1",
        post_stop_stress_multiple=Decimal(2),
        claim_stress_proof_digest="sha256:" + "c" * 64,
        risk_at_stop=Decimal(1),
        entry_order_type="market",
        initial_stop_price=Decimal("99.00"),
        take_profit_prices=(Decimal("102.00"),),
        take_profit_quantities=(Decimal("0.5"),),
        status=TicketStatus.TERMINAL,
    )


async def _seed_owner_console_causality(
    dsn: str,
    *,
    admission_strategy_group_id: str = "strategy-group:alpha",
    event_count: int = 10,
    command_count: int = 2,
    incident_count: int = 1,
) -> None:
    if event_count < 10 or command_count < 2 or incident_count < 1:
        raise ValueError("causality seed counts cannot remove baseline facts")
    await _seed_owner_console_signals(dsn)
    database_name = make_url(dsn).database
    assert database_name is not None
    admin_dsn = (
        make_url(ADMIN_DSN)
        .set(drivername="postgresql", database=database_name)
        .render_as_string(hide_password=False)
    )
    connection = await asyncpg.connect(admin_dsn)
    digest = "sha256:" + "a" * 64
    ticket = _owner_console_causality_ticket()
    try:
        async with connection.transaction():
            await connection.execute(
                "DELETE FROM brc_shadow_outcomes_current "
                "WHERE admission_decision_id = 'admission:z'"
            )
            await connection.execute(
                "DELETE FROM brc_admission_decisions "
                "WHERE admission_decision_id = 'admission:z'"
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
                ) VALUES (
                    'ticket:causality', 'episode:z', 'signal:z',
                    'strategy-group:alpha', 'strategy-version:alpha',
                    'event-spec:signal', 'universe:owner-console-signals', $1,
                    'profile:owner-console', 'policy:owner-console', 1,
                    'scope:z', 1, 'owner-console-account', 'binance-usdm',
                    'BTCUSDT', 'long',
                    'binance-usdm:owner-console-account:BTCUSDT:long', NULL,
                    'opening_range', 0, 2, 0, 0.04, 0.5, 1,
                    'exit-policy:test', 'sha256:' || repeat('b', 64),
                    100.00, 1, 100, 'claim:causality', 1, 1.1, 1, false,
                    100, 'stop_risk', 'cross',
                    'cross-margin-stop-stress-v1', 2,
                    'sha256:' || repeat('c', 64), 1, 'market', NULL, 99.00,
                    NULL, NULL, '["102.00"]'::jsonb, '["0.5"]'::jsonb,
                    'sha256:' || repeat('d', 64),
                    'sha256:' || repeat('e', 64), 'terminal',
                    1800000003000, 1800000060000, 1800000095000
                )
                """,
                digest,
            )
            await connection.execute(
                """
                INSERT INTO brc_capacity_claims (
                    capacity_claim_id, ticket_id, signal_event_id,
                    exposure_episode_id, strategy_group_id,
                    strategy_version_id, event_spec_id, universe_version_id,
                    universe_semantic_digest, runtime_profile_id,
                    owner_policy_id, owner_policy_version, runtime_scope_id,
                    runtime_scope_version, account_id, venue_id,
                    exchange_instrument_id, position_side, netting_domain_key,
                    fact_digest, exit_policy_id, exit_policy_semantic_hash,
                    entry_admission_snapshot_digest,
                    account_entry_health_digest,
                    instrument_entry_health_digest,
                    instrument_rules_projection_version,
                    account_capacity_domain_key, leverage_domain_key,
                    total_wallet_balance_at_claim,
                    total_margin_balance_at_claim,
                    total_initial_margin_at_claim,
                    total_maintenance_margin_at_claim,
                    available_margin_at_claim, mark_price_at_claim,
                    position_mode_at_claim, margin_mode_at_claim,
                    active_ticket_count_at_claim, remaining_slots_at_claim,
                    active_strategy_group_ticket_count_at_claim,
                    max_strategy_group_concurrent_tickets,
                    remaining_strategy_group_slots_at_claim,
                    exposure_family, active_family_ticket_count_at_claim,
                    family_ticket_limit, gross_risk_at_stop_at_claim,
                    directional_risk_at_stop_at_claim,
                    current_reserved_margin_at_claim,
                    max_ticket_stop_risk_fraction,
                    max_gross_stop_risk_fraction,
                    directional_stop_risk_limit_fraction,
                    max_ticket_initial_margin_fraction,
                    max_gross_initial_margin_utilization,
                    min_materialization_ratio, minimum_stop_risk_budget,
                    planned_stop_risk_budget,
                    max_post_fill_stop_risk_overrun_fraction,
                    post_fill_stop_risk_limit, post_stop_stress_multiple,
                    ticket_margin_budget, required_leverage,
                    selected_leverage, configured_leverage_at_claim,
                    leverage_change_required, exchange_max_leverage,
                    reserved_margin, cross_margin_stress_evidence,
                    entry_reference_price, quantity, notional, risk_at_stop,
                    entry_order_type, entry_limit_price, initial_stop_price,
                    pre_tp1_reclaim_price, exposure_session_end_ms,
                    take_profit_prices, take_profit_quantities,
                    decision_digest, created_at_ms, expires_at_ms
                ) VALUES (
                    'claim:causality', 'ticket:causality', 'signal:z',
                    'episode:z', 'strategy-group:alpha',
                    'strategy-version:alpha', 'event-spec:signal',
                    'universe:owner-console-signals', $1,
                    'profile:owner-console', 'policy:owner-console', 1,
                    'scope:z', 1, 'owner-console-account', 'binance-usdm',
                    'BTCUSDT', 'long',
                    'binance-usdm:owner-console-account:BTCUSDT:long',
                    'sha256:' || repeat('f', 64), 'exit-policy:test',
                    'sha256:' || repeat('b', 64),
                    'sha256:' || repeat('1', 64),
                    'sha256:' || repeat('2', 64),
                    'sha256:' || repeat('3', 64), 1,
                    'binance-usdm:owner-console-account',
                    'binance-usdm:owner-console-account:BTCUSDT',
                    1000, 1000, 0, 0, 900, 100, 'independent_sides', 'cross',
                    0, 3, NULL, NULL, NULL, 'opening_range', 0, 2, 0, 0, 0,
                    0.02, 0.06, 0.04, 0.30, 0.90, 0.50, 1, 1, 0.10, 1.1,
                    2, 100, 1, 1, 1, false, 10, 100, '{}'::jsonb,
                    100.00, 1, 100, 1, 'market', NULL, 99.00, NULL, NULL,
                    '["102.00"]'::jsonb, '["0.5"]'::jsonb,
                    'sha256:' || repeat('4', 64),
                    1800000002000, 1800000060000
                )
                """,
                digest,
            )
            await connection.execute(
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
                    'admission:z', 'signal:z', 'episode:z', $2,
                    'strategy-version:alpha', 'event-spec:signal',
                    'universe:owner-console-signals', $1,
                    'profile:owner-console', 'scope:z', 1,
                    'policy:owner-console', 1, 'binance-usdm',
                    'owner-console-account', 'BTCUSDT', 'long',
                    'opening_range', 1, 1, 'sha256:' || repeat('5', 64),
                    '{}'::jsonb, '{}'::jsonb, 'admitted', NULL,
                    'remaining_initial_margin', 'claim:causality',
                    'ticket:causality', 'sha256:' || repeat('1', 64),
                    'sha256:' || repeat('6', 64), 1800000002000
                )
                """,
                digest,
                admission_strategy_group_id,
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
                ) VALUES (
                    'ticket:causality', 'terminal', $1, $1, false, 0,
                    100.10, 1.10, NULL, 'within_limit', 'continue',
                    'within_limit', 'sha256:' || repeat('7', 64), 0,
                    'exchange:entry:1', 'exchange:stop:1', 'exchange:stop:2',
                    100.20, 'exchange:tp:1', 0.5, 0.5, 100.20,
                    'exchange:stop:1', NULL, NULL, 1800000040000, NULL,
                    'exchange:exit:1', 'review:causality:v2', NULL, NULL,
                    1800000100000
                )
                """,
                event_count,
            )
            issued_ticket = ticket.model_copy(
                update={"status": TicketStatus.ISSUED}
            )
            event_rows = (
                (
                    "event:causality:1",
                    1,
                    "TicketIssued",
                    TicketIssued(
                        event_id="event:causality:1",
                        sequence=1,
                        occurred_at_ms=1_800_000_003_000,
                        ticket=issued_ticket,
                    ).model_dump(mode="json"),
                    1_800_000_003_000,
                ),
                (
                    "event:causality:2",
                    2,
                    "EntryFilled",
                    {
                        "event_id": "event:causality:2",
                        "ticket_id": "ticket:causality",
                        "sequence": 2,
                        "occurred_at_ms": 1_800_000_010_000,
                        "filled_qty": "1",
                        "average_fill_price": "100.10",
                    },
                    1_800_000_010_000,
                ),
                (
                    "event:causality:3",
                    3,
                    "InitialStopConfirmed",
                    {
                        "event_id": "event:causality:3",
                        "ticket_id": "ticket:causality",
                        "sequence": 3,
                        "occurred_at_ms": 1_800_000_020_000,
                        "exchange_order_id": "exchange:stop:1",
                        "protected_qty": "1",
                    },
                    1_800_000_020_000,
                ),
                (
                    "event:causality:4",
                    4,
                    "TakeProfitFilled",
                    {
                        "event_id": "event:causality:4",
                        "ticket_id": "ticket:causality",
                        "sequence": 4,
                        "occurred_at_ms": 1_800_000_030_000,
                        "filled_qty": "0.5",
                        "average_fill_price": "102.00",
                        "runner_floor_price": "100.20",
                    },
                    1_800_000_030_000,
                ),
                (
                    "event:causality:5",
                    5,
                    "ProtectionReplacementConfirmed",
                    {
                        "event_id": "event:causality:5",
                        "ticket_id": "ticket:causality",
                        "sequence": 5,
                        "occurred_at_ms": 1_800_000_040_000,
                        "exchange_order_id": "exchange:stop:2",
                        "protected_qty": "0.5",
                        "stop_price": "100.20",
                        "replaces_exchange_order_id": "exchange:stop:1",
                        "source_watermark_ms": 1_800_000_040_000,
                    },
                    1_800_000_040_000,
                ),
                (
                    "event:causality:6",
                    6,
                    "ExitRequested",
                    {
                        "event_id": "event:causality:6",
                        "ticket_id": "ticket:causality",
                        "sequence": 6,
                        "occurred_at_ms": 1_800_000_050_000,
                        "reason": "initial_stop_triggered",
                    },
                    1_800_000_050_000,
                ),
                (
                    "event:causality:7",
                    7,
                    "PositionFlatConfirmed",
                    {
                        "event_id": "event:causality:7",
                        "ticket_id": "ticket:causality",
                        "sequence": 7,
                        "occurred_at_ms": 1_800_000_060_000,
                    },
                    1_800_000_060_000,
                ),
                (
                    "event:causality:8",
                    8,
                    "BudgetSettled",
                    {
                        "event_id": "event:causality:8",
                        "ticket_id": "ticket:causality",
                        "sequence": 8,
                        "occurred_at_ms": 1_800_000_070_000,
                    },
                    1_800_000_070_000,
                ),
                (
                    "event:causality:9",
                    9,
                    "ReviewRecorded",
                    {
                        "event_id": "event:causality:9",
                        "ticket_id": "ticket:causality",
                        "sequence": 9,
                        "occurred_at_ms": 1_800_000_100_000,
                        "review_id": "review:causality:v2",
                    },
                    1_800_000_100_000,
                ),
                (
                    "event:causality:10",
                    10,
                    "FutureLifecycleEvent",
                    {
                        "event_id": "event:causality:10",
                        "ticket_id": "ticket:causality",
                        "sequence": 10,
                        "occurred_at_ms": 1_800_000_101_000,
                    },
                    1_800_000_101_000,
                ),
            )
            await connection.executemany(
                """
                INSERT INTO brc_trade_events (
                    event_id, ticket_id, sequence, event_type, payload,
                    occurred_at_ms
                ) VALUES ($1, 'ticket:causality', $2, $3, $4::jsonb, $5)
                """,
                [
                    (event_id, sequence, event_type, json.dumps(payload), at_ms)
                    for event_id, sequence, event_type, payload, at_ms in event_rows
                ],
            )
            if event_count > 10:
                await connection.execute(
                    """
                    INSERT INTO brc_trade_events (
                        event_id, ticket_id, sequence, event_type, payload,
                        occurred_at_ms
                    )
                    SELECT
                        'event:causality:cap:' || sequence,
                        'ticket:causality',
                        sequence,
                        'FutureLifecycleEvent',
                        jsonb_build_object(
                            'event_id', 'event:causality:cap:' || sequence,
                            'ticket_id', 'ticket:causality',
                            'sequence', sequence,
                            'occurred_at_ms', 1800000200000 + sequence
                        ),
                        1800000200000 + sequence
                    FROM generate_series(11, $1) AS sequence
                    """,
                    event_count,
                )
            await connection.executemany(
                """
                INSERT INTO brc_exchange_commands (
                    command_id, ticket_id, command_kind, generation,
                    idempotency_key, venue_client_order_id, status, quantity,
                    request_payload, result_payload, claim_owner,
                    lease_until_ms, created_at_ms, deadline_at_ms,
                    completed_at_ms
                ) VALUES (
                    $1, 'ticket:causality', $2, 1, $3, $4, 'accepted', 1,
                    $5::jsonb, $6::jsonb, NULL, NULL, $7::bigint,
                    $7::bigint + 30000, $8::bigint
                )
                """,
                (
                    (
                        "command:entry:1",
                        "entry",
                        "idempotency:entry:1",
                        "client:entry:1",
                        json.dumps({"quantity": "1"}),
                        json.dumps({"exchange_order_id": "exchange:entry:1"}),
                        1_800_000_005_000,
                        1_800_000_010_000,
                    ),
                    (
                        "command:exit:1",
                        "exit",
                        "idempotency:exit:1",
                        "client:exit:1",
                        json.dumps({"quantity": "1"}),
                        json.dumps({"exchange_order_id": "exchange:exit:1"}),
                        1_800_000_045_000,
                        1_800_000_050_000,
                    ),
                ),
            )
            if command_count > 2:
                await connection.execute(
                    """
                    INSERT INTO brc_exchange_commands (
                        command_id, ticket_id, command_kind, generation,
                        idempotency_key, venue_client_order_id, status,
                        quantity, request_payload, result_payload,
                        claim_owner, lease_until_ms, created_at_ms,
                        deadline_at_ms, completed_at_ms
                    )
                    SELECT
                        'command:causality:cap:' || generation,
                        'ticket:causality',
                        'cancel_order',
                        generation,
                        'idempotency:causality:cap:' || generation,
                        'client:causality:cap:' || generation,
                        'accepted',
                        1,
                        '{"quantity":"1"}'::jsonb,
                        jsonb_build_object(
                            'exchange_order_id',
                            'exchange:causality:cap:' || generation
                        ),
                        NULL,
                        NULL,
                        1800000200000 + generation,
                        1800000230000 + generation,
                        1800000205000 + generation
                    FROM generate_series(1, $1) AS generation
                    """,
                    command_count - 2,
                )
            await connection.execute(
                """
                INSERT INTO brc_runtime_incidents (
                    incident_id, ticket_id, incident_kind, status,
                    first_blocker, entry_block_scope, entry_block_key,
                    details, opened_at_ms, resolved_at_ms
                ) VALUES (
                    'incident:causality:1', 'ticket:causality',
                    'exit_outcome_unknown', 'resolved', 'venue_timeout',
                    'none', NULL, '{"resolution":"reconciled"}'::jsonb,
                    1800000055000, 1800000065000
                )
                """
            )
            if incident_count > 1:
                await connection.execute(
                    """
                    INSERT INTO brc_runtime_incidents (
                        incident_id, ticket_id, incident_kind, status,
                        first_blocker, entry_block_scope, entry_block_key,
                        details, opened_at_ms, resolved_at_ms
                    )
                    SELECT
                        'incident:causality:cap:' || incident_number,
                        'ticket:causality',
                        'bounded_history_fixture',
                        'resolved',
                        'fixture',
                        'none',
                        NULL,
                        '{}'::jsonb,
                        1800000200000 + incident_number,
                        1800000205000 + incident_number
                    FROM generate_series(1, $1) AS incident_number
                    """,
                    incident_count - 1,
                )
            await connection.executemany(
                """
                INSERT INTO brc_trade_reviews (
                    review_id, ticket_id, revision, supersedes_review_id,
                    outcome, metrics, decision_impact, created_at_ms
                ) VALUES (
                    $1, 'ticket:causality', $2, $3, 'terminal_flat',
                    $4::jsonb, '{}'::jsonb, $5
                )
                """,
                (
                    (
                        "review:causality:v1",
                        1,
                        None,
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "999",
                                "trading_fees_quote": "0",
                                "funding_quote": "0",
                                "net_pnl_quote": "999",
                                "planned_r_multiple": "999",
                                "order_attribution": [],
                            }
                        ),
                        1_800_000_110_000,
                    ),
                    (
                        "review:causality:v2",
                        2,
                        "review:causality:v1",
                        json.dumps(
                            {
                                "economics_completeness": "complete",
                                "gross_realized_pnl_quote": "3.00",
                                "trading_fees_quote": "0.10",
                                "funding_quote": "0.00",
                                "net_pnl_quote": "2.90",
                                "planned_r_multiple": "2.90",
                                "order_attribution": [
                                    {
                                        "exchange_trade_id": "trade:exit:1",
                                        "exchange_order_id": "exchange:exit:1",
                                        "command_id": "command:exit:1",
                                        "role": "exit",
                                        "quantity": "1",
                                        "price": "103.00",
                                        "fee": {},
                                        "realized_pnl_quote": "3.00",
                                        "occurred_at_ms": 1_800_000_090_000,
                                    }
                                ],
                            }
                        ),
                        1_800_000_100_000,
                    ),
                ),
            )
    finally:
        await connection.close()


def _asyncpg_dsn(dsn: str) -> str:
    return (
        make_url(dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
