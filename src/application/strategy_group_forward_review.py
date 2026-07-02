"""Forward review tracking for read-only strategy group observations."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from src.application.strategy_group_live_readonly_observation import (
    RecentCandle,
    StrategyGroupMarketBarSource,
    StrategyGroupObservationRecord,
)


ReviewStatus = Literal["pending", "completed", "not_applicable", "failed"]

_HOUR_MS = 60 * 60 * 1000
_WINDOW_HOURS: dict[str, int] = {
    "1h": 1,
    "4h": 4,
    "12h": 12,
    "24h": 24,
    "72h": 72,
}


class StrategyGroupForwardReviewRecord(BaseModel):
    review_id: str
    observation_id: str
    candidate_id: str
    symbol: str
    side: str
    signal_type: str
    market_bar_timestamp_ms: int
    review_window: str
    review_due_at_ms: int
    review_status: ReviewStatus
    forward_return_pct: str | None = None
    mfe_pct: str | None = None
    mae_pct: str | None = None
    source: str
    calculated_at_ms: int | None = None
    notes: str | None = None
    not_order: bool = True
    not_execution_intent: bool = True
    no_execution_permission: bool = True
    no_order_permission: bool = True
    no_runtime_start: bool = True


def calculate_forward_reviews_for_observation(
    observation: StrategyGroupObservationRecord,
    *,
    market_source: StrategyGroupMarketBarSource,
    windows: list[str] | None = None,
    now_ms: int | None = None,
    candle_limit: int = 120,
) -> list[StrategyGroupForwardReviewRecord]:
    """Calculate completed windows and mark not-yet-due windows pending.

    A forward review uses only public/read-only closed candles. For a signal
    produced from a closed bar at timestamp T, the 1h outcome is the next
    closed 1h candle after that signal bar, so it is due at T + 2h.
    """

    if observation.signal_type != "would_enter":
        return [
            _base_review(
                observation,
                window,
                status="not_applicable",
                source=getattr(market_source, "source_id", "read_only_market_source"),
                notes="forward review is only calculated for would_enter observation signals",
            )
            for window in (windows or list(_WINDOW_HOURS))
        ]

    source_id = getattr(market_source, "source_id", "read_only_market_source")
    now = now_ms or int(time.time() * 1000)
    requested_windows = windows or list(_WINDOW_HOURS)
    candles = market_source.latest_closed_candles(
        symbol=observation.symbol,
        timeframe="1h",
        limit=candle_limit,
    )
    by_open = {candle.open_time_ms: candle for candle in candles}
    entry = _entry_close(observation)
    reviews: list[StrategyGroupForwardReviewRecord] = []

    for window in requested_windows:
        hours = _WINDOW_HOURS[window]
        due_at = _review_due_at_ms(observation.market_bar_timestamp_ms, window)
        if due_at > now:
            reviews.append(
                _base_review(
                    observation,
                    window,
                    status="pending",
                    source=source_id,
                    review_due_at_ms=due_at,
                    notes="review window has not reached due time",
                )
            )
            continue

        forward_bars = [
            by_open.get(observation.market_bar_timestamp_ms + offset * _HOUR_MS)
            for offset in range(1, hours + 1)
        ]
        if any(candle is None for candle in forward_bars):
            reviews.append(
                _base_review(
                    observation,
                    window,
                    status="pending",
                    source=source_id,
                    review_due_at_ms=due_at,
                    notes="required closed forward candles are not available from source yet",
                )
            )
            continue

        completed_bars = [candle for candle in forward_bars if candle is not None]
        exit_close = completed_bars[-1].close
        high = max(candle.high for candle in completed_bars)
        low = min(candle.low for candle in completed_bars)
        reviews.append(
            _base_review(
                observation,
                window,
                status="completed",
                source=source_id,
                review_due_at_ms=due_at,
                forward_return_pct=_pct(exit_close, entry),
                mfe_pct=_pct(high, entry),
                mae_pct=_pct(low, entry),
                calculated_at_ms=now,
                notes=f"calculated from {len(completed_bars)} closed 1h public/read-only bars",
            )
        )

    return reviews


def _review_due_at_ms(market_bar_timestamp_ms: int, window: str) -> int:
    return market_bar_timestamp_ms + (_WINDOW_HOURS[window] + 1) * _HOUR_MS


def _entry_close(observation: StrategyGroupObservationRecord) -> Decimal:
    if observation.market_bar_close is None:
        raise ValueError("observation market_bar_close is required for forward review")
    return Decimal(str(observation.market_bar_close))


def _pct(value: Decimal, entry: Decimal) -> str:
    return str((((value - entry) / entry) * Decimal("100")).quantize(Decimal("0.0001")))


def _base_review(
    observation: StrategyGroupObservationRecord,
    window: str,
    *,
    status: ReviewStatus,
    source: str,
    review_due_at_ms: int | None = None,
    forward_return_pct: str | None = None,
    mfe_pct: str | None = None,
    mae_pct: str | None = None,
    calculated_at_ms: int | None = None,
    notes: str | None = None,
) -> StrategyGroupForwardReviewRecord:
    due_at = review_due_at_ms if review_due_at_ms is not None else _review_due_at_ms(
        observation.market_bar_timestamp_ms,
        window,
    )
    return StrategyGroupForwardReviewRecord(
        review_id=f"{observation.record_id}:{window}",
        observation_id=observation.record_id,
        candidate_id=observation.candidate_id,
        symbol=observation.symbol,
        side=observation.side,
        signal_type=observation.signal_type,
        market_bar_timestamp_ms=observation.market_bar_timestamp_ms,
        review_window=window,
        review_due_at_ms=due_at,
        review_status=status,
        forward_return_pct=forward_return_pct,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        source=source,
        calculated_at_ms=calculated_at_ms,
        notes=notes,
    )
