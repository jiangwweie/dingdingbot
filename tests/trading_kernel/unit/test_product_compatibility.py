from __future__ import annotations

import pytest

from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductCompatibility,
    ProductCompatibilityError,
    require_product_compatibility,
)


def test_equity_product_cannot_enter_crypto_event_universe() -> None:
    crypto = ProductCompatibility(
        event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
        product_family="crypto_perpetual",
        asset_class="crypto",
        contract_type="PERPETUAL",
        underlying_type="CRYPTO",
        margin_asset="USDT",
    )
    equity = InstrumentProductProfile(
        exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        entry_session_policy="regular_only",
        status="candidate",
    )

    with pytest.raises(ProductCompatibilityError, match="PRODUCT_COMPATIBILITY_MISMATCH"):
        require_product_compatibility(crypto, equity)


def test_equity_sor_accepts_only_exact_tradfi_equity_profile() -> None:
    compatibility = ProductCompatibility(
        event_spec_id="event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
    )
    profile = InstrumentProductProfile(
        exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        entry_session_policy="regular_only",
        status="candidate",
    )

    require_product_compatibility(compatibility, profile)
