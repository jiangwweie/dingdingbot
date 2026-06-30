from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_replay_live_parity_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_replay_live_parity_audit",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event(symbol: str, *, boundary: bool = True) -> dict:
    return {
        "strategy_group_id": "MPG-001",
        "symbol": symbol,
        "event_time_utc": "2026-06-27T00:00:00+00:00",
        "fresh_like_signal_seen": True,
        "counterfactual_fresh_signal_present": True,
        "gate_breakdown": {
            "required_facts_replay_shape_present": True,
            "would_reach_action_time_boundary": boundary,
        },
    }


def _replay() -> dict:
    return {
        "strategy_rows": [
            {
                "strategy_group_id": "MPG-001",
                "path_id": "MPG-LONG",
                "window_results": [
                    {"window_days": 3, "counterfactual_events": [_event("ETHUSDT")]},
                    {
                        "window_days": 7,
                        "counterfactual_events": [_event("SOLUSDT")],
                    },
                    {
                        "window_days": 14,
                        "counterfactual_events": [_event("OPUSDT")],
                    },
                ],
            }
        ]
    }


def _mpg_watcher() -> dict:
    return {
        "status": "mpg_expanded_watcher_facts_ready",
        "watcher_scope": {
            "symbol_scope": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "primary_live_submit_symbol_scope": ["BTCUSDT", "ETHUSDT"],
            "expanded_readonly_watcher_symbols": ["SOLUSDT"],
            "source": "binance_usdm_public_facts_readonly",
        },
    }


def test_replay_live_parity_counts_windows_and_symbol_mismatches():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_replay(),
        cpm_facts={},
        mpg_watcher=_mpg_watcher(),
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    row = artifact["strategy_rows"][0]
    assert [window["window_days"] for window in row["window_results"]] == [3, 7, 14]
    assert row["replay_signal_count"] == 3
    assert row["live_detector_reproduced_count"] == 2
    assert row["mismatch_count"] == 1
    assert artifact["summary"]["mismatch_count"] == 1
    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["symbol"] == "OPUSDT"
    assert symbol_row["mismatch_reasons"] == [
        "signal_capture_defect:symbol_scope_not_attached"
    ]


def test_replay_live_parity_never_marks_unreproduced_signal_as_market_wait():
    module = _load_module()
    replay = _replay()
    replay["strategy_rows"][0]["window_results"][0]["counterfactual_events"] = [
        _event("ETHUSDT", boundary=False)
    ]

    artifact = module.build_replay_live_parity_audit(
        replay=replay,
        cpm_facts={},
        mpg_watcher=_mpg_watcher(),
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    reasons = {
        mismatch["mismatch_reason"]
        for row in artifact["strategy_rows"]
        for mismatch in row["mismatch_table"]
    }
    assert "market_wait" not in " ".join(reasons)
    assert "signal_capture_defect:action_time_boundary_not_reproduced" in reasons
    checks = artifact["checks"]
    assert checks["replay_treated_as_live_signal"] is False
    assert checks["finalgate_called"] is False
    assert checks["operation_layer_called"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False
