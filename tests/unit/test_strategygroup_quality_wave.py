from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from scripts.build_strategygroup_quality_wave import (
    INCLUDED_GROUPS,
    build_quality_wave_artifact,
    validate_artifact,
)


REGISTRY_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
TIER_REVIEW_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json"
)
CURRENT_QUALITY_WAVE_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)
TIER_POLICY_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
REQUIRED_FACTS_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-required-facts-map.md"
)
LOCAL_MONITOR_PATH = Path("output/runtime-monitor/latest-local-monitor-sequence.json")


def _strategy_asset_state_source() -> dict:
    current = json.loads(CURRENT_QUALITY_WAVE_PATH.read_text(encoding="utf-8"))
    asset_rows = []
    for row in current["rows"]:
        decision = row["current_decision"]
        if decision == "promote_review_only":
            decision = "promote"
        asset_rows.append(
            {
                "strategy_group_id": row["strategy_group_id"],
                "current_tier": row["current_tier"],
                "current_decision": decision,
                "promotion_scope": row["promotion_scope"],
                "promotion_target": row["promotion_target"],
                "required_next_evidence": row["required_next_evidence"],
                "next_checkpoint": row["next_engineering_checkpoint"],
                "reason": row["do_not_promote_reason"],
            }
        )
    return {
        "status": "strategy_asset_state_ready",
        "strategy_asset_state": {
            "status": "strategy_asset_state_ready",
            "asset_rows": asset_rows,
        },
    }


def _write_strategy_asset_state_source(tmp_path: Path) -> Path:
    path = tmp_path / "strategy-asset-state-source.json"
    path.write_text(
        json.dumps(_strategy_asset_state_source(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _inputs() -> tuple[dict, dict, dict, dict, str, dict]:
    return (
        json.loads(REGISTRY_PATH.read_text(encoding="utf-8")),
        json.loads(TIER_REVIEW_PATH.read_text(encoding="utf-8")),
        _strategy_asset_state_source(),
        json.loads(TIER_POLICY_PATH.read_text(encoding="utf-8")),
        REQUIRED_FACTS_PATH.read_text(encoding="utf-8")
        if REQUIRED_FACTS_PATH.exists()
        else "",
        json.loads(LOCAL_MONITOR_PATH.read_text(encoding="utf-8"))
        if LOCAL_MONITOR_PATH.exists()
        else {},
    )


def _artifact():
    inputs = _inputs()
    return build_quality_wave_artifact(*inputs)


def test_quality_wave_has_one_source_derived_row_per_included_group() -> None:
    artifact = _artifact()

    assert artifact["schema"] == "brc.strategygroup_quality_wave.v1"
    assert artifact["scope"] == "signal_observation_strategygroup_quality_wave"
    assert [row["strategy_group_id"] for row in artifact["rows"]] == INCLUDED_GROUPS
    assert len(artifact["rows"]) == 5
    assert validate_artifact(artifact) == []


def test_quality_wave_is_strategy_asset_provenance_not_primary_state() -> None:
    artifact = _artifact()

    assert artifact["readmodel_boundary"] == {
        "runtime_truth": False,
        "owner_supervision": True,
        "audit_evidence": True,
        "presentation_only": False,
    }
    provenance = artifact["strategy_asset_state_provenance"]
    assert provenance["state_family"] == "Strategy Asset State"
    assert provenance["source_role"] == "quality_evidence_provenance"
    assert provenance["primary_judgment_source"] is False
    assert (
        provenance["primary_judgment_source_name"] == "strategy_asset_state"
    )
    assert provenance["row_count"] == len(artifact["rows"])
    assert {row["strategy_group_id"] for row in provenance["rows"]} == set(
        INCLUDED_GROUPS
    )
    assert all("actionable_now" not in row for row in provenance["rows"])
    assert all("real_order_authority" not in row for row in provenance["rows"])
    assert artifact["strategy_asset_state_source"]["source"] == (
        "strategy_asset_state.asset_rows"
    )
    assert artifact["strategy_asset_state_source"]["row_count"] >= len(
        artifact["strategy_asset_state_provenance"]["rows"]
    )


def test_quality_wave_records_required_source_coverage() -> None:
    artifact = _artifact()

    coverage = artifact["source_coverage"]
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
        assert coverage[group]["strategy_asset_state_row"] is True
        assert "strategy_asset_state_source_row" not in coverage[group]
        assert coverage[group]["local_monitor_entrypoint"]


def test_quality_wave_classifies_current_gap_matrix() -> None:
    artifact = _artifact()
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}

    assert "decision_counts" not in artifact
    assert artifact["quality_wave_decision_counts"]["revise"] == 2
    assert artifact["quality_wave_decision_counts"]["promote_review_only"] == 1
    assert rows["BTPC-001"]["primary_gap_class"] == "fact_source_gap"
    assert rows["BTPC-001"]["secondary_gap_class"] == "classifier_gap"
    assert rows["VCB-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["LSR-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["BRF-001"]["primary_gap_class"] == "stale_or_missing_artifact_gap"
    assert rows["RBR-001"]["primary_gap_class"] == "parked_low_priority_gap"
    assert rows["RBR-001"]["system_can_continue"] is False


def test_quality_wave_keeps_brf_promote_review_scoped() -> None:
    artifact = _artifact()
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}
    brf = rows["BRF-001"]

    assert brf["current_decision"] == "promote_review_only"
    assert brf["promotion_scope"] == "review_only"
    assert brf["promotion_target"] == "promotion_evidence_review_only"
    assert "actionable_now" not in brf
    assert "real_order_authority" not in brf


def test_quality_wave_uses_strategy_asset_state_before_injected_legacy_rows() -> None:
    inputs = list(_inputs())
    tier_review = deepcopy(inputs[1])
    strategy_asset_state_source = deepcopy(inputs[2])
    for row in tier_review["rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["current_decision"] = "revise"
            row["required_next_evidence"] = "tier_review_should_not_win"
            row["do_not_promote_reason"] = "tier review should not win"
    for row in strategy_asset_state_source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["current_decision"] = "park"
            row["required_next_evidence"] = "asset_state_evidence_wins"
            row["reason"] = "asset state wins"
    inputs[1] = tier_review
    inputs[2] = strategy_asset_state_source

    artifact = build_quality_wave_artifact(*inputs)
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}

    assert rows["BTPC-001"]["current_decision"] == "park"
    assert "decision" not in rows["BTPC-001"]
    assert rows["BTPC-001"]["required_next_evidence"] == "asset_state_evidence_wins"
    assert rows["BTPC-001"]["do_not_promote_reason"] == "asset state wins"


def test_quality_wave_fails_closed_without_strategy_asset_state_rows() -> None:
    inputs = list(_inputs())
    strategy_asset_state_source = deepcopy(inputs[2])
    strategy_asset_state_source.pop("strategy_asset_state")
    inputs[2] = strategy_asset_state_source

    artifact = build_quality_wave_artifact(*inputs)

    errors = validate_artifact(artifact)
    assert artifact["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 0,
    }
    assert "BTPC-001.strategy_asset_state_row_missing" in errors
    assert (
        "BTPC-001.missing_strategy_asset_state_field:current_decision"
        in errors
    )
    assert (
        "BTPC-001.missing_strategy_asset_state_field:required_next_evidence"
        in errors
    )


def test_gap_closures_span_three_findings_and_two_groups_with_shared_guard() -> None:
    artifact = _artifact()

    closures = artifact["closures"]
    assert len(closures) >= 3
    groups = {closure["strategy_group_id"] for closure in closures}
    assert len(groups - {""}) >= 2
    assert any(closure["shared_infrastructure"] is True for closure in closures)
    assert any(
        closure["proves_owner_risk_acceptance_not_actionability"] is True
        for closure in closures
    )


def test_owner_risk_acceptance_never_sets_static_actionability() -> None:
    artifact = _artifact()

    assert artifact["global_authority_model"][
        "owner_risk_acceptance_cannot_grant_runtime_authority"
    ] is True
    assert artifact["global_authority_model"]["runtime_authority_sources"] == [
        "Tradeability Decision",
        "Runtime Safety State",
    ]
    assert "runtime_decides" not in artifact["global_authority_model"]
    assert "owner_risk_acceptance_cannot_set_actionable_now_true" not in artifact[
        "global_authority_model"
    ]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert all("actionable_now" not in row for row in artifact["rows"])
    assert all(row["owner_policy_action_required"] is False for row in artifact["rows"])


def test_negative_legacy_authority_mirror_is_rejected() -> None:
    artifact = _artifact()
    artifact["rows"][0]["actionable_now"] = True

    errors = validate_artifact(artifact)

    assert (
        "BTPC-001.quality_row_legacy_authority_mirror_present:actionable_now"
        in errors
    )


def test_negative_owner_operator_requirement_is_rejected() -> None:
    artifact = _artifact()
    artifact["rows"][1]["owner_policy_action_required"] = True

    errors = validate_artifact(artifact)

    assert "VCB-001.unexpected_owner_operator_requirement" in errors


def test_negative_missing_shared_closure_is_rejected() -> None:
    artifact = _artifact()
    for closure in artifact["closures"]:
        closure["shared_infrastructure"] = False

    errors = validate_artifact(artifact)

    assert "missing_shared_infrastructure_closure" in errors


def test_negative_unknown_gap_class_is_rejected() -> None:
    artifact = _artifact()
    artifact["rows"][0]["primary_gap_class"] = "unknown_gap"

    errors = validate_artifact(artifact)

    assert "BTPC-001.primary_gap_class_unknown:unknown_gap" in errors


def test_contradiction_detection_reports_registry_tier_drift() -> None:
    inputs = list(_inputs())
    registry = deepcopy(inputs[0])
    for row in registry["rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["default_tier"] = "L1"
    inputs[0] = registry

    artifact = build_quality_wave_artifact(*inputs)

    assert any(
        item["strategy_group_id"] == "BTPC-001"
        and item["source"] in {"tier_review", "strategy_asset_state", "tier_policy"}
        for item in artifact["contradictions"]
    )


def test_check_mode_passes_against_generated_files(tmp_path: Path) -> None:
    strategy_asset_state_path = _write_strategy_asset_state_source(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_quality_wave.py",
            "--strategy-asset-state-json",
            str(strategy_asset_state_path),
            "--local-monitor-json",
            str(LOCAL_MONITOR_PATH),
            "--check",
        ],
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


def test_quality_wave_cli_omitted_local_monitor_stays_missing(tmp_path: Path) -> None:
    output_json = tmp_path / "quality-wave.json"
    output_md = tmp_path / "quality-wave.md"
    strategy_asset_state_path = _write_strategy_asset_state_source(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_quality_wave.py",
            "--strategy-asset-state-json",
            str(strategy_asset_state_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert (
        artifact["source_authority"]["strategy_asset_state"]
        == "caller_supplied_strategy_asset_state"
    )
    assert artifact["source_authority"]["local_monitor_sequence"] == "caller_supplied"


def test_quality_wave_cli_requires_strategy_asset_state_source() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_quality_wave.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "--strategy-asset-state-json" in result.stderr
