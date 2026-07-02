#!/usr/bin/env python3
"""Fetch Binance USD-M public facts without private account authority.

The script reads public exchange endpoints only. It never reads secrets, signs
requests, calls account endpoints, places orders, or writes remote files. When
local public access is blocked, callers may use --ssh-host to run the same
public fetch from a remote host and write the resulting JSON locally.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
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
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.md"
)

SCHEMA = "brc.binance_usdm_public_facts.v1"
BASE_URL = "https://fapi.binance.com"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT")
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
    parser.add_argument("--symbols", nargs="*", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--ssh-host", help="Run the public fetch on this SSH host.")
    parser.add_argument(
        "--fallback-json",
        help=(
            "Use this existing local artifact when the current public fetch fails "
            "and the fallback is still fresh."
        ),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    symbols = [str(symbol).upper() for symbol in args.symbols]
    if args.ssh_host:
        artifact = _fetch_via_ssh(args.ssh_host, symbols)
    else:
        artifact = build_public_facts(symbols=symbols)
    if artifact["status"] != "binance_usdm_public_facts_ready" and args.fallback_json:
        artifact = _fallback_public_facts(
            artifact,
            fallback_path=Path(args.fallback_json),
            symbols=symbols,
        )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "ready_symbol_count": artifact["summary"]["ready_symbol_count"],
                "remote_interaction_count": artifact["interaction"][
                    "remote_interaction_count"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return (
        0
        if artifact["status"]
        in {
            "binance_usdm_public_facts_ready",
            "binance_usdm_public_facts_ready_from_fallback",
        }
        else 2
    )


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
    status = (
        "binance_usdm_public_facts_ready"
        if ready_count == len(symbols) and not errors
        else "binance_usdm_public_facts_unavailable"
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
    qty_step = market_lot.get("stepSize") or lot.get("stepSize")
    return {
        "symbol": symbol,
        "public_facts_ready": all(
            [
                contract_exists,
                mark_ready,
                funding_ok,
                spread_ok,
                min_notional_value is not None,
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
            "qty_step": qty_step,
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
        "status": "binance_usdm_public_facts_unavailable",
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


def _fallback_public_facts(
    current_artifact: dict[str, Any],
    *,
    fallback_path: Path,
    symbols: list[str],
) -> dict[str, Any]:
    if not fallback_path.exists():
        return current_artifact
    try:
        fallback = json.loads(fallback_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return current_artifact
    if not isinstance(fallback, dict):
        return current_artifact
    fallback_symbols = {
        str(row.get("symbol") or "")
        for row in fallback.get("symbols") or []
        if isinstance(row, dict) and row.get("public_facts_ready") is True
    }
    generated_at = _parse_utc(str(fallback.get("generated_at_utc") or ""))
    age_seconds = _age_seconds(generated_at, datetime.now(timezone.utc))
    fallback_fresh = (
        fallback.get("status")
        in {
            "binance_usdm_public_facts_ready",
            "binance_usdm_public_facts_ready_from_fallback",
        }
        and age_seconds is not None
        and age_seconds <= PUBLIC_FACT_MAX_AGE_SECONDS
        and set(symbols).issubset(fallback_symbols)
    )
    if not fallback_fresh:
        return current_artifact
    fallback = dict(fallback)
    fallback["status"] = "binance_usdm_public_facts_ready_from_fallback"
    fallback["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary = dict(fallback.get("summary") or {})
    errors = list(summary.get("errors") or [])
    errors.extend(current_artifact.get("summary", {}).get("errors") or [])
    summary["errors"] = errors
    summary["fallback_source"] = str(fallback_path)
    summary["fallback_age_seconds"] = age_seconds
    fallback["summary"] = summary
    checks = dict(fallback.get("checks") or {})
    checks["public_facts_ready"] = True
    checks["used_fallback_after_fetch_failure"] = True
    fallback["checks"] = checks
    fallback["interaction"] = non_executing_interaction(
        "L0_local_binance_usdm_public_facts_fallback"
    )
    fallback["safety_invariants"] = non_executing_safety_invariants(
        (
            "calls_finalgate",
            "calls_operation_layer",
            "calls_exchange_write",
            "places_order",
            "order_created",
        ),
        include_authority_mirrors=False,
    )
    return fallback


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
        "status": (
            "binance_usdm_public_facts_ready"
            if ready_count == len(symbols)
            else "binance_usdm_public_facts_unavailable"
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
    qty_step = market_lot.get("stepSize") or lot.get("stepSize")
    return {
        "symbol": symbol,
        "public_facts_ready": all(
            [
                contract_exists,
                mark_ready,
                funding_ok,
                spread_ok,
                min_notional_value is not None,
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
            "qty_step": qty_step,
            "contract_status": exchange_symbol.get("status"),
            "contract_type": exchange_symbol.get("contractType"),
        },
    }


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


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Binance USD-M Public Facts",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Ready symbols: `{artifact['summary']['ready_symbol_count']}` / `{artifact['summary']['symbol_count']}`",
        f"- Remote interactions: `{artifact['interaction']['remote_interaction_count']}`",
        f"- Output JSON: `{output_json}`",
        "",
        "| Symbol | Ready | Spread bps | Funding | Min notional | Qty step |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in artifact["symbols"]:
        facts = row.get("facts") or {}
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["symbol"],
                str(row["public_facts_ready"]).lower(),
                facts.get("spread_bps"),
                facts.get("last_funding_rate"),
                facts.get("min_notional"),
                facts.get("qty_step"),
            )
        )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
