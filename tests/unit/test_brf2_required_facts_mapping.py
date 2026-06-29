from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_required_facts_mapping.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_required_facts_mapping",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _owner_policy_scope() -> dict:
    return {
        "status": "brf2_owner_trial_policy_scope_recorded",
        "brf2_policy_scope_recorded": True,
        "owner_policy_scope_missing": False,
        "policy": {
            "strategy_group_id": "BRF2-001",
            "trial_identity": "BRF2_CONTROLLED_SHORT_TRIAL_V0",
        },
    }


def _trial_asset_admission_proposal() -> dict:
    return {
        "status": "trial_asset_admission_proposal_ready",
        "proposal": {
            "strategy_group_id": "BRF2-001",
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "proposed_stage": "admitted_trial_asset",
            "after_next_state": "armed_observation",
        },
    }


def test_brf2_required_facts_mapping_ready_case():
    module = _load_module()

    artifact = module.build_brf2_required_facts_mapping(
        trial_asset_admission_proposal=_trial_asset_admission_proposal(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["schema"] == module.SCHEMA
    assert artifact["status"] == "brf2_required_facts_mapping_ready"
    assert artifact["strategy_group_id"] == "BRF2-001"
    assert artifact["required_facts_mapping_ready"] is True
    assert artifact["after_next_state"] == "armed_observation"
    assert artifact["fresh_signal_rule"]["signal_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert artifact["fresh_signal_rule"]["side"] == "short"
    specs = {
        row["fact_key"]: row["accepted_statuses"]
        for row in artifact["required_fact_observation_specs"]
    }
    assert {
        "closed_1h_ohlcv",
        "closed_5m_ohlcv",
        "rally_context",
        "rally_failure_trigger_state",
        "short_squeeze_risk_state",
        "strong_reclaim_disable_state",
        "liquidity_downshift_state",
        "spread_liquidity_state",
    }.issubset(set(specs))
    assert "required_fact_keys" not in artifact
    assert specs["rally_context"] == [
        "bear_or_weak_reclaim",
        "ready",
        "weak_rally",
    ]
    assert specs["rally_failure_trigger_state"] == [
        "active",
        "confirmed",
        "ready",
    ]
    disable_specs = {
        row["fact_key"]: row
        for row in artifact["disable_fact_observation_specs"]
    }
    assert {
        "short_squeeze_risk_state",
        "strong_reclaim_disable_state",
        "rally_extension_invalidates_failure_state",
        "liquidity_downshift_state",
        "spread_liquidity_state",
    }.issubset(set(disable_specs))
    assert disable_specs["short_squeeze_risk_state"]["active_statuses"] == [
        "red",
        "unbounded",
        "unknown",
    ]
    assert "disable_fact_keys" not in artifact
    assert artifact["first_blocker_after_mapping"] == "fresh_brf2_short_signal_absent"
    assert "next_action" not in artifact
    assert artifact["mapping_checkpoint"] == (
        "continue_brf2_armed_observation_until_fresh_signal"
    )
    for authority_mirror in (
        "actionable_now",
        "real_order_authority",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert authority_mirror not in artifact["checks"]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]


def test_brf2_required_facts_mapping_blocks_without_policy_or_proposal():
    module = _load_module()

    artifact = module.build_brf2_required_facts_mapping(
        trial_asset_admission_proposal={},
        brf2_owner_trial_policy_scope={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == "brf2_required_facts_mapping_blocked"
    assert artifact["required_facts_mapping_ready"] is False
    assert artifact["after_next_state"] == "admitted_trial_asset"
    assert len(artifact["required_fact_observation_specs"]) == 8
    assert "brf2_owner_policy_not_recorded" in artifact["blockers"]
    assert "brf2_trial_asset_admission_proposal_not_ready" in artifact["blockers"]
    assert "actionable_now" not in artifact["checks"]
    assert "real_order_authority" not in artifact["checks"]


def test_brf2_required_facts_mapping_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    proposal_json = tmp_path / "proposal.json"
    policy_json = tmp_path / "policy.json"
    output_json = tmp_path / "mapping.json"
    output_md = tmp_path / "mapping.md"
    proposal_json.write_text(
        json.dumps(_trial_asset_admission_proposal()), encoding="utf-8"
    )
    policy_json.write_text(json.dumps(_owner_policy_scope()), encoding="utf-8")

    exit_code = module.main(
        [
            "--trial-asset-admission-proposal-json",
            str(proposal_json),
            "--brf2-owner-trial-policy-scope-json",
            str(policy_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["schema"] == module.SCHEMA
    assert artifact["status"] == "brf2_required_facts_mapping_ready"
    assert "BRF2 RequiredFacts Mapping" in output_md.read_text(encoding="utf-8")
