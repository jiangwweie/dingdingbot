from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.comparative_strength import (
    ComparativeStrengthError,
    compute_comparative_strength,
)
from src.domain.strategy_family_signal import StrategyFamilySignalInput
from tests.unit.test_strategy_family_signal_contract import _signal_input


TRIGGER_CLOSE_MS = 1_770_001_200_000


def _candles(*closes: str, trigger_close_ms: int = TRIGGER_CLOSE_MS):
    start = trigger_close_ms - (len(closes) * 3_600_000)
    return [
        {
            "open_time_ms": start + index * 3_600_000,
            "close_time_ms": start + (index + 1) * 3_600_000,
            "close": close,
        }
        for index, close in enumerate(closes)
    ]


def test_comparative_strength_computes_decimal_returns_and_competition_rank():
    snapshot = compute_comparative_strength(
        strategy_group_id="MPG-001",
        universe_symbols=("OPUSDT", "SOLUSDT", "SUIUSDT"),
        timeframe="1h",
        lookback_bars=2,
        candles_by_symbol={
            "OPUSDT": _candles("100", "105", "110"),
            "SOLUSDT": _candles("100", "104", "110"),
            "SUIUSDT": _candles("100", "101", "103"),
        },
        observed_at_ms=TRIGGER_CLOSE_MS + 1_000,
        valid_until_ms=TRIGGER_CLOSE_MS + 3_600_000,
        source_ref="pg_candidate_scope+binance_closed_1h",
    )

    members = {member.symbol: member for member in snapshot.members}
    assert members["OPUSDT"].return_pct == Decimal("10.0")
    assert members["SOLUSDT"].return_pct == Decimal("10.0")
    assert members["SUIUSDT"].return_pct == Decimal("3.00")
    assert members["OPUSDT"].rank == 1
    assert members["SOLUSDT"].rank == 1
    assert members["SUIUSDT"].rank == 3
    assert snapshot.trigger_candle_close_time_ms == TRIGGER_CLOSE_MS


def test_comparative_strength_rejects_missing_universe_member():
    with pytest.raises(ComparativeStrengthError, match="missing universe symbol"):
        compute_comparative_strength(
            strategy_group_id="MI-001",
            universe_symbols=("AVAXUSDT", "ETHUSDT", "SOLUSDT"),
            timeframe="1h",
            lookback_bars=2,
            candles_by_symbol={
                "AVAXUSDT": _candles("100", "102", "104"),
                "ETHUSDT": _candles("100", "101", "102"),
            },
            observed_at_ms=TRIGGER_CLOSE_MS + 1_000,
            valid_until_ms=TRIGGER_CLOSE_MS + 3_600_000,
            source_ref="pg_candidate_scope+binance_closed_1h",
        )


def test_comparative_strength_rejects_misaligned_trigger_close():
    with pytest.raises(ComparativeStrengthError, match="trigger close mismatch"):
        compute_comparative_strength(
            strategy_group_id="MPG-001",
            universe_symbols=("OPUSDT", "SOLUSDT"),
            timeframe="1h",
            lookback_bars=2,
            candles_by_symbol={
                "OPUSDT": _candles("100", "105", "110"),
                "SOLUSDT": _candles(
                    "100",
                    "104",
                    "109",
                    trigger_close_ms=TRIGGER_CLOSE_MS - 3_600_000,
                ),
            },
            observed_at_ms=TRIGGER_CLOSE_MS + 1_000,
            valid_until_ms=TRIGGER_CLOSE_MS + 3_600_000,
            source_ref="pg_candidate_scope+binance_closed_1h",
        )


def test_signal_input_accepts_typed_comparative_strength_snapshot():
    snapshot = compute_comparative_strength(
        strategy_group_id="MPG-001",
        universe_symbols=("OPUSDT", "SOLUSDT"),
        timeframe="1h",
        lookback_bars=2,
        candles_by_symbol={
            "OPUSDT": _candles("100", "105", "110"),
            "SOLUSDT": _candles("100", "104", "109"),
        },
        observed_at_ms=TRIGGER_CLOSE_MS + 1_000,
        valid_until_ms=TRIGGER_CLOSE_MS + 3_600_000,
        source_ref="pg_candidate_scope+binance_closed_1h",
    )
    payload = _signal_input().model_dump(mode="python")
    payload["comparative_strength_snapshot"] = snapshot

    signal_input = StrategyFamilySignalInput.model_validate(payload)

    assert signal_input.comparative_strength_snapshot is not None
    assert signal_input.comparative_strength_snapshot.member("OPUSDT").rank == 1
