"""Historical OHLCV snapshot builders for BRC strategy-family research.

These builders prepare read-only historical inputs for the BRC-R5-003A signal
contract. They do not run strategy evaluators, create SignalOutput, write
trial-trade-intent evidence, or touch live execution/order services.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    StrategyFamilySignalInput,
)


class HistoricalOhlcvReader(Protocol):
    async def fetch_recent_bars_ending_at(
        self,
        *,
        symbol: str,
        timeframe: str,
        timestamp_ms: int,
        limit: int,
    ) -> list[HistoricalOhlcvBar]:
        ...


class HistoricalMarketSnapshotBuilder:
    """Build a MarketSnapshot from historical OHLCV windows."""

    def __init__(
        self,
        *,
        repository: HistoricalOhlcvReader,
        primary_lookback: int = 64,
        context_lookback: int = 32,
        atr_period: int = 14,
    ) -> None:
        self._repository = repository
        self._primary_lookback = primary_lookback
        self._context_lookback = context_lookback
        self._atr_period = atr_period

    async def build(
        self,
        *,
        symbol: str,
        timestamp_ms: int,
        primary_timeframe: str,
        context_timeframes: list[str],
    ) -> MarketSnapshot:
        all_timeframes = [primary_timeframe, *[tf for tf in context_timeframes if tf != primary_timeframe]]
        windows: dict[str, list[HistoricalOhlcvBar]] = {}
        missing_fields = [
            "index_price",
            "bid",
            "ask",
            "bid_ask_spread",
            "quote_volume",
            "funding_rate",
            "next_funding_time_ms",
        ]

        for timeframe in all_timeframes:
            limit = self._primary_lookback if timeframe == primary_timeframe else self._context_lookback
            bars = await self._repository.fetch_recent_bars_ending_at(
                symbol=symbol,
                timeframe=timeframe,
                timestamp_ms=timestamp_ms,
                limit=limit,
            )
            windows[timeframe] = bars
            if not bars:
                missing_fields.append(f"candle_context.{timeframe}")

        primary_bars = windows.get(primary_timeframe) or []
        if not primary_bars:
            return MarketSnapshot(
                symbol=symbol,
                timestamp_ms=timestamp_ms,
                source="historical_ohlcv",
                freshness="missing",
                timeframe=primary_timeframe,
                candle_context=_serialize_windows(windows),
                source_latency_ms=0,
                missing_fields=sorted(set([*missing_fields, "last_price", "mark_price", "volume", "atr"])),
            )

        latest = primary_bars[-1]
        atr = _compute_atr(primary_bars, period=self._atr_period)
        if atr is None:
            missing_fields.append("atr")

        return MarketSnapshot(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            source="historical_ohlcv",
            freshness="historical",
            last_price=latest.close,
            mark_price=latest.close,
            index_price=None,
            bid=None,
            ask=None,
            bid_ask_spread=None,
            volume=latest.volume,
            quote_volume=latest.quote_volume,
            funding_rate=None,
            next_funding_time_ms=None,
            volatility=None,
            atr=atr,
            timeframe=primary_timeframe,
            candle_context={
                "source": "historical_ohlcv",
                "mark_price_proxy": "close",
                "requested_timestamp_ms": timestamp_ms,
                "latest_primary_bar_time_ms": latest.open_time_ms,
                "windows": _serialize_windows(windows),
            },
            source_latency_ms=0,
            missing_fields=sorted(set(missing_fields)),
        )


class HistoricalStrategyFamilySignalInputBuilder:
    """Build a historical StrategyFamilySignalInput skeleton."""

    def __init__(self, *, market_snapshot_builder: HistoricalMarketSnapshotBuilder) -> None:
        self._market_snapshot_builder = market_snapshot_builder

    async def build(
        self,
        *,
        strategy_family_metadata: StrategyFamilyMetadata,
        playbook_metadata: StrategyFamilyPlaybookMetadata,
        symbol: str,
        timestamp_ms: int,
        primary_timeframe: str,
        context_timeframes: list[str],
        evaluation_id: str | None = None,
    ) -> StrategyFamilySignalInput:
        resolved_evaluation_id = evaluation_id or (
            f"hist-{strategy_family_metadata.family_id}-{symbol}-{primary_timeframe}-{timestamp_ms}"
        )
        market_snapshot = await self._market_snapshot_builder.build(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            primary_timeframe=primary_timeframe,
            context_timeframes=context_timeframes,
        )
        input_quality = SignalDataQuality(
            status=(
                SignalDataQualityStatus.DEGRADED
                if market_snapshot.missing_fields
                else SignalDataQualityStatus.OK
            ),
            missing_fields=list(market_snapshot.missing_fields),
            warnings=[
                "historical research input only",
                "account facts are sanitized placeholders",
                "permission context is evidence only and grants no trading authority",
            ],
            source_latency_ms=0,
        )
        return StrategyFamilySignalInput(
            evaluation_id=resolved_evaluation_id,
            strategy_family_id=strategy_family_metadata.family_id,
            strategy_family_version_id=strategy_family_metadata.version_id,
            playbook_id=playbook_metadata.playbook_id,
            campaign_id="historical-research",
            binding_id="historical-research",
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            primary_timeframe=primary_timeframe,
            context_timeframes=list(context_timeframes),
            market_snapshot=market_snapshot,
            account_facts_snapshot=_historical_account_facts(timestamp_ms),
            position_open_order_summary={"position_count": 0, "open_order_count": 0},
            reconciliation_status={"status": "historical_not_applicable"},
            runtime_safety_snapshot={
                "source": "historical_research_placeholder",
                "runtime_state": "observe",
                "live_ready": False,
                "auto_execution_enabled": False,
            },
            execution_permission_resolution={
                "source": "historical_research_placeholder",
                "requested_permission": "signal_only",
                "final_permission": "signal_only",
                "configured_max_permission": "signal_only",
                "downgrade_reason": "historical research input grants no trading authority",
            },
            trial_constraints_snapshot={
                "source": "historical_research_placeholder",
                "constraints_applicable": False,
                "risk_bounds_review_only": True,
            },
            playbook_snapshot=playbook_metadata.model_dump(mode="json"),
            strategy_family_metadata=strategy_family_metadata.model_dump(mode="json"),
            source="historical_ohlcv_research",
            freshness="historical",
            input_quality=input_quality,
        )


def _historical_account_facts(timestamp_ms: int) -> AccountFactsSnapshot:
    return AccountFactsSnapshot(
        source="historical_research",
        truth_level="simulated_or_unavailable",
        timestamp_ms=timestamp_ms,
        freshness="historical_not_applicable",
        account_status="historical_research_placeholder",
        available_balance=None,
        positions=[],
        open_orders=[],
        position_count=0,
        open_order_count=0,
        unknown_unmanaged_counts={"orders": 0, "positions": 0},
        reconciliation_status={"status": "historical_not_applicable"},
        read_only_provider="historical_ohlcv_research",
        limitations=[
            "No live account facts are used.",
            "No sizing, leverage, venue, or order command is represented.",
        ],
    )


def _serialize_windows(windows: dict[str, list[HistoricalOhlcvBar]]) -> dict[str, list[dict]]:
    return {
        timeframe: [
            {
                "open_time_ms": bar.open_time_ms,
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
            }
            for bar in bars
        ]
        for timeframe, bars in windows.items()
    }


def _compute_atr(bars: list[HistoricalOhlcvBar], *, period: int) -> Decimal | None:
    if period <= 0 or len(bars) < period + 1:
        return None
    true_ranges: list[Decimal] = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    if len(true_ranges) < period:
        return None
    selected = true_ranges[-period:]
    return sum(selected, Decimal("0")) / Decimal(period)
