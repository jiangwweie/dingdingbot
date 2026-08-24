"""Observe one runtime scope at closed-bar event time without holding network I/O in PG."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
    resolve_selection_entry_authority,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    RuntimeScopeSnapshot,
    UnitOfWorkFactory,
    WarmReadiness,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeProjectionAuthorityChanged,
    ComparativeProjectionFailure,
    ComparativeUniverseProjection,
    build_comparative_projection_failure,
    comparative_member_set_digest,
    project_comparative_universe,
    serialize_comparative_projection,
)
from src.trading_kernel.application.project_shadow_outcome import (
    pending_shadow_spec_for_strategy_observation,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    advance_exposure_episode,
    build_episode_domain_key,
)
from src.trading_kernel.domain.market import (
    ClosedCandle,
    MarketSnapshot,
    Timeframe,
)
from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)


class ObservationStatus(StrEnum):
    WARMED = "warmed"
    SIGNAL_CREATED = "signal_created"
    DUPLICATE_SIGNAL = "duplicate_signal"
    NO_SIGNAL = "no_signal"
    INVALID = "invalid"


class ObservationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    runtime_commit: str
    schema_revision: str
    trigger_candle_close_time_ms: int
    observation_generation: int | None = None
    attempted_at_ms: int | None = None

    @field_validator(
        "runtime_scope_id",
        "runtime_commit",
        "schema_revision",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("observation identities must be non-blank")
        return normalized

    @field_validator("trigger_candle_close_time_ms")
    @classmethod
    def _require_positive_trigger(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("observation trigger must be positive")
        return value

    @field_validator("observation_generation", "attempted_at_ms")
    @classmethod
    def _require_positive_optional_time(
        cls,
        value: int | None,
    ) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("optional observation values must be positive")
        return value


class ObservationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ObservationStatus
    runtime_scope_id: str
    event_spec_id: str | None
    detector_reason: str
    signal_event_id: str | None
    current_fact_count: int


def build_warm_readiness(
    *,
    scope: RuntimeScopeSnapshot,
    facts: tuple[SignalFactSnapshot, ...],
    expected_fact_definition_ids: tuple[str, ...],
    warm_closed_bar_time_ms: int,
    warm_completed_at_ms: int,
) -> WarmReadiness:
    """Bind one complete, fresh typed Fact bundle to one Warming scope."""

    if (
        scope.lifecycle_state != "warming"
        or not scope.observation_enabled
        or scope.entry_enabled
    ):
        raise ValueError("warm readiness requires a warming-only scope")
    if warm_closed_bar_time_ms <= 0 or warm_completed_at_ms <= 0:
        raise ValueError("warm readiness times must be positive")
    if warm_completed_at_ms < warm_closed_bar_time_ms:
        raise ValueError("warm readiness cannot complete before its market bar")
    expected = tuple(sorted(expected_fact_definition_ids))
    actual = tuple(sorted(item.fact_definition_id for item in facts))
    if (
        not expected
        or len(expected) != len(set(expected))
        or actual != expected
        or len(actual) != len(set(actual))
    ):
        raise ValueError("warm readiness requires the exact Registry Fact set")
    if any(
        fact.observed_at_ms != warm_closed_bar_time_ms
        or fact.valid_until_ms <= warm_completed_at_ms
        for fact in facts
    ):
        raise ValueError("warm readiness facts are stale or future-dated")

    fact_digest = build_signal_fact_digest(facts)
    valid_until_ms = min(item.valid_until_ms for item in facts)
    readiness_digest = WarmReadiness.digest_for(
        runtime_scope_id=scope.runtime_scope_id,
        scope_version=scope.scope_version,
        observation_generation=scope.observation_generation,
        event_spec_id=scope.event_spec_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        universe_version_id=scope.universe_version_id,
        universe_semantic_digest=scope.universe_semantic_digest,
        fact_digest=fact_digest,
        warm_closed_bar_time_ms=warm_closed_bar_time_ms,
        warm_valid_until_ms=valid_until_ms,
    )
    return WarmReadiness(
        runtime_scope_id=scope.runtime_scope_id,
        scope_version=scope.scope_version,
        observation_generation=scope.observation_generation,
        event_spec_id=scope.event_spec_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        universe_version_id=scope.universe_version_id,
        universe_semantic_digest=scope.universe_semantic_digest,
        fact_digest=fact_digest,
        warm_closed_bar_time_ms=warm_closed_bar_time_ms,
        warm_completed_at_ms=warm_completed_at_ms,
        warm_valid_until_ms=valid_until_ms,
        readiness_digest=readiness_digest,
    )


async def observe_strategy_scope(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    request: ObservationRequest,
) -> ObservationResult:
    attempted_at_ms = (
        request.attempted_at_ms
        or request.trigger_candle_close_time_ms
    )
    async with uow_factory() as uow:
        if request.observation_generation is None:
            scope = await uow.signals.claim_observation_generation(
                request.runtime_scope_id
            )
        else:
            scope = await uow.signals.get_runtime_scope(
                request.runtime_scope_id
            )
        if scope is None:
            return _invalid_observation(
                request,
                event_spec_id=None,
                reason="scope_or_policy_mismatch",
            )
        if (
            request.observation_generation is not None
            and scope.observation_generation
            != request.observation_generation
        ):
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="scope_or_policy_mismatch",
            )
        projection_updated_at_ms = (
            attempted_at_ms
            if scope.lifecycle_state == "warming"
            else request.trigger_candle_close_time_ms
        )
        if not _scope_observation_permissions_are_valid(scope):
            if scope.lifecycle_state == "warming":
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="scope_or_policy_mismatch",
                    detector_reason="scope_or_policy_mismatch",
                    updated_at_ms=projection_updated_at_ms,
                )
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="scope_or_policy_mismatch",
            )
        event_spec = await uow.signals.get_event_spec(scope.event_spec_id)
        if event_spec is None or event_spec.status != "active":
            if scope.lifecycle_state == "warming":
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="registry_event_unavailable",
                    detector_reason="registry_event_unavailable",
                    updated_at_ms=projection_updated_at_ms,
                )
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="registry_event_unavailable",
            )
        try:
            observation_universe = (
                await uow.signals.get_observation_universe_members(
                    event_spec_id=scope.event_spec_id,
                    universe_version_id=scope.universe_version_id,
                )
            )
        except (RuntimeError, ValueError):
            await _save_observation_blocker(
                uow,
                scope=scope,
                blocker="universe_identity_inconsistent",
                detector_reason="universe_identity_inconsistent",
                updated_at_ms=projection_updated_at_ms,
            )
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="scope_or_policy_mismatch",
            )
        if (
            observation_universe is None
            or observation_universe.universe_version_id
            != scope.universe_version_id
            or observation_universe.semantic_digest
            != scope.universe_semantic_digest
            or observation_universe.lifecycle_state != scope.lifecycle_state
            or scope.exchange_instrument_id
            not in observation_universe.exchange_instrument_ids
        ):
            await _save_observation_blocker(
                uow,
                scope=scope,
                blocker="universe_identity_inconsistent",
                detector_reason="universe_identity_inconsistent",
                updated_at_ms=projection_updated_at_ms,
            )
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="scope_or_policy_mismatch",
            )
        contract = _contract_for_scope(scope)
        if contract is None:
            if scope.lifecycle_state == "warming":
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="registry_scope_mismatch",
                    detector_reason="registry_scope_mismatch",
                    updated_at_ms=projection_updated_at_ms,
                )
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="registry_scope_mismatch",
            )
        selection_authority_id = None
        if scope.lifecycle_state == "active":
            selection = await resolve_selection_entry_authority(
                uow,
                runtime_scope=scope,
                birth_selection_authority_id=None,
                observed_close_time_ms=request.trigger_candle_close_time_ms,
                now_ms=attempted_at_ms,
                allow_current_as_birth=True,
            )
            if not selection.allowed:
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker=selection.reason_code,
                    detector_reason=selection.reason_code,
                    updated_at_ms=projection_updated_at_ms,
                )
                return _invalid_observation(
                    request,
                    event_spec_id=scope.event_spec_id,
                    reason=selection.reason_code,
                )
            selection_authority_id = selection.selection_authority_id
        product_session: ProductSessionSnapshot | None = None
        comparative_lookback_bars = _comparative_lookback_bars(contract)
        comparative_projection: ComparativeUniverseProjection | None = None
        comparative_digest = None
        if comparative_lookback_bars is not None:
            try:
                comparative_digest = comparative_member_set_digest(
                    observation_universe.exchange_instrument_ids
                )
                comparative_outcome = (
                    await uow.strategy_universes.get_comparative_projection(
                        event_spec_id=scope.event_spec_id,
                        universe_version_id=scope.universe_version_id,
                        closed_bar_time_ms=(
                            request.trigger_candle_close_time_ms
                        ),
                        member_set_digest=comparative_digest,
                    )
                )
                if isinstance(
                    comparative_outcome,
                    ComparativeProjectionFailure,
                ):
                    if comparative_outcome.is_active(
                        attempted_at_ms=attempted_at_ms
                    ):
                        await _save_observation_blocker(
                            uow,
                            scope=scope,
                            blocker="observation_unavailable",
                            detector_reason="market_snapshot_unavailable",
                            updated_at_ms=projection_updated_at_ms,
                        )
                        return _invalid_observation(
                            request,
                            event_spec_id=scope.event_spec_id,
                            reason="market_snapshot_unavailable",
                        )
                else:
                    comparative_projection = comparative_outcome
            except (RuntimeError, ValueError):
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="comparative_projection_invalid",
                    detector_reason="comparative_projection_invalid",
                    updated_at_ms=projection_updated_at_ms,
                )
                return _invalid_observation(
                    request,
                    event_spec_id=scope.event_spec_id,
                    reason="comparative_projection_invalid",
                )

    try:
        if contract.strategy_group_id == "SOR-US-EQ-PERP-001":
            product_snapshots = await market_source.fetch_product_sessions(
                observation_universe.exchange_instrument_ids,
                observed_at_ms=request.trigger_candle_close_time_ms,
            )
            if tuple(
                item.exchange_instrument_id for item in product_snapshots
            ) != observation_universe.exchange_instrument_ids:
                raise ValueError("product snapshot identities changed")
            product_session = next(
                (
                    item
                    for item in product_snapshots
                    if item.exchange_instrument_id == scope.exchange_instrument_id
                ),
                None,
            )
            if product_session is None:
                raise ValueError("scope Product snapshot is unavailable")
            async with uow_factory() as uow:
                await uow.signals.upsert_product_sessions(product_snapshots)
        if (
            comparative_lookback_bars is not None
            and comparative_projection is None
            and comparative_digest is not None
        ):
            comparative_projection = (
                await _get_or_create_comparative_projection(
                    uow_factory,
                    market_source,
                    contract=contract,
                    scope=scope,
                    trigger_ms=request.trigger_candle_close_time_ms,
                    universe_member_ids=(
                        observation_universe.exchange_instrument_ids
                    ),
                    member_set_digest=comparative_digest,
                    lookback_bars=comparative_lookback_bars,
                    attempted_at_ms=attempted_at_ms,
                )
            )
        snapshot = await _load_market_snapshot(
            market_source,
            contract,
            scope,
            request.trigger_candle_close_time_ms,
            observation_universe.exchange_instrument_ids,
            comparative_projection=comparative_projection,
            product_session=product_session,
        )
    except ComparativeProjectionAuthorityChanged:
        async with uow_factory() as uow:
            await _save_observation_blocker(
                uow,
                scope=scope,
                blocker="comparative_projection_invalid",
                detector_reason="comparative_projection_invalid",
                updated_at_ms=projection_updated_at_ms,
            )
        return _invalid_observation(
            request,
            event_spec_id=contract.event_spec_id,
            reason="comparative_projection_invalid",
        )
    except (RuntimeError, TimeoutError, ValueError):
        async with uow_factory() as uow:
            await _save_observation_blocker(
                uow,
                scope=scope,
                blocker="observation_unavailable",
                detector_reason="market_snapshot_unavailable",
                updated_at_ms=projection_updated_at_ms,
            )
        return _invalid_observation(
            request,
            event_spec_id=contract.event_spec_id,
            reason="market_snapshot_unavailable",
        )

    if scope.lifecycle_state != "warming":
        detector_result = evaluate_strategy_snapshot(contract, snapshot)
    else:
        try:
            detector_result = evaluate_strategy_snapshot(contract, snapshot)
        except (RuntimeError, ValueError):
            async with uow_factory() as uow:
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="warm_facts_invalid",
                    detector_reason="warm_facts_invalid",
                    updated_at_ms=projection_updated_at_ms,
                )
            return _invalid_observation(
                request,
                event_spec_id=contract.event_spec_id,
                reason="warm_facts_invalid",
            )
    async with uow_factory() as uow:
        if detector_result.status is DetectorStatus.INVALID:
            await _save_observation_blocker(
                uow,
                scope=scope,
                blocker="observation_unavailable",
                detector_reason=detector_result.reason_code,
                updated_at_ms=projection_updated_at_ms,
            )
            return ObservationResult(
                status=ObservationStatus.INVALID,
                runtime_scope_id=scope.runtime_scope_id,
                event_spec_id=contract.event_spec_id,
                detector_reason=detector_result.reason_code,
                signal_event_id=None,
                current_fact_count=0,
            )

        current_episode = None
        if (
            scope.lifecycle_state == "active"
            and contract.episode_policy == "rising_edge"
        ):
            episode_domain_key = build_episode_domain_key(
                event_spec_id=contract.event_spec_id,
                exchange_instrument_id=scope.exchange_instrument_id,
                position_side=contract.position_side,
            )
            current_episode = await uow.signals.lock_exposure_episode(
                episode_domain_key
            )
        persisted_facts = await uow.signals.upsert_current_facts(
            runtime_scope_id=scope.runtime_scope_id,
            facts=detector_result.facts,
        )
        if scope.lifecycle_state == "warming":
            expected_fact_ids = tuple(
                item.fact_definition_id
                for item in (*contract.required_facts, *contract.disable_facts)
            )
            try:
                warm_readiness = build_warm_readiness(
                    scope=scope,
                    facts=persisted_facts,
                    expected_fact_definition_ids=expected_fact_ids,
                    warm_closed_bar_time_ms=request.trigger_candle_close_time_ms,
                    warm_completed_at_ms=attempted_at_ms,
                )
            except ValueError:
                await _save_observation_blocker(
                    uow,
                    scope=scope,
                    blocker="warm_facts_invalid",
                    detector_reason="warm_facts_invalid",
                    updated_at_ms=projection_updated_at_ms,
                )
                return _invalid_observation(
                    request,
                    event_spec_id=contract.event_spec_id,
                    reason="warm_facts_invalid",
                )
            await uow.signals.save_warm_readiness(warm_readiness)
            return ObservationResult(
                status=ObservationStatus.WARMED,
                runtime_scope_id=scope.runtime_scope_id,
                event_spec_id=contract.event_spec_id,
                detector_reason=detector_result.reason_code,
                signal_event_id=None,
                current_fact_count=len(persisted_facts),
            )
        exposure_episode_id = None
        if contract.episode_policy == "rising_edge":
            episode_transition = advance_exposure_episode(
                contract=contract,
                current=current_episode,
                detector_status=detector_result.status,
                occurred_at_ms=(
                    detector_result.occurred_at_ms
                    if detector_result.status is DetectorStatus.TRIGGERED
                    else None
                ),
                observed_at_ms=request.trigger_candle_close_time_ms,
                exchange_instrument_id=scope.exchange_instrument_id,
            )
            if episode_transition.current is not current_episode:
                await uow.signals.save_exposure_episode(
                    episode_transition.current,
                    expected_version=(
                        0
                        if current_episode is None
                        else current_episode.projection_version
                    ),
                )
            exposure_episode_id = episode_transition.exposure_episode_id
        if detector_result.status is DetectorStatus.NOT_TRIGGERED:
            await uow.signals.save_readiness(
                runtime_scope_id=scope.runtime_scope_id,
                readiness_state="signal_absent",
                first_blocker="signal_absent",
                signal_event_id=None,
                fact_summary={
                    "detector_reason": detector_result.reason_code,
                    "fact_count": len(persisted_facts),
                },
                updated_at_ms=request.trigger_candle_close_time_ms,
            )
            return ObservationResult(
                status=ObservationStatus.NO_SIGNAL,
                runtime_scope_id=scope.runtime_scope_id,
                event_spec_id=contract.event_spec_id,
                detector_reason=detector_result.reason_code,
                signal_event_id=None,
                current_fact_count=len(persisted_facts),
            )

        signal = produce_strategy_signal(
            contract=contract,
            scope=scope,
            detector_result=detector_result,
            persisted_facts=persisted_facts,
            exposure_episode_id=exposure_episode_id,
            selection_authority_id=selection_authority_id,
        )
        ingest_result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit=request.runtime_commit,
                schema_revision=request.schema_revision,
                now_ms=request.trigger_candle_close_time_ms,
            ),
        )
        if (
            ingest_result.status
            in {
                IngestSignalStatus.CANDIDATE_READY,
                IngestSignalStatus.DUPLICATE_SIGNAL,
            }
            and contract.strategy_group_id == "SOR-US-EQ-PERP-001"
        ):
            if product_session is None:
                raise RuntimeError("TradFi Signal lacks its Product snapshot")
            shadow = pending_shadow_spec_for_strategy_observation(
                signal=signal,
                product=product_session,
            )
            if shadow is None:
                raise RuntimeError("TradFi Signal cannot freeze Observation Outcome")
            await uow.shadow_outcomes.add_pending(shadow)
        if ingest_result.status is IngestSignalStatus.CANDIDATE_READY:
            status = ObservationStatus.SIGNAL_CREATED
        elif ingest_result.status is IngestSignalStatus.DUPLICATE_SIGNAL:
            status = ObservationStatus.DUPLICATE_SIGNAL
        else:
            await uow.signals.save_readiness(
                runtime_scope_id=scope.runtime_scope_id,
                readiness_state="blocked",
                first_blocker=ingest_result.status.value,
                signal_event_id=signal.signal_event_id,
                fact_summary={
                    "detector_reason": detector_result.reason_code,
                    "fact_count": len(persisted_facts),
                },
                updated_at_ms=request.trigger_candle_close_time_ms,
            )
            status = ObservationStatus.INVALID
        return ObservationResult(
            status=status,
            runtime_scope_id=scope.runtime_scope_id,
            event_spec_id=contract.event_spec_id,
            detector_reason=detector_result.reason_code,
            signal_event_id=signal.signal_event_id,
            current_fact_count=len(persisted_facts),
        )


def _scope_observation_permissions_are_valid(
    scope: RuntimeScopeSnapshot,
) -> bool:
    return (
        scope.lifecycle_state == "warming"
        and scope.observation_enabled
        and not scope.entry_enabled
    ) or (
        scope.lifecycle_state == "active"
        and scope.observation_enabled
        and scope.entry_enabled
    )


async def _save_observation_blocker(
    uow: KernelUnitOfWork,
    *,
    scope: RuntimeScopeSnapshot,
    blocker: str,
    detector_reason: str,
    updated_at_ms: int,
) -> None:
    if scope.lifecycle_state == "warming":
        await uow.signals.clear_warm_readiness(
            runtime_scope_id=scope.runtime_scope_id,
            scope_version=scope.scope_version,
            observation_generation=scope.observation_generation,
            event_spec_id=scope.event_spec_id,
            exchange_instrument_id=scope.exchange_instrument_id,
            universe_version_id=scope.universe_version_id,
            universe_semantic_digest=scope.universe_semantic_digest,
            blocker=blocker,
            updated_at_ms=updated_at_ms,
        )
        return
    await uow.signals.save_readiness(
        runtime_scope_id=scope.runtime_scope_id,
        readiness_state="blocked",
        first_blocker=blocker,
        signal_event_id=None,
        fact_summary={"detector_reason": detector_reason},
        updated_at_ms=updated_at_ms,
    )


def _contract_for_scope(
    scope: RuntimeScopeSnapshot,
) -> RegisteredStrategyContract | None:
    for contract in registered_strategy_contracts():
        if (
            contract.event_spec_id == scope.event_spec_id
            and contract.strategy_group_id == scope.strategy_group_id
            and contract.strategy_version_id == scope.strategy_version_id
            and contract.position_side == scope.position_side
        ):
            return contract
    return None


async def _load_market_snapshot(
    market_source: PublicMarketSource,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    trigger_ms: int,
    universe_member_ids: tuple[str, ...],
    *,
    comparative_projection: ComparativeUniverseProjection | None,
    product_session: ProductSessionSnapshot | None,
) -> MarketSnapshot:
    if contract.event_id in {"SOR-LONG", "SOR-SHORT"}:
        raw = await _fetch(
            market_source,
            scope.exchange_instrument_id,
            "15m",
            limit=120,
            trigger_ms=trigger_ms,
        )
        session_start_ms = (trigger_ms // 86_400_000) * 86_400_000
        return MarketSnapshot(
            exchange_instrument_id=scope.exchange_instrument_id,
            trigger_candle_close_time_ms=trigger_ms,
            candles_15m=tuple(
                item for item in raw if item.open_time_ms >= session_start_ms
            ),
        )
    if contract.event_id in {"SOR-US-LONG-15M", "SOR-US-SHORT-15M"}:
        raw = await _fetch(
            market_source,
            scope.exchange_instrument_id,
            "15m",
            limit=120,
            trigger_ms=trigger_ms,
        )
        return MarketSnapshot(
            exchange_instrument_id=scope.exchange_instrument_id,
            trigger_candle_close_time_ms=trigger_ms,
            candles_15m=raw,
            product_session=product_session,
        )

    comparative_lookback_bars = _comparative_lookback_bars(contract)
    if comparative_lookback_bars is not None:
        if comparative_projection is None:
            raise ValueError("comparative projection is unavailable")
        expected_digest = comparative_member_set_digest(
            universe_member_ids
        )
        if (
            comparative_projection.event_spec_id != scope.event_spec_id
            or comparative_projection.universe_version_id
            != scope.universe_version_id
            or comparative_projection.closed_bar_time_ms != trigger_ms
            or comparative_projection.member_set_digest != expected_digest
        ):
            raise ValueError("comparative projection identity mismatch")
        candidate_candles = comparative_projection.candles_for(
            scope.exchange_instrument_id
        )
        timeframes: tuple[Timeframe, ...] = (
            ("4h",) if contract.event_id == "MPG-LONG" else ()
        )
    elif contract.event_id in {"CPM-LONG", "BRF2-SHORT"}:
        candidate_candles = ()
        timeframes = ("1h", "4h")
    else:
        candidate_candles = ()
        timeframes = ("1h",)
    fetched = await asyncio.gather(
        *(
            _fetch(
                market_source,
                scope.exchange_instrument_id,
                timeframe,
                limit=25,
                trigger_ms=trigger_ms,
            )
            for timeframe in timeframes
        )
    )
    windows = dict(zip(timeframes, fetched, strict=True))
    return MarketSnapshot(
        exchange_instrument_id=scope.exchange_instrument_id,
        trigger_candle_close_time_ms=trigger_ms,
        candles_1h=(
            candidate_candles
            if comparative_projection is not None
            else windows.get("1h", ())
        ),
        candles_4h=windows.get("4h", ()),
        comparative_strength=(
            None
            if comparative_projection is None
            else comparative_projection.comparative_strength
        ),
    )


async def _get_or_create_comparative_projection(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    *,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    trigger_ms: int,
    universe_member_ids: tuple[str, ...],
    member_set_digest: str,
    lookback_bars: int,
    attempted_at_ms: int,
) -> ComparativeUniverseProjection:
    async with serialize_comparative_projection(
        event_spec_id=scope.event_spec_id,
        universe_version_id=scope.universe_version_id,
        closed_bar_time_ms=trigger_ms,
        member_set_digest=member_set_digest,
    ):
        async with uow_factory() as uow:
            persisted = (
                await uow.strategy_universes.get_comparative_projection(
                    event_spec_id=scope.event_spec_id,
                    universe_version_id=scope.universe_version_id,
                    closed_bar_time_ms=trigger_ms,
                    member_set_digest=member_set_digest,
                )
            )
        if isinstance(persisted, ComparativeUniverseProjection):
            return persisted
        if (
            isinstance(persisted, ComparativeProjectionFailure)
            and persisted.is_active(attempted_at_ms=attempted_at_ms)
        ):
            raise RuntimeError("comparative projection unavailable")

        try:
            projected = await project_comparative_universe(
                market_source,
                event_spec_id=scope.event_spec_id,
                universe_version_id=scope.universe_version_id,
                strategy_group_id=contract.strategy_group_id,
                exchange_instrument_ids=universe_member_ids,
                closed_bar_time_ms=trigger_ms,
                lookback_bars=lookback_bars,
                freshness_window_ms=contract.freshness_window_ms,
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            failure = build_comparative_projection_failure(
                event_spec_id=scope.event_spec_id,
                universe_version_id=scope.universe_version_id,
                member_set_digest=member_set_digest,
                closed_bar_time_ms=trigger_ms,
                observed_at_ms=attempted_at_ms,
                reason_code=(
                    "comparative_projection_incomplete"
                    if isinstance(exc, ValueError)
                    else "comparative_market_temporarily_unavailable"
                ),
            )
            async with uow_factory() as uow:
                persisted_failure = (
                    await uow.strategy_universes
                    .save_comparative_projection_failure(failure)
                )
            if isinstance(
                persisted_failure,
                ComparativeUniverseProjection,
            ):
                return persisted_failure
            raise RuntimeError("comparative projection unavailable") from exc
        async with uow_factory() as uow:
            return await uow.strategy_universes.save_comparative_projection(
                projected
            )


def _comparative_lookback_bars(
    contract: RegisteredStrategyContract,
) -> int | None:
    if contract.event_id == "MPG-LONG":
        return 8
    if contract.event_id == "MI-LONG":
        return 12
    return None


async def _fetch(
    market_source: PublicMarketSource,
    exchange_instrument_id: str,
    timeframe: Timeframe,
    *,
    limit: int,
    trigger_ms: int,
) -> tuple[ClosedCandle, ...]:
    candles = await market_source.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id=exchange_instrument_id,
            timeframe=timeframe,
            limit=limit,
            closed_at_ms=trigger_ms,
        )
    )
    return tuple(
        item
        for item in candles
        if item.close_time_ms <= trigger_ms
    )[-limit:]


def _invalid_observation(
    request: ObservationRequest,
    *,
    event_spec_id: str | None,
    reason: str,
) -> ObservationResult:
    return ObservationResult(
        status=ObservationStatus.INVALID,
        runtime_scope_id=request.runtime_scope_id,
        event_spec_id=event_spec_id,
        detector_reason=reason,
        signal_event_id=None,
        current_fact_count=0,
    )
