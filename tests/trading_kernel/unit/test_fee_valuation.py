from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)


def test_usdt_fee_uses_native_one_to_one_valuation_without_snapshot() -> None:
    valued = value_native_fee(
        native_fee=NativeFee(asset="USDT", amount=Decimal("0.25")),
        valuation_evidence=FeeValuationEvidence(
            method="native_usdt",
            rate_usdt_per_asset=Decimal(1),
            price_pair=None,
            observed_at_ms=None,
            valued_at_ms=1_000,
        ),
    )

    assert valued.usdt_value == Decimal("0.25")


def test_bnb_fee_uses_a_review_time_bnbusdt_index_snapshot() -> None:
    valued = value_native_fee(
        native_fee=NativeFee(asset="BNB", amount=Decimal("0.001")),
        valuation_evidence=FeeValuationEvidence(
            method="binance_usdm_bnbusdt_review_index_snapshot",
            rate_usdt_per_asset=Decimal(600),
            price_pair="BNBUSDT",
            observed_at_ms=1_500_000,
            valued_at_ms=1_000_000,
        ),
    )

    assert valued.usdt_value == Decimal("0.600")

    with pytest.raises(ValidationError, match="observed"):
        FeeValuationEvidence(
            method="binance_usdm_bnbusdt_review_index_snapshot",
            rate_usdt_per_asset=Decimal(600),
            price_pair="BNBUSDT",
            observed_at_ms=None,
            valued_at_ms=1_000_000,
        )


def test_fee_models_reject_unknown_asset_and_negative_native_amount() -> None:
    with pytest.raises(ValidationError, match="asset"):
        NativeFee(asset="BTC", amount=Decimal("0.1"))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="non-negative"):
        NativeFee(asset="BNB", amount=Decimal("-0.1"))
