from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from scripts.build_strategygroup_quality_wave import (
    INCLUDED_GROUPS,
    build_quality_wave_packet,
    load_inputs,
    validate_packet,
)


REGISTRY_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
TIER_REVIEW_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json"
)
DECISION_LEDGER_PATH = Path(
    "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)
TIER_POLICY_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
REQUIRED_FACTS_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-required-facts-map.md"
)
LOCAL_MONITOR_PATH = Path("output/runtime-monitor/latest-local-monitor-sequence.json")


def _packet():
    inputs = load_inputs(
        REGISTRY_PATH,
        TIER_REVIEW_PATH,
        DECISION_LEDGER_PATH,
        TIER_POLICY_PATH,
        REQUIRED_FACTS_PATH,
        LOCAL_MONITOR_PATH,
    )
    return build_quality_wave_packet(*inputs)


def test_quality_wave_has_one_source_derived_row_per_included_group() -> None:
    packet = _packet()

    assert packet["schema"] == "brc.strategygroup_quality_wave.v1"
    assert [row["strategy_group_id"] for row in packet["rows"]] == INCLUDED_GROUPS
    assert len(packet["rows"]) == 5
    assert validate_packet(packet) == []


def test_quality_wave_records_required_source_coverage() -> None:
    packet = _packet()

    coverage = packet["source_coverage"]
    assert coverage["BTPC-001"]["handoff_pack"] is True
    assert coverage["BTPC-001"]["replay_corpus"] is True
    assert coverage["BTPC-001"]["required_facts_mapping"] is True
    assert coverage["VCB-001"]["handoff_pack"] is False
    assert coverage["LSR-001"]["handoff_pack"] is False
    assert coverage["BRF-001"]["handoff_pack"] is False
    assert coverage["RBR-001"]["replay_corpus"] is False
    for group in INCLUDED_GROUPS:
        assert coverage[group]["registry_baseline_row"] is True
        assert coverage[group]["tier_review_row"] is True
        assert coverage[group]["decision_ledger_row"] is True
        assert coverage[group]["local_monitor_entrypoint"]


def test_quality_wave_classifies_current_gap_matrix() -> None:
    packet = _packet()
    rows = {row["strategy_group_id"]: row for row in packet["rows"]}

    assert rows["BTPC-001"]["primary_gap_class"] == "fact_source_gap"
    assert rows["BTPC-001"]["secondary_gap_class"] == "classifier_gap"
    assert rows["VCB-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["LSR-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["BRF-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["RBR-001"]["primary_gap_class"] == "parked_low_priority_gap"
    assert rows["RBR-001"]["system_can_continue"] is False


def test_gap_closures_span_three_findings_and_two_groups_with_shared_guard() -> None:
    packet = _packet()

    closures = packet["closures"]
    assert len(closures) >= 3
    groups = {closure["strategy_group_id"] for closure in closures}
    assert len(groups - {""}) >= 2
    assert any(closure["shared_infrastructure"] is True for closure in closures)
    assert any(
        closure["proves_owner_risk_acceptance_not_actionability"] is True
        for closure in closures
    )


def test_owner_risk_acceptance_never_sets_static_actionability() -> None:
    packet = _packet()

    assert packet["global_authority_model"][
        "owner_risk_acceptance_cannot_set_actionable_now_true"
    ] is True
    assert packet["safety_invariants"]["actionable_now"] is False
    assert all(row["actionable_now"] is False for row in packet["rows"])
    assert all(row["owner_policy_action_required"] is False for row in packet["rows"])


def test_negative_actionable_now_true_is_rejected() -> None:
    packet = _packet()
    packet["rows"][0]["actionable_now"] = True

    errors = validate_packet(packet)

    assert "BTPC-001.actionable_now_true" in errors


def test_negative_owner_operator_requirement_is_rejected() -> None:
    packet = _packet()
    packet["rows"][1]["owner_policy_action_required"] = True

    errors = validate_packet(packet)

    assert "VCB-001.unexpected_owner_operator_requirement" in errors


def test_negative_missing_shared_closure_is_rejected() -> None:
    packet = _packet()
    for closure in packet["closures"]:
        closure["shared_infrastructure"] = False

    errors = validate_packet(packet)

    assert "missing_shared_infrastructure_closure" in errors


def test_negative_unknown_gap_class_is_rejected() -> None:
    packet = _packet()
    packet["rows"][0]["primary_gap_class"] = "unknown_gap"

    errors = validate_packet(packet)

    assert "BTPC-001.primary_gap_class_unknown:unknown_gap" in errors


def test_contradiction_detection_reports_registry_tier_drift() -> None:
    inputs = list(
        load_inputs(
            REGISTRY_PATH,
            TIER_REVIEW_PATH,
            DECISION_LEDGER_PATH,
            TIER_POLICY_PATH,
            REQUIRED_FACTS_PATH,
            LOCAL_MONITOR_PATH,
        )
    )
    registry = deepcopy(inputs[0])
    for row in registry["rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["default_tier"] = "L1"
    inputs[0] = registry

    packet = build_quality_wave_packet(*inputs)

    assert any(
        item["strategy_group_id"] == "BTPC-001"
        and item["source"] in {"tier_review", "decision_ledger", "tier_policy"}
        for item in packet["contradictions"]
    )


def test_check_mode_passes_against_generated_files() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_quality_wave.py", "--check"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    assert report["row_count"] == 5
    assert report["closure_count"] >= 3
    assert report["contradiction_count"] == 0
