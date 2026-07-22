"""Observe one runtime scope at closed-bar event time without holding network I/O in PG."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.ports import (
    RuntimeScopeSnapshot,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
    produce_strategy_signal,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.market import (
    ClosedCandle,
    ComparativeStrengthMember,
    ComparativeStrengthSnapshot,
    MarketSnapshot,
    Timeframe,
)
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)


class ObservationStatus(StrEnum):
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


class ObservationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ObservationStatus
    runtime_scope_id: str
    event_spec_id: str | None
    detector_reason: str
    signal_event_id: str | None
    current_fact_count: int


async def observe_strategy_scope(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    request: ObservationRequest,
) -> ObservationResult:
    async with uow_factory() as uow:
        scope = await uow.signals.get_runtime_scope(request.runtime_scope_id)
        if scope is None or not scope.enabled:
            return _invalid_observation(
                request,
                event_spec_id=None if scope is None else scope.event_spec_id,
                reason="scope_or_policy_mismatch",
            )
        event_spec = await uow.signals.get_event_spec(scope.event_spec_id)
        if event_spec is None or event_spec.status != "active":
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="registry_event_unavailable",
            )
        contract = _contract_for_scope(scope)
        if contract is None:
            return _invalid_observation(
                request,
                event_spec_id=scope.event_spec_id,
                reason="registry_scope_mismatch",
            )

    try:
        snapshot = await _load_market_snapshot(
            market_source,
            contract,
            scope,
            request.trigger_candle_close_time_ms,
        )
    except (RuntimeError, TimeoutError, ValueError):
        async with uow_factory() as uow:
            await uow.signals.save_readiness(
                runtime_scope_id=scope.runtime_scope_id,
                readiness_state="blocked",
                first_blocker="observation_unavailable",
                signal_event_id=None,
                fact_summary={"detector_reason": "market_snapshot_unavailable"},
                updated_at_ms=request.trigger_candle_close_time_ms,
            )
        return _invalid_observation(
            request,
            event_spec_id=contract.event_spec_id,
            reason="market_snapshot_unavailable",
        )

    detector_result = evaluate_strategy_snapshot(contract, snapshot)
    async with uow_factory() as uow:
        if detector_result.status is DetectorStatus.INVALID:
            await uow.signals.save_readiness(
                runtime_scope_id=scope.runtime_scope_id,
                readiness_state="blocked",
                first_blocker="observation_unavailable",
                signal_event_id=None,
                fact_summary={"detector_reason": detector_result.reason_code},
                updated_at_ms=request.trigger_candle_close_time_ms,
            )
            return ObservationResult(
                status=ObservationStatus.INVALID,
                runtime_scope_id=scope.runtime_scope_id,
                event_spec_id=contract.event_spec_id,
                detector_reason=detector_result.reason_code,
                signal_event_id=None,
                current_fact_count=0,
            )

        persisted_facts = await uow.signals.upsert_current_facts(
            runtime_scope_id=scope.runtime_scope_id,
            facts=detector_result.facts,
        )
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


def _contract_for_scope(
    scope: RuntimeScopeSnapshot,
) -> RegisteredStrategyContract | None:
    for contract in registered_strategy_contracts():
        if (
            contract.event_spec_id == scope.event_spec_id
            and contract.strategy_group_id == scope.strategy_group_id
            and contract.strategy_version_id == scope.strategy_version_id
            and contract.position_side == scope.position_side
            and scope.exchange_instrument_id
            in {
                item.exchange_instrument_id
                for item in contract.candidate_instruments
            }
        ):
            return contract
    return None


async def _load_market_snapshot(
    market_source: PublicMarketSource,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    trigger_ms: int,
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

    timeframes: tuple[Timeframe, ...]
    if contract.event_id in {"CPM-LONG", "MPG-LONG", "BRF2-SHORT"}:
        timeframes = ("1h", "4h")
    else:
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
    comparative = await _build_comparative_strength(
        market_source,
        contract,
        scope,
        trigger_ms,
        candidate_candles=windows.get("1h", ()),
    )
    return MarketSnapshot(
        exchange_instrument_id=scope.exchange_instrument_id,
        trigger_candle_close_time_ms=trigger_ms,
        candles_1h=windows.get("1h", ()),
        candles_4h=windows.get("4h", ()),
        comparative_strength=comparative,
    )


async def _build_comparative_strength(
    market_source: PublicMarketSource,
    contract: RegisteredStrategyContract,
    scope: RuntimeScopeSnapshot,
    trigger_ms: int,
    *,
    candidate_candles: tuple[ClosedCandle, ...],
) -> ComparativeStrengthSnapshot | None:
    if contract.event_id == "MPG-LONG":
        lookback_bars = 8
    elif contract.event_id == "MI-LONG":
        lookback_bars = 12
    else:
        return None

    async def load_member(instrument_id: str) -> tuple[str, Decimal] | None:
        candles = (
            candidate_candles
            if instrument_id == scope.exchange_instrument_id
            and len(candidate_candles) >= lookback_bars + 1
            else await _fetch(
                market_source,
                instrument_id,
                "1h",
                limit=lookback_bars + 1,
                trigger_ms=trigger_ms,
            )
        )
        sample = candles[-(lookback_bars + 1) :]
        if len(sample) < lookback_bars + 1:
            return None
        return_pct = (
            (sample[-1].close - sample[0].close) / sample[0].close
        ) * Decimal("100")
        return instrument_id, return_pct

    raw_members = await asyncio.gather(
        *(
            load_member(item.exchange_instrument_id)
            for item in contract.candidate_instruments
        )
    )
    if any(item is None for item in raw_members):
        return None
    ranked = sorted(
        (item for item in raw_members if item is not None),
        key=lambda item: (-item[1], item[0]),
    )
    members = tuple(
        ComparativeStrengthMember(
            exchange_instrument_id=instrument_id,
            return_pct=return_pct,
            rank=rank,
        )
        for rank, (instrument_id, return_pct) in enumerate(ranked, start=1)
    )
    return ComparativeStrengthSnapshot(
        strategy_group_id=contract.strategy_group_id,
        timeframe="1h",
        lookback_bars=lookback_bars,
        trigger_candle_close_time_ms=trigger_ms,
        members=members,
        observed_at_ms=trigger_ms,
        valid_until_ms=trigger_ms + contract.freshness_window_ms,
        source_ref=(
            f"public_closed_ohlcv:{contract.strategy_group_id}:"
            f"{trigger_ms}:comparative"
        ),
    )


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
