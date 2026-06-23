from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_current_tradeability_artifact_matches_monitor_sequence_contract():
    verdict = _read_json(
        "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")

    verdict_rows = verdict.get("verdict_rows") or []
    monitor_checks = monitor.get("checks") or {}
    verdict_row_count = verdict.get("summary", {}).get("row_count")

    assert verdict["schema"] == "brc.strategygroup_tradeability_verdict.v1"
    assert verdict["scope"] == "strategygroup_tradeability_verdict_read_model"
    assert verdict["generated_at_utc"]
    assert verdict["owner_summary"]
    assert verdict_row_count == len(verdict_rows)
    assert verdict.get("checks", {}).get("row_count_matches_verdict_rows") is True
    assert monitor_checks.get("tradeability_row_count") == verdict_row_count
    assert monitor_checks.get("tradeability_verdict_rows_count") == len(verdict_rows)
    assert monitor_checks.get("tradeability_row_count_matches_verdict_rows") is True


def test_current_trial_asset_admission_proposal_artifact_is_complete():
    proposal_packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
    )
    proposal = proposal_packet.get("proposal") or {}

    assert (
        proposal_packet["schema"]
        == "brc.strategygroup_trial_asset_admission_proposal.v1"
    )
    assert (
        proposal_packet["scope"]
        == "strategygroup_trial_asset_admission_proposal_non_applying"
    )
    assert proposal_packet["generated_at_utc"]
    assert proposal["owner_policy_defaults"]
    assert proposal["owner_policy_required"] is False
    assert proposal["owner_policy_recorded"] is True
    assert proposal["owner_policy_scope_missing"] is False
    assert proposal["next_action"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert proposal["proposed_registry_row"]
    assert proposal["proposed_tier_policy_row"]
    assert proposal["runtime_admission_plan"]
    assert proposal["actionable_now"] is False
    assert proposal["real_order_authority"] is False


def test_current_brf2_owner_trial_policy_scope_artifact_is_complete():
    policy_packet = _read_json(
        "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
    )
    docs_policy_packet = _read_json(
        "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
    )
    policy = policy_packet.get("policy") or {}

    assert policy_packet["schema"] == "brc.brf2_owner_trial_policy_scope.v0"
    assert (
        policy_packet["scope"]
        == "final_owned_brf2_owner_trial_policy_scope_non_executing"
    )
    assert policy_packet["status"] == "brf2_owner_trial_policy_scope_recorded"
    assert docs_policy_packet["schema"] == policy_packet["schema"]
    assert policy_packet["brf2_policy_scope_recorded"] is True
    assert policy_packet["owner_policy_scope_missing"] is False
    assert policy["strategy_group_id"] == "BRF2-001"
    assert policy["trial_identity"] == "BRF2_TINY_SHORT_TRIAL_30U_V0"
    assert policy["capital_scope"]["amount"] == "30"
    assert policy["capital_scope"]["currency"] == "USDT"
    assert policy["capital_scope"]["loss_capable"] is True
    assert policy["side_scope"] == ["short"]
    assert policy["leverage_scenario"] == "5x_scenario_not_authority"
    assert policy["max_notional"]["amount"] == "150"
    assert policy["attempt_cap"] == 3
    assert policy["loss_unit"]["amount"] == "10"
    assert policy_packet["safety_invariants"]["actionable_now"] is False
    assert policy_packet["safety_invariants"]["real_order_authority"] is False
    assert policy_packet["safety_invariants"]["calls_finalgate"] is False
    assert policy_packet["safety_invariants"]["calls_operation_layer"] is False
    assert policy_packet["safety_invariants"]["calls_exchange_write"] is False
    assert policy_packet["safety_invariants"]["places_order"] is False


def test_current_three_strategy_live_trial_portfolio_artifact_is_complete():
    portfolio = _read_json(
        "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    checks = monitor.get("checks") or {}

    assert portfolio["schema"] == "brc.three_strategy_live_trial_portfolio.v1"
    assert portfolio["scope"] == "three_strategy_live_trial_portfolio_read_model"
    assert portfolio["status"] == "three_strategy_live_trial_portfolio_ready"
    assert portfolio["selected_strategy_groups"] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert portfolio["seat_count"] == 3
    assert portfolio["objective_met"] is True
    assert portfolio["checks"]["all_seats_have_first_blocker"] is True
    assert portfolio["checks"]["all_seats_have_required_facts"] is True
    assert portfolio["checks"]["all_seats_have_review_hooks"] is True
    assert portfolio["safety_invariants"]["actionable_now"] is False
    assert portfolio["safety_invariants"]["real_order_authority"] is False
    assert portfolio["safety_invariants"]["calls_finalgate"] is False
    assert portfolio["safety_invariants"]["calls_operation_layer"] is False
    assert portfolio["safety_invariants"]["calls_exchange_write"] is False
    assert portfolio["safety_invariants"]["places_order"] is False
    evidence = portfolio["final_evidence_packet"]
    assert evidence["closed_engineering_problem"]
    assert evidence["capability_unlocked"]
    assert evidence["three_strategy_portfolio_status"] == portfolio["status"]
    assert evidence["strategy_seat_table"]
    assert evidence["remaining_first_blockers"]
    assert evidence["next_live_submit_condition"]
    assert evidence["tests_run"]
    assert evidence["files_changed"]
    assert evidence["deploy_recommendation"]

    assert checks["three_strategy_live_trial_portfolio_ready"] is True
    assert checks["live_trial_seat_count"] == 3
    assert checks["live_trial_strategy_groups"] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert checks["live_trial_owner_policy_gap_count"] == 0
    assert checks["live_trial_engineering_gap_count"] >= 1
    assert checks["brf2_owner_policy_recorded"] is True
    assert checks["brf2_owner_policy_scope_missing"] is False
    assert checks["brf2_new_first_blocker"] == "required_facts_mapping_gap"
