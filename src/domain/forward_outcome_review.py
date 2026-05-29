"""Forward outcome review for historical would-enter signals."""

from __future__ import annotations

from decimal import Decimal

from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_signal_evaluation import (
    HistoricalForwardOutcome,
    HistoricalForwardOutcomeStatus,
)
from src.domain.strategy_family_signal import SignalSide, SignalType, StrategyFamilySignalOutput


DEFAULT_FORWARD_WINDOWS = {"4h": 4, "24h": 24, "72h": 72, "7d": 168}


def calculate_forward_outcomes(
    *,
    run_id: str,
    signal_output: StrategyFamilySignalOutput,
    entry_bar: HistoricalOhlcvBar | None,
    future_bars: list[HistoricalOhlcvBar],
    created_at_ms: int,
    windows: dict[str, int] | None = None,
) -> list[HistoricalForwardOutcome]:
    if signal_output.signal_type != SignalType.WOULD_ENTER or signal_output.side not in {
        SignalSide.LONG,
        SignalSide.SHORT,
    }:
        return []

    configured_windows = windows or DEFAULT_FORWARD_WINDOWS
    outcomes: list[HistoricalForwardOutcome] = []
    for window_label, bars_ahead in configured_windows.items():
        window_bars = future_bars[:bars_ahead]
        if entry_bar is None or not window_bars:
            outcomes.append(
                _incomplete_outcome(
                    run_id=run_id,
                    signal_output=signal_output,
                    window_label=window_label,
                    bars_ahead=bars_ahead,
                    created_at_ms=created_at_ms,
                )
            )
            continue
        outcomes.append(
            _calculate_window_outcome(
                run_id=run_id,
                signal_output=signal_output,
                entry_close=entry_bar.close,
                window_label=window_label,
                bars_ahead=bars_ahead,
                bars=window_bars,
                complete=len(window_bars) >= bars_ahead,
                created_at_ms=created_at_ms,
            )
        )
    return outcomes


def _calculate_window_outcome(
    *,
    run_id: str,
    signal_output: StrategyFamilySignalOutput,
    entry_close: Decimal,
    window_label: str,
    bars_ahead: int,
    bars: list[HistoricalOhlcvBar],
    complete: bool,
    created_at_ms: int,
) -> HistoricalForwardOutcome:
    if signal_output.side == SignalSide.LONG:
        best_index, best_high = max(enumerate((bar.high for bar in bars), start=1), key=lambda item: item[1])
        worst_index, worst_low = min(enumerate((bar.low for bar in bars), start=1), key=lambda item: item[1])
        mfe_pct = _pct(best_high - entry_close, entry_close)
        mae_pct = _pct(worst_low - entry_close, entry_close)
        pain_before_profit_pct = min(
            Decimal("0"),
            min((_pct(bar.low - entry_close, entry_close) for bar in bars[:best_index]), default=Decimal("0")),
        )
        final_return_pct = _pct(bars[-1].close - entry_close, entry_close)
    else:
        best_index, best_low = min(enumerate((bar.low for bar in bars), start=1), key=lambda item: item[1])
        worst_index, worst_high = max(enumerate((bar.high for bar in bars), start=1), key=lambda item: item[1])
        mfe_pct = _pct(entry_close - best_low, entry_close)
        mae_pct = _pct(entry_close - worst_high, entry_close)
        pain_before_profit_pct = min(
            Decimal("0"),
            min((_pct(entry_close - bar.high, entry_close) for bar in bars[:best_index]), default=Decimal("0")),
        )
        final_return_pct = _pct(entry_close - bars[-1].close, entry_close)

    return HistoricalForwardOutcome(
        outcome_id=f"{signal_output.signal_id}:{window_label}",
        run_id=run_id,
        signal_id=signal_output.signal_id,
        symbol=signal_output.symbol,
        timestamp_ms=signal_output.timestamp_ms,
        side=signal_output.side,
        window_label=window_label,
        bars_ahead=bars_ahead,
        status=(
            HistoricalForwardOutcomeStatus.COMPLETE
            if complete
            else HistoricalForwardOutcomeStatus.INCOMPLETE
        ),
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        time_to_mfe_bars=best_index,
        time_to_mae_bars=worst_index,
        pain_before_profit_pct=pain_before_profit_pct,
        profit_giveback_pct=max(Decimal("0"), mfe_pct - final_return_pct),
        follow_through=mfe_pct > abs(mae_pct),
        invalidation_hit=mae_pct <= Decimal("-2"),
        return_time_curve=[
            {"bar": index, "return_pct": str(_bar_return(signal_output.side, entry_close, bar.close))}
            for index, bar in enumerate(bars, start=1)
        ],
        created_at_ms=created_at_ms,
    )


def _incomplete_outcome(
    *,
    run_id: str,
    signal_output: StrategyFamilySignalOutput,
    window_label: str,
    bars_ahead: int,
    created_at_ms: int,
) -> HistoricalForwardOutcome:
    return HistoricalForwardOutcome(
        outcome_id=f"{signal_output.signal_id}:{window_label}",
        run_id=run_id,
        signal_id=signal_output.signal_id,
        symbol=signal_output.symbol,
        timestamp_ms=signal_output.timestamp_ms,
        side=signal_output.side,
        window_label=window_label,
        bars_ahead=bars_ahead,
        status=HistoricalForwardOutcomeStatus.INCOMPLETE,
        return_time_curve=[],
        created_at_ms=created_at_ms,
    )


def _bar_return(side: SignalSide, entry_close: Decimal, close: Decimal) -> Decimal:
    if side == SignalSide.SHORT:
        return _pct(entry_close - close, entry_close)
    return _pct(close - entry_close, entry_close)


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.0001"))
