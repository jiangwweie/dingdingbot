from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_three_strategy_live_trial_portfolio.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_three_strategy_live_trial_portfolio",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _registry() -> dict:
    return {
        "rows": [
            {"strategy_group_id": "MPG-001", "default_tier": "L4", "trial_eligible": True},
            {"strategy_group_id": "SOR-001", "default_tier": "L3", "trial_eligible": False},
        ]
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4", "mode": "tiny_real_order_eligible"},
            "SOR-001": {"tier": "L3", "mode": "conditional_armed_observation"},
        }
    }


def _capital_trial_envelope_projection() -> dict:
    return {
        "selected_non_mpg_trial_candidate": {
            "strategy_group_id": "BRF2-001",
            "side_scope": ["short"],
            "symbol_scope": ["owner_policy_required"],
            "risk_envelope": {
                "attempt_cap_per_review_cycle": 3,
                "daily_loss_cap_units": 1,
            },
            "required_facts_draft": ["closed_1h_ohlcv", "squeeze_risk_state"],
            "disable_or_review_facts_draft": ["short_squeeze_risk_state"],
        }
    }


def _trial_admission_proposal() -> dict:
    return {
        "proposal": {
            "strategy_group_id": "BRF2-001",
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "proposed_stage": "admitted_trial_asset",
            "runtime_admission_plan": {
                "required_facts_draft": ["closed_1h_ohlcv", "squeeze_risk_state"],
                "disable_or_review_facts_draft": ["short_squeeze_risk_state"],
            },
        }
    }


def _owner_policy_scope() -> dict:
    return {
        "status": "brf2_owner_trial_policy_scope_recorded",
        "brf2_policy_scope_recorded": True,
        "owner_policy_scope_missing": False,
        "policy": {
            "strategy_group_id": "BRF2-001",
            "trial_identity": "BRF2_CONTROLLED_SHORT_TRIAL_V0",
            "capital_scope": {
                "type": "isolated_subaccount_full_allocation",
                "allocation_mode": "full_available_isolated_subaccount",
                "amount_source": "action_time_exchange_available_balance",
                "currency": "USDT",
                "loss_capable": True,
            },
            "side_scope": ["short"],
            "symbol_scope": "brf2_research_supported_symbols_only",
            "leverage_scenario": "5x_scenario_not_authority",
            "max_notional": {
                "currency": "USDT",
                "calculation": "action_time_exchange_available_balance * leverage_scenario",
                "balance_source": "action_time_exchange_available_balance",
                "basis": "controlled subaccount dynamic allocation x leverage scenario",
                "final_authority": "runtime_profile_and_action_time_exchange_facts",
            },
            "attempt_cap": 3,
            "loss_unit": {
                "currency": "USDT",
                "calculation": "action_time_exchange_available_balance / attempt_cap",
                "balance_source": "action_time_exchange_available_balance",
                "basis": "controlled subaccount dynamic allocation / attempt cap",
            },
            "daily_loss_cap_units": 1,
            "max_consecutive_losses": 2,
            "valid_until": "one_review_cycle",
            "pause_conditions": ["two_consecutive_losses"],
            "authority_boundary": (
                "owner_policy_only; finalgate_required; operation_layer_required"
            ),
        },
    }


def _brf2_required_facts_mapping() -> dict:
    return {
        "status": "brf2_required_facts_mapping_ready",
        "strategy_group_id": "BRF2-001",
        "required_facts_mapping_ready": True,
        "after_next_state": "armed_observation",
        "fresh_signal_rule": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
            "side": "short",
        },
        "required_fact_observation_specs": [
            {"fact_key": "closed_1h_ohlcv", "accepted_statuses": ["ready"]},
            {"fact_key": "closed_5m_ohlcv", "accepted_statuses": ["ready"]},
            {"fact_key": "rally_context", "accepted_statuses": ["ready"]},
            {
                "fact_key": "rally_failure_trigger_state",
                "accepted_statuses": ["confirmed", "ready"],
            },
            {
                "fact_key": "short_squeeze_risk_state",
                "accepted_statuses": ["bounded", "clear"],
            },
            {
                "fact_key": "strong_reclaim_disable_state",
                "accepted_statuses": ["clear", "false"],
            },
            {
                "fact_key": "liquidity_downshift_state",
                "accepted_statuses": ["clear", "false"],
            },
            {
                "fact_key": "spread_liquidity_state",
                "accepted_statuses": ["acceptable", "ready"],
            },
        ],
        "disable_fact_observation_specs": [
            {
                "fact_key": "short_squeeze_risk_state",
                "active_statuses": ["red", "unbounded", "unknown"],
                "blocker": "squeeze_risk_not_clear",
            },
            {
                "fact_key": "strong_reclaim_disable_state",
                "active_statuses": ["active", "true"],
                "blocker": "strong_reclaim_disable_active",
            },
            {
                "fact_key": "rally_extension_invalidates_failure_state",
                "active_statuses": ["active", "true"],
                "blocker": "rally_extension_invalidates_failure",
            },
            {
                "fact_key": "liquidity_downshift_state",
                "active_statuses": ["active", "true"],
                "blocker": "liquidity_downshift_active",
            },
            {
                "fact_key": "spread_liquidity_state",
                "active_statuses": [
                    "missing",
                    "thin_volume",
                    "unknown",
                    "wide_spread",
                ],
                "blocker": "spread_liquidity_not_acceptable",
            },
        ],
        "block_conditions": [
            {
                "condition": "closed_1h_ohlcv_missing_or_stale",
                "behavior": "block_armed_observation",
            }
        ],
    }


def _brf2_runtime_signal_capture_missing_fact_input() -> dict:
    return {
        "status": "brf2_runtime_signal_capture_ready",
        "strategy_group_id": "BRF2-001",
        "fact_input_present": False,
        "watcher_tick_present": False,
        "signal_detector_preview": {
            "current_signal_state": "fact_input_missing",
            "fresh_signal_present": False,
            "first_blocker_class": "brf2_watcher_fact_input_missing",
            "first_blocker_owner": "engineering",
            "signal_capture_checkpoint": "attach_brf2_watcher_fact_input_producer",
        },
    }


def _trial_grade_signal_gate_audit() -> dict:
    def row(strategy_group_id: str, current_gate: str) -> dict:
        return {
            "strategy_group_id": strategy_group_id,
            "signal_grade_current_assessment": {
                "current_gate_looks_like": current_gate,
            },
            "verified_recent_window_counts": {
                "windows_days": {
                    "30": {
                        "trial_grade_observation_count": (
                            1 if strategy_group_id == "BRF2-001" else 0
                        ),
                        "action_time_trial_submit_count": 0,
                    }
                }
            },
            "fixture_replay_projection": {
                "trial_grade_trigger_case_count": 1,
                "max_loss_estimate_usdt": "30",
            },
            "tomorrow_same_structure_assessment": {
                "would_enter_controlled_live_trial": True,
            },
            "authority_boundary": {
                "trial_grade_signal_can_prepare_controlled_live": True,
                "trial_grade_signal_can_bypass_hard_safety_gates": False,
            },
        }

    return {
        "status": "trial_grade_signal_gate_audit_ready",
        "strategy_group_rows": {
            "MPG-001": row(
                "MPG-001",
                "l4_production_path_with_trial_grade_warning_candidates",
            ),
            "BRF2-001": row(
                "BRF2-001",
                "production_grade_strict_with_trial_grade_proxy_evidence",
            ),
            "SOR-001": row(
                "SOR-001",
                "conditional_armed_observation_with_trial_grade_replay_calibration",
            ),
        },
        "summary": {"hard_safety_gates_relaxed": False},
        "live_trial_policy_update": {
            "scope": "controlled_subaccount_live_scope",
            "does_not_change_production_grade_authority": True,
        },
    }


def _portfolio_with_trial_grade_audit(
    module,
    audit: dict,
    *,
    brf2_required_facts_mapping: dict | None = None,
) -> dict:
    return module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        brf2_required_facts_mapping=(
            brf2_required_facts_mapping or _brf2_required_facts_mapping()
        ),
        trial_grade_signal_gate_audit=audit,
        signal_coverage={"events": [{"strategy_group_id": "SOR-001"}]},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )


def test_three_strategy_portfolio_selects_mpg_brf2_and_sor():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        signal_coverage={"events": [{"strategy_group_id": "SOR-001"}]},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["status"] == "three_strategy_live_trial_portfolio_ready"
    assert packet["objective_met"] is True
    assert packet["selected_strategy_groups"] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert packet["seat_count"] == 3
    assert packet["replacement_rationale"]["replacement_used"] is False
    assert packet["replacement_rationale"]["replacement_candidate_order"] == [
        "FBS-001",
        "TEQ-001",
        "BTPC-001",
    ]
    assert "fallback_order" not in packet["replacement_rationale"]
    assert packet["checks"]["all_seats_have_first_blocker"] is True
    assert packet["checks"]["all_seats_have_required_facts"] is True
    assert packet["checks"]["all_seats_have_review_hooks"] is True
    assert packet["checks"]["all_seats_reference_trial_envelope"] is True
    assert "trial_envelope_actionable_now" not in packet["checks"]
    assert "trial_envelope_real_order_authority" not in packet["checks"]
    assert "actionable_now" not in packet["checks"]
    assert "real_order_authority" not in packet["checks"]

    trial_envelope = packet["trial_envelope"]
    assert trial_envelope["trial_envelope_id"] == (
        "three_strategy_live_trial_envelope_v1"
    )
    assert trial_envelope["state_family"] == "Strategy Policy / Trial Envelope"
    assert "primary_judgment_source" not in trial_envelope
    assert trial_envelope["primary_policy_source"] is True
    assert trial_envelope["tradeability_decision_source"] is False
    assert trial_envelope["runtime_truth_source"] is False
    assert trial_envelope["applies_to_strategy_groups"] == [
        "MPG-001",
        "BRF2-001",
        "SOR-001",
    ]
    assert trial_envelope["explicit_owner_policy_strategy_groups"] == ["BRF2-001"]
    assert trial_envelope["capital"]["amount_source"] == (
        "action_time_exchange_available_balance"
    )
    assert trial_envelope["capital"]["currency"] == "USDT"
    assert trial_envelope["attempt_cap"] == 3
    assert trial_envelope["loss_unit"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    assert trial_envelope["protection_required"] is True
    assert trial_envelope["review_required"] is True
    assert "actionable_now" not in trial_envelope
    assert "real_order_authority" not in trial_envelope
    assert trial_envelope["seat_policy_summaries"]["MPG-001"][
        "trial_envelope_role"
    ] == "existing_runtime_policy_boundary_member"
    assert trial_envelope["seat_policy_summaries"]["BRF2-001"][
        "trial_envelope_role"
    ] == "owner_recorded_30u_trial_policy_member"
    assert trial_envelope["seat_policy_summaries"]["SOR-001"][
        "trial_envelope_role"
    ] == "controlled_subaccount_policy_boundary_member"

    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["trial_envelope_id"] == "three_strategy_live_trial_envelope_v1"
    assert brf2["stage"] == "admitted_trial_asset"
    assert brf2["trial_policy_proposal_ready"] is True
    assert brf2["admitted_trial_asset_proposal_ready"] is True
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is False
    assert brf2["runtime_readiness"]["blocked_by"] == "required_facts_mapping_gap"
    assert brf2["runtime_readiness"]["tiny_live_ready"] is False
    assert brf2["runtime_readiness"]["live_submit_ready"] is False
    assert "readiness_separation" not in brf2["runtime_readiness"]
    readiness_stage = brf2["runtime_readiness"]["readiness_stage_evidence"]
    assert readiness_stage["trial_eligible"] is True
    assert readiness_stage["tiny_live_ready"] is False
    assert readiness_stage["live_submit_ready"] is False
    assert "actionable_now" not in readiness_stage
    assert "real_order_authority" not in readiness_stage
    assert readiness_stage[
        "can_create_execution_attempt"
    ] is False
    for seat in packet["seat_readiness"].values():
        assert "can_trade" not in seat["tradeability_decision_evidence"]
        assert "readiness_separation" not in seat["runtime_readiness"]
    assert brf2["owner_policy_required"] is False
    assert brf2["owner_policy_recorded"] is True
    assert brf2["owner_policy_scope_missing"] is False
    assert brf2["policy_scope"]["capital_scope"]["amount_source"] == (
        "action_time_exchange_available_balance"
    )
    assert brf2["policy_scope"]["max_notional"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    assert brf2["first_blocker"]["blocker_owner"] == "engineering"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "required_facts_mapping_gap"
    )
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == (
        "required_facts_mapping_gap"
    )
    assert packet["final_portfolio_evidence"]["brf2_policy_scope_recorded"] is True
    assert "final_evidence_packet" not in packet

    sor = packet["seat_readiness"]["SOR-001"]
    assert sor["trial_envelope_id"] == "three_strategy_live_trial_envelope_v1"
    assert sor["experiment_worthiness_review_closed"] is True
    assert sor["loss_envelope_expressed"] is True
    assert sor["first_blocker"]["first_blocker_class"] == (
        "fresh_session_range_signal_absent"
    )
    assert sor["first_blocker"]["blocker_owner"] == "market"

    assert "actionable_now" not in packet["safety_invariants"]
    assert "real_order_authority" not in packet["safety_invariants"]
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_three_strategy_portfolio_moves_brf2_to_armed_observation_after_mapping():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        brf2_required_facts_mapping=_brf2_required_facts_mapping(),
        trial_grade_signal_gate_audit=_trial_grade_signal_gate_audit(),
        signal_coverage={"events": [{"strategy_group_id": "SOR-001"}]},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["registry_admitted"] is False
    assert brf2["provisional_trial_asset_admitted"] is True
    assert brf2["admission_source"] == (
        "trial_asset_admission_proposal_owner_policy_requiredfacts"
    )
    assert brf2["registry_admission_status"] == (
        "not_registry_admitted_provisional_trial_asset"
    )
    assert brf2["required_facts_mapping_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is True
    assert brf2["runtime_readiness"]["blocked_by"] == (
        "fresh_brf2_short_signal_absent"
    )
    assert brf2["runtime_readiness"]["tiny_live_ready"] is False
    assert brf2["runtime_readiness"]["live_submit_ready"] is False
    assert "readiness_separation" not in brf2["runtime_readiness"]
    readiness_stage = brf2["runtime_readiness"]["readiness_stage_evidence"]
    assert readiness_stage["trial_eligible"] is True
    assert readiness_stage[
        "live_submit_ready_false_reason"
    ] == "no_fresh_signal"
    assert brf2["runtime_readiness"]["controlled_live_standby_ready"] is True
    assert (
        brf2["runtime_readiness"]["stage_5_waiting_live_opportunity_ready"] is True
    )
    assert (
        brf2["runtime_readiness"]["action_time_preflight_pending_fresh_signal"]
        is True
    )
    assert brf2["stage_5_status"] == "waiting_for_live_opportunity"
    assert brf2["trial_grade_signal_status"]["trial_grade_audit_ready"] is True
    assert (
        brf2["trial_grade_signal_status"][
            "trial_grade_signal_can_prepare_controlled_live"
        ]
        is True
    )
    assert (
        brf2["trial_grade_signal_status"][
            "trial_grade_signal_can_bypass_hard_safety_gates"
        ]
        is False
    )
    assert "actionable_now" not in brf2["trial_grade_signal_status"]
    assert "real_order_authority" not in brf2["trial_grade_signal_status"]
    assert brf2["first_blocker"]["decision_state"] == "not_tradable_market_wait"
    assert "verdict" not in brf2["first_blocker"]
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "fresh_brf2_short_signal_absent"
    )
    assert brf2["first_blocker"]["blocker_owner"] == "market"
    assert "next_action" not in brf2["first_blocker"]
    assert brf2["first_blocker"]["repair_checkpoint"] == (
        "continue_brf2_armed_observation_until_fresh_signal"
    )
    assert "tradeability_projection" not in brf2
    assert brf2["tradeability_decision_evidence"]["next_state_after_blocker_removed"] == (
        "live_submit_ready"
    )
    assert "tradeability_summary" not in packet
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == "fresh_signal_wait"
    assert packet["stage_5_live_opportunity_standby"]["ready"] is True
    assert packet["stage_5_live_opportunity_standby"]["standby_count"] == 3
    assert packet["stage_5_live_opportunity_standby"]["market_wait_count"] == 3
    assert (
        packet["stage_5_live_opportunity_standby"][
            "action_time_preflight_pending_fresh_signal"
        ]
        is True
    )
    for removed_projection_field in (
        "live_submit_ready_now",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in packet["stage_5_live_opportunity_standby"]
    assert (
        packet["stage_5_live_opportunity_standby"]["hard_safety_gates_relaxed"]
        is False
    )
    assert packet["checks"]["controlled_live_standby_ready"] is True
    assert packet["checks"]["controlled_live_standby_count"] == 3
    assert packet["checks"]["stage_5_waiting_live_opportunity"] is True
    assert packet["checks"]["action_time_preflight_pending_fresh_signal"] is True
    assert packet["checks"]["hard_safety_gates_relaxed"] is False


def test_three_strategy_portfolio_blocks_stage_5_when_production_authority_changes():
    module = _load_module()
    audit = copy.deepcopy(_trial_grade_signal_gate_audit())
    audit["live_trial_policy_update"][
        "does_not_change_production_grade_authority"
    ] = False

    packet = _portfolio_with_trial_grade_audit(module, audit)

    assert packet["stage_5_live_opportunity_standby"]["ready"] is False
    assert packet["stage_5_live_opportunity_standby"]["standby_count"] == 0
    assert packet["checks"]["controlled_live_standby_ready"] is False
    assert packet["seat_readiness"]["BRF2-001"]["trial_grade_signal_status"][
        "production_grade_authority_changed"
    ] is True


def test_three_strategy_portfolio_blocks_stage_5_when_hard_safety_bypass_allowed():
    module = _load_module()
    audit = copy.deepcopy(_trial_grade_signal_gate_audit())
    audit["strategy_group_rows"]["BRF2-001"]["authority_boundary"][
        "trial_grade_signal_can_bypass_hard_safety_gates"
    ] = True

    packet = _portfolio_with_trial_grade_audit(module, audit)

    assert packet["stage_5_live_opportunity_standby"]["ready"] is False
    assert "BRF2-001" not in packet["stage_5_live_opportunity_standby"][
        "standby_strategy_groups"
    ]
    assert packet["seat_readiness"]["BRF2-001"]["runtime_readiness"][
        "controlled_live_standby_ready"
    ] is False


def test_three_strategy_portfolio_blocks_stage_5_when_brf2_mapping_not_ready():
    module = _load_module()
    mapping = copy.deepcopy(_brf2_required_facts_mapping())
    mapping["required_facts_mapping_ready"] = False

    packet = _portfolio_with_trial_grade_audit(
        module,
        _trial_grade_signal_gate_audit(),
        brf2_required_facts_mapping=mapping,
    )

    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["runtime_readiness"]["controlled_live_standby_ready"] is False
    assert brf2["runtime_readiness"]["armed_observation_ready"] is False
    assert packet["stage_5_live_opportunity_standby"]["ready"] is False


def test_three_strategy_portfolio_blocks_stage_5_when_audit_row_missing():
    module = _load_module()
    audit = copy.deepcopy(_trial_grade_signal_gate_audit())
    del audit["strategy_group_rows"]["SOR-001"]

    packet = _portfolio_with_trial_grade_audit(module, audit)

    assert packet["stage_5_live_opportunity_standby"]["ready"] is False
    assert "SOR-001" not in packet["stage_5_live_opportunity_standby"][
        "standby_strategy_groups"
    ]
    assert packet["seat_readiness"]["SOR-001"]["trial_grade_signal_status"][
        "trial_grade_audit_ready"
    ] is False


def test_three_strategy_portfolio_blocks_stage_5_when_policy_scope_is_not_controlled_subaccount():
    module = _load_module()
    audit = copy.deepcopy(_trial_grade_signal_gate_audit())
    audit["live_trial_policy_update"]["scope"] = "production_trial"

    packet = _portfolio_with_trial_grade_audit(module, audit)

    assert packet["stage_5_live_opportunity_standby"]["ready"] is False
    assert packet["stage_5_live_opportunity_standby"][
        "trial_grade_policy_scope"
    ] == "production_trial"
    assert packet["checks"]["controlled_live_standby_count"] == 0


def test_three_strategy_portfolio_surfaces_brf2_fact_input_gap_after_mapping():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        brf2_required_facts_mapping=_brf2_required_facts_mapping(),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture_missing_fact_input(),
        signal_coverage={"events": [{"strategy_group_id": "SOR-001"}]},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is False
    assert brf2["runtime_readiness"]["blocked_by"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert brf2["first_blocker"]["decision_state"] == "not_tradable_facts"
    assert "verdict" not in brf2["first_blocker"]
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert brf2["first_blocker"]["blocker_owner"] == "engineering"
    assert "next_action" not in brf2["first_blocker"]
    assert brf2["first_blocker"]["repair_checkpoint"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    assert "tradeability_projection" not in brf2
    assert brf2["tradeability_decision_evidence"]["next_state_after_blocker_removed"] == (
        "armed_observation"
    )
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == (
        "brf2_watcher_fact_input_missing"
    )


def test_three_strategy_portfolio_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["schema"] == module.SCHEMA
    assert packet["seat_count"] == 3
    assert "Three Strategy Live Trial Portfolio" in output_md.read_text(
        encoding="utf-8"
    )


def test_three_strategy_portfolio_cli_omitted_capital_trial_projection_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["policy_scope"]["symbol_scope"] == [
        "brf2_research_supported_symbols_only"
    ]
    assert brf2["runtime_readiness"]["armed_observation_ready"] is True


def test_three_strategy_portfolio_cli_omitted_trial_admission_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["required_facts"]


def test_three_strategy_portfolio_cli_omitted_owner_policy_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    proposal = _trial_admission_proposal()
    proposal["proposal"]["owner_policy_recorded"] = False
    proposal["proposal"]["owner_policy_scope_missing"] = True
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(proposal), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "trial_asset_admission_candidate"
    assert brf2["owner_policy_required"] is True
    assert brf2["owner_policy_status"] == "trial_scope_policy_missing_machine_checkable"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "owner_trial_scope_or_capital_policy_missing"
    )


def test_three_strategy_portfolio_cli_omitted_required_facts_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "admitted_trial_asset"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "required_facts_mapping_gap"
    )


def test_three_strategy_portfolio_cli_omitted_runtime_capture_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "fresh_brf2_short_signal_absent"
    )


def test_three_strategy_portfolio_cli_omitted_trial_grade_audit_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    signal_json.write_text(json.dumps({"events": []}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["stage_5_live_opportunity_standby"]["status"] == (
        "pre_phase_5_trial_standby_closure"
    )
    assert packet["stage_5_live_opportunity_standby"]["standby_count"] == 0
    assert packet["seat_readiness"]["BRF2-001"]["trial_grade_signal_status"][
        "trial_grade_audit_ready"
    ] is False


def test_three_strategy_portfolio_cli_omitted_signal_coverage_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    projection_json = tmp_path / "projection.json"
    proposal_json = tmp_path / "proposal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    audit_json = tmp_path / "trial-grade-audit.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    mapping_json.write_text(json.dumps(_brf2_required_facts_mapping()), encoding="utf-8")
    capture_json.write_text(json.dumps({}), encoding="utf-8")
    audit_json.write_text(json.dumps({}), encoding="utf-8")

    exit_code = module.main(
        [
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-required-facts-mapping-json",
            str(mapping_json),
            "--brf2-runtime-signal-capture-json",
            str(capture_json),
            "--trial-grade-signal-gate-audit-json",
            str(audit_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["seat_readiness"]["SOR-001"]["observed_no_action_count"] == 0
