"""Pure aligned cross-symbol strength facts for StrategyGroup evaluators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ComparativeStrengthError(ValueError):
    """Raised when a complete aligned comparison cannot be computed."""


class ComparativeStrengthMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=128)
    start_close: Decimal = Field(gt=0)
    end_close: Decimal = Field(gt=0)
    return_pct: Decimal
    rank: int = Field(ge=1)


class ComparativeStrengthSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_group_id: str = Field(min_length=1, max_length=128)
    timeframe: str = Field(min_length=1, max_length=32)
    lookback_bars: int = Field(ge=1)
    trigger_candle_close_time_ms: int = Field(gt=0)
    universe_symbols: tuple[str, ...]
    members: tuple[ComparativeStrengthMember, ...]
    observed_at_ms: int = Field(ge=0)
    valid_until_ms: int = Field(gt=0)
    source_ref: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_complete_universe(self) -> "ComparativeStrengthSnapshot":
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("comparative strength validity must end after observation")
        universe = tuple(sorted(set(self.universe_symbols)))
        members = tuple(sorted(member.symbol for member in self.members))
        if universe != members:
            raise ValueError("comparative strength members must match universe")
        return self

    def member(self, symbol: str) -> ComparativeStrengthMember:
        normalized = _symbol(symbol)
        for member in self.members:
            if member.symbol == normalized:
                return member
        raise KeyError(normalized)


def compute_comparative_strength(
    *,
    strategy_group_id: str,
    universe_symbols: Sequence[str],
    timeframe: str,
    lookback_bars: int,
    candles_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    observed_at_ms: int,
    valid_until_ms: int,
    source_ref: str,
) -> ComparativeStrengthSnapshot:
    if lookback_bars < 1:
        raise ComparativeStrengthError("lookback bars must be positive")
    universe = tuple(sorted({_symbol(symbol) for symbol in universe_symbols}))
    if not universe or "" in universe:
        raise ComparativeStrengthError("comparative universe must be non-empty")
    normalized_candles = {
        _symbol(symbol): list(candles)
        for symbol, candles in candles_by_symbol.items()
    }
    missing = [symbol for symbol in universe if symbol not in normalized_candles]
    if missing:
        raise ComparativeStrengthError(
            "missing universe symbol: " + ",".join(missing)
        )

    returns: dict[str, tuple[Decimal, Decimal, Decimal, int]] = {}
    expected_trigger_close: int | None = None
    for symbol in universe:
        candles = normalized_candles[symbol]
        if len(candles) < lookback_bars + 1:
            raise ComparativeStrengthError(
                f"insufficient closed candles: {symbol}"
            )
        start = candles[-(lookback_bars + 1)]
        end = candles[-1]
        start_close = _positive_decimal(start.get("close"), symbol=symbol)
        end_close = _positive_decimal(end.get("close"), symbol=symbol)
        trigger_close = _positive_int(
            end.get("close_time_ms"),
            label=f"trigger close: {symbol}",
        )
        if expected_trigger_close is None:
            expected_trigger_close = trigger_close
        elif trigger_close != expected_trigger_close:
            raise ComparativeStrengthError(
                "trigger close mismatch: "
                f"{symbol}={trigger_close} expected={expected_trigger_close}"
            )
        return_pct = ((end_close - start_close) / start_close) * Decimal("100")
        returns[symbol] = (
            start_close,
            end_close,
            return_pct,
            trigger_close,
        )

    members = tuple(
        ComparativeStrengthMember(
            symbol=symbol,
            start_close=returns[symbol][0],
            end_close=returns[symbol][1],
            return_pct=returns[symbol][2],
            rank=1
            + sum(
                1
                for other in universe
                if returns[other][2] > returns[symbol][2]
            ),
        )
        for symbol in universe
    )
    return ComparativeStrengthSnapshot(
        strategy_group_id=strategy_group_id,
        timeframe=timeframe,
        lookback_bars=lookback_bars,
        trigger_candle_close_time_ms=int(expected_trigger_close or 0),
        universe_symbols=universe,
        members=members,
        observed_at_ms=observed_at_ms,
        valid_until_ms=valid_until_ms,
        source_ref=source_ref,
    )


def _symbol(value: object) -> str:
    return str(value or "").strip().upper().replace("/", "").replace(":USDT", "")


def _positive_decimal(value: object, *, symbol: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ComparativeStrengthError(f"invalid close: {symbol}") from exc
    if result <= 0:
        raise ComparativeStrengthError(f"non-positive close: {symbol}")
    return result


def _positive_int(value: object, *, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ComparativeStrengthError(f"invalid {label}") from exc
    if result <= 0:
        raise ComparativeStrengthError(f"non-positive {label}")
    return result
