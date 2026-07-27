from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.activate_strategy_universe import (
    ActivateStrategyUniverseRequest,
    activate_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    InstallStrategyUniverseRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.mark_strategy_universe_warm_ready import (
    MarkStrategyUniverseWarmReadyRequest,
    mark_strategy_universe_warm_ready,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.domain.corporate_events import CorporateEventCoverage
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.product_admission import ProductProfile
from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    UniverseMember,
    UniverseMemberRole,
    universe_for_event_spec,
)
from src.trading_kernel.infrastructure.pg_models import runtime_scopes_current
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    EntryWorkerStatus,
    run_entry_worker_once,
)
from tests.trading_kernel.full_chain.test_six_event_system_certification import (
    CertifiedVenue,
    six_event_engine,  # noqa: F401
)
from tests.trading_kernel.full_chain.test_us_equity_strategy_certification import (
    ENTRY_TIME_MS,
    EVENT_SPEC_ID,
    TRIGGER_CLOSE_MS,
    TRIGGER_HOUR_MS,
    USEquityEntryFactsSource,
    _complete_lifecycle,
    _digest,
    _market_windows,
    _seed_complete_us_runtime,
    _warm_and_activate,
)
from tests.trading_kernel.integration.test_rsr_vcb_observation import (
    WindowSource,
    _trigger_window,
)


AMD = "binance-usdm:AMDUSDT:perpetual"
REPLACEMENT_HOUR_MS = TRIGGER_HOUR_MS + 4 * 3_600_000
REPLACEMENT_CLOSE_MS = REPLACEMENT_HOUR_MS + 900_000


@pytest.mark.asyncio
async def test_warmed_universe_replaces_members_without_restarting_or_mutating_old_ticket(
    six_event_engine: AsyncEngine,  # noqa: F811
) -> None:
    initial = universe_for_event_spec(EVENT_SPEC_ID)
    await _seed_complete_us_runtime(six_event_engine)
    venue = CertifiedVenue()
    initial_windows = _market_windows(initial)
    initial_source = WindowSource(initial_windows)
    initial_projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        initial_source,
        universe_version_id=initial.universe_version_id,
        trigger_time_ms=TRIGGER_HOUR_MS,
        claim_owner="replacement-initial-projection",
    )
    await _warm_and_activate(
        six_event_engine,
        universe=initial,
        projection_run_id=initial_projection.projection_run_id,
    )
    old_armed = await _armed_for(
        six_event_engine,
        universe=initial,
        projection=initial_projection,
        instrument_id=initial.candidate_members[-1].exchange_instrument_id,
        at_ms=TRIGGER_HOUR_MS + 1,
    )
    initial_windows[(old_armed.exchange_instrument_id, "15m")] = _trigger_window(
        armed_at_ms=TRIGGER_HOUR_MS,
        boundary=old_armed.breakout_boundary,
    )
    old_scope_id = _initial_scope_id(old_armed.exchange_instrument_id)
    old_observation = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        initial_source,
        ObservationRequest(
            runtime_scope_id=old_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=TRIGGER_CLOSE_MS,
        ),
    )
    assert old_observation.status is ObservationStatus.SIGNAL_CREATED
    old_signal = await _signal(
        six_event_engine,
        old_observation.signal_event_id,
    )
    old_reference = _protection_reference(old_signal)
    old_entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        venue,
        USEquityEntryFactsSource(
            reference_price=old_reference * Decimal("1.04"),
            position_side="long",
        ),
        _entry_request(ENTRY_TIME_MS, "replacement-old-entry"),
    )
    assert old_entry.status is EntryWorkerStatus.DISPATCHED
    assert old_entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        old_ticket = await uow.tickets.get(old_entry.ticket_id)
    assert old_ticket is not None

    replacement = _replacement_universe(initial)
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        install_counts = await install_strategy_universe(
            uow,
            InstallStrategyUniverseRequest(
                universe=replacement,
                position_side="long",
                installed_at_ms=REPLACEMENT_HOUR_MS - 60_000,
            ),
        )
    assert install_counts.inserted_universe_version_count == 1
    await _seed_new_member_authority(six_event_engine)
    replacement_windows = _shift_windows(
        _market_windows(replacement),
        delta_ms=REPLACEMENT_HOUR_MS - TRIGGER_HOUR_MS,
    )
    replacement_source = WindowSource(replacement_windows)
    replacement_projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        replacement_source,
        universe_version_id=replacement.universe_version_id,
        trigger_time_ms=REPLACEMENT_HOUR_MS,
        claim_owner="replacement-v2-projection",
    )
    await _mark_all_warm(
        six_event_engine,
        universe=replacement,
        ready_at_ms=REPLACEMENT_HOUR_MS,
    )
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        activation = await activate_strategy_universe(
            uow,
            ActivateStrategyUniverseRequest(
                event_spec_id=EVENT_SPEC_ID,
                universe_version_id=replacement.universe_version_id,
                expected_current_universe_version_id=initial.universe_version_id,
                activated_at_ms=REPLACEMENT_HOUR_MS + 10,
            ),
        )
    assert activation.old_universe_version_id == initial.universe_version_id
    assert activation.new_universe_version_id == replacement.universe_version_id
    assert activation.activated_scope_count == 13

    await _assert_old_scope_cannot_reenter(
        six_event_engine,
        old_signal=old_signal,
        old_scope_id=old_scope_id,
        at_ms=REPLACEMENT_HOUR_MS + 20,
    )
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        frozen_old_ticket = await uow.tickets.get(old_ticket.identity.ticket_id)
    assert frozen_old_ticket == old_ticket
    await _complete_lifecycle(
        six_event_engine,
        venue=venue,
        ticket=old_ticket,
        base_ms=REPLACEMENT_HOUR_MS + 1_000,
    )

    new_armed = await _armed_for(
        six_event_engine,
        universe=replacement,
        projection=replacement_projection,
        instrument_id=AMD,
        at_ms=REPLACEMENT_HOUR_MS + 1,
    )
    replacement_windows[(AMD, "15m")] = _trigger_window(
        armed_at_ms=REPLACEMENT_HOUR_MS,
        boundary=new_armed.breakout_boundary,
    )
    new_scope_id = (
        "scope:RSRVCB-LONG-15M:v2:AMDUSDT:long"
    )
    new_observation = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        replacement_source,
        ObservationRequest(
            runtime_scope_id=new_scope_id,
            runtime_commit="kernel-test-head",
            schema_revision="0002_strategy_universe_us_equity",
            trigger_candle_close_time_ms=REPLACEMENT_CLOSE_MS,
        ),
    )
    assert new_observation.status is ObservationStatus.SIGNAL_CREATED
    new_signal = await _signal(
        six_event_engine,
        new_observation.signal_event_id,
    )
    new_entry = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(six_event_engine),
        venue,
        USEquityEntryFactsSource(
            reference_price=(
                _protection_reference(new_signal) * Decimal("1.04")
            ),
            position_side="long",
        ),
        _entry_request(
            REPLACEMENT_CLOSE_MS + 1_000,
            "replacement-new-entry",
        ),
    )
    assert new_entry.status is EntryWorkerStatus.DISPATCHED
    assert new_entry.ticket_id is not None
    async with PostgresKernelUnitOfWork(six_event_engine) as uow:
        new_ticket = await uow.tickets.get(new_entry.ticket_id)
    assert new_ticket is not None
    assert new_ticket.identity.netting_domain.exchange_instrument_id == AMD
    assert new_ticket.universe_version_id == replacement.universe_version_id
    assert new_ticket.universe_digest == replacement.semantic_digest()
    assert old_ticket.universe_version_id == initial.universe_version_id
    assert old_ticket.identity.netting_domain.exchange_instrument_id not in {
        member.exchange_instrument_id for member in replacement.candidate_members
    }


def _replacement_universe(
    initial: StrategyUniverseVersion,
) -> StrategyUniverseVersion:
    candidates = list(initial.candidate_members)
    removed = candidates[-1]
    candidates[-1] = UniverseMember(
        exchange_instrument_id=AMD,
        venue_symbol="AMDUSDT",
        role=UniverseMemberRole.CANDIDATE,
        priority_rank=removed.priority_rank,
    )
    return StrategyUniverseVersion(
        universe_version_id=f"universe:{EVENT_SPEC_ID}:v2",
        universe_version=2,
        strategy_group_id=initial.strategy_group_id,
        event_spec_id=initial.event_spec_id,
        event_id=initial.event_id,
        asset_class="us_equity",
        members=tuple(candidates) + initial.reference_members,
    )


async def _seed_new_member_authority(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.product_admission.upsert_product_profile(
            ProductProfile(
                product_profile_id="product-profile:AMDUSDT:v1",
                exchange_instrument_id=AMD,
                venue_id="binance-usdm",
                contract_type="TRADIFI_PERPETUAL",
                underlying_type="EQUITY",
                margin_asset="USDT",
                product_status="TRADING",
                configured_leverage=5,
                margin_mode="cross",
                observed_at_ms=TRIGGER_HOUR_MS,
                valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                semantic_digest=_digest("profile:AMDUSDT:v1"),
            ),
            source_payload={"source": "replacement-full-chain"},
            updated_at_ms=REPLACEMENT_HOUR_MS - 30_000,
        )
        await uow.product_admission.replace_corporate_event_authority(
            coverage=CorporateEventCoverage(
                coverage_id="coverage:AMDUSDT:v1",
                exchange_instrument_id=AMD,
                coverage_start_ms=TRIGGER_HOUR_MS - 86_400_000,
                coverage_end_ms=TRIGGER_HOUR_MS + 86_400_000,
                coverage_status="complete",
                valid_until_ms=TRIGGER_HOUR_MS + 86_400_000,
                coverage_digest=_digest("coverage:AMDUSDT:v1"),
            ),
            events=(),
            source_name="replacement-full-chain",
            observed_at_ms=REPLACEMENT_HOUR_MS - 30_000,
        )


async def _mark_all_warm(
    engine: AsyncEngine,
    *,
    universe: StrategyUniverseVersion,
    ready_at_ms: int,
) -> None:
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
    for scope_id in scope_ids:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await mark_strategy_universe_warm_ready(
                uow,
                MarkStrategyUniverseWarmReadyRequest(
                    runtime_scope_id=str(scope_id),
                    universe_version_id=universe.universe_version_id,
                    observation_fact_digest=_digest(
                        f"replacement-warm:{scope_id}"
                    ),
                    ready_at_ms=ready_at_ms,
                ),
            )


async def _assert_old_scope_cannot_reenter(
    engine: AsyncEngine,
    *,
    old_signal,
    old_scope_id: str,
    at_ms: int,
) -> None:
    stale_signal = old_signal.model_copy(
        update={
            "signal_event_id": "signal:retiring-scope-replay",
            "occurred_at_ms": at_ms,
            "observed_at_ms": at_ms,
            "expires_at_ms": at_ms + 60_000,
        }
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.signals.add(stale_signal) is True
        await uow.signals.save_readiness(
            runtime_scope_id=old_scope_id,
            readiness_state="candidate_ready",
            first_blocker=None,
            signal_event_id=stale_signal.signal_event_id,
            fact_summary={"source": "replacement-certification"},
            updated_at_ms=at_ms,
        )
        candidates = await uow.signals.list_ready_candidates(
            now_ms=at_ms,
            limit=64,
        )
    assert stale_signal.signal_event_id not in {
        candidate.signal.signal_event_id for candidate in candidates
    }
    async with engine.connect() as connection:
        old_scope = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id == old_scope_id
                )
            )
        ).mappings().one()
    assert old_scope["scope_state"] == "retiring"
    assert old_scope["entry_enabled"] is False


async def _armed_for(
    engine: AsyncEngine,
    *,
    universe: StrategyUniverseVersion,
    projection,
    instrument_id: str,
    at_ms: int,
):
    async with PostgresKernelUnitOfWork(engine) as uow:
        armed = await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=EVENT_SPEC_ID,
            universe_version_id=universe.universe_version_id,
            projection_run_id=projection.projection_run_id,
            exchange_instrument_id=instrument_id,
            now_ms=at_ms,
        )
    assert armed is not None
    return armed


async def _signal(engine: AsyncEngine, signal_event_id: str | None):
    assert signal_event_id is not None
    async with PostgresKernelUnitOfWork(engine) as uow:
        signal = await uow.signals.get(signal_event_id)
    assert signal is not None
    return signal


def _protection_reference(signal) -> Decimal:
    return Decimal(
        str(
            next(
                fact.value
                for fact in signal.facts
                if fact.role == "protection_reference"
            )
        )
    )


def _initial_scope_id(exchange_instrument_id: str) -> str:
    return (
        "scope:RSRVCB-LONG-15M:"
        f"{exchange_instrument_id.split(':')[1]}:long"
    )


def _entry_request(now_ms: int, worker_id: str) -> EntryWorkerRequest:
    return EntryWorkerRequest(
        worker_id=worker_id,
        runtime_commit="kernel-test-head",
        schema_revision="0002_strategy_universe_us_equity",
        now_ms=now_ms,
        lease_until_ms=now_ms + 5_000,
        timeout_seconds=1,
        admission_snapshot_validity_ms=30_000,
    )


def _shift_windows(
    windows: dict[tuple[str, str], tuple[ClosedCandle, ...]],
    *,
    delta_ms: int,
) -> dict[tuple[str, str], tuple[ClosedCandle, ...]]:
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
