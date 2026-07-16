from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRef,
    RiskClusterMembershipSnapshotRef,
)


def _identity_values() -> dict[str, str]:
    return {
        "exchange_instrument_id": "instrument-opaque-1",
        "exchange_id": "binance-usdm",
        "exchange_symbol": "SOLUSDT",
        "asset_class": "crypto",
        "instrument_type": "perpetual",
        "settlement_asset": "USDT",
        "margin_asset": "USDT",
        "instrument_identity_schema_version": "v1",
    }


def test_instrument_identity_is_explicit_opaque_and_immutable() -> None:
    identity = InstrumentRiskIdentity.model_validate(_identity_values())

    assert identity.exchange_instrument_id == "instrument-opaque-1"
    assert identity.instrument_type == "perpetual"
    with pytest.raises((TypeError, ValueError, ValidationError)):
        identity.exchange_instrument_id = "binance-usdm:SOLUSDT"


def test_instrument_identity_rejects_missing_or_blank_canonical_identity() -> None:
    with pytest.raises(ValidationError):
        InstrumentRiskIdentity.model_validate(
            {key: value for key, value in _identity_values().items() if key != "exchange_instrument_id"}
        )
    with pytest.raises(ValidationError):
        InstrumentRiskIdentity.model_validate(
            {**_identity_values(), "exchange_instrument_id": "   "}
        )


def test_rule_snapshot_and_cluster_membership_are_immutable_versioned_facts() -> None:
    rule = InstrumentRuleSnapshotRef(
        instrument_rule_snapshot_id="rule-snapshot-1",
        rule_schema_version="v1",
        price_tick=Decimal("0.01"),
        quantity_step=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal("1"),
        exchange_max_leverage_for_claim_notional=10,
        source_fact_snapshot_id="exchange-fact-1",
        valid_until_ms=1_752_480_060_000,
    )
    membership = RiskClusterMembershipSnapshotRef(
        cluster_membership_snapshot_id="cluster-membership-1",
        primary_risk_cluster_id="cluster:layer-1",
        semantic_hash="a" * 64,
    )

    assert rule.quantity_step == Decimal("0.001")
    assert membership.primary_risk_cluster_id == "cluster:layer-1"
    with pytest.raises((TypeError, ValueError, ValidationError)):
        rule.min_qty = Decimal("1")
