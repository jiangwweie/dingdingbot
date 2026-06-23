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


def _brf_reference_preview_packet(*, would_enter: bool = False) -> dict:
    return {
        "status": "preview_built",
        "preview": {
            "current_signals": [
                {
                    "record_id": "BRF-001-BTC-SHORT:brf-signal:1782097200000",
                    "candidate_id": "BRF-001-BTC-SHORT",
                    "strategy_group_id": "BRF-001",
                    "strategy_family_version_id": "BRF-001-v0",
                    "symbol": "BTC/USDT:USDT",
                    "side": "short" if would_enter else "none",
                    "signal_type": "would_enter" if would_enter else "no_action",
                    "confidence": "0.64" if would_enter else "0.25",
                    "market_bar_timestamp_ms": 1782097200000,
                    "reason_codes": (
                        [
                            "brf_bear_rally_extended",
                            "brf_rally_high_rejected",
                            "brf_short_squeeze_risk_reviewed",
                        ]
                        if would_enter
                        else ["brf_no_action_no_rally_extension"]
                    ),
                    "evidence_payload": {
                        "htf_context": "trend_down",
                        "rally_extension_confirmed": would_enter,
                        "rejection_confirmed": would_enter,
                        "price_action_structure": {
                            "bear_rally_failure": would_enter,
                            "closed_bar": True,
                            "rally_pct": "2.4802" if would_enter else "1.1053",
                            "rejection_upper_wick_ratio": (
                                "0.3603" if would_enter else "0.0539"
                            ),
                            "close_reversal_pct": (
                                "0.7752" if would_enter else "0.0125"
                            ),
                            "rally_high_reference": "64788.00",
                            "rally_low_reference": "63220.00",
                        },
                        "short_squeeze_risk": {
                            "status": "reviewed",
                            "squeeze_warning": False,
                            "squeeze_risk_level": "bounded_review",
                        },
                    },
                    "signal_input_snapshot": {
                        "market_snapshot": {
                            "candle_context": {
                                "closed_bar": True,
                                "windows": {
                                    "1h": [
                                        {
                                            "open_time_ms": 1782097200000,
                                            "open": "64226.50",
                                            "high": "64788.00",
                                            "low": "63888.00",
                                            "close": "63935.10",
                                            "volume": "1234.5",
                                        }
                                    ]
                                },
                            }
                        }
                    },
                }
            ]
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


def test_brf2_runtime_signal_facts_derives_from_brf_reference_watcher_row():
    module = _load_module()

    packet = module.build_brf2_runtime_signal_facts(
        source_packet=_brf_reference_preview_packet(would_enter=False),
        source_path=Path("preview.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    facts = packet["facts"]
    assert packet["status"] == module.READY_STATUS
    assert packet["strategy_group_id"] == "BRF2-001"
    assert packet["fact_input_present"] is True
    assert packet["watcher_tick_present"] is True
    assert packet["source_signal_context"]["source_strategy_group_id"] == "BRF-001"
    assert packet["source_signal_context"]["symbol"] == "BTC/USDT:USDT"
    assert facts["closed_1h_ohlcv"]["status"] == "ready"
    assert facts["closed_5m_ohlcv"]["status"] == "ready"
    assert facts["closed_5m_ohlcv"]["detail"][
        "proxy_is_not_action_time_live_required_fact"
    ] is True
    assert facts["rally_context"]["status"] == "not_satisfied"
    assert facts["rally_failure_trigger_state"]["status"] == "not_confirmed"
    assert facts["short_squeeze_risk_state"]["status"] == "bounded"
    assert facts["strong_reclaim_disable_state"]["status"] == "false"
    assert packet["first_blocker"]["class"] == "none"
    assert packet["checks"]["source_is_brf_reference_row"] is True
    assert packet["checks"]["actionable_now"] is False
    assert packet["checks"]["real_order_authority"] is False


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
