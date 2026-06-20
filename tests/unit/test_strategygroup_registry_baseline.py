from __future__ import annotations

import json
import subprocess
import sys

from scripts.build_strategygroup_registry_baseline import (
    EXPECTED_GROUPS,
    RISK_CLASS_KEYS,
    build_owner_markdown,
    build_registry_baseline,
    validate_packet,
)


FORBIDDEN_TRUE_FLAGS = {
    "real_order_authority",
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
    "changes_live_profile",
    "changes_order_sizing_defaults",
    "withdrawal_or_transfer",
}


def test_registry_baseline_schema_and_expected_rows() -> None:
    packet = build_registry_baseline()

    assert packet["schema"] == "brc.strategygroup_registry_baseline.v1"
    assert [row["strategy_group_id"] for row in packet["rows"]] == EXPECTED_GROUPS
    assert len(packet["rows"]) == 10
    assert validate_packet(packet) == []


def test_static_registry_never_marks_rows_actionable_now() -> None:
    packet = build_registry_baseline()

    assert packet["actionability_contract"]["actionable_now_source"] == (
        "runtime_state_only"
    )
    assert packet["actionability_contract"][
        "static_rows_must_not_set_actionable_now_true"
    ] is True
    assert all(row["actionable_now"] is False for row in packet["rows"])
    assert all("runtime_state_only" in row["actionable_now_reason"] for row in packet["rows"])


def test_registry_has_no_live_authority_flags() -> None:
    packet = build_registry_baseline()

    assert all(packet["safety_invariants"][flag] is False for flag in FORBIDDEN_TRUE_FLAGS)
    for row in packet["rows"]:
        assert row["safety_invariants"]["real_order_authority"] is False
        assert row["safety_invariants"]["calls_finalgate"] is False
        assert row["safety_invariants"]["calls_operation_layer"] is False
        assert row["safety_invariants"]["calls_exchange_write"] is False
        assert row["safety_invariants"]["places_order"] is False
        assert "does not authorize" in row["authority_boundary"]


def test_risk_classes_keep_owner_acceptance_boundary() -> None:
    packet = build_registry_baseline()

    for row in packet["rows"]:
        assert sorted(row["risk_gaps"]) == sorted(RISK_CLASS_KEYS)
        assert row["risk_gaps"]["strategy_quality_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["fact_coverage_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["economic_risk"]["owner_can_accept"] is True
        assert row["risk_gaps"]["execution_safety_risk"]["owner_can_accept"] is False
        assert row["risk_gaps"]["authority_risk"]["owner_can_accept"] is False


def test_evidence_refs_are_nonempty_and_path_deduped() -> None:
    packet = build_registry_baseline()

    for row in packet["rows"]:
        paths = [ref["path"] for ref in row["evidence_refs"]]
        assert paths
        assert len(paths) == len(set(paths)), row["strategy_group_id"]


def test_owner_markdown_includes_all_groups_and_boundary() -> None:
    packet = build_registry_baseline()
    markdown = build_owner_markdown(packet)

    for group in EXPECTED_GROUPS:
        assert group in markdown
    assert "actionable_now" in markdown
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
    assert report["row_count"] == 10
    assert report["errors"] == []
