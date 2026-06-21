from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_strategygroup_l2_intake_dry_run.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_l2_intake_dry_run",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _l2_packet() -> dict:
    return {
        "status": "l2_readiness_review_has_conditional_candidate",
        "readiness_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "conditional_l2_review_candidate": True,
                "may_create_shadow_candidate_now": False,
                "may_place_real_order_now": False,
            }
        ],
        "safety_invariants": {
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _handoff() -> dict:
    return {
        "strategy_group_id": "BTPC-001",
        "supported_symbols": ["AVAXUSDT"],
        "supported_sides": ["short"],
        "mode_recommendation": {"default": "observe_only"},
        "signal_ready_rule": {"status_name": "would_enter_observe_only"},
        "required_facts": {
            "account": ["available_balance"],
            "derivatives": ["short_squeeze_risk"],
            "exchange": ["symbol_availability"],
            "market": ["latest_price"],
            "risk": ["real_exchange_margin_liquidation_model"],
            "strategy": ["bear_trend_context"],
        },
        "risk_defaults": {
            "risk_tier": "not_live_order_eligible",
            "max_notional_per_action_usdt": "0",
            "max_active_positions": 0,
        },
        "hard_stops": ["short_squeeze_risk_unbounded"],
        "execution_boundary": {
            "research_handoff_only": True,
            "runtime_registration_authorized": False,
            "candidate_creation_authorized": False,
            "final_gate_input": False,
            "operation_layer_input": False,
            "real_submit_authorized": False,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_l2_intake_dry_run_passes_for_btpc_observe_only_handoff(tmp_path):
    module = _load_module()
    handoff_root = tmp_path / "handoffs"
    _write_json(handoff_root / "BTPC-001" / "handoff.json", _handoff())

    packet = module.build_l2_intake_dry_run(
        l2_readiness_packet=_l2_packet(),
        handoff_root=handoff_root,
    )

    assert packet["status"] == "l2_intake_dry_run_passed"
    assert packet["counts"] == {
        "candidate_count": 1,
        "failed_count": 0,
        "forbidden_effect_count": 0,
        "passed_count": 1,
        "source_blocked_count": 0,
        "source_conditional_candidate_count": 1,
        "source_enabled_l2_count": 0,
        "source_readiness_row_count": 1,
    }
    row = packet["dry_run_rows"][0]
    assert row["strategy_group_id"] == "BTPC-001"
    assert row["status"] == "passed"
    assert row["blockers"] == []
    assert packet["decision"]["tier_policy_change_ready_for_review"] is True
    assert packet["decision"]["no_candidate_reason"] is None
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["safety_invariants"]["tier_policy_changed"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_l2_intake_dry_run_fails_when_handoff_missing(tmp_path):
    module = _load_module()

    packet = module.build_l2_intake_dry_run(
        l2_readiness_packet=_l2_packet(),
        handoff_root=tmp_path / "missing-handoffs",
    )

    assert packet["status"] == "l2_intake_dry_run_failed"
    assert packet["counts"]["failed_count"] == 1
    assert "handoff_json_missing" in packet["dry_run_rows"][0]["blockers"]
    assert packet["operator_command_plan"]["places_order"] is False


def test_l2_intake_dry_run_explains_no_candidates_from_source_rows(tmp_path):
    module = _load_module()
    l2_packet = _l2_packet()
    l2_packet["status"] = "l2_readiness_review_already_enabled"
    l2_packet["readiness_rows"] = [
        {
            "strategy_group_id": "BTPC-001",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
            "current_tier": "L2",
            "l2_readiness": "l2_shadow_candidate_observation_enabled",
            "recommended_action": (
                "continue_l2_shadow_candidate_observation_without_l4_scope_change"
            ),
            "blocking_gaps_before_l2": [],
            "conditional_l2_review_candidate": False,
            "l2_shadow_candidate_observation_enabled": True,
            "may_create_shadow_candidate_now": False,
            "may_place_real_order_now": False,
        },
        {
            "strategy_group_id": "VCB-001",
            "symbol": "LINK/USDT:USDT",
            "side": "long",
            "current_tier": "L1",
            "l2_readiness": "blocked_classifier_redesign_required",
            "recommended_action": (
                "keep_l1_observe_only_until_false_breakout_disable_and_pre_entry_classifier_are_redesigned"
            ),
            "blocking_gaps_before_l2": ["false_breakout_disable_state_missing"],
            "conditional_l2_review_candidate": False,
            "l2_shadow_candidate_observation_enabled": False,
            "may_create_shadow_candidate_now": False,
            "may_place_real_order_now": False,
        },
    ]

    packet = module.build_l2_intake_dry_run(
        l2_readiness_packet=l2_packet,
        handoff_root=tmp_path / "handoffs",
    )

    assert packet["status"] == "l2_intake_dry_run_no_candidates"
    assert packet["counts"]["candidate_count"] == 0
    assert packet["counts"]["source_enabled_l2_count"] == 1
    assert packet["counts"]["source_blocked_count"] == 1
    assert packet["decision"]["no_candidate_reason"] == (
        "no_conditional_l2_review_candidates"
    )
    assert packet["decision"]["enabled_l2_groups"] == ["BTPC-001"]
    assert packet["decision"]["blocked_groups"] == ["VCB-001"]
    source_rows = {row["strategy_group_id"]: row for row in packet["source_readiness_rows"]}
    assert source_rows["BTPC-001"]["l2_shadow_candidate_observation_enabled"] is True
    assert source_rows["VCB-001"]["blocking_gaps_before_l2"] == [
        "false_breakout_disable_state_missing"
    ]
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["safety_invariants"]["order_created"] is False


def test_l2_intake_dry_run_blocks_forbidden_source_effect(tmp_path):
    module = _load_module()
    handoff_root = tmp_path / "handoffs"
    _write_json(handoff_root / "BTPC-001" / "handoff.json", _handoff())
    l2_packet = _l2_packet()
    l2_packet["safety_invariants"]["order_created"] = True

    packet = module.build_l2_intake_dry_run(
        l2_readiness_packet=l2_packet,
        handoff_root=handoff_root,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "source_l2_readiness.safety.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["operator_command_plan"]["calls_operation_layer"] is False


def test_l2_intake_dry_run_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    handoff_root = tmp_path / "handoffs"
    _write_json(handoff_root / "BTPC-001" / "handoff.json", _handoff())
    l2_path = tmp_path / "l2.json"
    out_path = tmp_path / "dry-run.json"
    owner_path = tmp_path / "dry-run.md"
    _write_json(l2_path, _l2_packet())

    exit_code = module.main(
        [
            "--l2-readiness-json",
            str(l2_path),
            "--handoff-root",
            str(handoff_root),
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
    assert file_payload["status"] == "l2_intake_dry_run_passed"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "L2 Intake Dry-Run" in owner_text
    assert "Source Readiness Rows" in owner_text
    assert "conditional_l2_candidate" in owner_text
