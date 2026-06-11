from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_no_signal_diagnostic_packet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_no_signal_diagnostic_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watch_packet(*, status="watching_no_signal", forbidden=False, ready=False):
    return {
        "status": "runtime_signal_ready" if ready else status,
        "active_runtime_observation": {
            "active_runtime_count": 2,
            "latest_iteration": 3,
            "iterations_completed": 3,
            "iterations_remaining": 84,
            "iterations_requested": 87,
            "stop_reason": "running",
            "packet_stale": False,
        },
        "checks": {
            "runtime_ready_signal_count": 1 if ready else 0,
            "strategy_group_would_enter_signal_count": 0,
            "strategy_group_no_action_signal_count": 2,
            "forbidden_effects": ["packet_0.order_created"] if forbidden else [],
        },
        "runtime_signals": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "CPM-001",
                "symbol": "BNB/USDT:USDT",
                "reason_codes": ["cpm_no_action_no_reclaim"],
            },
            {
                "runtime_instance_id": "runtime-2",
                "strategy_family_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "reason_codes": ["btpc_no_action_no_bear_pullback_continuation"],
            },
        ],
        "runtime_ready_signals": [
            {
                "runtime_instance_id": "runtime-ready",
                "strategy_family_id": "BTPC-001",
                "symbol": "AVAX/USDT:USDT",
                "reason_codes": ["btpc_ready"],
            }
        ]
        if ready
        else [],
        "strategy_group_no_action_signals": [
            {
                "strategy_group_id": "CPM-001",
                "symbol": "BNB/USDT:USDT",
                "reason_codes": ["cpm_no_action_no_reclaim"],
            },
            {
                "strategy_group_id": "RBR-001",
                "symbol": "ADA/USDT:USDT",
                "reason_codes": ["rbr_no_action_not_at_range_boundary"],
            },
            {
                "strategy_group_id": "VCB-001",
                "symbol": "LINK/USDT:USDT",
                "reason_codes": ["vcb_no_action_no_compression_breakout"],
            },
        ],
        "strategy_group_would_enter_signals": [],
        "safety_invariants": {
            "read_packets_only": True,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": [],
        },
    }


def test_no_signal_diagnostic_summarizes_running_window():
    module = _load_module()

    packet = module.build_no_signal_diagnostic_packet(_watch_packet())

    assert packet["status"] == "no_signal_observation_running"
    assert packet["signal_counts"]["runtime_ready_signal_count"] == 0
    assert packet["coverage"]["active_runtime_strategy_families"] == [
        "BTPC-001",
        "CPM-001",
    ]
    assert packet["coverage"]["active_runtime_count_less_than_preview_family_count"] is True
    assert packet["no_action_diagnostics"]["runtime_reason_counts"] == {
        "btpc_no_action_no_bear_pullback_continuation": 1,
        "cpm_no_action_no_reclaim": 1,
    }
    assert packet["operator_command_plan"]["allowed_next_actions"] == [
        "continue_active_runtime_observation"
    ]
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["owner_gate"]["diagnostic_only"] is True
    assert packet["right_tail_objective_context"]["no_signal_is_not_failure"] is True


def test_no_signal_diagnostic_surfaces_ready_signal_as_not_no_signal():
    module = _load_module()

    packet = module.build_no_signal_diagnostic_packet(_watch_packet(ready=True))

    assert packet["status"] == "runtime_signal_ready_not_no_signal"
    assert packet["operator_command_plan"]["next_step"] == (
        "review_runtime_ready_signal_prepare_path"
    )
    assert packet["safety_invariants"]["order_created"] is False


def test_no_signal_diagnostic_blocks_forbidden_source_packet():
    module = _load_module()

    packet = module.build_no_signal_diagnostic_packet(_watch_packet(forbidden=True))

    assert packet["status"] == "blocked_forbidden_effect"
    assert "packet_0.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert "safety.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_no_signal_diagnostic_cli_reads_and_writes_json(tmp_path, capsys):
    module = _load_module()
    watch_path = tmp_path / "watch.json"
    output_path = tmp_path / "diagnostic.json"
    watch_path.write_text(json.dumps(_watch_packet()), encoding="utf-8")

    exit_code = module.main(
        [
            "--watch-packet-json",
            str(watch_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_no_signal_diagnostic_packet"
