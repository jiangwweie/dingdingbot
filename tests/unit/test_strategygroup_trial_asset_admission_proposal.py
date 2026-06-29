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


def _capital_trial_envelope_projection() -> dict:
    return {
        "status": "trial_envelope_projection_ready",
        "selected_non_mpg_trial_candidate": {
            "strategy_group_id": "BRF2-001",
            "candidate_status": "short_experiment_evidence_pending_owner_policy",
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
        },
    }


def _trial_envelope() -> dict:
    return {
        "schema": "brc.strategygroup_capital_trial_envelope.v0",
        "strategy_group_id": "BRF2-001",
        "required_facts_draft": ["closed_1h_ohlcv"],
        "side_scope": ["short"],
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


def _assert_admission_does_not_answer_actionability(artifact: dict) -> None:
    assert "actionable_now" not in artifact["checks"]
    assert "real_order_authority" not in artifact["checks"]
    assert "actionable_now" not in artifact["proposal"]
    assert "real_order_authority" not in artifact["proposal"]
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]


def test_trial_asset_admission_proposal_promotes_engineering_to_owner_policy():
    module = _load_module()

    artifact = module.build_trial_asset_admission_proposal(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_envelope=_trial_envelope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    proposal = artifact["proposal"]
    assert proposal["strategy_group_id"] == "BRF2-001"
    assert proposal["current_stage"] == "tiny_live_intake_candidate"
    assert proposal["proposed_stage"] == "trial_asset_admission_candidate"
    assert proposal["owner_policy_required"] is True
    assert "next_action" not in proposal
    assert proposal["non_authority_checkpoint"] == "record_owner_trial_scope_policy"
    assert proposal["after_next_state"] == "admitted_trial_asset"
    assert proposal["proposed_registry_row"]["strategy_group_id"] == "BRF2-001"
    assert proposal["proposed_registry_row"]["trial_eligible"] is False
    assert "actionable_now=false" not in proposal["proposed_registry_row"][
        "authority_boundary"
    ]
    assert "real_order_authority=false" not in proposal["proposed_registry_row"][
        "authority_boundary"
    ]
    assert proposal["proposed_tier_policy_row"]["mode"] == (
        "trial_asset_admission_candidate"
    )
    assert proposal["runtime_admission_plan"]["required_facts_draft"] == [
        "closed_1h_ohlcv",
        "squeeze_risk_state",
    ]
    assert artifact["checks"]["registry_policy_mutated"] is False
    assert artifact["checks"]["tier_policy_mutated"] is False
    assert artifact["checks"]["owner_policy_required"] is True
    assert artifact["checks"]["owner_policy_confirmation_required"] is False
    _assert_admission_does_not_answer_actionability(artifact)
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False


def test_trial_asset_admission_proposal_blocks_legacy_authority_mirrors():
    module = _load_module()
    projection = _capital_trial_envelope_projection()
    trial_envelope = _trial_envelope()
    projection["actionable_now"] = True
    trial_envelope["real_order_authority"] = True

    artifact = module.build_trial_asset_admission_proposal(
        capital_trial_envelope_projection=projection,
        trial_envelope=trial_envelope,
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "legacy_authority_mirror_present:source[0].actionable_now"
        in artifact["checks"]["forbidden_effects"]
    )
    assert (
        "legacy_authority_mirror_present:source[1].real_order_authority"
        in artifact["checks"]["forbidden_effects"]
    )


def test_trial_asset_admission_proposal_consumes_recorded_owner_policy():
    module = _load_module()

    artifact = module.build_trial_asset_admission_proposal(
        capital_trial_envelope_projection=_capital_trial_envelope_projection(),
        trial_envelope=_trial_envelope(),
        brf2_owner_trial_policy_scope=_owner_policy_scope(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    proposal = artifact["proposal"]
    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    assert proposal["strategy_group_id"] == "BRF2-001"
    assert proposal["proposed_stage"] == "admitted_trial_asset"
    assert proposal["owner_policy_required"] is False
    assert proposal["owner_policy_recorded"] is True
    assert proposal["owner_policy_scope_missing"] is False
    assert "next_action" not in proposal
    assert proposal["non_authority_checkpoint"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert proposal["after_next_state"] == "armed_observation"
    assert proposal["owner_policy_defaults"]["trial_identity"] == (
        "BRF2_CONTROLLED_SHORT_TRIAL_V0"
    )
    assert proposal["owner_policy_defaults"]["max_notional"]["balance_source"] == (
        "action_time_exchange_available_balance"
    )
    assert proposal["owner_policy_defaults"]["authority_boundary"] == (
        "owner_policy_only; finalgate_required; operation_layer_required; "
        "no_exchange_write"
    )
    assert artifact["owner_policy_checkpoint"]["owner_policy_required"] is False
    assert artifact["owner_policy_checkpoint"]["owner_policy_recorded"] is True
    assert artifact["checks"]["owner_policy_scope_missing"] is False
    _assert_admission_does_not_answer_actionability(artifact)


def test_trial_asset_admission_proposal_cli_writes_outputs(tmp_path: Path):
    module = _load_module()
    projection_json = tmp_path / "projection.json"
    trial_json = tmp_path / "trial.json"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    trial_json.write_text(json.dumps(_trial_envelope()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-envelope-json",
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
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    md = output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Trial Asset Admission Proposal" in output_md.read_text(
        encoding="utf-8"
    )
    assert "Real order authority" not in md


def test_trial_asset_admission_proposal_cli_omitted_policy_artifact_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    trial_json = tmp_path / "trial.json"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    trial_json.write_text(json.dumps(_trial_envelope()), encoding="utf-8")

    exit_code = module.main(
        [
            "--trial-envelope-json",
            str(trial_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    assert artifact["proposal"]["strategy_group_id"] == "BRF2-001"
    assert artifact["proposal"]["owner_policy_required"] is True


def test_trial_asset_admission_proposal_cli_omitted_trial_envelope_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    projection_json = tmp_path / "projection.json"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    assert artifact["proposal"]["strategy_group_id"] == "BRF2-001"
    assert artifact["proposal"]["runtime_admission_plan"]["required_facts_draft"] == [
        "closed_1h_ohlcv",
        "squeeze_risk_state",
    ]


def test_trial_asset_admission_proposal_cli_omitted_owner_policy_does_not_read_default(
    tmp_path: Path,
):
    module = _load_module()
    projection_json = tmp_path / "projection.json"
    trial_json = tmp_path / "trial.json"
    output_json = tmp_path / "proposal.json"
    output_md = tmp_path / "proposal.md"
    projection_json.write_text(json.dumps(_capital_trial_envelope_projection()), encoding="utf-8")
    trial_json.write_text(json.dumps(_trial_envelope()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capital-trial-envelope-projection-json",
            str(projection_json),
            "--trial-envelope-json",
            str(trial_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "trial_asset_admission_proposal_ready"
    assert artifact["proposal"]["owner_policy_required"] is True
    assert artifact["owner_policy_checkpoint"]["owner_policy_scope_missing"] is True
