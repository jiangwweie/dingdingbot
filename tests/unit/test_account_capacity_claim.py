from __future__ import annotations

from decimal import Decimal

from src.domain.account_capacity_claim import (
    AccountCapacityClaimPayload,
    capacity_claim_hash,
    reservation_idempotency_key,
)


def _claim_payload(
    *,
    policy_event_id: str = "policy-event-1",
    exchange_instrument_id: str = "instrument-opaque-1",
    action_time_lane_input_id: str = "lane-input-1",
) -> AccountCapacityClaimPayload:
    return AccountCapacityClaimPayload(
        capacity_claim_schema_version="v1",
        reservation_id="reservation-1",
        ticket_id="ticket-1",
        exposure_episode_id="episode-1",
        action_time_invocation_id="invocation-1",
        action_time_lane_input_id=action_time_lane_input_id,
        promotion_candidate_id="promotion-1",
        signal_event_id="signal-1",
        account_id="account-1",
        runtime_profile_id="profile-1",
        strategy_group_id="MPG-001",
        side="long",
        instrument={
            "exchange_instrument_id": exchange_instrument_id,
            "exchange_id": "binance-usdm",
            "exchange_symbol": "SOLUSDT",
            "asset_class": "crypto",
            "instrument_type": "perpetual",
            "settlement_asset": "USDT",
            "margin_asset": "USDT",
            "instrument_identity_schema_version": "v1",
        },
        rule_snapshot={
            "instrument_rule_snapshot_id": "rule-snapshot-1",
            "rule_schema_version": "v1",
            "price_tick": Decimal("0.01"),
            "quantity_step": Decimal("0.001"),
            "min_qty": Decimal("0.001"),
            "min_notional": Decimal("5"),
            "contract_multiplier": Decimal("1"),
            "exchange_max_leverage_for_claim_notional": 10,
            "source_fact_snapshot_id": "exchange-fact-1",
            "valid_until_ms": 1_752_480_060_000,
        },
        cluster_snapshot={
            "cluster_membership_snapshot_id": "cluster-membership-1",
            "primary_risk_cluster_id": "cluster:layer-1",
            "semantic_hash": "a" * 64,
        },
        pricing_source_fact_snapshot_id="pricing-fact-1",
        account_source_fact_snapshot_id="account-fact-1",
        account_fact_schema_version="v1",
        account_risk_policy_version="risk-policy-v1",
        account_risk_policy_event_id=policy_event_id,
        claimed_budget_projection_version=7,
        entry_reference_price=Decimal("150"),
        stop_price=Decimal("145"),
        intended_qty=Decimal("0.8"),
        target_notional=Decimal("120"),
        allowed_risk_budget=Decimal("15"),
        planned_stop_risk=Decimal("4"),
        reserved_margin=Decimal("12"),
        selected_leverage=10,
        reserved_at_ms=1_752_480_000_000,
        expires_at_ms=1_752_480_060_000,
    )


def test_policy_event_changes_hash_but_not_idempotency_key() -> None:
    first = _claim_payload(policy_event_id="policy-event-1")
    second = _claim_payload(policy_event_id="policy-event-2")

    assert reservation_idempotency_key(first) == reservation_idempotency_key(second)
    assert capacity_claim_hash(first) != capacity_claim_hash(second)


def test_instrument_or_lane_drift_cannot_change_invocation_key() -> None:
    first = _claim_payload()
    drifted = _claim_payload(
        exchange_instrument_id="instrument-opaque-2",
        action_time_lane_input_id="lane-input-2",
    )

    assert reservation_idempotency_key(first) == reservation_idempotency_key(drifted)
    assert capacity_claim_hash(first) != capacity_claim_hash(drifted)


def test_decimal_claim_hash_is_canonical_and_mutable_state_is_excluded() -> None:
    first = _claim_payload()
    same_value_different_decimal_scale = _claim_payload()
    same_value_different_decimal_scale = same_value_different_decimal_scale.model_copy(
        update={"planned_stop_risk": Decimal("4.000")}
    )

    assert capacity_claim_hash(first) == capacity_claim_hash(same_value_different_decimal_scale)
    assert "status" not in AccountCapacityClaimPayload.model_fields
    assert "margin_accounting_state" not in AccountCapacityClaimPayload.model_fields
