from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_models import (
    budget_reservations,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    EntryWorkerStatus,
    run_entry_worker_once,
)
from tests.trading_kernel.full_chain.test_six_event_system_certification import (
    BNB,
    BTC,
    NOW_MS,
    CertifiedEntryAdmissionFactsSource,
    CertifiedMarketSource,
    CertifiedVenue,
    six_event_engine,  # noqa: F401
)
from tests.trading_kernel.full_chain.test_us_equity_strategy_certification import (
    ENTRY_TIME_MS,
    EVENT_SPEC_ID,
    TRIGGER_CLOSE_MS,
    TRIGGER_HOUR_MS,
    USEquityEntryFactsSource,
    _market_windows,
    _seed_complete_us_runtime,
    _warm_and_activate,
)
from tests.trading_kernel.integration.test_rsr_vcb_observation import (
    WindowSource,
    _trigger_window,
)
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec


@pytest.mark.asyncio
async def test_crypto_and_us_equity_share_three_ticket_and_portfolio_budgets(
    six_event_engine: AsyncEngine,  # noqa: F811
) -> None:
    await _seed_complete_us_runtime(six_event_engine)
    venue = CertifiedVenue()
    crypto_market = CertifiedMarketSource()

    first = await _observe_issue_and_protect_crypto(
        six_event_engine,
        venue=venue,
        market=crypto_market,
        runtime_scope_id="scope:SOR-LONG:BNBUSDT:long",
        instrument_id=BNB,
        observed_at_ms=NOW_MS,
    )

    universe = universe_for_event_spec(EVENT_SPEC_ID)
    windows = _market_windows(universe)
    us_market = WindowSource(windows)
    projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        us_market,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=TRIGGER_HOUR_MS,
        claim_owner="cross-asset-us-projection",
    )
    await _warm_and_activate(
        six_event_engine,
        universe=universe,
        projection_run_id=projection.projection_run_id,
    )
    armed = await _first_armed(
        six_event_engine,
        universe=universe,
        projection=projection,
    )
    windows[(armed.exchange_instrument_id, "15m")] = _trigger_window(
        armed_at_ms=TRIGGER_HOUR_MS,
        boundary=armed.breakout_boundary,
    )
    us_scope_id = (
        "scope:RSRVCB-LONG-15M:"
        f"{armed.exchange_instrument_id.split(':')[1]}:long"
    )
    observed_us = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        us_market,
        ObservationRequest(
            runtime_scope_id=us_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=TRIGGER_CLOSE_MS,
        ),
    )
    assert observed_us.status is ObservationStatus.SIGNAL_CREATED
    us_reference = await _signal_reference(
        six_event_engine,
        observed_us.signal_event_id,
    )
    us_ticket = await _issue_and_protect(
        six_event_engine,
        venue=venue,
        facts=USEquityEntryFactsSource(
            reference_price=us_reference * Decimal("1.04"),
            position_side="long",
        ),
        now_ms=ENTRY_TIME_MS,
    )

    third = await _observe_issue_and_protect_crypto(
        six_event_engine,
        venue=venue,
        market=crypto_market,
        runtime_scope_id="scope:SOR-SHORT:BTCUSDT:short",
        instrument_id=BTC,
        observed_at_ms=NOW_MS,
    )

    blocked_observation = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        crypto_market,
        ObservationRequest(
            runtime_scope_id="scope:CPM-LONG:ETHUSDT:long",
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )
    assert blocked_observation.status is ObservationStatus.SIGNAL_CREATED
    blocked_reference = await _signal_reference(
        six_event_engine,
        blocked_observation.signal_event_id,
    )
    blocked = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        venue,
        CertifiedEntryAdmissionFactsSource(
            reference_price=blocked_reference,
            position_side="long",
        ),
        _entry_request(NOW_MS + 3_000),
    )
    assert blocked.status is EntryWorkerStatus.ISSUE_REFUSED
    assert blocked.issue_status is not None
    assert blocked.issue_status.value == "budget_exhausted"

    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        exposure = await uow.entry_admission.get_account_exposure(
            "binance-usdm",
            "account-certification",
        )
        lane = await uow.entry_admission.get_global_lane()
    assert exposure is not None
    assert exposure.active_ticket_count == 3
    assert exposure.gross_risk_at_stop <= Decimal("90000")
    assert lane is not None and lane.status == "idle"
    async with six_event_engine.connect() as connection:
        active = (
            await connection.execute(
                sa.select(
                    trade_tickets.c.ticket_id,
                    trade_tickets.c.strategy_group_id,
                ).where(trade_tickets.c.active_netting_domain_key.is_not(None))
            )
        ).all()
        reserved_margin = Decimal(
            str(
                await connection.scalar(
                    sa.select(
                        sa.func.coalesce(
                            sa.func.sum(
                                budget_reservations.c.reserved_margin
                            ),
                            0,
                        )
                    ).where(budget_reservations.c.status == "active")
                )
            )
        )
    assert len(active) == 3
    assert {row.strategy_group_id for row in active} >= {
        "SOR-001",
        "RSRVCB-001",
    }
    assert {
        first.identity.ticket_id,
        us_ticket.identity.ticket_id,
        third.identity.ticket_id,
    } == {str(row.ticket_id) for row in active}
    assert reserved_margin <= Decimal("900000")


async def _observe_issue_and_protect_crypto(
    engine: AsyncEngine,
    *,
    venue: CertifiedVenue,
    market: CertifiedMarketSource,
    runtime_scope_id: str,
    instrument_id: str,
    observed_at_ms: int,
):
    observed = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(engine),
        market,
        ObservationRequest(
            runtime_scope_id=runtime_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=observed_at_ms,
        ),
    )
    assert observed.status is ObservationStatus.SIGNAL_CREATED
    reference = await _signal_reference(engine, observed.signal_event_id)
    position_side = "short" if ":short" in runtime_scope_id else "long"
    entry_reference = (
        reference * Decimal("0.96")
        if position_side == "short"
        else reference * Decimal("1.04")
    )
    ticket = await _issue_and_protect(
        engine,
        venue=venue,
        facts=CertifiedEntryAdmissionFactsSource(
            reference_price=entry_reference,
            position_side=position_side,
        ),
        now_ms=observed_at_ms + 1_000,
    )
    assert ticket.identity.netting_domain.exchange_instrument_id == instrument_id
    return ticket


async def _issue_and_protect(
    engine: AsyncEngine,
    *,
    venue: CertifiedVenue,
    facts,
    now_ms: int,
):
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        facts,
        _entry_request(now_ms),
    )
    assert entry.status is EntryWorkerStatus.DISPATCHED
    assert entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None

    async with PostgresKernelUnitOfWork(engine) as uow:
        reconciled = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    liquidation_price=ticket.projected_liquidation_price,
                    open_orders=(),
                    observed_at_ms=now_ms + 1_000,
                ),
            ),
        )
    assert reconciled.status is ReconcileTicketStatus.ENTRY_FILL_RECORDED
    for offset in (2_000, 3_000):
        dispatched = await dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            DispatchCommandRequest(
                worker_id=f"protect:{ticket.identity.ticket_id}:{offset}",
                ticket_id=ticket.identity.ticket_id,
                command_kinds=(
                    ExchangeCommandKind.INITIAL_STOP,
                    ExchangeCommandKind.TAKE_PROFIT,
                ),
                now_ms=now_ms + offset,
                lease_until_ms=now_ms + offset + 5_000,
                timeout_seconds=1,
                runtime_commit="kernel-test-head",
                schema_revision="0002_strategy_universe_us_equity",
                admission_snapshot_validity_ms=30_000,
            ),
        )
        assert dispatched.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POSITION_PROTECTED
    return ticket


async def _signal_reference(
    engine: AsyncEngine,
    signal_event_id: str | None,
) -> Decimal:
    assert signal_event_id is not None
    async with PostgresKernelUnitOfWork(engine) as uow:
        signal = await uow.signals.get(signal_event_id)
    assert signal is not None
    return Decimal(
        str(
            next(
                fact.value
                for fact in signal.facts
                if fact.role == "protection_reference"
            )
        )
    )


async def _first_armed(engine: AsyncEngine, *, universe, projection):
    for member in projection.top_two:
        async with PostgresKernelUnitOfWork(engine) as uow:
            armed = await uow.strategy_universes.get_active_armed_structure(
                event_spec_id=EVENT_SPEC_ID,
                universe_version_id=universe.universe_version_id,
                projection_run_id=projection.projection_run_id,
                exchange_instrument_id=member.exchange_instrument_id,
                now_ms=TRIGGER_HOUR_MS + 1,
            )
        if armed is not None:
            return armed
    raise AssertionError("projection produced no armed top-two member")


def _entry_request(now_ms: int) -> EntryWorkerRequest:
    return EntryWorkerRequest(
        worker_id=f"cross-asset-entry:{now_ms}",
        runtime_commit="kernel-test-head",
        schema_revision="0002_strategy_universe_us_equity",
        now_ms=now_ms,
        lease_until_ms=now_ms + 5_000,
        timeout_seconds=1,
        admission_snapshot_validity_ms=30_000,
    )
