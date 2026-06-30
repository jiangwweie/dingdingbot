#!/usr/bin/env python3
"""Build recent counterfactual live-submit replay for four armed candidates.

This artifact replays recent public market candles through lightweight,
non-authority StrategyGroup trigger approximations. It is intentionally
review-only: replay signals cannot become live RequiredFacts, candidate
authorization, FinalGate input, Operation Layer evidence, exchange writes, or
real orders.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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


DEFAULT_TRADEABILITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.md"
)

SCHEMA = "brc.four_candidate_recent_live_submit_replay.v1"
SCOPE = "strategygroup_recent_counterfactual_live_submit_replay_non_authority"
BINANCE_KLINES_ENDPOINT = "https://api.binance.com/api/v3/klines"
COINBASE_CANDLES_ENDPOINT = "https://api.exchange.coinbase.com/products/{product}/candles"
WINDOW_DAYS = (3, 7, 14)
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT")
INTERVALS = ("1h", "15m")
FOUR_CANDIDATES = ("MPG-001", "BRF2-001", "SOR-001", "CPM-RO-001")
COINBASE_PRODUCTS = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "AVAXUSDT": "AVAX-USD",
    "SUIUSDT": "SUI-USD",
    "OPUSDT": "OP-USD",
    "BNBUSDT": "BNB-USD",
}
INTERVAL_SECONDS = {"1h": 3600, "15m": 900}


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tradeability-json", default=str(DEFAULT_TRADEABILITY_JSON)
    )
    parser.add_argument(
        "--market-data-json",
        help=(
            "Optional fixture/prefetched market data. Shape: "
            "{symbol:{interval:[[open_time,open,high,low,close,volume], ...]}}"
        ),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_recent_live_submit_replay(
        tradeability=_read_optional_json(Path(args.tradeability_json)),
        market_data=(
            _read_optional_json(Path(args.market_data_json))
            if args.market_data_json
            else _fetch_market_data()
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "review_signal_count": artifact["summary"][
                    "counterfactual_review_signal_count"
                ],
                "missed_opportunity_review_count": artifact["summary"][
                    "missed_opportunity_review_count"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == "recent_counterfactual_replay_ready" else 2


def build_recent_live_submit_replay(
    *,
    tradeability: dict[str, Any],
    market_data: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    candles = _parse_market_data(market_data)
    source_name = str(market_data.get("source") or "unknown_public_market_data")
    rows_by_id = {
        str(row.get("strategy_group_id") or ""): row
        for row in tradeability.get("decision_rows") or []
        if isinstance(row, dict)
    }
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    market_ready = bool(candles) and all(
        candles.get(symbol, {}).get("1h") for symbol in SYMBOLS[:4]
    )

    strategy_rows = [
        _strategy_row(strategy_group_id, rows_by_id.get(strategy_group_id, {}), candles)
        for strategy_group_id in FOUR_CANDIDATES
    ]
    mi_review = _mi_candidate_review(candles)
    review_signal_count = sum(
        window["counterfactual_fresh_signal_count"]
        for row in strategy_rows
        for window in row["window_results"]
    )
    missed_review_count = sum(
        len(window["missed_opportunity_review_events"])
        for row in strategy_rows
        for window in row["window_results"]
    )
    scope_review_ids = sorted(
        {
            row["strategy_group_id"]
            for row in strategy_rows
            if any(
                event["symbol_scope_review_required"]
                for window in row["window_results"]
                for event in window["counterfactual_events"]
            )
        }
    )
    return {
        "schema": SCHEMA,
        "scope": SCOPE,
        "status": (
            "recent_counterfactual_replay_ready"
            if market_ready
            else "recent_counterfactual_replay_market_data_incomplete"
        ),
        "generated_at_utc": generated,
        "data_sources": {
            "public_market_candles": {
                "provider": source_name,
                "binance_endpoint": BINANCE_KLINES_ENDPOINT,
                "coinbase_endpoint": COINBASE_CANDLES_ENDPOINT,
                "intervals": list(INTERVALS),
                "symbols": list(SYMBOLS),
                "source_role": "public_market_replay_input_not_live_signal",
            }
        },
        "current_tradeability_snapshot": [
            _tradeability_projection(rows_by_id.get(strategy_group_id, {}))
            for strategy_group_id in FOUR_CANDIDATES
        ],
        "summary": {
            "window_days": list(WINDOW_DAYS),
            "strategy_count": len(strategy_rows),
            "symbol_count": len(SYMBOLS),
            "counterfactual_review_signal_count": review_signal_count,
            "missed_opportunity_review_count": missed_review_count,
            "symbol_scope_review_strategy_ids": scope_review_ids,
            "counterfactual_live_submit_allowed_count": 0,
            "default_next_step": (
                "review_recent_counterfactual_signals_then_tune_symbol_scope_or_facts_without_granting_live_authority"
            ),
        },
        "strategy_rows": strategy_rows,
        "fifth_candidate_review": mi_review,
        "authority_boundary": {
            "artifact_role": "review_only_counterfactual_replay",
            "tradeability_decision_source": False,
            "runtime_safety_state_source": False,
            "replay_or_public_market_data_treated_as_live_signal": False,
            "live_required_facts_satisfied": False,
            "candidate_authorization_created": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "checks": {
            "market_data_present": market_ready,
            "four_candidates_present": all(
                strategy_group_id in rows_by_id for strategy_group_id in FOUR_CANDIDATES
            ),
            "replay_is_not_live_signal": True,
            "does_not_call_finalgate": True,
            "does_not_call_operation_layer": True,
            "does_not_call_exchange_write": True,
            "does_not_create_order": True,
        },
        "interaction": non_executing_interaction(
            "L0_local_recent_counterfactual_live_submit_replay"
        ),
        "safety_invariants": non_executing_safety_invariants(
            (
                "exchange_write_called",
                "order_created",
                "final_gate_called",
                "operation_layer_called",
                "preview_or_replay_treated_as_live_signal",
            ),
            include_authority_mirrors=False,
        ),
    }


def _strategy_row(
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    candles: dict[str, dict[str, list[Candle]]],
) -> dict[str, Any]:
    config = _strategy_config(strategy_group_id)
    window_results = [
        _window_result(strategy_group_id, config, candles, window_days)
        for window_days in WINDOW_DAYS
    ]
    first_review = next(
        (
            event
            for window in window_results
            for event in window["missed_opportunity_review_events"]
        ),
        {},
    )
    return {
        "strategy_group_id": strategy_group_id,
        "path_id": config["path_id"],
        "side": config["side"],
        "current_tradeability": _tradeability_projection(tradeability_row),
        "replay_symbol_universe": config["symbols"],
        "primary_symbol_scope": config["primary_scope"],
        "window_results": window_results,
        "symbol_scope_review_required": bool(first_review),
        "first_review_reason": str(first_review.get("review_reason") or ""),
        "next_action": _next_action(strategy_group_id, window_results),
    }


def _window_result(
    strategy_group_id: str,
    config: dict[str, Any],
    candles: dict[str, dict[str, list[Candle]]],
    window_days: int,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    per_symbol_results: list[dict[str, Any]] = []
    for symbol in config["symbols"]:
        symbol_events = _strategy_events(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            candles=candles.get(symbol, {}),
            window_days=window_days,
            primary_scope=config["primary_scope"],
        )
        per_symbol_results.append(
            _symbol_window_result(
                symbol=symbol,
                symbol_events=symbol_events,
                primary_scope=config["primary_scope"],
            )
        )
        events.extend(symbol_events)
    events = sorted(events, key=lambda event: event["event_time_utc"])
    review_events = [
        event
        for event in events
        if event["missed_opportunity_review_required"]
    ]
    blocker_counts: dict[str, int] = {}
    for event in events:
        blocker_counts[event["first_blocker_class"]] = (
            blocker_counts.get(event["first_blocker_class"], 0) + 1
        )
    return {
        "window_days": window_days,
        "counterfactual_fresh_signal_count": len(events),
        "missed_opportunity_review_count": len(review_events),
        "per_symbol_results": per_symbol_results,
        "counterfactual_events": events[:20],
        "missed_opportunity_review_events": review_events[:10],
        "first_blocker_counts": blocker_counts,
        "window_answer": _window_answer(strategy_group_id, events, review_events),
    }


def _symbol_window_result(
    *,
    symbol: str,
    symbol_events: list[dict[str, Any]],
    primary_scope: list[str],
) -> dict[str, Any]:
    blocker_counts: dict[str, int] = {}
    for event in symbol_events:
        blocker_counts[event["first_blocker_class"]] = (
            blocker_counts.get(event["first_blocker_class"], 0) + 1
        )
    missed_events = [
        event
        for event in symbol_events
        if event["missed_opportunity_review_required"]
    ]
    return {
        "symbol": symbol,
        "symbol_in_primary_scope": symbol in primary_scope,
        "counterfactual_fresh_signal_count": len(symbol_events),
        "missed_opportunity_review_count": len(missed_events),
        "symbol_scope_review_required": any(
            event["symbol_scope_review_required"] for event in symbol_events
        ),
        "first_event_time_utc": (
            symbol_events[0]["event_time_utc"] if symbol_events else ""
        ),
        "first_blocker_counts": blocker_counts,
    }


def _strategy_events(
    *,
    strategy_group_id: str,
    symbol: str,
    candles: dict[str, list[Candle]],
    window_days: int,
    primary_scope: list[str],
) -> list[dict[str, Any]]:
    hourly = candles.get("1h") or []
    fifteen = candles.get("15m") or []
    if not hourly:
        return []
    cutoff = hourly[-1].open_time_ms - window_days * 24 * 60 * 60 * 1000
    if strategy_group_id == "SOR-001":
        raw_events = _sor_events(symbol=symbol, candles=fifteen, cutoff_ms=cutoff)
    else:
        raw_events = []
        for index in range(55, len(hourly)):
            candle = hourly[index]
            if candle.open_time_ms < cutoff:
                continue
            if _signal_present(strategy_group_id, hourly, index, symbol):
                raw_events.append(
                    {
                        "event_time_ms": candle.open_time_ms,
                        "signal_strength": _signal_strength(hourly, index),
                        "reason": _signal_reason(strategy_group_id),
                    }
                )
    return [
        _counterfactual_event(
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            event=event,
            primary_scope=primary_scope,
        )
        for event in raw_events
    ]


def _counterfactual_event(
    *,
    strategy_group_id: str,
    symbol: str,
    event: dict[str, Any],
    primary_scope: list[str],
) -> dict[str, Any]:
    in_primary_scope = symbol in primary_scope
    symbol_scope_review_required = (
        not in_primary_scope and strategy_group_id != "BRF2-001"
    )
    if not in_primary_scope and strategy_group_id in {"MPG-001", "CPM-RO-001", "SOR-001"}:
        first_blocker = "symbol_scope_review_required"
        blocker_owner = "engineering"
        review_reason = "fresh_like_signal_on_non_primary_replay_symbol"
    elif strategy_group_id == "BRF2-001":
        first_blocker = "short_squeeze_risk_state_disable_active"
        blocker_owner = "market"
        review_reason = "short_signal_blocked_by_squeeze_disable_context"
    else:
        first_blocker = "action_time_required_facts_not_replayed"
        blocker_owner = "runtime"
        review_reason = "fresh_like_signal_requires_live_action_time_facts"
    return {
        "event_time_utc": _iso(event["event_time_ms"]),
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "counterfactual_fresh_signal_present": True,
        "signal_strength": round(float(event.get("signal_strength") or 0.0), 4),
        "signal_reason": event["reason"],
        "symbol_in_primary_scope": in_primary_scope,
        "symbol_scope_review_required": symbol_scope_review_required,
        "counterfactual_live_submit_allowed": False,
        "first_blocker_class": first_blocker,
        "first_blocker_owner": blocker_owner,
        "missed_opportunity_review_required": (
            strategy_group_id != "BRF2-001"
        ),
        "review_reason": review_reason,
        "gate_breakdown": {
            "fresh_signal_present_in_replay": True,
            "required_facts_replay_shape_present": True,
            "candidate_authorization_shape_can_be_prepared": True,
            "live_action_time_required_facts_present": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write": False,
            "order_created": False,
        },
    }


def _signal_present(
    strategy_group_id: str,
    hourly: list[Candle],
    index: int,
    symbol: str,
) -> bool:
    close = hourly[index].close
    sma20 = _sma(hourly, index, 20)
    sma50 = _sma(hourly, index, 50)
    ret6 = _return_pct(hourly, index, 6)
    ret24 = _return_pct(hourly, index, 24)
    volume_ratio = _volume_ratio(hourly, index, 20)
    if strategy_group_id == "MPG-001":
        return close > sma20 > sma50 and ret24 >= 1.8 and ret6 >= 0.4 and volume_ratio >= 0.7
    if strategy_group_id == "CPM-RO-001":
        pullback_low = min(c.low for c in hourly[max(0, index - 12): index + 1])
        reclaim_level = max(c.high for c in hourly[max(0, index - 5): index])
        pullback_depth_normal = sma20 * 0.94 <= pullback_low <= sma20 * 1.025
        reclaim_confirmed = close > reclaim_level and ret6 >= 0.5
        return close > sma20 > sma50 and pullback_depth_normal and reclaim_confirmed
    if strategy_group_id == "BRF2-001":
        return close < sma20 < sma50 and ret24 <= -1.6 and ret6 <= -0.3
    return False


def _sor_events(symbol: str, candles: list[Candle], cutoff_ms: int) -> list[dict[str, Any]]:
    by_day: dict[str, list[Candle]] = {}
    for candle in candles:
        if candle.open_time_ms < cutoff_ms:
            continue
        day = datetime.fromtimestamp(candle.open_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(candle)
    events: list[dict[str, Any]] = []
    for day, rows in sorted(by_day.items()):
        opening = [
            candle
            for candle in rows
            if 13 * 60 + 30 <= _minute_of_day(candle.open_time_ms) < 14 * 60 + 30
        ]
        follow = [
            candle
            for candle in rows
            if 14 * 60 + 30 <= _minute_of_day(candle.open_time_ms) <= 18 * 60
        ]
        if len(opening) < 3 or not follow:
            continue
        opening_high = max(c.high for c in opening)
        opening_low = min(c.low for c in opening)
        opening_range = max((opening_high - opening_low) / opening_low, 0)
        for candle in follow:
            follow_return = (candle.close - opening_high) / opening_high
            if candle.close > opening_high and follow_return >= 0.006 and opening_range >= 0.002:
                events.append(
                    {
                        "event_time_ms": candle.open_time_ms,
                        "signal_strength": follow_return * 100,
                        "reason": "session_opening_range_up_break_follow_through",
                    }
                )
                break
    return events


def _mi_candidate_review(candles: dict[str, dict[str, list[Candle]]]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for symbol in ("SOLUSDT", "BNBUSDT", "ETHUSDT", "AVAXUSDT", "SUIUSDT"):
        hourly = candles.get(symbol, {}).get("1h") or []
        if len(hourly) < 30:
            continue
        cutoff = hourly[-1].open_time_ms - 14 * 24 * 60 * 60 * 1000
        for index in range(24, len(hourly)):
            if hourly[index].open_time_ms < cutoff:
                continue
            ret6 = _return_pct(hourly, index, 6)
            ret24 = _return_pct(hourly, index, 24)
            if ret6 >= 2.6 and ret24 >= 3.5 and _volume_ratio(hourly, index, 20) >= 0.8:
                events.append(
                    {
                        "event_time_utc": _iso(hourly[index].open_time_ms),
                        "symbol": symbol,
                        "ret6_pct": round(ret6, 3),
                        "ret24_pct": round(ret24, 3),
                    }
                )
    return {
        "candidate_id": "MI-001",
        "review_recommendation": (
            "open_formal_candidate_replay_review"
            if len(events) >= 2
            else "keep_on_watchlist"
        ),
        "recent_impulse_event_count": len(events),
        "events": events[:20],
        "authority_boundary": "review_only; no registry admission, tier change, or live authority",
    }


def _strategy_config(strategy_group_id: str) -> dict[str, Any]:
    configs = {
        "MPG-001": {
            "path_id": "MPG-LONG",
            "side": "long",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT", "OPUSDT"],
            "primary_scope": ["BTCUSDT", "ETHUSDT"],
        },
        "BRF2-001": {
            "path_id": "BRF2-SHORT",
            "side": "short",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            "primary_scope": ["BTCUSDT", "ETHUSDT"],
        },
        "SOR-001": {
            "path_id": "SOR-LONG",
            "side": "long",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            "primary_scope": ["BTCUSDT", "ETHUSDT"],
        },
        "CPM-RO-001": {
            "path_id": "CPM-LONG",
            "side": "long",
            "symbols": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "primary_scope": ["ETHUSDT"],
        },
    }
    return configs[strategy_group_id]


def _next_action(strategy_group_id: str, window_results: list[dict[str, Any]]) -> str:
    review_count = sum(row["missed_opportunity_review_count"] for row in window_results)
    if strategy_group_id == "BRF2-001":
        return "keep_brf2_armed_but_respect_short_squeeze_disable"
    if review_count:
        return "review_symbol_scope_and_fact_classifier_for_recent_counterfactual_signals"
    return "continue_armed_observation_waiting_for_market"


def _window_answer(
    strategy_group_id: str,
    events: list[dict[str, Any]],
    review_events: list[dict[str, Any]],
) -> str:
    if not events:
        return "no_counterfactual_fresh_signal_found_in_window"
    if strategy_group_id == "BRF2-001":
        return "short_counterfactual_seen_but_squeeze_disable_keeps_no_trade_reasonable"
    if review_events:
        return "counterfactual_fresh_like_signal_requires_symbol_scope_or_fact_review"
    return "fresh_like_signal_would_reach_action_time_fact_boundary_only"


def _tradeability_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or ""),
        "stage": str(row.get("stage") or ""),
        "decision": str(row.get("decision") or ""),
        "can_trade_now": row.get("can_trade_now") is True,
        "first_blocker_class": str(row.get("first_blocker_class") or ""),
        "blocker_owner": str(row.get("blocker_owner") or ""),
    }


def _parse_market_data(payload: dict[str, Any]) -> dict[str, dict[str, list[Candle]]]:
    root = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else payload
    parsed: dict[str, dict[str, list[Candle]]] = {}
    for symbol, intervals in root.items():
        if not isinstance(intervals, dict):
            continue
        parsed[str(symbol)] = {}
        for interval, rows in intervals.items():
            parsed[str(symbol)][str(interval)] = [_parse_candle(row) for row in rows or []]
    return parsed


def _parse_candle(row: Any) -> Candle:
    return Candle(
        open_time_ms=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )


def _fetch_market_data() -> dict[str, Any]:
    try:
        return {
            "source": "binance_spot_public_klines",
            "symbols": {
                symbol: {
                    interval: _fetch_binance_klines(symbol=symbol, interval=interval)
                    for interval in INTERVALS
                }
                for symbol in SYMBOLS
            },
        }
    except Exception as exc:
        return {
            "source": "coinbase_exchange_public_candles_fallback",
            "primary_source_error": f"{type(exc).__name__}:{exc}",
            "symbols": {
                symbol: {
                    interval: _fetch_coinbase_candles(symbol=symbol, interval=interval)
                    for interval in INTERVALS
                }
                for symbol in SYMBOLS
            },
        }


def _fetch_binance_klines(*, symbol: str, interval: str) -> list[list[Any]]:
    limit = 1000 if interval == "15m" else 400
    params = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    with urlopen(f"{BINANCE_KLINES_ENDPOINT}?{params}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_coinbase_candles(*, symbol: str, interval: str) -> list[list[Any]]:
    product = COINBASE_PRODUCTS[symbol]
    granularity = INTERVAL_SECONDS[interval]
    end_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = end_ts - 15 * 24 * 60 * 60
    max_span = granularity * 290
    rows: list[list[Any]] = []
    cursor = start_ts
    while cursor < end_ts:
        chunk_end = min(cursor + max_span, end_ts)
        params = urlencode(
            {
                "granularity": granularity,
                "start": datetime.fromtimestamp(cursor, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(chunk_end, tz=timezone.utc).isoformat(),
            }
        )
        request = Request(
            f"{COINBASE_CANDLES_ENDPOINT.format(product=product)}?{params}",
            headers={"User-Agent": "brc-recent-counterfactual-replay/1.0"},
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows.extend(_coinbase_to_kline(row) for row in payload)
        cursor = chunk_end
    dedup = {int(row[0]): row for row in rows}
    return [dedup[key] for key in sorted(dedup)]


def _coinbase_to_kline(row: list[Any]) -> list[Any]:
    timestamp_s, low, high, open_, close, volume = row
    return [
        int(timestamp_s) * 1000,
        str(open_),
        str(high),
        str(low),
        str(close),
        str(volume),
    ]


def _sma(candles: list[Candle], index: int, period: int) -> float:
    rows = candles[index - period + 1 : index + 1]
    return sum(c.close for c in rows) / period


def _return_pct(candles: list[Candle], index: int, lookback: int) -> float:
    previous = candles[max(0, index - lookback)].close
    if previous == 0:
        return 0.0
    return (candles[index].close - previous) / previous * 100


def _volume_ratio(candles: list[Candle], index: int, period: int) -> float:
    rows = candles[index - period + 1 : index + 1]
    avg = sum(c.volume for c in rows) / period
    return candles[index].volume / avg if avg else 0.0


def _signal_strength(candles: list[Candle], index: int) -> float:
    return max(_return_pct(candles, index, 6), _return_pct(candles, index, 24))


def _signal_reason(strategy_group_id: str) -> str:
    return {
        "MPG-001": "relative_strength_momentum_above_sma20_sma50",
        "CPM-RO-001": "pullback_reclaim_in_intact_uptrend",
        "BRF2-001": "bear_rally_failure_short_like_structure",
    }.get(strategy_group_id, "counterfactual_signal")


def _minute_of_day(open_time_ms: int) -> int:
    dt = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
    return dt.hour * 60 + dt.minute


def _iso(open_time_ms: int) -> str:
    return datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).isoformat()


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Four-Candidate Recent Counterfactual Live-Submit Replay",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Scope: `{artifact['scope']}`",
        f"- Review signals: `{artifact['summary']['counterfactual_review_signal_count']}`",
        f"- Missed-opportunity review count: `{artifact['summary']['missed_opportunity_review_count']}`",
        f"- Counterfactual live-submit allowed: `{artifact['summary']['counterfactual_live_submit_allowed_count']}`",
        f"- Output JSON: `{output_json}`",
        "",
        "## Current Tradeability",
        "",
        "| Strategy | Stage | Decision | First blocker | Owner |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in artifact["current_tradeability_snapshot"]:
        lines.append(
            f"| `{row['strategy_group_id']}` | `{row['stage']}` | `{row['decision']}` | `{row['first_blocker_class']}` | `{row['blocker_owner']}` |"
        )
    lines.extend(
        [
            "",
            "## Replay Summary",
            "",
            "| Strategy | 3d signals/review | 7d signals/review | 14d signals/review | Next action |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in artifact["strategy_rows"]:
        cells = []
        for window in row["window_results"]:
            cells.append(
                f"`{window['counterfactual_fresh_signal_count']}/{window['missed_opportunity_review_count']}`"
            )
        lines.append(
            f"| `{row['strategy_group_id']}` | {cells[0]} | {cells[1]} | {cells[2]} | `{row['next_action']}` |"
        )
    lines.extend(
        [
            "",
            "## Per-Symbol Replay",
            "",
            "| Strategy | Symbol | Primary scope | 3d signals/review | 7d signals/review | 14d signals/review |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in artifact["strategy_rows"]:
        symbols = row["replay_symbol_universe"]
        for symbol in symbols:
            cells = []
            primary_scope = False
            for window in row["window_results"]:
                symbol_result = next(
                    item
                    for item in window["per_symbol_results"]
                    if item["symbol"] == symbol
                )
                primary_scope = bool(symbol_result["symbol_in_primary_scope"])
                cells.append(
                    f"`{symbol_result['counterfactual_fresh_signal_count']}/{symbol_result['missed_opportunity_review_count']}`"
                )
            lines.append(
                f"| `{row['strategy_group_id']}` | `{symbol}` | `{str(primary_scope).lower()}` | {cells[0]} | {cells[1]} | {cells[2]} |"
            )
    fifth = artifact["fifth_candidate_review"]
    lines.extend(
        [
            "",
            "## Fifth Candidate Review",
            "",
            f"- Candidate: `{fifth['candidate_id']}`",
            f"- Recommendation: `{fifth['review_recommendation']}`",
            f"- Recent impulse events: `{fifth['recent_impulse_event_count']}`",
            "",
            "## Safety",
            "",
            "- Replay/public market data is not a live signal.",
            "- No FinalGate, Operation Layer, exchange write, order creation, live profile change, or order-sizing change.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
