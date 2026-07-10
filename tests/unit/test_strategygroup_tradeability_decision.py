from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_tradeability_decision.py"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


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


def _load_file_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_seeded_runtime_control_db(path: Path) -> str:
    migration = _load_file_module(MIGRATION_PATH, "migration_086_tradeability")
    seed = _load_file_module(SEED_PATH, "seed_runtime_control_tradeability")
    database_url = f"sqlite:///{path}"
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(conn))
            try:
                migration.upgrade()
            finally:
                migration.op = old_op
            seed.seed_runtime_control_state_foundation(conn)
    finally:
        engine.dispose()
    return database_url


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
                "strategy_asset_decision": "merge_as_classifier",
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


def _capital_trial_envelope_projection_with_cpm_stale_blockers() -> dict:
    packet = _capital_trial_envelope_projection()
    packet["capital_trial_eligibility_rows"].append(
        {
            "strategy_group_id": "CPM-RO-001",
            "candidate_family": "pullback_momentum",
            "candidate_status": "identity_review_before_trial_prepare",
            "identity_status": "registry_identity_unresolved",
            "execution_tier": "unknown",
            "side_scope": ["long"],
            "recent_opportunity_count": 18,
            "would_enter_forward_positive_count": 13,
            "tradable_forward_count": 13,
            "ranking_score": 161,
            "trial_recommendation": "defer_until_identity_or_merge_review_closed",
            "trial_blockers": [
                "would_enter_forward_outcome_pending:24h",
                "registry_identity_unresolved",
                "owner_capital_scope_not_confirmed",
                "fresh_signal_absent",
                "action_time_finalgate_not_reached",
                "official_operation_layer_not_reached",
            ],
            "actionable_now": False,
            "real_order_authority": False,
        }
    )
    return packet


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
    disable_active = signal_state == "blocked_by_disable_fact"
    return {
        "status": "brf2_runtime_signal_capture_ready",
        "signal_detector_preview": {
            "current_signal_state": signal_state,
            "fresh_signal_present": fresh,
            "first_blocker_class": (
                "brf2_fresh_short_signal_present_non_executing"
                if fresh
                else (
                    "short_squeeze_risk_state_disable_active"
                    if disable_active
                    else "fresh_brf2_short_signal_absent"
                )
            ),
            "first_blocker_owner": "runtime" if fresh else "market",
            "signal_capture_checkpoint": (
                "materialize_pg_brf2_candidate_authorization"
                if fresh
                else (
                    "continue_brf2_armed_observation_until_disable_clears"
                    if disable_active
                    else "continue_brf2_armed_observation_until_fresh_signal"
                )
            ),
            "missing_required_fact_keys": (
                []
                if fresh
                else (
                    ["short_squeeze_risk_state"]
                    if disable_active
                    else ["closed_1h_ohlcv"]
                )
            ),
            "active_disable_fact_keys": (
                ["short_squeeze_risk_state"] if disable_active else []
            ),
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


def _registry_with_cpm_trial_asset() -> dict:
    registry = _registry()
    registry["rows"].append(
        {
            "strategy_group_id": "CPM-RO-001",
            "display_name": "CPM Long Pullback Reclaim",
            "default_tier": "L3",
            "trial_eligible": True,
            "supported_sides": ["long"],
            "required_facts_summary": {"market": "pullback reclaim facts"},
            "actionable_now": False,
            "real_order_authority": False,
        }
    )
    return registry


def _tier_policy_with_cpm_armed_observation() -> dict:
    policy = _tier_policy()
    policy["current_strategy_groups"]["CPM-RO-001"] = {
        "tier": "L3",
        "mode": "armed_observation",
    }
    return policy


def _cpm_identity_routing_decision() -> dict:
    return {
        "status": "cpm_identity_routing_decision_ready",
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "identity_decision": "standalone_trial_asset",
        "cpm_long_vs_mpg_long_distinct": True,
        "checks": {
            "registry_identity_closed": True,
            "standalone_trial_asset": True,
        },
    }


def _cpm_owner_trial_policy_scope() -> dict:
    return {
        "status": "cpm_owner_trial_policy_scope_recorded",
        "strategy_group_id": "CPM-RO-001",
        "owner_policy_recorded": True,
        "cpm_policy_scope_recorded": True,
        "owner_policy_scope_missing": False,
        "policy": {
            "strategy_group_id": "CPM-RO-001",
            "trial_identity": "CPM_LONG_PULLBACK_RECLAIM_TRIAL_V0",
            "capital_scope": {
                "type": "isolated_subaccount_full_allocation",
                "amount_source": "action_time_exchange_available_balance",
            },
            "side_scope": ["long"],
            "symbol_scope": "cpm_research_supported_symbols_only",
            "leverage_scenario": "5x_scenario_not_authority",
            "max_notional": {
                "calculation": (
                    "action_time_exchange_available_balance * leverage_scenario"
                )
            },
            "attempt_cap": 3,
            "loss_unit": {
                "calculation": "action_time_exchange_available_balance / attempt_cap"
            },
        },
    }


def _cpm_required_facts_mapping() -> dict:
    return {
        "status": "cpm_required_facts_mapping_ready",
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "required_facts_mapping_ready": True,
        "live_required_facts_authority": False,
        "action_time_refresh_required": True,
        "fresh_signal_rule": {
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
        },
    }


def _cpm_runtime_signal_capture() -> dict:
    return {
        "status": "cpm_runtime_signal_capture_ready",
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "checks": {
            "watcher_scope_ready": True,
        },
        "signal_detector_preview": {
            "current_signal_state": "fresh_signal_absent",
            "fresh_signal_present": False,
            "first_blocker_class": "fresh_cpm_long_signal_absent",
            "first_blocker_owner": "market",
            "signal_capture_checkpoint": (
                "continue_cpm_long_armed_observation_until_reclaim_signal"
            ),
        },
        "shadow_candidate_shape": {
            "shadow_candidate_ready": False,
        },
    }


def _cpm_shadow_candidate_evidence() -> dict:
    return {
        "status": "cpm_shadow_candidate_evidence_waiting_for_fresh_signal",
        "strategy_group_id": "CPM-RO-001",
        "shadow_candidate_evidence_ready": False,
        "shadow_candidate_evidence": {
            "signal_state": "fresh_signal_absent",
        },
        "first_blocker": {
            "class": "fresh_cpm_long_signal_absent",
            "owner": "market",
        },
    }


def _cpm_dry_run_submit_rehearsal() -> dict:
    return {
        "status": "cpm_dry_run_submit_rehearsal_shape_ready",
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "dry_run_submit_rehearsal": "shape_ready",
        "checks": {
            "armed_observation_ready": True,
            "submit_rehearsal_shape_ready": True,
            "fresh_signal_submit_rehearsal_passed": False,
            "candidate_authorization_evidence_ready": False,
            "finalgate_dry_run_passed": False,
            "operation_layer_paper_passed": False,
            "execution_attempt_rehearsal_ready": False,
            "exchange_write": False,
            "order_created": False,
        },
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _valid_replay_live_parity_audit(*rows: dict) -> dict:
    per_symbol_rows = [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "ETHUSDT",
            "blocker_class": "computed_not_satisfied",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": ["reclaim_confirmed"],
            "next_action": "continue_observation_with_failed_fact_matrix",
        },
        {
            "strategy_group_id": "MPG-001",
            "symbol": "BTCUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "next_action": "continue_watcher_observation_until_fresh_signal",
        },
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "next_action": "continue_watcher_observation_until_fresh_signal",
        },
    ] + list(rows)
    deduped: dict[tuple[str, str], dict] = {}
    for row in per_symbol_rows:
        deduped[(row["strategy_group_id"], row["symbol"])] = row
    return {
        "schema": "brc.replay_live_parity_audit.v1",
        "scope": "replay_live_parity_audit_non_authority",
        "status": "replay_live_parity_audit_ready",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "per_symbol_mismatch_table": list(deduped.values()),
        "summary": {
            "strategy_count": 3,
            "replay_signal_count": 131,
            "live_detector_reproduced_count": 14,
            "mismatch_count": 117,
        },
    }


def _valid_action_time_boundary_artifact(*rows: dict) -> dict:
    strategy_rows = [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "ETHUSDT",
            "path_id": "CPM-LONG",
            "first_blocker": "fresh_cpm_long_signal_absent",
            "action_time_path_ready": True,
            "next_action": "wait_for_fresh_signal_then_refresh_private_action_time_facts",
        },
        {
            "strategy_group_id": "MPG-001",
            "symbol": "BTCUSDT",
            "path_id": "MPG-LONG",
            "first_blocker": "fresh_mpg_long_signal_absent",
            "action_time_path_ready": True,
            "next_action": "wait_for_fresh_signal_then_refresh_private_action_time_facts",
        },
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "path_id": "SOR-LONG",
            "first_blocker": "fresh_sor_long_signal_absent",
            "action_time_path_ready": True,
            "next_action": "wait_for_fresh_signal_then_refresh_private_action_time_facts",
        },
    ] + list(rows)
    deduped: dict[str, dict] = {}
    for row in strategy_rows:
        deduped[row["strategy_group_id"]] = row
    return {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "scope": "fresh_signal_action_time_boundary_non_authority",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "strategy_rows": list(deduped.values()),
        "summary": {
            "strategy_count": 3,
            "fresh_signal_present_count": 0,
            "would_enter_finalgate_if_private_facts_ready_count": 0,
            "live_submit_allowed_count": 0,
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
    assert rows["BRF2-001"]["first_blocker_class"] == "scope_not_attached"
    assert rows["BRF2-001"]["blocker_owner"] == "engineering"
    assert rows["BRF2-001"]["next_action"] == "build_trial_asset_admission_proposal"
    assert rows["BRF2-001"]["after_next_state"] == "trial_asset_admission_candidate"

    assert rows["MPG-001"]["decision"] == "not_tradable_facts"
    assert rows["MPG-001"]["stage"] == "armed_observation"
    assert rows["MPG-001"]["first_blocker_class"] == "artifact_missing"
    assert rows["MPG-001"]["blocker_owner"] == "engineering"

    assert rows["BTPC-001"]["decision"] == "not_tradable_facts"
    assert rows["BTPC-001"]["first_blocker_class"] == "artifact_missing"

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
    assert brf2["first_blocker_class"] == "artifact_missing"
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
    assert brf2["first_blocker_class"] == "market_wait_validated"
    assert brf2["legacy_blocker_raw"] == "fresh_brf2_short_signal_absent"
    assert brf2["market_wait_validation"]["valid"] is True
    assert all(brf2["market_wait_validation"]["checks"].values())
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
    assert packet["checks"]["market_wait_validated_has_full_checklist"] is True


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

    assert rows["CPM-RO-001"]["first_blocker_class"] == "scope_not_attached"
    assert rows["CPM-RO-001"]["decision"] == "not_tradable_asset_admission"
    assert rows["CPM-RO-001"]["stage"] == "observe_only_would_enter"
    assert rows["CPM-RO-001"]["required_facts_status"] == "not_applicable"

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
    assert paths["CPM-LONG"]["first_blocker"] == "scope_not_attached"
    assert paths["CPM-LONG"]["blocker_owner"] == "engineering"
    assert paths["CPM-SHORT"]["first_blocker"] == "scope_not_attached"
    assert paths["CPM-SHORT"]["blocker_owner"] == "engineering"
    assert paths["BRF2-SHORT"]["required_facts_mapping_status"] == "ready"
    assert paths["BRF2-SHORT"]["first_blocker"] == "market_wait_validated"
    assert paths["MPG-LONG"]["first_blocker"] == "artifact_missing"
    assert paths["SOR-LONG"]["first_blocker"] == "scope_not_attached"
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
    assert exits["RBR2-001"]["exit_decision"] == "merge_as_classifier"
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


def test_brf2_path_inherits_specific_market_disable_blocker_from_row():
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
            "blocked_by_disable_fact"
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    paths = {
        path["path_id"]: path
        for path in packet["july_bullish_rebound_trade_path_closure"]["paths"]
    }

    assert rows["BRF2-001"]["decision"] == "not_tradable_market_wait"
    assert rows["BRF2-001"]["first_blocker_class"] == "computed_not_satisfied"
    assert paths["BRF2-SHORT"]["first_blocker"] == "computed_not_satisfied"
    assert paths["BRF2-SHORT"]["blocker_owner"] == "market"
    assert paths["BRF2-SHORT"]["next_action"] == (
        "continue_brf2_armed_observation_until_disable_clears"
    )


def test_cpm_path_schema_does_not_promote_identity_review_to_market_wait():
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
    paths = {
        path["path_id"]: path
        for path in packet["july_bullish_rebound_trade_path_closure"]["paths"]
    }
    cpm = rows["CPM-RO-001"]

    assert cpm["stage"] != "armed_observation"
    assert cpm["decision"] != "not_tradable_market_wait"
    assert cpm["first_blocker_class"] != "fresh_cpm_long_signal_absent"
    assert cpm["required_facts_status"] != "ready"
    assert cpm["first_blocker_class"] == "scope_not_attached"
    assert paths["CPM-LONG"]["first_blocker"] == "scope_not_attached"
    assert paths["CPM-SHORT"]["first_blocker"] == "scope_not_attached"
    assert paths["CPM-LONG"]["required_facts_mapping_status"] == "not_applicable"
    assert paths["CPM-SHORT"]["required_facts_mapping_status"] == "not_applicable"


def test_cpm_fact_chain_promotes_to_armed_market_wait_only_after_closure():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=(
            _capital_trial_envelope_projection_with_cpm_stale_blockers()
        ),
        registry=_registry_with_cpm_trial_asset(),
        tier_policy=_tier_policy_with_cpm_armed_observation(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        cpm_identity_routing_decision=_cpm_identity_routing_decision(),
        cpm_owner_trial_policy_scope=_cpm_owner_trial_policy_scope(),
        cpm_required_facts_mapping=_cpm_required_facts_mapping(),
        cpm_runtime_signal_capture=_cpm_runtime_signal_capture(),
        cpm_shadow_candidate_evidence=_cpm_shadow_candidate_evidence(),
        cpm_dry_run_submit_rehearsal=_cpm_dry_run_submit_rehearsal(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    paths = {
        path["path_id"]: path
        for path in packet["july_bullish_rebound_trade_path_closure"]["paths"]
    }
    cpm = rows["CPM-RO-001"]
    cpm_long = paths["CPM-LONG"]

    assert cpm["stage"] == "armed_observation"
    assert cpm["decision"] == "not_tradable_market_wait"
    assert cpm["first_blocker_class"] == "market_wait_validated"
    assert cpm["legacy_blocker_raw"] == "fresh_cpm_long_signal_absent"
    assert cpm["market_wait_validation"]["valid"] is True
    assert all(cpm["market_wait_validation"]["checks"].values())
    assert cpm["blocker_owner"] == "market"
    assert cpm["next_action"] == (
        "continue_cpm_long_armed_observation_until_reclaim_signal"
    )
    assert cpm["required_facts_status"] == "ready"
    assert cpm["runtime_scope_status"]["owner_policy_recorded"] is True
    assert cpm["runtime_scope_status"]["cpm_identity_decision"] == (
        "standalone_trial_asset"
    )
    assert cpm["runtime_scope_status"]["cpm_current_signal_state"] == (
        "fresh_signal_absent"
    )
    cpm_secondary = {row["blocker"] for row in cpm["secondary_blockers"]}
    cpm_resolved = {row["blocker"] for row in cpm["resolved_blockers"]}
    assert cpm["secondary_blockers"] == []
    assert "registry_identity_unresolved" not in cpm_secondary
    assert "owner_capital_scope_not_confirmed" not in cpm_secondary
    assert "registry_identity_unresolved" in cpm_resolved
    assert "owner_capital_scope_not_confirmed" in cpm_resolved
    assert all(
        row["resolved_by"] == "cpm_registry_identity_and_owner_trial_policy"
        for row in cpm["resolved_blockers"]
    )
    assert cpm["evidence_snapshot"]["candidate_status"] == "armed_observation"
    assert cpm["evidence_snapshot"]["trial_recommendation"] == (
        "continue_cpm_long_armed_observation_until_fresh_signal"
    )
    assert "defer_until_identity_or_merge_review_closed" not in (
        cpm["evidence_snapshot"]["trial_recommendation"]
    )
    assert cpm_long["side"] == "long"
    assert cpm_long["required_facts_mapping_status"] == "ready"
    assert cpm_long["capital_scope_source"] == (
        "action_time_exchange_available_balance"
    )
    assert cpm_long["can_trade_now"] is False
    assert cpm_long["first_blocker"] == "market_wait_validated"
    assert cpm_long["blocker_owner"] == "market"
    assert "actionable_now" not in cpm
    assert "real_order_authority" not in cpm
    assert "actionable_now" not in cpm_long
    assert "real_order_authority" not in cpm_long
    assert packet["summary"]["tradable_now_count"] == 0


def test_tradeability_consumes_cpm_replay_live_parity_failed_fact_matrix():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=(
            _capital_trial_envelope_projection_with_cpm_stale_blockers()
        ),
        registry=_registry_with_cpm_trial_asset(),
        tier_policy=_tier_policy_with_cpm_armed_observation(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        trial_asset_admission_proposal=_trial_asset_admission_proposal_with_policy(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        cpm_identity_routing_decision=_cpm_identity_routing_decision(),
        cpm_owner_trial_policy_scope=_cpm_owner_trial_policy_scope(),
        cpm_required_facts_mapping=_cpm_required_facts_mapping(),
        cpm_runtime_signal_capture=_cpm_runtime_signal_capture(),
        cpm_shadow_candidate_evidence=_cpm_shadow_candidate_evidence(),
        cpm_dry_run_submit_rehearsal=_cpm_dry_run_submit_rehearsal(),
        three_strategy_live_trial_portfolio=(
            _three_strategy_portfolio_with_brf2_armed_observation()
        ),
        brf2_runtime_signal_capture=_brf2_runtime_signal_capture(),
        replay_live_parity_audit=_valid_replay_live_parity_audit(
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "ETHUSDT",
                "detector_attached": True,
                "watcher_tick_present": True,
                "computed": True,
                "failed_facts": ["htf_trend_intact", "reclaim_confirmed"],
                "blocker_class": "computed_not_satisfied",
                "next_action": "continue_observation_with_failed_fact_matrix",
            }
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    paths = {
        path["path_id"]: path
        for path in packet["july_bullish_rebound_trade_path_closure"]["paths"]
    }
    cpm = rows["CPM-RO-001"]

    assert cpm["stage"] == "armed_observation"
    assert cpm["decision"] == "not_tradable_market_wait"
    assert cpm["first_blocker_class"] == "computed_not_satisfied"
    assert cpm["blocker_owner"] == "market"
    assert "htf_trend_intact,reclaim_confirmed" in cpm["first_blocker_detail"]
    assert paths["CPM-LONG"]["first_blocker"] == "computed_not_satisfied"


def test_tradeability_consumes_mpg_replay_live_action_time_blocker():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        replay_live_parity_audit=_valid_replay_live_parity_audit(
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "blocker_class": "action_time_boundary_not_reproduced",
                "next_action": "repair_non_executing_action_time_rehearsal_path",
            }
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["stage"] == "armed_observation"
    assert mpg["decision"] == "not_tradable_execution_gate"
    assert mpg["first_blocker_class"] == "action_time_boundary_not_reproduced"
    assert mpg["legacy_blocker_raw"] == "action_time_boundary_not_reproduced"
    assert mpg["blocker_owner"] == "runtime"
    assert mpg["next_action"] == "repair_non_executing_action_time_rehearsal_path"


def test_tradeability_rejects_fixture_replay_live_parity_artifact():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        replay_live_parity_audit={
            "status": "fixture",
            "schema": "brc.replay_live_parity_audit.v1",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "summary": {
                "strategy_count": 3,
                "replay_signal_count": 131,
                "mismatch_count": 1,
            },
            "per_symbol_mismatch_table": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "SOLUSDT",
                    "blocker_class": "action_time_boundary_not_reproduced",
                },
                {
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETHUSDT",
                    "blocker_class": "computed_not_satisfied",
                },
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "blocker_class": "market_wait_validated",
                },
            ],
        },
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["decision"] == "not_tradable_facts"
    assert mpg["first_blocker_class"] == "schema_invalid"
    assert mpg["legacy_blocker_raw"] == "schema_invalid"
    assert "fixture or partial" in mpg["first_blocker_detail"]


def test_tradeability_consumes_action_time_boundary_artifact_without_parity():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        strategy_fresh_signal_action_time_boundary=(
            _valid_action_time_boundary_artifact(
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "SOLUSDT",
                    "first_blocker": "action_time_boundary_not_reproduced",
                    "next_action": "repair_non_executing_action_time_rehearsal_path",
                }
            )
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert rows["MPG-001"]["decision"] == "not_tradable_execution_gate"
    assert rows["MPG-001"]["first_blocker_class"] == (
        "action_time_boundary_not_reproduced"
    )


def test_tradeability_external_blocker_uses_canonical_lane_selection_rule():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        replay_live_parity_audit=_valid_replay_live_parity_audit(
            {
                "strategy_group_id": "MPG-001",
                "symbol": "SOLUSDT",
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "failed_facts": [],
                "mismatch_count": 25,
                "live_submit_scope_priority": 0,
                "lane_scope": "out_of_scope",
                "next_action": "refresh_or_repair_watcher_public_fact_input",
            },
            {
                "strategy_group_id": "MPG-001",
                "symbol": "OPUSDT",
                "blocker_class": "watcher_tick_missing",
                "detector_attached": True,
                "watcher_tick_present": False,
                "computed": False,
                "failed_facts": [],
                "mismatch_count": 3,
                "live_submit_scope_priority": 20,
                "lane_scope": "scoped_live_observation_proposal",
                "next_action": "refresh_or_repair_watcher_public_fact_input",
            },
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["first_blocker_class"] == "watcher_tick_missing"
    assert mpg["canonical_lane"]["symbol"] == "OPUSDT"
    assert mpg["canonical_lane"]["mismatch_count"] == 3
    assert mpg["canonical_lane"]["live_submit_scope_priority"] == 20
    assert mpg["canonical_lane"]["selection_rule"] == (
        "first_blocker_priority->live_submit_scope_priority->"
        "mismatch_count->symbol"
    )


def test_tradeability_rejects_cross_symbol_mpg_market_wait_evidence():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        replay_live_parity_audit=_valid_replay_live_parity_audit(),
        strategy_fresh_signal_action_time_boundary=(
            _valid_action_time_boundary_artifact(
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "SOLUSDT",
                    "path_id": "MPG-LONG",
                    "first_blocker": "fresh_mpg_long_signal_absent",
                    "action_time_path_ready": True,
                    "next_action": (
                        "wait_for_fresh_signal_then_refresh_private_action_time_facts"
                    ),
                }
            )
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["decision"] == "not_tradable_facts"
    assert mpg["first_blocker_class"] == "artifact_missing"
    assert mpg["first_blocker_detail"] == "market_wait_validated checklist is incomplete"
    assert mpg["next_action"] == "complete_market_wait_validation_checklist"


def test_tradeability_maps_mpg_public_facts_gap_to_scope_blocker():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        strategy_fresh_signal_action_time_boundary=(
            _valid_action_time_boundary_artifact(
                {
                    "strategy_group_id": "MPG-001",
                    "path_id": "MPG-STRONG-SYMBOL-ROTATION",
                    "first_blocker": "mpg_high_beta_public_facts_gap",
                    "required_facts_readiness": {
                        "public_facts_ready": False,
                        "private_action_time_facts_ready": False,
                    },
                    "next_action": (
                        "wait_for_fresh_signal_then_refresh_private_action_time_facts"
                    ),
                }
            )
        ),
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["decision"] == "not_tradable_asset_admission"
    assert mpg["first_blocker_class"] == "scope_not_attached"
    assert mpg["first_blocker_detail"] == "mpg_high_beta_public_facts_gap"
    assert mpg["next_action"] == (
        "produce_scoped_live_observation_or_scope_proposal"
    )
    assert mpg["next_action"] != (
        "wait_for_fresh_signal_then_refresh_private_action_time_facts"
    )


def test_tradeability_rejects_partial_action_time_boundary_artifact():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        strategy_fresh_signal_action_time_boundary={
            "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
            "scope": "fresh_signal_action_time_boundary_non_authority",
            "status": "strategy_fresh_signal_action_time_boundary_ready",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "summary": {
                "strategy_count": 1,
                "fresh_signal_present_count": 0,
                "would_enter_finalgate_if_private_facts_ready_count": 0,
                "live_submit_allowed_count": 0,
            },
            "strategy_rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "first_blocker": "action_time_boundary_not_reproduced",
                }
            ],
        },
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mpg = rows["MPG-001"]

    assert mpg["decision"] == "not_tradable_facts"
    assert mpg["first_blocker_class"] == "artifact_missing"
    assert "required WIP lanes" in mpg["first_blocker_detail"]


def test_tradeability_absorbs_mi_trial_admission_candidate_fact():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        mi_trial_admission_decision={
            "schema": "brc.mi_trial_admission_decision.v1",
            "scope": "mi_trial_admission_decision_non_authority",
            "status": "mi_trial_admission_decision_ready",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "strategy_group_id": "MI-001",
            "trial_admission_decision": "trial_asset_admission_candidate",
            "promotion_scope": "trial_admission",
            "tradeability": {
                "can_trade_now": False,
                "first_blocker": "trial_admission_fact_not_integrated",
                "blocker_owner": "engineering",
            },
        },
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mi = rows["MI-001"]

    assert mi["stage"] == "trial_asset_admission_candidate"
    assert mi["decision"] == "not_tradable_asset_admission"
    assert mi["first_blocker_class"] == "scope_not_attached"
    assert mi["runtime_scope_status"]["mi_trial_admission_decision"] == (
        "trial_asset_admission_candidate"
    )
    assert mi["runtime_scope_status"]["mi_promotion_scope"] == "trial_admission"


def test_tradeability_reclassifies_scoped_mi_trial_admission_to_policy_gap():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        mi_trial_admission_decision={
            "schema": "brc.mi_trial_admission_decision.v1",
            "scope": "mi_trial_admission_decision_non_authority",
            "status": "mi_trial_admission_decision_ready",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "strategy_group_id": "MI-001",
            "trial_admission_decision": "trial_asset_admission_candidate",
            "promotion_scope": "trial_admission",
            "symbol_scope": {
                "readonly_watcher_candidates": ["AVAXUSDT"],
                "primary_live_submit_symbol_scope": [],
                "live_submit_scope_changed": False,
            },
            "watcher_scope": {
                "source": "binance_usdm_public_facts_readonly",
                "symbol_scope": ["AVAXUSDT"],
                "read_only": True,
            },
            "tradeability": {
                "can_trade_now": False,
                "first_blocker": "mi_owner_policy_and_required_facts_mapping_needed",
                "blocker_owner": "owner_policy",
            },
        },
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mi = rows["MI-001"]

    assert mi["stage"] == "trial_asset_admission_candidate"
    assert mi["decision"] == "not_tradable_policy"
    assert mi["first_blocker_class"] == "policy_scope_missing"
    assert mi["blocker_owner"] == "owner"
    assert mi["next_action"] == "record_scoped_owner_policy"


def test_tradeability_rejects_invalid_mi_trial_admission_artifact():
    module = _load_module()

    packet = module.build_tradeability_decision(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        signal_coverage=_signal_coverage(),
        runtime_safety_state=_runtime_safety_state(),
        mi_trial_admission_decision={
            "status": "mi_trial_admission_decision_ready",
            "trial_admission_decision": "trial_asset_admission_candidate",
            "promotion_scope": "trial_admission",
            "tradeability": {
                "can_trade_now": False,
                "first_blocker": "trial_admission_fact_not_integrated",
                "blocker_owner": "engineering",
            },
        },
        generated_at_utc="2026-06-29T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    mi = rows["MI-001"]

    assert mi["decision"] == "not_tradable_facts"
    assert mi["first_blocker_class"] == "schema_invalid"
    assert mi["legacy_blocker_raw"] == "schema_invalid"
    assert "schema is not" in mi["first_blocker_detail"]


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
    assert brf2["decision"] == "not_tradable_facts"
    assert brf2["decision"] != "not_tradable_market_wait"
    assert (
        brf2["first_blocker_class"]
        == "schema_invalid"
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
    assert brf2["first_blocker_class"] == "watcher_tick_missing"
    assert brf2["blocker_owner"] == "runtime"
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
    assert brf2["first_blocker_class"] == "action_time_boundary_not_reproduced"
    assert brf2["blocker_owner"] == "runtime"
    assert brf2["next_action"] == (
        "materialize_pg_brf2_candidate_authorization_for_action_time_chain"
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
    assert brf2["first_blocker_class"] == "action_time_boundary_not_reproduced"
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
    assert brf2["first_blocker_class"] == "action_time_boundary_not_reproduced"
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


def test_cli_requires_pg_database_url(tmp_path: Path) -> None:
    env = {**os.environ, "PG_DATABASE_URL": ""}
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_tradeability_decision.py"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 2
    assert "PG_DATABASE_URL is required" in result.stderr


def test_cli_normalizes_asyncpg_database_url_before_engine_creation(
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    captured: dict[str, str] = {}

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class _Engine:
        def connect(self):
            return _Connection()

        def dispose(self):
            return None

    class _Repository:
        def __init__(self, conn):
            assert isinstance(conn, _Connection)

        def read_control_state(self):
            return {"source": "unit_pg_current"}

    def fake_create_engine(database_url: str):
        captured["database_url"] = database_url
        return _Engine()

    monkeypatch.setattr(module.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(module, "PgBackedRuntimeControlStateRepository", _Repository)
    monkeypatch.setattr(
        module,
        "build_tradeability_decision_from_control_state",
        lambda _state: {
            "status": "tradeability_decision_ready",
            "summary": {
                "row_count": 5,
                "top_decision": "not_tradable_market_wait",
                "top_strategy_group_id": "MPG-001",
                "tradable_now_count": 0,
            },
        },
    )

    returncode = module.main(
        [
            "--database-url",
            "postgresql+asyncpg://unit:secret@pg.example/brc",
        ]
    )

    assert returncode == 0
    assert captured["database_url"] == (
        "postgresql+psycopg://unit:secret@pg.example/brc"
    )
    assert json.loads(capsys.readouterr().out)["row_count"] == 5


def test_cli_pg_backed_tradeability_decision_reads_seeded_runtime_control_state(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn)
            packet = module.build_tradeability_decision_from_control_state(
                repository.read_control_state()
            )
    finally:
        engine.dispose()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["status"] == "tradeability_decision_ready"
    assert summary["row_count"] == 5
    rows = {row["strategy_group_id"]: row for row in packet["decision_rows"]}
    assert packet["source_mode"] == "db_backed"
    assert packet["projection_target"] == "production_current"
    assert packet["source_validation"]["legacy_file_authority"] is False
    assert set(rows) == {
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    }
    assert rows["CPM-RO-001"]["policy_scope"]["side_scope"] == ["long"]
    assert rows["MPG-001"]["policy_scope"]["side_scope"] == ["long"]
    assert rows["MI-001"]["policy_scope"]["side_scope"] == ["long"]
    assert rows["SOR-001"]["policy_scope"]["side_scope"] == ["long", "short"]
    assert rows["BRF2-001"]["policy_scope"]["side_scope"] == ["short"]
    assert packet["summary"]["tradable_now_count"] == 0
    for row in rows.values():
        assert row["state_source"] == "pg_current_candidate_pool"
        assert row["first_blocker_class"] not in {"artifact_missing", "schema_invalid"}
        assert row["runtime_safety_reference"]["live_submit_ready_for_strategy"] is False
        assert "actionable_now" not in row
        assert "real_order_authority" not in row
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False


def test_tradeability_ignores_expired_invalidated_and_non_live_pg_signals(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    now_ms = 1770001000000
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            _insert_tradeability_signal(
                conn,
                suffix="expired",
                expires_at_ms=now_ms - 1,
                event_time_ms=1770000900000,
            )
            _insert_tradeability_signal(
                conn,
                suffix="invalidated",
                expires_at_ms=now_ms + 600_000,
                invalidated_at_ms=now_ms - 1,
                event_time_ms=1770000899000,
            )
        with engine.connect() as conn:
            repository = PgBackedRuntimeControlStateRepository(conn, now_ms=now_ms)
            control_state = repository.read_control_state()
            non_live_signal = dict(control_state["live_signal_events"][0])
            non_live_signal.update(
                {
                    "signal_event_id": "signal:SOR-001:ETHUSDT:long:replay",
                    "source_kind": "replay",
                    "expires_at_ms": now_ms + 600_000,
                    "invalidated_at_ms": None,
                }
            )
            control_state["live_signal_events"].append(non_live_signal)
            signal_by_lane = module._fresh_signal_by_lane(control_state)
            packet = module.build_tradeability_decision_from_control_state(
                control_state
            )
    finally:
        engine.dispose()

    sor = next(row for row in packet["decision_rows"] if row["strategy_group_id"] == "SOR-001")
    assert ("SOR-001", "ETHUSDT", "long") not in signal_by_lane
    assert sor["decision"] != "tradable_now"


def test_pg_tradeability_classifies_all_five_as_validated_market_wait_when_ready(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    now_ms = 1770001000000
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_control_state()
        _attach_satisfied_pg_observation(control_state, now_ms=now_ms)

        packet = module.build_tradeability_decision_from_control_state(control_state)
    finally:
        engine.dispose()

    assert packet["status"] == "tradeability_decision_ready"
    assert packet["summary"]["tradable_now_count"] == 0
    assert packet["summary"]["market_first_blocker_count"] == 5
    assert {
        row["first_blocker_class"] for row in packet["decision_rows"]
    } == {"market_wait_validated"}
    assert all(
        row["market_wait_validation"]["valid"] is True
        for row in packet["decision_rows"]
    )


def _attach_satisfied_pg_observation(control_state: dict, *, now_ms: int) -> None:
    for event in control_state["strategy_side_event_specs"]:
        event.update(
            {
                "declared_signal_grade": "trial_grade_signal",
                "declared_required_execution_mode": "trial_live",
                "execution_eligibility_enabled": True,
            }
        )
    runtime_by_candidate = {
        row["candidate_scope_id"]: row
        for row in control_state["runtime_scope_bindings"]
        if row.get("status") == "active"
    }
    for index, candidate in enumerate(control_state["candidate_scope"], start=1):
        if candidate.get("status") != "active":
            continue
        runtime = runtime_by_candidate[candidate["candidate_scope_id"]]
        observed_at_ms = now_ms - 1000 + index
        lane_suffix = (
            f"{candidate['strategy_group_id']}:{candidate['symbol']}:{candidate['side']}"
        )
        control_state["watcher_runtime_coverage"].append(
            {
                "runtime_coverage_id": f"coverage:{lane_suffix}:ready",
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
                "detector_key": f"detector:{candidate['strategy_group_id']}:{candidate['side']}",
                "runtime_profile_id": runtime["runtime_profile_id"],
                "coverage_state": "covered",
                "liveness_state": "healthy",
                "last_tick_at_ms": observed_at_ms,
                "valid_until_ms": now_ms + 60_000,
                "is_current": True,
                "created_at_ms": observed_at_ms,
            }
        )
        control_state["runtime_fact_snapshots"].append(
            {
                "fact_snapshot_id": f"fact:{lane_suffix}:ready",
                "strategy_group_id": candidate["strategy_group_id"],
                "symbol": candidate["symbol"],
                "side": candidate["side"],
                "runtime_profile_id": runtime["runtime_profile_id"],
                "fact_surface": "pretrade_public",
                "source_kind": "live_market",
                "source_ref": f"unit:{lane_suffix}",
                "computed": True,
                "satisfied": True,
                "freshness_state": "fresh",
                "failed_facts": [],
                "fact_values": {"all_strategy_facts_satisfied": True},
                "blocker_class": None,
                "observed_at_ms": observed_at_ms,
                "valid_until_ms": now_ms + 60_000,
                "created_at_ms": observed_at_ms,
            }
        )


def test_pg_tradeability_ignores_expired_runtime_safety_snapshot(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    now_ms = 1770001000000
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_control_state()
        control_state["runtime_safety_state"].append(
            _pg_runtime_safety_row(
                now_ms=now_ms,
                valid_until_ms=now_ms - 1,
                lane_id="lane:SOR-001:ETHUSDT:long:expired",
            )
        )

        packet = module.build_tradeability_decision_from_control_state(control_state)
    finally:
        engine.dispose()

    sor = next(
        row
        for row in packet["decision_rows"]
        if row["strategy_group_id"] == "SOR-001"
    )
    assert packet["summary"]["tradable_now_count"] == 0
    assert sor["decision"] != "tradable_now"
    assert sor["runtime_safety_reference"]["snapshot_id"] == ""


def test_pg_tradeability_rejects_unexpired_orphan_runtime_safety_snapshot(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    now_ms = 1770001000000
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_control_state()
        control_state["runtime_safety_state"].append(
            _pg_runtime_safety_row(
                now_ms=now_ms,
                valid_until_ms=now_ms + 60_000,
                lane_id="lane:SOR-001:ETHUSDT:long:orphan",
            )
        )

        packet = module.build_tradeability_decision_from_control_state(control_state)
    finally:
        engine.dispose()

    sor = next(
        row
        for row in packet["decision_rows"]
        if row["strategy_group_id"] == "SOR-001"
    )
    assert packet["summary"]["tradable_now_count"] == 0
    assert sor["decision"] != "tradable_now"
    assert sor["runtime_safety_reference"]["lineage_verified"] is False


def test_pg_tradeability_accepts_only_verified_current_runtime_safety_lineage(
    tmp_path: Path,
) -> None:
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")
    now_ms = 1770001000000
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_control_state()
        _attach_verified_sor_chain(control_state, now_ms=now_ms)

        packet = module.build_tradeability_decision_from_control_state(control_state)
    finally:
        engine.dispose()

    sor = next(
        row
        for row in packet["decision_rows"]
        if row["strategy_group_id"] == "SOR-001"
    )
    assert packet["status"] == "tradeability_decision_ready"
    assert packet["summary"]["tradable_now_count"] == 1
    assert sor["decision"] == "tradable_now"
    assert sor["runtime_safety_reference"]["lineage_verified"] is True
    assert sor["runtime_safety_reference"]["live_submit_ready_for_strategy"] is True


def _attach_verified_sor_chain(control_state: dict, *, now_ms: int) -> None:
    lane_id = "lane:SOR-001:ETHUSDT:long:verified"
    signal_id = "signal:SOR-001:ETHUSDT:long:verified"
    promotion_id = "promotion:SOR-001:ETHUSDT:long:verified"
    ticket_id = "ticket:SOR-001:ETHUSDT:long:verified"
    handoff_id = "handoff:SOR-001:ETHUSDT:long:verified"
    command_id = "submit-command:SOR-001:ETHUSDT:long:verified"
    snapshot = _pg_runtime_safety_row(
        now_ms=now_ms,
        valid_until_ms=now_ms + 60_000,
        lane_id=lane_id,
    )
    snapshot["trusted_fact_refs"] = {
        "ticket_id": ticket_id,
        "ticket_hash": "ticket-hash:verified",
        "finalgate_pass_id": "finalgate-pass:verified",
        "signal_event_id": signal_id,
        "operation_layer_handoff_id": handoff_id,
        "operation_submit_command_id": command_id,
        "budget_reservation_id": "budget:verified",
        "protection_ref_id": "protection:verified",
        "public_fact_snapshot_id": "fact:public:verified",
        "action_time_fact_snapshot_id": "fact:action-time:verified",
        "account_safe_fact_snapshot_id": "fact:account-safe:verified",
        "account_mode_snapshot_id": "fact:account-mode:verified",
    }
    control_state["runtime_safety_state"].append(snapshot)
    scope = {
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "runtime_profile_id": "owner-runtime-console-v1",
    }
    control_state["live_signal_events"].append(
        {
            **scope,
            "signal_event_id": signal_id,
            "status": "facts_validated",
            "freshness_state": "fresh",
            "source_kind": "live_market",
            "invalidated_at_ms": None,
            "expires_at_ms": now_ms + 60_000,
            "execution_eligible": True,
        }
    )
    control_state["promotion_candidates"].append(
        {
            **scope,
            "promotion_candidate_id": promotion_id,
            "signal_event_id": signal_id,
            "status": "arbitration_won",
            "closed_at_ms": None,
            "expires_at_ms": now_ms + 60_000,
            "execution_eligible": True,
        }
    )
    control_state["action_time_lane_inputs"].append(
        {
            **scope,
            "action_time_lane_input_id": lane_id,
            "promotion_candidate_id": promotion_id,
            "signal_event_id": signal_id,
            "runtime_safety_snapshot_id": snapshot["runtime_safety_snapshot_id"],
            "lane_scope": "real_submit_candidate",
            "status": "ticket_created",
            "closed_at_ms": None,
            "expires_at_ms": now_ms + 60_000,
            "first_blocker_class": "action_time_preflight_ready",
            "execution_eligible": True,
        }
    )
    control_state["action_time_tickets"].append(
        {
            **scope,
            "ticket_id": ticket_id,
            "action_time_lane_input_id": lane_id,
            "signal_event_id": signal_id,
            "status": "finalgate_ready",
            "expires_at_ms": now_ms + 60_000,
            "execution_eligible": True,
            "ticket_hash": "ticket-hash:verified",
            "budget_reservation_id": "budget:verified",
            "protection_ref_id": "protection:verified",
            "public_fact_snapshot_id": "fact:public:verified",
            "action_time_fact_snapshot_id": "fact:action-time:verified",
            "account_safe_fact_snapshot_id": "fact:account-safe:verified",
            "account_mode_snapshot_id": "fact:account-mode:verified",
        }
    )
    control_state["action_time_ticket_events"].append(
        {
            "ticket_event_id": "ticket-event:SOR-001:ETHUSDT:long:verified",
            "ticket_id": ticket_id,
            "action_time_lane_input_id": lane_id,
            "to_status": "finalgate_ready",
            "event_payload": {"finalgate_pass_id": "finalgate-pass:verified"},
        }
    )
    control_state["operation_layer_handoffs"].append(
        {
            **scope,
            "operation_layer_handoff_id": handoff_id,
            "ticket_id": ticket_id,
            "action_time_lane_input_id": lane_id,
            "operation_submit_command_id": command_id,
            "finalgate_pass_id": "finalgate-pass:verified",
            "command_plan": {"finalgate_pass_id": "finalgate-pass:verified"},
            "status": "handoff_ready",
        }
    )


def _pg_runtime_safety_row(
    *,
    now_ms: int,
    valid_until_ms: int,
    lane_id: str,
) -> dict:
    return {
        "runtime_safety_snapshot_id": f"runtime_safety:{lane_id}",
        "action_time_lane_input_id": lane_id,
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "runtime_profile_id": "owner-runtime-console-v1",
        "safety_state": "live_submit_ready",
        "submit_allowed": True,
        "finalgate_ready": True,
        "operation_layer_ready": True,
        "protection_ready": True,
        "active_position_conflict": False,
        "facts_fresh": True,
        "trusted_fact_refs_complete": True,
        "blockers": [],
        "trusted_fact_refs": {
            "ticket_id": "ticket:SOR-001:ETHUSDT:long:orphan",
            "operation_layer_handoff_id": "handoff:SOR-001:ETHUSDT:long:orphan",
            "signal_event_id": "signal:SOR-001:ETHUSDT:long:orphan",
        },
        "observed_at_ms": now_ms - 100,
        "valid_until_ms": valid_until_ms,
        "created_at_ms": now_ms - 100,
        "authority_boundary": "unit no exchange write",
        "signal_grade": "trial_grade_signal",
        "required_execution_mode": "trial_live",
        "execution_eligible": True,
        "authority_source_ref": "event_spec:SOR-LONG:v2",
    }


def _insert_tradeability_signal(
    conn,
    *,
    suffix: str,
    expires_at_ms: int,
    event_time_ms: int,
    source_kind: str = "live_market",
    invalidated_at_ms: int | None = None,
) -> None:
    row = conn.execute(
        text(
            """
            SELECT c.candidate_scope_id, c.strategy_group_id, c.symbol, c.side,
                   b.event_spec_id, e.event_id
            FROM brc_strategy_group_candidate_scope c
            JOIN brc_candidate_scope_event_bindings b
              ON b.candidate_scope_id = c.candidate_scope_id
             AND b.status = 'active'
            JOIN brc_strategy_side_event_specs e
              ON e.event_spec_id = b.event_spec_id
             AND e.status = 'current'
            WHERE c.strategy_group_id = 'SOR-001'
              AND c.symbol = 'ETHUSDT'
              AND c.side = 'long'
            LIMIT 1
            """
        )
    ).mappings().one()
    conn.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, event_spec_id, strategy_group_id,
              symbol, side, detector_key, signal_type, source_kind, status,
              freshness_state, confidence, fact_snapshot_id, reason_codes,
              signal_payload, event_time_ms, trigger_candle_close_time_ms,
              observed_at_ms, expires_at_ms, invalidated_at_ms, created_at_ms
            ) VALUES (
              :signal_event_id, :candidate_scope_id, :event_spec_id,
              :strategy_group_id, :symbol, :side, 'detector:SOR-001:long',
              :event_id, :source_kind, 'facts_validated', 'fresh', 0.9,
              :fact_snapshot_id, '[]', '{}', :event_time_ms, :event_time_ms,
              1770000900001, :expires_at_ms, :invalidated_at_ms, 1770000900002
            )
            """
        ),
        {
            "signal_event_id": f"signal:SOR-001:ETHUSDT:long:{suffix}",
            "candidate_scope_id": row["candidate_scope_id"],
            "event_spec_id": row["event_spec_id"],
            "strategy_group_id": row["strategy_group_id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "event_id": row["event_id"],
            "source_kind": source_kind,
            "fact_snapshot_id": f"fact:SOR-001:ETHUSDT:long:{suffix}",
            "event_time_ms": event_time_ms,
            "expires_at_ms": expires_at_ms,
            "invalidated_at_ms": invalidated_at_ms,
        },
    )


def test_cli_rejects_legacy_file_input_flags(tmp_path: Path) -> None:
    output_json = tmp_path / "tradeability.json"
    output_md = tmp_path / "tradeability.md"
    legacy_flags = [
        "--allow-local-file-diagnostic",
        "--capital-trial-envelope-projection-json",
        "--registry-json",
        "--tier-policy-json",
        "--signal-coverage-json",
        "--runtime-safety-state-json",
        "--trial-asset-admission-proposal-json",
        "--brf2-owner-trial-policy-scope-json",
        "--cpm-identity-routing-decision-json",
        "--cpm-owner-trial-policy-scope-json",
        "--cpm-required-facts-mapping-json",
        "--cpm-runtime-signal-capture-json",
        "--cpm-shadow-candidate-evidence-json",
        "--cpm-dry-run-submit-rehearsal-json",
        "--three-strategy-live-trial-portfolio-json",
        "--brf2-runtime-signal-capture-json",
        "--brf2-shadow-candidate-evidence-json",
        "--trial-grade-signal-gate-audit-json",
        "--replay-live-parity-audit-json",
        "--mi-trial-admission-decision-json",
        "--strategy-fresh-signal-action-time-boundary-json",
        "--live-submit-readiness-json",
    ]

    for flag in legacy_flags:
        command = [
            sys.executable,
            "scripts/build_strategygroup_tradeability_decision.py",
            "--database-url",
            "sqlite:///legacy-rejection-does-not-connect.db",
            "--allow-non-postgres-for-test",
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            flag,
        ]
        if flag != "--allow-local-file-diagnostic":
            command.append(str(tmp_path / "legacy.json"))

        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 2, flag
        assert "unrecognized arguments" in result.stderr
        assert flag in result.stderr
        assert not output_json.exists()


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
    assert rows["BRF2-001"]["first_blocker_class"] == "artifact_missing"
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


def test_tradeability_decision_cli_prints_summary(tmp_path: Path, capsys):
    module = _load_module()
    database_url = _create_seeded_runtime_control_db(tmp_path / "runtime.db")

    exit_code = module.main(
        [
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "tradeability_decision_ready"
    assert summary["row_count"] == 5
    assert summary["tradable_now_count"] == 0
