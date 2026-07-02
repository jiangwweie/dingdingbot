from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from scripts.build_strategygroup_tier_review import (
    EXPECTED_GROUPS,
    EXPECTED_TIERS,
    SAFETY_INVARIANTS,
    build_tier_review_artifact,
    load_inputs,
    validate_inputs,
    validate_artifact,
)


REGISTRY_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
TIER_POLICY_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
STRATEGY_ASSET_STATE_PATH = Path(
    "output/runtime-monitor/latest-strategy-asset-state.json"
)


def _inputs(strategy_asset_state_source_path: Path = STRATEGY_ASSET_STATE_PATH):
    return load_inputs(REGISTRY_PATH, TIER_POLICY_PATH, strategy_asset_state_source_path)


def test_tier_review_schema_and_one_row_per_strategygroup() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)

    assert artifact["schema"] == "brc.strategygroup_tier_review.v1"
    assert [row["strategy_group_id"] for row in artifact["rows"]] == EXPECTED_GROUPS
    assert len(artifact["rows"]) == 10
    assert "decision_counts" not in artifact
    assert artifact["recommended_action_counts"]["keep"] == 6
    assert artifact["recommended_action_counts"]["revise"] == 2
    assert validate_inputs(registry, tier_policy) == []
    assert validate_artifact(artifact) == []


def test_tier_review_keeps_expected_policy_tiers() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)

    tiers = {row["strategy_group_id"]: row["current_tier"] for row in artifact["rows"]}
    assert tiers == EXPECTED_TIERS


def test_negative_registry_policy_tier_drift_is_rejected() -> None:
    registry, tier_policy, _strategy_asset_state_source = _inputs()
    mutated = deepcopy(tier_policy)
    mutated["current_strategy_groups"]["BTPC-001"]["tier"] = "L3"

    errors = validate_inputs(registry, mutated)

    assert any("tier_policy_mismatch:BTPC-001" in error for error in errors)
    assert any("registry_policy_tier_drift:BTPC-001" in error for error in errors)


def test_negative_row_legacy_authority_mirror_is_rejected() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()
    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)
    artifact["rows"][0]["actionable_now"] = True
    artifact["rows"][1]["real_order_authority"] = True

    errors = validate_artifact(artifact)

    assert (
        "MPG-001.tier_review_row_legacy_authority_mirror_present:actionable_now"
        in errors
    )
    assert (
        "TEQ-001.tier_review_row_legacy_authority_mirror_present:real_order_authority"
        in errors
    )


def test_negative_live_authority_flags_are_rejected() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()
    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)
    artifact["safety_invariants"]["calls_finalgate"] = True
    artifact["rows"][0]["safety_invariants"]["calls_operation_layer"] = True

    errors = validate_artifact(artifact)

    assert "safety_invariant_not_false:calls_finalgate" in errors
    assert "MPG-001.row_safety_invariant_not_false:calls_operation_layer" in errors


def test_strategy_uncertainty_is_not_execution_blocker() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)

    contract = artifact["runtime_authority_contract"]
    assert contract["strategy_uncertainty_is_not_execution_blocker"] is True
    assert contract["owner_scoped_risk_acceptance_may_promote_trial_eligibility"] is True
    assert contract["owner_scoped_risk_acceptance_cannot_grant_runtime_authority"] is True
    assert contract["runtime_authority_sources"] == [
        "Tradeability Decision",
        "Runtime Safety State",
    ]
    assert "actionability_contract" not in artifact
    for row in artifact["rows"]:
        assert row["strategy_uncertainty_is_execution_blocker"] is False
        assert "cannot grant runtime authority" in row[
            "owner_scoped_risk_acceptance_path"
        ]


def test_brf_promote_review_is_scoped_review_only() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}
    brf = rows["BRF-001"]

    assert brf["current_decision"] == "promote_review_only"
    assert brf["recommended_strategy_checkpoint"] == "promote_review_only"
    assert brf["promotion_scope"] == "review_only"
    assert brf["promotion_target"] == "promotion_evidence_review_only"
    assert brf["owner_policy_required"] is False
    assert "actionable_now" not in brf
    assert "real_order_authority" not in brf["safety_invariants"]


def test_tier_review_uses_strategy_asset_state_as_primary_decision_source() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()
    strategy_asset_state_source = deepcopy(strategy_asset_state_source)
    asset_rows = strategy_asset_state_source["strategy_asset_state"]["asset_rows"]
    for row in asset_rows:
        if row["strategy_group_id"] == "BTPC-001":
            row["current_decision"] = "park"
            row["promotion_scope"] = "not_applicable"
            row["promotion_target"] = "not_applicable"
            row["required_next_evidence"] = "asset_state_override_evidence"
            row["next_checkpoint"] = "asset_state_override_checkpoint"
            row["reason"] = "asset state is primary"
            break

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}

    assert artifact["strategy_asset_state_status"] == "strategy_asset_state_ready"
    assert rows["BTPC-001"]["tier_review_source"] == "strategy_asset_state"
    assert "decision_source" not in rows["BTPC-001"]
    assert "decision" not in rows["BTPC-001"]
    assert rows["BTPC-001"]["current_decision"] == "park"
    assert rows["BTPC-001"]["recommended_strategy_checkpoint"] == "park"
    assert rows["BTPC-001"]["required_next_evidence"] == "asset_state_override_evidence"


def test_tier_review_fails_closed_without_strategy_asset_state() -> None:
    registry, tier_policy, strategy_asset_state_source = _inputs()
    strategy_asset_state_source = deepcopy(strategy_asset_state_source)
    strategy_asset_state_source.pop("strategy_asset_state")

    artifact = build_tier_review_artifact(registry, tier_policy, strategy_asset_state_source)
    rows = {row["strategy_group_id"]: row for row in artifact["rows"]}

    assert artifact["strategy_asset_state_status"] == "missing_strategy_asset_state"
    assert rows["BTPC-001"]["tier_review_source"] == "registry_and_tier_policy"
    assert "decision_source" not in rows["BTPC-001"]
    assert rows["BTPC-001"]["current_decision"] == "keep_current_tier_no_promotion_evidence"


def test_owner_markdown_includes_groups_without_primary_internal_gate_labels() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tier_review.py",
            "--strategy-asset-state-json",
            str(STRATEGY_ASSET_STATE_PATH),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    markdown = Path(
        "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.md"
    ).read_text(encoding="utf-8")
    for group in EXPECTED_GROUPS:
        assert group in markdown
    for internal_label in ("FinalGate", "Operation Layer", "RequiredFacts"):
        assert internal_label not in markdown.split("## Owner 读法", 1)[0]


def test_check_mode_passes_against_generated_files() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tier_review.py",
            "--strategy-asset-state-json",
            str(STRATEGY_ASSET_STATE_PATH),
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
    assert all(value is False for value in SAFETY_INVARIANTS.values())


def test_tier_review_cli_requires_strategy_asset_state_source() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_tier_review.py"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "--strategy-asset-state-json" in result.stderr
