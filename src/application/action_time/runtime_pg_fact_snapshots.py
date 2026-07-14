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

from src.application.action_time.action_time_invocation import (
    bind_action_time_invocation_fact_refs,
)


PRETRADE_PUBLIC_FACT_SURFACE = "pretrade_public"
PUBLIC_FACT_VALID_FOR_MS = 300_000
ACCOUNT_SAFE_FACT_VALID_FOR_MS = 60_000
ACCOUNT_MODE_SOURCE_SUFFIX = "/fapi/v1/positionSide/dual"
ACCOUNT_MODE_MAX_FUTURE_SKEW_MS = 5_000


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
    ready_count = sum(_is_true(row.get("public_facts_ready")) for row in public_rows)
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


def write_account_safe_fact_snapshots(
    conn: sa.engine.Connection,
    *,
    artifact: dict[str, Any],
    source_ref: str,
    source_kind: str = "live_account_readonly",
    action_time_invocation_id: str | None = None,
) -> list[str]:
    """Persist account/action-time safety facts as PG snapshots."""

    generated_at_ms = _iso_to_ms(str(artifact.get("generated_at_utc") or "")) or _now_ms()
    checks = _json_dict(artifact.get("checks"))
    facts = _json_dict(artifact.get("facts"))
    account_mode = _json_dict(artifact.get("account_mode"))
    declared_safe_ready = checks.get("account_safe_facts_ready") is True
    account_safe_values = {
        **checks,
        **facts,
        "account_safe": checks.get("account_safe") is True,
        "open_orders_clear": checks.get("open_orders_clear") is True,
        "active_position_or_open_order_clear": (
            checks.get("active_position_or_open_order_clear") is True
        ),
        "action_time_available_balance": (
            checks.get("action_time_available_balance") is True
        ),
        "source_status": artifact.get("source_status"),
        "source_role": "readonly_account_action_time_facts",
    }
    mode_observed_at_ms = _iso_to_ms(str(account_mode.get("observed_at") or ""))
    mode_ready = _account_mode_is_safe(
        account_mode,
        generated_at_ms=generated_at_ms,
        observed_at_ms=mode_observed_at_ms,
    )
    safe_ready = declared_safe_ready and mode_ready
    blocker_class = None if safe_ready else "hard_safety_stop"
    failed_facts = _account_safe_failed_facts(artifact)
    if not mode_ready and "account_mode_ready" not in failed_facts:
        failed_facts.append("account_mode_ready")
    mode_status = str(account_mode.get("status") or "missing")
    observed_mode_expired = (
        mode_observed_at_ms is not None
        and generated_at_ms
        > mode_observed_at_ms + ACCOUNT_SAFE_FACT_VALID_FOR_MS
    )
    mode_freshness_state = (
        "fresh"
        if mode_ready
        else "stale"
        if mode_status == "stale" or observed_mode_expired
        else "missing"
        if mode_status in {"missing", "missing_identity"}
        else "unknown"
    )
    account_mode_values = {
        "account_id": account_mode.get("account_id"),
        "exchange_id": account_mode.get("exchange_id"),
        "account_mode": account_mode.get("account_mode") if mode_ready else None,
        "dual_side_position": (
            account_mode.get("dual_side_position") if mode_ready else None
        ),
        "position_mode_safe": mode_ready,
        "observed_at": account_mode.get("observed_at"),
        "source": account_mode.get("source"),
        "runtime_profile_id": account_mode.get("runtime_profile_id"),
        "account_mode_ready": mode_ready,
        "account_trade_permission": checks.get("account_trade_permission") is True,
        "source_signed_get_only": checks.get("source_signed_get_only") is True,
        "source_exchange_write_called": checks.get("source_exchange_write_called") is True,
        "source_order_created": checks.get("source_order_created") is True,
        "mode_source": "live_facts_readonly",
        "mode_status": mode_status,
    }
    rows = [
        {
            "fact_surface": "account_safe",
            "fact_values": account_safe_values,
            "failed": failed_facts,
            "satisfied": safe_ready,
            "blocker": blocker_class,
            "freshness_state": "fresh" if safe_ready else "stale",
            "observed_at_ms": generated_at_ms,
            "valid_until_ms": generated_at_ms + ACCOUNT_SAFE_FACT_VALID_FOR_MS,
        },
        {
            "fact_surface": "account_mode",
            "fact_values": account_mode_values,
            "failed": [] if mode_ready else ["account_mode_not_ready"],
            "satisfied": mode_ready,
            "blocker": None if mode_ready else "hard_safety_stop",
            "freshness_state": mode_freshness_state,
            "observed_at_ms": mode_observed_at_ms or generated_at_ms,
            "valid_until_ms": (
                mode_observed_at_ms + ACCOUNT_SAFE_FACT_VALID_FOR_MS
                if mode_observed_at_ms is not None
                else generated_at_ms
            ),
        },
    ]
    inserted: list[str] = []
    runtime_profile_id = str(account_mode.get("runtime_profile_id") or "").strip()
    account_id = str(account_mode.get("account_id") or "").strip()
    exchange_id = str(account_mode.get("exchange_id") or "").strip()
    account_safe_fact_snapshot_id = ""
    mode_fact_snapshot_id = ""
    for row in rows:
        fact_surface = str(row["fact_surface"])
        identity = (
            f"{account_id}:{exchange_id}"
            if account_id and exchange_id
            else "identity-missing"
        )
        fact_snapshot_id = (
            f"fact:global:{identity}:{fact_surface}:{generated_at_ms}"
        )
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
                  NULL,
                  NULL,
                  NULL,
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
                "fact_surface": fact_surface,
                "runtime_profile_id": runtime_profile_id or None,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "satisfied": row["satisfied"],
                "freshness_state": row["freshness_state"],
                "failed_facts": _json(row["failed"]),
                "fact_values": _json(row["fact_values"]),
                "blocker_class": row["blocker"],
                "observed_at_ms": row["observed_at_ms"],
                "valid_until_ms": row["valid_until_ms"],
                "created_at_ms": generated_at_ms,
            },
        )
        inserted.append(fact_snapshot_id)
        if fact_surface == "account_safe":
            account_safe_fact_snapshot_id = fact_snapshot_id
        if fact_surface == "account_mode":
            mode_fact_snapshot_id = fact_snapshot_id
    if account_id and exchange_id and mode_fact_snapshot_id:
        _upsert_exchange_account_mode_current(
            conn,
            account_id=account_id,
            exchange_id=exchange_id,
            runtime_profile_id=runtime_profile_id,
            mode_values=account_mode_values,
            mode_ready=mode_ready,
            mode_status=mode_status,
            fact_snapshot_id=mode_fact_snapshot_id,
            source_kind=source_kind,
            source_ref=source_ref,
            observed_at_ms=mode_observed_at_ms or generated_at_ms,
            valid_until_ms=(
                mode_observed_at_ms + ACCOUNT_SAFE_FACT_VALID_FOR_MS
                if mode_observed_at_ms is not None
                else generated_at_ms
            ),
            updated_at_ms=generated_at_ms,
        )
    if action_time_invocation_id:
        bind_action_time_invocation_fact_refs(
            conn,
            action_time_invocation_id=action_time_invocation_id,
            account_safe_fact_snapshot_id=account_safe_fact_snapshot_id or None,
            account_mode_fact_snapshot_id=mode_fact_snapshot_id or None,
            stage_at_ms=generated_at_ms,
        )
    return inserted


def _upsert_exchange_account_mode_current(
    conn: sa.engine.Connection,
    *,
    account_id: str,
    exchange_id: str,
    runtime_profile_id: str,
    mode_values: dict[str, Any],
    mode_ready: bool,
    mode_status: str,
    fact_snapshot_id: str,
    source_kind: str,
    source_ref: str,
    observed_at_ms: int,
    valid_until_ms: int,
    updated_at_ms: int,
) -> None:
    """Project one account/exchange mode when migration 113 is available."""

    table_name = "brc_exchange_account_modes_current"
    if not sa.inspect(conn).has_table(table_name):
        return
    table = sa.Table(table_name, sa.MetaData(), autoload_with=conn)
    current_id = f"account_mode_current:{account_id}:{exchange_id}"
    status = (
        "current"
        if mode_ready
        else "stale"
        if mode_status == "stale"
        else "unknown"
    )
    values = {
        "account_mode_current_id": current_id,
        "account_id": account_id,
        "exchange_id": exchange_id,
        "runtime_profile_id": runtime_profile_id or None,
        "position_mode": mode_values.get("account_mode") if mode_ready else None,
        "dual_side_position": (
            mode_values.get("dual_side_position") if mode_ready else None
        ),
        "position_mode_safe": mode_ready,
        "status": status,
        "fact_snapshot_id": fact_snapshot_id,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "observed_at_ms": observed_at_ms,
        "valid_until_ms": valid_until_ms,
        "updated_at_ms": updated_at_ms,
    }
    existing = conn.execute(
        sa.select(table.c.account_mode_current_id).where(
            table.c.account_mode_current_id == current_id
        )
    ).first()
    if existing:
        conn.execute(
            table.update()
            .where(table.c.account_mode_current_id == current_id)
            .values(**values)
        )
        return
    conn.execute(table.insert().values(**values))


def read_latest_account_safe_facts_artifact(
    conn: sa.engine.Connection,
) -> dict[str, Any]:
    account_safe = _latest_fact_snapshot(conn, fact_surface="account_safe")
    account_mode = _latest_fact_snapshot(conn, fact_surface="account_mode")
    if not account_safe:
        return {
            "schema": "brc.runtime_account_safe_facts.v1",
            "status": "runtime_account_safe_facts_blocked",
            "source_mode": "db_backed",
            "projection_target": "production_current",
            "checks": {
                "account_safe_facts_ready": False,
                "private_action_time_facts_ready": False,
                "active_position_or_open_order_clear": False,
                "action_time_available_balance": False,
            },
            "blockers": ["account_safe_fact_snapshot_missing"],
        }
    values = _json_dict(account_safe.get("fact_values"))
    mode_values = _json_dict(account_mode.get("fact_values"))
    ready = (
        _is_true(account_safe.get("computed"))
        and _is_true(account_safe.get("satisfied"))
        and account_safe.get("freshness_state") == "fresh"
        and _is_true(values.get("account_safe"))
    )
    checks = {
        **values,
        "account_safe_facts_ready": ready,
        "private_action_time_facts_ready": ready,
        "account_mode_snapshot_ready": (
            bool(account_mode)
            and _is_true(account_mode.get("computed"))
            and _is_true(account_mode.get("satisfied"))
            and account_mode.get("freshness_state") == "fresh"
            and mode_values.get("position_mode_safe") is True
            and mode_values.get("account_mode") in {"one_way", "hedge"}
        ),
    }
    return {
        "schema": "brc.runtime_account_safe_facts.v1",
        "scope": "runtime_account_safe_facts_readonly",
        "status": (
            "runtime_account_safe_facts_ready"
            if ready
            else "runtime_account_safe_facts_blocked"
        ),
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "generated_at_utc": _ms_to_iso(int(account_safe.get("observed_at_ms") or 0)),
        "account_safe_fact_snapshot_id": account_safe.get("fact_snapshot_id"),
        "account_mode_snapshot_id": account_mode.get("fact_snapshot_id") if account_mode else "",
        "checks": checks,
        "blockers": _json_list(account_safe.get("failed_facts")),
    }


def _latest_fact_snapshot(
    conn: sa.engine.Connection,
    *,
    fact_surface: str,
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_runtime_fact_snapshots
            WHERE fact_surface = :fact_surface
            ORDER BY observed_at_ms DESC, fact_snapshot_id DESC
            LIMIT 1
            """
        ),
        {"fact_surface": fact_surface},
    ).mappings().first()
    return dict(row) if row else {}


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
    result.setdefault("public_facts_ready", _is_true(row.get("satisfied")))
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


def _account_safe_failed_facts(artifact: dict[str, Any]) -> list[str]:
    blockers = [
        str(item)
        for item in artifact.get("blockers") or []
        if str(item or "")
    ]
    if blockers:
        return blockers
    checks = _json_dict(artifact.get("checks"))
    expected_true = (
        "account_safe_facts_ready",
        "account_safe",
        "private_action_time_facts_ready",
        "active_position_or_open_order_clear",
        "action_time_available_balance",
    )
    return [key for key in expected_true if checks.get(key) is not True]


def _account_mode_is_safe(
    values: dict[str, Any],
    *,
    generated_at_ms: int,
    observed_at_ms: int | None,
) -> bool:
    dual_side_position = values.get("dual_side_position")
    account_mode = values.get("account_mode")
    expected_mode = (
        "hedge"
        if dual_side_position is True
        else "one_way"
        if dual_side_position is False
        else None
    )
    source = str(values.get("source") or "")
    return (
        values.get("position_mode_safe") is True
        and type(dual_side_position) is bool
        and account_mode == expected_mode
        and str(values.get("account_id") or "").strip() != ""
        and str(values.get("exchange_id") or "").strip() != ""
        and observed_at_ms is not None
        and observed_at_ms <= generated_at_ms + ACCOUNT_MODE_MAX_FUTURE_SKEW_MS
        and generated_at_ms <= observed_at_ms + ACCOUNT_SAFE_FACT_VALID_FOR_MS
        and source.endswith(ACCOUNT_MODE_SOURCE_SUFFIX)
    )


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


def _is_true(value: Any) -> bool:
    return value is True or value == 1
