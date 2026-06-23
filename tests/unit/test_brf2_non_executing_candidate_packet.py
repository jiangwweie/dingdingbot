from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_non_executing_candidate_packet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_non_executing_candidate_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capture(*, fresh_signal_present: bool) -> dict:
    required_state = "satisfied" if fresh_signal_present else "missing"
    return {
        "status": "brf2_runtime_signal_capture_ready",
        "strategy_group_id": "BRF2-001",
        "watcher_scope": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
            "side_scope": ["short"],
        },
        "source_signal_context": {
            "signal_packet_id": "brf2-signal-001",
            "runtime_instance_id": "runtime-brf2-001",
            "symbol": "ADA/USDT:USDT",
            "timeframe": "5m_closed",
            "closed_at_utc": "2026-06-23T00:00:00+00:00",
            "source_strategy_group_id": "BRF-001",
            "source_candidate_id": "BRF-001-BTC-SHORT",
            "source_signal_type": "would_enter",
        },
        "fact_authority": "readonly_proxy_not_action_time_required_fact",
        "fact_authority_boundary": {
            "usable_for_armed_observation": True,
            "action_time_required_facts_satisfied": False,
            "usable_for_finalgate": False,
            "usable_for_operation_layer": False,
        },
        "signal_detector_preview": {
            "current_signal_state": (
                "fresh_signal_present"
                if fresh_signal_present
                else "fresh_signal_absent"
            ),
            "fresh_signal_present": fresh_signal_present,
            "first_blocker_class": (
                "brf2_fresh_short_signal_present_non_executing"
                if fresh_signal_present
                else "fresh_brf2_short_signal_absent"
            ),
            "first_blocker_owner": "runtime" if fresh_signal_present else "market",
            "next_action": (
                "build_brf2_non_executing_candidate_packet"
                if fresh_signal_present
                else "continue_brf2_armed_observation_until_fresh_signal"
            ),
            "required_fact_status": [
                {
                    "fact_key": "closed_1h_ohlcv",
                    "state": required_state,
                    "raw_state": "ready" if fresh_signal_present else "",
                    "fresh": fresh_signal_present,
                },
                {
                    "fact_key": "rally_failure_trigger_state",
                    "state": required_state,
                    "raw_state": "confirmed" if fresh_signal_present else "",
                    "fresh": fresh_signal_present,
                },
            ],
            "disable_fact_status": [
                {
                    "fact_key": "short_squeeze_risk_state",
                    "state": "clear",
                    "raw_state": "clear",
                    "fresh": True,
                },
            ],
        },
    }


def _missing_fact_input_capture() -> dict:
    packet = _capture(fresh_signal_present=False)
    packet["fact_input_present"] = False
    packet["watcher_tick_present"] = False
    packet["fact_input_status"] = "brf2_runtime_signal_facts_missing_watcher_input"
    packet["signal_detector_preview"] = {
        **packet["signal_detector_preview"],
        "current_signal_state": "fact_input_missing",
        "first_blocker_class": "brf2_watcher_fact_input_missing",
        "first_blocker_owner": "engineering",
        "next_action": "attach_brf2_watcher_fact_input_producer",
    }
    return packet


def test_brf2_candidate_packet_waits_without_fresh_signal():
    module = _load_module()

    packet = module.build_brf2_non_executing_candidate_packet(
        runtime_signal_capture=_capture(fresh_signal_present=False),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["schema"] == module.SCHEMA
    assert packet["status"] == module.WAITING_STATUS
    assert packet["candidate_packet_ready"] is False
    assert packet["candidate_packet"]["candidate_packet_id"] == ""
    assert packet["candidate_packet"]["source_signal_packet_id"] == "brf2-signal-001"
    assert packet["candidate_packet"]["symbol"] == "ADA/USDT:USDT"
    assert packet["first_blocker"]["class"] == "fresh_brf2_short_signal_absent"
    assert packet["first_blocker"]["owner"] == "market"
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["safety_invariants"]["authorization_evidence_created"] is False
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_brf2_candidate_packet_mirrors_missing_fact_input_blocker():
    module = _load_module()

    packet = module.build_brf2_non_executing_candidate_packet(
        runtime_signal_capture=_missing_fact_input_capture(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["status"] == module.WAITING_STATUS
    assert packet["candidate_packet_ready"] is False
    assert packet["candidate_packet"]["signal_state"] == "fact_input_missing"
    assert packet["first_blocker"]["class"] == "brf2_watcher_fact_input_missing"
    assert packet["first_blocker"]["owner"] == "engineering"
    assert packet["first_blocker"]["next_action"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False


def test_brf2_candidate_packet_ready_from_fresh_signal_without_authority():
    module = _load_module()

    packet = module.build_brf2_non_executing_candidate_packet(
        runtime_signal_capture=_capture(fresh_signal_present=True),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    candidate = packet["candidate_packet"]
    assert packet["status"] == module.READY_STATUS
    assert packet["candidate_packet_ready"] is True
    assert candidate["candidate_packet_id"] == "brf2-candidate:brf2-signal-001"
    assert candidate["symbol"] == "ADA/USDT:USDT"
    assert candidate["source_strategy_group_id"] == "BRF-001"
    assert candidate["source_candidate_id"] == "BRF-001-BTC-SHORT"
    assert candidate["source_signal_type"] == "would_enter"
    assert candidate["side"] == "short"
    assert candidate["fact_authority"] == "readonly_proxy_not_action_time_required_fact"
    assert candidate["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert packet["first_blocker"]["class"] == (
        "candidate_authorization_evidence_not_created"
    )
    assert packet["next_runtime_step"] == "prepare_fresh_candidate_authorization_evidence"
    assert "action_time_finalgate_packet_id" in candidate["required_next_chain"]
    assert "operation_layer_submit_authorization_id" in candidate["required_next_chain"]
    assert packet["checks"]["candidate_packet_ready"] is True
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["checks"]["action_time_required_facts_satisfied"] is False


def test_brf2_candidate_packet_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    capture_json = tmp_path / "capture.json"
    output_json = tmp_path / "candidate.json"
    output_md = tmp_path / "candidate.md"
    capture_json.write_text(
        json.dumps(_capture(fresh_signal_present=True)),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--runtime-signal-capture-json",
            str(capture_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == module.READY_STATUS
    assert packet["candidate_packet_ready"] is True
    assert "BRF2 Non-Executing Candidate Packet" in output_md.read_text(
        encoding="utf-8"
    )
