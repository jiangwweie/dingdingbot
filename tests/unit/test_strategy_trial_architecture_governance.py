from __future__ import annotations

from decimal import Decimal

from src.application.strategy_trial_architecture_governance import (
    MinimalLiveTrialGateRequest,
    StrategyTrialHardBlocker,
    build_bnb_strategy_trial_architecture_governance,
    evaluate_minimal_live_trial_gate,
)


def test_strategy_family_does_not_imply_order_authority():
    review = build_bnb_strategy_trial_architecture_governance()

    carrier = review.owner_review_packet.carrier
    assert carrier.strategy_family == "MI-001"
    assert carrier.carrier_id == "MI-001-BNB-LONG"
    assert carrier.strategy_family_order_authority is False
    assert carrier.carrier_is_order_authority is False
    assert review.non_permissions["no_execution_intent"] is True
    assert review.non_permissions["no_order_creation"] is True


def test_bnb_is_first_carrier_not_whole_architecture():
    review = build_bnb_strategy_trial_architecture_governance()

    carrier = review.owner_review_packet.carrier
    assert carrier.symbol == "BNBUSDT"
    assert carrier.runtime_symbol == "BNB/USDT:USDT"
    assert carrier.side == "long"
    assert carrier.max_notional == Decimal("20")
    assert carrier.protection_plan_type == "single_tp_plus_sl"
    assert review.bnb_state == "bnb_first_carrier_consolidated"
    assert any(
        item.concept == "Carrier" and item.classification == "carrier-specific by design"
        for item in review.architecture_classification
    )
    assert any(
        item.concept == "MinimalLiveTrialGate" and item.classification == "generic-ready"
        for item in review.architecture_classification
    )


def test_strategy_warnings_require_ack_but_are_not_hard_blockers():
    review = build_bnb_strategy_trial_architecture_governance()

    warning_ids = {warning.warning_id for warning in review.owner_review_packet.strategy_warnings}
    assert "strategy_not_proven_profitable" in warning_ids
    assert "forward_review_incomplete" in warning_ids
    assert all(
        warning.owner_ack_required and warning.blocks_after_ack is False
        for warning in review.owner_review_packet.strategy_warnings
    )
    assert review.minimal_live_trial_gate.acknowledgement_blockers == [
        "strategy_risk_acknowledgement_required"
    ]
    assert "strategy_risk_acknowledgement_required" not in review.minimal_live_trial_gate.hard_blockers


def test_acknowledged_strategy_warnings_do_not_block_after_owner_live_authorization():
    review = build_bnb_strategy_trial_architecture_governance(
        warnings_acknowledged=True,
        explicit_owner_live_authorization_exists=True,
    )

    assert review.authorization_draft.owner_confirmed is True
    assert review.authorization_draft.live_ready is False
    assert review.minimal_live_trial_gate.can_execute_bounded_live_trial is True
    assert review.minimal_live_trial_gate.hard_blockers == []
    assert review.minimal_live_trial_gate.acknowledgement_blockers == []
    assert review.minimal_live_trial_gate.execution_intent_created is False
    assert review.minimal_live_trial_gate.order_created is False


def test_missing_explicit_owner_live_authorization_blocks_live_execution():
    review = build_bnb_strategy_trial_architecture_governance(warnings_acknowledged=True)

    assert review.final_state == "strategy_trial_architecture_governed"
    assert review.authorization_draft.pending_owner_live_authorization is True
    assert review.authorization_draft.owner_confirmed is False
    assert review.minimal_live_trial_gate.can_execute_bounded_live_trial is False
    assert review.minimal_live_trial_gate.hard_blockers == ["live_authorization_missing"]
    assert review.minimal_live_trial_gate.final_state == "blocked_missing_owner_live_authorization"
    assert review.not_live_ready_until_explicit_owner_live_authorization is True


def test_hard_blockers_always_block_even_after_ack_and_owner_authorization():
    review = build_bnb_strategy_trial_architecture_governance(
        warnings_acknowledged=True,
        explicit_owner_live_authorization_exists=True,
        active_hard_blockers=[
            StrategyTrialHardBlocker(
                blocker_id="gks_blocked",
                active=True,
                description="GKS active",
                source="unit",
            )
        ],
    )

    assert review.final_state == (
        "strategy_trial_architecture_governance_blocked_with_explicit_hard_blockers"
    )
    assert review.minimal_live_trial_gate.can_execute_bounded_live_trial is False
    assert "gks_blocked" in review.minimal_live_trial_gate.hard_blockers


def test_authorization_scope_rejects_wrong_symbol_side_and_cap_violation():
    base = build_bnb_strategy_trial_architecture_governance(
        warnings_acknowledged=True,
        explicit_owner_live_authorization_exists=True,
    )
    gate = evaluate_minimal_live_trial_gate(
        authorization=base.authorization_draft,
        request=MinimalLiveTrialGateRequest(
            carrier_id="MI-001-BNB-LONG",
            symbol="SOL/USDT:USDT",
            side="short",
            requested_notional=Decimal("21"),
            protection_plan_type="single_tp_plus_sl",
            explicit_owner_live_authorization_exists=True,
            warnings_acknowledged=True,
        ),
        strategy_warnings=base.owner_review_packet.strategy_warnings,
        hard_blockers=[],
    )

    assert gate.can_execute_bounded_live_trial is False
    assert "symbol_mismatch" in gate.hard_blockers
    assert "side_mismatch" in gate.hard_blockers
    assert "cap_violation" in gate.hard_blockers
    assert gate.order_created is False


def test_protection_impossible_blocks_live_trial():
    base = build_bnb_strategy_trial_architecture_governance(
        warnings_acknowledged=True,
        explicit_owner_live_authorization_exists=True,
    )
    gate = evaluate_minimal_live_trial_gate(
        authorization=base.authorization_draft,
        request=MinimalLiveTrialGateRequest(
            carrier_id="MI-001-BNB-LONG",
            symbol="BNB/USDT:USDT",
            side="long",
            requested_notional=Decimal("20"),
            protection_plan_type="blocked_unprotectable_size",
            explicit_owner_live_authorization_exists=True,
            warnings_acknowledged=True,
        ),
        strategy_warnings=base.owner_review_packet.strategy_warnings,
        hard_blockers=[],
    )

    assert gate.can_execute_bounded_live_trial is False
    assert gate.hard_blockers == ["protection_not_executable"]
    assert gate.execution_permission_granted is False
