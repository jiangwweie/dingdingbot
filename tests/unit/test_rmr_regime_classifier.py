from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.rmr_regime_classifier import (
    RmrClassifierConfig,
    RmrRegimeAssessment,
    classify_rmr_regime,
)
from src.domain.strategy_semantics import MarketState


def _candle(index: int, close: Decimal, *, high: Decimal | None = None, low: Decimal | None = None):
    return {
        "open_time_ms": 1781000000000 + index * 3_600_000,
        "open": str(close),
        "high": str(high if high is not None else close + Decimal("1")),
        "low": str(low if low is not None else close - Decimal("1")),
        "close": str(close),
        "volume": "100",
    }


def test_rmr_classifies_directional_trend_down_without_execution_authority() -> None:
    candles = [
        _candle(index, Decimal("120") - Decimal(index * 2))
        for index in range(16)
    ]

    result = classify_rmr_regime(candles)

    assert result.status == "classified"
    assert result.market_state == MarketState.TREND_DOWN
    assert "directional_trend" in result.reason_codes
    assert result.strategy_effect["brf"] == "context_support_only_not_execution_authority"
    assert result.strategy_effect["execution_authority"] is False
    assert result.hard_filter is False
    assert result.execution_authority is False
    assert result.order_authority is False
    assert result.not_order is True
    assert result.not_execution_intent is True
    assert result.not_execution_authority is True


def test_rmr_classifies_chop_as_downgrade_evidence_not_hard_filter() -> None:
    closes = [
        Decimal("100"),
        Decimal("101"),
        Decimal("99.5"),
        Decimal("101.2"),
        Decimal("99.8"),
        Decimal("101.0"),
        Decimal("100.1"),
        Decimal("100.9"),
        Decimal("99.9"),
        Decimal("101.1"),
        Decimal("100.0"),
        Decimal("100.8"),
    ]
    candles = [
        _candle(index, close, high=Decimal("102"), low=Decimal("99"))
        for index, close in enumerate(closes)
    ]

    result = classify_rmr_regime(candles)

    assert result.market_state == MarketState.CHOP
    assert result.strategy_effect["cpm"] == "observe_only_or_raise_review"
    assert result.strategy_effect["brf"] == "observe_only_or_raise_review"
    assert result.strategy_effect["hard_filter"] is False
    assert result.strategy_effect["execution_authority"] is False
    assert "alternating_closes" in result.reason_codes


def test_rmr_requires_closed_candle_window() -> None:
    result = classify_rmr_regime(
        [_candle(index, Decimal("100")) for index in range(3)],
        config=RmrClassifierConfig(min_candles=6),
    )

    assert result.status == "review_inputs_required"
    assert result.market_state == MarketState.UNCERTAIN
    assert result.required_inputs == ["closed_ohlcv_window"]
    assert "insufficient_closed_candles" in result.reason_codes


def test_rmr_assessment_rejects_forbidden_execution_fields() -> None:
    with pytest.raises(ValueError, match="order_type"):
        RmrRegimeAssessment(
            status="classified",
            market_state=MarketState.RANGE,
            confidence=Decimal("0.7"),
            range_structure={"order_type": "MARKET"},
        )


def test_rmr_classifier_exposes_no_execution_methods() -> None:
    result = classify_rmr_regime(
        [_candle(index, Decimal("100") + Decimal(index)) for index in range(12)]
    )

    assert not hasattr(result, "create_order")
    assert not hasattr(result, "create_execution_intent")
    assert not hasattr(result, "place_order")
