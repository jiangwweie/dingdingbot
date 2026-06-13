from __future__ import annotations

import json

from scripts import runtime_live_attempt_readiness_packet as script


def _summary(
    runtime_id: str,
    *,
    status: str,
    blockers: list[str] | None = None,
    ready_for_prepare: bool = False,
    ready_for_final_gate_preflight: bool = False,
    symbol: str = "AVAX/USDT:USDT",
    side: str = "short",
) -> dict:
    return {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": symbol,
        "side": side,
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "ready_for_prepare": ready_for_prepare,
        "ready_for_final_gate_preflight": ready_for_final_gate_preflight,
        "blockers": blockers or [],
        "warnings": [],
        "signal_summary": {
            "evaluation_status": "observe_only",
            "signal_type": "no_action",
            "required_execution_mode": "observe_only",
            "side": "none",
            "confidence": "0.25",
            "reason_codes": ["no_ready_signal"],
            "human_summary": "No ready signal.",
        },
        "created_records": {
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
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _active_monitor_packet(
    summaries: list[dict],
    *,
    safety_overrides: dict | None = None,
    status: str = "blocked",
) -> dict:
    safety = {
        "uses_official_trading_console_api": True,
        "prepare_records_created": False,
        "shadow_candidate_created": False,
        "runtime_execution_intent_draft_created": False,
        "recorded_execution_intent_created": False,
        "submit_authorization_created": False,
        "protection_plan_created": False,
        "executable_execution_intent_created": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }
    safety.update(safety_overrides or {})
    blockers = []
    for item in summaries:
        for blocker in item.get("blockers") or []:
            blockers.append(f"{item['runtime_instance_id']}:{blocker}")
    return {
        "scope": "runtime_active_observation_monitor",
        "status": status,
        "active_runtime_count": len(summaries),
        "monitored_runtime_count": len(summaries),
        "selected_runtime_instance_ids": [
            item["runtime_instance_id"] for item in summaries
        ],
        "runtime_summaries": summaries,
        "blockers": blockers,
        "warnings": [],
        "safety_invariants": safety,
    }


def test_live_attempt_readiness_classifies_mixed_signal_and_runtime_gate_blockers():
    monitor = _active_monitor_packet(
        [
            _summary(
                "runtime-ada",
                status="waiting_for_signal",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
                symbol="ADA/USDT:USDT",
            ),
            _summary(
                "runtime-bnb",
                status="blocked",
                blockers=["next_attempt_gate_blocked"],
                symbol="BNB/USDT:USDT",
                side="long",
            ),
            _summary(
                "runtime-avax",
                status="waiting_for_signal",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            ),
        ]
    )

    packet = script.build_readiness_packet(
        active_monitor_packet=monitor,
        deployed_head="20843e89",
        release_name="release-rtf092",
        remote_report_path="/remote/reports/rtf094",
        health_json={"status": "ok", "runtime_bound": True, "live_ready": False},
    )

    assert packet["status"] == "live_attempt_blocked_by_runtime_or_signal_gate"
    assert packet["readiness_counts"]["waiting_signal_count"] == 2
    assert packet["readiness_counts"]["runtime_gate_blocked_count"] == 1
    assert packet["active_runtime_count"] == 3
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is True
    assert packet["safety_invariants"]["no_prepare_records_created_in_this_packet"] is True
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_exchange"] is False
    assert packet["operator_command_plan"][
        "uses_legacy_pre_attempt_rehearsal_as_primary_gate"
    ] is False
    assert packet["deployment_context"]["deployed_head"] == "20843e89"
    assert packet["deployment_context"]["live_ready"] is False


def test_live_attempt_readiness_waits_when_all_runtimes_wait_for_signal():
    monitor = _active_monitor_packet(
        [
            _summary(
                "runtime-ada",
                status="waiting_for_signal",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            ),
            _summary(
                "runtime-avax",
                status="waiting_for_signal",
                blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            ),
        ],
        status="waiting_for_signal",
    )

    packet = script.build_readiness_packet(active_monitor_packet=monitor)

    assert packet["status"] == "live_attempt_waiting_for_strategy_signal"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_live_read_only_observation_until_strategy_signal_ready"
    )


def test_live_attempt_readiness_reports_ready_for_prepare_review():
    monitor = _active_monitor_packet(
        [
            _summary(
                "runtime-ready",
                status="ready_for_prepare",
                ready_for_prepare=True,
                blockers=[],
            )
        ],
        status="ready_for_prepare",
    )

    packet = script.build_readiness_packet(active_monitor_packet=monitor)

    assert packet["status"] == "live_attempt_ready_for_prepare_review"
    assert packet["readiness_counts"]["ready_for_prepare_count"] == 1
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False


def test_live_attempt_readiness_blocks_forbidden_effects():
    monitor = _active_monitor_packet(
        [
            _summary(
                "runtime-ready",
                status="ready_for_final_gate_preflight",
                ready_for_final_gate_preflight=True,
            )
        ],
        safety_overrides={"exchange_write_called": True},
        status="ready_for_final_gate_preflight",
    )

    packet = script.build_readiness_packet(active_monitor_packet=monitor)

    assert packet["status"] == "live_attempt_blocked_forbidden_effect"
    assert packet["safety_invariants"]["forbidden_effects"][
        "exchange_write_called"
    ] is True
    assert packet["operator_command_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )


def test_live_attempt_readiness_cli_writes_json(tmp_path, capsys):
    monitor_path = tmp_path / "active-monitor.json"
    output_path = tmp_path / "readiness.json"
    monitor_path.write_text(
        json.dumps(
            _active_monitor_packet(
                [
                    _summary(
                        "runtime-avax",
                        status="waiting_for_signal",
                        blockers=[
                            "strategy_signal_not_ready_for_shadow_candidate_prepare"
                        ],
                    )
                ],
                status="waiting_for_signal",
            )
        ),
        encoding="utf-8",
    )

    assert script.main(
        [
            "--active-monitor-json",
            str(monitor_path),
            "--output-json",
            str(output_path),
            "--deployed-head",
            "20843e89",
        ]
    ) == 0

    captured = capsys.readouterr()
    stdout_packet = json.loads(captured.out)
    file_packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_packet["status"] == "live_attempt_waiting_for_strategy_signal"
    assert file_packet["deployment_context"]["deployed_head"] == "20843e89"
