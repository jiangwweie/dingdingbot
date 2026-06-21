from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_strategygroup_l2_tier_policy_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_l2_tier_policy_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _l2_intake_packet(*, forbidden: bool = False) -> dict:
    return {
        "status": "l2_intake_dry_run_passed",
        "decision": {
            "groups_ready_for_l2_policy_review": ["BTPC-001"],
            "l4_scope_change_recommended": False,
        },
        "dry_run_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "status": "passed",
                "blockers": [],
            }
        ],
        "safety_invariants": {
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _tier_policy(*, btpc_current: bool = False) -> dict:
    current = {
        "MPG-001": {"tier": "L4", "mode": "tiny_real_order_eligible"},
        "TEQ-001": {"tier": "L2", "mode": "shadow_candidate"},
    }
    known_new = {"BTPC": "L1", "VCB": "L1"}
    if btpc_current:
        current["BTPC-001"] = {"tier": "L2", "mode": "shadow_candidate"}
        known_new.pop("BTPC")
    return {
        "tier_definitions": {
            "L1": {
                "may_observe_market": True,
                "may_prepare_shadow_candidate": False,
                "may_reach_finalgate": False,
                "may_reach_operation_layer": False,
                "may_place_real_order": False,
            },
            "L2": {
                "may_observe_market": True,
                "may_prepare_shadow_candidate": True,
                "may_reach_finalgate": False,
                "may_reach_operation_layer": False,
                "may_place_real_order": False,
            },
            "L4": {
                "may_observe_market": True,
                "may_prepare_shadow_candidate": True,
                "may_reach_finalgate": True,
                "may_reach_operation_layer": True,
                "may_place_real_order": True,
            },
        },
        "current_strategy_groups": current,
        "new_strategy_group_defaults": {"known_new_groups": known_new},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_l2_tier_policy_review_recommends_btpc_l2_without_l4_scope_change():
    module = _load_module()

    packet = module.build_l2_tier_policy_review(
        l2_intake_packet=_l2_intake_packet(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "l2_tier_policy_review_recommended"
    assert packet["counts"]["ready_to_apply_count"] == 1
    assert packet["decision"]["groups_ready_to_apply_l2"] == ["BTPC-001"]
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_final_gate"] is False
    assert packet["operator_command_plan"]["calls_operation_layer"] is False
    row = packet["review_rows"][0]
    assert row["status"] == "ready_to_apply"
    assert row["target_tier"] == "L2"
    assert row["target_mode"] == "shadow_candidate"
    assert row["blockers"] == []
    assert packet["safety_invariants"]["order_created"] is False


def test_l2_tier_policy_review_detects_already_applied_btpc_l2():
    module = _load_module()

    packet = module.build_l2_tier_policy_review(
        l2_intake_packet=_l2_intake_packet(),
        tier_policy=_tier_policy(btpc_current=True),
    )

    assert packet["status"] == "l2_tier_policy_review_applied"
    assert packet["counts"]["already_applied_count"] == 1
    assert packet["decision"]["groups_already_l2"] == ["BTPC-001"]
    assert packet["operator_command_plan"]["changes_tier_policy"] is False


def test_l2_tier_policy_review_blocks_forbidden_source_effect():
    module = _load_module()

    packet = module.build_l2_tier_policy_review(
        l2_intake_packet=_l2_intake_packet(forbidden=True),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "source_l2_intake.safety.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["operator_command_plan"]["places_order"] is False


def test_l2_tier_policy_review_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    intake_path = tmp_path / "l2-intake.json"
    policy_path = tmp_path / "tier-policy.json"
    out_path = tmp_path / "tier-review.json"
    owner_path = tmp_path / "tier-review.md"
    _write_json(intake_path, _l2_intake_packet())
    _write_json(policy_path, _tier_policy())

    exit_code = module.main(
        [
            "--l2-intake-dry-run-json",
            str(intake_path),
            "--tier-policy-json",
            str(policy_path),
            "--output-json",
            str(out_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == "l2_tier_policy_review_recommended"
    assert "L2 Tier Policy Review" in owner_path.read_text(encoding="utf-8")
