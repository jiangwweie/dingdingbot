from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductCompatibility,
    ProductEntryStatus,
    ProductSessionSnapshot,
    evaluate_event_product_entry,
    evaluate_product_entry,
)


def _profile() -> InstrumentProductProfile:
    return InstrumentProductProfile(
        exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        entry_session_policy="regular_only",
        status="candidate",
        max_entry_spread_bps=Decimal(20),
        max_mark_index_deviation_bps=Decimal(50),
    )


def _snapshot(**updates: object) -> ProductSessionSnapshot:
    values: dict[str, object] = {
        "exchange_instrument_id": "binance-usdm:AAPLUSDT:perpetual",
        "product_family": "tradfi_equity_perpetual",
        "product_status": "active",
        "session_state": "regular",
        "regular_session_open_ms": 900,
        "regular_session_close_ms": 2_000,
        "mark_price": Decimal("100.10"),
        "index_price": Decimal(100),
        "funding_rate": Decimal("0.0001"),
        "best_bid": Decimal(100),
        "best_ask": Decimal("100.10"),
        "best_bid_quantity": Decimal(10),
        "best_ask_quantity": Decimal(10),
        "corporate_event_status": "unavailable",
        "observed_at_ms": 1_000,
        "valid_until_ms": 1_500,
        "source_ref": "binance:readonly",
    }
    values.update(updates)
    return ProductSessionSnapshot.model_validate(values)


def test_regular_fresh_tradfi_product_allows_entry_with_unavailable_corporate_data() -> None:
    decision = evaluate_product_entry(
        profile=_profile(),
        snapshot=_snapshot(),
        now_ms=1_100,
    )

    assert decision.status is ProductEntryStatus.ALLOWED
    assert decision.corporate_event_warning is True
    assert decision.spread_bps == Decimal("9.995002498750624687656171914")
    assert decision.mark_index_deviation_bps == Decimal("10.000")


@pytest.mark.parametrize(
    ("updates", "status"),
    (
        ({"session_state": "pre_market"}, ProductEntryStatus.SESSION_NOT_REGULAR),
        ({"valid_until_ms": 1_050}, ProductEntryStatus.SNAPSHOT_STALE),
        ({"best_ask": Decimal(101)}, ProductEntryStatus.SPREAD_TOO_WIDE),
        (
            {"mark_price": Decimal(101), "index_price": Decimal(100)},
            ProductEntryStatus.MARK_INDEX_DEVIATION_TOO_WIDE,
        ),
        (
            {"corporate_event_status": "blocked"},
            ProductEntryStatus.CORPORATE_EVENT_BLOCKED,
        ),
    ),
)
def test_tradfi_product_entry_fails_closed_on_action_time_blockers(
    updates: dict[str, object],
    status: ProductEntryStatus,
) -> None:
    decision = evaluate_product_entry(
        profile=_profile(),
        snapshot=_snapshot(**updates),
        now_ms=1_100,
    )

    assert decision.status is status


def test_event_product_authority_rejects_missing_or_mismatched_profile() -> None:
    compatibility = ProductCompatibility(
        event_spec_id="event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
    )
    missing = evaluate_event_product_entry(
        compatibility=compatibility,
        profile=None,
        snapshot=None,
        now_ms=1_100,
    )
    mismatched = evaluate_event_product_entry(
        compatibility=compatibility,
        profile=InstrumentProductProfile(
            exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            entry_session_policy="continuous",
            status="candidate",
        ),
        snapshot=None,
        now_ms=1_100,
    )

    assert missing.status is ProductEntryStatus.IDENTITY_MISMATCH
    assert mismatched.status is ProductEntryStatus.IDENTITY_MISMATCH
