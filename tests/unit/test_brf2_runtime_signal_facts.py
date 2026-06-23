from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_runtime_signal_facts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_brf2_runtime_signal_facts",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fresh_fact_packet() -> dict:
    return {
        "strategy_group_id": "BRF2-001",
        "signal_context": {
            "signal_packet_id": "brf2-signal-001",
            "runtime_instance_id": "runtime-brf2-001",
            "symbol": "ADA/USDT:USDT",
            "timeframe": "5m_closed",
            "closed_at_utc": "2026-06-23T00:00:00+00:00",
        },
        "facts": {
            "closed_1h_ohlcv": {"status": "ready"},
            "closed_5m_ohlcv": {"status": "ready"},
            "rally_context": {"status": "bear_or_weak_reclaim"},
            "rally_failure_trigger_state": {"status": "confirmed"},
        },
    }


def test_brf2_runtime_signal_facts_exposes_missing_watcher_input():
    module = _load_module()

    packet = module.build_brf2_runtime_signal_facts(
        source_packet={},
        source_path=Path("missing.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["schema"] == module.SCHEMA
    assert packet["status"] == module.MISSING_STATUS
    assert packet["strategy_group_id"] == "BRF2-001"
    assert packet["fact_input_present"] is False
    assert packet["watcher_tick_present"] is False
    assert packet["first_blocker"]["class"] == "brf2_watcher_fact_input_missing"
    assert packet["first_blocker"]["owner"] == "engineering"
    assert packet["next_action"] == "attach_brf2_watcher_fact_input_producer"
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False
    assert packet["safety_invariants"]["calls_finalgate"] is False
    assert packet["safety_invariants"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_brf2_runtime_signal_facts_accepts_explicit_brf2_fact_packet():
    module = _load_module()

    packet = module.build_brf2_runtime_signal_facts(
        source_packet=_fresh_fact_packet(),
        source_path=Path("facts.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert packet["status"] == module.READY_STATUS
    assert packet["fact_input_present"] is True
    assert packet["watcher_tick_present"] is True
    assert packet["source_signal_context"]["signal_packet_id"] == "brf2-signal-001"
    assert packet["source_signal_context"]["symbol"] == "ADA/USDT:USDT"
    assert packet["facts"]["closed_1h_ohlcv"]["status"] == "ready"
    assert packet["first_blocker"]["class"] == "none"
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False


def test_brf2_runtime_signal_facts_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    source_json = tmp_path / "facts.json"
    output_json = tmp_path / "latest-brf2-runtime-signal-facts.json"
    output_md = tmp_path / "latest-brf2-runtime-signal-facts.md"
    source_json.write_text(json.dumps(_fresh_fact_packet()), encoding="utf-8")

    exit_code = module.main(
        [
            "--source-json",
            str(source_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == module.READY_STATUS
    assert packet["fact_input_present"] is True
    assert "BRF2 Runtime Signal Facts" in output_md.read_text(encoding="utf-8")
