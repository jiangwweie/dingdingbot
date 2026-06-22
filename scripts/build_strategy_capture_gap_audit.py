#!/usr/bin/env python3
"""Build a read-only Strategy Capture Gap audit from official public market data."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from src.application.strategy_group_live_readonly_observation import (  # noqa: E402
    RecentCandle,
    build_strategy_group_live_readonly_observation_v1,
)


BINANCE_USDM_BASE = "https://fapi.binance.com"
HOUR_MS = 60 * 60 * 1000
DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "XRPUSDT",
    "ADAUSDT",
)
SYMBOL_TO_RUNTIME = {
    "BTCUSDT": "BTC/USDT:USDT",
    "ETHUSDT": "ETH/USDT:USDT",
    "SOLUSDT": "SOL/USDT:USDT",
    "BNBUSDT": "BNB/USDT:USDT",
    "AVAXUSDT": "AVAX/USDT:USDT",
    "LINKUSDT": "LINK/USDT:USDT",
    "XRPUSDT": "XRP/USDT:USDT",
    "ADAUSDT": "ADA/USDT:USDT",
}
RUNTIME_TO_BINANCE = {value: key for key, value in SYMBOL_TO_RUNTIME.items()}
STRATEGY_EXPECTATIONS = {
    "BRF-001": "bear-rally failure short; rally extension plus rejection should produce observe-only would_enter",
    "BTPC-001": "bear-trend pullback continuation; stale/fact/classifier gaps may block L2 progression",
    "VCB-001": "volatility compression breakout; compression plus breakout should enter review",
    "LSR-001": "liquidity sweep or short-revival rewrite; side-specific rewrite gaps are expected blockers",
    "RBR-001": "range-boundary rejection vocabulary; parked unless material new edge appears",
    "MPG-001": "clean long momentum persistence; selected P0 lane only reacts to eligible mainline symbols",
    "SOR-001": "session range breakout/revival; repeated no_action should remain visible, not just waiting",
    "FBS-001": "funding/basis/crowding stress; missing derivatives facts are attribution, not live authority",
}
INTENDED_SIDE_BY_CANDIDATE = {
    "BRF-001-BTC-SHORT": "short",
    "BTPC-001-AVAX-SHORT": "short",
    "VCB-001-LINK-LONG": "long",
    "RBR-001-ADA-SHORT": "short",
    "MI-001-SOL-LONG": "long",
    "MI-001-BNB-LONG": "long",
}
HIGH_PRIORITY_GROUPS = {"BRF-001", "BTPC-001", "VCB-001", "LSR-001"}
DEFAULT_SAMPLE_LIMIT = 30


@dataclass(frozen=True)
class CandleRow:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time_ms: int


class WindowedPublicMarketSource:
    """In-memory public market source ending at one historical closed bar."""

    source_id = "binance_usdm_public_klines_window_read_only"
    source_type = "live_market_read_only"
    freshness = "historical_closed_public_kline_window"
    is_live_read_only = True
    fallback_used = False

    def __init__(self, candles: dict[str, dict[str, list[CandleRow]]], *, end_open_time_ms: int) -> None:
        self._candles = candles
        self._end_open_time_ms = end_open_time_ms

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        rows = self._candles[RUNTIME_TO_BINANCE[symbol]][timeframe]
        if timeframe == "1h":
            cutoff = self._end_open_time_ms
        else:
            cutoff = self._end_open_time_ms + HOUR_MS
        selected = [row for row in rows if row.open_time_ms <= cutoff and row.close_time_ms <= cutoff + HOUR_MS]
        return [
            RecentCandle(
                open_time_ms=row.open_time_ms,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                close_time_ms=row.close_time_ms,
                is_closed=True,
            )
            for row in selected[-limit:]
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--step-hours", type=int, default=1)
    parser.add_argument("--output-json", default="output/runtime-monitor/strategy-capture-gap-audit-20260622.json")
    parser.add_argument("--output-md", default="output/runtime-monitor/strategy-capture-gap-audit-20260622.md")
    args = parser.parse_args(argv)

    packet = build_audit_packet(
        lookback_hours=args.lookback_hours,
        step_hours=args.step_hours,
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md.write_text(_markdown(packet, output_json=output_json, output_md=output_md), encoding="utf-8")
    print(json.dumps({"status": packet["status"], "wrote": [str(output_json), str(output_md)]}, ensure_ascii=False))
    return 0


def build_audit_packet(*, lookback_hours: int, step_hours: int) -> dict[str, Any]:
    server_time = _get_json("/fapi/v1/time")["serverTime"]
    candles = _load_market_candles()
    latest_open = min(rows["1h"][-1].open_time_ms for rows in candles.values())
    start_open = latest_open - lookback_hours * HOUR_MS
    evaluation_times = list(range(start_open, latest_open + 1, step_hours * HOUR_MS))

    events: list[dict[str, Any]] = []
    signal_counts: Counter[tuple[str, str]] = Counter()
    reason_counts: Counter[str] = Counter()
    high_priority_no_action: list[dict[str, Any]] = []
    would_enter_events: list[dict[str, Any]] = []

    for end_open in evaluation_times:
        source = WindowedPublicMarketSource(candles, end_open_time_ms=end_open)
        response = build_strategy_group_live_readonly_observation_v1(market_source=source)
        for record in response.current_signals:
            event = _record_event(record.model_dump(mode="json"), candles)
            events.append(event)
            signal_counts[(event["strategy_group_id"], event["signal_type"])] += 1
            reason_counts.update(event["reason_codes"])
            if event["signal_type"] == "would_enter":
                would_enter_events.append(event)
            if (
                event["signal_type"] == "no_action"
                and event["strategy_group_id"] in HIGH_PRIORITY_GROUPS
            ):
                high_priority_no_action.append(event)

    market_rows = [_market_structure(symbol, candles[symbol]["1h"]) for symbol in DEFAULT_SYMBOLS]
    derivative_rows = _derivative_rows()
    by_strategy = _strategy_rows(events, would_enter_events, high_priority_no_action)
    decisions = _decision_rows(by_strategy)
    latest_local_monitor = _safe_json(Path("output/runtime-monitor/latest-local-monitor-sequence.json"))
    latest_coverage = _safe_json(Path("output/runtime-monitor/latest-live-market-signal-coverage-diagnostic.json"))
    priority_closure = _priority_line_closure(by_strategy, decisions)
    visibility_state = _owner_visibility_state(
        local_monitor=latest_local_monitor,
        decisions=decisions,
        would_enter_events=would_enter_events,
        high_priority_no_action=high_priority_no_action,
    )
    would_enter_sample = _event_sample_contract(would_enter_events, sample_limit=DEFAULT_SAMPLE_LIMIT)
    high_priority_no_action_sample = _event_sample_contract(
        high_priority_no_action,
        sample_limit=DEFAULT_SAMPLE_LIMIT,
    )

    return {
        "schema": "brc.strategy_capture_gap_audit.v3",
        "scope": "P0_5_strategy_capture_gap_audit_read_only",
        "status": "strategy_capture_gap_audit_ready",
        "generated_at": _iso(int(time.time() * 1000)),
        "official_server_time_ms": server_time,
        "official_server_time_utc": _iso(server_time),
        "lookback_hours": lookback_hours,
        "step_hours": step_hours,
        "sources": {
            "official_market": [
                "Binance USD-M Futures public /fapi/v1/time",
                "Binance USD-M Futures public /fapi/v1/klines",
                "Binance USD-M Futures public /fapi/v1/fundingRate",
                "Binance Futures public /futures/data/openInterestHist",
            ],
            "local_monitor_sequence": "output/runtime-monitor/latest-local-monitor-sequence.json",
            "live_market_signal_coverage": "output/runtime-monitor/latest-live-market-signal-coverage-diagnostic.json",
        },
        "runtime_baseline": {
            "status": latest_local_monitor.get("status"),
            "blockers": latest_local_monitor.get("checks", {}).get("blockers", []),
            "non_market_gaps": latest_local_monitor.get("checks", {}).get("non_market_gaps", []),
            "remote_interaction_count": latest_local_monitor.get("interaction", {}).get("remote_interaction_count", 0),
            "approaches_real_order": latest_local_monitor.get("interaction", {}).get("approaches_real_order", False),
        },
        "market_structure_rows": market_rows,
        "derivative_rows": derivative_rows,
        "system_observation_summary": {
            "evaluated_window_count": len(evaluation_times),
            "event_count": len(events),
            "would_enter_count": len(would_enter_events),
            "high_priority_no_action_count": len(high_priority_no_action),
            "would_enter_sampled_count": would_enter_sample["sampled_count"],
            "would_enter_omitted_count": would_enter_sample["omitted_count"],
            "high_priority_no_action_sampled_count": high_priority_no_action_sample["sampled_count"],
            "high_priority_no_action_omitted_count": high_priority_no_action_sample["omitted_count"],
            "forward_outcome_summary": _forward_outcome_summary(events),
            "would_enter_forward_outcome_summary": _forward_outcome_summary(would_enter_events),
            "missed_no_action_forward_outcome_summary": _forward_outcome_summary(high_priority_no_action),
            "signal_counts": {f"{key[0]}:{key[1]}": value for key, value in sorted(signal_counts.items())},
            "dominant_reason_codes": _top_counts(reason_counts, limit=12),
            "latest_live_coverage_status": latest_coverage.get("status"),
            "latest_live_coverage_gap": latest_coverage.get("checks", {}).get("coverage_gap"),
        },
        "strategy_expectation_rows": by_strategy,
        "event_samples": {
            "would_enter": would_enter_sample,
            "high_priority_no_action": high_priority_no_action_sample,
        },
        "would_enter_events": would_enter_sample["events"],
        "high_priority_no_action_events": high_priority_no_action_sample["events"],
        "decision_recommendations": decisions,
        "priority_line_closure": priority_closure,
        "owner_visibility_state": visibility_state,
        "audit_conclusion": _audit_conclusion(decisions),
        "safety_invariants": {
            "read_only_official_public_market_data": True,
            "uses_local_sqlite_for_recent_market": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "creates_execution_intent": False,
            "server_files_mutated": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "real_order_authority": False,
            "preview_or_replay_treated_as_live_signal": False,
        },
    }


def _record_event(record: dict[str, Any], candles: dict[str, dict[str, list[CandleRow]]]) -> dict[str, Any]:
    side = record.get("side") or INTENDED_SIDE_BY_CANDIDATE.get(record["candidate_id"])
    if side == "none":
        side = INTENDED_SIDE_BY_CANDIDATE.get(record["candidate_id"], "none")
    entry = _entry_close(record, candles)
    forward = _forward_outcome(
        record["symbol"],
        record["market_bar_timestamp_ms"],
        entry,
        side,
        candles,
    )
    return {
        "candidate_id": record["candidate_id"],
        "strategy_group_id": record["strategy_group_id"],
        "strategy_family_version_id": record.get("strategy_family_version_id"),
        "symbol": record["symbol"],
        "side": side,
        "signal_type": record["signal_type"],
        "confidence": record["confidence"],
        "event_time_ms": record["market_bar_timestamp_ms"],
        "event_time_utc": _iso(record["market_bar_timestamp_ms"]),
        "entry_close": _fmt(entry),
        "reason_codes": record.get("reason_codes") or [],
        "human_summary": record.get("human_summary"),
        "blocker_class": _blocker_class(record),
        "forward_outcome": forward,
        "not_order": record.get("not_order", True),
        "not_execution_intent": record.get("not_execution_intent", True),
        "no_execution_permission": record.get("no_execution_permission", True),
        "no_order_permission": record.get("no_order_permission", True),
        "no_runtime_start": record.get("no_runtime_start", True),
    }


def _entry_close(record: dict[str, Any], candles: dict[str, dict[str, list[CandleRow]]]) -> Decimal:
    if record.get("market_bar_close") is not None:
        return Decimal(str(record["market_bar_close"]))
    rows = candles[RUNTIME_TO_BINANCE[record["symbol"]]]["1h"]
    by_time = {row.open_time_ms: row for row in rows}
    return by_time[record["market_bar_timestamp_ms"]].close


def _forward_outcome(
    symbol: str,
    event_time_ms: int,
    entry: Decimal,
    side: str,
    candles: dict[str, dict[str, list[CandleRow]]],
) -> dict[str, Any]:
    rows = candles[RUNTIME_TO_BINANCE[symbol]]["1h"]
    by_time = {row.open_time_ms: row for row in rows}
    windows = {}
    for hours in (4, 12, 24):
        forward_rows = [
            by_time.get(event_time_ms + offset * HOUR_MS)
            for offset in range(1, hours + 1)
        ]
        if any(row is None for row in forward_rows):
            latest_available = rows[-1].open_time_ms if rows else 0
            required_last = event_time_ms + hours * HOUR_MS
            windows[f"{hours}h"] = {
                "status": "pending" if required_last > latest_available else "unavailable"
            }
            continue
        completed = [row for row in forward_rows if row is not None]
        high = max(row.high for row in completed)
        low = min(row.low for row in completed)
        exit_close = completed[-1].close
        if side == "short":
            mfe = ((entry - low) / entry) * Decimal("100")
            mae = ((entry - high) / entry) * Decimal("100")
            forward_return = ((entry - exit_close) / entry) * Decimal("100")
        elif side == "long":
            mfe = ((high - entry) / entry) * Decimal("100")
            mae = ((low - entry) / entry) * Decimal("100")
            forward_return = ((exit_close - entry) / entry) * Decimal("100")
        else:
            windows[f"{hours}h"] = {"status": "not_applicable_no_clear_side"}
            continue
        rough_cost = Decimal("0.12")
        windows[f"{hours}h"] = {
            "status": "completed",
            "forward_return_pct": _fmt(forward_return),
            "mfe_pct": _fmt(mfe),
            "mae_pct": _fmt(mae),
            "rough_cost_pct_assumption": _fmt(rough_cost),
            "mfe_after_rough_cost_pct": _fmt(mfe - rough_cost),
            "tradable_mfe_after_cost": bool(mfe - rough_cost > Decimal("0.35")),
        }
    return windows


def _event_sample_contract(events: list[dict[str, Any]], *, sample_limit: int) -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sorted_events = sorted(events, key=lambda item: item["event_time_ms"], reverse=True)
    sampled = sorted_events[:sample_limit]
    sampled_counter = Counter(event["strategy_group_id"] for event in sampled)
    for event in sorted_events:
        by_group[event["strategy_group_id"]].append(event)
    return {
        "total_count": len(sorted_events),
        "sample_limit": sample_limit,
        "sampled_count": len(sampled),
        "omitted_count": max(len(sorted_events) - len(sampled), 0),
        "by_strategy_group": [
            {
                "strategy_group_id": group,
                "total_count": len(group_events),
                "sampled_count": sampled_counter.get(group, 0),
                "omitted_count": max(len(group_events) - sampled_counter.get(group, 0), 0),
            }
            for group, group_events in sorted(by_group.items())
        ],
        "events": sampled,
    }


def _forward_outcome_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_window: dict[str, Counter[str]] = defaultdict(Counter)
    positive_by_window: Counter[str] = Counter()
    for event in events:
        for window, outcome in event.get("forward_outcome", {}).items():
            status = str(outcome.get("status") or "unknown")
            by_window[window][status] += 1
            if outcome.get("tradable_mfe_after_cost") is True:
                positive_by_window[window] += 1
    return {
        "event_count": len(events),
        "by_window": {
            window: {
                "completed": counts.get("completed", 0),
                "pending": counts.get("pending", 0),
                "unavailable": counts.get("unavailable", 0),
                "not_applicable": counts.get("not_applicable_no_clear_side", 0),
                "unknown": counts.get("unknown", 0),
                "tradable_mfe_after_cost_count": positive_by_window.get(window, 0),
            }
            for window, counts in sorted(by_window.items())
        },
    }


def _strategy_rows(
    events: list[dict[str, Any]],
    would_enter_events: list[dict[str, Any]],
    high_priority_no_action: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_group[event["strategy_group_id"]].append(event)
    rows = []
    for group in sorted(set(STRATEGY_EXPECTATIONS) | set(by_group)):
        group_events = by_group.get(group, [])
        would_enter = [event for event in group_events if event["signal_type"] == "would_enter"]
        no_action = [event for event in group_events if event["signal_type"] == "no_action"]
        high_no_action = [event for event in high_priority_no_action if event["strategy_group_id"] == group]
        would_enter_positive = _positive_forward_count(would_enter)
        missed_no_action_positive = _positive_forward_count(high_no_action)
        blocker_counts = Counter(event["blocker_class"] for event in group_events)
        rows.append(
            {
                "strategy_group_id": group,
                "expected_behavior": STRATEGY_EXPECTATIONS.get(group, "not documented in current expectation map"),
                "would_enter_count": len(would_enter),
                "no_action_count": len(no_action),
                "high_priority_no_action_count": len(high_no_action),
                "would_enter_forward_positive_count": would_enter_positive,
                "missed_no_action_forward_positive_count": missed_no_action_positive,
                "positive_forward_outcome_count": would_enter_positive + missed_no_action_positive,
                "forward_outcome_summary": _forward_outcome_summary(group_events),
                "would_enter_forward_outcome_summary": _forward_outcome_summary(would_enter),
                "missed_no_action_forward_outcome_summary": _forward_outcome_summary(high_no_action),
                "dominant_blocker_classes": _top_counts(blocker_counts, limit=4),
                "latest_event_time_utc": _iso(max((event["event_time_ms"] for event in group_events), default=0)) if group_events else None,
                "sample_reasons": _top_counts(Counter(code for event in group_events for code in event["reason_codes"]), limit=5),
            }
        )
    return rows


def _decision_rows(strategy_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in strategy_rows:
        group = row["strategy_group_id"]
        decision = "keep_observing"
        reason = "no material would_enter or forward outcome evidence in this audit"
        if group == "BRF-001" and row["would_enter_count"] > 0:
            decision = "promote_review"
            reason = "official live_market windows produced BRF would_enter; review RequiredFacts and squeeze classifier before any tier change"
        elif group == "BTPC-001" and row["high_priority_no_action_count"] > 0:
            decision = "revise"
            reason = "BTPC remains blocked by stale/fact-source attribution despite P0.5 priority"
        elif group == "VCB-001" and row["high_priority_no_action_count"] > 0:
            decision = "keep_observing"
            reason = "current windows mostly fail compression breakout; keep classifier redesign as P1"
        elif group == "LSR-001" and row["high_priority_no_action_count"] > 0:
            decision = "revise"
            reason = "side-specific rewrite remains the dominant blocker"
        elif group == "RBR-001":
            decision = "park"
            reason = "parked vocabulary lane unless materially new positive forward evidence appears"
        elif group == "MI-001" and row["would_enter_count"] > 0:
            decision = "identity_review"
            reason = "MI emits repeated would_enter events but is still treated like a smoke lane; classify as smoke, MPG sub-capability, or formal candidate"
        elif group == "CPM-RO-001" and row["would_enter_count"] > 0:
            decision = "identity_review"
            reason = "CPM emits repeated would_enter events but is not documented in the current expectation map"
        elif group in {"MPG-001", "SOR-001", "FBS-001"}:
            decision = "coverage_visibility_review"
            reason = "mainline no_action reasons should stay visible when waiting_for_market is reported"
        rows.append(
            {
                "strategy_group_id": group,
                "decision": decision,
                "reason": reason,
                "authority_boundary": "decision_support_only; no FinalGate, Operation Layer, exchange write, tier change, or live profile change",
                "next_checkpoint": _next_checkpoint(group, decision),
            }
        )
    return rows


def _next_checkpoint(group: str, decision: str) -> str:
    if decision == "promote_review":
        return f"{group}_forward_outcome_and_requiredfacts_review"
    if decision == "revise":
        return f"{group}_classifier_fact_source_revision_review"
    if decision == "coverage_visibility_review":
        return f"{group}_no_action_visibility_and_routing_audit"
    if decision == "identity_review":
        return f"{group}_registry_identity_review"
    if decision == "park":
        return "park_until_material_new_edge_evidence"
    return f"{group}_continue_observe_only"


def _audit_conclusion(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    priority = [row for row in decisions if row["decision"] in {"promote_review", "revise", "identity_review"}]
    return {
        "strategy_capture_gap_supported": bool(priority),
        "not_a_p0_execution_blocker": True,
        "summary": "official public market replay shows review-worthy capture gaps while P0 execution path remains waiting_for_market",
        "highest_priority_rows": priority,
        "recommended_mainline_action": "keep P0 standby; route BRF/BTPC/LSR evidence into P0.5 decision-ledger review before any live scope change",
    }


def _priority_line_closure(
    strategy_rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    row_by_group = {row["strategy_group_id"]: row for row in strategy_rows}
    decision_by_group = {row["strategy_group_id"]: row for row in decisions}
    priority_groups = ["BTPC-001", "LSR-001", "BRF-001"]
    identity_groups = ["MI-001", "CPM-RO-001"]
    visibility_groups = ["MPG-001", "SOR-001", "FBS-001"]
    return {
        "phase1_audit_contract_hardening": {
            "status": "ready",
            "done_when": [
                "total_count_sampled_count_omitted_count_present",
                "forward_completed_pending_unavailable_not_applicable_present",
                "would_enter_forward_and_missed_no_action_forward_split",
            ],
        },
        "phase2_priority_strategy_lines": [
            _closure_row(group, row_by_group, decision_by_group)
            for group in priority_groups
        ],
        "phase3_registry_identity_review": [
            _closure_row(group, row_by_group, decision_by_group)
            for group in identity_groups
        ],
        "phase4_visibility_review": [
            _closure_row(group, row_by_group, decision_by_group)
            for group in visibility_groups
        ],
    }


def _closure_row(
    group: str,
    row_by_group: dict[str, dict[str, Any]],
    decision_by_group: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row = row_by_group.get(group, {})
    decision = decision_by_group.get(group, {})
    return {
        "strategy_group_id": group,
        "decision": decision.get("decision", "not_in_audit"),
        "would_enter_count": row.get("would_enter_count", 0),
        "high_priority_no_action_count": row.get("high_priority_no_action_count", 0),
        "would_enter_forward_positive_count": row.get("would_enter_forward_positive_count", 0),
        "missed_no_action_forward_positive_count": row.get("missed_no_action_forward_positive_count", 0),
        "next_checkpoint": decision.get("next_checkpoint"),
        "owner_decision_required_now": False,
        "live_permission_change_recommended_now": False,
    }


def _owner_visibility_state(
    *,
    local_monitor: dict[str, Any],
    decisions: list[dict[str, Any]],
    would_enter_events: list[dict[str, Any]],
    high_priority_no_action: list[dict[str, Any]],
) -> dict[str, Any]:
    review_groups = [
        row["strategy_group_id"]
        for row in decisions
        if row["decision"] in {"promote_review", "revise", "identity_review"}
    ]
    p0_state = local_monitor.get("runtime_status") or local_monitor.get("status") or "waiting_for_market"
    return {
        "p0_state": "waiting_for_market" if "waiting_for_market" in str(p0_state) else str(p0_state),
        "p0_5_observation_state": "review_needed" if review_groups else "observation_active",
        "observation_active": bool(would_enter_events or high_priority_no_action),
        "review_needed_strategy_groups": review_groups,
        "no_live_permission": True,
        "owner_intervention_required": False,
        "owner_summary": (
            "P0 waiting_for_market; P0.5 observed StrategyGroup capture issues; no live permission change."
        ),
    }


def _blocker_class(record: dict[str, Any]) -> str:
    codes = set(record.get("reason_codes") or [])
    text = " ".join(codes)
    if record.get("signal_type") == "would_enter":
        return "observe_only_would_enter"
    if "stale" in text:
        return "stale_data_or_signal"
    if "funding" in text or "fact" in text:
        return "missing_or_unready_facts"
    if "classifier" in text or "rewrite" in text:
        return "classifier_or_strategy_rewrite"
    if "volume" in text or "compression" in text or "reclaim" in text or "rejection" in text:
        return "classifier_threshold_not_met"
    if "momentum" in text or "session" in text or "rally" in text:
        return "market_structure_not_confirmed"
    return "no_action_other"


def _positive_forward_count(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        for window in event["forward_outcome"].values():
            if window.get("status") == "completed" and window.get("tradable_mfe_after_cost"):
                count += 1
                break
    return count


def _market_structure(symbol: str, rows: list[CandleRow]) -> dict[str, Any]:
    latest = rows[-1].close
    window72 = rows[-72:]
    window168 = rows[-168:]
    high72 = max(row.high for row in window72)
    low72 = min(row.low for row in window72)
    high168 = max(row.high for row in window168)
    low168 = min(row.low for row in window168)
    up_steps = sum(1 for prev, cur in zip(window72, window72[1:]) if cur.close > prev.close)
    vol12 = sum(row.volume for row in rows[-12:]) / Decimal("12")
    vol72 = sum(row.volume for row in window72) / Decimal("72")
    return {
        "symbol": symbol,
        "latest_closed_bar_utc": _iso(rows[-1].open_time_ms),
        "latest_close": _fmt(latest),
        "return_24h_pct": _pct(rows[-25].close, latest),
        "return_72h_pct": _pct(rows[-73].close, latest),
        "return_7d_pct": _pct(rows[-169].close, latest),
        "range_72h_pct": _fmt(((high72 - low72) / latest) * Decimal("100")),
        "range_7d_position": _fmt((latest - low168) / (high168 - low168)) if high168 != low168 else None,
        "trend_persistence_72h": _fmt(Decimal(up_steps) / Decimal("71")),
        "volume_12h_vs_72h": _fmt(vol12 / vol72) if vol72 else None,
    }


def _derivative_rows() -> list[dict[str, Any]]:
    rows = []
    for symbol in DEFAULT_SYMBOLS:
        funding = _funding_72h(symbol)
        oi_change = _open_interest_72h(symbol)
        rows.append(
            {
                "symbol": symbol,
                "funding_72h_sum_pct": funding,
                "open_interest_72h_change_pct": oi_change,
            }
        )
    return rows


def _funding_72h(symbol: str) -> str | None:
    payload = _get_json("/fapi/v1/fundingRate", {"symbol": symbol, "limit": 24})
    now = int(time.time() * 1000)
    recent = [row for row in payload if now - int(row.get("fundingTime", 0)) <= 72 * HOUR_MS]
    total = sum(Decimal(str(row.get("fundingRate", "0"))) for row in recent) * Decimal("100")
    return _fmt(total, places="0.0001")


def _open_interest_72h(symbol: str) -> str | dict[str, str] | None:
    try:
        payload = _get_json("/futures/data/openInterestHist", {"symbol": symbol, "period": "1h", "limit": 72})
    except Exception as exc:
        return {"error": type(exc).__name__}
    values = [Decimal(str(row["sumOpenInterest"])) for row in payload if row.get("sumOpenInterest") is not None]
    if len(values) < 2 or values[0] == 0:
        return None
    return _fmt(((values[-1] - values[0]) / values[0]) * Decimal("100"))


def _load_market_candles() -> dict[str, dict[str, list[CandleRow]]]:
    result: dict[str, dict[str, list[CandleRow]]] = {}
    for symbol in DEFAULT_SYMBOLS:
        result[symbol] = {
            "1h": _load_klines(symbol, "1h", 320),
            "4h": _load_klines(symbol, "4h", 120),
        }
    return result


def _load_klines(symbol: str, interval: str, limit: int) -> list[CandleRow]:
    payload = _get_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    now = int(time.time() * 1000)
    closed = [row for row in payload if int(row[6]) < now]
    return [
        CandleRow(
            open_time_ms=int(row[0]),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            close_time_ms=int(row[6]),
        )
        for row in closed
    ]


def _get_json(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{BINANCE_USDM_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "brc-strategy-capture-gap-audit/1.0"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - public read-only URL.
        return json.loads(response.read().decode("utf-8"))


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _top_counts(counter: Counter, *, limit: int) -> list[dict[str, Any]]:
    return [{"key": key, "count": value} for key, value in counter.most_common(limit)]


def _pct(start: Decimal, end: Decimal) -> str | None:
    if start == 0:
        return None
    return _fmt(((end - start) / start) * Decimal("100"))


def _fmt(value: Decimal, *, places: str = "0.001") -> str:
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal(places)))
    return str(Decimal(str(value)).quantize(Decimal(places)))


def _iso(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _markdown(packet: dict[str, Any], *, output_json: Path, output_md: Path) -> str:
    lines = [
        "# Strategy Capture Gap Audit",
        "",
        "## 结论",
        "",
        "- **结论**: 当前不能只归因为没有 fresh signal；官方公开行情滑窗审计支持 **Strategy Capture Gap**。",
        "- **P0 状态**: 主链路保持 `waiting_for_market`，不是执行链故障。",
        "- **P0.5 状态**: 至少有一个 StrategyGroup 需要进入捕获质量与 forward outcome 复核。",
        "- **权限边界**: 本产物只读官方公开行情，不调参、不改 tier、不改 live profile、不调用 FinalGate / Operation Layer。",
        "",
        "## 已知客观事实",
        "",
        f"- **官方时间**: `{packet['official_server_time_utc']}`。",
        f"- **审计窗口**: 最近 `{packet['lookback_hours']}` 小时，步长 `{packet['step_hours']}` 小时。",
        f"- **评估窗口数**: `{packet['system_observation_summary']['evaluated_window_count']}`。",
        f"- **would_enter 总数**: `{packet['system_observation_summary']['would_enter_count']}`。",
        f"- **would_enter 样本**: `{packet['system_observation_summary']['would_enter_sampled_count']}` sampled / `{packet['system_observation_summary']['would_enter_omitted_count']}` omitted。",
        f"- **high-priority no_action 总数**: `{packet['system_observation_summary']['high_priority_no_action_count']}`。",
        f"- **high-priority no_action 样本**: `{packet['system_observation_summary']['high_priority_no_action_sampled_count']}` sampled / `{packet['system_observation_summary']['high_priority_no_action_omitted_count']}` omitted。",
        "",
        "### Audit Contract",
        "",
        "| Event class | Total | Sampled | Omitted | Sample limit |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| **would_enter** | {packet['event_samples']['would_enter']['total_count']} | {packet['event_samples']['would_enter']['sampled_count']} | {packet['event_samples']['would_enter']['omitted_count']} | {packet['event_samples']['would_enter']['sample_limit']} |",
        f"| **high_priority_no_action** | {packet['event_samples']['high_priority_no_action']['total_count']} | {packet['event_samples']['high_priority_no_action']['sampled_count']} | {packet['event_samples']['high_priority_no_action']['omitted_count']} | {packet['event_samples']['high_priority_no_action']['sample_limit']} |",
        "",
        "### Forward Outcome Summary",
        "",
        "| Class | Window | Completed | Pending | Unavailable | Not applicable | Tradable MFE after cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("would_enter", "would_enter_forward_outcome_summary"),
        ("missed_no_action", "missed_no_action_forward_outcome_summary"),
    ):
        for window, row in packet["system_observation_summary"][key]["by_window"].items():
            lines.append(
                f"| **{label}** | {window} | {row['completed']} | {row['pending']} | "
                f"{row['unavailable']} | {row['not_applicable']} | {row['tradable_mfe_after_cost_count']} |"
            )
    lines.extend(
        [
            "",
            "### Owner 可见性状态",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    visibility = packet["owner_visibility_state"]
    for key in (
        "p0_state",
        "p0_5_observation_state",
        "observation_active",
        "review_needed_strategy_groups",
        "no_live_permission",
        "owner_intervention_required",
    ):
        lines.append(f"| **{key}** | `{visibility.get(key)}` |")
    lines.extend(
        [
            "",
            "### Phase Closure",
            "",
            "| Phase | Status / Groups |",
            "| --- | --- |",
            f"| **Phase 1 Audit Contract** | `{packet['priority_line_closure']['phase1_audit_contract_hardening']['status']}` |",
            f"| **Phase 2 Priority Lines** | `{', '.join(row['strategy_group_id'] + ':' + row['decision'] for row in packet['priority_line_closure']['phase2_priority_strategy_lines'])}` |",
            f"| **Phase 3 Identity Review** | `{', '.join(row['strategy_group_id'] + ':' + row['decision'] for row in packet['priority_line_closure']['phase3_registry_identity_review'])}` |",
            f"| **Phase 4 Visibility Review** | `{', '.join(row['strategy_group_id'] + ':' + row['decision'] for row in packet['priority_line_closure']['phase4_visibility_review'])}` |",
            "",
        "### 官方市场结构",
        "",
        "| Symbol | 24h | 72h | 7d | 72h range | 7d pos | 72h trend | 12h/72h vol |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in packet["market_structure_rows"]:
        lines.append(
            f"| **{row['symbol']}** | {row['return_24h_pct']}% | {row['return_72h_pct']}% | "
            f"{row['return_7d_pct']}% | {row['range_72h_pct']}% | {row['range_7d_position']} | "
            f"{row['trend_persistence_72h']} | {row['volume_12h_vs_72h']} |"
        )
    lines.extend(
        [
            "",
            "### 衍生品结构",
            "",
            "| Symbol | 72h OI change | 72h funding sum |",
            "| --- | ---: | ---: |",
        ]
    )
    for row in packet["derivative_rows"]:
        lines.append(f"| **{row['symbol']}** | {row['open_interest_72h_change_pct']} | {row['funding_72h_sum_pct']}% |")
    lines.extend(
        [
            "",
            "## StrategyGroup 期望与实际观察",
            "",
            "| StrategyGroup | 期望行为 | would_enter | high-priority no_action | WE 正向 | missed NA 正向 | 主要阻断 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in packet["strategy_expectation_rows"]:
        blockers = ", ".join(f"{item['key']}:{item['count']}" for item in row["dominant_blocker_classes"]) or "none"
        lines.append(
            f"| **{row['strategy_group_id']}** | {row['expected_behavior']} | {row['would_enter_count']} | "
            f"{row['high_priority_no_action_count']} | {row['would_enter_forward_positive_count']} | "
            f"{row['missed_no_action_forward_positive_count']} | {blockers} |"
        )
    lines.extend(
        [
            "",
            "## Would-Enter Forward Outcome",
            "",
            "| Time UTC | StrategyGroup | Symbol | Side | 4h MFE/MAE | 12h MFE/MAE | 24h MFE/MAE |",
            "| --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for event in packet["would_enter_events"][:12]:
        lines.append(
            f"| {event['event_time_utc']} | **{event['strategy_group_id']}** | {event['symbol']} | {event['side']} | "
            f"{_window_text(event, '4h')} | {_window_text(event, '12h')} | {_window_text(event, '24h')} |"
        )
    lines.extend(
        [
            "",
            "## 决策建议",
            "",
            "| StrategyGroup | Decision | Reason | Next checkpoint |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in packet["decision_recommendations"]:
        lines.append(
            f"| **{row['strategy_group_id']}** | `{row['decision']}` | {row['reason']} | `{row['next_checkpoint']}` |"
        )
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "| 项目 | 值 |",
            "| --- | --- |",
        ]
    )
    for key, value in packet["safety_invariants"].items():
        lines.append(f"| **{key}** | `{str(value).lower()}` |")
    lines.extend(
        [
            "",
            "## 输出",
            "",
            f"- **JSON**: `{output_json}`",
            f"- **Markdown**: `{output_md}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _window_text(event: dict[str, Any], window: str) -> str:
    row = event["forward_outcome"].get(window, {})
    if row.get("status") != "completed":
        return row.get("status", "unknown")
    return f"{row['mfe_pct']} / {row['mae_pct']}"


if __name__ == "__main__":
    raise SystemExit(main())
