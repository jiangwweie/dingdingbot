from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_strategy_signal_watch_packet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_strategy_signal_watch_packet",
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
        "latest_iteration": 6,
        "iterations_completed": 6,
        "packet_stale": False,
        "stop_reason": "running",
        "active_runtime_count": 1,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "CPM-001",
                "strategy_family_version_id": "CPM-001-v0",
                "symbol": "BNB/USDT:USDT",
                "side": "long",
                "status": status,
                "evaluation_status": "observe_only",
                "signal_type": signal_type,
                "signal_side": "none",
                "confidence": "0.25",
                "reason_codes": ["cpm_no_action_no_reclaim"],
                "human_summary": "No CPM action.",
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
                "candidate_id": "CPM-RO-001",
                "strategy_group_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["cpm_no_action_no_reclaim"],
                "human_summary": "No CPM action.",
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


def test_watch_packet_summarizes_waiting_no_signal():
    module = _load_module()

    packet = module.build_watch_packet(
        active_status_packet=_status_packet(),
        strategy_preview_packet=_strategy_preview(),
    )

    assert packet["status"] == "watching_no_signal"
    assert packet["checks"]["runtime_ready_signal_count"] == 0
    assert packet["checks"]["strategy_group_would_enter_signal_count"] == 0
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_active_runtime_observation"
    )
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["execution_intent_created"] is False


def test_watch_packet_surfaces_strategy_group_would_enter_without_execution():
    module = _load_module()

    packet = module.build_watch_packet(
        active_status_packet=_status_packet(),
        strategy_preview_packet=_strategy_preview(would_enter=True),
    )

    assert packet["status"] == "strategy_group_signal_review_available"
    assert packet["checks"]["strategy_group_would_enter_signal_count"] == 1
    assert packet["operator_command_plan"]["next_step"] == (
        "review_would_enter_strategy_group_without_execution"
    )
    assert packet["strategy_group_would_enter_signals"][0]["not_order"] is True
    assert packet["operator_command_plan"]["places_order"] is False


def test_watch_packet_blocks_forbidden_effects():
    module = _load_module()

    packet = module.build_watch_packet(
        active_status_packet=_status_packet(),
        strategy_preview_packet=_strategy_preview(forbidden=True),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["checks"]["forbidden_effects"] == ["packet_1.order_created"]
    assert packet["operator_command_plan"]["next_step"] == (
        "resolve_signal_watch_forbidden_effects"
    )


def test_watch_packet_cli_reads_status_file(tmp_path, capsys):
    module = _load_module()
    status_path = tmp_path / "status.json"
    output_path = tmp_path / "watch.json"
    status_path.write_text(json.dumps(_status_packet()), encoding="utf-8")

    code = module.main(
        [
            "--status-packet-json",
            str(status_path),
            "--strategy-source",
            "sample",
            "--output-json",
            str(output_path),
        ]
    )

    assert code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_strategy_signal_watch_packet"
    assert file_payload["safety_invariants"]["pg_observation_written"] is False
