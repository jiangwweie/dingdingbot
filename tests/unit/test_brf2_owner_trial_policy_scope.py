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

    packet = module.build_brf2_owner_trial_policy_scope(
        generated_at_utc="2026-06-23T00:00:00+00:00"
    )

    policy = packet["policy"]
    assert packet["status"] == "brf2_owner_trial_policy_scope_recorded"
    assert packet["brf2_policy_scope_recorded"] is True
    assert packet["owner_policy_scope_missing"] is False
    assert packet["brf2_stage_after_policy"] == "admitted_trial_asset"
    assert packet["brf2_new_first_blocker"] == "required_facts_mapping_gap"
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
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["checks"]["calls_finalgate"] is False
    assert packet["checks"]["calls_operation_layer"] is False
    assert packet["checks"]["calls_exchange_write"] is False
    assert packet["checks"]["places_order"] is False


def test_brf2_owner_trial_policy_scope_cli_writes_docs_and_output(tmp_path: Path):
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
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    docs_packet = json.loads(docs_json.read_text(encoding="utf-8"))
    assert packet["schema"] == module.SCHEMA
    assert docs_packet["schema"] == module.SCHEMA
    assert "BRF2 Owner Trial Policy Scope V0" in output_md.read_text(
        encoding="utf-8"
    )
    assert "BRF2 Owner Trial Policy Scope V0" in docs_md.read_text(encoding="utf-8")
