from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_strategygroup_signal_coverage_diagnostic.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_signal_coverage_diagnostic",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _runtime_summary(*, ready: bool = False, forbidden: bool = False) -> dict:
    return {
        "status": "waiting_for_signal",
        "order_created": forbidden,
        "exchange_write_called": False,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-mpg",
                "strategy_family_id": "MPG-001",
                "strategy_family_version_id": "MPG-001-v0",
                "symbol": "MSTR/USDT:USDT",
                "side": "long",
                "status": "waiting_for_signal",
                "signal_summary": {
                    "signal_type": "would_enter" if ready else "no_action",
                    "confidence": "0.81" if ready else "0.25",
                    "reason_codes": (
                        ["mpg_momentum_confirmed"]
                        if ready
                        else ["mpg_no_action_momentum_persistence_not_confirmed"]
                    ),
                    "human_summary": "MPG summary",
                },
            },
            {
                "runtime_instance_id": "runtime-sor",
                "strategy_family_id": "SOR-001",
                "strategy_family_version_id": "SOR-001-v0",
                "symbol": "XAG/USDT:USDT",
                "side": "short",
                "status": "waiting_for_signal",
                "signal_type": "no_action",
                "confidence": "0.25",
                "reason_codes": ["sor_no_action_session_breakout_not_confirmed"],
                "human_summary": "SOR summary",
            },
        ],
    }


def _preview(*, would_enter: bool = True, forbidden: bool = False) -> dict:
    would_enter_rows = [
        {
            "candidate_id": "BTPC-001-AVAX-SHORT",
            "strategy_group_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
            "signal_type": "would_enter",
            "confidence": "0.62",
            "reason_codes": ["btpc_structure_loss_confirmed"],
            "human_summary": "BTPC would enter",
            "not_order": True,
            "not_execution_intent": True,
            "no_execution_permission": True,
            "no_order_permission": True,
            "no_runtime_start": True,
        }
    ] if would_enter else []
    no_action_rows = [
        {
            "candidate_id": "BRF-001-BTC",
            "strategy_group_id": "BRF-001",
            "strategy_family_version_id": "BRF-001-v0",
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "signal_type": "no_action",
            "confidence": "0.20",
            "reason_codes": ["brf_no_action_no_rejection_close"],
            "human_summary": "BRF no action",
        }
    ]
    return {
        "status": "preview_built",
        "market_source": "sample_strategy_group_market_bar_source_v1",
        "checks": {
            "candidate_count": 2,
            "current_signal_count": len(would_enter_rows) + len(no_action_rows),
            "would_enter_signal_count": len(would_enter_rows),
            "no_action_signal_count": len(no_action_rows),
            "invalid_signal_count": 0,
            "forbidden_effects": [],
        },
        "would_enter_signals": would_enter_rows,
        "no_action_signals": no_action_rows,
        "invalid_signals": [],
        "operator_command_plan": {
            "places_order": forbidden,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "database_connected": False,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_started": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_diagnostic_surfaces_broader_would_enter_without_execution_authority():
    module = _load_module()

    packet = module.build_signal_coverage_diagnostic_packet(
        runtime_summary_packet=_runtime_summary(),
        broader_preview_packet=_preview(would_enter=True),
        source_name="sample",
    )

    assert packet["status"] == "mainline_no_signal_broader_would_enter"
    assert packet["owner_state"] == "coverage_review_needed"
    assert packet["checks"]["runtime_ready_signal_count"] == 0
    assert packet["checks"]["broader_would_enter_signal_count"] == 1
    assert packet["checks"]["coverage_gap"] is True
    assert packet["diagnosis"]["broader_signals_are_observe_only"] is True
    assert packet["diagnosis"]["does_not_authorize_real_order"] is True
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_final_gate"] is False
    assert packet["operator_command_plan"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"][
        "broader_signals_are_not_execution_authority"
    ] is True


def test_diagnostic_reports_waiting_when_mainline_and_broader_have_no_signal():
    module = _load_module()

    packet = module.build_signal_coverage_diagnostic_packet(
        runtime_summary_packet=_runtime_summary(),
        broader_preview_packet=_preview(would_enter=False),
        source_name="sample",
    )

    assert packet["status"] == "mainline_and_broader_no_signal"
    assert packet["owner_state"] == "waiting_for_opportunity"
    assert packet["checks"]["coverage_gap"] is False
    assert packet["diagnosis"]["mainline_runtime_is_waiting"] is True
    assert packet["diagnosis"]["broader_observation_has_would_enter"] is False


def test_diagnostic_defers_to_mainline_ready_signal():
    module = _load_module()

    packet = module.build_signal_coverage_diagnostic_packet(
        runtime_summary_packet=_runtime_summary(ready=True),
        broader_preview_packet=_preview(would_enter=True),
        source_name="sample",
    )

    assert packet["status"] == "mainline_runtime_signal_ready"
    assert packet["owner_state"] == "processing"
    assert packet["checks"]["runtime_ready_signal_count"] == 1
    assert packet["diagnosis"]["next_step"] == (
        "pause_lower_priority_work_and_continue_official_runtime_chain"
    )


def test_diagnostic_blocks_forbidden_source_effects():
    module = _load_module()

    packet = module.build_signal_coverage_diagnostic_packet(
        runtime_summary_packet=_runtime_summary(forbidden=True),
        broader_preview_packet=_preview(would_enter=True, forbidden=True),
        source_name="sample",
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["operator_command_plan"]["places_order"] is False
    assert "runtime.order_created" in packet["checks"]["forbidden_effects"]
    assert "preview.command_plan.places_order" in packet["checks"][
        "forbidden_effects"
    ]


def test_cli_writes_packet_and_owner_progress(tmp_path, capsys):
    module = _load_module()
    runtime_path = tmp_path / "runtime.json"
    preview_path = tmp_path / "preview.json"
    output_path = tmp_path / "diagnostic.json"
    owner_path = tmp_path / "owner.md"
    runtime_path.write_text(json.dumps(_runtime_summary()), encoding="utf-8")
    preview_path.write_text(json.dumps(_preview(would_enter=True)), encoding="utf-8")

    exit_code = module.main(
        [
            "--runtime-summary-json",
            str(runtime_path),
            "--broader-preview-json",
            str(preview_path),
            "--source",
            "sample",
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "strategygroup_signal_coverage_diagnostic"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "策略机会覆盖诊断" in owner_text
    assert "宽观察 Would-Enter 信号" in owner_text
    assert "当前判断" in owner_text
