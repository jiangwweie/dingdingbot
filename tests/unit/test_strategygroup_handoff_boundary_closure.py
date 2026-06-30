from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_handoff_boundary_closure import (
    REQUIRED_EXPLICIT_MISSING_GROUPS,
    build_handoff_boundary_closure,
    validate_artifact,
)


QUALITY_WAVE_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)


def _quality_wave() -> dict:
    return json.loads(QUALITY_WAVE_PATH.read_text(encoding="utf-8"))


def test_handoff_boundary_closure_records_vcb_lsr_brf_explicit_boundaries() -> None:
    artifact = build_handoff_boundary_closure(_quality_wave())

    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}
    assert artifact["status"] == "handoff_boundary_closure_ready"
    assert "decision" not in artifact
    assert validate_artifact(artifact) == []
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert review_outcome["source_role"] == "handoff_boundary_closure_lifecycle_evidence"
    assert review_outcome["primary_judgment_source"] is False
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["promote_or_live_authority_created"] is False
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    for group in REQUIRED_EXPLICIT_MISSING_GROUPS:
        assert rows[group]["boundary_state"] == "explicit_missing_handoff_boundary_accepted"
        assert rows[group]["handoff_pack_present"] is False
        assert "actionable_now" not in rows[group]
        assert "real_order_authority" not in rows[group]


def test_negative_missing_required_boundary_is_rejected() -> None:
    artifact = build_handoff_boundary_closure(_quality_wave())
    artifact["rows"] = [
        row for row in artifact["rows"] if row["strategy_group_id"] != "VCB-001"
    ]

    errors = validate_artifact(artifact)

    assert "VCB-001.missing_boundary_row" in errors


def test_negative_row_legacy_authority_mirror_is_rejected() -> None:
    artifact = build_handoff_boundary_closure(_quality_wave())
    row = next(row for row in artifact["rows"] if row["strategy_group_id"] == "LSR-001")
    row["actionable_now"] = True

    errors = validate_artifact(artifact)

    assert (
        "LSR-001.handoff_boundary_row_legacy_authority_mirror_present:actionable_now"
        in errors
    )


def test_source_rows_follow_quality_wave_boundary_state() -> None:
    quality_wave = deepcopy(_quality_wave())
    for row in quality_wave["rows"]:
        if row["strategy_group_id"] == "BRF-001":
            row["source_coverage"]["handoff_pack"] = True

    artifact = build_handoff_boundary_closure(quality_wave)

    errors = validate_artifact(artifact)
    assert "BRF-001.handoff_pack_unexpectedly_present" in errors


def test_negative_top_level_decision_is_rejected() -> None:
    artifact = build_handoff_boundary_closure(_quality_wave())
    artifact["decision"] = {
        "default_next_step": "legacy_parallel_judgment_source",
    }

    errors = validate_artifact(artifact)

    assert "top_level_decision_removed" in errors


def test_negative_review_outcome_cannot_answer_tradeability() -> None:
    artifact = build_handoff_boundary_closure(_quality_wave())
    artifact["review_outcome_state"]["tradeability_decision_source"] = True

    errors = validate_artifact(artifact)

    assert "review_outcome_state_must_not_answer_tradeability" in errors


def test_check_mode_passes_against_generated_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_handoff_boundary_closure.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_handoff_boundary_closure.py",
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
