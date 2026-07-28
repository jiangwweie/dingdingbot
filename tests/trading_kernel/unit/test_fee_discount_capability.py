from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.runtime_facts import (
    FeeDiscountCapabilityFacts,
    classify_fee_discount_capability,
)


def test_fee_discount_capability_is_available_only_with_fee_burn_and_positive_bnb() -> None:
    status = classify_fee_discount_capability(
        FeeDiscountCapabilityFacts(
            fee_burn_enabled=True,
            bnb_futures_wallet_balance=Decimal("0.02"),
            observed_at_ms=1_000,
            source="binance_usdm_readonly",
        )
    )

    assert status == "available"


def test_fee_discount_capability_is_warning_only_when_fee_burn_is_disabled_or_bnb_empty() -> None:
    disabled = classify_fee_discount_capability(
        FeeDiscountCapabilityFacts(
            fee_burn_enabled=False,
            bnb_futures_wallet_balance=Decimal("0.02"),
            observed_at_ms=1_000,
            source="binance_usdm_readonly",
        )
    )
    empty = classify_fee_discount_capability(
        FeeDiscountCapabilityFacts(
            fee_burn_enabled=True,
            bnb_futures_wallet_balance=Decimal("0"),
            observed_at_ms=1_000,
            source="binance_usdm_readonly",
        )
    )

    assert disabled == "unavailable"
    assert empty == "unavailable"
