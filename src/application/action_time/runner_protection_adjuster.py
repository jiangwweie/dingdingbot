#!/usr/bin/env python3
"""Materialize ticket-bound runner protection after TP1 fill.

This layer records the proof that the remaining runner has a replacement
reduce-only SL. It does not cancel, replace, or submit exchange orders itself;
those exchange mutations must come from the official ticket-bound operation
path and be passed in as already-created refs.
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


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.action_time.lifecycle_safety_core import (  # noqa: E402
    classify_runner_protection_adjustment,
)
from src.domain.ticket_exit_protection import (  # noqa: E402
    DEFAULT_REPLACEMENT_GRACE_MS,
    order_mapping_for_view,
    resolve_active_exit_protection_rows,
)


AUTHORITY_BOUNDARY = (
    "ticket_bound_runner_protection_adjuster; PG runner protection proof only; "
    "no FinalGate, Operation Layer, exchange cancel/replace, profile, sizing, "
    "withdrawal, or transfer authority"
)


def materialize_ticket_bound_runner_protection_adjustment(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    runner_sl_exchange_order_id: str,
    runner_sl_local_order_id: str = "",
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    set_id = str(exit_protection_set_id or "").strip()
    runner_exchange_id = str(runner_sl_exchange_order_id or "").strip()
    runner_local_id = str(runner_sl_local_order_id or "").strip()
    if not set_id:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["exit_protection_set_id_required"],
            protection_set={},
            runner_order={},
            next_action="provide_exit_protection_set_id",
        )

    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    if not protection_set:
        return _result(
            "blocked",
            now_ms=now_ms,
            blockers=["exit_protection_set_missing"],
            protection_set={},
            runner_order={},
            next_action="repair_ticket_bound_exit_protection_set",
        )

    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        str(protection_set.get("ticket_id") or ""),
    )
    orders = _orders_for_set(conn, set_id)
    sl_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="SL",
        orders=orders,
        position_is_open=True,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    tp1_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="TP1",
        orders=orders,
        position_is_open=True,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    runner_resolution = resolve_active_exit_protection_rows(
        exit_protection_set_id=set_id,
        role="RUNNER_SL",
        orders=orders,
        position_is_open=True,
        now_ms=now_ms,
        replacement_grace_ms=DEFAULT_REPLACEMENT_GRACE_MS,
    )
    sl_order = order_mapping_for_view(
        orders, sl_resolution.active_order or sl_resolution.lineage_leaf
    )
    tp1_order = order_mapping_for_view(orders, tp1_resolution.lineage_leaf)
    existing_runner = order_mapping_for_view(orders, runner_resolution.active_order)
    runner_result = _runner_mutation_result_for_set(conn, set_id)

    blockers = _blockers(
        protection_set=protection_set,
        lifecycle=lifecycle,
        sl_order=sl_order,
        tp1_order=tp1_order,
        runner_exchange_id=runner_exchange_id
        or str(existing_runner.get("exchange_order_id") or ""),
    )
    for resolution in (sl_resolution, tp1_resolution, runner_resolution):
        if resolution.fails_closed:
            blockers.extend(resolution.blockers)
    existing_runner_exchange_id = str(existing_runner.get("exchange_order_id") or "")
    if (
        existing_runner
        and runner_exchange_id
        and runner_exchange_id != existing_runner_exchange_id
    ):
        blockers.append("runner_sl_exchange_order_id_mismatch")
    if existing_runner and str(existing_runner.get("status") or "") in {
        "submitted",
        "open",
        "filled",
    }:
        blockers.extend(
            _runner_mutation_result_blockers(
                runner_result=runner_result,
                runner_exchange_id=existing_runner_exchange_id,
            )
        )
    elif runner_exchange_id and not existing_runner:
        blockers.extend(
            _runner_mutation_result_blockers(
                runner_result=runner_result,
                runner_exchange_id=runner_exchange_id,
            )
        )
    blockers = _dedupe(blockers)
    classification = classify_runner_protection_adjustment(
        blockers=blockers,
        tp1_waiting=_waiting_for_tp1_fill(blockers),
        runner_ref_missing_only=_waiting_for_runner_sl_ref(blockers),
    )
    if _waiting_for_tp1_fill(blockers):
        return _result(
            "waiting_for_tp1_fill",
            now_ms=now_ms,
            blockers=blockers,
            protection_set=protection_set,
            runner_order={},
            next_action="wait_for_tp1_fill",
        )
    if _waiting_for_runner_sl_ref(blockers):
        _mark_lifecycle_status(
            conn,
            lifecycle,
            status=classification.status,
            event_type=classification.event_type,
            blockers=blockers,
            now_ms=now_ms,
        )
        return _result(
            classification.status,
            now_ms=now_ms,
            blockers=blockers,
            protection_set=protection_set,
            runner_order={},
            next_action=classification.next_action,
        )
    if blockers:
        _mark_lifecycle_status(
            conn,
            lifecycle,
            status=classification.status,
            event_type=classification.event_type,
            blockers=blockers,
            now_ms=now_ms,
        )
        return _result(
            classification.status,
            now_ms=now_ms,
            blockers=blockers,
            protection_set=protection_set,
            runner_order={},
            next_action=classification.next_action,
        )
    if existing_runner and existing_runner.get("status") in {"submitted", "open", "filled"}:
        _materialize_runner_projection(
            conn,
            protection_set=protection_set,
            lifecycle=lifecycle,
            sl_order=sl_order,
            tp1_order=tp1_order,
            runner_order=existing_runner,
            now_ms=now_ms,
            insert_events=False,
        )
        return _result(
            "runner_protected",
            now_ms=now_ms,
            blockers=[],
            protection_set=protection_set,
            runner_order=existing_runner,
            next_action="continue_runner_monitoring",
            idempotent=True,
        )

    runner_qty = _decimal(protection_set.get("runner_qty"))
    runner_local_id = runner_local_id or _stable_id(
        "ticket_runner_sl_order",
        set_id,
        runner_exchange_id,
    )
    runner_order = {
        "exit_protection_order_id": _stable_id(
            "ticket_exit_protection_order",
            set_id,
            "RUNNER_SL",
            runner_local_id,
        ),
        "exit_protection_set_id": set_id,
        "ticket_id": str(protection_set["ticket_id"]),
        "role": "RUNNER_SL",
        "local_order_id": runner_local_id,
        "exchange_order_id": runner_exchange_id,
        "status": "submitted",
        "order_type": "STOP_MARKET",
        "side": str(sl_order["side"]),
        "qty": runner_qty,
        "price": None,
        "trigger_price": _decimal(sl_order.get("trigger_price")),
        "reduce_only": True,
        "replaces_exit_protection_order_id": str(sl_order["exit_protection_order_id"]),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    protection_update = _materialize_runner_projection(
        conn,
        protection_set=protection_set,
        lifecycle=lifecycle,
        sl_order=sl_order,
        tp1_order=tp1_order,
        runner_order=runner_order,
        now_ms=now_ms,
        insert_events=True,
    )
    return _result(
        "runner_protected",
        now_ms=now_ms,
        blockers=[],
        protection_set=protection_update,
        runner_order=runner_order,
        next_action="continue_runner_monitoring",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--exit-protection-set-id", required=True)
    parser.add_argument("--runner-sl-exchange-order-id", required=True)
    parser.add_argument("--runner-sl-local-order-id", default="")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)
    if args.require_database_url and not args.database_url:
        print("ERROR: PG_DATABASE_URL is required for runner protection", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if (
        not args.allow_non_postgres_for_test
        and not args.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    ):
        print("ERROR: runner protection adjuster requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            report = materialize_ticket_bound_runner_protection_adjustment(
                conn,
                exit_protection_set_id=args.exit_protection_set_id,
                runner_sl_exchange_order_id=args.runner_sl_exchange_order_id,
                runner_sl_local_order_id=args.runner_sl_local_order_id,
                now_ms=args.now_ms,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return 1 if report["status"] == "blocked" else 0


def _blockers(
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    runner_exchange_id: str,
) -> list[str]:
    blockers: list[str] = []
    if protection_set.get("protection_complete") is not True:
        blockers.append("exit_protection_set_not_complete")
    if protection_set.get("status") not in {
        "submitted",
        "reconciled",
        "runner_mutation_pending",
        "runner_protected",
    }:
        blockers.append(f"exit_protection_set_status:{protection_set.get('status')}")
    if not lifecycle:
        blockers.append("lifecycle_run_missing")
    elif lifecycle.get("status") not in {
        "position_protected",
        "tp1_filled",
        "sl_adjust_pending",
        "runner_mutation_pending",
        "runner_protected",
        "blocked",
    }:
        blockers.append(f"lifecycle_status_not_runner_adjustable:{lifecycle.get('status')}")
    if not sl_order:
        blockers.append("sl_protection_order_missing")
    elif sl_order.get("role") != "SL":
        blockers.append("sl_protection_order_role_mismatch")
    elif sl_order.get("reduce_only") is not True:
        blockers.append("sl_protection_order_reduce_only_missing")
    elif _decimal(sl_order.get("trigger_price")) <= 0:
        blockers.append("sl_trigger_price_missing")
    if not tp1_order:
        blockers.append("tp1_protection_order_missing")
    elif tp1_order.get("role") != "TP1":
        blockers.append("tp1_protection_order_role_mismatch")
    elif tp1_order.get("reduce_only") is not True:
        blockers.append("tp1_protection_order_reduce_only_missing")
    elif tp1_order.get("status") != "filled":
        blockers.append(f"tp1_not_filled:{tp1_order.get('status')}")
    if _decimal(protection_set.get("runner_qty")) <= 0:
        blockers.append("runner_qty_not_positive")
    if not runner_exchange_id:
        blockers.append("runner_sl_exchange_order_id_required")
    return _dedupe(blockers)


def _waiting_for_tp1_fill(blockers: list[str]) -> bool:
    return any(blocker.startswith("tp1_not_filled:") for blocker in blockers)


def _waiting_for_runner_sl_ref(blockers: list[str]) -> bool:
    return blockers == ["runner_sl_exchange_order_id_required"]


def _runner_mutation_result_for_set(
    conn: sa.engine.Connection,
    exit_protection_set_id: str,
) -> dict[str, Any]:
    if not exit_protection_set_id:
        return {}
    table = _table(conn, "brc_ticket_bound_runner_mutation_commands")
    row = conn.execute(
        sa.select(table).where(table.c.exit_protection_set_id == exit_protection_set_id)
    ).mappings().first()
    return dict(row) if row else {}


def _runner_mutation_result_blockers(
    *,
    runner_result: dict[str, Any],
    runner_exchange_id: str,
) -> list[str]:
    blockers: list[str] = []
    if not runner_result:
        return ["runner_mutation_result_missing"]
    status = str(runner_result.get("status") or "")
    if status != "result_recorded":
        blockers.append(f"runner_mutation_result_not_recorded:{status or 'missing'}")
    result_payload = _as_dict(runner_result.get("result_payload"))
    if result_payload.get("old_sl_cancelled") is not True:
        blockers.append("runner_mutation_result_old_sl_not_cancelled")
    if result_payload.get("runner_sl_submitted") is not True:
        blockers.append("runner_mutation_result_runner_sl_not_submitted")
    if result_payload.get("exchange_write_called") is not True:
        blockers.append("runner_mutation_result_exchange_write_not_confirmed")
    if str(result_payload.get("runner_sl_exchange_order_id") or "") != runner_exchange_id:
        blockers.append("runner_mutation_result_runner_sl_exchange_id_mismatch")
    if result_payload.get("withdrawal_or_transfer_created") not in {False, None, "", 0}:
        blockers.append("runner_mutation_result_forbidden_effect:withdrawal_or_transfer_created")
    if result_payload.get("live_profile_changed") not in {False, None, "", 0}:
        blockers.append("runner_mutation_result_forbidden_effect:live_profile_changed")
    if result_payload.get("order_sizing_changed") not in {False, None, "", 0}:
        blockers.append("runner_mutation_result_forbidden_effect:order_sizing_changed")
    for blocker in result_payload.get("blockers") or []:
        if str(blocker):
            blockers.append(f"runner_mutation_result_blocker:{blocker}")
    return _dedupe(blockers)


def _materialize_runner_projection(
    conn: sa.engine.Connection,
    *,
    protection_set: dict[str, Any],
    lifecycle: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    runner_order: dict[str, Any],
    now_ms: int,
    insert_events: bool,
) -> dict[str, Any]:
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_orders",
        "exit_protection_order_id",
        runner_order,
    )
    _update_order_status(conn, sl_order, status="replaced", now_ms=now_ms)
    _update_order_status(conn, tp1_order, status="filled", now_ms=now_ms)
    protection_update = {
        **protection_set,
        "status": "runner_protected",
        "sl_order_id": str(runner_order["local_order_id"]),
        "protection_complete": True,
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        protection_update,
    )
    lifecycle_update = {
        **lifecycle,
        "status": "runner_protected",
        "first_blocker": None,
        "blockers": [],
        "updated_at_ms": now_ms,
    }
    _upsert_row(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        lifecycle_update,
    )
    if insert_events:
        _insert_event(conn, lifecycle_update, "tp1_filled", {"tp1_order": tp1_order}, now_ms)
        _insert_event(
            conn,
            lifecycle_update,
            "sl_cancel_requested",
            {"replaced_sl_order": sl_order},
            now_ms,
        )
        _insert_event(
            conn,
            lifecycle_update,
            "runner_sl_submitted",
            {"runner_order": runner_order},
            now_ms,
        )
        _insert_event(
            conn,
            lifecycle_update,
            "runner_protected",
            {"exit_protection_set_id": protection_set["exit_protection_set_id"]},
            now_ms,
        )
    return protection_update


def _orders_for_set(conn: sa.engine.Connection, set_id: str) -> list[dict[str, Any]]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(table.c.exit_protection_set_id == set_id)
        ).mappings()
    ]


def _mark_lifecycle_status(
    conn: sa.engine.Connection,
    lifecycle: dict[str, Any],
    *,
    status: str,
    event_type: str,
    blockers: list[str],
    now_ms: int,
) -> None:
    if not lifecycle:
        return
    row = {
        **lifecycle,
        "status": status,
        "first_blocker": blockers[0],
        "blockers": blockers,
        "updated_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_order_lifecycle_runs", "lifecycle_run_id", row)
    _insert_event(
        conn,
        row,
        event_type,
        {
            "blockers": blockers,
            "lifecycle_status": status,
        },
        now_ms,
    )


def _update_order_status(
    conn: sa.engine.Connection,
    order: dict[str, Any],
    *,
    status: str,
    now_ms: int,
) -> None:
    row = {**order, "status": status, "updated_at_ms": now_ms}
    _upsert_row(
        conn,
        "brc_ticket_bound_exit_protection_orders",
        "exit_protection_order_id",
        row,
    )


def _insert_event(
    conn: sa.engine.Connection,
    lifecycle: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    now_ms: int,
) -> None:
    event = {
        "lifecycle_event_id": _stable_id(
            "ticket_lifecycle_event",
            str(lifecycle["lifecycle_run_id"]),
            event_type,
            str(now_ms),
        ),
        "lifecycle_run_id": str(lifecycle["lifecycle_run_id"]),
        "ticket_id": str(lifecycle["ticket_id"]),
        "protected_submit_attempt_id": str(lifecycle["protected_submit_attempt_id"]),
        "event_type": event_type,
        "event_payload": _json_safe(payload),
        "created_at_ms": now_ms,
    }
    _upsert_row(conn, "brc_ticket_bound_lifecycle_events", "lifecycle_event_id", event)


def _result(
    status: str,
    *,
    now_ms: int,
    blockers: list[str],
    protection_set: dict[str, Any],
    runner_order: dict[str, Any],
    next_action: str,
    idempotent: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema": "brc.ticket_bound_runner_protection_adjuster.v1",
        "status": status,
        "now_ms": now_ms,
        "ticket_id": protection_set.get("ticket_id"),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "runner_order_id": runner_order.get("exit_protection_order_id"),
        "runner_qty": str(runner_order.get("qty") or protection_set.get("runner_qty") or ""),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": _dedupe(blockers),
        "next_action": next_action,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "protection_set": protection_set,
        "runner_order": runner_order,
    }
    if idempotent:
        payload["idempotent_existing_runner_protection"] = True
    return payload


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    table = _table(conn, table_name)
    row = conn.execute(sa.select(table).where(table.c[id_column] == id_value)).mappings().first()
    return dict(row) if row else {}


def _upsert_row(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    row: dict[str, Any],
) -> None:
    table = _table(conn, table_name)
    values = {
        column.name: row.get(column.name)
        for column in table.columns
        if column.name in row
    }
    existing = conn.execute(
        sa.select(table.c[id_column]).where(table.c[id_column] == values[id_column])
    ).first()
    if existing:
        conn.execute(
            table.update().where(table.c[id_column] == values[id_column]).values(**values)
        )
    else:
        conn.execute(table.insert().values(**values))


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
