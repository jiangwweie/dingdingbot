from __future__ import annotations

import asyncio
from decimal import Decimal
import os
from pathlib import Path
import re
import subprocess
import sys
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
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    SetLeverageCommandPayload,
)
from src.trading_kernel.domain.capacity import freeze_capacity_claim
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    canonical_digest,
)
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    entry_lane_current,
    event_specs,
    owner_policy_current,
    runtime_incidents,
    runtime_scopes_current,
    strategy_groups,
    strategy_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.test_ticket import _identity, _ticket


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def issue_engine() -> AsyncEngine:
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
    ticket = _ticket(leverage_change_required=True)
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
        (ExchangeCommandKind.SET_LEVERAGE, 1)
    ]
    assert isinstance(commands[0].payload, SetLeverageCommandPayload)
    assert commands[0].venue_client_order_id is None
    assert commands[0].payload.leverage_fact_digest == _expected_leverage_fact_digest(
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
                        enabled=False,
                        scope_version=ticket.runtime_scope_version + 1,
                    )
                )
            return exposure

        uow.entry_admission.get_account_exposure = drift_scope_after_account_lock
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
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

        uow.entry_admission.get_account_exposure = open_incident_after_account_lock
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
                planned_stop_risk_fraction="0.03",
                max_initial_margin_utilization="0.90",
                max_leverage=10,
                supported_margin_mode="cross",
                min_liquidation_distance_to_stop_distance_ratio="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={},
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
                enabled=True,
                scope_version=4,
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
                enabled=True,
                scope_version=4,
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


def _ticket_for_signal(
    signal_event_id: str,
    exposure_episode_id: str,
    *,
    position_side: str,
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
                "initial_stop_price": Decimal("61000"),
                "take_profit_prices": (Decimal("58000"),),
                "projected_liquidation_price": Decimal("63000"),
            }
        )
    return _ticket(**terms)


def _issue_request(*, ticket, now_ms: int, claim_owner: str) -> IssueTicketRequest:
    configured_leverage = (
        ticket.selected_leverage - 1
        if ticket.leverage_change_required
        else ticket.selected_leverage
    )
    return IssueTicketRequest(
        capacity_claim=freeze_capacity_claim(
            ticket_identity=ticket.identity,
            owner_policy_id=ticket.owner_policy_id,
            owner_policy_version=ticket.owner_policy_version,
            runtime_scope_id=ticket.runtime_scope_id,
            runtime_scope_version=ticket.runtime_scope_version,
            fact_digest=ticket.fact_digest,
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
            total_wallet_balance_at_claim=Decimal("100"),
            total_margin_balance_at_claim=Decimal("100"),
            total_initial_margin_at_claim=Decimal("0"),
            total_maintenance_margin_at_claim=Decimal("0"),
            available_margin_at_claim=Decimal("100"),
            mark_price_at_claim=ticket.entry_reference_price,
            position_mode_at_claim="independent_sides",
            margin_mode_at_claim=ticket.margin_mode,
            active_ticket_count_at_claim=0,
            remaining_slots_at_claim=3,
            planned_stop_risk_fraction=Decimal("0.03"),
            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
            max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
            post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
            max_initial_margin_utilization=Decimal("0.90"),
            min_liquidation_distance_to_stop_distance_ratio=(
                ticket.min_liquidation_distance_to_stop_distance_ratio
            ),
            ticket_margin_budget=Decimal("30"),
            required_leverage=ticket.selected_leverage,
            selected_leverage=ticket.selected_leverage,
            configured_leverage_at_claim=configured_leverage,
            leverage_change_required=ticket.leverage_change_required,
            exchange_max_leverage=10,
            reserved_margin=ticket.reserved_margin,
            maintenance_margin_bracket_id="test:1",
            projected_liquidation_price=ticket.projected_liquidation_price,
            projected_liquidation_distance=Decimal("2000"),
            projected_liquidation_distance_to_stop_distance_ratio=(
                ticket.projected_liquidation_distance_to_stop_distance_ratio
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
            take_profit_prices=ticket.take_profit_prices,
            take_profit_quantities=ticket.take_profit_quantities,
        ),
        now_ms=now_ms,
        claim_owner=claim_owner,
    )


def _expected_leverage_fact_digest(*, claim) -> str:
    instrument_facts = AdmissionInstrumentFacts(
        exchange_instrument_id=(
            claim.ticket_identity.netting_domain.exchange_instrument_id
        ),
        mark_price=claim.mark_price_at_claim,
        configured_leverage=claim.configured_leverage_at_claim,
    )
    return canonical_digest(
        {
            "entry_admission_snapshot_digest": (
                claim.entry_admission_snapshot_digest
            ),
            "instrument_facts": instrument_facts,
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
        "enabled": True,
        "scope_version": ticket.runtime_scope_version,
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


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
