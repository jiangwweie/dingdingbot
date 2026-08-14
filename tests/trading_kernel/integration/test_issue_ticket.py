from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.issue_ticket import (
    IssueTicketRequest,
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.domain.capacity import freeze_capacity_claim
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    OrderCommandPayload,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    MaintenanceMarginBracket,
    StressPosition,
    evaluate_cross_margin_stress,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    entry_lane_current,
    event_product_compatibility,
    event_specs,
    instrument_product_profiles,
    instruments,
    owner_authorizations,
    owner_policy_current,
    runtime_incidents,
    runtime_scopes_current,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    strategy_groups,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE as SAFE_DATABASE,
)
from tests.trading_kernel.support.postgres import (
    TEST_POSTGRES_ADMIN_DSN as ADMIN_DSN,
)
from tests.trading_kernel.support.postgres import (
    async_database_url as _database_url,
)
from tests.trading_kernel.support.postgres import (
    run_alembic as _run_alembic,
)
from tests.trading_kernel.support.tickets import (
    make_ticket as _ticket,
)
from tests.trading_kernel.support.tickets import (
    make_ticket_identity as _identity,
)


@pytest_asyncio.fixture
async def issue_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_issue_ticket_claims_global_lane_and_reserves_budget_atomically(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=False)
    await _seed_policy(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="worker-1",
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert result.ticket_id == ticket.identity.ticket_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        persisted = await uow.tickets.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.venue_id,
            ticket.identity.netting_domain.account_id
        )
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    assert persisted is not None
    assert persisted.identity == ticket.identity
    assert persisted.selected_leverage == ticket.selected_leverage
    assert persisted.reserved_margin == ticket.reserved_margin
    assert persisted.capacity_claim_id.startswith("claim:")
    assert reservation is not None
    assert reservation.reserved_notional == ticket.notional
    assert reservation.reserved_risk == ticket.risk_at_stop
    assert lane is not None
    assert lane.ticket_id == ticket.identity.ticket_id
    assert exposure is not None
    assert exposure.gross_notional == ticket.notional
    assert exposure.active_ticket_count == 1
    assert [(command.kind, command.generation) for command in commands] == [
        (ExchangeCommandKind.ENTRY, 1)
    ]
    assert isinstance(commands[0].payload, OrderCommandPayload)
    assert commands[0].payload.leverage_verification_digest == _expected_leverage_fact_digest(
        claim=_issue_request(
            ticket=ticket,
            now_ms=1_001,
            claim_owner="worker-1",
        ).capacity_claim,
    )


@pytest.mark.asyncio
async def test_issue_ticket_prepares_only_entry_when_leverage_already_matches(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket(leverage_change_required=False)
    await _seed_policy(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.ISSUED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert [(command.kind, command.generation) for command in commands] == [
        (ExchangeCommandKind.ENTRY, 1)
    ]
    assert isinstance(commands[0].payload, OrderCommandPayload)
    assert commands[0].payload.leverage_verification_digest == (
        _expected_leverage_fact_digest(
            claim=_issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="worker-1",
            ).capacity_claim,
        )
    )

@pytest.mark.asyncio
async def test_scope_drift_after_lane_and_account_lock_leaves_no_durable_entry_state(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        original_get_account_exposure = uow.entry_admission.get_account_exposure

        async def drift_scope_after_account_lock(*args, **kwargs):
            exposure = await original_get_account_exposure(*args, **kwargs)
            async with issue_engine.begin() as connection:
                await connection.execute(
                    sa.update(runtime_scopes_current)
                    .where(
                        runtime_scopes_current.c.runtime_scope_id
                        == ticket.runtime_scope_id
                    )
                    .values(
                        scope_version=ticket.runtime_scope_version + 1,
                    )
                )
            return exposure

        monkeypatch.setattr(
            uow.entry_admission,
            "get_account_exposure",
            drift_scope_after_account_lock,
        )
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
    await _assert_no_durable_entry_state(issue_engine, ticket.identity.ticket_id)


@pytest.mark.asyncio
async def test_current_universe_switch_committing_before_issue_rejects_old_claim(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)
    await _seed_replacement_universe(issue_engine, ticket)
    switch_connection = await issue_engine.connect()
    switch_transaction = await switch_connection.begin()
    try:
        switch_backend_pid = int(
            await switch_connection.scalar(sa.text("SELECT pg_backend_pid()"))
        )
        await switch_connection.execute(
            sa.update(strategy_universe_current)
            .where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
            .values(
                universe_version_id="universe:sor-long:replacement",
                semantic_digest="sha256:" + "b" * 64,
                activation_generation=2,
                activated_at_ms=1_001,
            )
        )
        async with PostgresKernelUnitOfWork(issue_engine) as issue_uow:
            issue_connection = issue_uow._require_connection()
            issue_backend_pid = int(
                await issue_connection.scalar(sa.text("SELECT pg_backend_pid()"))
            )
            issue_task = asyncio.create_task(
                issue_ticket(
                    issue_uow,
                    _issue_request(
                        ticket=ticket,
                        now_ms=1_002,
                        claim_owner="worker-race",
                    ),
                )
            )
            await _wait_for_database_blocker(
                issue_engine,
                blocked_backend_pid=issue_backend_pid,
                blocker_backend_pid=switch_backend_pid,
            )
            assert issue_task.done() is False
            await switch_transaction.commit()
            result = await issue_task
    finally:
        if switch_transaction.is_active:
            await switch_transaction.rollback()
        await switch_connection.close()

    assert result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
    async with issue_engine.connect() as connection:
        current_version_id = await connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
        )
    assert current_version_id == "universe:sor-long:replacement"
    await _assert_no_durable_entry_state(issue_engine, ticket.identity.ticket_id)


@pytest.mark.asyncio
async def test_retired_strategy_version_blocks_ticket_issuance_before_durable_state(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)

    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_versions)
            .where(
                strategy_versions.c.strategy_version_id
                == ticket.identity.runtime.strategy_version_id
            )
            .values(status="retired")
        )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
    await _assert_no_durable_entry_state(issue_engine, ticket.identity.ticket_id)


@pytest.mark.asyncio
async def test_exact_account_incident_drift_after_lane_and_account_lock_leaves_no_durable_entry_state(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        original_get_account_exposure = uow.entry_admission.get_account_exposure

        async def open_incident_after_account_lock(*args, **kwargs):
            exposure = await original_get_account_exposure(*args, **kwargs)
            async with issue_engine.begin() as connection:
                await connection.execute(
                    sa.insert(runtime_incidents).values(
                        incident_id="incident:account-capacity-drift",
                        ticket_id=None,
                        incident_kind="account_capacity_unknown",
                        status="open",
                        first_blocker="account_capacity_unknown",
                        entry_block_scope=EntryBlockScope.ACCOUNT_CAPACITY.value,
                        entry_block_key=(
                            f"{ticket.identity.netting_domain.venue_id}:"
                            f"{ticket.identity.netting_domain.account_id}"
                        ),
                        details={},
                        opened_at_ms=1_000,
                        resolved_at_ms=None,
                    )
                )
            return exposure

        monkeypatch.setattr(
            uow.entry_admission,
            "get_account_exposure",
            open_incident_after_account_lock,
        )
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.ADMISSION_INCIDENT_OPEN
    await _assert_no_durable_entry_state(issue_engine, ticket.identity.ticket_id)


@pytest.mark.asyncio
async def test_occupied_global_lane_serializes_two_different_tickets(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-2", "episode-2", position_side="short")

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        issued = await issue_ticket(
            uow,
            _issue_request(ticket=first, now_ms=1_001, claim_owner="worker-1"),
        )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        blocked = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_002, claim_owner="worker-2"),
        )

    assert issued.status is IssueTicketStatus.ISSUED
    assert blocked.status is IssueTicketStatus.ENTRY_LANE_OCCUPIED


@pytest.mark.asyncio
async def test_expired_admission_snapshot_cannot_issue_ticket(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    ticket = _ticket(expires_at_ms=2_000)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=2_000, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.FACTS_EXPIRED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.tickets.get(ticket.identity.ticket_id) is None
        assert await uow.budgets.get_for_ticket(ticket.identity.ticket_id) is None


@pytest.mark.asyncio
async def test_missing_or_stale_owner_policy_blocks_ticket(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        missing = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    await _seed_policy(issue_engine, policy_version=8)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        stale = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_002, claim_owner="worker-1"),
        )

    assert missing.status is IssueTicketStatus.POLICY_MISSING_OR_STALE
    assert stale.status is IssueTicketStatus.POLICY_MISSING_OR_STALE


@pytest.mark.asyncio
async def test_policy_scope_drift_before_ticket_issue_creates_no_durable_state(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == ticket.owner_policy_id)
            .values(
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": ticket.identity.runtime.event_spec_id,
                            "runtime_profile_id": "tradfi-equity-usdm-v1",
                        }
                    ]
                }
            )
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.tickets.get(ticket.identity.ticket_id) is None
        assert await uow.budgets.get_for_ticket(ticket.identity.ticket_id) is None
        assert await uow.capacity_claims.get_for_ticket(ticket.identity.ticket_id) is None


@pytest.mark.asyncio
async def test_policy_and_budget_limits_fail_closed(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine, enabled=False)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        disabled = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )
    assert disabled.status is IssueTicketStatus.POLICY_DISABLED

    async with issue_engine.begin() as connection:
        await connection.execute(sa.delete(owner_policy_current))
        await connection.execute(sa.delete(runtime_scopes_current))
    await _seed_policy(issue_engine, max_concurrent_tickets=1)
    first = _ticket()
    await _issue_and_release_lane(issue_engine, first)
    exhausted_ticket = _ticket_for_signal("signal-budget", "episode-budget", position_side="short")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        exhausted = await issue_ticket(
            uow,
            _issue_request(
                ticket=exhausted_ticket,
                now_ms=1_002,
                claim_owner="worker-1",
            ),
        )
    assert exhausted.status is IssueTicketStatus.BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_active_netting_domain_blocks_a_new_exposure_episode(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-2", "episode-2", position_side="long")
    await _issue_and_release_lane(issue_engine, first)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_010, claim_owner="worker-2"),
        )

    assert result.status is IssueTicketStatus.ACTIVE_NETTING_DOMAIN


@pytest.mark.asyncio
async def test_long_and_short_are_independent_default_netting_domains(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    long_ticket = _ticket()
    short_ticket = _ticket_for_signal(
        "signal-2",
        "episode-2",
        position_side="short",
    )
    await _issue_and_release_lane(issue_engine, long_ticket)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=short_ticket,
                now_ms=1_010,
                claim_owner="worker-short",
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        exposure = await uow.entry_admission.get_account_exposure(
            long_ticket.identity.netting_domain.venue_id,
            long_ticket.identity.netting_domain.account_id
        )
    assert exposure is not None
    assert exposure.active_ticket_count == 2


@pytest.mark.asyncio
async def test_exposure_family_capacity_merges_long_short_and_rejects_third_without_artifacts(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket(risk_at_stop=Decimal(3), reserved_margin=Decimal(20))
    second_base = _ticket_for_signal(
        "signal-strategy-2",
        "episode-strategy-2",
        position_side="short",
    )
    second = _ticket(
        identity=second_base.identity,
        runtime_scope_id=second_base.runtime_scope_id,
        universe_version_id=second_base.universe_version_id,
        initial_stop_price=second_base.initial_stop_price,
        take_profit_prices=second_base.take_profit_prices,
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(20),
    )
    third = _ticket_for_instrument(
        "signal-strategy-3",
        "episode-strategy-3",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        runtime_scope_id="scope-sor-eth-long",
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(20),
    )
    await _seed_ticket_runtime_scope(issue_engine, third)

    await _issue_and_release_lane(issue_engine, first)
    await _issue_and_release_lane(issue_engine, second)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        refused = await issue_ticket(
            uow,
            _issue_request(
                ticket=third,
                now_ms=1_003,
                claim_owner="worker-strategy-3",
            ),
        )

    assert (
        refused.status
        is IssueTicketStatus.EXPOSURE_FAMILY_CAPACITY_EXHAUSTED
    )
    await _assert_no_durable_entry_state(
        issue_engine,
        third.identity.ticket_id,
    )


@pytest.mark.asyncio
async def test_two_sor_tickets_and_one_other_strategy_can_fill_account_capacity(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket(risk_at_stop=Decimal(3), reserved_margin=Decimal(20))
    second_base = _ticket_for_signal(
        "signal-account-2",
        "episode-account-2",
        position_side="short",
    )
    second = _ticket(
        identity=second_base.identity,
        runtime_scope_id=second_base.runtime_scope_id,
        universe_version_id=second_base.universe_version_id,
        initial_stop_price=second_base.initial_stop_price,
        take_profit_prices=second_base.take_profit_prices,
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(20),
    )
    third = _ticket_for_strategy_group(
        "signal-account-3",
        "episode-account-3",
        strategy_group_id="MI-001",
        strategy_version_id="MI-001:v2",
        event_spec_id="mi-long-v2",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        runtime_scope_id="scope-mi-eth-long",
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(20),
    )
    await _seed_ticket_runtime_scope(issue_engine, third)

    await _issue_and_release_lane(issue_engine, first)
    await _issue_and_release_lane(issue_engine, second)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=third,
                now_ms=1_003,
                claim_owner="worker-account-3",
            ),
        )
        exposure = await uow.entry_admission.get_account_exposure(
            first.identity.netting_domain.venue_id,
            first.identity.netting_domain.account_id,
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert exposure is not None
    assert exposure.active_ticket_count == 3


@pytest.mark.asyncio
async def test_exposure_family_active_count_is_isolated_by_venue_and_account(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    ticket = _ticket()
    await _issue_and_release_lane(issue_engine, ticket)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        exact = await uow.entry_admission.count_active_family_tickets(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exposure_family=ticket.exposure_family,
        )
        other_account = (
            await uow.entry_admission.count_active_family_tickets(
                venue_id=ticket.identity.netting_domain.venue_id,
                account_id="other-account",
                exposure_family=ticket.exposure_family,
            )
        )
        other_venue = (
            await uow.entry_admission.count_active_family_tickets(
                venue_id="other-venue",
                account_id=ticket.identity.netting_domain.account_id,
                exposure_family=ticket.exposure_family,
            )
        )

    assert exact == 1
    assert other_account == 0
    assert other_venue == 0


@pytest.mark.asyncio
async def test_exposure_family_active_count_excludes_terminal_tickets(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    ticket = _ticket()
    await _issue_and_release_lane(issue_engine, ticket)
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == ticket.identity.ticket_id)
            .values(
                status="terminal",
                active_netting_domain_key=None,
                terminal_at_ms=2_000,
            )
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        active_count = (
            await uow.entry_admission.count_active_family_tickets(
                venue_id=ticket.identity.netting_domain.venue_id,
                account_id=ticket.identity.netting_domain.account_id,
                exposure_family=ticket.exposure_family,
            )
        )

    assert active_count == 0


@pytest.mark.asyncio
async def test_three_current_v4_claims_can_use_gross_stop_risk_capacity(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal(
        "signal-risk-2",
        "episode-risk-2",
        position_side="short",
    )
    third = _ticket_for_strategy_group(
        "signal-risk-3",
        "episode-risk-3",
        strategy_group_id="MI-001",
        strategy_version_id="MI-001:v2",
        event_spec_id="mi-long-v2",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        runtime_scope_id="scope-mi-eth-long",
    )
    await _seed_ticket_runtime_scope(issue_engine, third)
    second_request = _issue_request(
        ticket=second,
        now_ms=1_002,
        claim_owner="worker-risk-2",
        stress_balance=Decimal(300),
    )
    third_request = _issue_request(
        ticket=third,
        now_ms=1_003,
        claim_owner="worker-risk-3",
        stress_balance=Decimal(300),
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        first_result = await issue_ticket(
            uow,
            _issue_request(
                ticket=first,
                now_ms=1_001,
                claim_owner="worker-risk-1",
                stress_balance=Decimal(300),
            ),
        )
    assert first_result.status is IssueTicketStatus.ISSUED
    await _release_global_entry_lane(issue_engine)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        second_result = await issue_ticket(uow, second_request)
    assert second_result.status is IssueTicketStatus.ISSUED
    await _release_global_entry_lane(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        third_result = await issue_ticket(uow, third_request)
        exposure = await uow.entry_admission.get_account_exposure(
            first.identity.netting_domain.venue_id,
            first.identity.netting_domain.account_id,
        )

    assert third_result.status is IssueTicketStatus.ISSUED
    assert exposure is not None
    assert exposure.gross_risk_at_stop == Decimal(9)
    assert exposure.active_ticket_count == 3


@pytest.mark.asyncio
async def test_three_current_v4_claims_can_use_gross_margin_capacity(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket(risk_at_stop=Decimal(3), reserved_margin=Decimal(45))
    second_base = _ticket_for_signal(
        "signal-margin-2",
        "episode-margin-2",
        position_side="short",
    )
    second = _ticket(
        identity=second_base.identity,
        runtime_scope_id=second_base.runtime_scope_id,
        universe_version_id=second_base.universe_version_id,
        initial_stop_price=second_base.initial_stop_price,
        take_profit_prices=second_base.take_profit_prices,
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(45),
    )
    third = _ticket_for_strategy_group(
        "signal-margin-3",
        "episode-margin-3",
        strategy_group_id="MI-001",
        strategy_version_id="MI-001:v2",
        event_spec_id="mi-long-v2",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        runtime_scope_id="scope-mi-eth-long",
        risk_at_stop=Decimal(3),
        reserved_margin=Decimal(45),
    )
    await _seed_ticket_runtime_scope(issue_engine, third)
    second_request = _issue_request(
        ticket=second,
        now_ms=1_002,
        claim_owner="worker-margin-2",
        stress_balance=Decimal(300),
        ticket_margin_budget=Decimal(45),
    )
    third_request = _issue_request(
        ticket=third,
        now_ms=1_003,
        claim_owner="worker-margin-3",
        stress_balance=Decimal(300),
        ticket_margin_budget=Decimal(45),
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        first_result = await issue_ticket(
            uow,
            _issue_request(
                ticket=first,
                now_ms=1_001,
                claim_owner="worker-margin-1",
                stress_balance=Decimal(300),
                ticket_margin_budget=Decimal(45),
            ),
        )
    assert first_result.status is IssueTicketStatus.ISSUED
    await _release_global_entry_lane(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        second_result = await issue_ticket(uow, second_request)
    assert second_result.status is IssueTicketStatus.ISSUED
    await _release_global_entry_lane(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        third_result = await issue_ticket(uow, third_request)
        exposure = await uow.entry_admission.get_account_exposure(
            first.identity.netting_domain.venue_id,
            first.identity.netting_domain.account_id,
        )

    assert third_result.status is IssueTicketStatus.ISSUED
    assert exposure is not None
    assert exposure.current_reserved_margin == Decimal(135)
    assert exposure.gross_risk_at_stop == Decimal(9)
    assert exposure.active_ticket_count == 3


@pytest.mark.asyncio
async def test_one_signal_cannot_create_a_second_ticket_identity(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-1", "episode-2", position_side="short")
    await _issue_and_release_lane(issue_engine, first)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_010, claim_owner="worker-2"),
        )

    assert result.status is IssueTicketStatus.DUPLICATE_SIGNAL


@pytest.mark.asyncio
async def test_two_worker_race_has_exactly_one_global_entry_winner(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    long_ticket = _ticket()
    short_ticket = _ticket_for_signal(
        "signal-2",
        "episode-2",
        position_side="short",
    )

    async def attempt(ticket, worker: str):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            return await issue_ticket(
                uow,
                _issue_request(ticket=ticket, now_ms=1_001, claim_owner=worker),
            )

    results = await asyncio.gather(
        attempt(long_ticket, "worker-long"),
        attempt(short_ticket, "worker-short"),
    )

    assert sorted(result.status for result in results) == sorted(
        [IssueTicketStatus.ISSUED, IssueTicketStatus.ENTRY_LANE_OCCUPIED]
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        persisted = [
            await uow.tickets.get(long_ticket.identity.ticket_id),
            await uow.tickets.get(short_ticket.identity.ticket_id),
        ]
    assert sum(ticket is not None for ticket in persisted) == 1


async def _seed_policy(
    engine: AsyncEngine,
    *,
    policy_version: int = 7,
    enabled: bool = True,
    new_entry_submit_enabled: bool = True,
    max_concurrent_tickets: int = 3,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=policy_version,
                enabled=enabled,
                new_entry_submit_enabled=new_entry_submit_enabled,
                priority_rank=1,
                max_concurrent_tickets=max_concurrent_tickets,
                max_strategy_group_concurrent_tickets=2,
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction="0.02",
                max_gross_stop_risk_fraction="0.06",
                max_ticket_initial_margin_fraction="0.30",
                max_gross_initial_margin_utilization="0.90",
                directional_stop_risk_limit_fraction="0.04",
                min_materialization_ratio="0.50",
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": "mi-long-v2",
                            "runtime_profile_id": "tiny-live-v1",
                        },
                        {
                            "event_spec_id": "sor-long-v2",
                            "runtime_profile_id": "tiny-live-v1",
                        },
                        {
                            "event_spec_id": "sor-short-v2",
                            "runtime_profile_id": "tiny-live-v1",
                        },
                    ]
                },
                updated_at_ms=1_000,
            )
        )
        identity = _identity()
        await _seed_ticket_registry(connection, _ticket())
        await _seed_ticket_registry(
            connection,
            _ticket_for_signal("signal-seed-short", "episode-seed-short", position_side="short"),
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="scope-sor-btc-long",
                strategy_group_id=identity.runtime.strategy_group_id,
                strategy_version_id=identity.runtime.strategy_version_id,
                event_spec_id=identity.runtime.event_spec_id,
                runtime_profile_id=identity.runtime.runtime_profile_id,
                owner_policy_id="policy-main",
                exchange_instrument_id=(
                    identity.netting_domain.exchange_instrument_id
                ),
                position_side="long",
                universe_version_id=_ticket().universe_version_id,
                universe_semantic_digest=_ticket().universe_semantic_digest,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=4,
                warm_closed_bar_time_ms=900,
                warm_completed_at_ms=900,
                warm_readiness_digest=_ticket().universe_semantic_digest,
                warm_valid_until_ms=2_000,
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="scope-short",
                strategy_group_id=identity.runtime.strategy_group_id,
                strategy_version_id=identity.runtime.strategy_version_id,
                event_spec_id="sor-short-v2",
                runtime_profile_id=identity.runtime.runtime_profile_id,
                owner_policy_id="policy-main",
                exchange_instrument_id=(
                    identity.netting_domain.exchange_instrument_id
                ),
                position_side="short",
                universe_version_id="universe:sor-short:4",
                universe_semantic_digest=_ticket().universe_semantic_digest,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=4,
                warm_closed_bar_time_ms=900,
                warm_completed_at_ms=900,
                warm_readiness_digest=_ticket().universe_semantic_digest,
                warm_valid_until_ms=2_000,
                updated_at_ms=1_000,
            )
        )


async def _issue_and_release_lane(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED
    await _release_global_entry_lane(engine)


async def _release_global_entry_lane(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(entry_lane_current).values(
                ticket_id=None,
                signal_event_id=None,
                status="idle",
                claimed_at_ms=None,
                lease_until_ms=None,
                claim_owner=None,
                version=entry_lane_current.c.version + 1,
            )
        )


async def _wait_for_database_blocker(
    engine: AsyncEngine,
    *,
    blocked_backend_pid: int,
    blocker_backend_pid: int,
) -> None:
    async def wait_until_observed() -> None:
        while True:
            async with engine.connect() as connection:
                blocking_pids = await connection.scalar(
                    sa.text("SELECT pg_blocking_pids(:blocked_backend_pid)"),
                    {"blocked_backend_pid": blocked_backend_pid},
                )
            if blocker_backend_pid in blocking_pids:
                return
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_until_observed(), timeout=2)


async def _seed_replacement_universe(engine: AsyncEngine, ticket) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id="universe:sor-long:replacement",
                strategy_group_id=ticket.identity.runtime.strategy_group_id,
                event_spec_id=ticket.identity.runtime.event_spec_id,
                universe_version=2,
                semantic_digest="sha256:" + "b" * 64,
                lifecycle_state="active",
                installed_at_ms=1_000,
                activated_at_ms=1_001,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members).values(
                universe_version_id="universe:sor-long:replacement",
                exchange_instrument_id=(
                    ticket.identity.netting_domain.exchange_instrument_id
                ),
            )
        )


def _ticket_for_signal(
    signal_event_id: str,
    exposure_episode_id: str,
    *,
    position_side: Literal["long", "short"],
):
    original = _identity()
    runtime = (
        original.runtime
        if position_side == "long"
        else original.runtime.model_copy(update={"event_spec_id": "sor-short-v2"})
    )
    domain = NettingDomain(
        venue_id=original.netting_domain.venue_id,
        account_id=original.netting_domain.account_id,
        exchange_instrument_id=original.netting_domain.exchange_instrument_id,
        position_side=position_side,
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=runtime,
        netting_domain=domain,
    )
    terms: dict[str, object] = {
        "identity": identity,
        "runtime_scope_id": (
            "scope-sor-btc-long" if position_side == "long" else "scope-short"
        ),
    }
    if position_side == "short":
        terms.update(
            {
                "universe_version_id": "universe:sor-short:4",
                "initial_stop_price": Decimal(61000),
                "take_profit_prices": (Decimal(58000),),
            }
        )
    return _ticket(**terms)


def _ticket_for_instrument(
    signal_event_id: str,
    exposure_episode_id: str,
    *,
    exchange_instrument_id: str,
    runtime_scope_id: str,
    **updates: object,
):
    original = _identity()
    domain = NettingDomain(
        venue_id=original.netting_domain.venue_id,
        account_id=original.netting_domain.account_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side="long",
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=original.runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=original.runtime,
        netting_domain=domain,
    )
    terms: dict[str, object] = {
        "identity": identity,
        "runtime_scope_id": runtime_scope_id,
    }
    terms.update(updates)
    return _ticket(**terms)


def _ticket_for_strategy_group(
    signal_event_id: str,
    exposure_episode_id: str,
    *,
    strategy_group_id: str,
    strategy_version_id: str,
    event_spec_id: str,
    exchange_instrument_id: str,
    runtime_scope_id: str,
    **updates: object,
):
    original = _identity()
    runtime = original.runtime.model_copy(
        update={
            "strategy_group_id": strategy_group_id,
            "strategy_version_id": strategy_version_id,
            "event_spec_id": event_spec_id,
        }
    )
    domain = NettingDomain(
        venue_id=original.netting_domain.venue_id,
        account_id=original.netting_domain.account_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side="long",
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=runtime,
        netting_domain=domain,
    )
    terms: dict[str, object] = {
        "identity": identity,
        "runtime_scope_id": runtime_scope_id,
        "universe_version_id": f"universe:{event_spec_id}:1",
        "exit_policy_id": f"exit-policy:{event_spec_id}",
        "exposure_family": (
            "opening_range"
            if strategy_group_id == "SOR-001"
            else "long_continuation"
        ),
        "family_ticket_limit": 2 if strategy_group_id == "SOR-001" else 1,
        "pre_tp1_reclaim_price": None,
        "exposure_session_end_ms": None,
    }
    terms.update(updates)
    return _ticket(**terms)


def _issue_request(
    *,
    ticket,
    now_ms: int,
    claim_owner: str,
    stress_balance: Decimal | None = None,
    ticket_margin_budget: Decimal = Decimal(30),
) -> IssueTicketRequest:
    configured_leverage = (
        ticket.selected_leverage - 1
        if ticket.leverage_change_required
        else ticket.selected_leverage
    )
    resolved_stress_balance = (
        Decimal(300)
        if stress_balance is None
        else stress_balance
    )
    return IssueTicketRequest(
        capacity_claim=freeze_capacity_claim(
            ticket_identity=ticket.identity,
            owner_policy_id=ticket.owner_policy_id,
            owner_policy_version=ticket.owner_policy_version,
            runtime_scope_id=ticket.runtime_scope_id,
            runtime_scope_version=ticket.runtime_scope_version,
            universe_version_id=ticket.universe_version_id,
            universe_semantic_digest=ticket.universe_semantic_digest,
            fact_digest=ticket.fact_digest,
            exit_policy_id=ticket.exit_policy_id,
            exit_policy_semantic_hash=ticket.exit_policy_semantic_hash,
            entry_admission_snapshot_digest="sha256:" + "2" * 64,
            account_entry_health_digest="sha256:" + "3" * 64,
            instrument_entry_health_digest="sha256:" + "4" * 64,
            instrument_rules_projection_version=1,
            account_capacity_domain_key=(
                f"{ticket.identity.netting_domain.venue_id}:"
                f"{ticket.identity.netting_domain.account_id}"
            ),
            leverage_domain_key=(
                f"{ticket.identity.netting_domain.venue_id}:"
                f"{ticket.identity.netting_domain.account_id}:"
                f"{ticket.identity.netting_domain.exchange_instrument_id}"
            ),
            total_wallet_balance_at_claim=resolved_stress_balance,
            total_margin_balance_at_claim=resolved_stress_balance,
            total_initial_margin_at_claim=Decimal(0),
            total_maintenance_margin_at_claim=Decimal(0),
            available_margin_at_claim=resolved_stress_balance,
            mark_price_at_claim=ticket.entry_reference_price,
            position_mode_at_claim="independent_sides",
            margin_mode_at_claim=ticket.margin_mode,
            active_ticket_count_at_claim=0,
            remaining_slots_at_claim=3,
            exposure_family=ticket.exposure_family,
            active_family_ticket_count_at_claim=0,
            family_ticket_limit=ticket.family_ticket_limit,
            remaining_family_slots_at_claim=ticket.family_ticket_limit,
            gross_risk_at_stop_at_claim=Decimal(0),
            directional_risk_at_stop_at_claim=Decimal(0),
            current_reserved_margin_at_claim=Decimal(0),
            max_ticket_stop_risk_fraction=Decimal("0.02"),
            max_gross_stop_risk_fraction=Decimal("0.06"),
            directional_stop_risk_limit_fraction=Decimal("0.04"),
            max_ticket_initial_margin_fraction=Decimal("0.30"),
            min_materialization_ratio=Decimal("0.50"),
            minimum_stop_risk_budget=Decimal(3),
            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
            max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
            post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
            max_gross_initial_margin_utilization=Decimal("0.90"),
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            ticket_margin_budget=ticket_margin_budget,
            required_leverage=ticket.selected_leverage,
            selected_leverage=ticket.selected_leverage,
            configured_leverage_at_claim=configured_leverage,
            leverage_change_required=ticket.leverage_change_required,
            exchange_max_leverage=10,
            reserved_margin=ticket.reserved_margin,
            cross_margin_stress_evidence=_stress_evidence(
                ticket,
                stress_balance=resolved_stress_balance,
            ),
            created_at_ms=ticket.created_at_ms,
            expires_at_ms=ticket.expires_at_ms,
            entry_reference_price=ticket.entry_reference_price,
            quantity=ticket.quantity,
            notional=ticket.notional,
            risk_at_stop=ticket.risk_at_stop,
            entry_order_type=ticket.entry_order_type,
            entry_limit_price=ticket.entry_limit_price,
            initial_stop_price=ticket.initial_stop_price,
            pre_tp1_reclaim_price=ticket.pre_tp1_reclaim_price,
            exposure_session_end_ms=ticket.exposure_session_end_ms,
            take_profit_prices=ticket.take_profit_prices,
            take_profit_quantities=ticket.take_profit_quantities,
        ),
        now_ms=now_ms,
        claim_owner=claim_owner,
    )


def _stress_evidence(ticket, *, stress_balance: Decimal | None = None):
    resolved_stress_balance = (
        max(Decimal(100), ticket.notional * Decimal(10))
        if stress_balance is None
        else stress_balance
    )
    configured_leverage = (
        ticket.selected_leverage - 1
        if ticket.leverage_change_required
        else ticket.selected_leverage
    )
    snapshot = AccountRiskSnapshot.create(
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        account_risk_mode="standard_usdm_single_asset",
        settlement_asset="USDT",
        position_mode="independent_sides",
        margin_mode="cross",
        exchange_instrument_id=(
            ticket.identity.netting_domain.exchange_instrument_id
        ),
        mark_price=ticket.entry_reference_price,
        configured_leverage=configured_leverage,
        total_wallet_balance=resolved_stress_balance,
        total_margin_balance=resolved_stress_balance,
        total_initial_margin=Decimal(0),
        total_maintenance_margin=Decimal(0),
        available_margin=resolved_stress_balance,
        account_positions=(),
        observed_at_ms=ticket.created_at_ms,
        valid_until_ms=ticket.expires_at_ms,
    )
    bracket = MaintenanceMarginBracket(
        bracket_id="test:1",
        notional_floor=Decimal(0),
        notional_cap=None,
        maintenance_margin_rate=Decimal("0.004"),
        maintenance_amount=Decimal(0),
    )
    return evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=snapshot,
            maintenance_margin_brackets=(bracket,),
            maintenance_margin_brackets_digest="sha256:" + "5" * 64,
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            evaluated_side=ticket.identity.netting_domain.position_side,
            reference_entry_price=ticket.entry_reference_price,
            initial_stop_price=ticket.initial_stop_price,
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            projected_instrument_positions=(
                StressPosition(
                    position_side=(
                        ticket.identity.netting_domain.position_side
                    ),
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                ),
            ),
        )
    )


def _expected_leverage_fact_digest(*, claim) -> str:
    return canonical_digest(
        {
            "entry_admission_snapshot_digest": (
                claim.entry_admission_snapshot_digest
            ),
            "instrument_facts": {
                "exchange_instrument_id": (
                    claim.ticket_identity.netting_domain.exchange_instrument_id
                ),
                "mark_price": claim.mark_price_at_claim,
                "configured_leverage": claim.configured_leverage_at_claim,
            },
        }
    )


async def _assert_no_durable_entry_state(
    engine: AsyncEngine,
    ticket_id: str,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.tickets.get(ticket_id) is None
        assert await uow.capacity_claims.get_for_ticket(ticket_id) is None
        assert await uow.budgets.get_for_ticket(ticket_id) is None
        assert await uow.exchange_commands.list_for_ticket(ticket_id) == []
        lane = await uow.entry_admission.get_global_lane()
        assert lane is not None
        assert lane.status == "idle"
        assert lane.ticket_id is None
    async with engine.connect() as connection:
        incident_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(runtime_incidents)
            .where(runtime_incidents.c.ticket_id == ticket_id)
        )
    assert incident_count == 0


async def _seed_ticket_runtime_scope(engine: AsyncEngine, ticket) -> None:
    """Give direct Ticket tests the same current Scope authority as production."""

    identity = ticket.identity
    values = {
        "runtime_scope_id": ticket.runtime_scope_id,
        "strategy_group_id": identity.runtime.strategy_group_id,
        "strategy_version_id": identity.runtime.strategy_version_id,
        "event_spec_id": identity.runtime.event_spec_id,
        "runtime_profile_id": identity.runtime.runtime_profile_id,
        "owner_policy_id": ticket.owner_policy_id,
        "exchange_instrument_id": identity.netting_domain.exchange_instrument_id,
        "position_side": identity.netting_domain.position_side,
        "universe_version_id": ticket.universe_version_id,
        "universe_semantic_digest": ticket.universe_semantic_digest,
        "lifecycle_state": "active",
        "observation_enabled": True,
        "entry_enabled": True,
        "scope_version": ticket.runtime_scope_version,
        "warm_closed_bar_time_ms": ticket.created_at_ms,
        "warm_completed_at_ms": ticket.created_at_ms,
        "warm_readiness_digest": ticket.universe_semantic_digest,
        "warm_valid_until_ms": ticket.expires_at_ms,
        "updated_at_ms": ticket.created_at_ms,
    }
    async with engine.begin() as connection:
        await _seed_ticket_registry(connection, ticket)
        await connection.execute(
            pg_insert(runtime_scopes_current)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[runtime_scopes_current.c.runtime_scope_id],
                set_=values,
            )
        )


async def _seed_ticket_registry(connection, ticket) -> None:
    identity = ticket.identity
    runtime = identity.runtime
    instrument = parse_binance_usdm_instrument_id(
        identity.netting_domain.exchange_instrument_id
    )
    await connection.execute(
        pg_insert(instruments)
        .values(
            exchange_instrument_id=identity.netting_domain.exchange_instrument_id,
            venue_id=identity.netting_domain.venue_id,
            asset_class="crypto",
            venue_symbol=instrument.symbol,
            contract_kind="perpetual",
            status="active",
        )
        .on_conflict_do_nothing(
            index_elements=[instruments.c.exchange_instrument_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_groups)
        .values(
            strategy_group_id=runtime.strategy_group_id,
            display_name=runtime.strategy_group_id,
            active_version_id=runtime.strategy_version_id,
            status="active",
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_groups.c.strategy_group_id],
            set_={
                "active_version_id": runtime.strategy_version_id,
                "status": "active",
                "updated_at_ms": ticket.created_at_ms,
            },
        )
    )
    authorization_id = f"owner-authorization:seed:{runtime.strategy_group_id}"
    event_id = f"strategy-control-event:seed:{runtime.strategy_group_id}"
    await connection.execute(
        pg_insert(owner_authorizations)
        .values(
            authorization_id=authorization_id,
            purpose="strategy_resume",
            owner_identity="system-seed",
            authentication_strength="session",
            request_digest="sha256:" + "0" * 64,
            target_scope={"seed": True},
            idempotency_key=f"owner-request:seed:{runtime.strategy_group_id}",
            authorized_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(index_elements=[owner_authorizations.c.authorization_id])
    )
    await connection.execute(
        pg_insert(strategy_entry_control_events)
        .values(
            strategy_entry_control_event_id=event_id,
            strategy_group_id=runtime.strategy_group_id,
            control_version=1,
            operation="resume",
            target_state="enabled",
            authorization_id=authorization_id,
            reason="seed_enabled",
            payload={},
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[strategy_entry_control_events.c.strategy_entry_control_event_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_entry_controls_current)
        .values(
            strategy_group_id=runtime.strategy_group_id,
            entry_state="enabled",
            control_version=1,
            last_event_id=event_id,
            reason="seed_enabled",
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[strategy_entry_controls_current.c.strategy_group_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_versions)
        .values(
            strategy_version_id=runtime.strategy_version_id,
            strategy_group_id=runtime.strategy_group_id,
            version=1,
            semantics={},
            status="active",
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_versions.c.strategy_version_id],
            set_={
                "strategy_group_id": runtime.strategy_group_id,
                "status": "active",
            },
        )
    )
    await connection.execute(
        pg_insert(event_specs)
        .values(
            event_spec_id=runtime.event_spec_id,
            strategy_version_id=runtime.strategy_version_id,
            event_id=f"event:{runtime.event_spec_id}",
            position_side=identity.netting_domain.position_side,
            timeframe="1h",
            freshness_window_ms=1_000,
            event_time_authority="close_time",
            entry_order_type=ticket.entry_order_type.value,
            protection_reference_fact_definition_id="fact:protection",
            exit_policy_id=f"exit:{runtime.event_spec_id}",
            execution_semantics={},
            status="active",
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[event_specs.c.event_spec_id],
            set_={
                "strategy_version_id": runtime.strategy_version_id,
                "position_side": identity.netting_domain.position_side,
                "entry_order_type": ticket.entry_order_type.value,
                "status": "active",
            },
        )
    )
    await connection.execute(
        pg_insert(event_product_compatibility)
        .values(
            event_spec_id=runtime.event_spec_id,
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            semantic_digest="sha256:" + "f" * 64,
            created_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[event_product_compatibility.c.event_spec_id]
        )
    )
    await connection.execute(
        pg_insert(instrument_product_profiles)
        .values(
            exchange_instrument_id=(
                identity.netting_domain.exchange_instrument_id
            ),
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            entry_session_policy="continuous",
            status="candidate",
            max_entry_spread_bps=None,
            max_mark_index_deviation_bps=None,
            semantic_digest="sha256:" + "e" * 64,
            updated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[instrument_product_profiles.c.exchange_instrument_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_versions)
        .values(
            universe_version_id=ticket.universe_version_id,
            strategy_group_id=runtime.strategy_group_id,
            event_spec_id=runtime.event_spec_id,
            universe_version=1,
            semantic_digest=ticket.universe_semantic_digest,
            lifecycle_state="active",
            installed_at_ms=ticket.created_at_ms,
            activated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_nothing(
            index_elements=[strategy_universe_versions.c.universe_version_id]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_members)
        .values(
            universe_version_id=ticket.universe_version_id,
            exchange_instrument_id=identity.netting_domain.exchange_instrument_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                strategy_universe_members.c.universe_version_id,
                strategy_universe_members.c.exchange_instrument_id,
            ]
        )
    )
    await connection.execute(
        pg_insert(strategy_universe_current)
        .values(
            event_spec_id=runtime.event_spec_id,
            universe_version_id=ticket.universe_version_id,
            semantic_digest=ticket.universe_semantic_digest,
            lifecycle_state="active",
            activation_generation=1,
            activated_at_ms=ticket.created_at_ms,
        )
        .on_conflict_do_update(
            index_elements=[strategy_universe_current.c.event_spec_id],
            set_={
                "universe_version_id": ticket.universe_version_id,
                "semantic_digest": ticket.universe_semantic_digest,
                "lifecycle_state": "active",
                "activated_at_ms": ticket.created_at_ms,
            },
        )
    )
