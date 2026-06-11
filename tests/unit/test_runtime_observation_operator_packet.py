from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_observation_operator_packet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_observation_operator_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _status_packet(*, status="waiting_for_signal", signal_type="no_action"):
    return {
        "status": status,
        "latest_status": status,
        "latest_iteration": 2,
        "iterations_completed": 2,
        "iterations_requested": 87,
        "iterations_remaining": 85,
        "packet_stale": False,
        "stop_reason": "running",
        "active_runtime_count": 1,
        "prepared_authorization_id": None,
        "shadow_candidate_id": None,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "status": status,
                "evaluation_status": "observe_only",
                "signal_type": signal_type,
                "signal_side": "none",
                "confidence": "0.25",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
                "human_summary": "No BTPC action.",
            }
        ],
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "creates_execution_intent": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _strategy_preview(*, would_enter=False, forbidden=False):
    return {
        "status": "preview_built",
        "source_requested": "sample",
        "market_source": "sample_source",
        "checks": {
            "candidate_count": 1,
            "current_signal_count": 1,
            "would_enter_signal_count": 1 if would_enter else 0,
            "no_action_signal_count": 0 if would_enter else 1,
            "forbidden_effects": [],
        },
        "would_enter_signals": [
            {
                "candidate_id": "BRF-001-BTC-SHORT",
                "strategy_group_id": "BRF-001",
                "strategy_family_version_id": "BRF-001-v0",
                "symbol": "BTC/USDT:USDT",
                "side": "short",
                "signal_type": "would_enter",
                "confidence": "0.65",
                "reason_codes": ["brf_rejection_close"],
                "human_summary": "BRF would enter.",
                "not_order": True,
                "not_execution_intent": True,
                "no_execution_permission": True,
                "no_order_permission": True,
                "no_runtime_start": True,
            }
        ]
        if would_enter
        else [],
        "no_action_signals": []
        if would_enter
        else [
            {
                "candidate_id": "BTPC-001-AVAX-SHORT",
                "strategy_group_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
                "side": "none",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
                "human_summary": "No BTPC action.",
                "not_order": True,
                "not_execution_intent": True,
                "no_execution_permission": True,
                "no_order_permission": True,
                "no_runtime_start": True,
            }
        ],
        "safety_invariants": {
            "preview_only": True,
            "pg_observation_written": False,
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
        },
    }


def test_operator_packet_summarizes_no_signal_without_execution():
    module = _load_module()

    packet = module.build_operator_packet(
        active_status_packet=_status_packet(),
        strategy_preview_packet=_strategy_preview(),
    )

    assert packet["status"] == "observation_running_no_signal"
    assert packet["watch_status"] == "watching_no_signal"
    assert packet["diagnostic_status"] == "no_signal_observation_running"
    assert packet["signal_counts"]["runtime_ready_signal_count"] == 0
    assert packet["operator_command_plan"]["allowed_next_actions"] == [
        "continue_active_runtime_observation"
    ]
    assert packet["operator_command_plan"]["creates_execution_intent"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["owner_gate"]["operator_review_only"] is True


def test_operator_packet_surfaces_runtime_ready_attention():
    module = _load_module()

    packet = module.build_operator_packet(
        active_status_packet=_status_packet(
            status="ready_for_prepare",
            signal_type="would_enter",
        ),
        strategy_preview_packet=_strategy_preview(),
    )

    assert packet["status"] == "runtime_signal_attention"
    assert packet["watch_status"] == "runtime_signal_ready"
    assert packet["operator_command_plan"]["next_step"] == (
        "review_runtime_ready_signal_prepare_or_preview_path"
    )
    assert packet["operator_command_plan"]["places_order"] is False


def test_operator_packet_blocks_forbidden_preview_effect():
    module = _load_module()

    packet = module.build_operator_packet(
        active_status_packet=_status_packet(),
        strategy_preview_packet=_strategy_preview(forbidden=True),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "packet_0.packet_1.order_created" in packet["safety_invariants"][
        "forbidden_effects"
    ]
    assert packet["operator_command_plan"]["calls_order_lifecycle"] is False


def test_operator_packet_cli_reads_status_and_writes_json(monkeypatch, tmp_path, capsys):
    module = _load_module()
    status_path = tmp_path / "status.json"
    output_path = tmp_path / "operator.json"
    status_path.write_text(json.dumps(_status_packet()), encoding="utf-8")
    monkeypatch.setattr(
        module,
        "build_preview_packet",
        lambda source_name: _strategy_preview(),
    )

    exit_code = module.main(
        [
            "--status-packet-json",
            str(status_path),
            "--strategy-source",
            "sample",
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_observation_operator_packet"
