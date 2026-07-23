from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    AdmissionOrder,
    AdmissionPosition,
    EntryAdmissionSnapshot,
)


def test_snapshot_digest_is_stable_for_one_exact_observation_cycle() -> None:
    snapshot = _snapshot()

    assert snapshot.digest() == _snapshot().digest()
    assert snapshot.digest().startswith("sha256:")
    assert len(snapshot.digest()) == 71


def test_snapshot_rejects_fractional_or_boolean_configured_leverage() -> None:
    payload = _snapshot().model_dump(mode="python")
    instrument_facts = payload["instrument_facts"]

    with pytest.raises(ValueError, match="configured leverage must be an integer"):
        EntryAdmissionSnapshot.model_validate(
            {
                **payload,
                "instrument_facts": (
                    {
                        **instrument_facts[0],
                        "configured_leverage": Decimal("3.5"),
                    },
                ),
            }
        )
    with pytest.raises(ValueError, match="configured leverage must be an integer"):
        EntryAdmissionSnapshot.model_validate(
            {
                **payload,
                "instrument_facts": (
                    {**instrument_facts[0], "configured_leverage": True},
                ),
            }
        )


def _snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        venue_id="binance-usdm",
        account_id="subaccount-main",
        position_mode="independent_sides",
        margin_mode="cross",
        total_wallet_balance=Decimal("100"),
        total_margin_balance=Decimal("100"),
        total_initial_margin=Decimal("10"),
        total_maintenance_margin=Decimal("1"),
        available_margin=Decimal("90"),
        best_bid_price=Decimal("100"),
        best_ask_price=Decimal("101"),
        instrument_facts=(
            AdmissionInstrumentFacts(
                exchange_instrument_id="SOLUSDT",
                mark_price=Decimal("100.5"),
                configured_leverage=3,
            ),
        ),
        positions=(
            AdmissionPosition(
                exchange_instrument_id="SOLUSDT",
                position_side="long",
                quantity=Decimal("0"),
                average_entry_price=None,
            ),
        ),
        open_orders=(
            AdmissionOrder(
                exchange_order_id="order:1",
                venue_client_order_id="brc-order-1",
                exchange_instrument_id="SOLUSDT",
                position_side="long",
                reduce_only=True,
            ),
        ),
        observed_at_ms=1_800_000_000_000,
        valid_until_ms=1_800_000_005_000,
    )
