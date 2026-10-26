"""Production-shaped local Event producer and terminal lifecycle certification harness."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import ObservationStatus
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    MonitorOwnerStatus,
    VenueCommandRequest,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
)
from src.trading_kernel.infrastructure.pg_models import runtime_scopes_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
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
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.readonly_api import get_owner_projection
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    AVAX,
    BTC,
    ETH,
    NOW_MS,
    OP,
    SOL,
    SUI,
    brf2_short_snapshot,
    cpm_long_snapshot,
    flat_candles,
    mpg_long_snapshot,
    sor_snapshot,
)

SAFE_TEST_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
EVENT_INSTRUMENTS = {
    "CPM-LONG": ETH,
    "MPG-LONG": SOL,
    "MI-LONG": SOL,
    "SOR-LONG": AVAX,
    "SOR-SHORT": BTC,
    "BRF2-SHORT": BTC,
    "SOR-1H-LONG": AVAX,
    "SOR-1H-SHORT": BTC,
}


class CertifiedMarketSource:
    def __init__(self,event_id: str | None=None) -> None:
        self.event_id=event_id
        cpm = cpm_long_snapshot()
        mpg = mpg_long_snapshot()
        brf2 = brf2_short_snapshot()
        sor_long = sor_snapshot(side="long").model_copy(
            update={"exchange_instrument_id": AVAX}
        )
        sor_short = sor_snapshot(side="short").model_copy(
            update={"exchange_instrument_id": BTC}
        )
        peer_1h = flat_candles(13, 3_600_000)
        self.responses = {
            (ETH, "1h"): cpm.candles_1h,
            (ETH, "4h"): cpm.candles_4h,
            (SOL, "1h"): mpg.candles_1h,
            (SOL, "4h"): mpg.candles_4h,
            (OP, "1h"): peer_1h,
            (AVAX, "1h"): peer_1h,
            (SUI, "1h"): peer_1h,
            (BTC, "1h"): brf2.candles_1h,
            (BTC, "4h"): brf2.candles_4h,
            (AVAX, "15m"): sor_long.candles_15m,
            (BTC, "15m"): sor_short.candles_15m,
        }

        if event_id in {'SOR-1H-LONG','SOR-1H-SHORT'}:
            d=NOW_MS//86400000*86400000
            long=event_id=='SOR-1H-LONG'
            self.responses[(EVENT_INSTRUMENTS[event_id],'1h')]=tuple(ClosedCandle(open_time_ms=d+i*3600000,close_time_ms=d+(i+1)*3600000,
                open=Decimal(100),high=Decimal(103 if long and i==7 else 101),low=Decimal(97 if not long and i==7 else 99),
                close=Decimal(102 if long else 98) if i==7 else Decimal(100),volume=Decimal(1000000)) for i in range(8))

    def shifted(self, delta_ms: int) -> CertifiedMarketSource:
        shifted = CertifiedMarketSource(self.event_id)
        shifted.responses = {
            key: tuple(
                candle.model_copy(
                    update={
                        "open_time_ms": candle.open_time_ms + delta_ms,
                        "close_time_ms": candle.close_time_ms + delta_ms,
                    }
                )
                for candle in candles
            )
            for key, candles in self.responses.items()
        }
        return shifted

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        if self.event_id in {"SOR-1H-LONG","SOR-1H-SHORT"} and request.timeframe=="1h":
            return _hourly_session_candles(request,self.event_id)
        return self.responses.get(
            (request.exchange_instrument_id, request.timeframe),
            (),
        )


class CertifiedEntryAdmissionFactsSource:
    def __init__(
        self,
        *,
        reference_price: Decimal,
        position_side: Literal["long", "short"],
    ) -> None:
        offset = max(reference_price * Decimal("0.0001"), Decimal("0.01"))
        spread = offset / Decimal(2)
        if position_side == "long":
            self.best_ask = reference_price + offset
            self.best_bid = self.best_ask - spread
        else:
            self.best_bid = reference_price - offset
            self.best_ask = self.best_bid + spread

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        return EntryAdmissionSnapshot(
            account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id=request.venue_id,
                account_id=request.account_id,
                account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",
                position_mode="independent_sides",
                margin_mode="cross",
                exchange_instrument_id=request.exchange_instrument_id,
                mark_price=(self.best_bid + self.best_ask) / Decimal(2),
                configured_leverage=5,
                total_wallet_balance=Decimal(1000000),
                total_margin_balance=Decimal(1000000),
                total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),
                available_margin=Decimal(1000000),
                account_positions=(),
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms + request.valid_for_ms,
            ),
            best_bid_price=self.best_bid,
            best_ask_price=self.best_ask,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=(self.best_bid + self.best_ask) / Decimal(2),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000000),
            total_margin_balance=Decimal(1000000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000000),
            account_positions=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CertifiedVenue:
    def __init__(self) -> None:
        self.calls: list[VenueCommandRequest] = []
        self.last_observed_at_ms = NOW_MS

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls.append(request)
        self.last_observed_at_ms = max(
            self.last_observed_at_ms + 1,
            request.deadline_at_ms - 29_999,
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self.last_observed_at_ms,
            exchange_order_id=(
                request.payload.exchange_order_id
                if isinstance(request.payload, CancelCommandPayload)
                else f"venue-{request.kind.value}-{len(self.calls)}"
            ),
        )

    async def lookup_command_truth(self, request):
        raise AssertionError(f"unexpected unknown command lookup: {request.command_id}")

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        self.last_observed_at_ms += 1
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=self.last_observed_at_ms,
            leverage_verification_digest="sha256:" + "4" * 64,
        )

    async def read_configured_leverage(
        self, request: LeverageTruthRequest
    ) -> LeverageTruthSnapshot:
        self.last_observed_at_ms += 1
        return LeverageTruthSnapshot(
            exchange_configured_leverage=request.desired_leverage,
            long_position_quantity=Decimal(0),
            short_position_quantity=Decimal(0),
            regular_open_order_ids=(),
            conditional_open_order_ids=(),
            observed_at_ms=self.last_observed_at_ms,
        )


class CertifiedPositionSource:
    def __init__(self) -> None:
        self.quantity = Decimal(0)
        self.average_entry_price: Decimal | None = None
        self.liquidation_price: Decimal | None = None

    def set_open(
        self,
        *,
        quantity: Decimal,
        average_entry_price: Decimal,
        position_side: str,
    ) -> None:
        self.quantity = quantity
        self.average_entry_price = average_entry_price
        self.liquidation_price = average_entry_price * (
            Decimal("0.75") if position_side == "long" else Decimal("1.25")
        )

    def set_flat(self) -> None:
        self.quantity = Decimal(0)
        self.average_entry_price = None
        self.liquidation_price = None

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        return PositionSnapshot(
            netting_domain=request.netting_domain,
            quantity=self.quantity,
            average_entry_price=self.average_entry_price,
            venue_reported_liquidation_price=self.liquidation_price,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
        )


class CertifiedPostFillFactsSource:
    def __init__(self, ticket) -> None:
        self.ticket = ticket

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        ticket = self.ticket
        stress_balance = max(Decimal(1000000), ticket.notional * Decimal(10))
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=ticket.entry_reference_price,
            configured_leverage=ticket.selected_leverage,
            total_wallet_balance=stress_balance,
            total_margin_balance=stress_balance,
            total_initial_margin=ticket.reserved_margin,
            total_maintenance_margin=Decimal(0),
            available_margin=stress_balance - ticket.reserved_margin,
            account_positions=(
                AccountRiskPosition(
                    exchange_instrument_id=request.exchange_instrument_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),
            ),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CertifiedLifecycleFactsSource:
    def __init__(self) -> None:
        self.facts: TicketLifecycleFacts | None = None

    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts:
        if self.facts is None:
            raise AssertionError("lifecycle facts requested before TP1 fill")
        return self.facts.model_copy(
            update={"observed_at_ms": request.observed_at_ms}
        )


class CertifiedReviewEconomicsSource:
    def __init__(self) -> None:
        self.requests: list[ReviewEconomicsRequest] = []

    async def read_review_economics(
        self,
        request: ReviewEconomicsRequest,
    ) -> ReviewEconomicsFacts:
        self.requests.append(request)
        entry_price = Decimal(100)
        exit_price = (
            Decimal(110)
            if request.netting_domain.position_side == "long"
            else Decimal(90)
        )
        half = request.expected_entry_quantity / Decimal(2)
        return ReviewEconomicsFacts(
            ticket_id=request.ticket_id,
            entry_fills=(
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:entry",
                    exchange_order_id=(
                        request.entry_order_reference.submitted_exchange_order_id
                    ),
                    command_id=request.entry_order_reference.command_id,
                    role=request.entry_order_reference.role,
                    quantity=request.expected_entry_quantity,
                    price=entry_price,
                    fee=_valued_usdt_fee("0.1", request.entry_time_ms),
                    realized_pnl_quote=Decimal(0),
                    occurred_at_ms=request.entry_time_ms,
                ),
            ),
            exit_fills=(
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:exit:1",
                    exchange_order_id=(
                        request.exit_order_references[0].submitted_exchange_order_id
                    ),
                    command_id=request.exit_order_references[0].command_id,
                    role=request.exit_order_references[0].role,
                    quantity=half,
                    price=exit_price,
                    fee=_valued_usdt_fee("0.05", request.exit_time_ms),
                    realized_pnl_quote=Decimal(0),
                    occurred_at_ms=request.exit_time_ms,
                ),
                ReviewFill(
                    exchange_trade_id=f"trade:{request.ticket_id}:exit:2",
                    exchange_order_id=(
                        request.exit_order_references[-1].submitted_exchange_order_id
                    ),
                    command_id=request.exit_order_references[-1].command_id,
                    role=request.exit_order_references[-1].role,
                    quantity=request.expected_entry_quantity - half,
                    price=exit_price,
                    fee=_valued_usdt_fee("0.05", request.exit_time_ms),
                    realized_pnl_quote=Decimal(0),
                    occurred_at_ms=request.exit_time_ms,
                ),
            ),
            funding_quote=Decimal(0),
            funding_unavailable_reason=None,
            observed_at_ms=request.observed_at_ms,
        )


def _valued_usdt_fee(amount: str, valued_at_ms: int):
    return value_native_fee(
        native_fee=NativeFee(asset="USDT", amount=Decimal(amount)),
        valuation_evidence=FeeValuationEvidence(
            method="native_usdt",
            rate_usdt_per_asset=Decimal(1),
            price_pair=None,
            observed_at_ms=None,
            valued_at_ms=valued_at_ms,
        ),
    )


def _maintenance_brackets() -> tuple[MaintenanceMarginBracket, ...]:
    return (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )


async def run_event_chain(
    six_event_engine: AsyncEngine,
    contract: RegisteredStrategyContract,
    hourly_dynamic: bool,
) -> None:
    instrument_id = EVENT_INSTRUMENTS[contract.event_id]
    runtime_scope_id = await (_seed_dynamic_hourly_runtime(six_event_engine,contract=contract,instrument_id=instrument_id) if hourly_dynamic else _seed_runtime(
        six_event_engine,
        contract=contract,
        instrument_id=instrument_id,
    ))
    def uow_factory() -> PostgresKernelUnitOfWork:
        return PostgresKernelUnitOfWork(six_event_engine)

    market_source = CertifiedMarketSource(contract.event_id)

    observed = await run_observation_worker_once(
        uow_factory,
        market_source,
        ObservationWorkerRequest(
            worker_id="observation-worker-certification",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 30_000,
            timeout_seconds=5,
            retry_interval_ms=1_000,
        ),
    )
    if hourly_dynamic:
        for _ in range(14):
            if observed.runtime_scope_id==runtime_scope_id:break
            observed=await run_observation_worker_once(uow_factory,market_source,ObservationWorkerRequest(worker_id='orb-live-observe',runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=NOW_MS,lease_until_ms=NOW_MS+30000,timeout_seconds=5,retry_interval_ms=1000))
    assert observed.status is ObservationWorkerStatus.OBSERVED
    assert observed.runtime_scope_id == runtime_scope_id
    assert observed.observation_status is ObservationStatus.SIGNAL_CREATED

    async with uow_factory() as uow:
        readiness = await uow.signals.get_readiness(runtime_scope_id)
        assert readiness is not None
        assert readiness.signal_event_id is not None
        signal = await uow.signals.get(readiness.signal_event_id)
    assert signal is not None
    reference_price = Decimal(
        str(next(fact.value for fact in signal.facts if fact.role == "protection_reference"))
    )

    venue = CertifiedVenue()
    position_source = CertifiedPositionSource()
    lifecycle_source = CertifiedLifecycleFactsSource()
    review_source = CertifiedReviewEconomicsSource()
    entry = await run_entry_worker_once(
        uow_factory,
        venue,
        CertifiedEntryAdmissionFactsSource(
            reference_price=(
                reference_price * Decimal("1.03")
                if contract.position_side == "long"
                else reference_price * Decimal("0.97")
            ),
            position_side=contract.position_side,
        ),
        EntryWorkerRequest(
            worker_id="entry-worker-certification",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=NOW_MS + 1_000,
            lease_until_ms=NOW_MS + 6_000,
            timeout_seconds=1,
            admission_snapshot_validity_ms=30_000,
        ),
        clock_ms=lambda: NOW_MS + 1_000,
    )
    async with uow_factory() as uow:
        entry_decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
    entry_diagnostic = (
        None
        if entry_decision is None
        else (
            entry_decision.first_blocker,
            entry_decision.binding_constraint,
            entry_decision.portfolio_usage,
        )
    )
    assert entry.status is EntryWorkerStatus.DISPATCHED, entry_diagnostic
    assert entry.ticket_id is not None

    async with uow_factory() as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None
    position_source.set_open(
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        position_side=ticket.identity.netting_domain.position_side,
    )
    reconciliation_request = ReconciliationWorkerRequest(
        worker_id="reconciliation-worker-certification",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=NOW_MS + 2_000,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=1_000,
    )
    filled = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request,
    )
    assert filled.status is ReconciliationWorkerStatus.POSITION_RECONCILED

    lifecycle_request = LifecycleWorkerRequest(
        worker_id="lifecycle-worker-certification",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=NOW_MS + 3_000,
        lease_until_ms=NOW_MS + 8_000,
        timeout_seconds=1,
        idle_poll_interval_ms=1_000,
    )
    initial_stop = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request,
    )
    assert initial_stop.status is LifecycleWorkerStatus.DISPATCHED
    post_fill_source = CertifiedPostFillFactsSource(ticket)
    post_fill = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(
            update={"now_ms": NOW_MS + 3_500}
        ),
        account_risk_source=post_fill_source,
        instrument_rules_source=post_fill_source,
    )
    assert post_fill.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert post_fill.detail == "post_fill_stress:passed"
    take_profit = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 4_000, "lease_until_ms": NOW_MS + 9_000}
        ),
    )
    assert take_profit.status is LifecycleWorkerStatus.DISPATCHED

    tp1_quantity = ticket.take_profit_quantities[0]
    runner_quantity = ticket.quantity - tp1_quantity
    lifecycle_source.facts = TicketLifecycleFacts(
        position_quantity=runner_quantity,
        tp1_filled_quantity=tp1_quantity,
        tp1_average_fill_price=ticket.take_profit_prices[0],
        allocated_entry_fee_quote=Decimal("0.1"),
        exit_taker_fee_rate=Decimal("0.0005"),
        price_tick=Decimal("0.1"),
        market_facts=None,
        observed_at_ms=NOW_MS + 5_000,
    )
    runner_replacement = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 5_000, "lease_until_ms": NOW_MS + 10_000}
        ),
    )
    assert runner_replacement.status is LifecycleWorkerStatus.DISPATCHED
    old_stop_cancel = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 6_000, "lease_until_ms": NOW_MS + 11_000}
        ),
    )
    assert old_stop_cancel.status is LifecycleWorkerStatus.DISPATCHED

    position_source.set_flat()
    external_flat = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 7_000}),
    )
    assert external_flat.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    runner_stop_cleanup = await run_lifecycle_worker_once(
        uow_factory,
        venue,
        lifecycle_source,
        lifecycle_request.model_copy(
            update={"now_ms": NOW_MS + 8_000, "lease_until_ms": NOW_MS + 13_000}
        ),
    )
    assert runner_stop_cleanup.status is LifecycleWorkerStatus.DISPATCHED
    matched = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 9_000}),
    )
    assert matched.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    settled = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 10_000}),
    )
    assert settled.status is ReconciliationWorkerStatus.SETTLED
    reviewed = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation_request.model_copy(update={"now_ms": NOW_MS + 11_000}),
        review_economics_source=review_source,
    )
    assert reviewed.status is ReconciliationWorkerStatus.REVIEWED

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        owner_state = await get_owner_projection(
            uow,
            ticket.identity.ticket_id,
        )

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TERMINAL
    assert aggregate.position_qty == 0
    assert review is not None
    assert review.metrics["event_spec_id"] == contract.event_spec_id
    assert review.metrics["economics_completeness"] == "complete"
    assert review.metrics["gross_realized_pnl_quote"] is not None
    assert review.metrics["trading_fees_quote"] == "0.20"
    assert review.metrics["net_pnl_quote"] is not None
    assert review.metrics["planned_r_multiple"] is not None
    assert review.metrics["actual_r_multiple"] is not None
    assert review.metrics["planned_stop_risk"] is not None
    assert review.metrics["actual_stop_risk"] is not None
    assert len(review_source.requests) == 1
    assert incident is None
    assert owner_state is not None
    assert owner_state.owner_status is MonitorOwnerStatus.COMPLETED
    assert [command.kind.value for command in commands] == [
        "entry",
        "initial_stop",
        "take_profit",
        "replace_protection",
        "cancel_order",
        "cancel_order",
    ]


def _hourly_session_candles(request: ClosedCandleRequest,event_id: str) -> tuple[ClosedCandle,...]:
    day=request.closed_at_ms//86400000*86400000
    count=(request.closed_at_ms-day)//3600000
    long=event_id=='SOR-1H-LONG'
    chosen=request.exchange_instrument_id==EVENT_INSTRUMENTS[event_id]
    return tuple(ClosedCandle(open_time_ms=day+i*3600000,close_time_ms=day+(i+1)*3600000,
        open=Decimal(100),high=Decimal(103 if chosen and long and day+(i+1)*3600000==NOW_MS else 101),
        low=Decimal(97 if chosen and not long and day+(i+1)*3600000==NOW_MS else 99),
        close=Decimal(102 if long else 98) if chosen and day+(i+1)*3600000==NOW_MS else Decimal(100),volume=Decimal(1000000)) for i in range(count))


async def _seed_dynamic_hourly_runtime(engine: AsyncEngine,*,contract: RegisteredStrategyContract,instrument_id: str) -> str:
    from src.trading_kernel.application.advance_strategy_universe import (
        UniverseActivationRequest,
        advance_strategy_universe,
    )
    from src.trading_kernel.application.install_strategy_universe import (
        UniverseInstallRequest,
        install_strategy_universe,
    )
    from src.trading_kernel.application.observe_strategy_scope import (
        ObservationRequest,
        observe_strategy_scope,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.application.run_instrument_selection import (
        RunInstrumentSelectionRequest,
        run_instrument_selection_once,
    )
    from src.trading_kernel.domain.instrument_selection import SelectionKline
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_EVENT_SPEC_IDS,
        ORB_STATIC_MEMBERS,
        OrbSessionSelectionSpec,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    from src.trading_kernel.interfaces.selection_runtime_worker import (
        SelectionRuntimeRequest,
        run_materialization_runtime_once,
    )
    day=NOW_MS//86400000*86400000;h=3600000;previous=day-86400000
    prep=NOW_MS-300000
    market=CertifiedMarketSource(contract.event_id)
    factory=lambda:PostgresKernelUnitOfWork(engine)
    spec=OrbSessionSelectionSpec()
    async with factory() as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='account-certification',runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=previous))
        await uow.instrument_selection.install_orb_spec(spec,installed_at_ms=previous+1)
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=1,reason='local paired Dynamic chain',idempotency_key='orb:full:resume',owner_identity='owner',now_ms=previous+2),authentication_strength='totp_step_up')
        await arm_acceptance_policy(uow,ArmAcceptancePolicyRequest(armed_at_ms=previous+3))
    async def certify(now):
        # Official certification producer checks the bounded due set; no venue mutation.
        for _ in range(24):
            result=await run_reconciliation_worker_once(factory,CertifiedVenue(),CertifiedPositionSource(),ReconciliationWorkerRequest(worker_id='orb:full:cert',runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=now,timeout_seconds=1,unknown_visibility_grace_ms=30000,idle_poll_interval_ms=1000,certification_lease_ms=60000,certification_valid_for_ms=600000,
                certification_eligible_check_interval_ms=300000,certification_owner_action_check_interval_ms=300000,certification_transient_retry_interval_ms=30000),instrument_certification_source=RecordingReadonlyCertificationSource(engine))
            if result.status is not ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED:break
    async def warm(uid,close,now):
        async with engine.connect() as connection:
            scopes=tuple((await connection.execute(sa.select(runtime_scopes_current.c.runtime_scope_id).where(runtime_scopes_current.c.universe_version_id==uid,runtime_scopes_current.c.lifecycle_state=='warming'))).scalars())
        for sid in scopes:
            result=await observe_strategy_scope(factory,market,ObservationRequest(runtime_scope_id=sid,runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=close,attempted_at_ms=now))
            assert result.status is ObservationStatus.WARMED,result.detector_reason
    for event in ORB_EVENT_SPEC_IDS:
        async with factory() as uow:
            installed=await install_strategy_universe(uow,UniverseInstallRequest(event_spec_id=event,runtime_profile_id=RUNTIME_PROFILE_ID,owner_policy_id='policy-main',exchange_instrument_ids=ORB_STATIC_MEMBERS,installed_at_ms=previous+h-1000))
        await certify(previous+h)
        await warm(installed.universe.universe_version_id,previous+h,previous+h)
        async with factory() as uow:
            active=await advance_strategy_universe(uow,UniverseActivationRequest(universe_version_id=installed.universe.universe_version_id,attempted_at_ms=previous+h+1))
        assert active.status.value=='activated'
    async with factory() as uow:
        control=await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=day,request=ControlMutationRequest(expected_version=1,reason='current daily Dynamic',idempotency_key='orb:full:dynamic',owner_identity='owner',now_ms=day+100),authentication_strength='totp_step_up')
    desired=tuple(sorted({'binance-usdm:ADAUSDT:perpetual','binance-usdm:AVAXUSDT:perpetual','binance-usdm:BNBUSDT:perpetual','binance-usdm:BTCUSDT:perpetual','binance-usdm:ETHUSDT:perpetual','binance-usdm:SOLUSDT:perpetual','binance-usdm:XRPUSDT:perpetual'}))
    class Selector:
        async def fetch_selection_klines(self,request):
            return tuple(SelectionKline(open_time_ms=day-23*h+i*900000,close_time_ms=day-23*h+(i+1)*900000,open=Decimal(100),close=Decimal(100),high=Decimal(101 if i<92 or request.exchange_instrument_id in desired else 103),low=Decimal(99),quote_volume=Decimal(1000000)) for i in range(96))
    selected=await run_instrument_selection_once(uow_factory=factory,market_source=Selector(),request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,selection_epoch_id=control.selection_epoch_id,period_anchor_ms=day,worker_id='orb:full:selection'),clock_ms=lambda:prep)
    assert selected.outcome=='SNAPSHOT_READY'
    for tick in range(1,15):
        await certify(prep+tick)
        async with engine.connect() as connection:
            warming=tuple((await connection.execute(sa.text("SELECT universe_version_id FROM brc_strategy_universe_versions WHERE strategy_group_id='SOR-1H-001' AND lifecycle_state='warming'"))).scalars())
        for uid in warming:await warm(uid,NOW_MS-h,prep+tick)
        progress=await run_materialization_runtime_once(uow_factory=factory,audit_source=PublicMarketAuthorityGapAuditSource(market),request=SelectionRuntimeRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,worker_id='orb:full:materialization',now_ms=prep+tick),clock_ms=lambda tick=tick:prep+tick)
        if progress.disposition is not None and progress.disposition.value=='ACTIVE_NEW':break
    assert progress.disposition.value=='ACTIVE_NEW',progress.reason_code
    async with engine.connect() as connection:
        sid=await connection.scalar(sa.select(runtime_scopes_current.c.runtime_scope_id).where(runtime_scopes_current.c.event_spec_id==contract.event_spec_id,runtime_scopes_current.c.exchange_instrument_id==instrument_id,runtime_scopes_current.c.lifecycle_state=='active'))
    return str(sid)


async def _seed_runtime(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
    instrument_id: str,
) -> str:
    warm_interval_ms = 900_000 if contract.timeframe == "15m" else 3_600_000
    warm_now_ms = NOW_MS - warm_interval_ms
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="account-certification",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=warm_now_ms - 10_000,
            ),
        )
        configured = await configure_strategy_universe(
            uow,
            UniverseConfigurationRequest(
                runtime_profile_id=RUNTIME_PROFILE_ID,
                event_id=contract.event_id,
                exchange_instrument_ids=(instrument_id,),
                installed_at_ms=warm_now_ms - 1_000,
            ),
        )
        if contract.strategy_group_id=='SOR-1H-001':
            from src.trading_kernel.application.owner_control import (
                ControlMutationRequest,
                set_strategy_entry_state,
            )
            from src.trading_kernel.domain.owner_control import StrategyEntryState
            await set_strategy_entry_state(uow,strategy_group_id=contract.strategy_group_id,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=1,reason='local hourly chain certification',idempotency_key='orb:certification:resume',owner_identity='owner',now_ms=warm_now_ms-800),authentication_strength='totp_step_up')
        await arm_acceptance_policy(
            uow,
            ArmAcceptancePolicyRequest(armed_at_ms=warm_now_ms - 500),
        )
    assert configured.universe is not None

    certification = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        CertifiedVenue(),
        CertifiedPositionSource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-universe-certification",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=warm_now_ms,
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
    assert certification.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED

    warm_source = CertifiedMarketSource(contract.event_id) if contract.strategy_group_id=="SOR-1H-001" else CertifiedMarketSource(contract.event_id).shifted(-warm_interval_ms)
    warmed = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        warm_source,
        ObservationWorkerRequest(
            worker_id="observation-worker-universe-warming",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=warm_now_ms,
            lease_until_ms=warm_now_ms + 30_000,
            timeout_seconds=5,
            retry_interval_ms=1_000,
        ),
    )
    assert warmed.status is ObservationWorkerStatus.OBSERVED
    assert warmed.observation_status is ObservationStatus.WARMED

    refreshed = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        CertifiedVenue(),
        CertifiedPositionSource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-active-certification-refresh",
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

    async with engine.connect() as connection:
        runtime_scope_id = await connection.scalar(
            sa.select(runtime_scopes_current.c.runtime_scope_id).where(
                runtime_scopes_current.c.universe_version_id
                == configured.universe.universe_version_id,
                runtime_scopes_current.c.exchange_instrument_id == instrument_id,
                runtime_scopes_current.c.lifecycle_state == "active",
            )
        )
    assert runtime_scope_id is not None
    return str(runtime_scope_id)
