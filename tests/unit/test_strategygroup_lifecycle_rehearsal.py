from __future__ import annotations

import json
import subprocess
import sys

from scripts.build_strategygroup_lifecycle_rehearsal import (
    REQUIRED_SCENARIOS,
    build_lifecycle_rehearsal,
    validate_artifact,
)


def test_lifecycle_rehearsal_covers_major_non_live_branches() -> None:
    artifact = build_lifecycle_rehearsal()

    assert artifact["status"] == "lifecycle_rehearsal_ready"
    assert "decision" not in artifact
    assert validate_artifact(artifact) == []
    assert [row["scenario"] for row in artifact["scenario_rows"]] == REQUIRED_SCENARIOS
    assert artifact["cost_pnl_review"]["review_shape_ready"] is True
    runtime_safety = artifact["runtime_safety_state"]
    assert runtime_safety["state_family"] == "Runtime Safety State"
    assert runtime_safety["source_role"] == "lifecycle_rehearsal_evidence"
    assert runtime_safety["primary_judgment_source"] is False
    assert runtime_safety["tradeability_decision_source"] is False
    assert runtime_safety["execution_attempt_source"] is False
    assert "actionable_now" not in runtime_safety
    assert "real_order_authority" not in runtime_safety
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    for row in artifact["scenario_rows"]:
        assert "real_order_authority" not in row


def test_negative_missing_scenario_is_rejected() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["scenario_rows"] = artifact["scenario_rows"][:-1]

    errors = validate_artifact(artifact)

    assert "missing_scenario:rough_cost_pnl_review" in errors


def test_negative_exchange_write_is_rejected() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["scenario_rows"][0]["exchange_write"] = True

    errors = validate_artifact(artifact)

    assert "submit_accepted.exchange_write_not_false" in errors


def test_negative_top_level_decision_is_rejected() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["decision"] = {
        "default_next_step": "legacy_parallel_rehearsal_judgment_source",
    }

    errors = validate_artifact(artifact)

    assert "top_level_decision_removed" in errors


def test_negative_runtime_safety_cannot_answer_tradeability() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["runtime_safety_state"]["tradeability_decision_source"] = True

    errors = validate_artifact(artifact)

    assert "runtime_safety_state_must_not_answer_tradeability" in errors


def test_negative_runtime_safety_cannot_open_execution_attempt() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["runtime_safety_state"]["execution_attempt_source"] = True

    errors = validate_artifact(artifact)

    assert "runtime_safety_state_must_not_open_execution_attempt" in errors


def test_negative_legacy_authority_mirrors_are_rejected() -> None:
    artifact = build_lifecycle_rehearsal()
    artifact["runtime_safety_state"]["actionable_now"] = False
    artifact["runtime_safety_state"]["real_order_authority"] = False
    artifact["safety_invariants"]["actionable_now"] = False
    artifact["safety_invariants"]["real_order_authority"] = False
    artifact["scenario_rows"][0]["actionable_now"] = False
    artifact["scenario_rows"][0]["real_order_authority"] = False

    errors = validate_artifact(artifact)

    assert (
        "runtime_safety_state.legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "runtime_safety_state.legacy_authority_mirror_present:real_order_authority"
        in errors
    )
    assert "safety_invariant.legacy_authority_mirror_present:actionable_now" in errors
    assert (
        "safety_invariant.legacy_authority_mirror_present:real_order_authority"
        in errors
    )
    assert (
        "submit_accepted.legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "submit_accepted.legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_check_mode_passes_against_generated_lifecycle_rehearsal() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_lifecycle_rehearsal.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_lifecycle_rehearsal.py", "--check"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
