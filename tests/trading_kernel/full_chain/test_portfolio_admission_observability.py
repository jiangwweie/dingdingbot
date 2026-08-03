from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.ingest_signal import (
    SignalAuthorityStatus,
    validate_signal_authority,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
)
from src.trading_kernel.domain.admission_decision import AdmissionDecisionStatus
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.cross_margin_stress import AccountRiskSnapshot
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import (
    admission_decisions,
    capacity_claims,
    exchange_commands,
    instrument_certification_current,
    owner_policy_current,
    runtime_scopes_current,
    shadow_outcomes_current,
    signal_events,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    EntryWorkerStatus,
    run_entry_worker_once,
)
from src.trading_kernel.interfaces.lifecycle_worker import (
    LifecycleWorkerRequest,
    LifecycleWorkerStatus,
    run_lifecycle_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.test_six_event_system_certification import (
    CertifiedEntryAdmissionFactsSource,
    CertifiedLifecycleFactsSource,
    CertifiedPositionSource,
    CertifiedPostFillFactsSource,
    CertifiedVenue,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)
from tests.trading_kernel.integration.universe_certification_support import (
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    BTC,
    ETH,
    NOW_MS,
    brf2_short_snapshot,
    cpm_long_snapshot,
    sor_snapshot,
)

BNB = "binance-usdm:BNBUSDT:perpetual"
DOGE = "binance-usdm:DOGEUSDT:perpetual"
REPLAY_WALLET_BALANCE = Decimal(1_000_000)
TWO_HOURS_MS = 2 * 3_600_000
SEVEN_HOURS_MS = 7 * 3_600_000
NINE_HOURS_FIFTEEN_MINUTES_MS = 9 * 3_600_000 + 15 * 60_000


@pytest_asyncio.fixture
async def replay_engine() -> AsyncGenerator[AsyncEngine, None]:
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


class RecordingReplayMarketSource:
    """Public-market recording fake; it is the only market input to replay."""

    def __init__(self) -> None:
        cpm = cpm_long_snapshot()
        brf2 = brf2_short_snapshot()
        sor = sor_snapshot(side="short")
        self._base_responses = {
            (BNB, "1h"): cpm.candles_1h,
            (BNB, "4h"): cpm.candles_4h,
            (DOGE, "1h"): cpm.candles_1h,
            (DOGE, "4h"): cpm.candles_4h,
            (ETH, "1h"): brf2.candles_1h,
            (ETH, "4h"): brf2.candles_4h,
        }
        self._sor_opening = sor.candles_15m[:4]
        self._sor_filler = sor.candles_15m[4]
        self._sor_trigger = sor.candles_15m[-1]
        self._offset_ms = 0
        self.calls: list[ClosedCandleRequest] = []

    def at(self, offset_ms: int) -> RecordingReplayMarketSource:
        self._offset_ms = offset_ms
        return self

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.calls.append(request)
        if request.exchange_instrument_id == BTC and request.timeframe == "15m":
            return self._sor_session_candles(request.closed_at_ms)
        return tuple(
            candle.model_copy(
                update={
                    "open_time_ms": candle.open_time_ms + self._offset_ms,
                    "close_time_ms": candle.close_time_ms + self._offset_ms,
                }
            )
            for candle in self._base_responses.get(
                (request.exchange_instrument_id, request.timeframe),
                (),
            )
        )

    def _sor_session_candles(self, closed_at_ms: int) -> tuple[ClosedCandle, ...]:
        interval_ms = 900_000
        session_start_ms = (closed_at_ms // 86_400_000) * 86_400_000
        candle_count = (closed_at_ms - session_start_ms) // interval_ms
        assert candle_count >= 5
        assert session_start_ms + candle_count * interval_ms == closed_at_ms
        templates = (
            *self._sor_opening,
            *(self._sor_filler for _ in range(candle_count - 5)),
            self._sor_trigger,
        )
        return tuple(
            candle.model_copy(
                update={
                    "open_time_ms": session_start_ms + index * interval_ms,
                    "close_time_ms": session_start_ms + (index + 1) * interval_ms,
                }
            )
            for index, candle in enumerate(templates)
        )


class ReplayEntryAdmissionFactsSource(CertifiedEntryAdmissionFactsSource):
    """Recording action facts with the Policy v4 fixed 5x exchange truth."""

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        snapshot = await super().read_entry_admission_snapshot(request)
        account_risk = _with_fixed_leverage(snapshot.account_risk_snapshot)
        return snapshot.model_copy(
            update={"account_risk_snapshot": account_risk}
        )

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        snapshot = await super().read_account_risk_snapshot(request)
        return _with_fixed_leverage(snapshot)


def _with_fixed_leverage(snapshot: AccountRiskSnapshot) -> AccountRiskSnapshot:
    payload = snapshot.model_dump(exclude={"snapshot_digest"})
    payload["configured_leverage"] = 5
    return AccountRiskSnapshot.create(**payload)


class ReplayLifecycleFactsSource(CertifiedLifecycleFactsSource):
    """Recording lifecycle facts for every actual Ticket selected by a worker."""

    async def read_lifecycle_facts(self, request) -> TicketLifecycleFacts:
        return TicketLifecycleFacts(
            position_quantity=request.expected_position_quantity,
            tp1_filled_quantity=Decimal(0),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=Decimal(0),
            exit_taker_fee_rate=Decimal("0.0005"),
            price_tick=request.price_tick,
            market_facts=None,
            observed_at_ms=request.observed_at_ms,
        )


class ReplayPositionSource:
    def __init__(self, tickets) -> None:
        self._tickets = {ticket.identity.ticket_id: ticket for ticket in tickets}

    async def read_position_snapshot(self, request) -> PositionSnapshot:
        ticket = self._tickets[request.ticket_id]
        return PositionSnapshot(
            netting_domain=ticket.identity.netting_domain,
            quantity=ticket.quantity,
            average_entry_price=ticket.entry_reference_price,
            venue_reported_liquidation_price=None,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
        )


class ReplayPostFillFactsSource(CertifiedPostFillFactsSource):
    def __init__(self, tickets) -> None:
        self._tickets_by_instrument = {
            ticket.identity.netting_domain.exchange_instrument_id: ticket
            for ticket in tickets
        }
        super().__init__(next(iter(self._tickets_by_instrument.values())))

    async def read_account_risk_snapshot(self, request):
        self.ticket = self._tickets_by_instrument[request.exchange_instrument_id]
        return await super().read_account_risk_snapshot(request)

    async def read_instrument_rules(self, request):
        self.ticket = self._tickets_by_instrument[request.exchange_instrument_id]
        return await super().read_instrument_rules(request)


@pytest.mark.asyncio
async def test_overnight_portfolio_replay_uses_observation_producer_for_decisions_and_shadow(
    replay_engine: AsyncEngine,
) -> None:
    """Would fail if a replay bypassed Observation or lost portfolio evidence."""

    source = RecordingReplayMarketSource()
    await _seed_replay_runtime(replay_engine, source)
    venue = CertifiedVenue()

    bnb = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, BNB),
        offset_ms=0,
    )
    assert bnb[1] is EntryWorkerStatus.DISPATCHED and bnb[5] is not None, bnb
    bnb_positions = await _release_entry_lane(
        replay_engine,
        venue,
        ticket_id=bnb[5],
        now_ms=NOW_MS + 2_000,
    )
    await _refresh_instrument_certification(
        replay_engine,
        bnb_positions,
        exchange_instrument_id=DOGE,
        now_ms=NOW_MS + TWO_HOURS_MS - 1,
    )
    venue_call_count_before_doge = len(venue.calls)
    doge = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, DOGE),
        offset_ms=TWO_HOURS_MS,
    )
    assert len(venue.calls) == venue_call_count_before_doge
    assert doge[:2] == (
        ObservationStatus.SIGNAL_CREATED,
        EntryWorkerStatus.ISSUE_REFUSED,
    ), doge
    await _refresh_instrument_certification(
        replay_engine,
        bnb_positions,
        exchange_instrument_id=ETH,
        now_ms=NOW_MS + SEVEN_HOURS_MS - 1,
    )
    brf2 = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, ETH),
        offset_ms=SEVEN_HOURS_MS,
    )
    assert brf2[1] is EntryWorkerStatus.DISPATCHED and brf2[5] is not None, brf2
    brf2_positions = await _release_entry_lane(
        replay_engine,
        venue,
        ticket_id=brf2[5],
        now_ms=NOW_MS + SEVEN_HOURS_MS + 2_000,
    )
    await _refresh_instrument_certification(
        replay_engine,
        brf2_positions,
        exchange_instrument_id=BTC,
        now_ms=NOW_MS + NINE_HOURS_FIFTEEN_MINUTES_MS - 1,
    )
    sor = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, BTC),
        offset_ms=NINE_HOURS_FIFTEEN_MINUTES_MS,
    )

    assert bnb[0] is ObservationStatus.SIGNAL_CREATED
    assert bnb[1] is EntryWorkerStatus.DISPATCHED, bnb
    assert doge[:2] == (
        ObservationStatus.SIGNAL_CREATED,
        EntryWorkerStatus.ISSUE_REFUSED,
    )
    assert brf2[:2] == (
        ObservationStatus.SIGNAL_CREATED,
        EntryWorkerStatus.DISPATCHED,
    )
    assert sor[:2] == (
        ObservationStatus.SIGNAL_CREATED,
        EntryWorkerStatus.DISPATCHED,
    )
    assert source.calls

    async with PostgresKernelUnitOfWork(replay_engine) as uow:
        decisions = await uow.admission_decisions.list_recent(limit=8)
        sor_signal = await uow.signals.get(sor[2])
    assert sor_signal is not None
    sor_session_start_ms = (
        expected_sor_time := NOW_MS + NINE_HOURS_FIFTEEN_MINUTES_MS
    ) // 86_400_000 * 86_400_000
    sor_fact_values = {
        fact.fact_definition_id: fact.value for fact in sor_signal.facts
    }
    assert next(
        value
        for fact_id, value in sor_fact_values.items()
        if "session_start_ms_v3" in fact_id
    ) == str(sor_session_start_ms)
    assert next(
        value
        for fact_id, value in sor_fact_values.items()
        if "session_end_ms_v3" in fact_id
    ) == str(sor_session_start_ms + 86_400_000)
    assert sor_signal.occurred_at_ms == expected_sor_time
    async with replay_engine.connect() as connection:
        policy = (
            await connection.execute(sa.select(owner_policy_current))
        ).mappings().one()
        signal_rows = tuple(
            (
                await connection.execute(
                    sa.select(signal_events).order_by(signal_events.c.occurred_at_ms)
                )
            )
            .mappings()
            .all()
        )
        decision_rows = tuple(
            (
                await connection.execute(
                    sa.select(admission_decisions).order_by(
                        admission_decisions.c.decided_at_ms
                    )
                )
            )
            .mappings()
            .all()
        )
        ticket_rows = tuple(
            (
                await connection.execute(
                    sa.select(trade_tickets).order_by(trade_tickets.c.created_at_ms)
                )
            )
            .mappings()
            .all()
        )
        claim_rows = tuple(
            (
                await connection.execute(
                    sa.select(capacity_claims).order_by(capacity_claims.c.created_at_ms)
                )
            )
            .mappings()
            .all()
        )
        command_rows = tuple(
            (await connection.execute(sa.select(exchange_commands))).mappings().all()
        )
        doge_command_count = await connection.scalar(
            sa.select(sa.func.count(exchange_commands.c.command_id))
            .select_from(
                admission_decisions.outerjoin(
                    trade_tickets,
                    admission_decisions.c.ticket_id == trade_tickets.c.ticket_id,
                ).outerjoin(
                    exchange_commands,
                    trade_tickets.c.ticket_id == exchange_commands.c.ticket_id,
                )
            )
            .where(admission_decisions.c.signal_event_id == doge[2])
        )
        shadow = (
            await connection.execute(
                sa.select(shadow_outcomes_current).where(
                    shadow_outcomes_current.c.admission_decision_id
                    == next(
                        decision.admission_decision_id
                        for decision in decisions
                        if decision.signal_event_id == doge[2]
                    )
                )
            )
        ).mappings().one_or_none()
        active_ticket_ids = tuple(
            await connection.scalars(
                sa.select(trade_tickets.c.ticket_id)
                .where(trade_tickets.c.terminal_at_ms.is_(None))
                .order_by(trade_tickets.c.ticket_id)
                .limit(4)
            )
        )
    async with PostgresKernelUnitOfWork(replay_engine) as uow:
        active_tickets = []
        for ticket_id in active_ticket_ids:
            ticket = await uow.tickets.get(str(ticket_id))
            if ticket is not None:
                active_tickets.append(ticket)
        tickets = tuple(active_tickets)

    by_instrument = {item.exchange_instrument_id: item for item in decisions}
    expected_signal_times = (
        NOW_MS,
        NOW_MS + TWO_HOURS_MS,
        NOW_MS + SEVEN_HOURS_MS,
        NOW_MS + NINE_HOURS_FIFTEEN_MINUTES_MS,
    )
    expected_decision_times = tuple(value + 1_000 for value in expected_signal_times)
    assert tuple(row["exchange_instrument_id"] for row in signal_rows) == (
        BNB,
        DOGE,
        ETH,
        BTC,
    )
    assert tuple(int(row["occurred_at_ms"]) for row in signal_rows) == (
        expected_signal_times
    )
    assert tuple(row["exchange_instrument_id"] for row in decision_rows) == (
        BNB,
        DOGE,
        ETH,
        BTC,
    )
    assert tuple(int(row["decided_at_ms"]) for row in decision_rows) == (
        expected_decision_times
    )
    assert tuple(row["exchange_instrument_id"] for row in ticket_rows) == (
        BNB,
        ETH,
        BTC,
    )
    assert tuple(int(row["created_at_ms"]) for row in ticket_rows) == (
        expected_decision_times[0],
        expected_decision_times[2],
        expected_decision_times[3],
    )

    assert policy["policy_version"] == 4
    assert policy["max_concurrent_tickets"] == 3
    assert policy["max_ticket_stop_risk_fraction"] == Decimal("0.02")
    assert policy["max_gross_stop_risk_fraction"] == Decimal("0.06")
    assert policy["max_ticket_initial_margin_fraction"] == Decimal("0.30")
    assert policy["max_gross_initial_margin_utilization"] == Decimal("0.90")
    assert policy["min_materialization_ratio"] == Decimal("0.50")
    assert policy["directional_stop_risk_limit_fraction"] == Decimal("0.04")
    assert policy["family_ticket_limits"] == {
        "long_continuation": 1,
        "opening_range": 2,
        "rally_failure_short": 1,
    }
    assert policy["max_leverage"] == 10
    assert policy["supported_margin_mode"] == "cross"

    assert len(tickets) == 3
    assert len(claim_rows) == 3
    ticket_risk_limit = REPLAY_WALLET_BALANCE * Decimal("0.02")
    gross_risk_limit = REPLAY_WALLET_BALANCE * Decimal("0.06")
    ticket_margin_limit = REPLAY_WALLET_BALANCE * Decimal("0.30")
    gross_margin_limit = REPLAY_WALLET_BALANCE * Decimal("0.90")
    minimum_materialized_risk = ticket_risk_limit * Decimal("0.50")
    directional_risk_limit = REPLAY_WALLET_BALANCE * Decimal("0.04")
    assert sum(ticket.risk_at_stop for ticket in tickets) <= gross_risk_limit
    assert sum(ticket.reserved_margin for ticket in tickets) <= gross_margin_limit
    assert (
        sum(
            ticket.risk_at_stop
            for ticket in tickets
            if ticket.identity.netting_domain.position_side == "long"
        )
        <= directional_risk_limit
    )
    assert (
        sum(
            ticket.risk_at_stop
            for ticket in tickets
            if ticket.identity.netting_domain.position_side == "short"
        )
        <= directional_risk_limit
    )
    assert sum(
        ticket.exposure_family == "long_continuation" for ticket in tickets
    ) <= 1
    assert sum(
        ticket.exposure_family == "rally_failure_short" for ticket in tickets
    ) <= 1
    assert sum(ticket.exposure_family == "opening_range" for ticket in tickets) <= 2
    assert by_instrument[BNB].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[ETH].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[BTC].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[DOGE].decision_status is AdmissionDecisionStatus.REJECTED
    assert by_instrument[DOGE].first_blocker == "exposure_family_capacity_exhausted"
    assert by_instrument[DOGE].capacity_claim_id is None
    assert by_instrument[DOGE].ticket_id is None
    assert doge_command_count == 0
    admitted_ticket_ids = {
        str(decision.ticket_id)
        for decision in decisions
        if decision.decision_status is AdmissionDecisionStatus.ADMITTED
    }
    assert {str(row["ticket_id"]) for row in command_rows} == admitted_ticket_ids

    claims_by_ticket_id = {str(row["ticket_id"]): row for row in claim_rows}
    decisions_by_ticket_id = {
        str(row["ticket_id"]): row
        for row in decision_rows
        if row["ticket_id"] is not None
    }
    for ticket_row in ticket_rows:
        ticket_id = str(ticket_row["ticket_id"])
        claim = claims_by_ticket_id[ticket_id]
        decision = decisions_by_ticket_id[ticket_id]
        assert str(claim["capacity_claim_id"]) == str(ticket_row["capacity_claim_id"])
        assert str(claim["signal_event_id"]) == str(ticket_row["signal_event_id"])
        assert str(decision["capacity_claim_id"]) == str(claim["capacity_claim_id"])
        assert str(decision["signal_event_id"]) == str(ticket_row["signal_event_id"])
        assert claim["owner_policy_version"] == 4
        assert ticket_row["owner_policy_version"] == 4
        assert claim["total_wallet_balance_at_claim"] == REPLAY_WALLET_BALANCE
        assert claim["max_ticket_stop_risk_fraction"] == Decimal("0.02")
        assert claim["max_gross_stop_risk_fraction"] == Decimal("0.06")
        assert claim["max_ticket_initial_margin_fraction"] == Decimal("0.30")
        assert claim["max_gross_initial_margin_utilization"] == Decimal("0.90")
        assert claim["min_materialization_ratio"] == Decimal("0.50")
        assert claim["directional_stop_risk_limit_fraction"] == Decimal("0.04")
        assert claim["minimum_stop_risk_budget"] == minimum_materialized_risk
        assert claim["planned_stop_risk_budget"] == ticket_risk_limit
        assert claim["ticket_margin_budget"] == ticket_margin_limit
        assert minimum_materialized_risk <= claim["risk_at_stop"] <= ticket_risk_limit
        assert claim["reserved_margin"] <= ticket_margin_limit
        assert claim["selected_leverage"] == 5
        assert claim["configured_leverage_at_claim"] == 5
        assert claim["exchange_max_leverage"] == 10
        assert ticket_row["selected_leverage"] == 5
        assert claim["margin_mode_at_claim"] == "cross"
        assert ticket_row["margin_mode"] == "cross"
        assert claim["exposure_family"] == ticket_row["exposure_family"]
        assert claim["family_ticket_limit"] == {
            "long_continuation": 1,
            "opening_range": 2,
            "rally_failure_short": 1,
        }[str(ticket_row["exposure_family"])]
    assert shadow is not None
    assert shadow["admission_decision_id"] == by_instrument[DOGE].admission_decision_id
    assert shadow["status"] == "pending"
    assert all(ticket.identity.netting_domain.exchange_instrument_id != DOGE for ticket in tickets)

    async with replay_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(admission_decisions)
        ) == 4
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_tickets)
        ) == 3
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(shadow_outcomes_current)
        ) == 1


async def _seed_replay_runtime(
    engine: AsyncEngine,
    source: RecordingReplayMarketSource,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="account-portfolio-replay",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=NOW_MS - 10_000_000,
            ),
        )

    for event_id, members in (
        ("CPM-LONG", (BNB, DOGE)),
        ("BRF2-SHORT", (ETH,)),
        ("SOR-SHORT", (BTC,)),
    ):
        await _install_and_activate(
            engine,
            source,
            event_id=event_id,
            members=members,
        )

    async with PostgresKernelUnitOfWork(engine) as uow:
        await arm_acceptance_policy(
            uow,
            ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS - 1),
        )
    async with engine.begin() as connection:
        promoted = await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.policy_version == 2)
            .values(policy_version=4)
        )
    assert promoted.rowcount == 1


async def _install_and_activate(
    engine: AsyncEngine,
    source: RecordingReplayMarketSource,
    *,
    event_id: str,
    members: tuple[str, ...],
) -> None:
    contract = next(
        item for item in registered_strategy_contracts() if item.event_id == event_id
    )
    warm_interval_ms = 900_000 if contract.timeframe == "15m" else 3_600_000
    warm_at_ms = NOW_MS - warm_interval_ms
    async with PostgresKernelUnitOfWork(engine) as uow:
        configured = await configure_strategy_universe(
            uow,
            UniverseConfigurationRequest(
                runtime_profile_id=RUNTIME_PROFILE_ID,
                event_id=event_id,
                exchange_instrument_ids=members,
                installed_at_ms=warm_at_ms - 1_000,
            ),
        )
    assert configured.universe is not None

    for _ in members:
        certified = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            CertifiedVenue(),
            CertifiedPositionSource(),
            ReconciliationWorkerRequest(
                worker_id="replay-certification",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=warm_at_ms,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=1_000,
                certification_lease_ms=60_000,
                certification_valid_for_ms=600_000,
                certification_eligible_check_interval_ms=300_000,
                certification_owner_action_check_interval_ms=300_000,
                certification_transient_retry_interval_ms=30_000,
            ),
            instrument_certification_source=RecordingReadonlyCertificationSource(engine),
        )
        assert certified.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED

    async with engine.connect() as connection:
        scope_ids = tuple(
            await connection.scalars(
                sa.select(runtime_scopes_current.c.runtime_scope_id).where(
                    runtime_scopes_current.c.universe_version_id
                    == configured.universe.universe_version_id
                )
            )
        )
    for scope_id in scope_ids:
        warmed = await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(engine),
            source.at(-warm_interval_ms),
            ObservationRequest(
                runtime_scope_id=scope_id,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=warm_at_ms,
                attempted_at_ms=warm_at_ms,
            ),
        )
        assert warmed.status is ObservationStatus.WARMED

    for _ in members:
        refreshed = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            CertifiedVenue(),
            CertifiedPositionSource(),
            ReconciliationWorkerRequest(
                worker_id="replay-certification-refresh",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=NOW_MS - 1,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=1_000,
            ),
            instrument_certification_source=RecordingReadonlyCertificationSource(engine),
        )
        assert refreshed.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED

    async with PostgresKernelUnitOfWork(engine) as uow:
        activation = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=configured.universe.universe_version_id,
                attempted_at_ms=NOW_MS - 1,
            ),
        )
    assert activation.status in {
        UniverseActivationStatus.ACTIVATED,
        UniverseActivationStatus.ALREADY_ACTIVE,
    }


async def _observe_and_admit(
    engine: AsyncEngine,
    source: RecordingReplayMarketSource,
    venue: CertifiedVenue,
    *,
    runtime_scope_id: str,
    offset_ms: int,
) -> tuple[
    ObservationStatus,
    EntryWorkerStatus,
    str,
    str | None,
    str | None,
    str | None,
]:
    observed_at_ms = NOW_MS + offset_ms
    observation = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(engine),
        source.at(offset_ms),
        ObservationRequest(
            runtime_scope_id=runtime_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=observed_at_ms,
            attempted_at_ms=observed_at_ms,
        ),
    )
    assert observation.signal_event_id is not None
    async with PostgresKernelUnitOfWork(engine) as uow:
        signal = await uow.signals.get(observation.signal_event_id)
        authority = await validate_signal_authority(
            uow,
            signal,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=observed_at_ms + 1_000,
        )
    assert signal is not None
    assert authority is SignalAuthorityStatus.VALID, signal
    reference_price = Decimal(
        str(
            next(
                fact.value
                for fact in signal.facts
                if fact.role == "protection_reference"
            )
        )
    )
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        ReplayEntryAdmissionFactsSource(
            reference_price=(
                reference_price * Decimal("1.03")
                if signal.position_side == "long"
                else reference_price * Decimal("0.97")
            ),
            position_side=signal.position_side,
        ),
        EntryWorkerRequest(
            worker_id="portfolio-replay-entry",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=observed_at_ms + 1_000,
            lease_until_ms=observed_at_ms + 31_000,
            timeout_seconds=1,
            admission_snapshot_validity_ms=30_000,
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        persisted_decision = await uow.admission_decisions.get_for_signal(
            observation.signal_event_id
        )
    return (
        observation.status,
        entry.status,
        observation.signal_event_id,
        None if entry.issue_status is None else entry.issue_status.value,
        None if persisted_decision is None else persisted_decision.binding_constraint,
        entry.ticket_id,
    )


async def _active_scope_id(engine: AsyncEngine, instrument_id: str) -> str:
    async with engine.connect() as connection:
        scope_id = await connection.scalar(
            sa.select(runtime_scopes_current.c.runtime_scope_id).where(
                runtime_scopes_current.c.exchange_instrument_id == instrument_id,
                runtime_scopes_current.c.lifecycle_state == "active",
            )
        )
    assert scope_id is not None
    return str(scope_id)


async def _release_entry_lane(
    engine: AsyncEngine,
    venue: CertifiedVenue,
    *,
    ticket_id: str | None,
    now_ms: int,
) -> ReplayPositionSource:
    assert ticket_id is not None
    async with engine.connect() as connection:
        active_ticket_ids = tuple(
            await connection.scalars(
                sa.select(trade_tickets.c.ticket_id)
                .where(trade_tickets.c.terminal_at_ms.is_(None))
                .order_by(trade_tickets.c.ticket_id)
                .limit(4)
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        ticket = await uow.tickets.get(ticket_id)
        active_tickets = []
        for candidate_id in active_ticket_ids:
            persisted = await uow.tickets.get(str(candidate_id))
            if persisted is not None:
                active_tickets.append(persisted)
        tickets = tuple(active_tickets)
    assert ticket is not None
    positions = ReplayPositionSource(tickets)
    reconciled = None
    for attempt in range(4):
        candidate = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            positions,
            ReconciliationWorkerRequest(
                worker_id=f"portfolio-replay-reconciliation-{attempt}",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now_ms + attempt * 1_000,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=1_000,
            ),
        )
        if (
            candidate.status is ReconciliationWorkerStatus.POSITION_RECONCILED
            and candidate.ticket_id == ticket_id
        ):
            reconciled = candidate
            break
    assert reconciled is not None
    lifecycle_source = ReplayLifecycleFactsSource()
    lifecycle_request = LifecycleWorkerRequest(
        worker_id="portfolio-replay-lifecycle",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=now_ms + 1_000,
        lease_until_ms=now_ms + 6_000,
        timeout_seconds=1,
        idle_poll_interval_ms=1_000,
    )
    initial_stop = None
    for attempt in range(4):
        candidate = await run_lifecycle_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            lifecycle_source,
            lifecycle_request.model_copy(
                update={
                    "now_ms": now_ms + 1_000 + attempt * 1_000,
                    "lease_until_ms": now_ms + 6_000 + attempt * 1_000,
                }
            ),
        )
        if candidate.status is LifecycleWorkerStatus.DISPATCHED:
            initial_stop = candidate
            break
        assert candidate.status is LifecycleWorkerStatus.NO_CHANGE
    assert initial_stop is not None
    post_fill_source = ReplayPostFillFactsSource(tickets)
    post_fill = None
    for attempt in range(4):
        candidate = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            positions,
            ReconciliationWorkerRequest(
                worker_id=f"portfolio-replay-post-fill-{attempt}",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now_ms + 5_500 + attempt * 1_000,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=1_000,
            ),
            account_risk_source=post_fill_source,
            instrument_rules_source=post_fill_source,
        )
        if (
            candidate.status is ReconciliationWorkerStatus.POSITION_RECONCILED
            and candidate.ticket_id == ticket_id
            and candidate.detail == "post_fill_stress:passed"
        ):
            post_fill = candidate
            break
    assert post_fill is not None
    take_profit = await run_lifecycle_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": now_ms + 6_000, "lease_until_ms": now_ms + 11_000}
        ),
    )
    assert take_profit.status is LifecycleWorkerStatus.DISPATCHED
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket_id)
        lane = await uow.entry_admission.get_global_lane()
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert lane is not None
    assert lane.status == "idle"
    return positions


async def _refresh_instrument_certification(
    engine: AsyncEngine,
    positions: ReplayPositionSource,
    *,
    exchange_instrument_id: str,
    now_ms: int,
) -> None:
    for attempt in range(8):
        await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            CertifiedVenue(),
            positions,
            ReconciliationWorkerRequest(
                worker_id=f"portfolio-replay-cert-refresh-{attempt}",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now_ms,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=1_000,
            ),
            instrument_certification_source=RecordingReadonlyCertificationSource(
                engine
            ),
        )
        async with engine.connect() as connection:
            valid_until_ms = await connection.scalar(
                sa.select(instrument_certification_current.c.valid_until_ms).where(
                    instrument_certification_current.c.runtime_profile_id
                    == RUNTIME_PROFILE_ID,
                    instrument_certification_current.c.exchange_instrument_id
                    == exchange_instrument_id,
                    instrument_certification_current.c.status == "eligible",
                    instrument_certification_current.c.blocker_code.is_(None),
                )
            )
        if valid_until_ms is not None and int(valid_until_ms) > now_ms:
            return
    raise AssertionError(
        f"certification did not refresh {exchange_instrument_id} by {now_ms}"
    )
