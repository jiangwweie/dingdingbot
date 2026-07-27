from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    entry_lane_current,
    owner_policy_current,
    owner_policy_events,
    positions_current,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_scopes_current,
    strategy_universe_cutovers,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    build_runtime_seed_identity,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.strategy_universe_cutover import (
    StrategyUniverseCutoverBlocked,
    StrategyUniverseCutoverRequest,
    apply_strategy_universe_cutover,
    inspect_strategy_universe_cutover,
)
from tests.trading_kernel.integration.test_runtime_authority_seed import (
    _insert_terminal_reviewed_ticket,
    runtime_seed_engine,  # noqa: F401
)


COMMIT = "a" * 40
APPLIED_AT_MS = 1_800_000_100_000


@pytest.mark.asyncio
async def test_cutover_dry_run_is_read_only_and_apply_replay_is_idempotent(
    runtime_seed_engine: AsyncEngine,  # noqa: F811
) -> None:
    request = await _seed_cutover_runtime(runtime_seed_engine)
    await _insert_append_only_signal(runtime_seed_engine)

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        dry_run = await inspect_strategy_universe_cutover(uow, request)
    assert dry_run.status == "ready"
    assert dry_run.before_counts.runtime_scope_count == 49

    async with runtime_seed_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_cutovers)
        ) == 0

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        applied = await apply_strategy_universe_cutover(uow, request)
    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        replay = await apply_strategy_universe_cutover(uow, request)

    assert applied.status == "applied"
    assert replay == applied
    assert applied.after_counts is not None
    assert applied.after_counts.runtime_scope_count == 49
    async with runtime_seed_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_cutovers)
        ) == 1
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_scopes_current)
        ) == 49
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_events).where(
                trade_events.c.event_id == "append-only-signal-marker"
            )
        ) == 1
        policy = (
            await connection.execute(sa.select(owner_policy_current))
        ).mappings().one()
        assert policy["policy_version"] == 2
        assert policy["new_entry_submit_enabled"] is True
        capabilities = {
            str(row["capability_key"]): bool(row["enabled"])
            for row in (
                await connection.execute(
                    sa.select(runtime_capabilities_current)
                )
            ).mappings()
        }
        assert capabilities == {
            "exchange_commands": True,
            "strategy_signal_ingest": True,
        }


@pytest.mark.asyncio
async def test_cutover_terminalizes_only_exact_owner_flat_ticket_and_incident(
    runtime_seed_engine: AsyncEngine,  # noqa: F811
) -> None:
    await _seed_cutover_runtime(runtime_seed_engine)
    await _insert_active_cutover_ticket(runtime_seed_engine)
    request = _cutover_request(
        terminal_ticket_ids=("ticket-acceptance",),
        resolved_incident_ids=("incident:cutover-ticket",),
    )

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        inspection = await inspect_strategy_universe_cutover(uow, request)
    assert inspection.status == "ready"
    assert inspection.before_counts.active_ticket_count == 1
    assert inspection.before_counts.nonzero_position_count == 1
    assert inspection.before_counts.open_incident_count == 1

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        result = await apply_strategy_universe_cutover(uow, request)
    assert result.status == "applied"

    async with runtime_seed_engine.connect() as connection:
        ticket = (
            await connection.execute(
                sa.select(trade_tickets).where(
                    trade_tickets.c.ticket_id == "ticket-acceptance"
                )
            )
        ).mappings().one()
        aggregate = (
            await connection.execute(
                sa.select(trade_aggregates).where(
                    trade_aggregates.c.ticket_id == "ticket-acceptance"
                )
            )
        ).mappings().one()
        reservation = (
            await connection.execute(
                sa.select(budget_reservations).where(
                    budget_reservations.c.ticket_id == "ticket-acceptance"
                )
            )
        ).mappings().one()
        incident = (
            await connection.execute(
                sa.select(runtime_incidents).where(
                    runtime_incidents.c.incident_id
                    == "incident:cutover-ticket"
                )
            )
        ).mappings().one()
        cutover_event = (
            await connection.execute(
                sa.select(trade_events).where(
                    trade_events.c.ticket_id == "ticket-acceptance",
                    trade_events.c.event_type == "CutoverTerminalized",
                )
            )
        ).mappings().one()
        review = (
            await connection.execute(
                sa.select(trade_reviews).where(
                    trade_reviews.c.ticket_id == "ticket-acceptance"
                )
            )
        ).mappings().one()

    assert ticket["status"] == "cutover_terminal"
    assert ticket["active_netting_domain_key"] is None
    assert ticket["terminal_at_ms"] == APPLIED_AT_MS
    assert aggregate["status"] == "terminal"
    assert Decimal(aggregate["position_qty"]) == 0
    assert aggregate["last_event_sequence"] == 2
    assert reservation["status"] == "released"
    assert incident["status"] == "resolved"
    assert cutover_event["payload"]["external_flat_verification_digest"] == (
        "sha256:" + "f" * 64
    )
    assert review["outcome"] == "external_flat_cutover"


@pytest.mark.asyncio
async def test_cutover_blocks_wrong_exact_identity_without_mutation(
    runtime_seed_engine: AsyncEngine,  # noqa: F811
) -> None:
    request = await _seed_cutover_runtime(runtime_seed_engine)
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_capabilities_current)
            .where(
                runtime_capabilities_current.c.capability_key
                == "exchange_commands"
            )
            .values(enabled=True)
        )

    async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
        inspection = await inspect_strategy_universe_cutover(uow, request)
    assert inspection.status == "blocked"
    assert inspection.blockers == ("exchange_commands_not_fenced",)

    with pytest.raises(
        StrategyUniverseCutoverBlocked,
        match="exchange_commands_not_fenced",
    ):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await apply_strategy_universe_cutover(uow, request)
    async with runtime_seed_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_scopes_current)
        ) == 49
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_cutovers)
        ) == 0


@pytest.mark.asyncio
async def test_cutover_mid_transaction_failure_rolls_back_every_mutation(
    runtime_seed_engine: AsyncEngine,  # noqa: F811
) -> None:
    request = await _seed_cutover_runtime(runtime_seed_engine)
    async with runtime_seed_engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_events).values(
                owner_policy_event_id="policy-event:forced-conflict",
                owner_policy_id="policy-main",
                policy_version=2,
                operation="forced_conflict",
                payload={},
                created_at_ms=APPLIED_AT_MS - 1,
            )
        )

    with pytest.raises(IntegrityError):
        async with PostgresKernelUnitOfWork(runtime_seed_engine) as uow:
            await apply_strategy_universe_cutover(uow, request)

    async with runtime_seed_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_scopes_current)
        ) == 49
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_cutovers)
        ) == 0
        policy = (
            await connection.execute(sa.select(owner_policy_current))
        ).mappings().one()
        assert policy["policy_version"] == 1
        assert policy["new_entry_submit_enabled"] is False


async def _seed_cutover_runtime(
    engine: AsyncEngine,
) -> StrategyUniverseCutoverRequest:
    seed_request = RuntimeAuthoritySeedRequest(
        account_id="subaccount-main",
        runtime_commit=COMMIT,
        schema_revision="0002_strategy_universe_us_equity",
        seeded_at_ms=1_800_000_000_000,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(uow, seed_request)
    return _cutover_request(
        target_seed_identity=build_runtime_seed_identity(seed_request)
    )


def _cutover_request(
    *,
    target_seed_identity: str | None = None,
    terminal_ticket_ids: tuple[str, ...] = (),
    resolved_incident_ids: tuple[str, ...] = (),
) -> StrategyUniverseCutoverRequest:
    if target_seed_identity is None:
        target_seed_identity = build_runtime_seed_identity(
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-main",
                runtime_commit=COMMIT,
                schema_revision="0002_strategy_universe_us_equity",
                seeded_at_ms=APPLIED_AT_MS,
            )
        )
    return StrategyUniverseCutoverRequest(
        cutover_id="cutover:strategy-universe:20260727",
        account_id="subaccount-main",
        target_runtime_commit=COMMIT,
        target_schema_revision="0002_strategy_universe_us_equity",
        target_seed_identity=target_seed_identity,
        external_flat_verification_digest="sha256:" + "f" * 64,
        terminal_ticket_ids=terminal_ticket_ids,
        resolved_incident_ids=resolved_incident_ids,
        applied_at_ms=APPLIED_AT_MS,
    )


async def _insert_append_only_signal(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(trade_events).values(
                event_id="append-only-signal-marker",
                ticket_id="historical-ticket",
                sequence=1,
                event_type="HistoricalAuditMarker",
                payload={},
                occurred_at_ms=1_800_000_000_010,
            )
        )


async def _insert_active_cutover_ticket(engine: AsyncEngine) -> None:
    await _insert_terminal_reviewed_ticket(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.delete(trade_reviews).where(
                trade_reviews.c.ticket_id == "ticket-acceptance"
            )
        )
        await connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == "ticket-acceptance")
            .values(
                status="position_protected",
                active_netting_domain_key="acceptance-domain",
                terminal_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(trade_aggregates).values(
                ticket_id="ticket-acceptance",
                status="position_protected",
                version=1,
                last_event_sequence=1,
                entry_lane_held=True,
                position_qty=Decimal("0.1"),
                protected_qty=Decimal("0.1"),
                tp1_target_qty=Decimal("0.05"),
                tp1_filled_qty=Decimal("0"),
                updated_at_ms=1_800_000_000_200,
            )
        )
        await connection.execute(
            sa.insert(trade_events).values(
                event_id="event:ticket-acceptance:issued",
                ticket_id="ticket-acceptance",
                sequence=1,
                event_type="TicketIssued",
                payload={},
                occurred_at_ms=1_800_000_000_110,
            )
        )
        await connection.execute(
            sa.insert(budget_reservations).values(
                budget_reservation_id="budget:ticket-acceptance",
                ticket_id="ticket-acceptance",
                owner_policy_id="policy-main",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                reserved_notional=Decimal("10"),
                reserved_risk=Decimal("1"),
                reserved_margin=Decimal("2"),
                planned_stop_risk_budget=Decimal("1"),
                risk_reservation_basis="planned_stop_distance",
                status="active",
                created_at_ms=1_800_000_000_110,
                released_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(positions_current).values(
                netting_domain_key="acceptance-domain",
                ticket_id="ticket-acceptance",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                quantity=Decimal("0.1"),
                average_entry_price=Decimal("100"),
                observed_at_ms=1_800_000_000_200,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(runtime_incidents).values(
                incident_id="incident:cutover-ticket",
                ticket_id="ticket-acceptance",
                incident_kind="external_flat",
                status="open",
                first_blocker="owner_manual_flat_cutover",
                entry_block_scope="none",
                entry_block_key=None,
                details={},
                opened_at_ms=1_800_000_000_200,
                resolved_at_ms=None,
            )
        )
        await connection.execute(
            sa.update(entry_lane_current).values(
                ticket_id="ticket-acceptance",
                signal_event_id="signal-acceptance",
                status="claimed",
                claimed_at_ms=1_800_000_000_200,
                lease_until_ms=1_800_000_100_000,
                claim_owner="old-worker",
            )
        )
        await connection.execute(
            sa.update(account_exposure_current).values(
                gross_notional=Decimal("10"),
                gross_risk_at_stop=Decimal("1"),
                active_ticket_count=1,
            )
        )
