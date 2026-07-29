from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOrder,
    AdmissionOwnership,
    EntryAdmissionSnapshot,
    OwnedPositionProjection,
)


def test_snapshot_digest_is_stable_for_one_exact_observation_cycle() -> None:
    snapshot = _snapshot()

    assert snapshot.digest() == _snapshot().digest()
    assert snapshot.digest().startswith("sha256:")
    assert len(snapshot.digest()) == 71


def test_snapshot_rejects_fractional_or_boolean_configured_leverage() -> None:
    payload = _snapshot().account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )

    with pytest.raises(ValueError, match="configured leverage must be"):
        AccountRiskSnapshot.create(
            **{**payload, "configured_leverage": Decimal("3.5")}
        )
    with pytest.raises(ValueError, match="configured leverage must be"):
        AccountRiskSnapshot.create(**{**payload, "configured_leverage": True})


def test_ownership_requires_one_quantity_projection_per_owned_domain() -> None:
    with pytest.raises(
        ValueError,
        match="projections must match owned domain identities",
    ):
        AdmissionOwnership(owned_position_domain_keys=("domain:long",))

    with pytest.raises(
        ValueError,
        match="projections must match owned domain identities",
    ):
        AdmissionOwnership(
            owned_position_projections=(
                OwnedPositionProjection(
                    netting_domain_key="domain:long",
                    quantity=Decimal("0.001"),
                ),
            ),
        )


def _snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id="SOLUSDT",
            mark_price=Decimal("100.5"),
            configured_leverage=3,
            total_wallet_balance=Decimal(100),
            total_margin_balance=Decimal(100),
            total_initial_margin=Decimal(10),
            total_maintenance_margin=Decimal(1),
            available_margin=Decimal(90),
            account_positions=(
                AccountRiskPosition(
                    exchange_instrument_id="SOLUSDT",
                    position_side="long",
                    quantity=Decimal("0.1"),
                    average_entry_price=Decimal(100),
                    current_unrealized_pnl=Decimal("0.05"),
                    current_maintenance_margin=Decimal(1),
                ),
            ),
            observed_at_ms=1_800_000_000_000,
            valid_until_ms=1_800_000_005_000,
        ),
        best_bid_price=Decimal(100),
        best_ask_price=Decimal(101),
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
