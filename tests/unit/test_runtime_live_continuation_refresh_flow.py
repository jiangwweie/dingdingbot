from __future__ import annotations

import json

from scripts import runtime_live_continuation_refresh_flow as script


def _runtime_summary(
    runtime_id: str,
    *,
    status: str = "waiting_for_signal",
    blockers: list[str] | None = None,
    ready_for_prepare: bool = False,
    ready_for_final_gate_preflight: bool = False,
    symbol: str = "AVAX/USDT:USDT",
    side: str = "short",
    family: str = "BTPC-001",
) -> dict:
    return {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": symbol,
        "side": side,
        "strategy_family_id": family,
        "strategy_family_version_id": f"{family}-v0",
        "ready_for_prepare": ready_for_prepare,
        "ready_for_final_gate_preflight": ready_for_final_gate_preflight,
        "blockers": blockers or [],
        "warnings": [],
        "signal_summary": {
            "evaluation_status": "observe_only",
            "signal_type": "no_action",
            "required_execution_mode": "observe_only",
            "confidence": "0.25",
            "reason_codes": ["no_ready_signal"],
            "human_summary": "No ready signal.",
        },
        "created_records": {
            "prepare_records_created": False,
            "shadow_candidate_created": False,
            "runtime_execution_intent_draft_created": False,
            "recorded_execution_intent_created": False,
            "submit_authorization_created": False,
            "protection_plan_created": False,
        },
        "forbidden_effects": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _active_monitor(*rows: dict, exchange_write_called: bool = False) -> dict:
    return {
        "scope": "runtime_active_observation_monitor",
        "status": "blocked",
        "active_runtime_count": len(rows),
        "monitored_runtime_count": len(rows),
        "selected_runtime_instance_ids": [row["runtime_instance_id"] for row in rows],
        "runtime_summaries": list(rows),
        "blockers": [
            f"{row['runtime_instance_id']}:{blocker}"
            for row in rows
            for blocker in row.get("blockers") or []
        ],
        "warnings": [],
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "exchange_write_called": exchange_write_called,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "execute_real_submit": False,
            "exchange_submit_armed": False,
            "local_registration_armed": False,
            "executable_execution_intent_created": False,
            "position_opened": False,
            "position_closed": False,
        },
    }


def _lifecycle_packet(**overrides) -> dict:
    packet = {
        "scope": "runtime_position_lifecycle_exit_readiness_artifact",
        "status": "position_lifecycle_hold_or_standing_recovery_ready",
        "runtime_instance_id": "runtime-bnb",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "position_lifecycle_plan": {
            "next_step": "continue_monitoring_or_prepare_official_reduce_only_recovery",
            "allows_new_attempt_now": False,
            "reduce_only_close_ready_for_owner_authorization": False,
            "reduce_only_recovery_ready_for_standing_authorization": True,
            "standing_recovery_authorization_scope": (
                "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
            ),
        },
        "safety_invariants": {
            "forbidden_effects": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "runtime_state_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "position_closed": False,
            }
        },
    }
    packet.update(overrides)
    return packet


def test_refresh_flow_builds_readiness_and_selector_for_current_mixed_state():
    refresh, readiness, selector = script.build_refresh_flow_artifacts(
        active_monitor_artifact=_active_monitor(
            _runtime_summary(
                "runtime-ada",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
                symbol="ADA/USDT:USDT",
                family="RBR-001",
            ),
            _runtime_summary(
                "runtime-bnb",
                status="blocked",
                blockers=["next_attempt_gate_blocked"],
                symbol="BNB/USDT:USDT",
                side="long",
                family="CPM-001",
            ),
            _runtime_summary(
                "runtime-avax",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            ),
        ),
        lifecycle_artifacts=[_lifecycle_packet()],
        deployed_head="6b671626",
    )

    assert refresh["status"] == "continuation_refresh_monitor_position_or_standing_recovery"
    assert readiness["status"] == "live_attempt_blocked_by_runtime_or_signal_gate"
    assert selector["status"] == "continuation_monitor_position_or_standing_recovery"
    assert refresh["selected_continuation"]["runtime_instance_id"] == "runtime-bnb"
    assert "operator_command_plan" not in refresh
    assert refresh["refresh_plan"]["not_execution_authority"] is True
    assert refresh["refresh_plan"]["execute_tiny_live_attempt_now"] is False
    assert refresh["refresh_plan"]["execute_reduce_only_close_now"] is False
    assert refresh["refresh_plan"]["ready_for_controlled_tiny_live_path"] is False
    assert refresh["safety_invariants"]["projection_only"] is True
    assert "packet_only" not in refresh["safety_invariants"]
    assert refresh["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_refresh_flow_marks_ready_for_final_gate_path():
    refresh, _, selector = script.build_refresh_flow_artifacts(
        active_monitor_artifact=_active_monitor(
            _runtime_summary(
                "runtime-ready",
                status="ready_for_final_gate_preflight",
                ready_for_final_gate_preflight=True,
                symbol="AVAX/USDT:USDT",
            )
        )
    )

    assert refresh["status"] == "continuation_refresh_ready_for_final_gate_review"
    assert selector["selected_continuation"]["selected_action"] == (
        "review_final_gate_preflight"
    )
    assert refresh["refresh_plan"]["ready_for_controlled_tiny_live_path"] is True
    assert refresh["refresh_plan"]["execute_tiny_live_attempt_now"] is False


def test_refresh_flow_blocks_forbidden_effects():
    refresh, _, _ = script.build_refresh_flow_artifacts(
        active_monitor_artifact=_active_monitor(
            _runtime_summary("runtime-avax"),
            exchange_write_called=True,
        )
    )

    assert refresh["status"] == "continuation_refresh_blocked_forbidden_effect"
    assert refresh["safety_invariants"]["no_forbidden_live_side_effects"] is False


def test_refresh_flow_cli_writes_all_artifacts(tmp_path, capsys):
    active_path = tmp_path / "active-monitor.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    output_dir = tmp_path / "out"
    output_json = tmp_path / "refresh.json"
    active_path.write_text(
        json.dumps(
            _active_monitor(
                _runtime_summary(
                    "runtime-bnb",
                    status="blocked",
                    blockers=["next_attempt_gate_blocked"],
                    symbol="BNB/USDT:USDT",
                    side="long",
                    family="CPM-001",
                )
            )
        ),
        encoding="utf-8",
    )
    lifecycle_path.write_text(json.dumps(_lifecycle_packet()), encoding="utf-8")

    assert script.main(
        [
            "--active-monitor-json",
            str(active_path),
            "--lifecycle-json",
            str(lifecycle_path),
            "--output-dir",
            str(output_dir),
            "--output-json",
            str(output_json),
            "--deployed-head",
            "6b671626",
        ]
    ) == 0

    stdout_artifact = json.loads(capsys.readouterr().out)
    assert stdout_artifact["status"] == "continuation_refresh_monitor_position_or_standing_recovery"
    assert json.loads(output_json.read_text(encoding="utf-8"))["deployment_context"][
        "deployed_head"
    ] == "6b671626"
    assert "operator_command_plan" not in stdout_artifact
    assert (output_dir / "live-attempt-readiness-artifact.json").exists()
    assert (output_dir / "live-continuation-selector-projection.json").exists()
    assert (output_dir / "live-continuation-refresh-flow.json").exists()
