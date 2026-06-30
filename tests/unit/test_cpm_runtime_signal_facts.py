from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_cpm_runtime_signal_facts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_cpm_runtime_signal_facts",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _kline(
    open_time_ms: int,
    *,
    close_time_ms: int,
    open_price: str = "100",
    high: str = "106",
    low: str = "99",
    close: str = "105",
    volume: str = "1000",
) -> list:
    return [
        open_time_ms,
        open_price,
        high,
        low,
        close,
        volume,
        close_time_ms,
        "0",
        1,
        "0",
        "0",
        "0",
    ]


def _candles_for_symbol(*, fresh: bool = True) -> dict[str, list[list]]:
    base = 1780272000000
    one_minute = 60_000
    hour = 60 * one_minute
    four_hour = 4 * hour
    fifteen = 15 * one_minute
    latest_close = "105" if fresh else "95"
    latest_low = "99" if fresh else "94"
    candles_15m = [
        _kline(
            base + idx * fifteen,
            close_time_ms=base + idx * fifteen + fourteen_minutes,
            close="100",
            low="98",
        )
        for idx, fourteen_minutes in enumerate([899_000] * 11)
    ]
    candles_15m.append(
        _kline(
            base + 11 * fifteen,
            close_time_ms=base + 11 * fifteen + 899_000,
            close=latest_close,
            low=latest_low,
        )
    )
    candles_1h = [
        _kline(
            base - (20 - idx) * hour,
            close_time_ms=base - (20 - idx) * hour + hour - 1_000,
            close="100",
            low="98",
        )
        for idx in range(20)
    ]
    candles_4h = [
        _kline(
            base - (20 - idx) * four_hour,
            close_time_ms=base - (20 - idx) * four_hour + four_hour - 1_000,
            close="100",
            low="98",
        )
        for idx in range(20)
    ]
    return {"15m": candles_15m, "1h": candles_1h, "4h": candles_4h}


def _public_facts(symbols: list[str]) -> dict:
    return {
        "status": "binance_usdm_public_facts_ready",
        "symbols": [
            {
                "symbol": symbol,
                "public_facts_ready": True,
                "exchange_contract_exists": True,
                "mark_price_fresh": True,
                "funding_not_extreme": True,
                "spread_ok": True,
                "min_notional_ok": True,
                "qty_step_ok": True,
                "leverage_available": True,
                "facts": {"spread_bps": 0.5, "last_funding_rate": "0.0001"},
            }
            for symbol in symbols
        ],
    }


def test_cpm_runtime_signal_facts_use_real_closed_candles_not_proxy():
    module = _load_module()
    symbols = ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"]

    artifact = module.build_cpm_runtime_signal_facts(
        public_facts=_public_facts(symbols),
        symbols=symbols,
        candle_payloads={symbol: _candles_for_symbol(fresh=True) for symbol in symbols},
        generated_at_utc="2026-06-01T05:00:00+00:00",
    )

    assert artifact["detector_source_mode"] == "binance_usdm_public_closed_candles"
    assert artifact["watcher_tick_present"] is True
    assert artifact["checks"]["uses_readonly_cpm_proxy"] is False
    assert artifact["checks"]["uses_replay_signal_as_live_signal"] is False
    assert artifact["checks"]["detector_source_is_real_candles"] is True
    assert artifact["live_detector"]["primary_symbol"] == "ETHUSDT"
    assert artifact["live_detector"]["fresh_signal_present"] is True
    assert artifact["live_detector"]["missing_required_trigger_facts"] == []
    assert artifact["source_signal_context"]["candle_close_time_utc"]
    assert artifact["watcher_scope"]["symbol_scope"] == symbols
    assert "readonly_cpm_proxy" not in json.dumps(
        {
            "source_signal_context": artifact["source_signal_context"],
            "facts": artifact["facts"],
            "live_detector": artifact["live_detector"],
        }
    )
    for key in [
        "htf_trend_intact",
        "pullback_depth_normal",
        "reclaim_confirmed",
        "invalidated_below_level",
        "liquidity_ok",
        "funding_not_extreme",
    ]:
        assert artifact["facts"][key]["status"] == "ready"


def test_cpm_runtime_signal_facts_report_field_level_missing_reasons():
    module = _load_module()
    symbols = ["ETHUSDT", "SOLUSDT"]

    artifact = module.build_cpm_runtime_signal_facts(
        public_facts=_public_facts(symbols),
        symbols=symbols,
        candle_payloads={
            "ETHUSDT": _candles_for_symbol(fresh=False),
            "SOLUSDT": _candles_for_symbol(fresh=True),
        },
        generated_at_utc="2026-06-01T05:00:00+00:00",
    )

    missing = artifact["live_detector"]["missing_required_trigger_facts"]
    assert artifact["live_detector"]["fresh_signal_present"] is False
    assert "htf_trend_intact" in missing
    assert "reclaim_confirmed" in missing
    assert artifact["first_blocker"]["class"] == "fresh_cpm_long_signal_absent"
    assert artifact["first_blocker"]["owner"] == "market"
    assert artifact["checks"]["detected_fresh_signal_count"] == 1


def test_cpm_runtime_signal_facts_fail_closed_when_candles_missing():
    module = _load_module()

    artifact = module.build_cpm_runtime_signal_facts(
        public_facts=_public_facts(["ETHUSDT"]),
        symbols=["ETHUSDT"],
        candle_payloads={"ETHUSDT": {"15m": [], "1h": [], "4h": []}},
        generated_at_utc="2026-06-01T05:00:00+00:00",
    )

    assert artifact["watcher_tick_present"] is False
    assert artifact["live_detector"]["fresh_signal_present"] is False
    assert artifact["first_blocker"]["class"] == "cpm_live_detector_candle_input_missing"
    assert artifact["first_blocker"]["owner"] == "engineering"
    assert set(artifact["live_detector"]["missing_required_trigger_facts"]) >= {
        "htf_trend_intact",
        "pullback_depth_normal",
        "reclaim_confirmed",
        "invalidated_below_level",
    }


def test_cpm_runtime_signal_facts_can_fallback_to_previous_real_candle_artifact(
    tmp_path: Path,
):
    module = _load_module()
    fallback_path = tmp_path / "fallback.json"
    fallback = module.build_cpm_runtime_signal_facts(
        public_facts=_public_facts(["ETHUSDT"]),
        symbols=["ETHUSDT"],
        candle_payloads={"ETHUSDT": _candles_for_symbol(fresh=True)},
        generated_at_utc="2026-06-01T05:00:00+00:00",
    )
    fallback_path.write_text(json.dumps(fallback), encoding="utf-8")
    current = module.build_cpm_runtime_signal_facts(
        public_facts=_public_facts(["ETHUSDT"]),
        symbols=["ETHUSDT"],
        candle_payloads={"ETHUSDT": {"15m": [], "1h": [], "4h": []}},
        generated_at_utc="2026-06-01T05:00:00+00:00",
    )

    artifact = module._fallback_runtime_signal_facts(
        current,
        fallback_path=fallback_path,
        symbols=["ETHUSDT"],
    )

    assert artifact["status"] == "cpm_runtime_signal_facts_ready_from_fallback"
    assert artifact["watcher_tick_present"] is True
    assert artifact["checks"]["used_fallback_after_candle_fetch_failure"] is True
    assert artifact["checks"]["uses_replay_signal_as_live_signal"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["order_created"] is False
