from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_sor_session_scope_detector.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_sor_session_scope_detector",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_symbol(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "public_facts_ready": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "funding_not_extreme": True,
    }


def _public_facts() -> dict:
    return {
        "symbols": [
            _public_symbol("ETHUSDT"),
            _public_symbol("SOLUSDT"),
            _public_symbol("BTCUSDT"),
            _public_symbol("AVAXUSDT"),
        ]
    }


def _row(open_time_ms: int, close: str, high: str, low: str) -> list:
    return [
        open_time_ms,
        "100",
        high,
        low,
        close,
        "1000",
        open_time_ms + 899_000,
        "0",
        1,
        "0",
        "0",
        "0",
    ]


def _candles(*, breakout: bool) -> list[list]:
    start = int(datetime(2026, 6, 30, tzinfo=timezone.utc).timestamp() * 1000)
    fifteen = 15 * 60 * 1000
    rows = [
        _row(start + idx * fifteen, close="100", high="101", low="99")
        for idx in range(4)
    ]
    rows.append(
        _row(
            start + 4 * fifteen,
            close="103" if breakout else "100.5",
            high="103.5" if breakout else "101",
            low="100",
        )
    )
    return rows


def test_sor_session_detector_builds_authorized_symbol_scope():
    module = _load_module()

    artifacts = module.build_sor_session_scope_detector(
        public_facts=_public_facts(),
        candle_payloads={
            "ETHUSDT": _candles(breakout=False),
            "SOLUSDT": _candles(breakout=True),
            "BTCUSDT": _candles(breakout=False),
            "AVAXUSDT": _candles(breakout=False),
        },
        generated_at_utc="2026-06-30T02:00:00+00:00",
    )

    scope = artifacts["scope"]
    detector = artifacts["detector"]
    assert scope["expanded_readonly_watcher_symbols"] == ["SOLUSDT", "AVAXUSDT"]
    assert scope["primary_live_submit_symbol_scope"] == ["BTCUSDT", "ETHUSDT"]
    assert scope["reviewed_symbols"] == ["ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT"]
    assert {row["symbol"] for row in detector["symbol_detector_rows"]} == {
        "ETHUSDT",
        "SOLUSDT",
        "BTCUSDT",
        "AVAXUSDT",
    }
    sol = next(row for row in detector["symbol_detector_rows"] if row["symbol"] == "SOLUSDT")
    avax = next(row for row in detector["symbol_detector_rows"] if row["symbol"] == "AVAXUSDT")
    assert sol["opening_range"]["high"] == 101.0
    assert sol["breakout_level"] == 101.0
    assert sol["follow_through"] is True
    assert sol["invalidation"]["held"] is True
    assert sol["fresh_session_range_signal"] is True
    assert avax["fresh_session_range_signal"] is False
    assert "breakout_level_crossed" in avax["missing_required_trigger_facts"]
    assert detector["summary"]["fresh_session_signal_count"] == 1
    for artifact in artifacts.values():
        checks = artifact["checks"]
        assert checks["primary_live_submit_scope_changed"] is False
        assert checks["live_profile_changed"] is False
        assert checks["order_sizing_changed"] is False
        assert checks["finalgate_called"] is False
        assert checks["operation_layer_called"] is False
        assert checks["exchange_write_called"] is False
        assert checks["order_created"] is False
        assert checks["live_submit_allowed"] is False


def test_sor_session_detector_fails_closed_without_candles():
    module = _load_module()

    artifacts = module.build_sor_session_scope_detector(
        public_facts=_public_facts(),
        candle_payloads={
            "ETHUSDT": [],
            "SOLUSDT": [],
            "BTCUSDT": [],
            "AVAXUSDT": [],
        },
        generated_at_utc="2026-06-30T02:00:00+00:00",
    )

    detector = artifacts["detector"]
    assert detector["summary"]["fresh_session_signal_count"] == 0
    for row in detector["symbol_detector_rows"]:
        assert row["fresh_session_range_signal"] is False
        assert "opening_range_available" in row["missing_required_trigger_facts"]


def test_sor_session_detector_can_fetch_candles_via_readonly_ssh(monkeypatch):
    module = _load_module()

    def fake_fetch(host: str, symbols: tuple[str, ...]) -> dict[str, list[list]]:
        assert host == "tokyo"
        assert symbols == ("ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT")
        return {
            "ETHUSDT": _candles(breakout=False),
            "SOLUSDT": _candles(breakout=True),
            "BTCUSDT": _candles(breakout=False),
            "AVAXUSDT": _candles(breakout=False),
        }

    monkeypatch.setattr(module, "_fetch_klines_via_ssh", fake_fetch)

    artifacts = module.build_sor_session_scope_detector(
        public_facts=_public_facts(),
        ssh_host="tokyo",
        generated_at_utc="2026-06-30T02:00:00+00:00",
    )

    detector = artifacts["detector"]
    sol = next(row for row in detector["symbol_detector_rows"] if row["symbol"] == "SOLUSDT")
    assert sol["latest_candle_close_time_utc"]
    assert sol["fresh_session_range_signal"] is True
