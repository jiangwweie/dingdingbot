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
            "runtime_admission_plan": {
                "required_facts_draft": ["closed_1h_ohlcv", "squeeze_risk_state"],
                "disable_or_review_facts_draft": ["short_squeeze_risk_state"],
            },
        }
    }


def test_three_strategy_portfolio_selects_mpg_brf2_and_sor():
    module = _load_module()

    packet = module.build_three_strategy_live_trial_portfolio(
        registry=_registry(),
        tier_policy=_tier_policy(),
        capital_trial_bridge=_capital_trial_bridge(),
        trial_asset_admission_proposal=_trial_admission_proposal(),
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
    assert brf2["trial_policy_proposal_ready"] is True
    assert brf2["admitted_trial_asset_proposal_ready"] is True
    assert brf2["armed_observation_plan_ready"] is True
    assert brf2["first_blocker"]["blocker_owner"] == "owner"

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


def test_three_strategy_portfolio_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    registry_json = tmp_path / "registry.json"
    tier_json = tmp_path / "tier.json"
    bridge_json = tmp_path / "bridge.json"
    proposal_json = tmp_path / "proposal.json"
    signal_json = tmp_path / "signal.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    registry_json.write_text(json.dumps(_registry()), encoding="utf-8")
    tier_json.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    bridge_json.write_text(json.dumps(_capital_trial_bridge()), encoding="utf-8")
    proposal_json.write_text(json.dumps(_trial_admission_proposal()), encoding="utf-8")
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
