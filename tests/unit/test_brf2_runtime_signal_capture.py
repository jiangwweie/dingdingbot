from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_runtime_signal_capture.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_runtime_signal_capture",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mapping() -> dict:
    return {
        "status": "brf2_required_facts_mapping_ready",
        "required_facts_mapping_ready": True,
        "fresh_signal_rule": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
            "side": "short",
            "timeframes": ["1h_closed", "5m_closed"],
            "freshness_window_ms": 300000,
        },
        "required_fact_keys": [
            "closed_1h_ohlcv",
            "closed_5m_ohlcv",
            "rally_context",
            "rally_failure_trigger_state",
            "short_squeeze_risk_state",
            "strong_reclaim_disable_state",
            "liquidity_downshift_state",
            "spread_liquidity_state",
        ],
        "disable_fact_keys": [
            "short_squeeze_risk_state",
            "strong_reclaim_disable_state",
            "rally_extension_invalidates_failure_state",
            "liquidity_downshift_state",
            "spread_liquidity_state",
        ],
    }


def _owner_policy() -> dict:
    return {
        "policy": {
            "strategy_group_id": "BRF2-001",
            "symbol_scope": "brf2_research_supported_symbols_only",
            "side_scope": ["short"],
        }
    }


def _fresh_facts() -> dict:
    return {
        "facts": {
            "closed_1h_ohlcv": {"status": "ready"},
            "closed_5m_ohlcv": {"status": "ready"},
            "rally_context": {"status": "bear_or_weak_reclaim"},
            "rally_failure_trigger_state": {"status": "confirmed"},
            "short_squeeze_risk_state": {"status": "clear"},
            "strong_reclaim_disable_state": {"status": "false"},
            "rally_extension_invalidates_failure_state": {"status": "false"},
            "liquidity_downshift_state": {"status": "false"},
            "spread_liquidity_state": {"status": "acceptable"},
        }
    }


def test_brf2_runtime_signal_capture_waits_without_fact_input():
    module = _load_module()

    packet = module.build_brf2_runtime_signal_capture(
        required_facts_mapping=_mapping(),
        owner_policy=_owner_policy(),
        fact_input={},
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["schema"] == module.SCHEMA
    assert packet["status"] == "brf2_runtime_signal_capture_ready"
    preview = packet["signal_detector_preview"]
    assert preview["current_signal_state"] == "fresh_signal_absent"
    assert preview["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert preview["fresh_signal_present"] is False
    assert len(preview["missing_required_fact_keys"]) == 8
    assert packet["candidate_packet_shape"]["candidate_packet_ready"] is False
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_brf2_runtime_signal_capture_builds_non_executing_candidate_shape():
    module = _load_module()

    packet = module.build_brf2_runtime_signal_capture(
        required_facts_mapping=_mapping(),
        owner_policy=_owner_policy(),
        fact_input=_fresh_facts(),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    preview = packet["signal_detector_preview"]
    candidate = packet["candidate_packet_shape"]
    assert preview["current_signal_state"] == "fresh_signal_present"
    assert preview["fresh_signal_present"] is True
    assert preview["missing_required_fact_keys"] == []
    assert preview["active_disable_fact_keys"] == []
    assert candidate["candidate_packet_ready"] is True
    assert candidate["candidate_packet_type"] == (
        "brf2_non_executing_short_signal_candidate"
    )
    assert "action_time_finalgate_packet_id" in candidate["required_next_chain"]
    assert "operation_layer_submit_authorization_id" in candidate["required_next_chain"]
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False


def test_brf2_runtime_signal_capture_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    mapping_json = tmp_path / "mapping.json"
    policy_json = tmp_path / "policy.json"
    fact_json = tmp_path / "facts.json"
    output_json = tmp_path / "capture.json"
    output_md = tmp_path / "capture.md"
    mapping_json.write_text(json.dumps(_mapping()), encoding="utf-8")
    policy_json.write_text(json.dumps(_owner_policy()), encoding="utf-8")
    fact_json.write_text(json.dumps(_fresh_facts()), encoding="utf-8")

    exit_code = module.main(
        [
            "--required-facts-mapping-json",
            str(mapping_json),
            "--owner-policy-json",
            str(policy_json),
            "--fact-input-json",
            str(fact_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "brf2_runtime_signal_capture_ready"
    assert packet["signal_detector_preview"]["current_signal_state"] == (
        "fresh_signal_present"
    )
    assert "BRF2 Runtime Signal Capture" in output_md.read_text(encoding="utf-8")
