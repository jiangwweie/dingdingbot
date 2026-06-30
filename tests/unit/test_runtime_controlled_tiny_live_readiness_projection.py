from __future__ import annotations

import json

from scripts import runtime_controlled_tiny_live_readiness_projection as script


def _selected(
    *,
    ready_for_prepare: bool = False,
    ready_for_final_gate_preflight: bool = False,
    runtime_id: str = "runtime-avax",
) -> dict:
    return {
        "runtime_instance_id": runtime_id,
        "selected_action": "prepare_shadow_candidate",
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "ready_for_prepare": ready_for_prepare,
        "ready_for_final_gate_preflight": ready_for_final_gate_preflight,
        "blockers": [],
        "warnings": [],
    }


def _refresh(
    *,
    status: str = "continuation_refresh_monitor_position_or_standing_recovery",
    selected: dict | None = None,
    forbidden: bool = False,
) -> dict:
    return {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": status,
        "readiness_status": "live_attempt_blocked_by_runtime_or_signal_gate",
        "selector_status": "continuation_monitor_position_or_standing_recovery",
        "active_runtime_count": 3,
        "selected_continuation": selected
        or {
            "runtime_instance_id": "runtime-bnb",
            "selected_action": "monitor_position_or_prepare_official_reduce_only_recovery",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "strategy_family_id": "CPM-001",
            "strategy_family_version_id": "CPM-001-v0",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
        },
        "blockers": ["runtime-bnb:next_attempt_gate_blocked"],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "safety_invariants": {
            "packet_only": True,
            "forbidden_effects": {
                "exchange_write_called": forbidden,
                "order_created": False,
                "order_lifecycle_called": False,
                "runtime_state_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "position_closed": False,
                "execute_real_submit": False,
                "exchange_submit_armed": False,
                "local_registration_armed": False,
                "executable_execution_intent_created": False,
            },
        },
        "refresh_plan": {
            "ready_for_controlled_tiny_live_path": status
            in {
                "continuation_refresh_ready_for_prepare",
                "continuation_refresh_ready_for_final_gate_review",
            },
            "execute_tiny_live_attempt_now": False,
            "execute_reduce_only_close_now": False,
        },
    }


def test_projection_waits_for_ready_selector_without_execution_authority():
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(),
        deployed_head="b1009096",
        release_name="brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow",
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_waiting_for_ready_selector"
    )
    assert projection["blockers"] == [
        "continuation_refresh_monitor_position_or_standing_recovery"
    ]
    assert projection["readiness_inputs"]["ready_for_prepare"] is False
    assert projection["readiness_inputs"]["ready_for_final_gate_preflight"] is False
    assert "operator_command_plan" not in projection
    assert projection["readiness_plan"]["not_execution_authority"] is True
    assert projection["readiness_plan"]["next_step"] == (
        "continue_selector_refresh_until_ready"
    )
    assert projection["readiness_plan"]["execute_tiny_live_attempt_now"] is False
    assert projection["readiness_plan"]["places_order"] is False
    assert projection["readiness_plan"]["calls_exchange"] is False
    assert projection["safety_invariants"]["projection_only"] is True
    assert "packet_only" not in projection["safety_invariants"]
    assert projection["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_projection_marks_official_prepare_ready_only_from_prepare_refresh_status():
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(ready_for_prepare=True),
        )
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_ready_for_official_prepare"
    )
    assert projection["blockers"] == []
    assert projection["readiness_plan"]["next_step"] == (
        "run_official_prepare_then_final_gate_preflight"
    )
    assert projection["readiness_plan"]["creates_shadow_candidate"] is False
    assert projection["right_tail_objective_context"][
        "new_attempt_not_started_by_projection"
    ]


def test_projection_marks_final_gate_ready_only_from_final_gate_refresh_status():
    selected = _selected(ready_for_final_gate_preflight=True)
    selected["selected_action"] = "review_final_gate_preflight"
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(
            status="continuation_refresh_ready_for_final_gate_review",
            selected=selected,
        )
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_ready_for_final_gate_review"
    )
    assert projection["readiness_plan"]["next_step"] == (
        "run_official_final_gate_preflight_before_controlled_tiny_live_submit"
    )
    assert projection["readiness_plan"]["requires_fresh_final_gate_before_submit"]
    assert projection["readiness_plan"]["calls_order_lifecycle"] is False


def test_projection_blocks_forbidden_effects_in_source_refresh():
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(forbidden=True)
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_blocked_forbidden_effect"
    )
    assert projection["blockers"] == ["forbidden_live_side_effect_detected"]
    assert projection["readiness_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )
    assert projection["safety_invariants"]["no_forbidden_live_side_effects"] is False


def test_projection_blocks_inconsistent_ready_status_and_selected_flags():
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(ready_for_prepare=False),
        )
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_blocked_inconsistent_selector"
    )
    assert projection["blockers"] == [
        "selector_ready_status_without_matching_selected_flags"
    ]
    assert (
        projection["readiness_plan"]["next_step"]
        == "refresh_selector_before_readiness_projection"
    )


def test_projection_blocks_mismatched_prepare_and_final_gate_flags():
    projection = script.build_readiness_projection(
        refresh_artifact=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(
                ready_for_prepare=False,
                ready_for_final_gate_preflight=True,
            ),
        )
    )

    assert (
        projection["status"]
        == "controlled_tiny_live_readiness_projection_blocked_inconsistent_selector"
    )


def test_projection_cli_writes_json_and_returns_zero_for_waiting(tmp_path, capsys):
    refresh_path = tmp_path / "refresh.json"
    output_path = tmp_path / "readiness-projection.json"
    refresh_path.write_text(json.dumps(_refresh()), encoding="utf-8")

    assert script.main(
        [
            "--refresh-json",
            str(refresh_path),
            "--deployed-head",
            "b1009096",
            "--release-name",
            "brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow",
            "--remote-report-path",
            "/home/ubuntu/brc-deploy/reports/rtf099",
            "--output-json",
            str(output_path),
        ]
    ) == 0

    stdout_projection = json.loads(capsys.readouterr().out)
    file_projection = json.loads(output_path.read_text(encoding="utf-8"))
    assert (
        stdout_projection["status"]
        == "controlled_tiny_live_readiness_projection_waiting_for_ready_selector"
    )
    assert file_projection["deployment_context"]["deployed_head"] == "b1009096"
    assert "operator_command_plan" not in file_projection
    assert file_projection["readiness_plan"]["execute_tiny_live_attempt_now"] is False
