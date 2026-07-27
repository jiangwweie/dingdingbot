from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.activate_strategy_universe import (
    ActivateStrategyUniverseRequest,
    activate_strategy_universe,
)
from src.trading_kernel.application.apply_corporate_event_authority import (
    ApplyCorporateEventAuthorityRequest,
    apply_corporate_event_authority,
)
from src.trading_kernel.application.build_product_admission_snapshot import (
    build_product_admission_context,
)
from src.trading_kernel.application.complete_corporate_action_reprofile import (
    CompleteCorporateActionReprofileRequest,
    complete_corporate_action_reprofile,
)
from src.trading_kernel.application.mark_strategy_universe_warm_ready import (
    MarkStrategyUniverseWarmReadyRequest,
    mark_strategy_universe_warm_ready,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.application.runtime_facts import (
    ProductMarketFactsRequest,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.corporate_events import (
    CorporateEvent,
    CorporateEventCertainty,
    CorporateEventCoverage,
    CorporateEventKind,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    canonical_digest,
)
from src.trading_kernel.domain.product_admission import (
    ProductMarketFacts,
    ProductProfile,
)
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    runtime_capabilities_current,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.us_market_calendar_seed import (
    seed_us_market_calendar,
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
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.test_six_event_system_certification import (
    CertifiedEntryAdmissionFactsSource,
    CertifiedLifecycleFactsSource,
    CertifiedPositionSource,
    CertifiedReviewEconomicsSource,
    CertifiedVenue,
    _maintenance_brackets,
    six_event_engine,  # noqa: F401
)
from tests.trading_kernel.integration.test_rsr_vcb_observation import (
    EVENT_SPEC_ID,
    WindowSource,
    _candles,
    _compressed_projection_candles,
    _trigger_window,
)


TRIGGER_HOUR_MS = 1_800_025_200_000
TRIGGER_CLOSE_MS = TRIGGER_HOUR_MS + 900_000
ENTRY_TIME_MS = TRIGGER_CLOSE_MS + 1_000


class USEquityEntryFactsSource(CertifiedEntryAdmissionFactsSource):
    async def read_entry_admission_snapshot(self, request):
        snapshot = await super().read_entry_admission_snapshot(request)
        instrument = snapshot.instrument_facts[0]
        return snapshot.model_copy(
            update={
                "instrument_facts": (
                    AdmissionInstrumentFacts(
                        exchange_instrument_id=(
                            instrument.exchange_instrument_id
                        ),
                        mark_price=instrument.mark_price,
                        configured_leverage=5,
                    ),
                )
            }
        )

    async def read_product_market_facts(
        self,
        request: ProductMarketFactsRequest,
    ) -> ProductMarketFacts:
        midpoint = (self.best_bid + self.best_ask) / Decimal("2")
        return ProductMarketFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            best_bid=self.best_bid,
            best_ask=self.best_ask,
            mark_price=midpoint,
            index_price=midpoint,
            top5_bid_depth=Decimal("1000000000000"),
            top5_ask_depth=Decimal("1000000000000"),
            funding_rate=Decimal("0.0001"),
            funding_observed_at_ms=request.observed_at_ms - 1,
            observed_at_ms=request.observed_at_ms - 1,
        )


@pytest.mark.asyncio
async def test_rsr_vcb_us_equity_reaches_terminal_review_through_real_kernel(
    six_event_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    await _seed_complete_us_runtime(six_event_engine)
    windows = _market_windows(universe)
    source = WindowSource(windows)
    projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=TRIGGER_HOUR_MS,
        claim_owner="us-full-chain-projection",
    )
    await _warm_and_activate(
        six_event_engine,
        universe=universe,
        projection_run_id=projection.projection_run_id,
    )

    armed = None
    for member in projection.top_two:
        async with PostgresKernelUnitOfWork(six_event_engine) as uow:
            current = await uow.strategy_universes.get_active_armed_structure(
                event_spec_id=EVENT_SPEC_ID,
                universe_version_id=universe.universe_version_id,
                projection_run_id=projection.projection_run_id,
                exchange_instrument_id=member.exchange_instrument_id,
                now_ms=TRIGGER_HOUR_MS + 1,
            )
        if current is not None:
            armed = current
            break
    assert armed is not None
    windows[(armed.exchange_instrument_id, "15m")] = _trigger_window(
        armed_at_ms=TRIGGER_HOUR_MS,
        boundary=armed.breakout_boundary,
    )
    runtime_scope_id = (
        "scope:RSRVCB-LONG-15M:"
        f"{armed.exchange_instrument_id.split(':')[1]}:long"
    )
    observed = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        source,
        ObservationRequest(
            runtime_scope_id=runtime_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=TRIGGER_CLOSE_MS,
        ),
    )
    assert observed.status is ObservationStatus.SIGNAL_CREATED
    assert observed.signal_event_id is not None

    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        signal = await uow.signals.get(observed.signal_event_id)
    assert signal is not None
    assert signal.projection_run_id == projection.projection_run_id
    assert signal.armed_structure_id == armed.armed_structure_id
    reference_price = Decimal(
        str(
            next(
                fact.value
                for fact in signal.facts
                if fact.role == "protection_reference"
            )
        )
    )

    venue = CertifiedVenue()
    entry_facts = USEquityEntryFactsSource(
        reference_price=reference_price,
        position_side="long",
    )
    entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        venue,
        entry_facts,
        EntryWorkerRequest(
            worker_id="us-entry-worker-certification",
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            now_ms=ENTRY_TIME_MS,
            lease_until_ms=ENTRY_TIME_MS + 5_000,
            timeout_seconds=1,
            admission_snapshot_validity_ms=30_000,
        ),
    )
    assert entry.status is EntryWorkerStatus.DISPATCHED
    assert entry.ticket_id is not None

    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        ticket = await uow.tickets.get(entry.ticket_id)
    assert ticket is not None
    assert ticket.selected_leverage == 5
    assert ticket.session_code == "US_REGULAR"
    assert ticket.session_multiplier == Decimal("1")
    assert ticket.universe_version_id == universe.universe_version_id
    assert ticket.product_policy_version_id == "product-policy:us-equity:v1"
    assert ticket.exit_policy.event_spec_id == EVENT_SPEC_ID

    await _complete_lifecycle(
        six_event_engine,
        venue=venue,
        ticket=ticket,
        base_ms=ENTRY_TIME_MS,
    )


@pytest.mark.asyncio
async def test_effective_split_freezes_reprofiles_rewarms_and_reactivates(
    six_event_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    await _seed_complete_us_runtime(six_event_engine)
    windows = _market_windows(universe)
    source = WindowSource(windows)
    projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=TRIGGER_HOUR_MS,
        claim_owner="corporate-action-initial-projection",
    )
    await _warm_and_activate(
        six_event_engine,
        universe=universe,
        projection_run_id=projection.projection_run_id,
    )
    member = universe.candidate_members[-1]
    scope_id = f"scope:RSRVCB-LONG-15M:{member.venue_symbol}:long"
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        initial_armed = await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=EVENT_SPEC_ID,
            universe_version_id=universe.universe_version_id,
            projection_run_id=projection.projection_run_id,
            exchange_instrument_id=member.exchange_instrument_id,
            now_ms=TRIGGER_HOUR_MS + 1,
        )
    assert initial_armed is not None

    effective_at_ms = TRIGGER_HOUR_MS + 100
    split = CorporateEvent(
        corporate_event_version_id=f"event:{member.venue_symbol}:split:v1",
        exchange_instrument_id=member.exchange_instrument_id,
        event_kind=CorporateEventKind.SPLIT,
        certainty=CorporateEventCertainty.EXACT_TIME,
        event_date=datetime.fromtimestamp(
            effective_at_ms / 1_000,
            tz=timezone.utc,
        ).date(),
        effective_at_ms=effective_at_ms,
        status="active",
    )
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        frozen_scope_ids = await apply_corporate_event_authority(
            uow,
            ApplyCorporateEventAuthorityRequest(
                source_name="corporate-action-full-chain",
                coverage=CorporateEventCoverage(
                    coverage_id=f"coverage:{member.venue_symbol}:split:v1",
                    exchange_instrument_id=member.exchange_instrument_id,
                    coverage_start_ms=TRIGGER_HOUR_MS - 86_400_000,
                    coverage_end_ms=TRIGGER_HOUR_MS + 86_400_000,
                    coverage_status="complete",
                    valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                    coverage_digest=_digest(
                        f"coverage:{member.venue_symbol}:split:v1"
                    ),
                ),
                events=(split,),
                observed_at_ms=effective_at_ms + 1,
            ),
        )
    assert frozen_scope_ids == (scope_id,)
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        frozen_scope = await uow.signals.get_runtime_scope(scope_id)
        invalidated = await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=EVENT_SPEC_ID,
            universe_version_id=universe.universe_version_id,
            projection_run_id=projection.projection_run_id,
            exchange_instrument_id=member.exchange_instrument_id,
            now_ms=effective_at_ms + 2,
        )
    assert frozen_scope is not None
    assert frozen_scope.scope_state == "warming"
    assert frozen_scope.entry_enabled is False
    assert frozen_scope.scope_version == 2
    assert frozen_scope.reprofile_required_at_ms == effective_at_ms
    assert invalidated is None

    refreshed_at_ms = effective_at_ms + 1_000
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        await uow.product_admission.upsert_product_profile(
            ProductProfile(
                product_profile_id=(
                    f"product-profile:{member.venue_symbol}:v2"
                ),
                profile_version=2,
                exchange_instrument_id=member.exchange_instrument_id,
                venue_id="binance-usdm",
                contract_type="TRADIFI_PERPETUAL",
                underlying_type="EQUITY",
                margin_asset="USDT",
                product_status="TRADING",
                configured_leverage=5,
                margin_mode="cross",
                observed_at_ms=refreshed_at_ms,
                valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                semantic_digest=_digest(
                    f"profile:{member.venue_symbol}:v2"
                ),
            ),
            source_payload={"source": "post-split-exchange-info"},
            updated_at_ms=refreshed_at_ms,
        )
        brackets = _maintenance_brackets()
        rules = await uow.signals.upsert_instrument_rules(
            venue_id="binance-usdm",
            exchange_instrument_id=member.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal("5"),
            exchange_max_leverage=10,
            maintenance_margin_brackets=brackets,
            maintenance_margin_brackets_digest=canonical_digest(brackets),
            observed_at_ms=refreshed_at_ms,
            valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
        )
    assert rules.projection_version == 1

    rewarm_at_ms = TRIGGER_HOUR_MS + 4 * 3_600_000
    shifted_source = WindowSource(
        _shift_market_windows(
            _market_windows(universe),
            delta_ms=rewarm_at_ms - TRIGGER_HOUR_MS,
        )
    )
    reprofile_projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        shifted_source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=rewarm_at_ms,
        claim_owner="corporate-action-reprofile-projection",
    )
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        await mark_strategy_universe_warm_ready(
            uow,
            MarkStrategyUniverseWarmReadyRequest(
                runtime_scope_id=scope_id,
                universe_version_id=universe.universe_version_id,
                observation_fact_digest=_digest(
                    f"post-split-warm:{scope_id}"
                ),
                ready_at_ms=rewarm_at_ms,
            ),
        )
        await complete_corporate_action_reprofile(
            uow,
            CompleteCorporateActionReprofileRequest(
                runtime_scope_id=scope_id,
                universe_version_id=universe.universe_version_id,
                completed_at_ms=rewarm_at_ms + 1,
            ),
        )
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        active_scope = await uow.signals.get_runtime_scope(scope_id)
        authority = await uow.product_admission.load_current_authority(
            member.exchange_instrument_id
        )
        rearmed = await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=EVENT_SPEC_ID,
            universe_version_id=universe.universe_version_id,
            projection_run_id=reprofile_projection.projection_run_id,
            exchange_instrument_id=member.exchange_instrument_id,
            now_ms=rewarm_at_ms + 1,
        )
        context = await build_product_admission_context(
            uow,
            market_facts=ProductMarketFacts(
                exchange_instrument_id=member.exchange_instrument_id,
                best_bid=Decimal("99.9"),
                best_ask=Decimal("100"),
                mark_price=Decimal("100"),
                index_price=Decimal("100"),
                top5_bid_depth=Decimal("1000000"),
                top5_ask_depth=Decimal("1000000"),
                funding_rate=Decimal("0.0001"),
                funding_observed_at_ms=rewarm_at_ms - 1,
                observed_at_ms=rewarm_at_ms,
            ),
            action_time_ms=rewarm_at_ms,
        )
    assert active_scope is not None
    assert active_scope.scope_state == "active"
    assert active_scope.entry_enabled is True
    assert active_scope.reprofile_required_at_ms is None
    assert authority is not None and authority.profile.profile_version == 2
    assert rearmed is not None
    assert context is not None
    assert context.corporate_event_admission.allowed is True


async def _seed_complete_us_runtime(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="account-certification",
                runtime_commit="kernel-test-head",
                schema_revision="0002_strategy_universe_us_equity",
                seeded_at_ms=TRIGGER_HOUR_MS - 86_400_000,
            ),
        )
        await seed_us_market_calendar(
            uow,
            seeded_at_ms=TRIGGER_HOUR_MS - 86_400_000,
        )
        universe = universe_for_event_spec(EVENT_SPEC_ID)
        for index, member in enumerate(universe.candidate_members):
            digest = _digest(f"profile:{member.exchange_instrument_id}")
            await uow.product_admission.upsert_product_profile(
                ProductProfile(
                    product_profile_id=(
                        f"product-profile:{member.venue_symbol}:v1"
                    ),
                    exchange_instrument_id=member.exchange_instrument_id,
                    venue_id="binance-usdm",
                    contract_type="TRADIFI_PERPETUAL",
                    underlying_type="EQUITY",
                    margin_asset="USDT",
                    product_status="TRADING",
                    configured_leverage=5,
                    margin_mode="cross",
                    observed_at_ms=TRIGGER_HOUR_MS - 86_400_000,
                    valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                    semantic_digest=digest,
                ),
                source_payload={
                    "source": "full_chain_exchange_info",
                    "ordinal": index,
                },
                updated_at_ms=TRIGGER_HOUR_MS - 10_000,
            )
            coverage = CorporateEventCoverage(
                coverage_id=f"coverage:{member.venue_symbol}:v1",
                exchange_instrument_id=member.exchange_instrument_id,
                coverage_start_ms=TRIGGER_HOUR_MS - 86_400_000,
                coverage_end_ms=TRIGGER_HOUR_MS + 86_400_000,
                coverage_status="complete",
                valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                coverage_digest=_digest(
                    f"coverage:{member.exchange_instrument_id}"
                ),
            )
            await uow.product_admission.replace_corporate_event_authority(
                coverage=coverage,
                events=(),
                source_name="full_chain_corporate_provider",
                observed_at_ms=TRIGGER_HOUR_MS - 10_000,
            )
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current).values(
                new_entry_submit_enabled=True
            )
        )
        await connection.execute(
            sa.update(runtime_capabilities_current).values(enabled=True)
        )


async def _warm_and_activate(
    engine: AsyncEngine,
    *,
    universe,
    projection_run_id: str,
) -> None:
    del projection_run_id
    async with engine.connect() as connection:
        scope_ids = tuple(
            (
                await connection.execute(
                    sa.select(runtime_scopes_current.c.runtime_scope_id).where(
                        runtime_scopes_current.c.universe_version_id
                        == universe.universe_version_id
                    )
                )
            ).scalars()
        )
    assert len(scope_ids) == 13
    for runtime_scope_id in scope_ids:
        async with PostgresKernelUnitOfWork(engine) as uow:
            digest = await mark_strategy_universe_warm_ready(
                uow,
                MarkStrategyUniverseWarmReadyRequest(
                    runtime_scope_id=str(runtime_scope_id),
                    universe_version_id=universe.universe_version_id,
                    observation_fact_digest=_digest(
                        f"observation:{runtime_scope_id}"
                    ),
                    ready_at_ms=TRIGGER_HOUR_MS,
                ),
            )
        assert digest.startswith("sha256:")
    async with PostgresKernelUnitOfWork(engine) as uow:
        activation = await activate_strategy_universe(
            uow,
            ActivateStrategyUniverseRequest(
                event_spec_id=EVENT_SPEC_ID,
                universe_version_id=universe.universe_version_id,
                expected_current_universe_version_id=None,
                activated_at_ms=TRIGGER_HOUR_MS + 10,
            ),
        )
    assert activation.activated_scope_count == 13


def _market_windows(universe) -> dict[tuple[str, str], tuple]:
    start_1h = TRIGGER_HOUR_MS - 744 * 3_600_000
    as_of_4h = TRIGGER_HOUR_MS - TRIGGER_HOUR_MS % 14_400_000
    start_4h = as_of_4h - 200 * 14_400_000
    windows: dict[tuple[str, str], tuple] = {}
    for index, member in enumerate(universe.members):
        if member == universe.candidate_members[-1]:
            candles = _compressed_projection_candles(
                start_ms=start_1h,
                count=744,
            )
        else:
            slope = (
                Decimal(index + 2) / Decimal("1000")
                if member in universe.candidate_members
                else Decimal("0.0005")
            )
            candles = _candles(
                start_ms=start_1h,
                count=744,
                duration_ms=3_600_000,
                slope=slope,
            )
        windows[(member.exchange_instrument_id, "1h")] = candles
    for member in universe.reference_members:
        windows[(member.exchange_instrument_id, "4h")] = _candles(
            start_ms=start_4h,
            count=200,
            duration_ms=14_400_000,
            slope=Decimal("0.01"),
        )
    return windows


async def _complete_lifecycle(
    engine: AsyncEngine,
    *,
    venue: CertifiedVenue,
    ticket,
    base_ms: int,
) -> None:
    def uow_factory() -> PostgresKernelUnitOfWork:
        return PostgresKernelUnitOfWork(engine)

    position_source = CertifiedPositionSource()
    lifecycle_source = CertifiedLifecycleFactsSource()
    review_source = CertifiedReviewEconomicsSource()
    position_source.set_open(
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        position_side="long",
    )
    reconciliation = ReconciliationWorkerRequest(
        worker_id="us-reconciliation-certification",
        runtime_commit="kernel-test-head",
        schema_revision="0002_strategy_universe_us_equity",
        now_ms=base_ms + 1_000,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=1_000,
    )
    filled = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation,
    )
    assert filled.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    lifecycle = LifecycleWorkerRequest(
        worker_id="us-lifecycle-certification",
        runtime_commit="kernel-test-head",
        schema_revision="0002_strategy_universe_us_equity",
        now_ms=base_ms + 2_000,
        lease_until_ms=base_ms + 7_000,
        timeout_seconds=1,
        idle_poll_interval_ms=1_000,
    )
    assert (
        await run_lifecycle_worker_once(
            uow_factory,
            venue,
            lifecycle_source,
            lifecycle,
        )
    ).status is LifecycleWorkerStatus.DISPATCHED
    assert (
        await run_lifecycle_worker_once(
            uow_factory,
            venue,
            lifecycle_source,
            lifecycle.model_copy(
                update={
                    "now_ms": base_ms + 3_000,
                    "lease_until_ms": base_ms + 8_000,
                }
            ),
        )
    ).status is LifecycleWorkerStatus.DISPATCHED

    tp1_quantity = ticket.take_profit_quantities[0]
    lifecycle_source.facts = TicketLifecycleFacts(
        position_quantity=ticket.quantity - tp1_quantity,
        tp1_filled_quantity=tp1_quantity,
        tp1_average_fill_price=ticket.take_profit_prices[0],
        allocated_entry_fee_quote=Decimal("0.1"),
        exit_taker_fee_rate=Decimal("0.0005"),
        price_tick=Decimal("0.1"),
        market_facts=None,
        observed_at_ms=base_ms + 4_000,
    )
    for offset in (4_000, 5_000):
        assert (
            await run_lifecycle_worker_once(
                uow_factory,
                venue,
                lifecycle_source,
                lifecycle.model_copy(
                    update={
                        "now_ms": base_ms + offset,
                        "lease_until_ms": base_ms + offset + 5_000,
                    }
                ),
            )
        ).status is LifecycleWorkerStatus.DISPATCHED

    position_source.set_flat()
    assert (
        await run_reconciliation_worker_once(
            uow_factory,
            venue,
            position_source,
            reconciliation.model_copy(update={"now_ms": base_ms + 6_000}),
        )
    ).status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert (
        await run_lifecycle_worker_once(
            uow_factory,
            venue,
            lifecycle_source,
            lifecycle.model_copy(
                update={
                    "now_ms": base_ms + 7_000,
                    "lease_until_ms": base_ms + 12_000,
                }
            ),
        )
    ).status is LifecycleWorkerStatus.DISPATCHED
    for offset, expected in (
        (8_000, ReconciliationWorkerStatus.POSITION_RECONCILED),
        (9_000, ReconciliationWorkerStatus.SETTLED),
    ):
        assert (
            await run_reconciliation_worker_once(
                uow_factory,
                venue,
                position_source,
                reconciliation.model_copy(
                    update={"now_ms": base_ms + offset}
                ),
            )
        ).status is expected
    reviewed = await run_reconciliation_worker_once(
        uow_factory,
        venue,
        position_source,
        reconciliation.model_copy(update={"now_ms": base_ms + 10_000}),
        review_economics_source=review_source,
    )
    assert reviewed.status is ReconciliationWorkerStatus.REVIEWED
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TERMINAL
    assert aggregate.position_qty == 0
    assert review is not None
    assert review.metrics["event_spec_id"] == EVENT_SPEC_ID
    assert review.metrics["economics_completeness"] == "complete"
    assert reservation is not None and reservation.status == "released"
    assert incident is None


def _digest(value: str) -> str:
    return f"sha256:{sha256(value.encode()).hexdigest()}"


def _shift_market_windows(
    windows: dict[tuple[str, str], tuple],
    *,
    delta_ms: int,
) -> dict[tuple[str, str], tuple]:
    return {
        key: tuple(
            candle.model_copy(
                update={
                    "open_time_ms": candle.open_time_ms + delta_ms,
                    "close_time_ms": candle.close_time_ms + delta_ms,
                }
            )
            for candle in candles
        )
        for key, candles in windows.items()
    }
