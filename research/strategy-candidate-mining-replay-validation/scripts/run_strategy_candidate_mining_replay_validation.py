#!/usr/bin/env python3
"""Mine StrategyGroup trial candidates with replay evidence.

Research-only script. It fetches public Binance USD-M candles, evaluates a
fixed set of candidate strategy families, and writes machine/human-readable
evidence for main-control trial-intake review. It does not touch main-control,
FinalGate, Operation Layer, exchange writes, live profiles, or tier policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "research" / "strategy-candidate-mining-replay-validation"
DATA_DIR = BASE / "data"
REPORT_DIR = BASE / "reports"
PACK_DIR = BASE / "packs"

REPORT_JSON = REPORT_DIR / "strategy-candidate-mining-replay-validation.json"
REPORT_MD = REPORT_DIR / "strategy-candidate-mining-replay-validation.md"
INDEX_MD = REPORT_DIR / "INDEX.md"

TASK_ID = "STRATEGY-CANDIDATE-MINING-REPLAY-VALIDATION-001"
VERSION = "2026-06-30-r0"
TZ_CST = timezone(timedelta(hours=8))
API = "https://fapi.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"]
WINDOW_DAYS = [3, 7, 14, 30]
ROUND_TRIP_COST_PCT = 0.12

AUTHORITY_BOUNDARY = {
    "research_only": True,
    "execution_authority": False,
    "actionable_now": False,
    "real_order_authority": False,
    "finalgate_input": False,
    "operation_layer_input": False,
    "exchange_write": False,
    "order_created": False,
    "live_profile_change": False,
    "tier_policy_change": False,
}


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    strategy_family: str
    side: str
    timeframes: list[str]
    entry_rule: str
    stop_rule: str
    tp_rule: str
    time_stop: str
    cooldown_hours: int
    max_holding_hours: int
    symbols: list[str]
    selector: Callable[[dict[str, Any], list[dict[str, Any]], int, dict[str, dict[str, Any]]], bool]
    stop_target: Callable[[dict[str, Any], list[dict[str, Any]], int, float], tuple[float, float]]
    research_question: str
    intended_role: str


def main() -> int:
    end = datetime(2026, 6, 30, 8, 0, tzinfo=TZ_CST)
    start = end - timedelta(days=38)
    candles_1h: dict[str, list[dict[str, Any]]] = {}
    candles_5m: dict[str, list[dict[str, Any]]] = {}
    for symbol in SYMBOLS:
        candles_1h[symbol] = load_candles(symbol, "1h", start, end)
        candles_5m[symbol] = load_candles(symbol, "5m", end - timedelta(days=33), end)
        enrich(candles_1h[symbol])

    btc_by_time = {row["open_time_cst"]: row for row in candles_1h["BTCUSDT"]}
    specs = build_specs()
    candidates = []
    handoff_packs = []
    for spec in specs:
        replay = replay_candidate(spec, candles_1h, candles_5m, btc_by_time, end)
        classification = classify_candidate(spec, replay)
        candidate = {
            "candidate_id": spec.candidate_id,
            "strategy_family": spec.strategy_family,
            "side": spec.side,
            "timeframes": spec.timeframes,
            "symbol_scope": [to_contract(symbol) for symbol in spec.symbols],
            "research_question": spec.research_question,
            "intended_role": spec.intended_role,
            "entry_rule": spec.entry_rule,
            "exit_rule": f"{spec.tp_rule}; {spec.time_stop}",
            "stop_rule": spec.stop_rule,
            "tp_rule": spec.tp_rule,
            "time_stop": spec.time_stop,
            "cooldown": f"{spec.cooldown_hours}h per symbol",
            "replay": replay,
            "status": classification["status"],
            "status_reason": classification["status_reason"],
            "main_control_absorbability": classification["main_control_absorbability"],
            "recommended_tradeability_first_blocker": classification["first_blocker"],
            "known_failure_modes": failure_modes(spec, replay),
            "required_facts_draft": required_facts(spec),
            "disable_facts": disable_facts(spec),
            "risk_envelope": risk_envelope(spec),
            "overlap_with_other_strategies": overlap_read(spec),
        }
        candidates.append(candidate)
        if candidate["status"] == "main_control_handoff_candidate":
            pack = handoff_pack(candidate)
            handoff_packs.append(pack)
            write_json(PACK_DIR / f"{candidate['candidate_id']}-handoff-draft.json", pack)

    report = build_report(end, candidates, handoff_packs, candles_1h)
    validate(report)
    write_json(REPORT_JSON, report)
    write_text(REPORT_MD, render_report_md(report))
    write_text(INDEX_MD, render_index_md(report))
    print(json.dumps({
        "status": report["status"],
        "candidate_count": len(report["candidates"]),
        "symbol_count": len(report["symbol_coverage"]),
        "main_control_handoff_candidates": len(report["main_control_handoff_candidates"]),
        "watcher_scope_candidates": len(report["watcher_scope_candidates"]),
        "park_or_kill": len(report["park_or_kill"]),
        "report": rel(REPORT_JSON),
    }, ensure_ascii=False, sort_keys=True))
    return 0


def load_candles(symbol: str, interval: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / f"{symbol.lower()}-{interval}-{start:%Y%m%d%H}-{end:%Y%m%d%H}.json"
    if cache.exists():
        rows = read_json(cache)["rows"]
    else:
        rows = fetch_klines(symbol, interval, start.astimezone(timezone.utc), end.astimezone(timezone.utc))
        write_json(cache, {"symbol": symbol, "interval": interval, "rows": rows})
        time.sleep(0.15)
    return [parse_kline(row, interval) for row in rows]


def fetch_klines(symbol: str, interval: str, start: datetime, end: datetime) -> list[list[Any]]:
    rows: list[list[Any]] = []
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1500,
        }
        payload = public_json("/fapi/v1/klines", params)
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + interval_ms(interval)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
    unique = {int(row[0]): row for row in rows}
    return [unique[key] for key in sorted(unique)]


def public_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{API}{path}?{urlencode(params)}"
    with urlopen(url, timeout=25) as response:
        return json.loads(response.read())


def parse_kline(row: list[Any], interval: str) -> dict[str, Any]:
    open_time = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
    return {
        "open_time_ms": int(row[0]),
        "open_time_cst": open_time.astimezone(TZ_CST).strftime("%Y-%m-%d %H:%M"),
        "interval": interval,
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def enrich(rows: list[dict[str, Any]]) -> None:
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    for i, row in enumerate(rows):
        rng = max(row["high"] - row["low"], 0.00000001)
        row["return_1h_pct"] = pct(row["close"], row["open"])
        for hours in [2, 3, 4, 6, 12, 24]:
            row[f"return_{hours}h_pct"] = pct(row["close"], closes[i - hours]) if i >= hours else None
        row["ema12"] = ema(closes[: i + 1], 12)
        row["ema24"] = ema(closes[: i + 1], 24)
        row["sma20"] = statistics.mean(closes[max(0, i - 19): i + 1])
        row["atr14_pct"] = atr_pct(rows, i, 14)
        row["volume_ratio_24h"] = row["volume"] / max(statistics.mean(volumes[max(0, i - 23): i + 1]), 0.00000001)
        row["close_location"] = (row["close"] - row["low"]) / rng
        row["body_to_range"] = abs(row["close"] - row["open"]) / rng
        if i >= 24:
            hi = max(x["high"] for x in rows[i - 24:i])
            lo = min(x["low"] for x in rows[i - 24:i])
            row["range_24h_pct"] = (hi / lo - 1) * 100 if lo else None
            row["range_position_24h"] = (row["close"] - lo) / max(hi - lo, 0.00000001)
        else:
            row["range_24h_pct"] = None
            row["range_position_24h"] = None


def build_specs() -> list[CandidateSpec]:
    return [
        CandidateSpec(
            candidate_id="CPM-MULTI-LONG-001",
            strategy_family="cpm_multi_symbol_pullback_continuation",
            side="long",
            timeframes=["1h signal", "5m path"],
            entry_rule="Uptrend context, 6h positive pressure, controlled 1h pullback, close not near low.",
            stop_rule="Below recent 4h low capped at 2.2%.",
            tp_rule="1.6R target capped near 4.5%.",
            time_stop="6h time stop.",
            cooldown_hours=4,
            max_holding_hours=6,
            symbols=["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=cpm_long_selector,
            stop_target=cpm_long_stop_target,
            research_question="Can CPM expand from a single ETH short observation into a multi-symbol pullback continuation family?",
            intended_role="main pullback continuation trial candidate",
        ),
        CandidateSpec(
            candidate_id="CPM-MULTI-SHORT-001",
            strategy_family="cpm_multi_symbol_pullback_continuation",
            side="short",
            timeframes=["1h signal", "5m path"],
            entry_rule="Downtrend context, 6h downside pressure, weak rebound failure, close not near high.",
            stop_rule="Above recent 4h high capped at 2.2%.",
            tp_rule="1.5R target capped near 3.8%.",
            time_stop="4h time stop.",
            cooldown_hours=4,
            max_holding_hours=4,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=cpm_short_selector,
            stop_target=cpm_short_stop_target,
            research_question="Can CPM short become a multi-symbol weak continuation family instead of ETH-only?",
            intended_role="short-window pullback failure trial candidate",
        ),
        CandidateSpec(
            candidate_id="MI-RS-IMPULSE-001",
            strategy_family="relative_strength_impulse",
            side="long",
            timeframes=["1h signal", "6h/24h relative strength", "5m path"],
            entry_rule="Symbol outperforms BTC on 6h and 24h, with volume/range confirmation and 1h impulse close.",
            stop_rule="Below impulse base capped at 2.8%.",
            tp_rule="1.8R target capped near 6%.",
            time_stop="8h time stop.",
            cooldown_hours=6,
            max_holding_hours=8,
            symbols=["SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "ETHUSDT"],
            selector=mi_selector,
            stop_target=mi_stop_target,
            research_question="Should MI-001 / relative strength impulse become a formal trial candidate or merge into MPG?",
            intended_role="independent or MPG-subcapability momentum ignition candidate",
        ),
        CandidateSpec(
            candidate_id="EARLY-RECLAIM-LONG-001",
            strategy_family="early_reclaim_long",
            side="long",
            timeframes=["1h signal", "2h/4h reclaim", "5m path"],
            entry_rule="Prior weakness, reclaim above SMA20 or local breakdown level, strong close, false reclaim filter.",
            stop_rule="Below reclaim base capped at 2.4%.",
            tp_rule="1.7R target capped near 5%.",
            time_stop="8h time stop.",
            cooldown_hours=6,
            max_holding_hours=8,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=early_reclaim_selector,
            stop_target=early_reclaim_stop_target,
            research_question="Can early reclaim long catch the first recovery leg missed by MPG/CPM?",
            intended_role="July-upside recovery watcher or trial candidate",
        ),
        CandidateSpec(
            candidate_id="MPG-HIGH-BETA-LONG-001",
            strategy_family="mpg_high_elasticity_expansion",
            side="long",
            timeframes=["1h signal", "5m path"],
            entry_rule="High-beta symbol with 1h/6h momentum ignition, EMA alignment, range/volume confirmation.",
            stop_rule="Below impulse base capped at 3.0%.",
            tp_rule="1.8R target capped near 6%.",
            time_stop="8h time stop.",
            cooldown_hours=6,
            max_holding_hours=8,
            symbols=["SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT"],
            selector=mpg_selector,
            stop_target=mpg_stop_target,
            research_question="Should MPG primary scope expand to SOL / AVAX / SUI / OP?",
            intended_role="high-elasticity momentum continuation candidate",
        ),
        CandidateSpec(
            candidate_id="SOR-MULTI-SESSION-BREAKOUT-001",
            strategy_family="session_opening_range_breakout",
            side="long",
            timeframes=["1h session signal", "5m path"],
            entry_rule="Session breakout above prior 4h opening range with follow-through and volume confirmation.",
            stop_rule="Below range midpoint/low capped at 2.0%.",
            tp_rule="1.5R target capped near 4.5%.",
            time_stop="4h time stop.",
            cooldown_hours=4,
            max_holding_hours=4,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            selector=sor_selector,
            stop_target=sor_stop_target,
            research_question="Should SOR expand from BTC/ETH to SOL/AVAX session breakout?",
            intended_role="session breakout watcher scope candidate",
        ),
        CandidateSpec(
            candidate_id="BRF2-WEAK-MARKET-SHORT-001",
            strategy_family="bear_rebound_failure_short",
            side="short",
            timeframes=["1h failed rebound", "5m path"],
            entry_rule="Weak trend, prior rebound, bearish rejection candle, close below EMA12.",
            stop_rule="Above rebound high capped at 2.5%.",
            tp_rule="1.7R target capped near 5%.",
            time_stop="6h time stop.",
            cooldown_hours=6,
            max_holding_hours=6,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=brf2_selector,
            stop_target=brf2_stop_target,
            research_question="Is BRF2 only weak-market standby, or a clearer short trial candidate?",
            intended_role="weak-market short reserve candidate",
        ),
        CandidateSpec(
            candidate_id="RBR2-RANGE-REVERSION-SHORT-001",
            strategy_family="range_mean_reversion",
            side="short",
            timeframes=["1h range rejection", "5m path"],
            entry_rule="Low-trend 24h range, upper range rejection, short toward mid-range.",
            stop_rule="Above range high capped at 1.6%.",
            tp_rule="Range midline or 1.4R, whichever is closer.",
            time_stop="6h time stop.",
            cooldown_hours=4,
            max_holding_hours=6,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=rbr2_selector,
            stop_target=rbr2_stop_target,
            research_question="Can RBR2 move from role candidate to tradable mean-reversion trial?",
            intended_role="range-regime role candidate or low-loss trial",
        ),
        CandidateSpec(
            candidate_id="CPM-SOL-SHORT-001",
            strategy_family="cpm_multi_symbol_pullback_continuation_filtered",
            side="short",
            timeframes=["1h signal", "5m path"],
            entry_rule="SOL-only CPM short continuation with original CPM short rule and execution cooldown.",
            stop_rule="Above recent 4h high capped at 2.2%.",
            tp_rule="1.5R target capped near 3.8%.",
            time_stop="4h time stop.",
            cooldown_hours=4,
            max_holding_hours=4,
            symbols=["SOLUSDT"],
            selector=cpm_short_selector,
            stop_target=cpm_short_stop_target,
            research_question="Does the CPM short edge concentrate in SOL enough to form a scoped trial candidate?",
            intended_role="single-symbol short-window trial candidate",
        ),
        CandidateSpec(
            candidate_id="MPG-SOL-HIGH-BETA-LONG-001",
            strategy_family="mpg_high_elasticity_expansion_filtered",
            side="long",
            timeframes=["1h signal", "5m path"],
            entry_rule="SOL-only high-beta momentum ignition with EMA and volume/range confirmation.",
            stop_rule="Below impulse base capped at 3.0%.",
            tp_rule="1.8R target capped near 6%.",
            time_stop="8h time stop.",
            cooldown_hours=6,
            max_holding_hours=8,
            symbols=["SOLUSDT"],
            selector=mpg_selector,
            stop_target=mpg_stop_target,
            research_question="Is SOL the only MPG high-beta expansion lane worth trial review now?",
            intended_role="scoped MPG symbol expansion candidate",
        ),
        CandidateSpec(
            candidate_id="BRF2-QUALITY-BASKET-SHORT-001",
            strategy_family="bear_rebound_failure_short_filtered",
            side="short",
            timeframes=["1h failed rebound", "5m path"],
            entry_rule="BRF2 failed rebound short on historically cleaner symbols, excluding Europe session.",
            stop_rule="Above rebound high capped at 2.5%.",
            tp_rule="1.7R target capped near 5%.",
            time_stop="6h time stop.",
            cooldown_hours=6,
            max_holding_hours=6,
            symbols=["SUIUSDT", "AVAXUSDT", "SOLUSDT", "BNBUSDT", "ETHUSDT"],
            selector=brf2_quality_selector,
            stop_target=brf2_stop_target,
            research_question="Can BRF2 become a clearer short candidate if noisy OP/BTC/Europe slices are disabled?",
            intended_role="weak-market short trial/watch candidate",
        ),
        CandidateSpec(
            candidate_id="MI-ASIA-RS-IMPULSE-001",
            strategy_family="relative_strength_impulse_filtered",
            side="long",
            timeframes=["1h signal", "6h/24h relative strength", "Asia session", "5m path"],
            entry_rule="Relative-strength impulse restricted to Asia session where replay shows cleaner continuation.",
            stop_rule="Below impulse base capped at 2.8%.",
            tp_rule="1.8R target capped near 6%.",
            time_stop="8h time stop.",
            cooldown_hours=6,
            max_holding_hours=8,
            symbols=["SOLUSDT", "AVAXUSDT", "OPUSDT", "ETHUSDT"],
            selector=mi_asia_selector,
            stop_target=mi_stop_target,
            research_question="Can MI become a watcher or trial candidate by adding session discipline?",
            intended_role="relative-strength watcher scope candidate",
        ),
        CandidateSpec(
            candidate_id="CPM-ASIA-SHORT-001",
            strategy_family="cpm_multi_symbol_pullback_continuation_filtered",
            side="short",
            timeframes=["1h signal", "Asia session", "5m path"],
            entry_rule="CPM short continuation restricted to Asia session across major/high-beta symbols.",
            stop_rule="Above recent 4h high capped at 2.2%.",
            tp_rule="1.5R target capped near 3.8%.",
            time_stop="4h time stop.",
            cooldown_hours=4,
            max_holding_hours=4,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT", "BNBUSDT"],
            selector=cpm_short_asia_selector,
            stop_target=cpm_short_stop_target,
            research_question="Can the prior CPM Asia-session ETH finding generalize across symbols?",
            intended_role="watcher scope short-window candidate",
        ),
    ]


def replay_candidate(
    spec: CandidateSpec,
    candles_1h: dict[str, list[dict[str, Any]]],
    candles_5m: dict[str, list[dict[str, Any]]],
    btc_by_time: dict[str, dict[str, Any]],
    end: datetime,
) -> dict[str, Any]:
    all_events = []
    for symbol in spec.symbols:
        rows = candles_1h[symbol]
        path_rows = candles_5m[symbol]
        path_by_time = sorted(path_rows, key=lambda row: row["open_time_ms"])
        for i, row in enumerate(rows):
            if i < 30 or i + 1 >= len(rows):
                continue
            if not spec.selector(row, rows, i, btc_by_time):
                continue
            event = build_event(spec, symbol, rows, i)
            evaluated = evaluate_event(event, path_by_time)
            all_events.append(evaluated)
    all_events.sort(key=lambda item: (dt_cst(item["signal_time_cst"]), item["symbol"]))
    windows: dict[str, Any] = {}
    for days in WINDOW_DAYS:
        start = end - timedelta(days=days)
        raw = [event for event in all_events if start <= dt_cst(event["signal_time_cst"]) <= end]
        executed = apply_execution_shape(raw, spec.cooldown_hours)
        windows[f"{days}d"] = summarize_window(raw, executed)
    return {
        "windows": windows,
        "all_event_count_38d": len(all_events),
        "path_realism": "5m path replay with conservative same-bar stop-first ordering",
        "fee_slippage_funding_assumption": {
            "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
            "funding": "ignored unless explicitly favorable; replay is after-cost proxy",
        },
    }


def build_event(spec: CandidateSpec, symbol: str, rows: list[dict[str, Any]], i: int) -> dict[str, Any]:
    signal = rows[i]
    entry = rows[i + 1]
    entry_price = entry["open"]
    stop, target = spec.stop_target(signal, rows, i, entry_price)
    return {
        "candidate_id": spec.candidate_id,
        "symbol": symbol,
        "side": spec.side,
        "signal_time_cst": signal["open_time_cst"],
        "entry_time_cst": entry["open_time_cst"],
        "entry_price_proxy": round(entry_price, 6),
        "stop_price_proxy": round(stop, 6),
        "tp_price_proxy": round(target, 6),
        "time_stop_hours": spec.max_holding_hours,
        "return_1h_pct": round(signal["return_1h_pct"], 4),
        "return_6h_pct": round(signal.get("return_6h_pct") or 0, 4),
        "return_12h_pct": round(signal.get("return_12h_pct") or 0, 4),
        "return_24h_pct": round(signal.get("return_24h_pct") or 0, 4),
        "atr14_pct": round(signal.get("atr14_pct") or 0, 4),
        "volume_ratio_24h": round(signal.get("volume_ratio_24h") or 0, 4),
        "session": session_of(signal["open_time_cst"]),
    }


def evaluate_event(event: dict[str, Any], path_rows: list[dict[str, Any]]) -> dict[str, Any]:
    entry_time = dt_cst(event["entry_time_cst"])
    end_time = entry_time + timedelta(hours=event["time_stop_hours"])
    path = [row for row in path_rows if entry_time <= dt_cst(row["open_time_cst"]) < end_time]
    entry = event["entry_price_proxy"]
    stop = event["stop_price_proxy"]
    target = event["tp_price_proxy"]
    side = event["side"]
    exit_price = path[-1]["close"] if path else entry
    exit_time = path[-1]["open_time_cst"] if path else event["entry_time_cst"]
    exit_reason = "time_stop"
    max_adverse = 0.0
    max_favorable = 0.0
    for row in path:
        if side == "long":
            max_adverse = max(max_adverse, (entry / row["low"] - 1) * 100)
            max_favorable = max(max_favorable, (row["high"] / entry - 1) * 100)
            stop_hit = row["low"] <= stop
            target_hit = row["high"] >= target
        else:
            max_adverse = max(max_adverse, (row["high"] / entry - 1) * 100)
            max_favorable = max(max_favorable, (entry / row["low"] - 1) * 100)
            stop_hit = row["high"] >= stop
            target_hit = row["low"] <= target
        if stop_hit and target_hit:
            exit_price = stop
            exit_time = row["open_time_cst"]
            exit_reason = "stop_first_same_bar_conservative"
            break
        if stop_hit:
            exit_price = stop
            exit_time = row["open_time_cst"]
            exit_reason = "stop_hit"
            break
        if target_hit:
            exit_price = target
            exit_time = row["open_time_cst"]
            exit_reason = "target_hit"
            break
    gross = (exit_price / entry - 1) * 100 if side == "long" else (entry / exit_price - 1) * 100
    return {
        **event,
        "exit_time_cst": exit_time,
        "exit_price_proxy": round(exit_price, 6),
        "exit_reason": exit_reason,
        "gross_return_pct": round(gross, 4),
        "after_cost_return_pct": round(gross - ROUND_TRIP_COST_PCT, 4),
        "max_adverse_excursion_pct": round(max(0.0, max_adverse), 4),
        "max_favorable_excursion_pct": round(max(0.0, max_favorable), 4),
    }


def apply_execution_shape(events: list[dict[str, Any]], cooldown_hours: int) -> list[dict[str, Any]]:
    cooldown: dict[str, datetime] = {}
    executed = []
    attempts_by_day: dict[tuple[str, str], int] = {}
    for event in sorted(events, key=lambda item: (dt_cst(item["entry_time_cst"]), item["symbol"])):
        entry_time = dt_cst(event["entry_time_cst"])
        key = event["symbol"]
        day_key = (event["symbol"], entry_time.strftime("%Y-%m-%d"))
        if cooldown.get(key) and entry_time < cooldown[key]:
            continue
        if attempts_by_day.get(day_key, 0) >= 3:
            continue
        executed.append(event)
        attempts_by_day[day_key] = attempts_by_day.get(day_key, 0) + 1
        cooldown[key] = max(dt_cst(event["exit_time_cst"]), entry_time + timedelta(hours=cooldown_hours))
    return executed


def summarize_window(raw: list[dict[str, Any]], executed: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [row["after_cost_return_pct"] for row in executed]
    raw_returns = [row["after_cost_return_pct"] for row in raw]
    return {
        "event_count": len(raw),
        "unique_event_count": len(executed),
        "symbol_distribution": count_by(executed, "symbol"),
        "raw_symbol_distribution": count_by(raw, "symbol"),
        "session_distribution": count_by(executed, "session"),
        "after_cost_return_sum": round(sum(returns), 4),
        "raw_after_cost_return_sum": round(sum(raw_returns), 4),
        "after_cost_median": round(percentile(returns, 50), 4),
        "after_cost_p75": round(percentile(returns, 75), 4),
        "after_cost_p90": round(percentile(returns, 90), 4),
        "positive_rate": safe_rate([value > 0 for value in returns]),
        "stop_hit_rate": safe_rate([row["exit_reason"].startswith("stop") for row in executed]),
        "target_hit_rate": safe_rate([row["exit_reason"] == "target_hit" for row in executed]),
        "max_drawdown_proxy": round(max_drawdown(returns), 4),
        "worst_5_events": sorted(
            (sample_event(row) for row in executed),
            key=lambda item: item["after_cost_return_pct"],
        )[:5],
        "best_5_events": sorted((sample_event(row) for row in executed), key=lambda item: item["after_cost_return_pct"], reverse=True)[:5],
    }


def classify_candidate(spec: CandidateSpec, replay: dict[str, Any]) -> dict[str, str]:
    w30 = replay["windows"]["30d"]
    w14 = replay["windows"]["14d"]
    p90 = w30["after_cost_p90"]
    median = w30["after_cost_median"]
    events = w30["unique_event_count"]
    dd = w30["max_drawdown_proxy"]
    stop = w30["stop_hit_rate"]
    if events >= 8 and median >= 0 and p90 >= 1.2 and dd > -12 and stop <= 0.35 and w14["after_cost_return_sum"] > 0:
        return {
            "status": "main_control_handoff_candidate",
            "status_reason": "30d and 14d execution-shaped replay show positive center or right-tail with bounded drawdown.",
            "main_control_absorbability": "Draft handoff pack generated; suitable for Tradeability Decision intake, not live authority.",
            "first_blocker": "owner_policy_required",
        }
    if events >= 5 and p90 >= 1.5 and dd > -15:
        return {
            "status": "watcher_scope_candidate",
            "status_reason": "Right-tail exists, but median/stability is not strong enough for handoff candidate.",
            "main_control_absorbability": "Absorb as watcher scope or replay-to-review lane.",
            "first_blocker": "asset_admission",
        }
    if spec.candidate_id.startswith("RBR2") and events >= 5:
        return {
            "status": "role_candidate",
            "status_reason": "Mean-reversion role can diversify trend strategies, but independent return quality is insufficient.",
            "main_control_absorbability": "Keep as portfolio role candidate / classifier input.",
            "first_blocker": "strategy_quality",
        }
    if spec.candidate_id.startswith("BRF2") and events >= 5:
        return {
            "status": "classifier_candidate",
            "status_reason": "Weak-market short evidence is better used as squeeze/failed-rebound classifier unless replay improves.",
            "main_control_absorbability": "Absorb as disable/weak-market classifier evidence.",
            "first_blocker": "strategy_quality",
        }
    if events == 0 or p90 <= 0:
        return {
            "status": "kill",
            "status_reason": "No useful right-tail in current replay window.",
            "main_control_absorbability": "Do not absorb except as negative evidence.",
            "first_blocker": "strategy_quality",
        }
    return {
        "status": "park",
        "status_reason": "Replay evidence is mixed and not strong enough for current intake.",
        "main_control_absorbability": "Park until new market window or rule revision.",
        "first_blocker": "strategy_quality",
    }


def handoff_pack(candidate: dict[str, Any]) -> dict[str, Any]:
    w30 = candidate["replay"]["windows"]["30d"]
    return {
        "candidate_id": candidate["candidate_id"],
        "strategy_family": candidate["strategy_family"],
        "side": candidate["side"],
        "symbol_scope": candidate["symbol_scope"],
        "timeframes": candidate["timeframes"],
        "entry_rule": candidate["entry_rule"],
        "exit_rule": candidate["exit_rule"],
        "stop_rule": candidate["stop_rule"],
        "tp_rule": candidate["tp_rule"],
        "time_stop": candidate["time_stop"],
        "cooldown": candidate["cooldown"],
        "risk_envelope": candidate["risk_envelope"],
        "required_facts_draft": candidate["required_facts_draft"],
        "disable_facts": candidate["disable_facts"],
        "replay_summary": {
            "event_count": w30["unique_event_count"],
            "after_cost_median": w30["after_cost_median"],
            "after_cost_p75": w30["after_cost_p75"],
            "after_cost_p90": w30["after_cost_p90"],
            "max_drawdown_proxy": w30["max_drawdown_proxy"],
        },
        "known_failure_modes": candidate["known_failure_modes"],
        "main_control_absorbability": candidate["main_control_absorbability"],
        **AUTHORITY_BOUNDARY,
    }


def build_report(end: datetime, candidates: list[dict[str, Any]], packs: list[dict[str, Any]], candles_1h: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            status_rank(c["status"]),
            c["replay"]["windows"]["30d"]["after_cost_p90"],
            c["replay"]["windows"]["30d"]["after_cost_return_sum"],
        ),
        reverse=True,
    )
    return {
        "schema": "brc.strategy_candidate_mining_replay_validation.v1",
        "status": "strategy_candidate_mining_replay_validation_ready_research_only",
        "task_id": TASK_ID,
        "version": VERSION,
        "generated_at_cst": end.strftime("%Y-%m-%d %H:%M"),
        **AUTHORITY_BOUNDARY,
        "objective": "Mine replay-validated StrategyGroup trial candidates for main-control absorption.",
        "source_scope": ["research/", "research/*/reports/", "research/*/data/", "public Binance USD-M candles"],
        "symbol_coverage": [to_contract(symbol) for symbol in SYMBOLS],
        "data_rows": {symbol: len(rows) for symbol, rows in candles_1h.items()},
        "replay_windows": [f"{days}d" for days in WINDOW_DAYS],
        "replay_method": "1h signal extraction, 5m path replay, after-cost proxy, cooldown-shaped unique events.",
        "candidates": ranked,
        "candidate_ranking": [
            {
                "candidate_id": c["candidate_id"],
                "status": c["status"],
                "30d_unique_events": c["replay"]["windows"]["30d"]["unique_event_count"],
                "30d_sum": c["replay"]["windows"]["30d"]["after_cost_return_sum"],
                "30d_median": c["replay"]["windows"]["30d"]["after_cost_median"],
                "30d_p90": c["replay"]["windows"]["30d"]["after_cost_p90"],
                "30d_dd": c["replay"]["windows"]["30d"]["max_drawdown_proxy"],
            }
            for c in ranked
        ],
        "main_control_handoff_candidates": [c for c in ranked if c["status"] == "main_control_handoff_candidate"],
        "watcher_scope_candidates": [c for c in ranked if c["status"] == "watcher_scope_candidate"],
        "park_or_kill": [c for c in ranked if c["status"] in {"park", "kill", "role_candidate", "classifier_candidate"}],
        "handoff_packs": packs,
        "safety_boundary": dict(AUTHORITY_BOUNDARY),
        "main_control_next_steps": [
            "Review main_control_handoff_candidates as Tradeability Decision intake only.",
            "Map RequiredFacts and disable facts before any runtime admission.",
            "Keep watcher_scope_candidates in replay-to-review or live watcher, not order authority.",
            "Record park/kill candidates as negative evidence to avoid repeated token burn.",
        ],
    }


def render_report_md(report: dict[str, Any]) -> str:
    lines = [
        "# Strategy Candidate Mining + Replay Validation",
        "",
        f"- **Task**: `{report['task_id']}`",
        f"- **Status**: `{report['status']}`",
        f"- **Generated CST**: `{report['generated_at_cst']}`",
        f"- **Symbols**: `{len(report['symbol_coverage'])}`",
        f"- **Candidates**: `{len(report['candidates'])}`",
        f"- **Main-control handoff candidates**: `{len(report['main_control_handoff_candidates'])}`",
        f"- **Watcher scope candidates**: `{len(report['watcher_scope_candidates'])}`",
        "",
        "## Candidate Ranking",
        "",
        "| Rank | Candidate | Status | 30d unique | 30d sum | Median | P75 | P90 | DD |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, c in enumerate(report["candidates"], 1):
        w = c["replay"]["windows"]["30d"]
        lines.append(
            f"| {i} | `{c['candidate_id']}` | `{c['status']}` | {w['unique_event_count']} | "
            f"{w['after_cost_return_sum']} | {w['after_cost_median']} | {w['after_cost_p75']} | {w['after_cost_p90']} | {w['max_drawdown_proxy']} |"
        )
    lines += [
        "",
        "## Direction Summary",
        "",
        "| Candidate | Family | Side | Symbols | Absorbability |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for c in report["candidates"]:
        lines.append(
            f"| `{c['candidate_id']}` | `{c['strategy_family']}` | `{c['side']}` | "
            f"{len(c['symbol_scope'])} | {c['main_control_absorbability']} |"
        )
    lines += [
        "",
        "## Main-Control Handoff Candidates",
        "",
    ]
    if report["main_control_handoff_candidates"]:
        for c in report["main_control_handoff_candidates"]:
            lines.append(f"- **{c['candidate_id']}**: {c['status_reason']}")
    else:
        lines.append("- None in this run.")
    lines += [
        "",
        "## Watcher Scope Candidates",
        "",
    ]
    if report["watcher_scope_candidates"]:
        for c in report["watcher_scope_candidates"]:
            lines.append(f"- **{c['candidate_id']}**: {c['status_reason']}")
    else:
        lines.append("- None in this run.")
    lines += [
        "",
        "## Park / Kill / Role / Classifier",
        "",
    ]
    for c in report["park_or_kill"]:
        lines.append(f"- **{c['candidate_id']}** `{c['status']}`: {c['status_reason']}")
    lines += [
        "",
        "## Safety Boundary",
        "",
        "```json",
        json.dumps(report["safety_boundary"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def render_index_md(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Strategy Candidate Mining Replay Validation Index",
        "",
        "- [Human report](strategy-candidate-mining-replay-validation.md)",
        "- [Machine report](strategy-candidate-mining-replay-validation.json)",
        f"- Candidates evaluated: `{len(report['candidates'])}`",
        f"- Symbols covered: `{len(report['symbol_coverage'])}`",
        f"- Main-control handoff candidates: `{len(report['main_control_handoff_candidates'])}`",
        f"- Watcher scope candidates: `{len(report['watcher_scope_candidates'])}`",
        "",
        "## Generated Handoff Drafts",
        "",
        *[
            f"- `../packs/{candidate['candidate_id']}-handoff-draft.json`"
            for candidate in report["main_control_handoff_candidates"]
        ],
        "",
    ])


def validate(report: dict[str, Any]) -> None:
    assert report["research_only"] is True
    assert report["execution_authority"] is False
    assert report["actionable_now"] is False
    assert report["exchange_write"] is False
    assert len(report["candidates"]) >= 6
    assert len(report["symbol_coverage"]) >= 7
    for candidate in report["candidates"]:
        for days in WINDOW_DAYS:
            key = f"{days}d"
            assert key in candidate["replay"]["windows"], candidate["candidate_id"]
            window = candidate["replay"]["windows"][key]
            for field in [
                "event_count",
                "unique_event_count",
                "symbol_distribution",
                "after_cost_median",
                "after_cost_p75",
                "after_cost_p90",
                "max_drawdown_proxy",
                "worst_5_events",
                "best_5_events",
            ]:
                assert field in window, (candidate["candidate_id"], key, field)


# Selectors.


def cpm_long_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return (
        row["close"] > row["ema12"] > row["ema24"]
        and value(row, "return_6h_pct") >= 0.8
        and -1.8 <= row["return_1h_pct"] <= 0.25
        and row["close_location"] >= 0.42
        and value(row, "atr14_pct") <= 2.8
    )


def cpm_short_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return (
        row["close"] < row["ema12"] < row["ema24"]
        and value(row, "return_6h_pct") <= -0.9
        and -0.1 >= row["return_1h_pct"] >= -2.8
        and row["close_location"] <= 0.58
        and value(row, "atr14_pct") <= 3.0
    )


def mi_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    b = btc.get(row["open_time_cst"])
    if not b:
        return False
    rs6 = value(row, "return_6h_pct") - value(b, "return_6h_pct")
    rs24 = value(row, "return_24h_pct") - value(b, "return_24h_pct")
    return (
        rs6 >= 0.9
        and rs24 >= 1.2
        and row["return_1h_pct"] >= 0.45
        and row["volume_ratio_24h"] >= 1.05
        and row["close_location"] >= 0.58
    )


def early_reclaim_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    prior_low = min(x["low"] for x in rows[i - 6:i])
    prior_high = max(x["high"] for x in rows[i - 4:i])
    reclaimed_sma = rows[i - 1]["close"] < rows[i - 1]["sma20"] and row["close"] > row["sma20"]
    reclaimed_local = row["close"] > prior_high and rows[i - 2]["close"] < prior_high
    return (
        value(row, "return_6h_pct") <= 1.2
        and (reclaimed_sma or reclaimed_local)
        and row["return_1h_pct"] >= 0.35
        and row["close_location"] >= 0.55
        and (row["close"] / prior_low - 1) * 100 <= 7.5
    )


def mpg_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return (
        row["return_1h_pct"] >= 0.75
        and value(row, "return_6h_pct") >= 1.4
        and row["close"] > row["ema12"] > row["ema24"]
        and row["volume_ratio_24h"] >= 1.0
        and value(row, "atr14_pct") >= 0.45
        and row["close_location"] >= 0.55
    )


def sor_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    hour = dt_cst(row["open_time_cst"]).hour
    if hour not in {8, 9, 15, 16, 21, 22}:
        return False
    prior_high = max(x["high"] for x in rows[i - 4:i])
    return (
        row["close"] > prior_high * 1.0015
        and row["return_1h_pct"] >= 0.35
        and row["volume_ratio_24h"] >= 1.0
        and row["close_location"] >= 0.60
    )


def brf2_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    prior_rebound = pct(rows[i - 1]["close"], rows[i - 4]["close"]) if i >= 4 else 0
    return (
        value(row, "return_24h_pct") <= 1.0
        and prior_rebound >= 0.45
        and row["return_1h_pct"] <= -0.35
        and row["close"] < row["ema12"]
        and row["close_location"] <= 0.45
    )


def brf2_quality_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return brf2_selector(row, rows, i, btc) and session_of(row["open_time_cst"]) != "europe"


def mi_asia_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return mi_selector(row, rows, i, btc) and session_of(row["open_time_cst"]) == "asia"


def cpm_short_asia_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return cpm_short_selector(row, rows, i, btc) and session_of(row["open_time_cst"]) == "asia"


def rbr2_selector(row: dict[str, Any], rows: list[dict[str, Any]], i: int, btc: dict[str, dict[str, Any]]) -> bool:
    return (
        value(row, "range_24h_pct") <= 6.5
        and abs(value(row, "return_24h_pct")) <= 2.5
        and value(row, "range_position_24h") >= 0.78
        and row["return_1h_pct"] <= 0.25
        and row["close_location"] <= 0.55
    )


# Stop/target calculators.


def cpm_long_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    recent_low = min(x["low"] for x in rows[i - 4:i + 1])
    stop = max(recent_low * 0.999, entry * 0.978)
    risk = max(entry - stop, entry * 0.006)
    return stop, entry + min(risk * 1.6, entry * 0.045)


def cpm_short_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    recent_high = max(x["high"] for x in rows[i - 4:i + 1])
    stop = min(recent_high * 1.001, entry * 1.022)
    risk = max(stop - entry, entry * 0.006)
    return stop, entry - min(risk * 1.5, entry * 0.038)


def mi_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    base = min(x["low"] for x in rows[i - 3:i + 1])
    stop = max(base * 0.998, entry * 0.972)
    risk = max(entry - stop, entry * 0.008)
    return stop, entry + min(risk * 1.8, entry * 0.06)


def early_reclaim_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    base = min(x["low"] for x in rows[i - 6:i + 1])
    stop = max(base * 0.999, entry * 0.976)
    risk = max(entry - stop, entry * 0.007)
    return stop, entry + min(risk * 1.7, entry * 0.05)


def mpg_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    base = min(x["low"] for x in rows[i - 3:i + 1])
    stop = max(base * 0.998, entry * 0.970)
    risk = max(entry - stop, entry * 0.008)
    return stop, entry + min(risk * 1.8, entry * 0.06)


def sor_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    range_low = min(x["low"] for x in rows[i - 4:i])
    stop = max(range_low * 0.999, entry * 0.980)
    risk = max(entry - stop, entry * 0.006)
    return stop, entry + min(risk * 1.5, entry * 0.045)


def brf2_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    high = max(x["high"] for x in rows[i - 4:i + 1])
    stop = min(high * 1.001, entry * 1.025)
    risk = max(stop - entry, entry * 0.007)
    return stop, entry - min(risk * 1.7, entry * 0.05)


def rbr2_stop_target(row: dict[str, Any], rows: list[dict[str, Any]], i: int, entry: float) -> tuple[float, float]:
    high = max(x["high"] for x in rows[i - 24:i + 1])
    low = min(x["low"] for x in rows[i - 24:i + 1])
    stop = min(high * 1.001, entry * 1.016)
    mid = (high + low) / 2
    risk = max(stop - entry, entry * 0.005)
    target = max(mid, entry - risk * 1.4)
    return stop, target


def required_facts(spec: CandidateSpec) -> list[str]:
    facts = [
        "fresh_closed_1h_candle",
        "latest_5m_path_candles",
        "latest_price",
        "mark_price",
        "available_balance",
        "active_position_same_symbol",
        "open_order_same_symbol",
        "min_notional",
        "qty_step",
        "price_tick",
        "cooldown_state",
    ]
    if "relative_strength" in spec.strategy_family:
        facts += ["btc_reference_return_6h", "btc_reference_return_24h", "symbol_volume_ratio"]
    if "session" in spec.strategy_family:
        facts += ["session_window", "opening_range_high_low"]
    if spec.side == "short":
        facts += ["funding_rate", "squeeze_disable_state"]
    return facts


def disable_facts(spec: CandidateSpec) -> list[str]:
    facts = [
        "active_position_same_symbol",
        "open_order_same_symbol",
        "cooldown_active",
        "stale_market_facts",
        "mark_last_divergence_abnormal",
    ]
    if spec.side == "short":
        facts += ["strong_reclaim_detected", "short_squeeze_risk_spike"]
    if "range" in spec.strategy_family:
        facts += ["range_breakout_confirmed_against_reversion"]
    return facts


def risk_envelope(spec: CandidateSpec) -> dict[str, Any]:
    return {
        "loss_unit": "0.5U-1.5U research unit depending on leverage scenario",
        "attempt_cap": "3 attempts/day/symbol, 6 attempts/7d/symbol",
        "max_consecutive_losses": "2 per symbol before pause",
        "leverage_scenarios": ["1x", "2x", "3x", "5x"],
        "capital_scope": "30U bounded trial candidate unless main control assigns lower scope",
    }


def failure_modes(spec: CandidateSpec, replay: dict[str, Any]) -> list[str]:
    w30 = replay["windows"]["30d"]
    modes = ["stale_or_clustered_signal", "fee_slippage_sensitivity", "false_breakout_or_reclaim"]
    if w30["stop_hit_rate"] > 0.3:
        modes.append("high_stop_hit_rate")
    if w30["max_drawdown_proxy"] < -10:
        modes.append("left_tail_drawdown_cluster")
    if max(w30["symbol_distribution"].values(), default=0) >= max(3, w30["unique_event_count"] * 0.6):
        modes.append("symbol_concentration")
    if spec.side == "short":
        modes.append("squeeze_or_reclaim_risk")
    return modes


def overlap_read(spec: CandidateSpec) -> str:
    if spec.candidate_id.startswith("CPM"):
        return "Potential overlap with MPG/MI momentum continuation; use cooldown and family priority."
    if spec.candidate_id.startswith("MI"):
        return "May merge into MPG if relative-strength adds no independent lift."
    if spec.candidate_id.startswith("MPG"):
        return "High overlap with MI; use as scope-expansion evidence."
    if spec.candidate_id.startswith("SOR"):
        return "Session-specific, lower overlap if session gate is preserved."
    if spec.candidate_id.startswith("RBR2"):
        return "Potential diversifier against trend strategies."
    if spec.candidate_id.startswith("BRF2"):
        return "Weak-market short overlaps with CPM short and failed-upside classifiers."
    return "No overlap assessment."


def sample_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "after_cost_return_pct": row["after_cost_return_pct"],
        "symbol": row["symbol"],
        "signal_time_cst": row["signal_time_cst"],
        "entry_time_cst": row["entry_time_cst"],
        "entry_price_proxy": row["entry_price_proxy"],
        "stop_price_proxy": row["stop_price_proxy"],
        "tp_price_proxy": row["tp_price_proxy"],
        "exit_reason": row["exit_reason"],
        "max_adverse_excursion_pct": row["max_adverse_excursion_pct"],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def safe_rate(values: list[bool]) -> float:
    if not values:
        return 0.0
    return round(sum(1 for value in values if value) / len(values), 4)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] * (c - k) + values[c] * (k - f)


def max_drawdown(returns: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for ret in returns:
        equity += ret
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def status_rank(status: str) -> int:
    return {
        "main_control_handoff_candidate": 6,
        "watcher_scope_candidate": 5,
        "replay_promising_needs_path_check": 4,
        "role_candidate": 3,
        "classifier_candidate": 2,
        "park": 1,
        "kill": 0,
    }.get(status, 0)


def session_of(time_cst: str) -> str:
    hour = dt_cst(time_cst).hour
    if 8 <= hour < 15:
        return "asia"
    if 15 <= hour < 21:
        return "europe"
    if 21 <= hour or hour < 2:
        return "us_late"
    return "post_us"


def interval_ms(interval: str) -> int:
    if interval == "1h":
        return 3_600_000
    if interval == "5m":
        return 300_000
    raise ValueError(interval)


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def atr_pct(rows: list[dict[str, Any]], index: int, period: int) -> float | None:
    if index < period:
        return None
    trs = []
    for i in range(index - period + 1, index + 1):
        prev_close = rows[i - 1]["close"] if i > 0 else rows[i]["close"]
        tr = max(rows[i]["high"] - rows[i]["low"], abs(rows[i]["high"] - prev_close), abs(rows[i]["low"] - prev_close))
        trs.append(tr / rows[i]["close"] * 100)
    return statistics.mean(trs)


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def value(row: dict[str, Any], key: str) -> float:
    raw = row.get(key)
    return 0.0 if raw is None else float(raw)


def dt_cst(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_CST)


def to_contract(symbol: str) -> str:
    return symbol.replace("USDT", "/USDT:USDT")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
