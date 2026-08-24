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
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapScope,
    AuthorityGapScopeResult,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

_SOR_EVENT_SPEC_IDS = frozenset(
    {SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID}
)
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
        if any(item.event_spec_id not in _SOR_EVENT_SPEC_IDS for item in scopes):
            raise AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit supports only certified SOR v4 scopes"
            )

        expected_bars = (
            request.audited_through_close_time_ms - request.audit.session_start_ms
        ) // INTERVAL_MS
        if (
            request.audited_through_close_time_ms % INTERVAL_MS != 0
            or not 5 <= expected_bars <= 96
            or request.audit.unauthorized_from_close_time_ms
            > request.audited_through_close_time_ms
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
                        timeframe="15m",
                        limit=expected_bars,
                        since_ms=request.audit.session_start_ms,
                        closed_at_ms=request.audited_through_close_time_ms,
                    )
                )
            _validate_session_path(
                candles,
                session_start_ms=request.audit.session_start_ms,
                expected_bars=expected_bars,
            )
            return tuple(
                _evaluate_scope(
                    scope,
                    candles=candles,
                    session_start_ms=request.audit.session_start_ms,
                    unauthorized_from_close_time_ms=(
                        request.audit.unauthorized_from_close_time_ms
                    ),
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
) -> None:
    if len(candles) != expected_bars or any(
        candle.open_time_ms != session_start_ms + index * INTERVAL_MS
        or candle.close_time_ms != session_start_ms + (index + 1) * INTERVAL_MS
        for index, candle in enumerate(candles)
    ):
        raise AuthorityGapAuditSourceIntegrityError(
            "Authority Gap Audit requires a complete canonical 15m path"
        )


def _evaluate_scope(
    scope: AuthorityGapScope,
    *,
    candles: tuple[ClosedCandle, ...],
    session_start_ms: int,
    unauthorized_from_close_time_ms: int,
) -> AuthorityGapScopeResult:
    contract = strategy_contract_for(scope.event_spec_id)
    first_natural_trigger_at_ms: int | None = None
    for bar_count in range(5, len(candles) + 1):
        close_time_ms = session_start_ms + bar_count * INTERVAL_MS
        detector_result = evaluate_strategy_snapshot(
            contract,
            MarketSnapshot(
                exchange_instrument_id=scope.exchange_instrument_id,
                trigger_candle_close_time_ms=close_time_ms,
                candles_15m=candles[:bar_count],
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
