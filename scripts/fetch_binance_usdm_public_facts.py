#!/usr/bin/env python3
"""Fetch Binance USD-M public facts into PG without private account authority.

The script reads public exchange endpoints only. It never reads secrets, signs
requests, calls account endpoints, places orders, or writes JSON/Markdown state
files. PG runtime fact snapshots are the sole current-state projection; stdout
is process diagnostics only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
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
from runtime_pg_fact_snapshots import (  # noqa: E402
    write_pretrade_public_fact_snapshots,
)
from pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.application.comparative_strength_fact_service import (  # noqa: E402
    ComparativeStrengthFactPlan,
    load_comparative_strength_fact_plan,
    materialize_comparative_strength_fact_snapshots,
)
from src.infrastructure.binance_public_kline_market_source import (  # noqa: E402
    BinancePublicKlineMarketSource,
)


SCHEMA = "brc.binance_usdm_public_facts.v1"
BASE_URL = "https://fapi.binance.com"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT")
STATUS_READY = "binance_usdm_public_facts_ready"
STATUS_PARTIAL = "binance_usdm_public_facts_partial"
STATUS_UNAVAILABLE = "binance_usdm_public_facts_unavailable"
PUBLIC_FACT_KEYS = (
    "exchange_contract_exists",
    "mark_price_fresh",
    "funding_not_extreme",
    "spread_ok",
    "min_notional_ok",
    "qty_step_ok",
    "leverage_available",
)
PUBLIC_FACT_MAX_AGE_SECONDS = 300


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help=(
            "Symbols to fetch. When omitted in DB-backed production mode, "
            "active StrategyGroup candidate symbols are read from PG."
        ),
    )
    parser.add_argument("--ssh-host", help="Run the public fetch on this SSH host.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        help="PostgreSQL DSN for writing DB-backed public fact snapshots.",
    )
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Require PG_DATABASE_URL; this is the production mode.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed public facts",
            file=sys.stderr,
        )
        return 2
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: DB-backed public facts require PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            symbols = (
                _normalize_symbols(args.symbols)
                if args.symbols is not None
                else _active_candidate_symbols(conn)
            )
            comparative_plan = _comparative_plan_if_available(conn)
        if not symbols:
            print(
                "ERROR: active candidate symbols are required for DB-backed public facts",
                file=sys.stderr,
            )
            return 2
        symbols = sorted(set(symbols))
        if args.ssh_host:
            artifact = _fetch_via_ssh(args.ssh_host, symbols)
        else:
            artifact = build_public_facts(symbols=symbols)
        comparative_candles: dict[str, list[dict[str, Any]]] = {}
        comparative_fetch_blocker = ""
        if comparative_plan.required_symbols and not args.ssh_host:
            try:
                comparative_candles = _fetch_comparative_candles(
                    BinancePublicKlineMarketSource(),
                    comparative_plan.required_symbols,
                )
            except Exception as exc:  # noqa: BLE001 - persist unavailable facts.
                comparative_fetch_blocker = (
                    f"comparative_candle_fetch_failed:{type(exc).__name__}"
                )
        with engine.begin() as conn:
            fact_snapshot_ids = write_pretrade_public_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="binance_usdm_public_facts_fetch",
            )
            comparative_result = (
                materialize_comparative_strength_fact_snapshots(
                    conn,
                    candles_by_symbol=comparative_candles,
                    observed_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                    source_ref="binance_closed_1h",
                )
                if comparative_plan.groups
                else {
                    "status": "comparative_strength_not_configured",
                    "materialized_count": 0,
                    "blocked_count": 0,
                    "blockers": [],
                }
            )
            if comparative_fetch_blocker:
                comparative_result["blockers"] = [
                    comparative_fetch_blocker,
                    *list(comparative_result.get("blockers") or []),
                ]
    finally:
        engine.dispose()
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["pg_fact_snapshot_ids"] = fact_snapshot_ids
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "ready_symbol_count": artifact["summary"]["ready_symbol_count"],
                "pg_fact_snapshot_count": len(fact_snapshot_ids),
                "comparative_fact_status": comparative_result["status"],
                "comparative_fact_snapshot_count": int(
                    comparative_result.get("materialized_count") or 0
                )
                + int(comparative_result.get("blocked_count") or 0),
                "remote_interaction_count": artifact["interaction"][
                    "remote_interaction_count"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return _exit_code_for_status(str(artifact["status"]))


def _comparative_plan_if_available(
    conn: sa.engine.Connection,
) -> ComparativeStrengthFactPlan:
    required_tables = {
        "brc_strategy_group_candidate_scope",
        "brc_candidate_scope_event_bindings",
        "brc_strategy_side_event_specs",
        "brc_required_fact_contracts",
    }
    if not required_tables <= set(sa.inspect(conn).get_table_names()):
        return ComparativeStrengthFactPlan(groups=(), required_symbols=())
    return load_comparative_strength_fact_plan(conn)


def _fetch_comparative_candles(
    source: Any,
    symbols: tuple[str, ...] | list[str],
) -> dict[str, list[dict[str, Any]]]:
    return {
        symbol: [
            {
                "open_time_ms": int(candle.open_time_ms),
                "close_time_ms": int(candle.close_time_ms),
                "close": str(candle.close),
            }
            for candle in source.latest_closed_candles(
                symbol=symbol,
                timeframe="1h",
                limit=13,
            )
        ]
        for symbol in sorted(set(symbols))
    }


def build_public_facts(
    *, symbols: list[str], generated_at_utc: str | None = None
) -> dict[str, Any]:
    generated_dt = (
        _parse_utc(generated_at_utc)
        if generated_at_utc
        else datetime.now(timezone.utc)
    )
    generated = generated_dt.isoformat()
    errors: list[str] = []
    exchange_info = _fetch_json("/fapi/v1/exchangeInfo", errors)
    symbol_rows = {
        str(item.get("symbol") or ""): item
        for item in exchange_info.get("symbols") or []
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        rows.append(_symbol_row(symbol, symbol_rows.get(symbol, {}), errors, generated_dt))
    ready_count = sum(row["public_facts_ready"] is True for row in rows)
    status = _artifact_status(
        ready_count=ready_count,
        symbol_count=len(symbols),
        errors=errors,
    )
    return {
        "schema": SCHEMA,
        "scope": "binance_usdm_public_readonly_facts",
        "status": status,
        "generated_at_utc": generated,
        "source": {
            "venue": "binance_usdm",
            "endpoint_base": BASE_URL,
            "source_role": "public_market_and_contract_facts_not_account_facts",
            "signed_request": False,
            "private_account_endpoint": False,
        },
        "summary": {
            "symbol_count": len(symbols),
            "ready_symbol_count": ready_count,
            "public_fact_keys": list(PUBLIC_FACT_KEYS),
            "public_fact_max_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
            "private_action_time_facts_included": False,
            "errors": errors,
        },
        "symbols": rows,
        "checks": {
            "public_facts_ready": ready_count == len(symbols) and not errors,
            "signed_request": False,
            "private_account_endpoint": False,
            "exchange_write": False,
            "order_created": False,
        },
        "interaction": non_executing_interaction("L0_local_binance_usdm_public_facts"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "order_created",
            ),
            include_authority_mirrors=False,
        ),
    }


def _active_candidate_symbols(conn: sa.engine.Connection) -> list[str]:
    rows = conn.execute(
        sa.text(
            """
            SELECT DISTINCT symbol
            FROM brc_strategy_group_candidate_scope
            WHERE status = 'active'
              AND observation_scope = 'active_wip'
            ORDER BY symbol
            """
        )
    ).mappings()
    return _normalize_symbols([row["symbol"] for row in rows])


def _normalize_symbols(symbols: list[str] | tuple[str, ...] | None) -> list[str]:
    return [
        symbol
        for symbol in (_compact_symbol(raw) for raw in (symbols or []))
        if symbol and symbol != "STRATEGY_SCOPE"
    ]


def _compact_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "/" in text:
        base = text.split("/", 1)[0]
        quote = text.split("/", 1)[1].split(":", 1)[0]
        return f"{base}{quote}".replace("-", "")
    return text.replace("-", "").replace(":", "")


def _symbol_row(
    symbol: str,
    exchange_symbol: dict[str, Any],
    errors: list[str],
    observed_at: datetime,
) -> dict[str, Any]:
    premium = _fetch_json(f"/fapi/v1/premiumIndex?symbol={symbol}", errors)
    book = _fetch_json(f"/fapi/v1/ticker/bookTicker?symbol={symbol}", errors)
    filters = {
        str(item.get("filterType") or ""): item
        for item in exchange_symbol.get("filters") or []
        if isinstance(item, dict)
    }
    lot = filters.get("LOT_SIZE") or {}
    market_lot = filters.get("MARKET_LOT_SIZE") or {}
    min_notional = filters.get("MIN_NOTIONAL") or {}
    bid = _to_float(book.get("bidPrice"))
    ask = _to_float(book.get("askPrice"))
    mark = _to_float(premium.get("markPrice"))
    mark_observed_at = _timestamp_ms_to_utc(premium.get("time"))
    mark_age_seconds = _age_seconds(mark_observed_at, observed_at)
    funding = _to_float(premium.get("lastFundingRate"))
    spread_bps = ((ask - bid) / mark * 10000) if bid and ask and mark else None
    contract_exists = exchange_symbol.get("status") == "TRADING"
    mark_ready = (
        mark is not None
        and mark > 0
        and mark_age_seconds is not None
        and mark_age_seconds <= PUBLIC_FACT_MAX_AGE_SECONDS
    )
    funding_ok = funding is not None and abs(funding) <= 0.003
    spread_ok = spread_bps is not None and spread_bps <= 10
    min_notional_value = _to_float(min_notional.get("notional"))
    market_min_qty = _to_float(market_lot.get("minQty"))
    market_step = _to_float(market_lot.get("stepSize"))
    active_lot = (
        market_lot
        if market_min_qty is not None
        and market_min_qty > 0
        and market_step is not None
        and market_step > 0
        else lot
    )
    min_qty = active_lot.get("minQty")
    qty_step = active_lot.get("stepSize")
    quantity_rule_source = (
        "MARKET_LOT_SIZE" if active_lot is market_lot else "LOT_SIZE"
    )
    return {
        "symbol": symbol,
        "public_facts_ready": all(
            [
                contract_exists,
                mark_ready,
                funding_ok,
                spread_ok,
                min_notional_value is not None,
                _to_float(min_qty) is not None,
                bool(qty_step),
            ]
        ),
        "exchange_contract_exists": contract_exists,
        "mark_price_fresh": mark_ready,
        "mark_price_observed_at_utc": (
            mark_observed_at.isoformat() if mark_observed_at else None
        ),
        "mark_price_age_seconds": mark_age_seconds,
        "max_mark_price_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
        "funding_not_extreme": funding_ok,
        "spread_ok": spread_ok,
        "min_notional_ok": min_notional_value is not None,
        "qty_step_ok": bool(qty_step),
        "leverage_available": contract_exists,
        "facts": {
            "mark_price": premium.get("markPrice"),
            "mark_price_observed_at_utc": (
                mark_observed_at.isoformat() if mark_observed_at else None
            ),
            "last_funding_rate": premium.get("lastFundingRate"),
            "bid_price": book.get("bidPrice"),
            "ask_price": book.get("askPrice"),
            "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
            "min_notional": min_notional.get("notional"),
            "min_qty": min_qty,
            "qty_step": qty_step,
            "quantity_rule_source": quantity_rule_source,
            "order_rule_surface": "market_entry",
            "contract_status": exchange_symbol.get("status"),
            "contract_type": exchange_symbol.get("contractType"),
        },
    }


def _fetch_via_ssh(host: str, symbols: list[str]) -> dict[str, Any]:
    remote_code = f"""
import json
import sys
import urllib.request

BASE_URL = {BASE_URL!r}
SYMBOLS = {symbols!r}

def fetch(path):
    req = urllib.request.Request(BASE_URL + path, headers={{"User-Agent": "brc-readonly-monitor/1.0"}})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))

payload = {{
    "exchangeInfo": fetch("/fapi/v1/exchangeInfo"),
    "premium": {{symbol: fetch(f"/fapi/v1/premiumIndex?symbol={{symbol}}") for symbol in SYMBOLS}},
    "book": {{symbol: fetch(f"/fapi/v1/ticker/bookTicker?symbol={{symbol}}") for symbol in SYMBOLS}},
}}
print(json.dumps(payload, ensure_ascii=False))
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
        artifact = _unavailable_artifact(
            symbols=symbols,
            error=f"ssh_public_fetch_failed:{result.returncode}:{result.stderr.strip()}",
        )
        artifact["interaction"] = _interaction_with_remote_count(
            "L1_tokyo_binance_usdm_public_facts_fetch", 1
        )
        return artifact
    raw = json.loads(result.stdout)
    artifact = _build_from_prefetched(symbols=symbols, raw=raw)
    artifact["interaction"] = _interaction_with_remote_count(
        "L1_tokyo_binance_usdm_public_facts_fetch", 1
    )
    return artifact


def _unavailable_artifact(symbols: list[str], error: str) -> dict[str, Any]:
    rows = [
        {
            "symbol": symbol,
            "public_facts_ready": False,
            "exchange_contract_exists": False,
            "mark_price_fresh": False,
            "mark_price_observed_at_utc": None,
            "mark_price_age_seconds": None,
            "max_mark_price_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
            "funding_not_extreme": False,
            "spread_ok": False,
            "min_notional_ok": False,
            "qty_step_ok": False,
            "leverage_available": False,
            "facts": {},
        }
        for symbol in symbols
    ]
    return {
        "schema": SCHEMA,
        "scope": "binance_usdm_public_readonly_facts",
        "status": STATUS_UNAVAILABLE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "venue": "binance_usdm",
            "endpoint_base": BASE_URL,
            "source_role": "public_market_and_contract_facts_not_account_facts",
            "signed_request": False,
            "private_account_endpoint": False,
        },
        "summary": {
            "symbol_count": len(symbols),
            "ready_symbol_count": 0,
            "public_fact_keys": list(PUBLIC_FACT_KEYS),
            "public_fact_max_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
            "private_action_time_facts_included": False,
            "errors": [error],
        },
        "symbols": rows,
        "checks": {
            "public_facts_ready": False,
            "signed_request": False,
            "private_account_endpoint": False,
            "exchange_write": False,
            "order_created": False,
        },
        "interaction": non_executing_interaction("L0_local_binance_usdm_public_facts"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "order_created",
            ),
            include_authority_mirrors=False,
        ),
    }


def _build_from_prefetched(symbols: list[str], raw: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    exchange_info = raw.get("exchangeInfo") if isinstance(raw, dict) else {}
    symbol_rows = {
        str(item.get("symbol") or ""): item
        for item in (exchange_info or {}).get("symbols") or []
        if isinstance(item, dict)
    }
    premiums = raw.get("premium") if isinstance(raw.get("premium"), dict) else {}
    books = raw.get("book") if isinstance(raw.get("book"), dict) else {}
    rows = [
        _symbol_row_from_payload(
            symbol,
            symbol_rows.get(symbol, {}),
            premiums.get(symbol, {}),
            books.get(symbol, {}),
            datetime.now(timezone.utc),
        )
        for symbol in symbols
    ]
    ready_count = sum(row["public_facts_ready"] is True for row in rows)
    return {
        "schema": SCHEMA,
        "scope": "binance_usdm_public_readonly_facts",
        "status": _artifact_status(
            ready_count=ready_count,
            symbol_count=len(symbols),
            errors=errors,
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "venue": "binance_usdm",
            "endpoint_base": BASE_URL,
            "source_role": "public_market_and_contract_facts_not_account_facts",
            "signed_request": False,
            "private_account_endpoint": False,
        },
        "summary": {
            "symbol_count": len(symbols),
            "ready_symbol_count": ready_count,
            "public_fact_keys": list(PUBLIC_FACT_KEYS),
            "public_fact_max_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
            "private_action_time_facts_included": False,
            "errors": errors,
        },
        "symbols": rows,
        "checks": {
            "public_facts_ready": ready_count == len(symbols),
            "signed_request": False,
            "private_account_endpoint": False,
            "exchange_write": False,
            "order_created": False,
        },
        "interaction": non_executing_interaction("L0_local_binance_usdm_public_facts"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "order_created",
            ),
            include_authority_mirrors=False,
        ),
    }


def _symbol_row_from_payload(
    symbol: str,
    exchange_symbol: dict[str, Any],
    premium: dict[str, Any],
    book: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    filters = {
        str(item.get("filterType") or ""): item
        for item in exchange_symbol.get("filters") or []
        if isinstance(item, dict)
    }
    lot = filters.get("LOT_SIZE") or {}
    market_lot = filters.get("MARKET_LOT_SIZE") or {}
    min_notional = filters.get("MIN_NOTIONAL") or {}
    bid = _to_float(book.get("bidPrice"))
    ask = _to_float(book.get("askPrice"))
    mark = _to_float(premium.get("markPrice"))
    mark_observed_at = _timestamp_ms_to_utc(premium.get("time"))
    mark_age_seconds = _age_seconds(mark_observed_at, observed_at)
    funding = _to_float(premium.get("lastFundingRate"))
    spread_bps = ((ask - bid) / mark * 10000) if bid and ask and mark else None
    contract_exists = exchange_symbol.get("status") == "TRADING"
    mark_ready = (
        mark is not None
        and mark > 0
        and mark_age_seconds is not None
        and mark_age_seconds <= PUBLIC_FACT_MAX_AGE_SECONDS
    )
    funding_ok = funding is not None and abs(funding) <= 0.003
    spread_ok = spread_bps is not None and spread_bps <= 10
    min_notional_value = _to_float(min_notional.get("notional"))
    market_min_qty = _to_float(market_lot.get("minQty"))
    market_step = _to_float(market_lot.get("stepSize"))
    active_lot = (
        market_lot
        if market_min_qty is not None
        and market_min_qty > 0
        and market_step is not None
        and market_step > 0
        else lot
    )
    min_qty = active_lot.get("minQty")
    qty_step = active_lot.get("stepSize")
    quantity_rule_source = (
        "MARKET_LOT_SIZE" if active_lot is market_lot else "LOT_SIZE"
    )
    return {
        "symbol": symbol,
        "public_facts_ready": all(
            [
                contract_exists,
                mark_ready,
                funding_ok,
                spread_ok,
                min_notional_value is not None,
                _to_float(min_qty) is not None,
                bool(qty_step),
            ]
        ),
        "exchange_contract_exists": contract_exists,
        "mark_price_fresh": mark_ready,
        "mark_price_observed_at_utc": (
            mark_observed_at.isoformat() if mark_observed_at else None
        ),
        "mark_price_age_seconds": mark_age_seconds,
        "max_mark_price_age_seconds": PUBLIC_FACT_MAX_AGE_SECONDS,
        "funding_not_extreme": funding_ok,
        "spread_ok": spread_ok,
        "min_notional_ok": min_notional_value is not None,
        "qty_step_ok": bool(qty_step),
        "leverage_available": contract_exists,
        "facts": {
            "mark_price": premium.get("markPrice"),
            "mark_price_observed_at_utc": (
                mark_observed_at.isoformat() if mark_observed_at else None
            ),
            "last_funding_rate": premium.get("lastFundingRate"),
            "bid_price": book.get("bidPrice"),
            "ask_price": book.get("askPrice"),
            "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
            "min_notional": min_notional.get("notional"),
            "min_qty": min_qty,
            "qty_step": qty_step,
            "quantity_rule_source": quantity_rule_source,
            "order_rule_surface": "market_entry",
            "contract_status": exchange_symbol.get("status"),
            "contract_type": exchange_symbol.get("contractType"),
        },
    }


def _artifact_status(
    *,
    ready_count: int,
    symbol_count: int,
    errors: list[str],
) -> str:
    if errors or symbol_count <= 0 or ready_count <= 0:
        return STATUS_UNAVAILABLE
    if ready_count == symbol_count:
        return STATUS_READY
    return STATUS_PARTIAL


def _exit_code_for_status(status: str) -> int:
    # Partial means the public source is reachable and PG has per-symbol
    # fail-closed facts. It must not stop the whole watcher tick.
    return 0 if status in {STATUS_READY, STATUS_PARTIAL} else 2


def _fetch_json(path: str, errors: list[str]) -> dict[str, Any]:
    try:
        request = Request(
            BASE_URL + path,
            headers={"User-Agent": "brc-readonly-monitor/1.0"},
        )
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception as exc:  # pragma: no cover - network environment dependent
        errors.append(f"{path}:{type(exc).__name__}:{exc}")
        return {}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _timestamp_ms_to_utc(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _age_seconds(observed_at: datetime | None, now: datetime) -> int | None:
    if observed_at is None:
        return None
    return max(0, int((now - observed_at).total_seconds()))


def _interaction_with_remote_count(level: str, count: int) -> dict[str, Any]:
    interaction = non_executing_interaction(level)
    interaction["remote_interaction_count"] = count
    return interaction


if __name__ == "__main__":
    raise SystemExit(main())
