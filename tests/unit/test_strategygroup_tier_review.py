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
    build_tier_review_packet,
    load_inputs,
    validate_inputs,
    validate_packet,
)


REGISTRY_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
TIER_POLICY_PATH = Path(
    "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DECISION_LEDGER_PATH = Path(
    "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)


def _inputs(decision_ledger_path: Path = DECISION_LEDGER_PATH):
    return load_inputs(REGISTRY_PATH, TIER_POLICY_PATH, decision_ledger_path)


def test_tier_review_schema_and_one_row_per_strategygroup() -> None:
    registry, tier_policy, decision_ledger = _inputs()

    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)

    assert packet["schema"] == "brc.strategygroup_tier_review.v1"
    assert [row["strategy_group_id"] for row in packet["rows"]] == EXPECTED_GROUPS
    assert len(packet["rows"]) == 10
    assert validate_inputs(registry, tier_policy) == []
    assert validate_packet(packet) == []


def test_tier_review_keeps_expected_policy_tiers() -> None:
    registry, tier_policy, decision_ledger = _inputs()

    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)

    tiers = {row["strategy_group_id"]: row["current_tier"] for row in packet["rows"]}
    assert tiers == EXPECTED_TIERS


def test_negative_registry_policy_tier_drift_is_rejected() -> None:
    registry, tier_policy, _decision_ledger = _inputs()
    mutated = deepcopy(tier_policy)
    mutated["current_strategy_groups"]["BTPC-001"]["tier"] = "L3"

    errors = validate_inputs(registry, mutated)

    assert any("tier_policy_mismatch:BTPC-001" in error for error in errors)
    assert any("registry_policy_tier_drift:BTPC-001" in error for error in errors)


def test_negative_actionable_now_true_is_rejected() -> None:
    registry, tier_policy, decision_ledger = _inputs()
    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)
    packet["rows"][0]["actionable_now"] = True

    errors = validate_packet(packet)

    assert "MPG-001.actionable_now_true" in errors


def test_negative_live_authority_flags_are_rejected() -> None:
    registry, tier_policy, decision_ledger = _inputs()
    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)
    packet["safety_invariants"]["real_order_authority"] = True
    packet["rows"][0]["safety_invariants"]["calls_operation_layer"] = True

    errors = validate_packet(packet)

    assert "safety_invariant_not_false:real_order_authority" in errors
    assert "MPG-001.row_safety_invariant_not_false:calls_operation_layer" in errors


def test_missing_decision_ledger_is_explicit_and_non_authorizing(tmp_path: Path) -> None:
    registry, tier_policy, decision_ledger = load_inputs(
        REGISTRY_PATH,
        TIER_POLICY_PATH,
        tmp_path / "missing-decision-ledger.json",
    )

    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)

    assert packet["ledger_status"] == "missing_generated_view"
    assert len(packet["rows"]) == 10
    assert all(row["actionable_now"] is False for row in packet["rows"])
    assert validate_packet(packet) == []


def test_strategy_uncertainty_is_not_execution_blocker() -> None:
    registry, tier_policy, decision_ledger = _inputs()

    packet = build_tier_review_packet(registry, tier_policy, decision_ledger)

    contract = packet["actionability_contract"]
    assert contract["strategy_uncertainty_is_not_execution_blocker"] is True
    assert contract["owner_scoped_risk_acceptance_may_promote_trial_eligibility"] is True
    assert contract["owner_scoped_risk_acceptance_cannot_set_actionable_now_true"] is True
    for row in packet["rows"]:
        assert row["strategy_uncertainty_is_execution_blocker"] is False
        assert "cannot set runtime actionability to true" in row[
            "owner_scoped_risk_acceptance_path"
        ]


def test_owner_markdown_includes_groups_without_primary_internal_gate_labels() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_tier_review.py"],
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
