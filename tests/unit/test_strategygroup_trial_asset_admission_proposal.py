from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_trial_asset_admission_proposal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_trial_asset_admission_proposal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bridge() -> dict:
    return {
        "status": "capital_trial_readiness_bridge_ready",
        "selected_non_mpg_trial_candidate": {
            "strategy_group_id": "BRF2-001",
            "candidate_status": "short_candidate_trade_packet_pending_owner_policy",
            "required_facts_draft": [
                "closed_1h_ohlcv",
                "squeeze_risk_state",
            ],
            "disable_or_review_facts_draft": [
                "disable_strong_reclaim_proxy",
            ],
            "risk_envelope": {
                "attempt_cap_per_review_cycle": 3,
                "daily_loss_cap_units": 1,
            },
            "symbol_scope": ["owner_policy_required"],
            "side_scope": ["short"],
            "actionable_now": False,
            "real_order_authority": False,
        },
    }


def _trial_packet() -> dict:
    return {
        "schema": "brc.strategygroup_capital_trial_packet.v0",
        "strategy_group_id": "BRF2-001",
        "required_facts_draft": ["closed_1h_ohlcv"],
        "side_scope": ["short"],
        "actionable_now": False,
        "real_order_authority": False,
        "authority_boundary": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
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


def test_trial_asset_admission_proposal_promotes_engineering_to_owner_policy():
    module = _load_module()

    packet = module.build_trial_asset_admission_proposal(
        capital_trial_bridge=_bridge(),
        trial_packet=_trial_packet(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["status"] == "trial_asset_admission_proposal_ready"
    proposal = packet["proposal"]
    assert proposal["strategy_group_id"] == "BRF2-001"
    assert proposal["current_stage"] == "tiny_live_intake_candidate"
    assert proposal["proposed_stage"] == "trial_asset_admission_candidate"
    assert proposal["owner_policy_required"] is True
    assert proposal["next_action"] == "record_owner_trial_scope_policy"
    assert proposal["after_next_state"] == "admitted_trial_asset"
    assert proposal["proposed_registry_row"]["strategy_group_id"] == "BRF2-001"
    assert proposal["proposed_registry_row"]["trial_eligible"] is False
    assert proposal["proposed_tier_policy_row"]["mode"] == (
        "trial_asset_admission_candidate"
    )
    assert proposal["runtime_admission_plan"]["required_facts_draft"] == [
        "closed_1h_ohlcv",
        "squeeze_risk_state",
    ]
    assert packet["checks"]["registry_policy_mutated"] is False
    assert packet["checks"]["tier_policy_mutated"] is False
    assert packet["checks"]["owner_policy_required"] is True
    assert packet["checks"]["owner_decision_required"] is False
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False


def test_trial_asset_admission_proposal_consumes_recorded_owner_policy():
    module = _load_module()

    packet = module.build_trial_asset_admission_proposal(
        capital_trial_bridge=_bridge(),
        trial_packet=_trial_packet(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    proposal = packet["proposal"]
    assert packet["status"] == "trial_asset_admission_proposal_ready"
    assert proposal["strategy_group_id"] == "BRF2-001"
    assert proposal["proposed_stage"] == "admitted_trial_asset"
    assert proposal["owner_policy_required"] is False
    assert proposal["owner_policy_recorded"] is True
    assert proposal["owner_policy_scope_missing"] is False
    assert proposal["next_action"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert proposal["after_next_state"] == "armed_observation"
    assert proposal["owner_policy_defaults"]["trial_identity"] == (
        "BRF2_TINY_SHORT_TRIAL_30U_V0"
    )
    assert proposal["owner_policy_defaults"]["max_notional"]["amount"] == "150"
    assert packet["owner_policy_checkpoint"]["owner_policy_required"] is False
    assert packet["owner_policy_checkpoint"]["owner_policy_recorded"] is True
    assert packet["checks"]["owner_policy_scope_missing"] is False
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False


def test_trial_asset_admission_proposal_cli_writes_outputs(tmp_path: Path):
    module = _load_module()
    bridge_json = tmp_path / "bridge.json"
    trial_json = tmp_path / "trial.json"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    bridge_json.write_text(json.dumps(_bridge()), encoding="utf-8")
    trial_json.write_text(json.dumps(_trial_packet()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-readiness-bridge-json",
            str(bridge_json),
            "--trial-packet-json",
            str(trial_json),
            "--brf2-owner-trial-policy-scope-json",
            str(tmp_path / "missing-policy.json"),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "trial_asset_admission_proposal_ready"
    assert "StrategyGroup Trial Asset Admission Proposal" in output_md.read_text(
        encoding="utf-8"
    )
