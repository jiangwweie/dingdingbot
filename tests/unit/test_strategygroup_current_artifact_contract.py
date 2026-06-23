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
    assert policy_packet["view_mode"] == "monitor_view_from_final_owned_policy"
    assert policy_packet["source_policy_json"].endswith(
        "docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json"
    )
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


def test_current_brf2_required_facts_mapping_artifact_is_complete():
    mapping = _read_json("output/runtime-monitor/latest-brf2-required-facts-mapping.json")

    assert mapping["schema"] == "brc.brf2_required_facts_mapping.v1"
    assert mapping["scope"] == "brf2_required_facts_mapping_for_armed_observation"
    assert mapping["status"] == "brf2_required_facts_mapping_ready"
    assert mapping["generated_at_utc"]
    assert mapping["strategy_group_id"] == "BRF2-001"
    assert mapping["required_facts_mapping_ready"] is True
    assert mapping["after_next_state"] == "armed_observation"
    assert mapping["fresh_signal_rule"]["signal_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert {
        "closed_1h_ohlcv",
        "closed_5m_ohlcv",
        "rally_context",
        "rally_failure_trigger_state",
        "short_squeeze_risk_state",
        "strong_reclaim_disable_state",
        "liquidity_downshift_state",
        "spread_liquidity_state",
    }.issubset(set(mapping["required_fact_keys"]))
    assert mapping["checks"]["actionable_now"] is False
    assert mapping["checks"]["real_order_authority"] is False
    assert mapping["checks"]["calls_finalgate"] is False
    assert mapping["checks"]["calls_operation_layer"] is False
    assert mapping["checks"]["calls_exchange_write"] is False
    assert mapping["checks"]["places_order"] is False


def test_current_brf2_runtime_signal_capture_artifact_is_complete():
    facts = _read_json("output/runtime-monitor/latest-brf2-runtime-signal-facts.json")
    capture = _read_json("output/runtime-monitor/latest-brf2-runtime-signal-capture.json")
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    checks = monitor.get("checks") or {}
    preview = capture["signal_detector_preview"]
    candidate = capture["candidate_packet_shape"]

    assert capture["schema"] == "brc.brf2_runtime_signal_capture.v1"
    assert capture["scope"] == "brf2_runtime_signal_capture_read_model"
    assert capture["status"] == "brf2_runtime_signal_capture_ready"
    assert capture["generated_at_utc"]
    assert capture["strategy_group_id"] == "BRF2-001"
    assert facts["schema"] == "brc.brf2_runtime_signal_facts.v1"
    assert facts["status"] == "brf2_runtime_signal_facts_ready"
    assert facts["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert facts["fact_authority_boundary"]["usable_for_armed_observation"] is True
    assert facts["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert facts["fact_authority_boundary"]["usable_for_finalgate"] is False
    assert capture["fact_input_present"] == facts["fact_input_present"]
    assert capture["watcher_tick_present"] == facts["watcher_tick_present"]
    assert capture["fact_authority"] == facts["fact_authority"]
    assert capture["fact_authority_boundary"] == facts["fact_authority_boundary"]
    assert capture["source_signal_context"]["signal_packet_id"] == (
        facts["source_signal_context"]["signal_packet_id"]
    )
    assert capture["source_signal_context"]["symbol"] == (
        facts["source_signal_context"]["symbol"]
    )
    assert capture["source_signal_context"]["source_strategy_group_id"] == "BRF-001"
    assert capture["watcher_scope"]["signal_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert capture["watcher_scope"]["side_scope"] == ["short"]
    assert preview["detector_ready"] is True
    assert preview["current_signal_state"] == "fresh_signal_absent"
    assert preview["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert preview["first_blocker_owner"] == "market"
    assert capture["no_action_attribution"]["attribution_ready"] is True
    assert candidate["candidate_packet_type"] == (
        "brf2_non_executing_short_signal_candidate"
    )
    assert "action_time_finalgate_packet_id" in candidate["required_next_chain"]
    assert "operation_layer_submit_authorization_id" in candidate["required_next_chain"]
    assert candidate["fact_authority"] == facts["fact_authority"]
    assert candidate["fact_authority_boundary"] == facts["fact_authority_boundary"]
    assert capture["checks"]["actionable_now"] is False
    assert capture["checks"]["real_order_authority"] is False
    assert capture["checks"]["action_time_required_facts_satisfied"] is False
    assert capture["checks"]["calls_finalgate"] is False
    assert capture["checks"]["calls_operation_layer"] is False
    assert capture["checks"]["calls_exchange_write"] is False
    assert capture["checks"]["places_order"] is False
    assert checks["brf2_runtime_signal_capture_ready"] is True
    assert checks["brf2_runtime_signal_fact_input_present"] == (
        facts["fact_input_present"]
    )
    assert checks["brf2_runtime_signal_watcher_tick_present"] == (
        facts["watcher_tick_present"]
    )
    assert checks["brf2_runtime_signal_state"] == preview["current_signal_state"]
    assert checks["brf2_runtime_candidate_packet_ready"] == (
        candidate["candidate_packet_ready"]
    )


def test_current_brf2_non_executing_candidate_packet_artifact_is_complete():
    packet = _read_json(
        "output/runtime-monitor/latest-brf2-non-executing-candidate-packet.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    checks = monitor.get("checks") or {}
    candidate = packet["candidate_packet"]

    assert packet["schema"] == "brc.brf2_non_executing_candidate_packet.v1"
    assert packet["scope"] == "brf2_non_executing_candidate_packet_read_model"
    assert packet["status"] in {
        "brf2_non_executing_candidate_packet_ready",
        "brf2_non_executing_candidate_packet_waiting_for_fresh_signal",
    }
    assert packet["generated_at_utc"]
    assert packet["strategy_group_id"] == "BRF2-001"
    assert candidate["candidate_packet_type"] == (
        "brf2_non_executing_short_signal_candidate"
    )
    assert candidate["side"] == "short"
    assert candidate["symbol"]
    assert candidate["source_signal_packet_id"]
    assert candidate["source_strategy_group_id"] == "BRF-001"
    assert candidate["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert candidate["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert "action_time_finalgate_packet_id" in candidate["required_next_chain"]
    assert "operation_layer_submit_authorization_id" in candidate["required_next_chain"]
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["checks"]["action_time_required_facts_satisfied"] is False
    assert packet["checks"]["calls_finalgate"] is False
    assert packet["checks"]["calls_operation_layer"] is False
    assert packet["checks"]["calls_exchange_write"] is False
    assert packet["checks"]["places_order"] is False
    assert checks["brf2_non_executing_candidate_packet_status"] == packet["status"]
    assert checks["brf2_non_executing_candidate_packet_ready"] == (
        packet["candidate_packet_ready"]
    )


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
    brf2 = portfolio["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["required_facts_mapping_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is True
    assert brf2["runtime_readiness"]["blocked_by"] == (
        "fresh_brf2_short_signal_absent"
    )
    assert brf2["runtime_readiness"]["tiny_live_ready"] is False
    assert brf2["runtime_readiness"]["live_submit_ready"] is False
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
    assert checks["live_trial_engineering_gap_count"] == 0
    assert checks["live_trial_market_wait_count"] == 3
    assert checks["brf2_owner_policy_recorded"] is True
    assert checks["brf2_owner_policy_scope_missing"] is False
    assert checks["brf2_required_facts_mapping_ready"] is True
    assert checks["brf2_after_required_facts_mapping_state"] == "armed_observation"
    assert checks["brf2_fresh_signal_rule_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert checks["brf2_runtime_signal_fact_input_present"] is True
    assert checks["brf2_runtime_signal_watcher_tick_present"] is True
    assert checks["brf2_runtime_signal_state"] == "fresh_signal_absent"
    assert checks["brf2_runtime_signal_first_blocker_class"] == (
        "fresh_brf2_short_signal_absent"
    )


def test_current_tradeability_brf2_resolves_old_owner_policy_blockers():
    verdict = _read_json(
        "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json"
    )
    rows = {row["strategy_group_id"]: row for row in verdict["verdict_rows"]}
    brf2 = rows["BRF2-001"]
    secondary = {row["blocker"] for row in brf2["secondary_blockers"]}
    resolved = {row["blocker"] for row in brf2["resolved_blockers"]}

    assert brf2["runtime_scope_status"]["owner_policy_recorded"] is True
    assert brf2["runtime_scope_status"]["owner_policy_scope_missing"] is False
    assert brf2["stage"] == "armed_observation"
    assert brf2["verdict"] == "not_tradable_market_wait"
    assert brf2["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert brf2["blocker_owner"] == "market"
    assert brf2["next_action"] == (
        "continue_brf2_armed_observation_until_fresh_signal"
    )
    assert "owner_capital_scope_not_confirmed" not in secondary
    assert "owner_trial_identity_not_confirmed" not in secondary
    assert "owner_capital_scope_not_confirmed" in resolved
    assert "owner_trial_identity_not_confirmed" in resolved
