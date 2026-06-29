from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_tradeability_decision.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_tradeability_decision",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capital_trial_envelope_projection() -> dict:
    return {
        "status": "trial_envelope_projection_ready",
        "capital_trial_eligibility_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "candidate_family": "short_research_intake",
                "candidate_status": "short_experiment_evidence_pending_owner_policy",
                "research_intake_position": "paper_observation_admission_candidate",
                "identity_status": "main_control_research_intake_asset",
                "execution_tier": "unknown",
                "pool_stage": "tiny_live_intake_candidate_with_path_risk",
                "promotion_scope": "intake_only",
                "tiny_live_ready": False,
                "owner_policy_required": True,
                "risk_boundary_ready": False,
                "risk_boundary_missing": [
                    "capital_scope",
                    "max_notional",
                    "valid_until",
                    "trial_identity",
                ],
                "risk_envelope": {
                    "attempt_cap_per_review_cycle": 3,
                    "daily_loss_cap_units": 1,
                },
                "symbol_scope": ["owner_policy_required"],
                "side_scope": ["short"],
                "recent_opportunity_count": 11,
                "would_enter_forward_positive_count": 8,
                "tradable_forward_count": 8,
                "ranking_score": 597,
                "trial_recommendation": "experiment_candidate_prepare_pending_owner_policy",
                "trial_blockers": [
                    "source_non_executing_trial_readiness_not_closed",
                    "owner_capital_scope_not_confirmed",
                    "owner_trial_identity_not_confirmed",
                    "fresh_signal_absent",
                    "action_time_finalgate_not_reached",
                    "official_operation_layer_not_reached",
                ],
                "required_facts_draft": [
                    "closed_1h_ohlcv",
                    "squeeze_risk_state",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "BTPC-001",
                "candidate_family": "portfolio_capture_gap",
                "identity_status": "registry_or_portfolio_identity_present",
                "execution_tier": "L2",
                "candidate_status": "revise_before_trial_prepare",
                "side_scope": ["short"],
                "trial_recommendation": "defer_until_fact_source_classifier_closed",
                "trial_blockers": [
                    "no_action_or_classifier_attribution_needs_closure",
                    "stale_fact_source_classifier_blocker_unclosed",
                    "fresh_signal_absent",
                    "action_time_finalgate_not_reached",
                    "official_operation_layer_not_reached",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "RBR2-001",
                "candidate_family": "short_research_intake",
                "research_intake_position": "role_only_intake_candidate",
                "candidate_status": "role_only_short_experiment_candidate_watchlist",
                "strategy_asset_decision": "keep_observing",
                "first_blocker": "RBR2-001_role_only_range_detector_classifier_merge_note",
                "next_action": "keep_rbr2_as_range_detector_classifier_review_input",
                "post_action_expected_state": "classifier_review_input",
                "side_scope": ["short"],
                "trial_blockers": [
                    "best role is filler not main right-tail engine",
                    "fresh_signal_absent",
                ],
                "actionable_now": False,
                "real_order_authority": False,
            },
        ],
        "selected_non_mpg_trial_candidate": {
            "strategy_group_id": "BRF2-001",
            "candidate_family": "short_research_intake",
            "candidate_status": "short_experiment_evidence_pending_owner_policy",
            "research_intake_position": "paper_observation_admission_candidate",
            "promotion_scope": "intake_only",
            "tiny_live_ready": False,
            "side_scope": ["short"],
                "trial_blockers": [
                    "source_non_executing_trial_readiness_not_closed",
                    "owner_capital_scope_not_confirmed",
                    "owner_trial_identity_not_confirmed",
                    "fresh_signal_absent",
                ],
        },
    }


def _registry() -> dict:
    return {
        "status": "registry_ready",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "default_tier": "L4",
                "trial_eligible": True,
                "supported_sides": ["long"],
                "required_facts_summary": {"market": "latest price"},
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "BTPC-001",
                "default_tier": "L2",
                "trial_eligible": False,
                "supported_sides": ["short"],
                "required_facts_summary": {"market": "closed candles"},
                "actionable_now": False,
                "real_order_authority": False,
            },
            {
                "strategy_group_id": "RBR-001",
                "default_tier": "L1",
                "trial_eligible": False,
                "supported_sides": ["short_review"],
                "actionable_now": False,
                "real_order_authority": False,
            },
        ],
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {
                "tier": "L4",
                "mode": "tiny_real_order_eligible",
            },
            "BTPC-001": {
                "tier": "L2",
                "mode": "shadow_candidate",
            },
        }
    }


def _signal_coverage() -> dict:
    return {
        "status": "mainline_no_signal_low_priority_broader_would_enter",
        "checks": {
            "runtime_ready_signal_count": 0,
            "broader_would_enter_signal_count": 1,
        },
        "broader_observation": {
            "would_enter_signals": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETH/USDT:USDT",
                    "side": "long",
                    "signal_type": "would_enter",
                    "not_live_signal": True,
                    "actionable_now": False,
                    "real_order_authority": False,
                    "reason": "CPM-RO-001_registry_identity_review",
                },
                {
                    "strategy_group_id": "RBR-001",
                    "symbol": "ADA/USDT:USDT",
                    "side": "short",
                    "signal_type": "would_enter",
                    "not_live_signal": True,
                    "actionable_now": False,
                    "real_order_authority": False,
                }
            ]
        },
    }


def _runtime_safety_state() -> dict:
    return {
        "status": "live_submit_standby_waiting_for_market",
        "checks": {
            "live_submit_ready": False,
            "fresh_signal_state": "none",
        },
        "decision": {
            "live_submit_ready": False,
            "live_submit_ready_false_reason": "no_fresh_signal",
            "actionable_now": False,
            "real_order_authority": False,
        },
        "runtime_safety_state": {
            "state_family": "Runtime Safety State",
            "status": "live_submit_standby_waiting_for_market",
            "primary_judgment_source": True,
            "live_submit_ready": False,
            "live_submit_ready_false_reason": "no_fresh_signal",
            "actionable_now": False,
            "real_order_authority": False,
            "fresh_signal_state": "none",
        },
    }


def _runtime_safety_state_ready_for(strategy_group_id: str | None) -> dict:
    packet = {
        "status": "live_submit_ready",
        "checks": {
            "live_submit_ready": True,
            "fresh_signal_state": "fresh_selected_strategygroup_signal",
        },
        "decision": {
            "live_submit_ready": True,
            "actionable_now": True,
            "real_order_authority": True,
        },
        "runtime_safety_state": {
            "state_family": "Runtime Safety State",
            "status": "live_submit_ready",
            "primary_judgment_source": True,
            "live_submit_ready": True,
            "ready_for_finalgate_checkpoint": True,
            "live_submit_ready_false_reason": "awaiting_finalgate_and_operation_layer",
            "fresh_signal_state": "fresh_selected_strategygroup_signal",
        },
    }
    if strategy_group_id:
        packet["selected_strategy_group_id"] = strategy_group_id
        packet["runtime_scope"] = {"strategy_group_id": strategy_group_id}
        packet["fresh_signal"] = {"strategy_group_id": strategy_group_id}
    return packet


def _runtime_safety_state_ready_for_with_legacy_mirrors_false(
    strategy_group_id: str | None,
) -> dict:
    packet = _runtime_safety_state_ready_for(strategy_group_id)
    packet["checks"] = {
        "live_submit_ready": False,
        "fresh_signal_state": "none",
    }
    packet["decision"] = {
        "live_submit_ready": False,
        "live_submit_ready_false_reason": "no_fresh_signal",
        "actionable_now": False,
        "real_order_authority": False,
    }
    packet["runtime_safety_state"] = {
        "state_family": "Runtime Safety State",
        "status": "live_submit_ready",
        "primary_judgment_source": True,
        "live_submit_ready": True,
        "ready_for_finalgate_checkpoint": True,
        "live_submit_ready_false_reason": "awaiting_finalgate_and_operation_layer",
        "fresh_signal_state": "fresh_selected_strategygroup_signal",
    }
    return packet


def _runtime_safety_state_with_brf2_candidate_authorization_state() -> dict:
    packet = _runtime_safety_state()
    packet["runtime_safety_state"] = {
        "state_family": "Runtime Safety State",
        "status": "processing_ready_for_finalgate_checkpoint",
        "primary_judgment_source": True,
        "live_submit_ready": False,
        "live_submit_ready_false_reason": "awaiting_finalgate_and_operation_layer",
        "actionable_now": False,
        "real_order_authority": False,
        "fresh_signal_state": "fresh",
        "candidate_authorization_state": {
            "state_family": "Runtime Safety State",
            "state_role": "candidate_authorization",
            "state_source": "brf2_shadow_candidate_evidence_provenance",
            "strategy_group_id": "BRF2-001",
            "status": "candidate_authorization_evidence_pending",
            "primary_judgment_source": False,
            "shadow_candidate_evidence_ready": True,
            "authorization_evidence_created": False,
            "ready_for_finalgate_checkpoint": False,
            "first_blocker_class": (
                "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
            ),
            "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
            "live_submit_authority": False,
            "operation_layer_authority": False,
            "actionable_now": False,
            "real_order_authority": False,
        },
    }
    return packet


def _trial_asset_admission_proposal() -> dict:
    return {
        "status": "trial_asset_admission_proposal_ready",
        "proposal": {
            "strategy_group_id": "BRF2-001",
            "current_stage": "tiny_live_intake_candidate",
            "proposed_stage": "trial_asset_admission_candidate",
            "next_action": "record_owner_trial_scope_policy",
            "after_next_state": "admitted_trial_asset",
            "actionable_now": False,
            "real_order_authority": False,
        },
        "checks": {
            "owner_policy_blocker_present": True,
            "owner_decision_required": False,
            "actionable_now": False,
            "real_order_authority": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _trial_asset_admission_proposal_with_policy() -> dict:
    packet = _trial_asset_admission_proposal()
    packet["proposal"] = {
        **packet["proposal"],
        "proposed_stage": "admitted_trial_asset",
        "owner_policy_required": False,
        "owner_policy_recorded": True,
        "owner_policy_scope_missing": False,
        "next_action": "close_brf2_required_facts_mapping_for_armed_observation",
        "after_next_state": "armed_observation",
    }
    packet["checks"] = {
        **packet["checks"],
        "owner_policy_blocker_present": False,
        "owner_policy_recorded": True,
        "owner_policy_scope_missing": False,
    }
    return packet


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
            "authority_boundary": "owner_policy_only; actionable_now=false",
        },
    }


def _three_strategy_portfolio_with_brf2_armed_observation() -> dict:
    return {
        "status": "three_strategy_live_trial_portfolio_ready",
        "selected_strategy_groups": ["MPG-001", "BRF2-001", "SOR-001"],
        "trial_envelope": {
            "trial_envelope_id": "three_strategy_live_trial_envelope_v1",
            "state_family": "Strategy Policy / Trial Envelope",
            "primary_judgment_source": True,
            "applies_to_strategy_groups": ["MPG-001", "BRF2-001", "SOR-001"],
            "explicit_owner_policy_strategy_groups": ["BRF2-001"],
            "capital": {
                "type": "isolated_subaccount_full_allocation",
                "allocation_mode": "full_available_isolated_subaccount",
                "amount_source": "action_time_exchange_available_balance",
                "currency": "USDT",
                "loss_capable": True,
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
            "leverage_scenario": "5x_scenario_not_authority",
            "max_notional": {
                "currency": "USDT",
                "calculation": "action_time_exchange_available_balance * leverage_scenario",
                "balance_source": "action_time_exchange_available_balance",
                "basis": "controlled subaccount dynamic allocation x leverage scenario",
            },
            "protection_required": True,
            "review_required": True,
            "seat_policy_summaries": {
                "BRF2-001": {
                    "strategy_group_id": "BRF2-001",
                    "stage": "armed_observation",
                    "owner_policy_status": "owner_trial_scope_policy_recorded",
                    "owner_policy_required": False,
                    "capital_scope": {
                        "type": "isolated_subaccount_full_allocation",
                        "allocation_mode": "full_available_isolated_subaccount",
                        "amount_source": "action_time_exchange_available_balance",
                        "currency": "USDT",
                        "loss_capable": True,
                    },
                    "attempt_cap": 3,
                    "loss_unit": {
                        "currency": "USDT",
                        "calculation": "action_time_exchange_available_balance / attempt_cap",
                        "balance_source": "action_time_exchange_available_balance",
                        "basis": "controlled subaccount dynamic allocation / attempt cap",
                    },
                    "symbol_scope": ["brf2_research_supported_symbols_only"],
                    "side_scope": ["short"],
                    "trial_envelope_role": "owner_recorded_30u_trial_policy_member",
                }
            },
            "actionable_now": False,
            "real_order_authority": False,
        },
        "seat_readiness": {
            "MPG-001": {
                "stage": "armed_observation",
                "runtime_readiness": {
                    "controlled_live_standby_ready": True,
                    "stage_5_waiting_live_opportunity_ready": True,
                    "action_time_preflight_pending_fresh_signal": True,
                },
            },
            "BRF2-001": {
                "stage": "armed_observation",
                "required_facts_mapping_ready": True,
                "runtime_readiness": {
                    "armed_observation_ready": True,
                    "tiny_live_ready": False,
                    "live_submit_ready": False,
                    "controlled_live_standby_ready": True,
                    "stage_5_waiting_live_opportunity_ready": True,
                    "action_time_preflight_pending_fresh_signal": True,
                },
                "first_blocker": {
                    "decision_state": "not_tradable_market_wait",
                    "first_blocker_class": "fresh_brf2_short_signal_absent",
                    "blocker_owner": "market",
                    "next_action": (
                        "continue_brf2_armed_observation_until_fresh_signal"
                    ),
                },
                "tradeability_decision_evidence": {
                    "can_trade": False,
                    "decision_state": "not_tradable_market_wait",
                    "next_state_after_blocker_removed": "live_submit_ready",
                },
            },
            "SOR-001": {
                "stage": "armed_observation",
                "runtime_readiness": {
                    "controlled_live_standby_ready": True,
                    "stage_5_waiting_live_opportunity_ready": True,
                    "action_time_preflight_pending_fresh_signal": True,
                },
            }
        },
        "checks": {
            "actionable_now": False,
            "real_order_authority": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _trial_grade_signal_gate_audit() -> dict:
    return {
        "status": "trial_grade_signal_gate_audit_ready",
        "strategy_group_rows": {
            "BRF2-001": {
                "strategy_group_id": "BRF2-001",
                "signal_grade_current_assessment": {
                    "current_gate_looks_like": "controlled_live_standby",
                },
                "verified_recent_window_counts": {
                    "windows_days": {
                        "30": {
                            "trial_grade_observation_count": 2,
                            "action_time_trial_submit_count": 0,
                        },
                    },
                },
                "fixture_replay_projection": {
                    "trial_grade_trigger_case_count": 2,
                    "max_loss_estimate_usdt": "10",
                },
                "tomorrow_same_structure_assessment": {
                    "would_enter_controlled_live_trial": True,
                },
                "authority_boundary": {
                    "trial_grade_signal_can_prepare_controlled_live": True,
                    "trial_grade_signal_can_bypass_hard_safety_gates": False,
                },
            },
        },
        "checks": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _brf2_runtime_signal_capture(signal_state: str = "fresh_signal_absent") -> dict:
    fresh = signal_state == "fresh_signal_present"
    return {
        "status": "brf2_runtime_signal_capture_ready",
        "signal_detector_preview": {
            "current_signal_state": signal_state,
            "fresh_signal_present": fresh,
            "first_blocker_class": (
                "brf2_fresh_short_signal_present_non_executing"
                if fresh
                else "fresh_brf2_short_signal_absent"
            ),
            "first_blocker_owner": "runtime" if fresh else "market",
            "signal_capture_checkpoint": (
                "build_brf2_shadow_candidate_evidence"
                if fresh
                else "continue_brf2_armed_observation_until_fresh_signal"
            ),
            "missing_required_fact_keys": [] if fresh else ["closed_1h_ohlcv"],
            "active_disable_fact_keys": [],
        },
        "shadow_candidate_shape": {
            "shadow_candidate_ready": fresh,
            "shadow_candidate_type": (
                "brf2_non_executing_short_signal_candidate_evidence"
            ),
        },
        "checks": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _brf2_runtime_signal_capture_missing_fact_input() -> dict:
    packet = _brf2_runtime_signal_capture("fact_input_missing")
    packet["fact_input_status"] = "brf2_runtime_signal_facts_missing_watcher_input"
    packet["fact_input_present"] = False
    packet["watcher_tick_present"] = False
    packet["signal_detector_preview"] = {
        **packet["signal_detector_preview"],
        "fact_input_present": False,
        "watcher_tick_present": False,
        "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
        "fresh_signal_present": False,
        "current_signal_state": "fact_input_missing",
        "first_blocker_class": "brf2_watcher_fact_input_missing",
        "first_blocker_owner": "engineering",
        "signal_capture_checkpoint": "attach_brf2_watcher_fact_input_producer",
    }
    packet["shadow_candidate_shape"]["shadow_candidate_ready"] = False
    return packet


def _brf2_shadow_candidate_evidence() -> dict:
    return {
        "status": "brf2_shadow_candidate_evidence_ready",
        "strategy_group_id": "BRF2-001",
        "shadow_candidate_evidence_ready": True,
        "shadow_candidate_evidence": {
            "shadow_candidate_evidence_id": (
                "brf2-shadow-evidence:brf2-signal-001"
            ),
            "shadow_candidate_evidence_type": (
                "brf2_non_executing_short_signal_candidate_evidence"
            ),
            "strategy_group_id": "BRF2-001",
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
            "source_signal_observation_id": "brf2-signal-001",
            "symbol": "ADA/USDT:USDT",
            "side": "short",
            "signal_state": "fresh_signal_present",
        },
        "first_blocker": {
            "class": "candidate_authorization_evidence_not_created",
            "owner": "runtime",
            "next_action": "prepare_fresh_candidate_authorization_evidence",
        },
        "checks": {
            "actionable_now": False,
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "actionable_now": False,
            "real_order_authority": False,
            "authorization_evidence_created": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def test_tradeability_decision_classifies_first_blockers_without_authority():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert packet["status"] == "tradeability_decision_ready"
    assert packet["summary"]["top_decision"] == "not_tradable_asset_admission"
    assert rows["BRF2-001"]["decision"] == "not_tradable_asset_admission"
    assert rows["BRF2-001"]["first_blocker_class"] == (
        "strategy_group_not_admitted_as_final_trial_asset"
    )
    assert rows["BRF2-001"]["blocker_owner"] == "engineering"
    assert rows["BRF2-001"]["next_action"] == "build_trial_asset_admission_proposal"
    assert rows["BRF2-001"]["after_next_state"] == "trial_asset_admission_candidate"

    assert rows["MPG-001"]["decision"] == "not_tradable_market_wait"
    assert rows["MPG-001"]["stage"] == "armed_observation"
    assert rows["MPG-001"]["blocker_owner"] == "market"

    assert rows["BTPC-001"]["decision"] == "not_tradable_facts"
    assert rows["BTPC-001"]["first_blocker_class"] == (
        "required_facts_or_classifier_mapping_unclosed"
    )

    assert rows["RBR-001"]["decision"] == "not_tradable_strategy_quality"
    assert rows["RBR-001"]["stage"] == "observe_only_would_enter"
    assert rows["RBR-001"]["evidence_snapshot"]["latest_observe_only_symbol"] == (
        "ADA/USDT:USDT"
    )

    assert rows["RBR2-001"]["stage"] == "role_only_intake_candidate"
    assert rows["RBR2-001"]["decision"] == "not_tradable_strategy_quality"

    assert packet["summary"]["tradable_now_count"] == 0
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]
    assert packet["checks"]["market_wait_only_after_admission"] is True
    assert packet["checks"]["row_count_matches_decision_rows"] is True
    assert packet["checks"]["one_current_decision_per_strategy_group"] is True
    assert "tradable_now_count" not in packet["checks"]
    assert "actionable_now_count" not in packet["checks"]
    assert "real_order_authority_count" not in packet["checks"]
    for row in packet["decision_rows"]:
        assert "actionable_now" not in row
        assert "real_order_authority" not in row
        assert row["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_tradeability_decision_advances_brf2_to_policy_blocker_after_proposal():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["BRF2-001"]["stage"] == "trial_asset_admission_candidate"
    assert rows["BRF2-001"]["decision"] == "not_tradable_policy"
    assert rows["BRF2-001"]["blocker_owner"] == "owner"
    assert rows["BRF2-001"]["next_action"] == "record_owner_trial_scope_policy"
    assert rows["BRF2-001"]["after_next_state"] == "admitted_trial_asset"
    assert rows["BRF2-001"]["runtime_scope_status"][
        "trial_asset_admission_proposal_ready"
    ] is True
    assert packet["owner_summary"]["owner_policy_blocker_present"] is True
    assert packet["owner_summary"]["owner_intervention_required"] is False
    assert "owner_policy_blocker_present" not in packet["checks"]
    assert "owner_decision_required" not in packet["checks"]


def test_tradeability_decision_advances_brf2_to_facts_blocker_after_policy_recorded():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "admitted_trial_asset"
    assert brf2["decision"] == "not_tradable_facts"
    assert brf2["first_blocker_class"] == "required_facts_mapping_gap"
    assert brf2["blocker_owner"] == "engineering"
    assert brf2["next_action"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert brf2["after_next_state"] == "armed_observation"
    assert brf2["runtime_scope_status"]["owner_policy_recorded"] is True
    assert brf2["runtime_scope_status"]["owner_policy_scope_missing"] is False
    assert brf2["runtime_scope_status"]["brf2_trial_identity"] == (
        "BRF2_CONTROLLED_SHORT_TRIAL_V0"
    )
    assert brf2["policy_scope"]["capital_scope"]["amount_source"] == (
        "action_time_exchange_available_balance"
    )
    assert brf2["policy_scope"]["max_notional"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    secondary = {row["blocker"] for row in brf2["secondary_blockers"]}
    resolved = {row["blocker"] for row in brf2["resolved_blockers"]}
    assert "owner_capital_scope_not_confirmed" not in secondary
    assert "owner_trial_identity_not_confirmed" not in secondary
    assert "owner_capital_scope_not_confirmed" in resolved
    assert "owner_trial_identity_not_confirmed" in resolved
    assert all(
        row["resolved_by"] == "brf2_owner_trial_policy_scope"
        for row in brf2["resolved_blockers"]
    )
    assert packet["owner_summary"]["owner_policy_blocker_present"] is False
    assert packet["summary"]["engineering_first_blocker_count"] >= 1
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_tradeability_decision_moves_brf2_to_market_wait_after_mapping():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_market_wait"
    assert brf2["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert brf2["blocker_owner"] == "market"
    assert brf2["next_action"] == (
        "continue_brf2_armed_observation_until_fresh_signal"
    )
    assert brf2["after_next_state"] == "live_submit_ready"
    assert brf2["required_facts_status"] == "ready"
    assert brf2["signal_grade_status"]["controlled_live_standby_ready"] is True
    assert (
        brf2["signal_grade_status"]["stage_5_waiting_live_opportunity_ready"]
        is True
    )
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False
    assert packet["summary"]["tradable_now_count"] == 0
    assert packet["summary"]["controlled_live_standby_count"] == 3
    assert packet["summary"]["stage_5_waiting_live_opportunity_ready_count"] == 3
    assert packet["checks"]["market_wait_only_after_admission"] is True


def test_tradeability_decision_consumes_july_bullish_rebound_trade_paths():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    closure = packet["july_bullish_rebound_trade_path_closure"]
    paths = {path["path_id"]: path for path in closure["paths"]}
    exits = {
        row["strategy_group_id"]: row for row in closure["observe_only_exits"]
    }

    assert packet["checks"]["july_bullish_rebound_paths_consumed"] is True
    assert packet["checks"]["cpm_non_market_blocker_preserved"] is True
    assert closure["summary"]["required_long_paths_present"] is True
    assert closure["summary"]["required_short_guard_paths_present"] is True
    assert closure["summary"]["long_side_path_count"] == 3
    assert closure["summary"]["short_side_guard_path_count"] == 2
    assert closure["summary"]["required_rbr_exit_rows_present"] is True
    assert closure["checks"]["capital_scope_uses_action_time_exchange_available_balance"]
    assert closure["checks"]["no_fixed_30u_contract"] is True
    assert closure["checks"]["rbr_observe_only_has_exit_decision"] is True

    assert rows["CPM-RO-001"]["first_blocker_class"] == (
        "cpm_registry_identity_gap"
    )
    assert rows["CPM-RO-001"]["decision"] == "not_tradable_asset_admission"
    assert rows["CPM-RO-001"]["stage"] == "observe_only_would_enter"
    assert rows["CPM-RO-001"]["required_facts_status"] == "missing"

    assert paths["CPM-LONG"]["trigger_required_facts"] == [
        "htf_trend_intact",
        "pullback_depth_normal",
        "reclaim_confirmed",
        "invalidated_below_level",
        "liquidity_ok",
        "funding_not_extreme",
        "action_time_available_balance",
    ]
    assert paths["CPM-SHORT"]["trigger_required_facts"] == [
        "htf_weakness_or_rebound_context",
        "bounce_depth_normal",
        "bounce_loss_confirmed",
        "invalidated_above_level",
        "liquidity_ok",
        "funding_not_extreme",
        "action_time_available_balance",
    ]
    assert paths["CPM-LONG"]["first_blocker"] == "cpm_registry_identity_gap"
    assert paths["CPM-LONG"]["blocker_owner"] == "engineering"
    assert paths["CPM-SHORT"]["first_blocker"] == "cpm_registry_identity_gap"
    assert paths["CPM-SHORT"]["blocker_owner"] == "engineering"
    assert paths["BRF2-SHORT"]["required_facts_mapping_status"] == "ready"
    assert paths["BRF2-SHORT"]["first_blocker"] == "fresh_brf2_short_signal_absent"
    assert paths["MPG-LONG"]["first_blocker"] == "fresh_mpg_long_signal_absent"
    assert paths["SOR-LONG"]["first_blocker"] == (
        "strategy_group_not_admitted_as_final_trial_asset"
    )
    assert paths["SOR-LONG"]["blocker_owner"] == "engineering"

    mpg_diff = paths["MPG-LONG"]["production_vs_trial_trigger_diff"]
    sor_diff = paths["SOR-LONG"]["production_vs_trial_trigger_diff"]
    assert "closed_momentum_persistence_bar" in mpg_diff["hard_gates"]
    assert "thin_recent_replay_sample" in mpg_diff["review_warnings"]
    assert "FinalGate" in mpg_diff["cannot_relax"]
    assert "session_window_active" in sor_diff["hard_gates"]
    assert "session_slippage_estimate_rough" in sor_diff["review_warnings"]
    assert "Operation Layer" in sor_diff["cannot_relax"]

    assert exits["RBR-001"]["exit_decision"] == "park"
    assert exits["RBR2-001"]["exit_decision"] == "keep_observing"
    for path in paths.values():
        assert path["can_trade_now"] is False
        assert path["capital_scope_source"] == (
            "action_time_exchange_available_balance"
        )
        assert path["first_blocker"]
        assert path["next_action"]
        assert path["post_action_expected_state"]
        assert "actionable_now" not in path
        assert "real_order_authority" not in path


def test_july_closure_does_not_pass_rbr_exit_check_when_rows_are_absent():
    module = _load_module()

    closure = module._july_bullish_rebound_trade_path_closure(
        [
            {
                "strategy_group_id": "MPG-001",
                "trade_paths": [
                    {
                        "path_id": "MPG-LONG",
                        "side": "long",
                        "capital_scope_source": (
                            "action_time_exchange_available_balance"
                        ),
                        "can_trade_now": False,
                    }
                ],
            }
        ]
    )

    assert closure["summary"]["required_rbr_exit_rows_present"] is False
    assert closure["checks"]["rbr_observe_only_has_exit_decision"] is False


def test_tradeability_decision_does_not_default_portfolio_blocker_to_market_wait():
    module = _load_module()
    portfolio = _three_strategy_portfolio_with_brf2_armed_observation()
    portfolio["seat_readiness"]["BRF2-001"]["first_blocker"].pop(
        "decision_state"
    )
    portfolio["seat_readiness"]["BRF2-001"]["tradeability_decision_evidence"].pop(
        "decision_state"
    )

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=portfolio,
        brf2_runtime_signal_capture={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["decision"] == "not_tradable_execution_gate"
    assert brf2["decision"] != "not_tradable_market_wait"
    assert (
        brf2["first_blocker_class"]
        == "portfolio_tradeability_decision_state_missing"
    )
    assert brf2["blocker_owner"] == "engineering"
    assert brf2["next_action"] == "repair_portfolio_tradeability_decision_evidence"


def test_tradeability_decision_prefers_trial_envelope_before_legacy_seat_policy():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["policy_scope"]["source"] == "trial_envelope"
    assert brf2["policy_scope"]["trial_envelope_id"] == (
        "three_strategy_live_trial_envelope_v1"
    )
    assert brf2["policy_scope"]["capital_scope"]["amount_source"] == (
        "action_time_exchange_available_balance"
    )
    assert brf2["policy_scope"]["attempt_cap"] == 3
    assert brf2["policy_scope"]["loss_unit"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    assert brf2["policy_scope"]["protection_required"] is True
    assert brf2["policy_scope"]["review_required"] is True
    assert brf2["runtime_scope_status"]["trial_envelope_id"] == (
        "three_strategy_live_trial_envelope_v1"
    )
    assert brf2["runtime_scope_status"]["trial_envelope_primary"] is True
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_tradeability_decision_exposes_brf2_watcher_fact_input_gap():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture_missing_fact_input(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_facts"
    assert brf2["first_blocker_class"] == "brf2_watcher_fact_input_missing"
    assert brf2["blocker_owner"] == "engineering"
    assert brf2["next_action"] == "attach_brf2_watcher_fact_input_producer"
    assert brf2["after_next_state"] == "armed_observation"
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False
    assert packet["summary"]["top_strategy_group_id"] == "BRF2-001"
    assert packet["summary"]["top_decision"] == "not_tradable_facts"


def test_tradeability_decision_moves_brf2_to_candidate_packet_after_fresh_capture():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(
            "fresh_signal_present"
        ),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_execution_gate"
    assert brf2["first_blocker_class"] == (
        "brf2_candidate_authorization_evidence_not_created"
    )
    assert brf2["blocker_owner"] == "runtime"
    assert brf2["next_action"] == (
        "build_brf2_shadow_candidate_evidence_for_action_time_chain"
    )
    assert brf2["after_next_state"] == "shadow_candidate_evidence_ready"
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False
    assert packet["summary"]["tradable_now_count"] == 0


def test_tradeability_decision_moves_brf2_past_candidate_packet_when_ready():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=(
            _runtime_safety_state_with_brf2_candidate_authorization_state()
        ),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(
            "fresh_signal_present"
        ),
        brf2_shadow_candidate_evidence=(
            _brf2_shadow_candidate_evidence()
        ),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_execution_gate"
    assert brf2["first_blocker_class"] == (
        "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
    )
    assert brf2["blocker_owner"] == "runtime"
    assert brf2["next_action"] == "prepare_fresh_candidate_authorization_evidence"
    assert brf2["after_next_state"] == (
        "candidate_authorization_evidence_pending_action_time_finalgate"
    )
    assert "brf2_shadow_candidate_evidence_ready" not in (
        brf2["runtime_scope_status"]
    )
    assert "brf2_shadow_candidate_evidence_status" not in (
        brf2["runtime_scope_status"]
    )
    candidate_provenance = brf2["brf2_shadow_candidate_evidence_provenance"]
    assert candidate_provenance["projection_role"] == (
        "shadow_candidate_evidence_provenance"
    )
    assert candidate_provenance["primary_judgment_source"] is False
    assert candidate_provenance["non_executing_evidence"] is True
    assert candidate_provenance["shadow_candidate_evidence_ready"] is True
    for removed_projection_field in (
        "live_submit_authority",
        "operation_layer_authority",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in candidate_provenance
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False
    assert packet["summary"]["tradable_now_count"] == 0


def test_tradeability_prefers_runtime_safety_candidate_authorization_state():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=(
            _runtime_safety_state_with_brf2_candidate_authorization_state()
        ),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(
            "fresh_signal_present"
        ),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["decision"] == "not_tradable_execution_gate"
    assert brf2["first_blocker_class"] == (
        "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
    )
    assert brf2["next_action"] == "prepare_fresh_candidate_authorization_evidence"
    assert brf2["after_next_state"] == (
        "candidate_authorization_evidence_pending_action_time_finalgate"
    )
    assert (
        brf2["brf2_shadow_candidate_evidence_provenance"][
            "shadow_candidate_evidence_ready"
        ]
        is False
    )
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_does_not_read_default_brf2_shadow_candidate_evidence_provenance(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    provenance = brf2["brf2_shadow_candidate_evidence_provenance"]
    assert provenance["active"] is False
    assert provenance["shadow_candidate_evidence_ready"] is False
    assert provenance["primary_judgment_source"] is False
    assert "actionable_now" not in provenance
    assert "real_order_authority" not in provenance
    runtime_scope = brf2["runtime_scope_status"]
    assert runtime_scope["brf2_runtime_signal_capture_status"] == ""
    assert runtime_scope["brf2_current_signal_state"] == ""
    assert brf2["first_blocker_class"] != "fresh_brf2_short_signal_absent"


def test_cli_explicit_brf2_runtime_signal_capture_path_feeds_signal_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    brf2_capture_json = tmp_path / "brf2-capture.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    brf2_capture_json.write_text(
        json.dumps(_brf2_runtime_signal_capture()),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--brf2-runtime-signal-capture-json",
            str(brf2_capture_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    runtime_scope = brf2["runtime_scope_status"]
    assert (
        runtime_scope["brf2_runtime_signal_capture_status"]
        == "brf2_runtime_signal_capture_ready"
    )
    assert runtime_scope["brf2_current_signal_state"] == "fresh_signal_absent"
    assert brf2["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_runtime_safety_state_does_not_read_default_runtime_safety(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    policy_json.write_text(json.dumps({}), encoding="utf-8")
    admission_json.write_text(json.dumps({}), encoding="utf-8")
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]
    assert mpg["decision"] != "tradable_now"
    assert mpg["first_blocker_class"] != "fresh_executable_signal_absent"
    assert packet["summary"]["tradable_now_count"] == 0
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]


def test_cli_rejects_legacy_live_submit_readiness_alias(tmp_path: Path) -> None:
    projection_json = tmp_path / "projection.json"
    runtime_safety_json = tmp_path / "runtime-safety.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(
        json.dumps(_capital_trial_envelope_projection()),
        encoding="utf-8",
    )
    runtime_safety_json.write_text(json.dumps(_runtime_safety_state()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--live-submit-readiness-json",
            str(runtime_safety_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --live-submit-readiness-json" in result.stderr
    assert not output_json.exists()


def test_cli_without_explicit_trial_asset_admission_does_not_read_default_proposal(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    policy_json.write_text(json.dumps({}), encoding="utf-8")
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "tiny_live_intake_candidate"
    assert brf2["decision"] == "not_tradable_asset_admission"
    assert brf2["first_blocker_class"] == (
        "strategy_group_not_admitted_as_final_trial_asset"
    )
    assert brf2["runtime_scope_status"][
        "trial_asset_admission_proposal_ready"
    ] is False
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_trial_asset_admission_path_feeds_strategy_asset_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    policy_json = tmp_path / "policy.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal()),
        encoding="utf-8",
    )
    policy_json.write_text(json.dumps({}), encoding="utf-8")
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "trial_asset_admission_candidate"
    assert brf2["decision"] == "not_tradable_policy"
    assert brf2["first_blocker_class"] == "owner_trial_scope_or_capital_policy_missing"
    assert brf2["runtime_scope_status"][
        "trial_asset_admission_proposal_ready"
    ] is True
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_brf2_owner_policy_does_not_read_default_scope(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal()),
        encoding="utf-8",
    )
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "trial_asset_admission_candidate"
    assert brf2["decision"] == "not_tradable_policy"
    assert brf2["first_blocker_class"] == "owner_trial_scope_or_capital_policy_missing"
    runtime_scope = brf2["runtime_scope_status"]
    assert runtime_scope["owner_policy_recorded"] is False
    assert runtime_scope["owner_policy_scope_missing"] is True
    assert runtime_scope["brf2_trial_identity"] == ""
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_brf2_owner_policy_path_feeds_policy_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    policy_json = tmp_path / "policy.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal()),
        encoding="utf-8",
    )
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "trial_asset_admission_candidate"
    assert brf2["decision"] == "not_tradable_facts"
    assert brf2["first_blocker_class"] == "required_facts_mapping_gap"
    runtime_scope = brf2["runtime_scope_status"]
    assert runtime_scope["owner_policy_recorded"] is True
    assert runtime_scope["owner_policy_scope_missing"] is False
    assert runtime_scope["brf2_trial_identity"] == "BRF2_CONTROLLED_SHORT_TRIAL_V0"
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_three_strategy_portfolio_does_not_read_default_trial_envelope(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    policy_json = tmp_path / "policy.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal_with_policy()),
        encoding="utf-8",
    )
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["decision"] == "not_tradable_facts"
    assert brf2["first_blocker_class"] == "required_facts_mapping_gap"
    assert brf2["policy_scope"]["source"] == "brf2_owner_trial_policy_scope"
    assert brf2["runtime_scope_status"]["live_trial_portfolio_seat"] is False
    assert brf2["runtime_scope_status"]["trial_envelope_id"] == ""
    assert brf2["runtime_scope_status"]["trial_envelope_primary"] is False
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_three_strategy_portfolio_path_feeds_trial_envelope_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal_with_policy()),
        encoding="utf-8",
    )
    portfolio_json.write_text(
        json.dumps(_three_strategy_portfolio_with_brf2_armed_observation()),
        encoding="utf-8",
    )
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["stage"] == "armed_observation"
    assert brf2["decision"] == "not_tradable_market_wait"
    assert brf2["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert brf2["policy_scope"]["source"] == "trial_envelope"
    assert brf2["runtime_scope_status"]["live_trial_portfolio_seat"] is True
    assert brf2["runtime_scope_status"]["trial_envelope_id"] == (
        "three_strategy_live_trial_envelope_v1"
    )
    assert brf2["runtime_scope_status"]["trial_envelope_primary"] is True
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_trial_grade_audit_does_not_read_default_audit(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal_with_policy()),
        encoding="utf-8",
    )
    portfolio_json.write_text(
        json.dumps(_three_strategy_portfolio_with_brf2_armed_observation()),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    signal_grade = brf2["signal_grade_status"]
    assert signal_grade["trial_grade_audit_ready"] is False
    assert "current_gate_looks_like" not in signal_grade
    assert signal_grade["controlled_live_standby_ready"] is True
    assert signal_grade["stage_5_waiting_live_opportunity_ready"] is True
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_trial_grade_audit_path_feeds_trial_grade_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    admission_json.write_text(
        json.dumps(_trial_asset_admission_proposal_with_policy()),
        encoding="utf-8",
    )
    portfolio_json.write_text(
        json.dumps(_three_strategy_portfolio_with_brf2_armed_observation()),
        encoding="utf-8",
    )
    trial_grade_json.write_text(
        json.dumps(_trial_grade_signal_gate_audit()),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    signal_grade = brf2["signal_grade_status"]
    assert signal_grade["trial_grade_audit_ready"] is True
    assert signal_grade["current_gate_looks_like"] == "controlled_live_standby"
    assert signal_grade["recent_30d_trial_grade_observation_count"] == 2
    assert signal_grade["fixture_trial_grade_trigger_case_count"] == 2
    assert signal_grade["trial_grade_signal_can_prepare_controlled_live"] is True
    assert signal_grade["trial_grade_signal_can_bypass_hard_safety_gates"] is False
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_signal_coverage_does_not_read_default_observation(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert "RBR-001" not in rows
    assert all(
        row["runtime_scope_status"]["observe_only_would_enter"] is False
        for row in rows.values()
    )
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]


def test_cli_explicit_signal_coverage_path_feeds_observe_only_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    rbr = rows["RBR-001"]
    assert rbr["runtime_scope_status"]["observe_only_would_enter"] is True
    assert rbr["evidence_snapshot"]["latest_observe_only_symbol"] == "ADA/USDT:USDT"
    assert rbr["evidence_snapshot"]["latest_observe_only_side"] == "short"
    assert "actionable_now" not in rbr
    assert "real_order_authority" not in rbr
    assert rbr["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_without_explicit_capital_trial_envelope_projection_does_not_read_default_candidate_rows(
    tmp_path: Path,
) -> None:
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert "BRF2-001" not in rows
    assert packet["summary"]["selected_candidate_strategy_group_id"] == ""
    assert packet["summary"]["selected_candidate_decision"] == "none"
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]


def test_cli_explicit_capital_trial_envelope_projection_path_feeds_candidate_rows(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    assert brf2["evidence_snapshot"]["candidate_status"] == (
        "short_experiment_evidence_pending_owner_policy"
    )
    assert brf2["decision"] == "not_tradable_asset_admission"
    assert packet["summary"]["selected_candidate_strategy_group_id"] == "BRF2-001"
    assert packet["summary"]["selected_candidate_decision"] == (
        "not_tradable_asset_admission"
    )
    assert "actionable_now" not in brf2
    assert "real_order_authority" not in brf2
    assert brf2["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_runtime_safety_state_path_feeds_runtime_safety_state(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    live_json = tmp_path / "live.json"
    policy_json = tmp_path / "policy.json"
    admission_json = tmp_path / "admission.json"
    portfolio_json = tmp_path / "portfolio.json"
    trial_grade_json = tmp_path / "trial-grade.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    live_json.write_text(json.dumps(_runtime_safety_state()), encoding="utf-8")
    policy_json.write_text(json.dumps({}), encoding="utf-8")
    admission_json.write_text(json.dumps({}), encoding="utf-8")
    portfolio_json.write_text(json.dumps({}), encoding="utf-8")
    trial_grade_json.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--runtime-safety-state-json",
            str(live_json),
            "--trial-asset-admission-proposal-json",
            str(admission_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--three-strategy-live-trial-portfolio-json",
            str(portfolio_json),
            "--trial-grade-signal-gate-audit-json",
            str(trial_grade_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]
    assert mpg["stage"] == "armed_observation"
    assert mpg["decision"] == "not_tradable_market_wait"
    assert mpg["first_blocker_class"] == "fresh_executable_signal_absent"
    assert "actionable_now" not in mpg
    assert "real_order_authority" not in mpg
    assert mpg["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_cli_explicit_brf2_shadow_evidence_path_keeps_provenance_only(
    tmp_path: Path,
) -> None:
    projection_json = tmp_path / "projection.json"
    brf2_shadow_candidate_evidence_json = tmp_path / "brf2-shadow-evidence.json"
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    brf2_shadow_candidate_evidence_json.write_text(
        json.dumps(_brf2_shadow_candidate_evidence()),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--brf2-shadow-candidate-evidence-json",
            str(brf2_shadow_candidate_evidence_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    brf2 = rows["BRF2-001"]
    provenance = brf2["brf2_shadow_candidate_evidence_provenance"]
    assert provenance["projection_role"] == "shadow_candidate_evidence_provenance"
    assert provenance["shadow_candidate_evidence_ready"] is True
    assert provenance["primary_judgment_source"] is False
    for removed_projection_field in (
        "live_submit_authority",
        "operation_layer_authority",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in provenance


def test_scoped_live_submit_only_marks_matching_strategy_group_tradable():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state_ready_for("MPG-001"),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["MPG-001"]["stage"] == "live_submit_ready"
    assert rows["MPG-001"]["decision"] == "tradable_now"
    assert "actionable_now" not in rows["MPG-001"]
    assert "real_order_authority" not in rows["MPG-001"]
    assert rows["MPG-001"]["runtime_safety_reference"][
        "live_submit_ready_for_strategy"
    ] is True

    assert rows["BRF2-001"]["decision"] == "not_tradable_facts"
    assert rows["BRF2-001"]["first_blocker_class"] == "required_facts_mapping_gap"
    assert rows["BTPC-001"]["decision"] != "tradable_now"
    assert rows["RBR-001"]["decision"] != "tradable_now"
    assert rows["RBR2-001"]["decision"] != "tradable_now"
    assert packet["summary"]["tradable_now_count"] == 1
    assert packet["summary"]["top_strategy_group_id"] == "MPG-001"
    assert packet["summary"]["top_decision"] == "tradable_now"
    assert packet["summary"]["selected_candidate_strategy_group_id"] == "BRF2-001"
    assert packet["summary"]["selected_candidate_decision"] == "not_tradable_facts"
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]
    assert (
        packet["checks"]["decision_rows_do_not_emit_legacy_authority_mirrors"]
        is True
    )
    assert packet["checks"]["tradable_now_scoped_to_live_submit"] is True


def test_tradeability_uses_runtime_safety_state_as_live_submit_authority():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state_ready_for_with_legacy_mirrors_false(
            "MPG-001"
        ),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["MPG-001"]["decision"] == "tradable_now"
    assert "actionable_now" not in rows["MPG-001"]
    assert "real_order_authority" not in rows["MPG-001"]
    assert rows["MPG-001"]["runtime_safety_reference"][
        "live_submit_ready_for_strategy"
    ] is True
    assert packet["checks"]["tradable_now_scoped_to_live_submit"] is True


def test_unscoped_live_submit_ready_does_not_make_any_row_tradable():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state_ready_for(None),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["MPG-001"]["decision"] != "tradable_now"


def test_legacy_live_submit_mirrors_do_not_reconstruct_runtime_safety_state():
    module = _load_module()
    legacy_live_submit = _runtime_safety_state_ready_for("MPG-001")
    legacy_live_submit.pop("runtime_safety_state")

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=legacy_live_submit,
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["MPG-001"]["decision"] != "tradable_now"
    assert "actionable_now" not in rows["MPG-001"]
    assert "real_order_authority" not in rows["MPG-001"]
    assert rows["MPG-001"]["runtime_safety_reference"][
        "live_submit_ready_for_strategy"
    ] is False
    assert packet["summary"]["tradable_now_count"] == 0
    assert rows["BRF2-001"]["decision"] == "not_tradable_facts"
    assert packet["summary"]["tradable_now_count"] == 0
    assert "actionable_now_count" not in packet["summary"]
    assert "real_order_authority_count" not in packet["summary"]
    for row in packet["decision_rows"]:
        assert "actionable_now" not in row
        assert "real_order_authority" not in row
        assert row["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False


def test_tradeability_decision_cli_writes_json_and_markdown(tmp_path: Path):
    module = _load_module()
    projection_json = tmp_path / "projection.json"
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    signal_json = tmp_path / "signal.json"
    live_json = tmp_path / "live.json"
    policy_json = tmp_path / "policy.json"
    brf2_capture_json = tmp_path / "brf2-capture.json"
    output_json = tmp_path / "decision.json"
    output_md = tmp_path / "decision.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    signal_json.write_text(json.dumps(_signal_coverage()), encoding="utf-8")
    live_json.write_text(json.dumps(_runtime_safety_state()), encoding="utf-8")
    policy_json.write_text(json.dumps({}), encoding="utf-8")
    brf2_capture_json.write_text(json.dumps({}), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--registry-json",
            str(registry_json),
            "--tier-policy-json",
            str(tier_json),
            "--signal-coverage-json",
            str(signal_json),
            "--runtime-safety-state-json",
            str(live_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--brf2-runtime-signal-capture-json",
            str(brf2_capture_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "tradeability_decision_ready"
    assert packet["schema"] == module.SCHEMA
    assert packet["scope"] == "strategygroup_tradeability_decision_read_model"
    assert packet["generated_at_utc"]
    assert "real_order_authority" not in packet["owner_summary"]
    assert "actionable_now" not in packet["owner_summary"]
    assert packet["summary"]["row_count"] == len(packet["decision_rows"])
    assert packet["checks"]["row_count_matches_decision_rows"] is True
    assert (
        packet["checks"]["decision_rows_do_not_emit_legacy_authority_mirrors"]
        is True
    )
    assert packet["checks"]["tradable_now_scoped_to_live_submit"] is True
    assert packet["safety_invariants"][
        "decision_generator_changes_runtime_safety_state"
    ] is False
    assert packet["safety_invariants"][
        "decision_generator_creates_execution_attempt"
    ] is False
    assert "legacy_verdict_generator_actionable_now" not in packet["safety_invariants"]
    assert "legacy_verdict_generator_real_order_authority" not in packet["safety_invariants"]
    markdown = output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Tradeability Decision" in markdown
    assert "Real order authority" not in markdown
    assert "does not set actionable_now or real_order_authority" not in markdown
    assert "Runtime Safety State remains the live-submit safety source" in markdown
