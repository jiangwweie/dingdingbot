#!/usr/bin/env python3
"""Build SOR authorized-symbol scope and session breakout detector facts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)
from runtime_pg_fact_snapshots import read_pretrade_public_facts_artifact  # noqa: E402


BASE_URL = "https://fapi.binance.com"
PRIMARY_LIVE_SCOPE = ("BTCUSDT", "ETHUSDT")
READONLY_EXPANSION_SCOPE = ("SOLUSDT", "AVAXUSDT")
SYMBOLS = ("ETHUSDT", "SOLUSDT", "BTCUSDT", "AVAXUSDT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument(
        "--ssh-host",
        default="",
        help="Optional SSH host for read-only Binance USD-M kline fetch.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for DB-backed SOR detector", file=sys.stderr)
        return 2
    if not args.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print("ERROR: DB-backed SOR detector requires PostgreSQL DSN", file=sys.stderr)
        return 2
    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as conn:
            public_facts = read_pretrade_public_facts_artifact(conn, symbols=list(SYMBOLS))
    finally:
        engine.dispose()

    artifacts = build_sor_session_scope_detector(public_facts=public_facts, ssh_host=args.ssh_host)
    print(
        json.dumps(
            {
                "status": "sor_session_scope_detector_ready",
                "fresh_session_signal_count": artifacts["detector"]["summary"][
                    "fresh_session_signal_count"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_sor_session_scope_detector(
    *,
    public_facts: dict[str, Any],
    candle_payloads: dict[str, list[list[Any]]] | None = None,
    ssh_host: str = "",
    generated_at_utc: str | None = None,
) -> dict[str, dict[str, Any]]:
    now = _parse_utc(generated_at_utc) if generated_at_utc else datetime.now(timezone.utc)
    public_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in public_facts.get("symbols") or []
        if isinstance(row, dict)
    }
    if candle_payloads is None:
        candle_payloads = (
            _fetch_klines_via_ssh(ssh_host, SYMBOLS)
            if ssh_host
            else {symbol: _fetch_klines(symbol) for symbol in SYMBOLS}
        )
    detector_rows = [
        _detector_row(
            symbol=symbol,
            public_row=public_by_symbol.get(symbol, {}),
            candles=candle_payloads.get(symbol, []),
            generated_at=now,
        )
        for symbol in SYMBOLS
    ]
    scope = _scope_artifact(detector_rows, now.isoformat())
    detector = _detector_artifact(detector_rows, now.isoformat())
    return {"scope": scope, "detector": detector}


def _scope_artifact(rows: list[dict[str, Any]], generated_at_utc: str) -> dict[str, Any]:
    ready_symbols = [
        row["symbol"]
        for row in rows
        if row["symbol"] in READONLY_EXPANSION_SCOPE and row["public_facts_ready"]
    ]
    return {
        "schema": "brc.sor_expanded_scope.v1",
        "scope": "sor_sol_avax_readonly_scope_non_authority",
        "status": "sor_expanded_scope_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": "SOR-001",
        "primary_live_submit_symbol_scope": list(PRIMARY_LIVE_SCOPE),
        "expanded_readonly_watcher_symbols": ready_symbols,
        "reviewed_symbols": list(SYMBOLS),
        "primary_live_submit_scope_changed": False,
        "symbol_evidence": rows,
        "checks": _common_checks(),
        "interaction": non_executing_interaction("L0_local_sor_expanded_scope"),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-sor-expanded-scope.json",
            "md": "latest-sor-expanded-scope.md",
        },
    }


def _detector_artifact(rows: list[dict[str, Any]], generated_at_utc: str) -> dict[str, Any]:
    fresh_count = sum(
        event_row.get("fresh_signal") is True
        for row in rows
        for event_row in row.get("side_event_rows", [])
    )
    return {
        "schema": "brc.sor_session_detector_facts.v1",
        "scope": "sor_session_breakout_detector_facts_non_authority",
        "status": "sor_session_detector_facts_ready",
        "generated_at_utc": generated_at_utc,
        "strategy_group_id": "SOR-001",
        "path_id": "SOR-SIDE-SPECIFIC-SESSION-RANGE",
        "detector_source_mode": "binance_usdm_public_closed_candles",
        "generic_sor_signal_allowed": False,
        "symbol_detector_rows": rows,
        "summary": {
            "fresh_session_signal_count": fresh_count,
            "fresh_side_event_count": fresh_count,
            "supported_event_ids": ["SOR-LONG", "SOR-SHORT"],
            "first_blocker": (
                "private_action_time_facts_required"
                if fresh_count
                else "fresh_sor_session_range_signal_absent"
            ),
        },
        "checks": {
            **_common_checks(),
            "detector_source_is_real_candles": True,
            "fresh_session_signal_present": fresh_count > 0,
        },
        "interaction": non_executing_interaction("L0_local_sor_session_detector_facts"),
        "safety_invariants": _safety_invariants(),
        "output_file_names": {
            "json": "latest-sor-session-detector-facts.json",
            "md": "latest-sor-session-detector-facts.md",
        },
    }


def _detector_row(
    *,
    symbol: str,
    public_row: dict[str, Any],
    candles: list[list[Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    closed = _closed_candles(candles, generated_at)
    session = _current_session_candles(closed, generated_at)
    opening = session[:4]
    latest = session[-1] if session else {}
    opening_high = max([_float(row.get("high")) for row in opening if _float(row.get("high")) is not None], default=None)
    opening_low = min([_float(row.get("low")) for row in opening if _float(row.get("low")) is not None], default=None)
    close = _float(latest.get("close"))
    prior = session[-2] if len(session) >= 2 else {}
    prior_close = _float(prior.get("close"))
    long_breakout = close is not None and opening_high is not None and close > opening_high
    long_follow_through = long_breakout and (prior_close is None or close >= prior_close)
    long_invalidation_ok = close is not None and opening_low is not None and close > opening_low
    short_breakdown = close is not None and opening_low is not None and close < opening_low
    short_follow_through = short_breakdown and (prior_close is None or close <= prior_close)
    short_invalidation_ok = close is not None and opening_high is not None and close < opening_high
    public_ready = (
        public_row.get("public_facts_ready") is True
        and public_row.get("spread_ok") is True
        and public_row.get("min_notional_ok") is True
        and public_row.get("qty_step_ok") is True
        and public_row.get("funding_not_extreme") is True
    )
    long_fresh = bool(public_ready and long_breakout and long_follow_through and long_invalidation_ok)
    short_fresh = bool(public_ready and short_breakdown and short_follow_through and short_invalidation_ok)
    long_missing = []
    short_missing = []
    if not public_ready:
        long_missing.append("public_facts_ready")
        short_missing.append("public_facts_ready")
    if opening_high is None or opening_low is None:
        long_missing.append("opening_range_available")
        short_missing.append("opening_range_available")
    if not long_breakout:
        long_missing.append("breakout_level_crossed")
    if not long_follow_through:
        long_missing.append("follow_through_confirmed")
    if not long_invalidation_ok:
        long_missing.append("invalidation_level_held")
    if not short_breakdown:
        short_missing.append("breakdown_level_crossed")
    if not short_follow_through:
        short_missing.append("bearish_follow_through_confirmed")
    if not short_invalidation_ok:
        short_missing.append("reclaim_invalidation_clear")
    side_event_rows = [
        {
            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v1",
            "event_id": "SOR-LONG",
            "side": "long",
            "event_direction": "closed_15m_breakout_above_opening_range_high",
            "trigger_level": opening_high,
            "protection_ref_type": "opening_range_low_reference",
            "protection_level": opening_low,
            "follow_through": long_follow_through,
            "invalidation_held": long_invalidation_ok,
            "fresh_signal": long_fresh,
            "missing_required_trigger_facts": long_missing,
            "trigger_candle_close_time_utc": latest.get("close_time_utc"),
        },
        {
            "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v1",
            "event_id": "SOR-SHORT",
            "side": "short",
            "event_direction": "closed_15m_breakdown_below_opening_range_low",
            "trigger_level": opening_low,
            "protection_ref_type": "opening_range_high_reference",
            "protection_level": opening_high,
            "follow_through": short_follow_through,
            "invalidation_held": short_invalidation_ok,
            "fresh_signal": short_fresh,
            "missing_required_trigger_facts": short_missing,
            "trigger_candle_close_time_utc": latest.get("close_time_utc"),
        },
    ]
    return {
        "symbol": symbol,
        "timeframe": "15m_closed",
        "public_facts_ready": public_ready,
        "generic_sor_signal_allowed": False,
        "side_event_rows": side_event_rows,
        "opening_range": {
            "high": opening_high,
            "low": opening_low,
            "source": "utc_session_first_four_15m_closed_candles",
        },
        "breakout_level": opening_high,
        "breakdown_level": opening_low,
        "follow_through": long_follow_through,
        "invalidation": {
            "level": opening_low,
            "held": long_invalidation_ok,
        },
        "latest_close": close,
        "latest_candle_close_time_utc": latest.get("close_time_utc"),
        "fresh_session_range_signal": long_fresh,
        "fresh_session_range_short_signal": short_fresh,
        "missing_required_trigger_facts": long_missing,
        "primary_trial_scope_decision": "readonly_watcher_only_not_primary_live_scope",
        "primary_trial_scope_rejection_reason": (
            "requires_session_detector_forward_observation_and_private_action_time_facts"
        ),
    }


def _fetch_klines(symbol: str) -> list[list[Any]]:
    query = urlencode({"symbol": symbol, "interval": "15m", "limit": 120})
    request = Request(
        f"{BASE_URL}/fapi/v1/klines?{query}",
        headers={"User-Agent": "brc-readonly-monitor/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _fetch_klines_via_ssh(host: str, symbols: tuple[str, ...]) -> dict[str, list[list[Any]]]:
    remote_code = f"""
import json
import urllib.parse
import urllib.request

BASE_URL = {BASE_URL!r}
SYMBOLS = {list(symbols)!r}

def fetch(symbol):
    query = urllib.parse.urlencode({{"symbol": symbol, "interval": "15m", "limit": 120}})
    req = urllib.request.Request(
        BASE_URL + "/fapi/v1/klines?" + query,
        headers={{"User-Agent": "brc-readonly-monitor/1.0"}},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, list) else []

print(json.dumps({{symbol: fetch(symbol) for symbol in SYMBOLS}}, ensure_ascii=False))
"""
    result = subprocess.run(
        ["ssh", host, "python3", "-"],
        check=False,
        capture_output=True,
        input=remote_code,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {symbol: [] for symbol in symbols}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {symbol: [] for symbol in symbols}
    if not isinstance(payload, dict):
        return {symbol: [] for symbol in symbols}
    return {
        symbol: payload.get(symbol) if isinstance(payload.get(symbol), list) else []
        for symbol in symbols
    }


def _closed_candles(rows: list[list[Any]], now: datetime) -> list[dict[str, Any]]:
    now_ms = int(now.timestamp() * 1000)
    closed = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            continue
        close_time_ms = _int(row[6])
        if close_time_ms is None or close_time_ms > now_ms:
            continue
        closed.append(
            {
                "open_time_ms": _int(row[0]),
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "close_time_ms": close_time_ms,
                "close_time_utc": datetime.fromtimestamp(
                    close_time_ms / 1000, tz=timezone.utc
                ).isoformat(),
            }
        )
    return closed


def _current_session_candles(
    candles: list[dict[str, Any]], generated_at: datetime
) -> list[dict[str, Any]]:
    session_start = generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    session_start_ms = int(session_start.timestamp() * 1000)
    return [row for row in candles if int(row.get("open_time_ms") or 0) >= session_start_ms]


def _common_checks() -> dict[str, bool]:
    return {
        "primary_live_submit_scope_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "candidate_authorization_created": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "live_submit_allowed": False,
    }


def _safety_invariants() -> dict[str, bool]:
    return {
        **non_executing_safety_invariants(tuple(), include_authority_mirrors=False),
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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


if __name__ == "__main__":
    raise SystemExit(main())
