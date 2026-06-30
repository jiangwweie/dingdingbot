from __future__ import annotations

from src.domain import runtime_readiness_state
from src.domain.runtime_readiness_state import (
    NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS,
    candidate_authorization_state_from_runtime_safety_artifact,
    candidate_authorization_state_from_source,
    false_flag_errors,
    live_submit_ready_for_strategy_artifact,
    non_authoritative_state_errors,
    readiness_separation_from_runtime_safety_artifact,
)


def test_packet_compatibility_aliases_are_not_runtime_readiness_boundary() -> None:
    assert not hasattr(runtime_readiness_state, "runtime_safety_state_from_packet")
    assert not hasattr(
        runtime_readiness_state,
        "readiness_separation_from_runtime_safety_packet",
    )
    assert not hasattr(runtime_readiness_state, "live_submit_ready_for_strategy")
    assert not hasattr(runtime_readiness_state, "scoped_strategy_group_ids")


def test_pre_live_rehearsal_ready_does_not_create_execution_attempt() -> None:
    artifact = {
        "runtime_safety_state": {
            "pre_live_rehearsal_ready": True,
            "live_submit_ready": False,
            "ready_for_finalgate_checkpoint": False,
            "fresh_signal_state": "none",
            "live_submit_ready_false_reason": "no_fresh_signal",
        }
    }

    separation = readiness_separation_from_runtime_safety_artifact(artifact)

    assert separation.pre_live_rehearsal_ready is True
    assert separation.live_submit_ready is False
    assert separation.can_create_execution_attempt is False
    read_model = separation.as_read_model()
    assert "actionable_now" not in read_model
    assert "real_order_authority" not in read_model
    assert read_model["execution_attempt_required_for_lifecycle_entry"] is True
    assert read_model["live_submit_ready_source"] == "Runtime Safety action-time chain"
    assert "live_submit_ready_authority" not in read_model


def test_scoped_live_submit_ready_can_only_enter_matching_strategy() -> None:
    artifact = {
        "selected_strategy_group_id": "MPG-001",
        "runtime_scope": {"strategy_group_id": "MPG-001"},
        "runtime_safety_state": {
            "live_submit_ready": True,
            "ready_for_finalgate_checkpoint": True,
            "fresh_signal_state": "fresh",
        },
    }

    assert live_submit_ready_for_strategy_artifact(
        artifact=artifact,
        strategy_group_id="MPG-001",
    )
    assert not live_submit_ready_for_strategy_artifact(
        artifact=artifact,
        strategy_group_id="BRF2-001",
    )


def test_legacy_live_submit_mirrors_are_not_runtime_authority() -> None:
    artifact = {
        "selected_strategy_group_id": "MPG-001",
        "checks": {"live_submit_ready": True},
        "decision": {
            "live_submit_ready": True,
            "actionable_now": True,
            "real_order_authority": True,
        },
    }

    separation = readiness_separation_from_runtime_safety_artifact(artifact)

    assert separation.live_submit_ready is False
    assert separation.can_create_execution_attempt is False
    assert "actionable_now" not in separation.as_read_model()
    assert "real_order_authority" not in separation.as_read_model()
    assert not live_submit_ready_for_strategy_artifact(
        artifact=artifact,
        strategy_group_id="MPG-001",
    )


def test_candidate_authorization_state_projection_strips_legacy_authority_mirrors() -> None:
    projection = candidate_authorization_state_from_source(
        {
            "state_source": "brf2_shadow_candidate_evidence",
            "strategy_group_id": "BRF2-001",
            "status": "candidate_authorization_evidence_pending",
            "primary_judgment_source": True,
            "shadow_candidate_evidence_ready": True,
            "authorization_evidence_created": False,
            "ready_for_finalgate_checkpoint": False,
            "first_blocker_class": (
                "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
            ),
            "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
            "live_submit_authority": False,
            "operation_layer_authority": False,
            "actionable_now": False,
            "real_order_authority": False,
        }
    )

    assert projection == {
        "state_family": "Runtime Safety State",
        "state_role": "candidate_authorization",
        "state_source": "brf2_shadow_candidate_evidence",
        "strategy_group_id": "BRF2-001",
        "status": "candidate_authorization_evidence_pending",
        "primary_judgment_source": False,
        "shadow_candidate_evidence_ready": True,
        "authorization_evidence_created": False,
        "ready_for_finalgate_checkpoint": False,
        "first_blocker_class": (
            "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
        ),
        "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
        "execution_attempt_required_for_lifecycle_entry": True,
    }
    assert "live_submit_authority" not in projection
    assert "operation_layer_authority" not in projection
    assert "actionable_now" not in projection
    assert "real_order_authority" not in projection


def test_candidate_authorization_state_read_from_runtime_safety_is_strategy_scoped() -> None:
    artifact = {
        "runtime_safety_state": {
            "candidate_authorization_state": {
                "state_family": "Runtime Safety State",
                "state_role": "candidate_authorization",
                "state_source": "brf2_shadow_candidate_evidence",
                "strategy_group_id": "BRF2-001",
                "status": "candidate_authorization_evidence_pending",
                "shadow_candidate_evidence_ready": True,
                "authorization_evidence_created": False,
            }
        }
    }

    assert candidate_authorization_state_from_runtime_safety_artifact(
        artifact,
        strategy_group_id="BRF2-001",
    )["status"] == "candidate_authorization_evidence_pending"
    assert candidate_authorization_state_from_runtime_safety_artifact(
        artifact,
        strategy_group_id="MPG-001",
    ) == {}


def test_non_authoritative_state_errors_preserve_boundary_error_names() -> None:
    errors = non_authoritative_state_errors(
        {
            "primary_judgment_source": True,
            "tradeability_decision_source": True,
            "execution_attempt_source": True,
            "actionable_now": True,
            "real_order_authority": True,
        },
        error_prefix="runtime_safety_state",
        false_keys=(
            "primary_judgment_source",
            "tradeability_decision_source",
            "execution_attempt_source",
            "actionable_now",
            "real_order_authority",
        ),
    )

    assert errors == [
        "runtime_safety_state_must_not_be_primary",
        "runtime_safety_state_must_not_answer_tradeability",
        "runtime_safety_state_must_not_open_execution_attempt",
        "runtime_safety_state_not_false:actionable_now",
        "runtime_safety_state_not_false:real_order_authority",
    ]


def test_false_flag_errors_preserve_safety_invariant_error_names() -> None:
    errors = false_flag_errors(
        {
            "final_gate_called": True,
            "operation_layer_called": True,
            "exchange_write_called": True,
            "order_created": True,
            "live_profile_changed": True,
            "order_sizing_defaults_changed": True,
            "withdrawal_or_transfer_created": True,
        },
        error_prefix="safety_invariant",
        false_keys=NON_EXECUTING_SIDE_EFFECT_FALSE_KEYS,
    )

    assert errors == [
        "safety_invariant_not_false:final_gate_called",
        "safety_invariant_not_false:operation_layer_called",
        "safety_invariant_not_false:exchange_write_called",
        "safety_invariant_not_false:order_created",
        "safety_invariant_not_false:live_profile_changed",
        "safety_invariant_not_false:order_sizing_defaults_changed",
        "safety_invariant_not_false:withdrawal_or_transfer_created",
    ]
