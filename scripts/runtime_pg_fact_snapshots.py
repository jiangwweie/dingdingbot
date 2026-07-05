"""PG helpers for runtime fact snapshots.

This module is intentionally small and script-facing. It keeps production
fact-source reads and writes on the PG side so runtime scripts do not drift back
to latest JSON artifacts as inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import sqlalchemy as sa


PRETRADE_PUBLIC_FACT_SURFACE = "pretrade_public"
PUBLIC_FACT_VALID_FOR_MS = 300_000


def write_pretrade_public_fact_snapshots(
    conn: sa.engine.Connection,
    *,
    artifact: dict[str, Any],
    source_ref: str,
    source_kind: str = "live_market",
) -> list[str]:
    """Persist fetched public facts as lane-scoped PG fact snapshots."""

    rows = _active_candidate_scope_rows(conn)
    public_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in artifact.get("symbols") or []
        if isinstance(row, dict)
    }
    created_at_ms = _iso_to_ms(str(artifact.get("generated_at_utc") or "")) or _now_ms()
    inserted: list[str] = []
    for candidate in rows:
        symbol = str(candidate.get("symbol") or "").upper()
        public_row = public_by_symbol.get(symbol)
        if not public_row:
            continue
        observed_at_ms = (
            _iso_to_ms(str(public_row.get("mark_price_observed_at_utc") or ""))
            or created_at_ms
        )
        fact_snapshot_id = (
            "fact:"
            f"{candidate['strategy_group_id']}:{symbol}:{candidate['side']}:"
            f"{PRETRADE_PUBLIC_FACT_SURFACE}:{observed_at_ms}:{created_at_ms}"
        )
        satisfied = public_row.get("public_facts_ready") is True
        failed_facts = _failed_public_fact_keys(public_row)
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_runtime_fact_snapshots (
                  fact_snapshot_id,
                  strategy_group_id,
                  symbol,
                  side,
                  runtime_profile_id,
                  fact_surface,
                  source_kind,
                  source_ref,
                  computed,
                  satisfied,
                  freshness_state,
                  failed_facts,
                  fact_values,
                  blocker_class,
                  observed_at_ms,
                  valid_until_ms,
                  created_at_ms
                ) VALUES (
                  :fact_snapshot_id,
                  :strategy_group_id,
                  :symbol,
                  :side,
                  :runtime_profile_id,
                  :fact_surface,
                  :source_kind,
                  :source_ref,
                  true,
                  :satisfied,
                  :freshness_state,
                  :failed_facts,
                  :fact_values,
                  :blocker_class,
                  :observed_at_ms,
                  :valid_until_ms,
                  :created_at_ms
                )
                """
            ),
            {
                "fact_snapshot_id": fact_snapshot_id,
                "strategy_group_id": str(candidate["strategy_group_id"]),
                "symbol": symbol,
                "side": str(candidate["side"]),
                "runtime_profile_id": candidate.get("runtime_profile_id"),
                "fact_surface": PRETRADE_PUBLIC_FACT_SURFACE,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "satisfied": satisfied,
                "freshness_state": "fresh" if satisfied else "stale",
                "failed_facts": _json(failed_facts),
                "fact_values": _json(
                    {
                        **public_row,
                        "public_symbol_row": public_row,
                        "fact_source": "binance_usdm_public_readonly",
                    }
                ),
                "blocker_class": None if satisfied else "computed_not_satisfied",
                "observed_at_ms": observed_at_ms,
                "valid_until_ms": observed_at_ms + PUBLIC_FACT_VALID_FOR_MS,
                "created_at_ms": created_at_ms,
            },
        )
        inserted.append(fact_snapshot_id)
    return inserted


def read_pretrade_public_facts_artifact(
    conn: sa.engine.Connection,
    *,
    symbols: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Read latest public facts from PG and expose the legacy export shape."""

    symbol_filter = {str(symbol).upper() for symbol in (symbols or [])}
    statement = sa.text(
        """
        SELECT *
        FROM brc_runtime_fact_snapshots
        WHERE fact_surface = :fact_surface
        ORDER BY observed_at_ms ASC, fact_snapshot_id ASC
        """
    )
    latest_by_symbol: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        statement, {"fact_surface": PRETRADE_PUBLIC_FACT_SURFACE}
    ).mappings():
        row_dict = dict(row)
        symbol = str(row_dict.get("symbol") or "").upper()
        if not symbol or symbol in {"STRATEGY_SCOPE"}:
            continue
        if symbol_filter and symbol not in symbol_filter:
            continue
        latest_by_symbol[symbol] = row_dict

    public_rows = [
        _public_symbol_row_from_snapshot(row)
        for symbol, row in sorted(latest_by_symbol.items())
    ]
    ready_count = sum(row.get("public_facts_ready") is True for row in public_rows)
    latest_observed_ms = max(
        [int(row.get("observed_at_ms") or 0) for row in latest_by_symbol.values()],
        default=0,
    )
    return {
        "schema": "brc.binance_usdm_public_facts.v1",
        "scope": "binance_usdm_public_readonly_facts",
        "status": (
            "binance_usdm_public_facts_ready"
            if public_rows and ready_count == len(public_rows)
            else "binance_usdm_public_facts_unavailable"
        ),
        "generated_at_utc": _ms_to_iso(latest_observed_ms),
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "summary": {
            "symbol_count": len(public_rows),
            "ready_symbol_count": ready_count,
            "private_action_time_facts_included": False,
        },
        "symbols": public_rows,
    }


def _active_candidate_scope_rows(conn: sa.engine.Connection) -> list[dict[str, Any]]:
    statement = sa.text(
        """
        SELECT
          candidate.strategy_group_id,
          candidate.symbol,
          candidate.side,
          runtime.runtime_profile_id
        FROM brc_strategy_group_candidate_scope AS candidate
        LEFT JOIN brc_runtime_scope_bindings AS runtime
          ON runtime.candidate_scope_id = candidate.candidate_scope_id
         AND runtime.status = 'active'
        WHERE candidate.status = 'active'
        ORDER BY candidate.strategy_group_id, candidate.symbol, candidate.side
        """
    )
    return [dict(row) for row in conn.execute(statement).mappings()]


def _public_symbol_row_from_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    values = _json_dict(row.get("fact_values"))
    public_row = _json_dict(values.get("public_symbol_row")) or values
    result = dict(public_row)
    result.setdefault("symbol", row.get("symbol"))
    result.setdefault("public_facts_ready", row.get("satisfied") is True)
    failed = _json_list(row.get("failed_facts"))
    for key in failed:
        result.setdefault(str(key), False)
    return result


def _failed_public_fact_keys(public_row: dict[str, Any]) -> list[str]:
    keys = (
        "exchange_contract_exists",
        "mark_price_fresh",
        "funding_not_extreme",
        "spread_ok",
        "min_notional_ok",
        "qty_step_ok",
        "leverage_available",
    )
    failed = [key for key in keys if public_row.get(key) is not True]
    if public_row.get("public_facts_ready") is not True:
        failed.insert(0, "public_facts_ready")
    return list(dict.fromkeys(failed))


def _iso_to_ms(value: str) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _ms_to_iso(value: int) -> str:
    if value <= 0:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
