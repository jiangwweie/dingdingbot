from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)


def test_usdt_fee_uses_native_one_to_one_valuation_without_candle() -> None:
    valued = value_native_fee(
        native_fee=NativeFee(asset="USDT", amount=Decimal("0.25")),
        valuation_evidence=FeeValuationEvidence(
            method="native_usdt",
            rate_usdt_per_asset=Decimal("1"),
            price_pair=None,
            candle_open_time_ms=None,
            candle_close_time_ms=None,
            valued_at_ms=1_000,
        ),
    )

    assert valued.usdt_value == Decimal("0.25")


def test_bnb_fee_requires_completed_bnbusdt_index_candle_within_staleness_bound() -> None:
    valued = value_native_fee(
        native_fee=NativeFee(asset="BNB", amount=Decimal("0.001")),
        valuation_evidence=FeeValuationEvidence(
            method="binance_usdm_bnbusdt_index_1m_previous_close",
            rate_usdt_per_asset=Decimal("600"),
            price_pair="BNBUSDT",
            candle_open_time_ms=900_000,
            candle_close_time_ms=959_999,
            valued_at_ms=1_000_000,
        ),
    )

    assert valued.usdt_value == Decimal("0.600")

    with pytest.raises(ValidationError, match="candle"):
        FeeValuationEvidence(
            method="binance_usdm_bnbusdt_index_1m_previous_close",
            rate_usdt_per_asset=Decimal("600"),
            price_pair="BNBUSDT",
            candle_open_time_ms=900_000,
            candle_close_time_ms=959_999,
            valued_at_ms=1_080_000,
        )


def test_fee_models_reject_unknown_asset_and_negative_native_amount() -> None:
    with pytest.raises(ValidationError, match="asset"):
        NativeFee(asset="BTC", amount=Decimal("0.1"))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="non-negative"):
        NativeFee(asset="BNB", amount=Decimal("-0.1"))
