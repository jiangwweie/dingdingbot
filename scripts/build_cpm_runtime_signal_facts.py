#!/usr/bin/env python3
"""Build CPM runtime signal fact input from Binance USD-M closed candles."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)


DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.md"
)
DEFAULT_PUBLIC_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)

SCHEMA = "brc.cpm_runtime_signal_facts.v1"
BASE_URL = "https://fapi.binance.com"
DEFAULT_SYMBOLS = ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT")
TIMEFRAMES = ("15m", "1h", "4h")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-facts-json", default=str(DEFAULT_PUBLIC_FACTS_JSON))
    parser.add_argument("--symbols", nargs="*", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    symbols = [str(symbol).upper() for symbol in args.symbols]
    artifact = build_cpm_runtime_signal_facts(
        public_facts=_read_optional_json(Path(args.public_facts_json)),
        symbols=symbols,
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(json.dumps({"status": artifact["status"], "output_json": str(output_json)}))
    return 0


def build_cpm_runtime_signal_facts(
    *,
    public_facts: dict[str, Any] | None = None,
    symbols: list[str] | None = None,
    candle_payloads: dict[str, dict[str, list[list[Any]]]] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    now = _parse_utc(generated_at_utc) if generated_at_utc else datetime.now(timezone.utc)
    symbols = [str(symbol).upper() for symbol in (symbols or list(DEFAULT_SYMBOLS))]
    if not symbols:
        symbols = list(DEFAULT_SYMBOLS)
    public_facts = public_facts or {}
    public_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in public_facts.get("symbols") or []
        if isinstance(row, dict)
    }
    candle_payloads = candle_payloads or _fetch_candles(symbols)
    per_symbol = [
        _symbol_detector_row(
            symbol=symbol,
            candles=candle_payloads.get(symbol, {}),
            public_row=public_by_symbol.get(symbol, {}),
            generated_at=now,
        )
        for symbol in symbols
    ]
    watcher_tick_present = any(row["candle_close_time_utc"] for row in per_symbol)
    primary_symbol = "ETHUSDT" if "ETHUSDT" in symbols else symbols[0]
    primary_row = next((row for row in per_symbol if row["symbol"] == primary_symbol), per_symbol[0])
    trigger_facts = primary_row["trigger_facts"]
    facts = {
        "htf_trend_intact": _fact_from_trigger(trigger_facts["htf_trend_intact"]),
        "pullback_depth_normal": _fact_from_trigger(trigger_facts["pullback_depth_normal"]),
        "reclaim_confirmed": _fact_from_trigger(trigger_facts["reclaim_confirmed"]),
        "invalidated_below_level": _fact_from_trigger(trigger_facts["invalidated_below_level"]),
        "liquidity_ok": _fact_from_trigger(trigger_facts["liquidity_ok"]),
        "funding_not_extreme": _fact_from_trigger(trigger_facts["funding_not_extreme"]),
        "active_position_or_open_order_clear": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
        "action_time_available_balance": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
        "htf_trend_broken": _disable_from_trigger(trigger_facts["htf_trend_intact"]),
        "pullback_depth_abnormal": _disable_from_trigger(
            trigger_facts["pullback_depth_normal"]
        ),
        "reclaim_failed_or_stale": _disable_from_trigger(
            trigger_facts["reclaim_confirmed"]
        ),
        "liquidity_not_ok": _disable_from_trigger(trigger_facts["liquidity_ok"]),
        "funding_extreme": _disable_from_trigger(trigger_facts["funding_not_extreme"]),
        "active_position_or_open_order_conflict": _fact(
            "action_time_required", False, "runtime_action_time_exchange_facts"
        ),
    }
    fresh_symbol_count = sum(row["fresh_signal_present"] is True for row in per_symbol)
    primary_fresh = primary_row["fresh_signal_present"] is True
    return {
        "schema": SCHEMA,
        "scope": "cpm_runtime_signal_facts_live_detector_read_model",
        "status": "cpm_runtime_signal_facts_ready",
        "generated_at_utc": now.isoformat(),
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "fact_input_present": True,
        "watcher_tick_present": watcher_tick_present,
        "detector_source_mode": "binance_usdm_public_closed_candles",
        "fact_authority": "binance_usdm_public_candles_not_action_time_private_facts",
        "fact_authority_boundary": {
            "live_required_facts_authority": False,
            "action_time_refresh_required": True,
            "replay_treated_as_live_signal": False,
        },
        "source_signal_context": {
            "source": "binance_usdm_public_closed_candles",
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
            "source_signal_type": "live_detector_readonly",
            "symbol": primary_symbol,
            "timeframe": primary_row.get("timeframe"),
            "candle_close_time_utc": primary_row.get("candle_close_time_utc"),
        },
        "watcher_scope": {
            "symbol_scope": symbols,
            "primary_live_submit_symbol_scope": [primary_symbol],
            "expanded_readonly_symbol_scope": [
                symbol for symbol in symbols if symbol != primary_symbol
            ],
            "timeframes": list(TIMEFRAMES),
        },
        "live_detector": {
            "source": "binance_usdm_public_closed_candles",
            "fresh_signal_present": primary_fresh,
            "detected_fresh_signal_count": fresh_symbol_count,
            "primary_symbol": primary_symbol,
            "per_symbol_signal_facts": per_symbol,
            "missing_required_trigger_facts": primary_row[
                "missing_required_trigger_facts"
            ],
        },
        "facts": facts,
        "first_blocker": {
            "class": (
                "none"
                if primary_fresh
                else primary_row["first_blocker_class"]
            ),
            "owner": "runtime" if primary_fresh else primary_row["first_blocker_owner"],
            "repair_checkpoint": (
                "run_cpm_runtime_signal_capture"
                if primary_fresh
                else primary_row["next_checkpoint"]
            ),
        },
        "checks": {
            "fact_input_present": True,
            "watcher_tick_present": watcher_tick_present,
            "action_time_facts_are_authority": False,
            "uses_readonly_cpm_proxy": False,
            "uses_replay_signal_as_live_signal": False,
            "detector_source_is_real_candles": True,
            "primary_fresh_signal_present": primary_fresh,
            "detected_fresh_signal_count": fresh_symbol_count,
        },
        "interaction": non_executing_interaction("L0_local_cpm_runtime_signal_facts"),
        "safety_invariants": non_executing_safety_invariants(
            tuple(), include_authority_mirrors=False
        ),
    }


def _symbol_detector_row(
    *,
    symbol: str,
    candles: dict[str, list[list[Any]]],
    public_row: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    candles_15m = _closed_candles(candles.get("15m") or [], generated_at)
    candles_1h = _closed_candles(candles.get("1h") or [], generated_at)
    candles_4h = _closed_candles(candles.get("4h") or [], generated_at)
    candle_input_missing = not candles_15m or not candles_1h or not candles_4h
    latest_15m = candles_15m[-1] if candles_15m else {}
    close = _float(latest_15m.get("close"))
    candle_close_time = latest_15m.get("close_time_utc")
    sma20_1h = _sma([_float(row.get("close")) for row in candles_1h[-20:]])
    sma20_4h = _sma([_float(row.get("close")) for row in candles_4h[-20:]])
    recent_lows = [_float(row.get("low")) for row in candles_15m[-12:]]
    previous = candles_15m[-2] if len(candles_15m) >= 2 else {}
    prior_close = _float(previous.get("close"))
    low = _float(latest_15m.get("low"))
    trend_ref = sma20_4h if sma20_4h is not None else sma20_1h
    pullback_ref = sma20_1h or trend_ref
    pullback_depth_pct = (
        ((low - pullback_ref) / pullback_ref * 100)
        if low is not None and pullback_ref
        else None
    )
    reclaim_confirmed = bool(
        close is not None
        and pullback_ref
        and close > pullback_ref
        and (prior_close is None or prior_close <= close)
    )
    invalidation_level = min([value for value in recent_lows if value is not None], default=None)
    trigger_facts = {
        "htf_trend_intact": _trigger(
            close is not None and trend_ref is not None and close >= trend_ref,
            "close_above_4h_or_1h_sma20",
            {"close": close, "trend_reference": trend_ref},
            fresh=not candle_input_missing,
        ),
        "pullback_depth_normal": _trigger(
            pullback_depth_pct is not None and -6.0 <= pullback_depth_pct <= 2.5,
            "latest_low_within_normal_pullback_band_vs_1h_sma20",
            {"pullback_depth_pct": _round(pullback_depth_pct)},
            fresh=not candle_input_missing,
        ),
        "reclaim_confirmed": _trigger(
            reclaim_confirmed,
            "latest_closed_15m_close_reclaimed_reference",
            {"close": close, "reference": pullback_ref, "prior_close": prior_close},
            fresh=not candle_input_missing,
        ),
        "invalidated_below_level": _trigger(
            invalidation_level is not None and close is not None and close > invalidation_level,
            "latest_close_above_recent_swing_low_invalidation_level",
            {"invalidation_level": invalidation_level, "close": close},
            fresh=not candle_input_missing,
        ),
        "liquidity_ok": _trigger(
            public_row.get("public_facts_ready") is True
            and public_row.get("spread_ok") is True
            and public_row.get("min_notional_ok") is True
            and public_row.get("qty_step_ok") is True,
            "public_contract_spread_min_notional_and_qty_step_ok",
            {"spread_bps": _as_dict(public_row.get("facts")).get("spread_bps")},
        ),
        "funding_not_extreme": _trigger(
            public_row.get("funding_not_extreme") is True,
            "public_premium_index_funding_not_extreme",
            {
                "last_funding_rate": _as_dict(public_row.get("facts")).get(
                    "last_funding_rate"
                )
            },
        ),
    }
    missing = [key for key, value in trigger_facts.items() if value["value"] is not True]
    fresh = not missing
    if candle_input_missing:
        first_blocker_class = "cpm_live_detector_candle_input_missing"
        first_blocker_owner = "engineering"
        next_checkpoint = "refresh_cpm_binance_usdm_closed_candles"
    elif missing:
        first_blocker_class = "fresh_cpm_long_signal_absent"
        first_blocker_owner = "market"
        next_checkpoint = "continue_cpm_long_armed_observation_until_reclaim_signal"
    else:
        first_blocker_class = "private_action_time_facts_required"
        first_blocker_owner = "runtime"
        next_checkpoint = "refresh_private_action_time_facts"
    return {
        "symbol": symbol,
        "timeframe": "15m_closed",
        "candle_close_time_utc": candle_close_time,
        "fresh_signal_present": fresh,
        "candle_input_missing": candle_input_missing,
        "trigger_facts": trigger_facts,
        "missing_required_trigger_facts": missing,
        "first_blocker_class": first_blocker_class,
        "first_blocker_owner": first_blocker_owner,
        "next_checkpoint": next_checkpoint,
    }


def _fetch_candles(symbols: list[str]) -> dict[str, dict[str, list[list[Any]]]]:
    return {
        symbol: {
            timeframe: _fetch_json(
                "/fapi/v1/klines?"
                + urlencode({"symbol": symbol, "interval": timeframe, "limit": 80})
            )
            for timeframe in TIMEFRAMES
        }
        for symbol in symbols
    }


def _fetch_json(path: str) -> Any:
    request = Request(BASE_URL + path, headers={"User-Agent": "brc-readonly-monitor/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return []


def _closed_candles(rows: list[list[Any]], now: datetime) -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    now_ms = int(now.timestamp() * 1000)
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            continue
        close_time_ms = _int(row[6])
        if close_time_ms is None or close_time_ms > now_ms:
            continue
        closed.append(
            {
                "open_time_ms": _int(row[0]),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "close_time_ms": close_time_ms,
                "close_time_utc": datetime.fromtimestamp(
                    close_time_ms / 1000, tz=timezone.utc
                ).isoformat(),
            }
        )
    return closed


def _trigger(
    value: bool,
    rule: str,
    metrics: dict[str, Any],
    *,
    fresh: bool = True,
) -> dict[str, Any]:
    return {
        "value": bool(value),
        "status": "satisfied" if value else "not_satisfied",
        "fresh": fresh,
        "source": "binance_usdm_public_closed_candles",
        "rule": rule,
        "metrics": metrics,
    }


def _fact_from_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ready" if trigger.get("value") is True else "not_satisfied",
        "fresh": trigger.get("fresh") is not False,
        "source": trigger.get("source") or "binance_usdm_public_closed_candles",
    }


def _disable_from_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "false",
        "fresh": trigger.get("fresh") is not False,
        "source": trigger.get("source") or "binance_usdm_public_closed_candles",
    }


def _fact(status: str, fresh: bool, source: str) -> dict[str, Any]:
    return {"status": status, "fresh": fresh, "source": source}


def _sma(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM Runtime Signal Facts",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Fact input present: `{_yes_no(artifact['fact_input_present'])}`",
            f"- Watcher tick present: `{_yes_no(artifact['watcher_tick_present'])}`",
            f"- Detector source: `{artifact['detector_source_mode']}`",
            f"- Primary fresh signal: `{_yes_no(artifact['checks']['primary_fresh_signal_present'])}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
