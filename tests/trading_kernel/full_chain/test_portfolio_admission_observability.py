from __future__ import annotations

import asyncio
import importlib
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
from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
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
from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    set_strategy_entry_state,
)
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.admission_decision import AdmissionDecisionStatus
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.cross_margin_stress import AccountRiskSnapshot
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    admission_decisions,
    capacity_claims,
    entry_lane_current,
    exchange_commands,
    instrument_certification_current,
    owner_policy_current,
    owner_policy_events,
    readiness_current,
    runtime_profiles,
    runtime_scopes_current,
    schema_metadata,
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
    deploy_compatible_upgrade_identity,
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
from tests.trading_kernel.integration.universe_certification_support import (
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.support.certified_boundaries import (
    CertifiedEntryAdmissionFactsSource,
    CertifiedLifecycleFactsSource,
    CertifiedPositionSource,
    CertifiedPostFillFactsSource,
    CertifiedVenue,
)
from tests.trading_kernel.support.migrations import (
    V4_REVISION,
    _install_source_runtime_identity,
    _prepare_production_shaped_0002,
)
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
from tests.trading_kernel.unit.detectors.fixtures import (
    BTC,
    ETH,
    NOW_MS,
    SOL,
    brf2_short_snapshot,
    cpm_long_snapshot,
    sor_snapshot,
)

BNB = "binance-usdm:BNBUSDT:perpetual"
DOGE = "binance-usdm:DOGEUSDT:perpetual"
REPLAY_WALLET_BALANCE = Decimal(1_000_000)
TWO_HOURS_MS = 2 * 3_600_000
SEVEN_HOURS_MS = 7 * 3_600_000
NINE_HOURS_MS = 9 * 3_600_000
CERTIFIED_0002_REGISTRY_MANIFEST_HASH = str(
    importlib.import_module(
        "migrations.trading_kernel.versions.0003_portfolio_admission_observability"
    ).CERTIFIED_0002_REGISTRY_MANIFEST_HASH
)


@pytest_asyncio.fixture
async def replay_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", V4_REVISION)
    engine = create_async_engine(database_url)
    try:
        await _prepare_production_shaped_0002(engine)
        await _install_source_runtime_identity(engine)
        async with engine.begin() as connection:
            await connection.execute(
                sa.insert(account_exposure_current).values(
                    venue_id="binance-usdm",
                    account_id="subaccount-source-test",
                    gross_notional=Decimal(0),
                    gross_risk_at_stop=Decimal(0),
                    current_reserved_margin=Decimal(0),
                    active_ticket_count=0,
                    projection_version=0,
                    updated_at_ms=1_000,
                )
            )
            await connection.execute(
                sa.insert(entry_lane_current).values(
                    lane_id="global-entry",
                    ticket_id=None,
                    signal_event_id=None,
                    status="idle",
                    claimed_at_ms=None,
                    lease_until_ms=None,
                    claim_owner=None,
                    version=0,
                )
            )
            await connection.execute(
                sa.insert(schema_metadata).values(
                    metadata_key="registry_semantic_hash",
                    metadata_value=CERTIFIED_0002_REGISTRY_MANIFEST_HASH,
                    updated_at_ms=1_000,
                )
            )
        _run_alembic(database_url, "upgrade", CURRENT_SCHEMA_REVISION)
        async with PostgresKernelUnitOfWork(engine) as uow:
            deployed = await deploy_compatible_upgrade_identity(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-source-test",
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000_000,
                ),
            )
        assert deployed.refreshed_existing_authority is True
        async with engine.connect() as connection:
            profile = (
                (
                    await connection.execute(
                        sa.select(runtime_profiles).where(
                            runtime_profiles.c.runtime_profile_id == RUNTIME_PROFILE_ID
                        )
                    )
                )
                .mappings()
                .one()
            )
            metadata = dict(
                (
                    await connection.execute(
                        sa.select(
                            schema_metadata.c.metadata_key,
                            schema_metadata.c.metadata_value,
                        )
                    )
                ).all()
            )
        assert profile["runtime_profile_id"] == "tiny-live-v1"
        assert profile["venue_id"] == "binance-usdm"
        assert profile["account_id"] == "subaccount-source-test"
        assert profile["position_mode"] == "independent_sides"
        assert set(metadata) == {
            "registry_semantic_hash",
            "runtime_commit",
            "schema_revision",
            "seed_identity",
        }
        assert metadata["runtime_commit"] == "kernel-test-head"
        assert metadata["schema_revision"] == CURRENT_SCHEMA_REVISION
        assert metadata["seed_identity"] == deployed.runtime_seed_semantic_hash
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
        if request.exchange_instrument_id == BTC and request.timeframe == "1h":
            day = request.closed_at_ms // 86_400_000 * 86_400_000
            times = range(day, request.closed_at_ms, 3_600_000)
            return tuple(candle.model_copy(update={"open_time_ms":t,"close_time_ms":t+3_600_000})
                for t,candle in ((t,self._sor_trigger if t+3_600_000==request.closed_at_ms else self._sor_filler if t>day else self._sor_opening[0]) for t in times))
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
        return snapshot.model_copy(update={"account_risk_snapshot": account_risk})

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
    replay_baseline_command_ids = await _exchange_command_ids(replay_engine)

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
    command_ids_before_doge = await _exchange_command_ids(replay_engine)
    doge = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, DOGE),
        offset_ms=TWO_HOURS_MS,
    )
    assert len(venue.calls) == venue_call_count_before_doge
    assert await _exchange_command_ids(replay_engine) == command_ids_before_doge
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
        now_ms=NOW_MS + NINE_HOURS_MS - 1,
    )
    sor = await _observe_and_admit(
        replay_engine,
        source,
        venue,
        runtime_scope_id=await _active_scope_id(replay_engine, BTC),
        offset_ms=NINE_HOURS_MS,
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
    decision_signal_ids = tuple(decision.signal_event_id for decision in decisions)
    admitted_decision_ticket_ids = tuple(
        str(decision.ticket_id)
        for decision in decisions
        if decision.ticket_id is not None
    )
    admitted_decision_claim_ids = tuple(
        str(decision.capacity_claim_id)
        for decision in decisions
        if decision.capacity_claim_id is not None
    )
    assert sor_signal is not None
    sor_session_start_ms = (
        (expected_sor_time := NOW_MS + NINE_HOURS_MS)
        // 86_400_000
        * 86_400_000
    )
    sor_fact_values = {fact.fact_definition_id: fact.value for fact in sor_signal.facts}
    assert next(
        value
        for fact_id, value in sor_fact_values.items()
        if "session_start_ms_1h_v1" in fact_id
    ) == str(sor_session_start_ms)
    assert next(
        value
        for fact_id, value in sor_fact_values.items()
        if "session_end_ms_1h_v1" in fact_id
    ) == str(sor_session_start_ms + 86_400_000)
    assert sor_signal.occurred_at_ms == expected_sor_time
    async with replay_engine.connect() as connection:
        policy = (
            (await connection.execute(sa.select(owner_policy_current))).mappings().one()
        )
        policy_events = tuple(
            (
                await connection.execute(
                    sa.select(owner_policy_events).order_by(
                        owner_policy_events.c.policy_version
                    )
                )
            )
            .mappings()
            .all()
        )
        signal_rows = tuple(
            (
                await connection.execute(
                    sa.select(signal_events)
                    .where(signal_events.c.signal_event_id.in_(decision_signal_ids))
                    .order_by(signal_events.c.occurred_at_ms)
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
                    sa.select(trade_tickets)
                    .where(trade_tickets.c.ticket_id.in_(admitted_decision_ticket_ids))
                    .order_by(trade_tickets.c.created_at_ms)
                )
            )
            .mappings()
            .all()
        )
        claim_rows = tuple(
            (
                await connection.execute(
                    sa.select(capacity_claims)
                    .where(
                        capacity_claims.c.capacity_claim_id.in_(
                            admitted_decision_claim_ids
                        )
                    )
                    .order_by(capacity_claims.c.created_at_ms)
                )
            )
            .mappings()
            .all()
        )
        command_rows = tuple(
            (await connection.execute(sa.select(exchange_commands))).mappings().all()
        )
        shadow = (
            (
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
            )
            .mappings()
            .one_or_none()
        )
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
        NOW_MS + NINE_HOURS_MS,
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

    assert tuple(int(row["policy_version"]) for row in policy_events) == (4, 5, 6)
    migration_policy_event, r4_identity_event, armed_policy_event = policy_events
    assert migration_policy_event["owner_policy_event_id"] == (
        "policy-event:policy-main:v4"
    )
    assert migration_policy_event["operation"] == (
        "compatible_upgrade_portfolio_admission_v4"
    )
    assert r4_identity_event["owner_policy_event_id"] == "policy-event:policy-main:v5"
    assert r4_identity_event["operation"] == "tradfi_live_policy_scope_expanded"
    assert armed_policy_event["owner_policy_event_id"] == "policy-event:policy-main:v6"
    assert armed_policy_event["operation"] == "arm_acceptance_ticket"
    for event, version, submit_enabled in (
        (migration_policy_event, 4, False),
        (r4_identity_event, 5, False),
        (armed_policy_event, 6, True),
    ):
        payload = event["payload"]
        assert payload["policy_version"] == version
        assert payload["enabled"] is True
        assert payload["new_entry_submit_enabled"] is submit_enabled
        assert payload["priority_rank"] == 1
        assert payload["max_concurrent_tickets"] == 3
        assert payload["family_ticket_limits"] == {
            "long_continuation": 1,
            "opening_range": 2,
            "rally_failure_short": 1,
        }
        assert Decimal(str(payload["max_ticket_stop_risk_fraction"])) == Decimal("0.02")
        assert Decimal(str(payload["max_gross_stop_risk_fraction"])) == Decimal("0.06")
        assert Decimal(str(payload["max_ticket_initial_margin_fraction"])) == (
            Decimal("0.30")
        )
        assert Decimal(str(payload["max_gross_initial_margin_utilization"])) == Decimal(
            "0.90"
        )
        assert Decimal(str(payload["directional_stop_risk_limit_fraction"])) == Decimal(
            "0.04"
        )
        assert Decimal(str(payload["min_materialization_ratio"])) == Decimal("0.50")
        assert payload["max_leverage"] == 10
        assert payload["supported_margin_mode"] == "cross"
    assert (
        int(migration_policy_event["created_at_ms"])
        < int(r4_identity_event["created_at_ms"])
        < int(armed_policy_event["created_at_ms"])
    )

    assert policy["policy_version"] == 6
    assert policy["enabled"] is True
    assert policy["new_entry_submit_enabled"] is True
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
    assert sum(ticket.exposure_family == "long_continuation" for ticket in tickets) <= 1
    assert (
        sum(ticket.exposure_family == "rally_failure_short" for ticket in tickets) <= 1
    )
    assert sum(ticket.exposure_family == "opening_range" for ticket in tickets) <= 2
    assert by_instrument[BNB].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[ETH].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[BTC].decision_status is AdmissionDecisionStatus.ADMITTED
    assert by_instrument[DOGE].decision_status is AdmissionDecisionStatus.REJECTED
    assert by_instrument[DOGE].first_blocker == "exposure_family_capacity_exhausted"
    assert by_instrument[DOGE].capacity_claim_id is None
    assert by_instrument[DOGE].ticket_id is None
    admitted_ticket_ids = {
        str(decision.ticket_id)
        for decision in decisions
        if decision.decision_status is AdmissionDecisionStatus.ADMITTED
    }
    replay_command_rows = tuple(
        row
        for row in command_rows
        if str(row["command_id"]) not in replay_baseline_command_ids
    )
    assert {str(row["ticket_id"]) for row in replay_command_rows} == (
        admitted_ticket_ids
    )

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
        assert decision["owner_policy_version"] == 6
        assert claim["owner_policy_version"] == 6
        assert ticket_row["owner_policy_version"] == 6
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
        assert (
            claim["family_ticket_limit"]
            == {
                "long_continuation": 1,
                "opening_range": 2,
                "rally_failure_short": 1,
            }[str(ticket_row["exposure_family"])]
        )
    assert shadow is not None
    assert shadow["admission_decision_id"] == by_instrument[DOGE].admission_decision_id
    assert shadow["status"] == "pending"
    assert all(
        ticket.identity.netting_domain.exchange_instrument_id != DOGE
        for ticket in tickets
    )

    async with replay_engine.connect() as connection:
        assert (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(admission_decisions)
            )
            == 4
        )
        assert (
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(trade_tickets)
                .where(trade_tickets.c.ticket_id.in_(admitted_decision_ticket_ids))
            )
            == 3
        )
        assert (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(shadow_outcomes_current)
            )
            == 1
        )


@pytest_asyncio.fixture
async def capacity_engine():
    from tests.trading_kernel.support.postgres import (
        create_empty_database,
        drop_disposable_database,
    )
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        _run_alembic(url, "upgrade", "0009_capacity_policy_v0")
        yield engine
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


async def _install_capacity_then_upgrade(engine, request):
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_compatible_upgrade_identity(uow,request.model_copy(update={"seeded_at_ms":NOW_MS-8_000_000}))
    await engine.dispose()
    _run_alembic(engine.url.render_as_string(hide_password=False), "upgrade", CURRENT_SCHEMA_REVISION)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_compatible_upgrade_identity(uow,request.model_copy(update={
            "schema_revision":CURRENT_SCHEMA_REVISION,"seeded_at_ms":NOW_MS-8_000_000+1}))


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent_last_slot,research_case", [
    (False, "enabled"), (True, "enabled"), (False, "budget_one"),
    (False, "disabled"), (False, "builder_failure"),
    (False, "quota_failure"), (False, "insert_failure"),
    (False, "control_failure"),
])
async def test_capacity_v0_two_natural_same_strategy_tickets_and_third_refusal(
    capacity_engine, concurrent_last_slot, research_case, monkeypatch, caplog,
) -> None:
    issue_engine = capacity_engine
    source_request = RuntimeAuthoritySeedRequest(account_id="subaccount-source-test", runtime_commit="kernel-test-head",
        schema_revision="0009_capacity_policy_v0", seeded_at_ms=NOW_MS-10_000_000)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await seed_runtime_authority(uow, source_request)
        await set_strategy_entry_state(uow, strategy_group_id="SOR-001", target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=1,reason="owner_retired_sor", idempotency_key="capacity-natural:sor-pause",
                owner_identity="owner",now_ms=NOW_MS-9_000_000), authentication_strength="totp_step_up")
    await _install_capacity_then_upgrade(issue_engine,source_request)
    # Faults affect only optional research in this disposable PostgreSQL.
    async with issue_engine.begin() as connection:
        await connection.execute(sa.text("UPDATE brc_research_collection_control "
            "SET enabled=:enabled,daily_limit=:limit,control_version=2"),
            {"enabled": research_case != "disabled", "limit": 1 if research_case == "budget_one" else 2})
        if research_case in {"quota_failure", "insert_failure"}:
            table = ("brc_research_collection_daily" if research_case == "quota_failure"
                     else "brc_shadow_outcomes_current")
            action = "UPDATE" if research_case == "quota_failure" else "INSERT"
            await connection.execute(sa.text("CREATE FUNCTION inject_research_failure() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected research failure' "
                "USING ERRCODE='23514'; END; $$"))
            await connection.execute(sa.text(f"CREATE TRIGGER inject_research_failure BEFORE {action} "
                f"ON {table} FOR EACH ROW EXECUTE FUNCTION inject_research_failure()"))
    if research_case == "builder_failure":
        module = importlib.import_module("src.trading_kernel.application.observe_strategy_scope")
        def fail_builder(**kwargs):
            raise ValueError("injected frozen research path failure")
        monkeypatch.setattr(module, "pending_generic_signal_path_spec", fail_builder)
    if research_case == "control_failure":
        from src.trading_kernel.infrastructure.pg_repositories import (
            PostgresShadowOutcomeRepository,
        )
        async def fail_control(self):
            await self._connection.execute(sa.text("SELECT 1/0"))
        monkeypatch.setattr(PostgresShadowOutcomeRepository, "signal_path_enabled", fail_control)
    market = RecordingReplayMarketSource()
    template = cpm_long_snapshot()
    market._base_responses[(SOL,"1h")] = template.candles_1h
    market._base_responses[(SOL,"4h")] = template.candles_4h
    await _install_and_activate(issue_engine, market, event_id="CPM-LONG", members=(BNB,DOGE,SOL))
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await arm_acceptance_policy(uow, ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS-1))
    venue = CertifiedVenue()
    issued = []
    positions = None
    for index, member in enumerate((BNB,DOGE,SOL)):
        if concurrent_last_slot and index==1:
            for candidate in (DOGE,SOL):
                offset=2*3_600_000
                await _refresh_instrument_certification(issue_engine, positions,exchange_instrument_id=candidate,now_ms=NOW_MS+offset-1)
                observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(issue_engine),market.at(offset),
                    ObservationRequest(runtime_scope_id=await _active_scope_id(issue_engine,candidate),runtime_commit="kernel-test-head",
                        schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=NOW_MS+offset,attempted_at_ms=NOW_MS+offset))
                assert observed.status is ObservationStatus.SIGNAL_CREATED
            barrier = asyncio.Event()
            class RacingFacts(ReplayEntryAdmissionFactsSource):
                reads=0
                async def read_entry_admission_snapshot(self,request,*,barrier=barrier):
                    self.reads+=1
                    if self.reads==2:
                        barrier.set()
                    await asyncio.wait_for(barrier.wait(),timeout=5)
                    return await super().read_entry_admission_snapshot(request)
            facts=RacingFacts(reference_price=Decimal(102)*Decimal("1.03"),position_side="long")
            async def contender(worker,*,facts=facts,offset=offset):
                return await run_entry_worker_once(lambda:PostgresKernelUnitOfWork(issue_engine),venue,facts,
                    EntryWorkerRequest(worker_id=worker,runtime_commit="kernel-test-head",schema_revision=CURRENT_SCHEMA_REVISION,
                        now_ms=NOW_MS+offset+1000,lease_until_ms=NOW_MS+offset+31000,timeout_seconds=10,
                        admission_snapshot_validity_ms=30000), clock_ms=lambda: NOW_MS+offset+1000)
            results=await asyncio.gather(contender("capacity-race-a"),contender("capacity-race-b"))
            winners=[item for item in results if item.status is EntryWorkerStatus.DISPATCHED]
            assert len(winners)==1,results
            issued.append(winners[0].ticket_id)
            await _release_entry_lane(issue_engine,venue,ticket_id=winners[0].ticket_id,now_ms=NOW_MS+offset+2000)
            retried = await run_entry_worker_once(lambda:PostgresKernelUnitOfWork(issue_engine),venue,facts,
                EntryWorkerRequest(worker_id="capacity-race-followup",runtime_commit="kernel-test-head",schema_revision=CURRENT_SCHEMA_REVISION,
                    now_ms=NOW_MS+offset+15000,lease_until_ms=NOW_MS+offset+45000,timeout_seconds=10,
                    admission_snapshot_validity_ms=30000), clock_ms=lambda offset=offset: NOW_MS+offset+15000)
            assert retried.status is EntryWorkerStatus.ISSUE_REFUSED, retried
            assert retried.issue_status.value in {"exposure_family_capacity_exhausted","strategy_side_capacity_exhausted","budget_exhausted"},retried
            break
        offset = index*2*3_600_000
        if positions is not None:
            await _refresh_instrument_certification(issue_engine, positions,exchange_instrument_id=member,now_ms=NOW_MS+offset-1)
        result = await _observe_and_admit(issue_engine, market, venue,
            runtime_scope_id=await _active_scope_id(issue_engine,member), offset_ms=offset)
        if index<2:
            assert result[1] is EntryWorkerStatus.DISPATCHED, result
            issued.append(result[5])
            positions = await _release_entry_lane(issue_engine, venue,ticket_id=result[5],now_ms=NOW_MS+offset+2000)
        else:
            assert result[1] is EntryWorkerStatus.ISSUE_REFUSED, result
            assert result[4] in {"exposure_family_capacity_exhausted", "directional_risk_exhausted"}, result
    async with issue_engine.connect() as connection:
        tickets = (await connection.execute(sa.select(trade_tickets))).mappings().all()
    assert len(tickets)==2
    async with issue_engine.connect() as connection:
        expected_samples = (0 if research_case.endswith("failure") else
                            1 if research_case in {"budget_one", "disabled"} else 2)
        assert await connection.scalar(sa.select(sa.func.count()).select_from(shadow_outcomes_current))==expected_samples
        assert await connection.scalar(sa.select(sa.func.count()).select_from(signal_events))==3
        decisions = (await connection.execute(sa.select(admission_decisions))).mappings().all()
        assert sorted(row['decision_status'] for row in decisions)==['admitted','admitted','rejected']
        ready = (await connection.execute(sa.select(readiness_current).where(
            readiness_current.c.signal_event_id.in_([row['signal_event_id'] for row in decisions])))).mappings().all()
        assert len(ready)==3
        assert sorted(row['readiness_state'] for row in ready)==['blocked','processing','processing']
        daily = (await connection.execute(sa.text('SELECT * FROM brc_research_collection_daily'))).mappings().all()
        if research_case in {'enabled','budget_one'}:
            assert len(daily)==1
            assert daily[0]['admitted_count']==expected_samples
            assert daily[0]['skipped_count']==3-expected_samples
            assert sum(v['admitted'] for v in daily[0]['coverage_counts'].values())==expected_samples
            assert sum(v['skipped'] for v in daily[0]['coverage_counts'].values())==3-expected_samples
        else:
            assert daily==[]
        if research_case.endswith('failure'):
            failures=[r for r in caplog.records if r.message.startswith('research_collection_failed')]
            assert {r.signal_event_id for r in failures}=={r['signal_event_id'] for r in decisions}
    from scripts.trading_kernel.configure_research_collection import _parser, configure
    day = NOW_MS//86_400_000*86_400_000
    report = await configure(_parser().parse_args([
        '--database-url',issue_engine.url.render_as_string(hide_password=False),
        '--show','--day-start-ms',str(day)]))
    if research_case in {'enabled','budget_one'}:
        assert report['coverage']['admitted_count']==expected_samples
        assert report['coverage']['skipped_count']==3-expected_samples
        assert report['coverage']['skipped_budget']==3-expected_samples
        assert report['sample_population']=='quota_limited_prospective'
        expected_coverage = {}
        for event in sorted(decisions,key=lambda row: row['decided_at_ms']):
            # Signal occurrence, rather than Admission delay, owns the UTC bucket.
            async with issue_engine.connect() as connection:
                occurred = await connection.scalar(sa.select(signal_events.c.occurred_at_ms).where(
                    signal_events.c.signal_event_id==event['signal_event_id']))
            hour = occurred%86_400_000//3_600_000
            key = f'CPM-RO-001/{hour:02d}'
            bucket = expected_coverage.setdefault(key,{'admitted':0,'skipped':0})
            async with issue_engine.connect() as connection:
                sampled = await connection.scalar(sa.select(sa.func.count()).select_from(shadow_outcomes_current).where(
                    shadow_outcomes_current.c.signal_event_id==event['signal_event_id']))
            bucket['admitted' if sampled else 'skipped']+=1
        assert report['coverage']['coverage_counts']==expected_coverage
    else:
        assert report['coverage'] is None
    assert BNB in {row["exchange_instrument_id"] for row in tickets}
    assert {row["exchange_instrument_id"] for row in tickets}<={BNB,DOGE,SOL}
    assert len({row["signal_event_id"] for row in tickets})==2
    assert len({row["exposure_episode_id"] for row in tickets})==2
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        for index,ticket_id in enumerate(issued):
            claim = await uow.capacity_claims.get_for_ticket(ticket_id)
            assert claim.max_same_strategy_side==2
            assert claim.family_ticket_limit==2
            assert claim.active_strategy_side_ticket_count_at_claim==index
    for index,ticket_id in enumerate(issued):
        at = NOW_MS+6*3_600_000+index*100_000
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            ticket = await uow.tickets.get(ticket_id)
            frozen = ticket.model_dump(mode="json")
            protected = await uow.aggregates.get(ticket_id)
            commands = await uow.exchange_commands.list_for_ticket(ticket_id)
            opened = tuple(VenueOrderSnapshot(exchange_order_id=(protected.initial_stop_exchange_order_id
                if command.kind is ExchangeCommandKind.INITIAL_STOP else protected.tp1_exchange_order_id),
                venue_client_order_id=command.venue_client_order_id,position_side="long",reduce_only=True)
                for command in commands if command.kind in {ExchangeCommandKind.INITIAL_STOP,ExchangeCommandKind.TAKE_PROFIT})
            await request_exit(uow,ExitTicketRequest(ticket_id=ticket_id,reason="capacity_validation_controlled_exit",requested_at_ms=at))
        result = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(issue_engine),venue,
            DispatchCommandRequest(worker_id="capacity-exit",ticket_id=ticket_id,now_ms=at+1,
                lease_until_ms=at+5000,timeout_seconds=1,runtime_commit="kernel-test-head",schema_revision=CURRENT_SCHEMA_REVISION), clock_ms=lambda at=at: at+1)
        assert result.status.value=="accepted"
        matched = False
        for step in range(5):
            async with PostgresKernelUnitOfWork(issue_engine) as uow:
                reconciled = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=ticket_id,
                    snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,quantity=Decimal(0),
                        average_entry_price=None,open_orders=opened,observed_at_ms=at+100+step*1000)))
            if reconciled.status.value=="matched":
                matched=True
                break
            cancel = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(issue_engine),venue,
                DispatchCommandRequest(worker_id="capacity-cleanup",ticket_id=ticket_id,now_ms=at+200+step*1000,
                    lease_until_ms=at+5200+step*1000,timeout_seconds=1,runtime_commit="kernel-test-head",schema_revision=CURRENT_SCHEMA_REVISION), clock_ms=lambda at=at,step=step: at+200+step*1000)
            assert cancel.status.value=="accepted"
            async with PostgresKernelUnitOfWork(issue_engine) as uow:
                command = await uow.exchange_commands.get(cancel.command_id)
            assert command.kind is ExchangeCommandKind.CANCEL_ORDER
            opened=tuple(order for order in opened if order.exchange_order_id!=command.payload.exchange_order_id)
        assert matched and opened==()
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await settle_ticket(uow,SettleTicketRequest(ticket_id=ticket_id,settled_at_ms=at+10_000))
            await record_trade_review(uow,RecordTradeReviewRequest(ticket_id=ticket_id,
                review_id=f"review:capacity:{index}",outcome="closed",metrics={"economics_evidence":"structural_test_only"},
                decision_impact={"capacity_policy":"v0"},recorded_at_ms=at+10_001))
            aggregate = await uow.aggregates.get(ticket_id)
            assert aggregate.status is AggregateStatus.TERMINAL
            assert (await uow.budgets.get_for_ticket(ticket_id)).status=="released"
            assert (await uow.reviews.get_for_ticket(ticket_id)).review_id==f"review:capacity:{index}"
            closed_ticket = await uow.tickets.get(ticket_id)
            assert {k:v for k,v in closed_ticket.model_dump(mode="json").items() if k!="status"}=={k:v for k,v in frozen.items() if k!="status"}
            assert await uow.entry_admission.count_active_strategy_side_tickets(
                venue_id=ticket.identity.netting_domain.venue_id,account_id=ticket.identity.netting_domain.account_id,
                strategy_group_id=ticket.identity.runtime.strategy_group_id,position_side="long")==1-index
        from src.trading_kernel.interfaces.read_signal_path import read_signal_path
        path = await read_signal_path(issue_engine,signal_event_id=ticket.identity.signal_event_id)
        if research_case.endswith('failure') or research_case=='disabled' or (research_case=='budget_one' and index==1):
            assert path is None
            continue
        assert path is not None and path.evaluation_kind=="generic_signal_path_v1"
        assert path.ticket_id==ticket_id
        assert path.review_id==f"review:capacity:{index}" and path.review_revision==1
        assert path.review_metrics=={"economics_evidence":"structural_test_only"}
        assert path.path_initial_risk_per_unit is not None
        assert path.ticket_initial_stop_price==ticket.initial_stop_price
        assert path.ticket_frozen_stop_risk==ticket.risk_at_stop
        if index==0:
            from src.trading_kernel.application.settle_ticket import (
                ReviseTradeReviewRequest,
                revise_trade_review,
            )
            async with PostgresKernelUnitOfWork(issue_engine) as uow:
                await revise_trade_review(uow,ReviseTradeReviewRequest(ticket_id=ticket_id,
                    review_id='review:capacity:revision2',supersedes_review_id=f'review:capacity:{index}',
                    outcome='closed',metrics={'economics_evidence':'revised_structural_test_only'},
                    decision_impact={'capacity_policy':'v0'},recorded_at_ms=at+10_002))
            revised_path=await read_signal_path(issue_engine,signal_event_id=ticket.identity.signal_event_id)
            assert revised_path.review_revision==2 and revised_path.review_id=='review:capacity:revision2'
            assert revised_path.review_metrics=={'economics_evidence':'revised_structural_test_only'}
            assert revised_path.path_initial_risk_per_unit==path.path_initial_risk_per_unit


@pytest.mark.asyncio
async def test_capacity_v0_brf2_family_one_overrides_strategy_side_two(capacity_engine) -> None:
    issue_engine = capacity_engine
    request=RuntimeAuthoritySeedRequest(account_id="subaccount-source-test",runtime_commit="kernel-test-head",
        schema_revision="0009_capacity_policy_v0",seeded_at_ms=NOW_MS-10_000_000)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await seed_runtime_authority(uow,request)
        await set_strategy_entry_state(uow,strategy_group_id="SOR-001",target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=1,reason="owner_retired_sor",idempotency_key="brf2-capacity:sor-pause",
                owner_identity="owner",now_ms=NOW_MS-9_000_000),authentication_strength="totp_step_up")
    await _install_capacity_then_upgrade(issue_engine,request)
    market=RecordingReplayMarketSource()
    template=brf2_short_snapshot()
    market._base_responses[(SOL,"1h")]=template.candles_1h
    market._base_responses[(SOL,"4h")]=template.candles_4h
    await _install_and_activate(issue_engine,market,event_id="BRF2-SHORT",members=(ETH,SOL))
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await arm_acceptance_policy(uow,ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS-1))
    venue=CertifiedVenue()
    first=await _observe_and_admit(issue_engine,market,venue,runtime_scope_id=await _active_scope_id(issue_engine,ETH),offset_ms=0)
    assert first[1] is EntryWorkerStatus.DISPATCHED,first
    positions=await _release_entry_lane(issue_engine,venue,ticket_id=first[5],now_ms=NOW_MS+2000)
    await _refresh_instrument_certification(issue_engine,positions,exchange_instrument_id=SOL,now_ms=NOW_MS+TWO_HOURS_MS-1)
    second=await _observe_and_admit(issue_engine,market,venue,runtime_scope_id=await _active_scope_id(issue_engine,SOL),offset_ms=TWO_HOURS_MS)
    assert second[1] is EntryWorkerStatus.ISSUE_REFUSED,second
    assert second[4]=="exposure_family_capacity_exhausted",second
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        claim=await uow.capacity_claims.get_for_ticket(first[5])
        assert claim.max_same_strategy_side==2 and claim.family_ticket_limit==1
        rejected=await uow.admission_decisions.get_for_signal(second[2])
        assert rejected.portfolio_usage.max_same_strategy_side==2
        assert rejected.portfolio_usage.active_strategy_side_ticket_count==1
        assert rejected.portfolio_usage.active_family_ticket_count==1
        assert rejected.ticket_id is None


async def _seed_replay_runtime(
    engine: AsyncEngine,
    source: RecordingReplayMarketSource,
) -> None:
    for event_id, members in (
        ("CPM-LONG", (BNB, DOGE)),
        ("BRF2-SHORT", (ETH,)),
        ("SOR-1H-SHORT", (BTC,)),
    ):
        await _install_and_activate(
            engine,
            source,
            event_id=event_id,
            members=members,
        )

    async with PostgresKernelUnitOfWork(engine) as uow:
        await set_strategy_entry_state(uow,strategy_group_id="SOR-1H-001",target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=1,reason="hourly replay",idempotency_key="replay:hourly:resume",owner_identity="owner",now_ms=NOW_MS-2),authentication_strength="totp_step_up")
        await arm_acceptance_policy(
            uow,
            ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS - 1),
        )


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
            instrument_certification_source=RecordingReadonlyCertificationSource(
                engine
            ),
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
            instrument_certification_source=RecordingReadonlyCertificationSource(
                engine
            ),
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
        clock_ms=lambda: observed_at_ms + 1_000,
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


async def _exchange_command_ids(engine: AsyncEngine) -> tuple[str, ...]:
    async with engine.connect() as connection:
        return tuple(
            str(command_id)
            for command_id in await connection.scalars(
                sa.select(exchange_commands.c.command_id).order_by(
                    exchange_commands.c.command_id
                )
            )
        )


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
