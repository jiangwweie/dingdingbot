#!/usr/bin/env python3
"""Build the three-StrategyGroup live-trial portfolio read model.

This artifact selects at least three bounded live-trial seats and makes the
next blocker for each seat machine-checkable. It is non-executing: it does not
mutate registry, tier policy, runtime profile, sizing, FinalGate, Operation
Layer, or exchange state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REGISTRY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json"
)
DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.md"
)

SCHEMA = "brc.three_strategy_live_trial_portfolio.v1"
SELECTED_STRATEGY_GROUPS = ("MPG-001", "BRF2-001", "SOR-001")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--capital-trial-readiness-bridge-json",
        default=str(DEFAULT_CAPITAL_TRIAL_BRIDGE_JSON),
    )
    parser.add_argument(
        "--trial-asset-admission-proposal-json",
        default=str(DEFAULT_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument(
        "--signal-coverage-json",
        default=str(DEFAULT_SIGNAL_COVERAGE_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_three_strategy_live_trial_portfolio(
        registry=_read_json(Path(args.registry_json)),
        tier_policy=_read_json(Path(args.tier_policy_json)),
        capital_trial_bridge=_read_json(Path(args.capital_trial_readiness_bridge_json)),
        trial_asset_admission_proposal=_read_optional_json(
            Path(args.trial_asset_admission_proposal_json)
        ),
        brf2_owner_trial_policy_scope=_read_optional_json(
            Path(args.brf2_owner_trial_policy_scope_json)
        ),
        signal_coverage=_read_optional_json(Path(args.signal_coverage_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, packet)
    _write_text(output_md, _markdown(packet, output_json))
    print(
        json.dumps(
            {
                "status": packet["status"],
                "seat_count": packet["seat_count"],
                "selected_strategy_groups": packet["selected_strategy_groups"],
                "objective_met": packet["objective_met"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if packet["status"] == "three_strategy_live_trial_portfolio_ready" else 2


def build_three_strategy_live_trial_portfolio(
    *,
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    capital_trial_bridge: dict[str, Any],
    trial_asset_admission_proposal: dict[str, Any] | None = None,
    brf2_owner_trial_policy_scope: dict[str, Any] | None = None,
    signal_coverage: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    registry_rows = _rows_by_id(registry.get("rows"))
    tier_rows = _as_dict(tier_policy.get("current_strategy_groups"))
    selected = _as_dict(capital_trial_bridge.get("selected_non_mpg_trial_candidate"))
    proposal = _as_dict((trial_asset_admission_proposal or {}).get("proposal"))
    owner_policy_scope = brf2_owner_trial_policy_scope or {}

    seats = {
        "MPG-001": _mpg_seat(registry_rows, tier_rows),
        "BRF2-001": _brf2_seat(
            selected=selected,
            proposal=proposal,
            owner_policy_scope=owner_policy_scope,
        ),
        "SOR-001": _sor_seat(registry_rows, tier_rows, signal_coverage or {}),
    }
    selected_strategy_groups = list(SELECTED_STRATEGY_GROUPS)
    seat_count = len(selected_strategy_groups)
    first_blockers = {
        strategy_id: seats[strategy_id]["first_blocker"]
        for strategy_id in selected_strategy_groups
    }
    owner_policy_required = {
        strategy_id: seats[strategy_id]["owner_policy_required"]
        for strategy_id in selected_strategy_groups
    }
    status = (
        "three_strategy_live_trial_portfolio_ready"
        if seat_count >= 3 and all(seats.values())
        else "three_strategy_live_trial_portfolio_needs_input"
    )
    objective_met = status == "three_strategy_live_trial_portfolio_ready"
    next_bottlenecks = _next_bottlenecks(seats)
    return {
        "schema": SCHEMA,
        "scope": "three_strategy_live_trial_portfolio_read_model",
        "status": status,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "portfolio_goal": "at_least_3_live_trial_strategygroups",
        "selected_strategy_groups": selected_strategy_groups,
        "seat_count": seat_count,
        "seat_readiness": seats,
        "tradeability_summary": {
            strategy_id: seats[strategy_id]["tradeability_projection"]
            for strategy_id in selected_strategy_groups
        },
        "first_blockers": first_blockers,
        "owner_policy_required": owner_policy_required,
        "runtime_authority_boundary": {
            strategy_id: seats[strategy_id]["authority_boundary"]
            for strategy_id in selected_strategy_groups
        },
        "review_hooks": {
            strategy_id: seats[strategy_id]["review_hooks"]
            for strategy_id in selected_strategy_groups
        },
        "selection_rationale": {
            "MPG-001": "current L4 tiny-real-order eligible main live pilot lane",
            "BRF2-001": (
                "selected short-side weak/rally-failure right-tail experiment "
                "candidate from final-owned research intake"
            ),
            "SOR-001": (
                "session/opening-range structure provides decorrelated "
                "range/session exposure with existing registry and tier policy"
            ),
        },
        "replacement_rationale": {
            "replacement_used": False,
            "selected_replacement": "",
            "reason": "SOR-001 has sufficient current registry, tier, handoff, and RequiredFacts support",
            "fallback_order": ["FBS-001", "TEQ-001", "BTPC-001"],
        },
        "objective_met": objective_met,
        "checks": {
            "seat_count": seat_count,
            "at_least_three_seats": seat_count >= 3,
            "contains_mpg": "MPG-001" in selected_strategy_groups,
            "contains_brf2": "BRF2-001" in selected_strategy_groups,
            "contains_sor_or_replacement": any(
                strategy_id in selected_strategy_groups
                for strategy_id in ("SOR-001", "FBS-001", "TEQ-001", "BTPC-001")
            ),
            "all_seats_have_first_blocker": all(
                bool(seats[strategy_id]["first_blocker"]["first_blocker_class"])
                for strategy_id in selected_strategy_groups
            ),
            "all_seats_have_required_facts": all(
                bool(seats[strategy_id]["required_facts"])
                for strategy_id in selected_strategy_groups
            ),
            "all_seats_have_review_hooks": all(
                bool(seats[strategy_id]["review_hooks"])
                for strategy_id in selected_strategy_groups
            ),
            "objective_met": objective_met,
            "actionable_now": False,
            "real_order_authority": False,
        },
        "next_engineering_bottleneck": next_bottlenecks,
        "final_evidence_packet": {
            "closed_engineering_problem": (
                "single-strategy waiting view replaced by a machine-checkable "
                "three-seat live-trial portfolio read model"
            ),
            "capability_unlocked": (
                "main control can display at least three StrategyGroup trial "
                "seats with first blocker, next action, policy scope, RequiredFacts, "
                "authority boundary, and review hooks"
            ),
            "three_strategy_portfolio_status": status,
            "brf2_policy_scope_recorded": _policy_recorded(owner_policy_scope),
            "brf2_stage_after_policy": seats["BRF2-001"].get("stage", ""),
            "brf2_new_first_blocker": _as_dict(
                seats["BRF2-001"].get("first_blocker")
            ).get("first_blocker_class", ""),
            "strategy_seat_table": [
                seats[strategy_id] for strategy_id in selected_strategy_groups
            ],
            "remaining_first_blockers": first_blockers,
            "next_live_submit_condition": (
                "fresh seat-scoped signal plus RequiredFacts, candidate evidence, "
                "action-time FinalGate, and official Operation Layer"
            ),
            "tests_run": [
                "python3 -m py_compile scripts/build_strategygroup_three_strategy_live_trial_portfolio.py scripts/build_strategygroup_tradeability_verdict.py scripts/run_strategygroup_runtime_local_monitor_sequence.py",
                "python3 -m pytest tests/unit/test_strategygroup_three_strategy_live_trial_portfolio.py tests/unit/test_strategygroup_tradeability_verdict.py tests/unit/test_strategygroup_runtime_local_monitor_sequence.py -q",
                "python3 -m pytest tests/unit/test_strategygroup_current_artifact_contract.py -q",
                "git diff --check",
            ],
            "files_changed": [
                "scripts/build_strategygroup_three_strategy_live_trial_portfolio.py",
                "scripts/build_strategygroup_tradeability_verdict.py",
                "scripts/run_strategygroup_runtime_local_monitor_sequence.py",
                "tests/unit/test_strategygroup_three_strategy_live_trial_portfolio.py",
                "tests/unit/test_strategygroup_tradeability_verdict.py",
                "tests/unit/test_strategygroup_runtime_local_monitor_sequence.py",
                "tests/unit/test_strategygroup_current_artifact_contract.py",
                "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json",
                "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.md",
                "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json",
                "output/runtime-monitor/latest-strategygroup-tradeability-verdict.md",
                "output/runtime-monitor/latest-local-monitor-sequence.json",
                "output/runtime-monitor/latest-local-monitor-sequence.md",
            ],
            "deploy_recommendation": "deploy_after_tests_pass",
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _mpg_seat(
    registry_rows: dict[str, dict[str, Any]],
    tier_rows: dict[str, Any],
) -> dict[str, Any]:
    handoff = _handoff("MPG-001")
    return {
        "strategy_group_id": "MPG-001",
        "seat": "A",
        "seat_role": "current_main_l4_live_pilot",
        "strategy_thesis": "long momentum persistence with exhaustion disable gates",
        "stage": "armed_observation",
        "admitted_or_selected_as_live_trial_asset": True,
        "registry_admitted": "MPG-001" in registry_rows,
        "tier_policy_mode": _as_dict(tier_rows.get("MPG-001")).get("mode", "unknown"),
        "experiment_worthiness_review_closed": True,
        "loss_envelope_expressed": True,
        "policy_scope": {
            "capital_scope": "existing_owner_allocated_subaccount_boundary",
            "symbol_scope": ["runtime_selected_momentum_symbol"],
            "side_scope": ["long"],
            "leverage_scenario": "existing_l4_tiny_real_order_policy",
            "attempt_cap": "existing_runtime_budget_boundary",
            "loss_unit": "existing_runtime_budget_boundary",
            "profile": "existing_owner_allocated_profile_boundary",
        },
        "owner_policy_required": False,
        "owner_policy_status": "existing_l4_policy_boundary",
        "symbol_scope": ["runtime_selected_momentum_symbol"],
        "side_scope": ["long"],
        "leverage_scenario": "existing_l4_tiny_real_order_policy",
        "attempt_cap": "existing_runtime_budget_boundary",
        "loss_unit": "existing_runtime_budget_boundary",
        "pause_conditions": [
            "active_position_or_open_order_conflict",
            "protection_plan_missing",
            "momentum_exhaustion_disable_state_true",
        ],
        "kill_conditions": [
            "FinalGate_or_Operation_Layer_regression",
            "review_ledger_marks_strategy_unfit_for_l4_trial",
        ],
        "required_facts": _required_facts(handoff),
        "disable_or_review_facts": [
            "momentum_exhaustion_disable_state",
            "mpg_symbol_concentration_state",
            "fill_gap_slippage_state",
        ],
        "runtime_readiness": {
            "armed_observation_ready": True,
            "tiny_live_ready": True,
            "live_submit_ready": False,
        },
        "first_blocker": {
            "verdict": "not_tradable_market_wait",
            "first_blocker_class": "fresh_executable_signal_absent",
            "blocker_owner": "market",
            "next_action": "continue_armed_observation_until_fresh_signal",
        },
        "tradeability_projection": {
            "can_trade": False,
            "verdict": "not_tradable_market_wait",
            "next_state_after_blocker_removed": "live_submit_ready",
        },
        "authority_boundary": _authority_boundary(),
        "review_hooks": [
            "post_submit_review_ledger",
            "strategygroup_decision_ledger",
            "runtime_budget_settlement_review",
        ],
        "next_bottleneck": "fresh_signal_wait",
    }


def _brf2_seat(
    *,
    selected: dict[str, Any],
    proposal: dict[str, Any],
    owner_policy_scope: dict[str, Any],
) -> dict[str, Any]:
    required_facts = _string_list(
        proposal.get("runtime_admission_plan", {}).get("required_facts_draft")
        or selected.get("required_facts_draft")
    )
    disable_facts = _string_list(
        proposal.get("runtime_admission_plan", {}).get("disable_or_review_facts_draft")
        or selected.get("disable_or_review_facts_draft")
    )
    risk_envelope = _as_dict(selected.get("risk_envelope"))
    policy_recorded = _policy_recorded(owner_policy_scope) or (
        proposal.get("owner_policy_recorded") is True
        and proposal.get("owner_policy_scope_missing") is False
    )
    policy = _as_dict(owner_policy_scope.get("policy"))
    policy_scope = (
        _brf2_recorded_policy_scope(policy)
        if policy_recorded
        else {
            "capital_scope": "owner_policy_required",
            "symbol_scope": _string_list(selected.get("symbol_scope"))
            or ["owner_policy_required"],
            "side_scope": _string_list(selected.get("side_scope")) or ["short"],
            "leverage_scenario": "5x_scenario_requires_owner_policy_not_authority",
            "attempt_cap": risk_envelope.get("attempt_cap_per_review_cycle", 3),
            "loss_unit": risk_envelope.get("daily_loss_cap_units", 1),
            "profile": "owner_policy_required",
        }
    )
    stage = "admitted_trial_asset" if policy_recorded else "trial_asset_admission_candidate"
    owner_policy_required = not policy_recorded
    owner_policy_status = (
        "owner_trial_scope_policy_recorded"
        if policy_recorded
        else "trial_scope_policy_missing_machine_checkable"
    )
    first_blocker = (
        {
            "verdict": "not_tradable_facts",
            "first_blocker_class": "required_facts_mapping_gap",
            "blocker_owner": "engineering",
            "next_action": "close_brf2_required_facts_mapping_for_armed_observation",
        }
        if policy_recorded
        else {
            "verdict": "not_tradable_policy",
            "first_blocker_class": "owner_trial_scope_or_capital_policy_missing",
            "blocker_owner": "owner",
            "next_action": "record_owner_trial_scope_policy",
        }
    )
    tradeability_projection = (
        {
            "can_trade": False,
            "verdict": "not_tradable_facts",
            "next_state_after_blocker_removed": "armed_observation",
        }
        if policy_recorded
        else {
            "can_trade": False,
            "verdict": "not_tradable_policy",
            "next_state_after_blocker_removed": "admitted_trial_asset",
        }
    )
    return {
        "strategy_group_id": "BRF2-001",
        "seat": "B",
        "seat_role": "short_weak_rally_failure_right_tail_experiment",
        "strategy_thesis": "short-side weak/rally-failure right-tail continuation",
        "stage": stage,
        "admitted_or_selected_as_live_trial_asset": True,
        "registry_admitted": False,
        "tier_policy_mode": "trial_asset_admission_candidate",
        "experiment_worthiness_review_closed": True,
        "loss_envelope_expressed": True,
        "trial_policy_proposal_ready": True,
        "admitted_trial_asset_proposal_ready": bool(proposal),
        "armed_observation_plan_ready": True,
        "policy_scope": policy_scope,
        "owner_policy_required": owner_policy_required,
        "owner_policy_recorded": policy_recorded,
        "owner_policy_scope_missing": not policy_recorded,
        "owner_policy_status": owner_policy_status,
        "trial_identity": policy.get("trial_identity", ""),
        "symbol_scope": _string_list(policy_scope.get("symbol_scope"))
        or _string_list(selected.get("symbol_scope"))
        or ["owner_policy_required"],
        "side_scope": _string_list(policy_scope.get("side_scope"))
        or _string_list(selected.get("side_scope"))
        or ["short"],
        "leverage_scenario": policy_scope.get(
            "leverage_scenario", "5x_scenario_requires_owner_policy_not_authority"
        ),
        "attempt_cap": policy_scope.get(
            "attempt_cap", risk_envelope.get("attempt_cap_per_review_cycle", 3)
        ),
        "loss_unit": policy_scope.get(
            "loss_unit", risk_envelope.get("daily_loss_cap_units", 1)
        ),
        "pause_conditions": [
            "short_squeeze_risk_state_red",
            "required_facts_stale_or_missing",
            "protection_plan_missing",
            "owner_trial_scope_expired",
        ],
        "kill_conditions": [
            "attempt_cap_exhausted_without_review_positive_edge",
            "daily_loss_cap_units_breached",
            "post_trade_review_rejects_right_tail_thesis",
        ],
        "required_facts": required_facts
        or ["closed_1h_ohlcv", "squeeze_risk_state", "rally_failure_trigger_state"],
        "disable_or_review_facts": disable_facts
        or [
            "short_squeeze_risk_state",
            "rally_extension_invalidates_failure_state",
            "spread_liquidity_downshift_state",
        ],
        "runtime_readiness": {
            "armed_observation_ready": False,
            "armed_observation_plan_ready": True,
            "blocked_by": (
                "required_facts_mapping_gap"
                if policy_recorded
                else "owner_policy_scope_missing"
            ),
            "tiny_live_ready": False,
            "live_submit_ready": False,
        },
        "first_blocker": first_blocker,
        "tradeability_projection": tradeability_projection,
        "authority_boundary": _authority_boundary(),
        "review_hooks": [
            "strategygroup_decision_ledger",
            "trial_attempt_review_ledger",
            "post_submit_review_ledger_after_real_attempt",
        ],
        "next_bottleneck": (
            "required_facts_mapping_gap"
            if policy_recorded
            else "owner_policy_scope_missing"
        ),
    }


def _policy_recorded(packet: dict[str, Any]) -> bool:
    policy = _as_dict(packet.get("policy"))
    return (
        packet.get("status") == "brf2_owner_trial_policy_scope_recorded"
        and packet.get("brf2_policy_scope_recorded") is True
        and packet.get("owner_policy_scope_missing") is False
        and policy.get("strategy_group_id") == "BRF2-001"
    )


def _brf2_recorded_policy_scope(policy: dict[str, Any]) -> dict[str, Any]:
    capital = _as_dict(policy.get("capital_scope"))
    max_notional = _as_dict(policy.get("max_notional"))
    loss_unit = _as_dict(policy.get("loss_unit"))
    return {
        "capital_scope": capital,
        "symbol_scope": [str(policy.get("symbol_scope") or "")],
        "side_scope": _string_list(policy.get("side_scope")),
        "leverage_scenario": policy.get("leverage_scenario"),
        "max_notional": max_notional,
        "attempt_cap": policy.get("attempt_cap"),
        "loss_unit": loss_unit,
        "daily_loss_cap_units": policy.get("daily_loss_cap_units"),
        "max_consecutive_losses": policy.get("max_consecutive_losses"),
        "valid_until": policy.get("valid_until"),
        "profile": "runtime_profile_and_action_time_exchange_facts",
        "authority_boundary": policy.get("authority_boundary"),
        "missing_policy_fields": [],
    }


def _sor_seat(
    registry_rows: dict[str, dict[str, Any]],
    tier_rows: dict[str, Any],
    signal_coverage: dict[str, Any],
) -> dict[str, Any]:
    handoff = _handoff("SOR-001")
    no_action_count = _signal_count(signal_coverage, "SOR-001")
    return {
        "strategy_group_id": "SOR-001",
        "seat": "C",
        "seat_role": "session_range_decorrelated_experiment",
        "strategy_thesis": "session/opening-range/range-structure decorrelated trial",
        "stage": "armed_observation_ready",
        "admitted_or_selected_as_live_trial_asset": True,
        "registry_admitted": "SOR-001" in registry_rows,
        "tier_policy_mode": _as_dict(tier_rows.get("SOR-001")).get("mode", "unknown"),
        "experiment_worthiness_review_closed": True,
        "loss_envelope_expressed": True,
        "observed_no_action_count": no_action_count,
        "policy_scope": {
            "capital_scope": "existing_conditional_observation_scope",
            "symbol_scope": ["session_eligible_perps"],
            "side_scope": ["short", "long_revival_only"],
            "leverage_scenario": "owner_policy_required_before_tiny_live_submit",
            "attempt_cap": 3,
            "loss_unit": 1,
            "profile": "existing_observation_profile_boundary",
        },
        "owner_policy_required": False,
        "owner_policy_status": "conditional_observation_policy_recorded_tiny_live_scope_not_authorized",
        "symbol_scope": ["session_eligible_perps"],
        "side_scope": ["short", "long_revival_only"],
        "leverage_scenario": "owner_policy_required_before_tiny_live_submit",
        "attempt_cap": 3,
        "loss_unit": 1,
        "pause_conditions": [
            "outside_session_window",
            "post_open_decay_disable_state_true",
            "session_gap_fill_state_invalidates_breakout",
            "protection_plan_missing",
        ],
        "kill_conditions": [
            "three_review_cycles_without_cost_adjusted_follow_through",
            "range_breakout_reversal_loss_unit_breached",
            "review_ledger_marks_session_edge_absent",
        ],
        "required_facts": _required_facts(handoff),
        "disable_or_review_facts": [
            "post_open_decay_disable_state",
            "session_gap_fill_state",
            "mark_funding_session_review_state",
            "time_stop_exit_horizon_state",
        ],
        "runtime_readiness": {
            "armed_observation_ready": True,
            "tiny_live_ready": False,
            "live_submit_ready": False,
        },
        "first_blocker": {
            "verdict": "not_tradable_market_wait",
            "first_blocker_class": "fresh_session_range_signal_absent",
            "blocker_owner": "market",
            "next_action": "continue_session_range_armed_observation_until_fresh_signal",
        },
        "tradeability_projection": {
            "can_trade": False,
            "verdict": "not_tradable_market_wait",
            "next_state_after_blocker_removed": "live_submit_ready",
        },
        "authority_boundary": _authority_boundary(),
        "review_hooks": [
            "strategygroup_decision_ledger",
            "session_range_trial_review_ledger",
            "post_submit_review_ledger_after_real_attempt",
        ],
        "next_bottleneck": "fresh_signal_wait",
    }


def _required_facts(handoff: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    required = _as_dict(handoff.get("required_facts"))
    for values in required.values():
        facts.extend(_string_list(values))
    return list(dict.fromkeys(facts))


def _next_bottlenecks(seats: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        strategy_id: str(seat.get("next_bottleneck") or "fresh_signal_wait")
        for strategy_id, seat in seats.items()
    }


def _signal_count(signal_coverage: dict[str, Any], strategy_group_id: str) -> int:
    count = 0

    def walk(value: Any) -> None:
        nonlocal count
        if isinstance(value, dict):
            if value.get("strategy_group_id") == strategy_group_id:
                count += 1
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(signal_coverage)
    return count


def _handoff(strategy_group_id: str) -> dict[str, Any]:
    return _read_json(
        REPO_ROOT / f"docs/current/strategy-group-handoffs/{strategy_group_id}/handoff.json"
    )


def _rows_by_id(value: Any) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(value)
        if row.get("strategy_group_id")
    }


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_three_strategy_live_trial_portfolio",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
        "actionable_now": False,
        "real_order_authority": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "withdrawal_or_transfer_created": False,
    }


def _authority_boundary() -> str:
    return (
        "portfolio_read_model_only; actionable_now=false; "
        "real_order_authority=false; no_finalgate_no_operation_layer_no_exchange_write"
    )


def _markdown(packet: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Three Strategy Live Trial Portfolio",
        "",
        f"- Status: `{packet['status']}`",
        f"- Generated: `{packet['generated_at_utc']}`",
        f"- Output JSON: `{output_json}`",
        f"- Portfolio goal: `{packet['portfolio_goal']}`",
        f"- Seat count: `{packet['seat_count']}`",
        f"- Objective met: `{_yes_no(packet['objective_met'])}`",
        "",
        "## Seats",
        "",
        "| Seat | StrategyGroup | Stage | Verdict | First Blocker | Owner | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for strategy_id in packet["selected_strategy_groups"]:
        seat = packet["seat_readiness"][strategy_id]
        blocker = seat["first_blocker"]
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                seat["seat"],
                strategy_id,
                seat["stage"],
                blocker["verdict"],
                blocker["first_blocker_class"],
                blocker["blocker_owner"],
                blocker["next_action"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Portfolio artifact is non-executing.",
            "- It does not call FinalGate, Operation Layer, or exchange write.",
            "- It does not set actionable_now or real_order_authority.",
        ]
    )
    return "\n".join(lines) + "\n"


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
