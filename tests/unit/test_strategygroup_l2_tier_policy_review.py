from __future__ import annotations

from copy import deepcopy
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


def _l2_intake_artifact(*, forbidden: bool = False) -> dict:
    return {
        "status": "l2_intake_dry_run_passed",
        "review_outcome_state": {
            "groups_ready_for_l2_policy_review": ["BTPC-001"],
            "l4_scope_change_recommended": False,
            "tradeability_decision_source": False,
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

    artifact = module.build_l2_tier_policy_review(
        l2_intake_artifact=_l2_intake_artifact(),
        tier_policy=_tier_policy(),
    )

    assert artifact["status"] == "l2_tier_policy_review_recommended"
    assert artifact["counts"]["ready_to_apply_count"] == 1
    assert "decision" not in artifact
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["groups_ready_to_apply_l2"] == ["BTPC-001"]
    assert review_outcome["l4_scope_change_recommended"] is False
    assert review_outcome["tradeability_decision_source"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert "operator_command_plan" not in artifact
    row = artifact["review_rows"][0]
    assert row["status"] == "ready_to_apply"
    assert row["target_tier"] == "L2"
    assert row["target_mode"] == "shadow_candidate"
    assert row["blockers"] == []
    assert artifact["safety_invariants"]["order_created"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_l2_tier_policy_review_rejects_legacy_l2_intake_packet_kwarg():
    module = _load_module()

    try:
        module.build_l2_tier_policy_review(
            l2_intake_packet=_l2_intake_artifact(),
            tier_policy=_tier_policy(),
        )
    except TypeError as exc:
        assert "l2_intake_packet" in str(exc)
    else:
        raise AssertionError("legacy l2_intake_packet kwarg must be rejected")


def test_l2_tier_policy_review_detects_already_applied_btpc_l2():
    module = _load_module()

    artifact = module.build_l2_tier_policy_review(
        l2_intake_artifact=_l2_intake_artifact(),
        tier_policy=_tier_policy(btpc_current=True),
    )

    assert artifact["status"] == "l2_tier_policy_review_applied"
    assert artifact["counts"]["already_applied_count"] == 1
    assert "decision" not in artifact
    assert artifact["review_outcome_state"]["groups_already_l2"] == ["BTPC-001"]
    assert artifact["safety_invariants"]["tier_policy_changed"] is False


def test_l2_tier_policy_review_blocks_forbidden_source_effect():
    module = _load_module()

    artifact = module.build_l2_tier_policy_review(
        l2_intake_artifact=_l2_intake_artifact(forbidden=True),
        tier_policy=_tier_policy(),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert "source_l2_intake.safety.order_created" in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_l2_tier_policy_review_rejects_source_authority_mirrors():
    module = _load_module()
    intake = deepcopy(_l2_intake_artifact())
    intake["review_outcome_state"]["actionable_now"] = False
    intake["safety_invariants"]["real_order_authority"] = False
    intake["dry_run_rows"][0]["actionable_now"] = False

    artifact = module.build_l2_tier_policy_review(
        l2_intake_artifact=intake,
        tier_policy=_tier_policy(),
    )

    forbidden = artifact["safety_invariants"]["source_forbidden_effects"]
    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "source_l2_intake.review_outcome_state."
        "legacy_authority_mirror_present:actionable_now"
    ) in forbidden
    assert (
        "source_l2_intake.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in forbidden
    assert (
        "source_l2_intake.dry_run_rows.BTPC-001."
        "legacy_authority_mirror_present:actionable_now"
    ) in forbidden
    assert artifact["review_outcome_state"]["tradeability_decision_source"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["operation_layer_called"] is False


def test_l2_tier_policy_review_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    intake_path = tmp_path / "l2-intake.json"
    policy_path = tmp_path / "tier-policy.json"
    out_path = tmp_path / "tier-review.json"
    owner_path = tmp_path / "tier-review.md"
    _write_json(intake_path, _l2_intake_artifact())
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
