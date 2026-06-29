from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_owner_trial_policy_scope.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_owner_trial_policy_scope",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_brf2_owner_trial_policy_scope_records_30u_boundary_without_authority():
    module = _load_module()

    artifact = module.build_brf2_owner_trial_policy_scope(
        generated_at_utc="2026-06-23T00:00:00+00:00"
    )

    policy = artifact["policy"]
    assert artifact["status"] == "brf2_owner_trial_policy_scope_recorded"
    assert artifact["brf2_policy_scope_recorded"] is True
    assert artifact["owner_policy_scope_missing"] is False
    assert artifact["brf2_stage_after_policy"] == "admitted_trial_asset"
    assert artifact["brf2_new_first_blocker"] == "required_facts_mapping_gap"
    assert "brf2_next_action" not in artifact
    assert artifact["brf2_policy_checkpoint"] == (
        "close_brf2_required_facts_mapping_for_armed_observation"
    )
    assert "final_policy_evidence" in artifact
    assert "final_evidence_packet" not in artifact
    assert policy["strategy_group_id"] == "BRF2-001"
    assert policy["trial_identity"] == "BRF2_TINY_SHORT_TRIAL_30U_V0"
    assert policy["capital_scope"] == {
        "type": "isolated_subaccount_full_allocation",
        "amount": "30",
        "currency": "USDT",
        "loss_capable": True,
    }
    assert policy["side_scope"] == ["short"]
    assert policy["symbol_scope"] == "brf2_research_supported_symbols_only"
    assert policy["leverage_scenario"] == "5x_scenario_not_authority"
    assert policy["max_notional"]["amount"] == "150"
    assert policy["attempt_cap"] == 3
    assert policy["loss_unit"]["amount"] == "10"
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
    assert "actionable_now" not in policy["authority_boundary"]
    assert "real_order_authority" not in policy["authority_boundary"]


def test_brf2_owner_trial_policy_scope_cli_default_writes_output_only(
    tmp_path: Path,
):
    module = _load_module()
    authority = module.build_brf2_owner_trial_policy_scope(
        generated_at_utc="2026-06-23T00:00:00+00:00"
    )
    policy_json = tmp_path / "policy.json"
    output_json = tmp_path / "output.json"
    output_md = tmp_path / "output.md"
    docs_json = tmp_path / "docs.json"
    docs_md = tmp_path / "docs.md"
    policy_json.write_text(json.dumps(authority), encoding="utf-8")

    exit_code = module.main(
        [
            "--policy-json",
            str(policy_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--docs-json",
            str(docs_json),
            "--docs-md",
            str(docs_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["schema"] == module.SCHEMA
    assert artifact["view_mode"] == "monitor_view_from_final_owned_policy"
    assert artifact["source_policy_json"] == str(policy_json)
    assert "final_policy_evidence" in artifact
    assert "final_evidence_packet" not in artifact
    markdown = output_md.read_text(encoding="utf-8")
    assert "BRF2 Owner Trial Policy Scope V0" in markdown
    assert "Actionable now" not in markdown
    assert "Real order authority" not in markdown
    assert not docs_json.exists()
    assert not docs_md.exists()


def test_brf2_owner_trial_policy_scope_cli_writes_docs_only_when_explicit(
    tmp_path: Path,
):
    module = _load_module()
    output_json = tmp_path / "output.json"
    output_md = tmp_path / "output.md"
    docs_json = tmp_path / "docs.json"
    docs_md = tmp_path / "docs.md"

    exit_code = module.main(
        [
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
            "--docs-json",
            str(docs_json),
            "--docs-md",
            str(docs_md),
            "--write-docs",
        ]
    )

    assert exit_code == 0
    docs_artifact = json.loads(docs_json.read_text(encoding="utf-8"))
    assert docs_artifact["schema"] == module.SCHEMA
    assert "final_policy_evidence" in docs_artifact
    assert "final_evidence_packet" not in docs_artifact
    markdown = docs_md.read_text(encoding="utf-8")
    assert "BRF2 Owner Trial Policy Scope V0" in markdown
    assert "Actionable now" not in markdown
    assert "Real order authority" not in markdown
