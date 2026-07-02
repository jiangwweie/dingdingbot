from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_btpc_fact_classifier_guard import (
    EXPECTED_STATUSES,
    build_btpc_fact_classifier_guard,
    validate_artifact,
)


def _artifact(status: str) -> dict:
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
        "review_outcome_state": {
            "default_next_step": "continue_source_review",
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "tradeability_decision_source": False,
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


def _guard_artifact() -> dict:
    return build_btpc_fact_classifier_guard(
        l2_decision=_artifact(
            EXPECTED_STATUSES["btpc_l2_keep_revise_fact_source_review"]
        ),
        live_source_mapping=_artifact(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_artifact(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )


def test_btpc_fact_classifier_guard_rolls_up_ready_inputs_without_live_authority() -> None:
    artifact = _guard_artifact()

    assert artifact["status"] == "btpc_fact_classifier_guard_ready"
    assert validate_artifact(artifact) == []
    assert "actionable_now" not in artifact["btpc_state"]
    assert "real_order_authority" not in artifact["btpc_state"]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert "decision" not in artifact["btpc_state"]
    assert artifact["btpc_state"]["current_review_outcome"] == "revise"
    assert "decision" not in artifact
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert review_outcome["source_role"] == "btpc_fact_classifier_guard_provenance"
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["runtime_authority_sources"] == [
        "Tradeability Decision",
        "Runtime Safety State",
    ]
    assert review_outcome["owner_risk_acceptance_cannot_grant_runtime_authority"] is True
    assert "owner_risk_acceptance_cannot_set_actionable_now_true" not in review_outcome


def test_negative_missing_ready_source_status_is_rejected() -> None:
    artifact = build_btpc_fact_classifier_guard(
        l2_decision=_artifact("wrong_status"),
        live_source_mapping=_artifact(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_artifact(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )

    assert artifact["status"] == "btpc_fact_classifier_guard_failed"
    assert any(
        error.startswith("btpc_l2_keep_revise_fact_source_review.unexpected_status")
        for error in artifact["validation_errors"]
    )


def test_negative_source_without_review_outcome_default_step_is_rejected() -> None:
    source = _artifact(EXPECTED_STATUSES["btpc_l2_keep_revise_fact_source_review"])
    source.pop("review_outcome_state")

    artifact = build_btpc_fact_classifier_guard(
        l2_decision=source,
        live_source_mapping=_artifact(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_artifact(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )

    assert artifact["status"] == "btpc_fact_classifier_guard_failed"
    assert (
        "btpc_l2_keep_revise_fact_source_review."
        "missing_review_outcome_default_next_step"
    ) in artifact["validation_errors"]


def test_negative_source_review_outcome_cannot_answer_tradeability() -> None:
    source = _artifact(EXPECTED_STATUSES["btpc_l2_keep_revise_fact_source_review"])
    source["review_outcome_state"]["tradeability_decision_source"] = True

    artifact = build_btpc_fact_classifier_guard(
        l2_decision=source,
        live_source_mapping=_artifact(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_artifact(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )

    assert artifact["status"] == "btpc_fact_classifier_guard_failed"
    assert (
        "btpc_l2_keep_revise_fact_source_review."
        "review_outcome_must_not_answer_tradeability"
    ) in artifact["validation_errors"]


def test_negative_source_authority_mirror_fields_are_rejected() -> None:
    source = _artifact(EXPECTED_STATUSES["btpc_l2_keep_revise_fact_source_review"])
    source["safety_invariants"]["real_order_authority"] = False
    source["review_outcome_state"]["actionable_now"] = False
    source["action_rows"] = [
        {
            "action": "review_btpc_strong_uptrend_conflict_disable_rule",
            "real_order_authority": False,
        }
    ]

    artifact = build_btpc_fact_classifier_guard(
        l2_decision=source,
        live_source_mapping=_artifact(
            EXPECTED_STATUSES["btpc_live_derivatives_fact_source_mapping"]
        ),
        classifier_rule_review=_artifact(
            EXPECTED_STATUSES["btpc_classifier_rule_review"]
        ),
    )

    assert artifact["status"] == "btpc_fact_classifier_guard_failed"
    assert (
        "btpc_l2_keep_revise_fact_source_review."
        "safety_invariants.legacy_authority_mirror_present:real_order_authority"
    ) in artifact["validation_errors"]
    assert (
        "btpc_l2_keep_revise_fact_source_review."
        "review_outcome_state.legacy_authority_mirror_present:actionable_now"
    ) in artifact["validation_errors"]
    assert (
        "btpc_l2_keep_revise_fact_source_review."
        "action_rows.review_btpc_strong_uptrend_conflict_disable_rule."
        "legacy_authority_mirror_present:real_order_authority"
    ) in artifact["validation_errors"]


def test_negative_exchange_write_safety_flag_is_rejected() -> None:
    artifact = _guard_artifact()
    artifact["safety_invariants"]["exchange_write_called"] = True

    errors = validate_artifact(artifact)

    assert "safety_invariants_not_false:exchange_write_called" in errors


def test_negative_legacy_top_level_decision_is_rejected() -> None:
    artifact = _guard_artifact()
    artifact["decision"] = {
        "real_order_scope_change_recommended": False,
    }

    errors = validate_artifact(artifact)

    assert "legacy_top_level_decision_present" in errors


def test_negative_legacy_btpc_state_decision_is_rejected() -> None:
    artifact = _guard_artifact()
    artifact["btpc_state"]["decision"] = "revise"

    errors = validate_artifact(artifact)

    assert "btpc_state_legacy_decision_present" in errors


def test_negative_review_outcome_tradeability_source_is_rejected() -> None:
    artifact = _guard_artifact()
    artifact["review_outcome_state"]["tradeability_decision_source"] = True

    errors = validate_artifact(artifact)

    assert "review_outcome_state_must_not_answer_tradeability" in errors


def test_check_mode_passes_after_real_btpc_guard_generation() -> None:
    required = [
        Path("output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.json"),
        Path("output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"),
        Path("output/runtime-monitor/latest-btpc-classifier-rule-review.json"),
    ]
    if not all(path.exists() for path in required):
        return
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_btpc_fact_classifier_guard.py",
            "--btpc-l2-review-json",
            str(required[0]),
            "--btpc-live-source-mapping-json",
            str(required[1]),
            "--btpc-classifier-rule-review-json",
            str(required[2]),
        ],
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


def test_btpc_fact_classifier_guard_cli_omitted_inputs_do_not_read_defaults(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "guard.json"
    owner_path = tmp_path / "guard.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_btpc_fact_classifier_guard.py",
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["status"] == "btpc_fact_classifier_guard_failed"
    rows = {row["artifact"]: row for row in artifact["source_rows"]}
    assert rows["btpc_l2_keep_revise_fact_source_review"]["status"] is None
    assert rows["btpc_live_derivatives_fact_source_mapping"]["status"] is None
    assert rows["btpc_classifier_rule_review"]["status"] is None
