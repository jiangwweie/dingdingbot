from __future__ import annotations

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


def _capital_trial_bridge() -> dict:
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
            "trial_identity": "BRF2_TINY_SHORT_TRIAL_30U_V0",
            "capital_scope": {
                "type": "isolated_subaccount_full_allocation",
                "amount": "30",
                "currency": "USDT",
                "loss_capable": True,
            },
            "side_scope": ["short"],
            "symbol_scope": "brf2_research_supported_symbols_only",
            "leverage_scenario": "5x_scenario_not_authority",
            "max_notional": {
                "amount": "150",
                "currency": "USDT",
                "basis": "30U capital x 5x scenario",
                "final_authority": "runtime_profile_and_action_time_exchange_facts",
            },
            "attempt_cap": 3,
            "loss_unit": {
                "amount": "10",
                "currency": "USDT",
                "basis": "30U / 3 attempts",
            },
            "daily_loss_cap_units": 1,
            "max_consecutive_losses": 2,
            "valid_until": "one_review_cycle",
            "pause_conditions": ["two_consecutive_losses"],
            "authority_boundary": "owner_policy_only; actionable_now=false",
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
        "required_fact_keys": [
            "closed_1h_ohlcv",
            "closed_5m_ohlcv",
            "rally_context",
            "rally_failure_trigger_state",
            "short_squeeze_risk_state",
            "strong_reclaim_disable_state",
            "liquidity_downshift_state",
            "spread_liquidity_state",
        ],
        "disable_fact_keys": [
            "short_squeeze_risk_state",
            "strong_reclaim_disable_state",
            "rally_extension_invalidates_failure_state",
            "liquidity_downshift_state",
            "spread_liquidity_state",
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
            "next_action": "attach_brf2_watcher_fact_input_producer",
        },
    }


def test_three_strategy_portfolio_selects_mpg_brf2_and_sor():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_bridge=_capital_trial_bridge(),
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
    assert packet["checks"]["all_seats_have_first_blocker"] is True
    assert packet["checks"]["all_seats_have_required_facts"] is True
    assert packet["checks"]["all_seats_have_review_hooks"] is True

    brf2 = packet["seat_readiness"]["BRF2-001"]
    assert brf2["stage"] == "admitted_trial_asset"
    assert brf2["trial_policy_proposal_ready"] is True
    assert brf2["admitted_trial_asset_proposal_ready"] is True
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_plan_ready"] is True
    assert brf2["runtime_readiness"]["armed_observation_ready"] is False
    assert brf2["runtime_readiness"]["blocked_by"] == "required_facts_mapping_gap"
    assert brf2["runtime_readiness"]["tiny_live_ready"] is False
    assert brf2["runtime_readiness"]["live_submit_ready"] is False
    assert brf2["owner_policy_required"] is False
    assert brf2["owner_policy_recorded"] is True
    assert brf2["owner_policy_scope_missing"] is False
    assert brf2["policy_scope"]["capital_scope"]["amount"] == "30"
    assert brf2["policy_scope"]["max_notional"]["amount"] == "150"
    assert brf2["first_blocker"]["blocker_owner"] == "engineering"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "required_facts_mapping_gap"
    )
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == (
        "required_facts_mapping_gap"
    )
    assert packet["final_evidence_packet"]["brf2_policy_scope_recorded"] is True

    sor = packet["seat_readiness"]["SOR-001"]
    assert sor["experiment_worthiness_review_closed"] is True
    assert sor["loss_envelope_expressed"] is True
    assert sor["first_blocker"]["first_blocker_class"] == (
        "fresh_session_range_signal_absent"
    )
    assert sor["first_blocker"]["blocker_owner"] == "market"

    assert packet["safety_invariants"]["actionable_now"] is False
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_three_strategy_portfolio_moves_brf2_to_armed_observation_after_mapping():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_bridge=_capital_trial_bridge(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        brf2_required_facts_mapping=_brf2_required_facts_mapping(),
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
    assert brf2["first_blocker"]["verdict"] == "not_tradable_market_wait"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "fresh_brf2_short_signal_absent"
    )
    assert brf2["first_blocker"]["blocker_owner"] == "market"
    assert brf2["first_blocker"]["next_action"] == (
        "continue_brf2_armed_observation_until_fresh_signal"
    )
    assert brf2["tradeability_projection"]["next_state_after_blocker_removed"] == (
        "live_submit_ready"
    )
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == "fresh_signal_wait"


def test_three_strategy_portfolio_surfaces_brf2_fact_input_gap_after_mapping():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_bridge=_capital_trial_bridge(),
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
    assert brf2["first_blocker"]["verdict"] == "not_tradable_facts"
    assert brf2["first_blocker"]["first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert brf2["first_blocker"]["blocker_owner"] == "engineering"
    assert brf2["first_blocker"]["next_action"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    assert brf2["tradeability_projection"]["next_state_after_blocker_removed"] == (
        "armed_observation"
    )
    assert packet["next_engineering_bottleneck"]["BRF2-001"] == (
        "brf2_watcher_fact_input_missing"
    )


def test_three_strategy_portfolio_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    bridge_json = tmp_path / "bridge.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    policy_json = tmp_path / "policy.json"
    mapping_json = tmp_path / "brf2-required-facts.json"
    capture_json = tmp_path / "brf2-runtime-signal-capture.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    bridge_json.write_text(json.dumps(_capital_trial_bridge()), encoding="utf-8")
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
            "--capital-trial-readiness-bridge-json",
            str(bridge_json),
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
