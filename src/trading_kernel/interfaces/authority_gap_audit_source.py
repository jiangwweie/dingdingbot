"""Production-shaped public-market evaluator for SOR Authority Gap Audits."""

from __future__ import annotations

import asyncio

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditDetectorDriftError,
    AuthorityGapAuditEvaluationRequest,
    AuthorityGapAuditSourceIntegrityError,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.orb_session_selection import (
    ORB_SELECTION_SPEC_ID,
    daily_entry_interval_ms,
    daily_event_spec_ids,
    daily_first_offset_ms,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapScope,
    AuthorityGapScopeResult,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

_SOR_EVENT_SPEC_IDS = frozenset({SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID})
_MAX_AUDIT_SCOPES = 40


class PublicMarketAuthorityGapAuditSource:
    """Replay exact SOR v4 first-trigger semantics from public closed bars."""

    def __init__(
        self,
        market_source: PublicMarketSource,
        *,
        max_concurrency: int = 6,
    ) -> None:
        if not 1 <= max_concurrency <= 24:
            raise ValueError("Authority Gap Audit concurrency must be between 1 and 24")
        self._market_source = market_source
        self._max_concurrency = max_concurrency

    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        scopes = tuple(
            sorted(
                request.scopes,
                key=lambda item: (item.event_spec_id, item.exchange_instrument_id),
            )
        )
        if not scopes or len(scopes) > _MAX_AUDIT_SCOPES:
            raise AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit scope count is outside bounds"
            )
        if len(scopes) != len(
            {(item.event_spec_id, item.exchange_instrument_id) for item in scopes}
        ):
            raise AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit scopes must be exact and unique"
            )
        event_ids = daily_event_spec_ids(request.audit.selection_spec_id)
        interval = daily_entry_interval_ms(request.audit.selection_spec_id)
        hourly = request.audit.selection_spec_id == ORB_SELECTION_SPEC_ID
        if any(item.event_spec_id not in event_ids for item in scopes):
            raise AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit scopes must match the exact Selection identity"
            )

        expected_bars = (
            request.audited_through_close_time_ms - request.audit.session_start_ms
        ) // interval
        if (
            request.audited_through_close_time_ms % interval != 0
            or not (1 if hourly else 5) <= expected_bars <= (23 if hourly else 96)
            or (
                request.audit.unauthorized_from_close_time_ms
                > request.audited_through_close_time_ms
                and not (
                    hourly
                    and expected_bars == 1
                    and request.audit.unauthorized_from_close_time_ms
                    == request.audit.session_start_ms + 2 * interval
                )
            )
        ):
            raise AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit window is not a bounded SOR session"
            )

        scopes_by_instrument: dict[str, list[AuthorityGapScope]] = {}
        for scope in scopes:
            scopes_by_instrument.setdefault(scope.exchange_instrument_id, []).append(
                scope
            )
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def evaluate_instrument(
            instrument_id: str,
            instrument_scopes: list[AuthorityGapScope],
        ) -> tuple[AuthorityGapScopeResult, ...]:
            async with semaphore:
                candles = await self._market_source.fetch_closed_candles(
                    ClosedCandleRequest(
                        exchange_instrument_id=instrument_id,
                        timeframe="1h" if hourly else "15m",
                        limit=expected_bars,
                        since_ms=request.audit.session_start_ms,
                        closed_at_ms=request.audited_through_close_time_ms,
                    )
                )
            _validate_session_path(
                candles,
                session_start_ms=request.audit.session_start_ms,
                expected_bars=expected_bars,
                interval_ms=interval,
            )
            return tuple(
                _evaluate_scope(
                    scope,
                    candles=candles,
                    session_start_ms=request.audit.session_start_ms,
                    unauthorized_from_close_time_ms=(
                        request.audit.unauthorized_from_close_time_ms
                    ),
                    selection_spec_id=request.audit.selection_spec_id,
                )
                for scope in instrument_scopes
            )

        groups = await asyncio.gather(
            *(
                evaluate_instrument(instrument_id, instrument_scopes)
                for instrument_id, instrument_scopes in sorted(
                    scopes_by_instrument.items()
                )
            )
        )
        return tuple(
            sorted(
                (item for group in groups for item in group),
                key=lambda item: (
                    item.scope.event_spec_id,
                    item.scope.exchange_instrument_id,
                ),
            )
        )


def _validate_session_path(
    candles: tuple[ClosedCandle, ...],
    *,
    session_start_ms: int,
    expected_bars: int,
    interval_ms: int = INTERVAL_MS,
) -> None:
    if len(candles) != expected_bars or any(
        candle.open_time_ms != session_start_ms + index * interval_ms
        or candle.close_time_ms != session_start_ms + (index + 1) * interval_ms
        for index, candle in enumerate(candles)
    ):
        raise AuthorityGapAuditSourceIntegrityError(
            "Authority Gap Audit requires a complete canonical "
            + ("15m" if interval_ms == INTERVAL_MS else "1h")
            + " path"
        )


def _evaluate_scope(
    scope: AuthorityGapScope,
    *,
    candles: tuple[ClosedCandle, ...],
    session_start_ms: int,
    unauthorized_from_close_time_ms: int,
    selection_spec_id: str = "sor-dynamic-selection-v0",
) -> AuthorityGapScopeResult:
    contract = strategy_contract_for(scope.event_spec_id)
    first_natural_trigger_at_ms: int | None = None
    interval = daily_entry_interval_ms(selection_spec_id)
    hourly = selection_spec_id == ORB_SELECTION_SPEC_ID
    for bar_count in range(
        daily_first_offset_ms(selection_spec_id) // interval, len(candles) + 1
    ):
        close_time_ms = session_start_ms + bar_count * interval
        detector_result = evaluate_strategy_snapshot(
            contract,
            MarketSnapshot(
                exchange_instrument_id=scope.exchange_instrument_id,
                trigger_candle_close_time_ms=close_time_ms,
                candles_15m=() if hourly else candles[:bar_count],
                candles_1h=candles[:bar_count] if hourly else (),
            ),
        )
        if detector_result.status is DetectorStatus.INVALID:
            raise AuthorityGapAuditDetectorDriftError(
                "Authority Gap Audit detector rejected canonical input"
            )
        if detector_result.status is DetectorStatus.TRIGGERED:
            if close_time_ms >= unauthorized_from_close_time_ms:
                first_natural_trigger_at_ms = close_time_ms
            break
    return AuthorityGapScopeResult(
        scope=scope,
        session_reference=str(session_start_ms),
        first_natural_trigger_at_ms=first_natural_trigger_at_ms,
    )
