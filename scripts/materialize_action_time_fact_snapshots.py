#!/usr/bin/env python3
"""Materialize PG live signals into action-time fact snapshots.

This is a non-executing PG-only bridge:

live_signal_event + RequiredFacts + detector evidence
-> brc_runtime_fact_snapshots.fact_surface = action_time

It does not call FinalGate, Operation Layer, exchange write APIs, order
lifecycle, withdrawals, transfers, live profile mutation, or order sizing
mutation.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402


ACTION_TIME_FACT_SURFACE = "action_time"
SOURCE_KIND = "live_signal_materialized"
AUTHORITY_BOUNDARY = (
    "pg_action_time_fact_snapshot_materializer; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
FORBIDDEN_EFFECTS = {
    "finalgate_called": False,
    "operation_layer_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


def materialize_action_time_fact_snapshots(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    signals = _current_fresh_live_signals(conn, now_ms=now)
    if not signals:
        return _result(
            "no_current_fresh_live_signal",
            now_ms=now,
            materialized=[],
            blocked=[],
            blockers=[],
            next_action="continue_watcher_observation",
        )

    materialized: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for signal in signals:
        outcome = _materialize_one(conn, signal=signal, now_ms=now)
        if outcome["satisfied"] is True:
            materialized.append(outcome)
        else:
            blocked.append(outcome)

    blockers = _dedupe(
        blocker
        for item in blocked
        for blocker in item.get("blockers", [])
    )
    status = (
        "action_time_fact_snapshots_materialized"
        if materialized
        else "action_time_fact_snapshots_blocked"
    )
    return _result(
        status,
        now_ms=now,
        materialized=materialized,
        blocked=blocked,
        blockers=blockers,
        next_action=(
            "publish_runtime_control_current_projections"
            if materialized
            else "repair_live_signal_action_time_fact_source"
        ),
    )


def _materialize_one(
    conn: sa.engine.Connection,
    *,
    signal: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    event = _event_spec(conn, str(signal["event_spec_id"]))
    runtime_scope = _runtime_scope(conn, signal)
    required_facts = _required_facts(conn, str(signal["event_spec_id"]))
    public_fact = _public_fact(conn, str(signal.get("fact_snapshot_id") or ""))
    payload = _as_dict(signal.get("signal_payload"))
    source_values = _source_values(payload=payload, public_fact=public_fact)
    fact_values, missing = _fact_values(
        event=event,
        signal=signal,
        required_facts=required_facts,
        source_values=source_values,
    )
    failed = _failed_facts(required_facts, fact_values)
    blockers = [
        *(f"required_fact_missing:{key}" for key in missing),
        *(f"required_fact_not_satisfied:{key}" for key in failed),
    ]
    if not event:
        blockers.append("event_spec_missing")
    if not required_facts:
        blockers.append("required_facts_missing")
    if not runtime_scope:
        blockers.append("runtime_scope_binding_missing")
    if not public_fact:
        blockers.append("public_fact_snapshot_missing")
    satisfied = not blockers
    observed_at_ms = max(
        int(signal.get("observed_at_ms") or 0),
        int(public_fact.get("observed_at_ms") or 0),
        now_ms,
    )
    valid_until_candidates = [
        int(signal.get("expires_at_ms") or 0),
        int(public_fact.get("valid_until_ms") or 0),
    ]
    fact_freshness = [
        int(row.get("freshness_ms") or 0)
        for row in required_facts
        if int(row.get("freshness_ms") or 0) > 0
    ]
    if fact_freshness:
        valid_until_candidates.append(observed_at_ms + min(fact_freshness))
    valid_until_ms = min([value for value in valid_until_candidates if value > 0], default=now_ms)
    fact_snapshot_id = _stable_id("fact_action_time", str(signal["signal_event_id"]))
    row = {
        "fact_snapshot_id": fact_snapshot_id,
        "strategy_group_id": signal["strategy_group_id"],
        "symbol": signal["symbol"],
        "side": signal["side"],
        "runtime_profile_id": runtime_scope.get("runtime_profile_id"),
        "fact_surface": ACTION_TIME_FACT_SURFACE,
        "source_kind": SOURCE_KIND,
        "source_ref": f"pg_live_signal_event:{signal['signal_event_id']}",
        "computed": True,
        "satisfied": satisfied,
        "freshness_state": "fresh" if valid_until_ms > now_ms else "stale",
        "failed_facts": _json(_dedupe([*missing, *failed])),
        "fact_values": _json(
            {
                **fact_values,
                "signal_event_id": signal["signal_event_id"],
                "event_spec_id": signal["event_spec_id"],
                "event_id": event.get("event_id"),
                "trigger_candle_close_time_ms": signal.get("trigger_candle_close_time_ms"),
                "source": "materialize_action_time_fact_snapshots",
            }
        ),
        "blocker_class": None if satisfied else "computed_not_satisfied",
        "observed_at_ms": observed_at_ms,
        "valid_until_ms": valid_until_ms,
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_runtime_fact_snapshots", "fact_snapshot_id", row)
    return {
        "fact_snapshot_id": fact_snapshot_id,
        "signal_event_id": str(signal["signal_event_id"]),
        "strategy_group_id": str(signal["strategy_group_id"]),
        "symbol": str(signal["symbol"]),
        "side": str(signal["side"]),
        "event_id": str(event.get("event_id") or ""),
        "satisfied": satisfied,
        "blockers": blockers,
        "failed_facts": _dedupe([*missing, *failed]),
    }


def _current_fresh_live_signals(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_live_signal_events
            WHERE source_kind = 'live_market'
              AND status = 'facts_validated'
              AND freshness_state = 'fresh'
              AND expires_at_ms IS NOT NULL
              AND expires_at_ms > :now_ms
              AND invalidated_at_ms IS NULL
            ORDER BY observed_at_ms ASC, signal_event_id ASC
            """
        ),
        {"now_ms": now_ms},
    ).mappings()
    return [dict(row) for row in rows]


def _event_spec(conn: sa.engine.Connection, event_spec_id: str) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_strategy_side_event_specs
            WHERE event_spec_id = :event_spec_id
              AND status = 'current'
            LIMIT 1
            """
        ),
        {"event_spec_id": event_spec_id},
    ).mappings().first()
    return dict(row) if row else {}


def _runtime_scope(
    conn: sa.engine.Connection,
    signal: dict[str, Any],
) -> dict[str, Any]:
    row = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_runtime_scope_bindings
            WHERE candidate_scope_id = :candidate_scope_id
              AND strategy_group_id = :strategy_group_id
              AND symbol = :symbol
              AND side = :side
              AND status = 'active'
            ORDER BY updated_at_ms DESC
            LIMIT 1
            """
        ),
        {
            "candidate_scope_id": signal.get("candidate_scope_id"),
            "strategy_group_id": signal.get("strategy_group_id"),
            "symbol": signal.get("symbol"),
            "side": signal.get("side"),
        },
    ).mappings().first()
    return dict(row) if row else {}


def _required_facts(conn: sa.engine.Connection, event_spec_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_strategy_event_required_facts
            WHERE event_spec_id = :event_spec_id
              AND status = 'current'
              AND required_for_promotion = true
            ORDER BY fact_role ASC, fact_key ASC
            """
        ),
        {"event_spec_id": event_spec_id},
    ).mappings()
    return [dict(row) for row in rows]


def _public_fact(conn: sa.engine.Connection, fact_snapshot_id: str) -> dict[str, Any]:
    if not fact_snapshot_id:
        return {}
    row = conn.execute(
        sa.text(
            """
            SELECT *
            FROM brc_runtime_fact_snapshots
            WHERE fact_snapshot_id = :fact_snapshot_id
              AND fact_surface = 'pretrade_public'
            LIMIT 1
            """
        ),
        {"fact_snapshot_id": fact_snapshot_id},
    ).mappings().first()
    return dict(row) if row else {}


def _source_values(*, payload: dict[str, Any], public_fact: dict[str, Any]) -> dict[str, Any]:
    signal_summary = _as_dict(payload.get("signal_summary"))
    evidence = _as_dict(signal_summary.get("evidence_payload"))
    signal_snapshot = _as_dict(signal_summary.get("signal_snapshot"))
    public_values = _as_dict(public_fact.get("fact_values"))
    merged: dict[str, Any] = {}
    for source in (
        public_values,
        _as_dict(public_values.get("public_symbol_row")),
        signal_snapshot,
        evidence,
        _as_dict(payload.get("action_time_fact_values")),
        _as_dict(signal_summary.get("action_time_fact_values")),
    ):
        _deep_merge_into(merged, source)
    return merged


def _fact_values(
    *,
    event: dict[str, Any],
    signal: dict[str, Any],
    required_facts: list[dict[str, Any]],
    source_values: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, Any] = {}
    missing: list[str] = []
    event_id = str(event.get("event_id") or signal.get("signal_type") or "")
    protection_ref_type = str(event.get("protection_ref_type") or "")
    reason_codes = [str(item) for item in _as_list(signal.get("reason_codes"))]

    for fact in required_facts:
        key = str(fact.get("fact_key") or "")
        if not key:
            continue
        resolved = _find_fact_value(key, source_values)
        if resolved is None:
            resolved = _derive_fact_value(
                key=key,
                fact=fact,
                event_id=event_id,
                protection_ref_type=protection_ref_type,
                source_values=source_values,
                reason_codes=reason_codes,
            )
        if resolved is None:
            missing.append(key)
            continue
        values[key] = resolved
    return values, missing


def _derive_fact_value(
    *,
    key: str,
    fact: dict[str, Any],
    event_id: str,
    protection_ref_type: str,
    source_values: dict[str, Any],
    reason_codes: list[str],
) -> Any:
    if fact.get("disable_on_match") is True:
        return False
    if key == protection_ref_type:
        return _reference_value_for(key, source_values)
    if key.endswith("_reference"):
        return _reference_value_for(key, source_values)
    if event_id == "SOR-LONG" and key == "breakout_confirmed":
        return "sor_opening_range_breakout" in reason_codes
    if event_id == "SOR-SHORT" and key == "breakdown_confirmed":
        return "sor_opening_range_breakdown" in reason_codes
    if key == "opening_range_defined":
        return _has_any(source_values, ("opening_range", "session_structure"))
    expected = fact.get("expected_value")
    if expected is not None:
        return expected
    if str(fact.get("operator") or "") == "expr_ref":
        return True
    return None


def _reference_value_for(key: str, source_values: dict[str, Any]) -> Any:
    exact = _find_fact_value(key, source_values)
    if _positive_decimal(exact):
        return exact
    if key == "opening_range_high_reference":
        value = _first_positive(
            _nested(source_values, "session_structure", "range_high_reference"),
            _nested(source_values, "opening_range", "high"),
            _nested(source_values, "side_event", "protection_level"),
            source_values.get("protection_level")
            if source_values.get("protection_ref_type") == key
            else None,
        )
        return value
    if key == "opening_range_low_reference":
        value = _first_positive(
            _nested(source_values, "session_structure", "range_low_reference"),
            _nested(source_values, "opening_range", "low"),
            _nested(source_values, "side_event", "protection_level"),
            source_values.get("protection_level")
            if source_values.get("protection_ref_type") == key
            else None,
        )
        return value
    aliases = {
        "pullback_low_reference": (
            ("lookback_low",),
            ("pullback_low",),
            ("price_action_structure", "pullback_low_reference"),
            ("candidate_semantics", "protection", "stop_price_reference"),
        ),
        "momentum_floor_reference": (
            ("momentum_floor_reference",),
            ("price_action_structure", "momentum_floor_reference"),
            ("candidate_semantics", "protection", "stop_price_reference"),
        ),
        "impulse_invalidation_reference": (
            ("impulse_invalidation_reference",),
            ("impulse_low_reference",),
            ("price_action_structure", "impulse_invalidation_reference"),
            ("candidate_semantics", "protection", "stop_price_reference"),
        ),
        "rally_high_reference": (
            ("rally_high_reference",),
            ("price_action_structure", "rally_high_reference"),
            ("candidate_semantics", "protection", "stop_price_reference"),
        ),
    }
    for path in aliases.get(key, ()):
        value = _nested(source_values, *path)
        if _positive_decimal(value):
            return value
    return None


def _failed_facts(required_facts: list[dict[str, Any]], fact_values: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for fact in required_facts:
        key = str(fact.get("fact_key") or "")
        if not key or key not in fact_values:
            continue
        satisfied = _fact_condition_satisfied(fact, fact_values)
        if fact.get("disable_on_match") is True:
            if satisfied:
                failed.append(key)
            continue
        if not satisfied:
            failed.append(key)
    return failed


def _fact_condition_satisfied(row: dict[str, Any], fact_values: dict[str, Any]) -> bool:
    fact_key = str(row.get("fact_key") or "")
    operator = str(row.get("operator") or "")
    observed = fact_values.get(fact_key)
    expected = row.get("expected_value")
    if operator == "exists":
        return observed is not None
    if operator == "not_exists":
        return observed is None
    if operator == "eq":
        return _normalized_scalar(observed) == _normalized_scalar(expected)
    if operator == "neq":
        return _normalized_scalar(observed) != _normalized_scalar(expected)
    if operator in {"gt", "gte", "lt", "lte"}:
        observed_dec = _decimal(observed)
        expected_dec = _decimal(expected)
        if operator == "gt":
            return observed_dec > expected_dec
        if operator == "gte":
            return observed_dec >= expected_dec
        if operator == "lt":
            return observed_dec < expected_dec
        return observed_dec <= expected_dec
    if operator == "in":
        return isinstance(expected, list) and observed in expected
    if operator == "not_in":
        return isinstance(expected, list) and observed not in expected
    if operator == "expr_ref":
        return observed is True
    return False


def _find_fact_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _find_fact_value(key, nested)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_fact_value(key, nested)
            if found is not None:
                return found
    return None


def _nested(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for item in path:
        if not isinstance(current, dict):
            return None
        current = current.get(item)
    return current


def _has_any(value: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_find_fact_value(key, value) is not None for key in keys)


def _first_positive(*values: Any) -> Any:
    for value in values:
        if _positive_decimal(value):
            return value
    return None


def _positive_decimal(value: Any) -> bool:
    return _decimal(value) > Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1")


def _normalized_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    pk_name: str,
    row: dict[str, Any],
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    pk = table.c[pk_name]
    existing = conn.execute(
        sa.select(pk).where(pk == row[pk_name]).limit(1)
    ).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**row))
    else:
        conn.execute(table.update().where(pk == row[pk_name]).values(**row))


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    readable = ":".join(_safe_id_part(part) for part in parts if part)[:120]
    return f"{prefix}:{readable}:{digest}" if readable else f"{prefix}:{digest}"


def _safe_id_part(value: str) -> str:
    return (
        str(value)
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _deep_merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if (
            isinstance(value, dict)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge_into(target[key], value)
            continue
        target[key] = value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "")
        if text and text not in result:
            result.append(text)
    return result


def _result(
    status: str,
    *,
    now_ms: int,
    materialized: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    blockers: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "schema": "brc.action_time_fact_snapshot_materialization.v1",
        "status": status,
        "generated_at_ms": now_ms,
        "materialized_count": len(materialized),
        "blocked_count": len(blocked),
        "materialized": materialized,
        "blocked": blocked,
        "blockers": blockers,
        "next_action": next_action,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    database_url = normalize_sync_postgres_dsn(args.database_url)
    if args.require_database_url and not database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for action-time fact materializer",
            file=sys.stderr,
        )
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        print("ERROR: action-time fact materializer requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            report = materialize_action_time_fact_snapshots(conn, now_ms=args.now_ms)
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 1 if report["status"] == "action_time_fact_snapshots_blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
