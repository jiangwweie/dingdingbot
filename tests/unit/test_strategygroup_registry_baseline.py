from __future__ import annotations

import json
import subprocess
import sys

from scripts.build_strategygroup_registry_baseline import (
    EXPECTED_GROUPS,
    RISK_CLASS_KEYS,
    build_owner_markdown,
    build_registry_baseline,
    validate_artifact,
)


FORBIDDEN_TRUE_FLAGS = {
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
    "changes_live_profile",
    "changes_order_sizing_defaults",
    "withdrawal_or_transfer",
}


def test_registry_baseline_schema_and_expected_rows() -> None:
    artifact = build_registry_baseline()

    assert artifact["schema"] == "brc.strategygroup_registry_baseline.v1"
    assert [row["strategy_group_id"] for row in artifact["rows"]] == EXPECTED_GROUPS
    assert len(artifact["rows"]) == 11
    assert validate_artifact(artifact) == []


def test_static_registry_never_grants_runtime_authority() -> None:
    artifact = build_registry_baseline()

    assert artifact["runtime_authority_contract"]["runtime_authority_sources"] == [
        "Tradeability Decision",
        "Runtime Safety State",
    ]
    assert artifact["runtime_authority_contract"][
        "static_rows_must_not_grant_runtime_authority"
    ] is True
    assert "actionability_contract" not in artifact
    for row in artifact["rows"]:
        assert "actionable_now" not in row
        assert "actionable_now_reason" not in row
        assert "real_order_authority" not in row


def test_negative_static_row_legacy_authority_mirror_is_rejected() -> None:
    artifact = build_registry_baseline()
    artifact["rows"][0]["actionable_now"] = True
    artifact["rows"][0]["actionable_now_reason"] = "legacy mirror"
    artifact["rows"][1]["real_order_authority"] = True

    errors = validate_artifact(artifact)

    assert (
        "MPG-001.static_row_legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "MPG-001.static_row_legacy_authority_mirror_present:actionable_now_reason"
        in errors
    )
    assert (
        "CPM-RO-001.static_row_legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_registry_has_no_live_authority_flags() -> None:
    artifact = build_registry_baseline()

    assert all(artifact["safety_invariants"][flag] is False for flag in FORBIDDEN_TRUE_FLAGS)
    assert "real_order_authority" not in artifact["safety_invariants"]
    for row in artifact["rows"]:
        assert "real_order_authority" not in row["safety_invariants"]
        assert row["safety_invariants"]["calls_finalgate"] is False
        assert row["safety_invariants"]["calls_operation_layer"] is False
        assert row["safety_invariants"]["calls_exchange_write"] is False
        assert row["safety_invariants"]["places_order"] is False
        assert "does not authorize" in row["authority_boundary"]


def test_risk_classes_keep_owner_acceptance_boundary() -> None:
    artifact = build_registry_baseline()

    for row in artifact["rows"]:
        assert sorted(row["risk_gaps"]) == sorted(RISK_CLASS_KEYS)
        assert row["risk_gaps"]["strategy_quality_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["fact_coverage_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["economic_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["execution_safety_risk"]["owner_can_accept"] is False
        assert row["risk_gaps"]["authority_risk"]["owner_can_accept"] is False


def test_evidence_refs_are_nonempty_and_path_deduped() -> None:
    artifact = build_registry_baseline()

    for row in artifact["rows"]:
        paths = [ref["path"] for ref in row["evidence_refs"]]
        assert paths
        assert len(paths) == len(set(paths)), row["strategy_group_id"]


def test_owner_markdown_includes_all_groups_and_boundary() -> None:
    artifact = build_registry_baseline()
    markdown = build_owner_markdown(artifact)

    for group in EXPECTED_GROUPS:
        assert group in markdown
    assert "actionable_now" not in markdown
    assert "runtime-only" in markdown
    assert "does not authorize" in markdown


def test_check_mode_passes_against_generated_files() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_registry_baseline.py",
            "--check",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    assert report["row_count"] == 11
    assert report["errors"] == []
