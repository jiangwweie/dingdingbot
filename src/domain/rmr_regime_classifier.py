"""RMR range/chop regime classifier semantics.

RMR is classifier evidence for BRC strategy runtime governance. It is not a
trading strategy, execution filter, order, execution intent, or authorization
source. The classifier only consumes explicit closed-candle facts and emits
review/downgrade context for other strategies.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields
from src.domain.strategy_semantics import MarketState


class RmrRegimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "RmrRegimeModel":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root=self.__class__.__name__)
        return self


class RmrClosedCandle(RmrRegimeModel):
    open_time_ms: int = Field(ge=0)
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: Optional[Decimal] = Field(default=None, ge=Decimal("0"))

    @model_validator(mode="after")
    def _validate_ohlc_shape(self) -> "RmrClosedCandle":
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        return self


class RmrClassifierConfig(RmrRegimeModel):
    min_candles: int = Field(default=12, ge=4)
    trend_pct_threshold: Decimal = Field(default=Decimal("3.0"), gt=Decimal("0"))
    trend_efficiency_threshold: Decimal = Field(default=Decimal("0.45"), ge=Decimal("0"), le=Decimal("1"))
    chop_efficiency_threshold: Decimal = Field(default=Decimal("0.30"), ge=Decimal("0"), le=Decimal("1"))
    chop_alternation_threshold: Decimal = Field(default=Decimal("0.55"), ge=Decimal("0"), le=Decimal("1"))
    range_pct_threshold: Decimal = Field(default=Decimal("2.5"), gt=Decimal("0"))


class RmrRegimeAssessment(RmrRegimeModel):
    status: Literal["classified", "review_inputs_required"]
    market_state: MarketState = MarketState.UNCERTAIN
    confidence: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))
    confidence_semantics: Literal[
        "regime_evidence_only_not_execution_probability"
    ] = "regime_evidence_only_not_execution_probability"
    required_inputs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    range_structure: dict[str, Any] = Field(default_factory=dict)
    volatility_state: dict[str, Any] = Field(default_factory=dict)
    strategy_effect: dict[str, Any] = Field(default_factory=dict)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True
    hard_filter: Literal[False] = False
    execution_authority: Literal[False] = False
    order_authority: Literal[False] = False
    warnings: list[str] = Field(default_factory=list)


def classify_rmr_regime(
    candles: list[dict[str, Any] | RmrClosedCandle],
    *,
    config: RmrClassifierConfig | None = None,
) -> RmrRegimeAssessment:
    """Classify range/chop/trend state from explicit closed-candle facts."""

    cfg = config or RmrClassifierConfig()
    parsed, errors = _parse_candles(candles)
    if len(parsed) < cfg.min_candles:
        return RmrRegimeAssessment(
            status="review_inputs_required",
            required_inputs=["closed_ohlcv_window"],
            reason_codes=["insufficient_closed_candles"],
            warnings=[
                f"RMR requires at least {cfg.min_candles} closed candles; got {len(parsed)}",
                *errors,
            ],
        )

    ordered = sorted(parsed, key=lambda candle: candle.open_time_ms)
    first_close = ordered[0].close
    last_close = ordered[-1].close
    highest = max(candle.high for candle in ordered)
    lowest = min(candle.low for candle in ordered)
    range_pct = _pct(highest - lowest, last_close)
    net_move_pct = _pct(last_close - first_close, first_close)
    efficiency = (
        abs(net_move_pct) / range_pct if range_pct > Decimal("0") else Decimal("0")
    )
    avg_bar_range_pct = sum(
        (_pct(candle.high - candle.low, candle.close) for candle in ordered),
        Decimal("0"),
    ) / Decimal(len(ordered))
    alternation_ratio = _alternation_ratio(ordered)
    close_position = (
        (last_close - lowest) / (highest - lowest)
        if highest > lowest
        else Decimal("0.5")
    )
    market_state, reason_codes, confidence = _classify_state(
        net_move_pct=net_move_pct,
        range_pct=range_pct,
        efficiency=efficiency,
        alternation_ratio=alternation_ratio,
        cfg=cfg,
    )
    return RmrRegimeAssessment(
        status="classified",
        market_state=market_state,
        confidence=_q(confidence),
        reason_codes=reason_codes,
        range_structure={
            "highest_high": _s(highest),
            "lowest_low": _s(lowest),
            "range_pct": _s(_q(range_pct)),
            "close_position_in_range": _s(_q(close_position)),
            "net_move_pct": _s(_q(net_move_pct)),
            "direction_efficiency": _s(_q(efficiency)),
            "candle_count": len(ordered),
        },
        volatility_state={
            "average_bar_range_pct": _s(_q(avg_bar_range_pct)),
            "alternation_ratio": _s(_q(alternation_ratio)),
            "range_pct": _s(_q(range_pct)),
            "path_efficiency": _s(_q(efficiency)),
        },
        strategy_effect=_strategy_effect(market_state),
        warnings=[
            "RMR output is regime evidence only and must not hard-filter execution.",
        ],
    )


def _parse_candles(
    candles: list[dict[str, Any] | RmrClosedCandle],
) -> tuple[list[RmrClosedCandle], list[str]]:
    parsed: list[RmrClosedCandle] = []
    errors: list[str] = []
    for index, item in enumerate(candles):
        try:
            parsed.append(
                item if isinstance(item, RmrClosedCandle) else RmrClosedCandle.model_validate(item)
            )
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"candle_{index}_invalid:{exc}")
    return parsed, errors


def _classify_state(
    *,
    net_move_pct: Decimal,
    range_pct: Decimal,
    efficiency: Decimal,
    alternation_ratio: Decimal,
    cfg: RmrClassifierConfig,
) -> tuple[MarketState, list[str], Decimal]:
    abs_net = abs(net_move_pct)
    if (
        abs_net >= cfg.trend_pct_threshold
        and efficiency >= cfg.trend_efficiency_threshold
    ):
        direction = MarketState.TREND_UP if net_move_pct > Decimal("0") else MarketState.TREND_DOWN
        confidence = min(
            Decimal("0.95"),
            Decimal("0.50")
            + min(efficiency, Decimal("1")) * Decimal("0.30")
            + min(abs_net / Decimal("10"), Decimal("0.20")),
        )
        return direction, ["directional_trend", direction.value.lower()], confidence

    if (
        efficiency <= cfg.chop_efficiency_threshold
        and alternation_ratio >= cfg.chop_alternation_threshold
    ):
        confidence = min(
            Decimal("0.90"),
            Decimal("0.45")
            + alternation_ratio * Decimal("0.35")
            + (cfg.chop_efficiency_threshold - efficiency) * Decimal("0.30"),
        )
        return MarketState.CHOP, ["low_path_efficiency", "alternating_closes"], confidence

    if range_pct <= cfg.range_pct_threshold and efficiency <= Decimal("0.40"):
        confidence = min(
            Decimal("0.85"),
            Decimal("0.45")
            + ((cfg.range_pct_threshold - range_pct) / cfg.range_pct_threshold)
            * Decimal("0.25")
            + (Decimal("0.40") - efficiency) * Decimal("0.25"),
        )
        return MarketState.RANGE, ["compressed_range", "low_directional_efficiency"], confidence

    return MarketState.UNCERTAIN, ["regime_uncertain"], Decimal("0.30")


def _alternation_ratio(candles: list[RmrClosedCandle]) -> Decimal:
    signs: list[int] = []
    for prev, current in zip(candles, candles[1:]):
        diff = current.close - prev.close
        if diff > Decimal("0"):
            signs.append(1)
        elif diff < Decimal("0"):
            signs.append(-1)
    if len(signs) < 2:
        return Decimal("0")
    switches = sum(1 for prev, current in zip(signs, signs[1:]) if prev != current)
    return Decimal(switches) / Decimal(len(signs) - 1)


def _strategy_effect(market_state: MarketState) -> dict[str, Any]:
    if market_state == MarketState.CHOP:
        return {
            "cpm": "observe_only_or_raise_review",
            "brf": "observe_only_or_raise_review",
            "hard_filter": False,
            "execution_authority": False,
        }
    if market_state == MarketState.RANGE:
        return {
            "cpm": "lower_confidence_or_observe_only",
            "brf": "lower_confidence_or_observe_only",
            "hard_filter": False,
            "execution_authority": False,
        }
    if market_state == MarketState.TREND_UP:
        return {
            "cpm": "context_support_only_not_execution_authority",
            "brf": "raise_short_side_review_requirement",
            "hard_filter": False,
            "execution_authority": False,
        }
    if market_state == MarketState.TREND_DOWN:
        return {
            "cpm": "raise_long_side_review_requirement",
            "brf": "context_support_only_not_execution_authority",
            "hard_filter": False,
            "execution_authority": False,
        }
    return {
        "cpm": "no_regime_authority",
        "brf": "no_regime_authority",
        "hard_filter": False,
        "execution_authority": False,
    }


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _s(value: Decimal) -> str:
    return str(value)
