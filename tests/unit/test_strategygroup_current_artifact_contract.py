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


def test_current_trial_grade_signal_gate_audit_artifact_matches_monitor_sequence_contract():
    audit = _read_json(
        "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")
    checks = monitor.get("checks") or {}
    summary = audit.get("summary") or {}
    rows = audit.get("strategy_group_rows") or {}

    assert audit["schema"] == "brc.strategygroup_trial_grade_signal_gate_audit.v1"
    assert (
        audit["scope"]
        == "strategygroup_trial_grade_signal_gate_audit_non_executing"
    )
    assert audit["status"] == "trial_grade_signal_gate_audit_ready"
    assert audit["generated_at_utc"]
    assert audit["signal_grade_catalog"]["observe_only_signal"]["may_place_order"] is False
    assert audit["signal_grade_catalog"]["invalid_signal"]["may_place_order"] is False
    assert set(audit["signal_grade_catalog"]) == {
        "observe_only_signal",
        "trial_grade_signal",
        "production_grade_signal",
        "invalid_signal",
    }
    assert "action_time_finalgate" in audit["hard_safety_gate_list"]
    assert "official_operation_layer" in audit["hard_safety_gate_list"]
    assert "no_live_profile_or_order_sizing_expansion" in audit[
        "hard_safety_gate_list"
    ]
    live_trial_policy_update = audit["live_trial_policy_update"]
    assert live_trial_policy_update["scope"] == "30U_bounded_trial_only"
    assert (
        live_trial_policy_update["does_not_change_production_grade_authority"]
        is True
    )
    assert live_trial_policy_update["does_not_expand_live_profile"] is True
    assert (
        live_trial_policy_update["does_not_change_order_sizing_defaults"] is True
    )
    assert audit["checks"]["hard_safety_gates_not_relaxed"] is True
    assert audit["checks"]["risk_expressed_as_envelope"] is True
    assert audit["checks"]["replay_or_proxy_not_action_time_authority"] is True
    assert audit["checks"]["actionable_now"] is False
    assert audit["checks"]["real_order_authority"] is False
    assert audit["checks"]["calls_finalgate"] is False
    assert audit["checks"]["calls_operation_layer"] is False
    assert audit["checks"]["calls_exchange_write"] is False
    assert audit["checks"]["places_order"] is False
    assert audit["safety_invariants"]["actionable_now"] is False
    assert audit["safety_invariants"]["real_order_authority"] is False
    assert (
        audit["safety_invariants"]["action_time_required_facts_satisfied_by_proxy"]
        is False
    )
    assert audit["safety_invariants"]["places_order"] is False
    assert summary["strategy_group_count"] == 3
    assert summary["trial_grade_observation_count_30d"] == 1
    assert summary["action_time_trial_submit_count_30d"] == 0
    assert summary["hard_safety_gates_relaxed"] is False
    assert set(rows) == {"MPG-001", "BRF2-001", "SOR-001"}

    for strategy_group_id, row in rows.items():
        assert row["strategy_group_id"] == strategy_group_id
        assert row["production_grade_gate_profile"]["grade"] == (
            "production_grade_signal"
        )
        assert row["trial_grade_gate_profile"]["grade"] == "trial_grade_signal"
        assert row["trial_grade_trigger_diff"]
        assert row["hard_safety_gate_list"] == audit["hard_safety_gate_list"]
        assert row["risk_envelope"]["attempt_cap"] >= 1
        assert row["risk_envelope"]["stop_or_protection_required"] is True
        assert set(row["verified_recent_window_counts"]["windows_days"]) == {
            "7",
            "14",
            "30",
        }
        assert (
            row["verified_recent_window_counts"][
                "counts_do_not_authorize_submit"
            ]
            is True
        )
        assert (
            row["verified_recent_window_counts"][
                "verified_recent_counts_are_action_time_counts"
            ]
            is False
        )
        assert row["fixture_replay_projection"]["max_loss_estimate_usdt"]
        assert row["fixture_replay_projection"]["projection_boundary"]
        assert row["false_positive_review_pack"]
        assert (
            row["authority_boundary"][
                "trial_grade_signal_can_bypass_hard_safety_gates"
            ]
            is False
        )
        assert row["authority_boundary"]["actionable_now"] is False
        assert row["authority_boundary"]["real_order_authority"] is False

    brf2 = rows["BRF2-001"]
    brf2_counts_30d = brf2["verified_recent_window_counts"]["windows_days"]["30"]
    assert brf2_counts_30d["trial_grade_observation_count"] == 1
    assert brf2_counts_30d["action_time_trial_submit_count"] == 0
    assert brf2["risk_envelope"]["path_risk_treatment"] == (
        "known_path_risk_enters_envelope_not_trade_denial"
    )
    assert brf2["tomorrow_same_structure_assessment"]["would_enter_30u_trial"] is True

    sor = rows["SOR-001"]
    assert sor["fixture_replay_projection"]["trial_grade_trigger_case_count"] == 1
    assert sor["tomorrow_same_structure_assessment"]["would_enter_30u_trial"] is True

    assert checks["trial_grade_signal_gate_audit_ready"] is True
    assert checks["trial_grade_strategy_group_count"] == summary["strategy_group_count"]
    assert checks["trial_grade_observation_count_30d"] == (
        summary["trial_grade_observation_count_30d"]
    )
    assert checks["trial_grade_action_time_submit_count_30d"] == 0
    assert checks["trial_grade_hard_safety_gates_relaxed"] is False
    assert (
        checks["trial_grade_brf2_would_enter_30u_trial_if_same_structure"]
        is True
    )
    assert (
        checks["trial_grade_sor_would_enter_30u_trial_if_same_structure"]
        is True
    )


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
    stage_5 = portfolio["stage_5_live_opportunity_standby"]
    assert stage_5["status"] == "phase_5_waiting_for_live_opportunity"
    assert stage_5["ready"] is True
    assert stage_5["standby_count"] == 3
    assert stage_5["market_wait_count"] == 3
    assert stage_5["action_time_preflight_pending_fresh_signal"] is True
    assert stage_5["hard_safety_gates_relaxed"] is False
    assert stage_5["actionable_now"] is False
    assert stage_5["real_order_authority"] is False
    brf2 = portfolio["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["stage_5_status"] == "waiting_for_live_opportunity"
    assert brf2["trial_grade_signal_status"]["trial_grade_audit_ready"] is True
    assert (
        brf2["trial_grade_signal_status"][
            "trial_grade_signal_can_prepare_30u_trial"
        ]
        is True
    )
    assert (
        brf2["trial_grade_signal_status"][
            "trial_grade_signal_can_bypass_hard_safety_gates"
        ]
        is False
    )
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["required_facts_mapping_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is True
    assert brf2["runtime_readiness"]["trial_grade_30u_standby_ready"] is True
    assert (
        brf2["runtime_readiness"]["stage_5_waiting_live_opportunity_ready"] is True
    )
    assert (
        brf2["runtime_readiness"]["action_time_preflight_pending_fresh_signal"]
        is True
    )
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
    assert checks["stage_5_waiting_live_opportunity_ready"] is True
    assert checks["stage_5_status"] == "phase_5_waiting_for_live_opportunity"
    assert checks["trial_grade_30u_standby_count"] == 3
    assert checks["action_time_preflight_pending_fresh_signal"] is True
    assert checks["stage_5_hard_safety_gates_relaxed"] is False
    assert checks["tradeability_trial_grade_30u_standby_count"] == 3
    assert checks["tradeability_stage_5_waiting_live_opportunity_ready_count"] == 3
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
