from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_btpc_fact_classifier_guard import (
    EXPECTED_STATUSES,
    build_btpc_fact_classifier_guard,
    validate_packet,
)


def _packet(status: str) -> dict:
    return {
        "status": status,
        "interaction": {
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "decision": {
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "runtime_started": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "tier_policy_changed": False,
            "l2_promotion_authorized": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _guard_packet() -> dict:
    return build_btpc_fact_classifier_guard(
        l2_decision=_packet(
            EXPECTED_STATUSES["btpc_l2_keep_revise_fact_source_decision"]
        ),
        live_source_mapping=_packet(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_packet(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )


def test_btpc_fact_classifier_guard_rolls_up_ready_inputs_without_live_authority() -> None:
    packet = _guard_packet()

    assert packet["status"] == "btpc_fact_classifier_guard_ready"
    assert validate_packet(packet) == []
    assert packet["btpc_state"]["actionable_now"] is False
    assert packet["btpc_state"]["real_order_authority"] is False
    assert packet["decision"]["owner_risk_acceptance_cannot_set_actionable_now_true"] is True


def test_negative_missing_ready_source_status_is_rejected() -> None:
    packet = build_btpc_fact_classifier_guard(
        l2_decision=_packet("wrong_status"),
        live_source_mapping=_packet(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_packet(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )

    assert packet["status"] == "btpc_fact_classifier_guard_failed"
    assert any(
        error.startswith("btpc_l2_keep_revise_fact_source_decision.unexpected_status")
        for error in packet["validation_errors"]
    )


def test_negative_live_authority_flag_is_rejected() -> None:
    packet = _guard_packet()
    packet["btpc_state"]["real_order_authority"] = True

    errors = validate_packet(packet)

    assert "btpc_state_not_false:real_order_authority" in errors


def test_check_mode_passes_after_real_btpc_guard_generation() -> None:
    required = [
        Path("output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"),
        Path("output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"),
        Path("output/runtime-monitor/latest-btpc-classifier-rule-review.json"),
    ]
    if not all(path.exists() for path in required):
        return
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_btpc_fact_classifier_guard.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_btpc_fact_classifier_guard.py", "--check"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
