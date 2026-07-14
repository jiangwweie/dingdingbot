"""Read-only reconciliation for ambiguous ticket-bound exchange commands."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_command import (
    record_exchange_command_outcome,
)
from src.application.action_time.lifecycle_exchange_command_completion import (
    apply_completed_lifecycle_exchange_sources,
)
from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_exchange_command_domain_hold,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    ExchangeOrderLookupRequest,
    ExchangeOrderLookupResult,
    ExchangeOrderLookupStatus,
    ExchangeOrderLookupView,
    required_exchange_order_lookup_view,
)


VISIBILITY_WINDOW_MS = 30_000
AUTHORITY_BOUNDARY = (
    "ticket_bound_exchange_command_reconciliation; read-only lookup by "
    "persisted client_order_id; no submit, cancel, replace, profile, sizing, "
    "withdrawal, transfer, or file authority"
)


async def run_one_unknown_exchange_command_reconciliation(
    engine: sa.Engine,
    *,
    gateway: Any,
    now_ms: int,
) -> dict[str, Any]:
    """Short select -> transaction-free lookup -> short result projection."""

    with engine.begin() as conn:
        command = select_one_unknown_exchange_command(conn)
    if not command:
        return {
            "schema": "brc.ticket_bound_exchange_command_reconciliation_worker.v1",
            "status": "no_unknown_commands",
            "exchange_read_called": False,
            "exchange_write_called": False,
            "blockers": [],
        }
    identity_blockers = _gateway_identity_blockers(command, gateway)
    if identity_blockers:
        decision = {
            "status": "hard_stopped",
            "exchange_order_id": None,
            "blockers": identity_blockers,
        }
    else:
        decision = await lookup_unknown_exchange_command(
            command=command,
            gateway=gateway,
            now_ms=now_ms,
        )
    with engine.begin() as conn:
        applied = apply_unknown_exchange_command_decision(
            conn,
            command=command,
            decision=decision,
            now_ms=now_ms,
        )
    return {
        "schema": "brc.ticket_bound_exchange_command_reconciliation_worker.v1",
        **applied,
        "exchange_read_called": not identity_blockers,
        "exchange_write_called": False,
        "automatic_resubmit_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def select_one_unknown_exchange_command(
    conn: sa.engine.Connection,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_ticket_bound_exchange_commands",
        sa.MetaData(),
        autoload_with=conn,
    )
    query = (
        sa.select(table)
        .where(table.c.command_state == "outcome_unknown")
        .order_by(table.c.updated_at_ms.asc())
        .limit(1)
    )
    if conn.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    row = conn.execute(query).mappings().first()
    return dict(row) if row else {}


async def lookup_unknown_exchange_command(
    *,
    command: dict[str, Any],
    gateway: Any,
    now_ms: int,
) -> dict[str, Any]:
    try:
        if str(command.get("command_kind") or "") == "cancel_order":
            return await _lookup_unknown_cancel_command(
                command=command,
                gateway=gateway,
                now_ms=now_ms,
            )
        request = _lookup_request_from_command(command)
        expected_view = required_exchange_order_lookup_view(request)
        result = await gateway.find_order_by_client_id(
            request,
            observed_at_ms=now_ms,
        )
    except Exception as exc:
        return {
            "status": "lookup_failed",
            "exchange_order_id": None,
            "blockers": [
                f"exchange_command_lookup_failed:{type(exc).__name__}"
            ],
        }
    return _place_lookup_decision(
        command=command,
        result=result,
        expected_view=expected_view,
        now_ms=now_ms,
    )


async def _lookup_unknown_cancel_command(
    *,
    command: dict[str, Any],
    gateway: Any,
    now_ms: int,
) -> dict[str, Any]:
    target = str(command.get("target_exchange_order_id") or "").strip()
    if not target:
        return {
            "status": "hard_stopped",
            "exchange_order_id": None,
            "blockers": ["cancel_target_exchange_order_id_missing"],
        }
    orders = await gateway.fetch_all_open_orders(str(command["gateway_symbol"]))
    if any(_order_contains_exchange_id(order, target) for order in orders or []):
        return {
            "status": "lookup_failed",
            "exchange_order_id": target,
            "blockers": ["cancel_effect_not_confirmed_target_still_open"],
        }
    return {
        "status": "reconciled_submitted",
        "exchange_order_id": target,
        "blockers": [],
        "lookup_evidence": {
            "lookup_status": ExchangeOrderLookupStatus.CANCEL_EFFECT_CONFIRMED.value,
            "lookup_view": ExchangeOrderLookupView.COMPLETE_OPEN_ORDERS.value,
            "identity_kind": "target_exchange_order_id",
            "client_order_id": str(command.get("client_order_id") or ""),
            "gateway_symbol": str(command.get("gateway_symbol") or ""),
            "observed_at_ms": now_ms,
            "visibility_window_elapsed": True,
        },
    }


def _place_lookup_decision(
    *,
    command: dict[str, Any],
    result: ExchangeOrderLookupResult,
    expected_view: ExchangeOrderLookupView,
    now_ms: int,
) -> dict[str, Any]:
    evidence = _lookup_evidence(
        result,
        visibility_window_elapsed=False,
    )
    if result.lookup_view is not expected_view:
        return {
            "status": "hard_stopped",
            "exchange_order_id": result.exchange_order_id,
            "blockers": ["required_lookup_view_mismatch"],
            "lookup_evidence": evidence,
        }
    if result.status is ExchangeOrderLookupStatus.NOT_FOUND:
        deadline = int(command.get("updated_at_ms") or now_ms) + VISIBILITY_WINDOW_MS
        if now_ms < deadline:
            return {
                "status": "pending_visibility",
                "exchange_order_id": None,
                "blockers": ["exchange_command_visibility_window_active"],
                "lookup_evidence": evidence,
            }
        evidence["visibility_window_elapsed"] = True
        return {
            "status": "reconciled_absent",
            "exchange_order_id": None,
            "blockers": [],
            "lookup_evidence": evidence,
        }
    if result.status is not ExchangeOrderLookupStatus.FOUND:
        return {
            "status": "lookup_failed",
            "exchange_order_id": None,
            "blockers": ["exchange_command_lookup_status_unsupported"],
            "lookup_evidence": evidence,
        }
    exchange_order_id = str(result.exchange_order_id or "").strip()
    actual_client_id = str(result.client_order_id or "").strip()
    actual_symbol = str(result.gateway_symbol or "").strip()
    contradictory = (
        not exchange_order_id
        or (
            bool(actual_client_id)
            and actual_client_id != str(command["client_order_id"])
        )
        or (
            bool(actual_symbol)
            and actual_symbol != str(command["gateway_symbol"])
        )
    )
    if contradictory:
        return {
            "status": "hard_stopped",
            "exchange_order_id": exchange_order_id or None,
            "blockers": ["reconciled_exchange_identity_contradictory"],
            "lookup_evidence": evidence,
        }
    return {
        "status": "reconciled_submitted",
        "exchange_order_id": exchange_order_id,
        "blockers": [],
        "lookup_evidence": evidence,
    }


def apply_unknown_exchange_command_decision(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    decision: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    status = str(decision.get("status") or "")
    blockers = [str(item) for item in decision.get("blockers") or []]
    if status in {"lookup_failed", "pending_visibility"}:
        return {
            "status": status,
            "exchange_command_id": command.get("exchange_command_id"),
            "first_blocker": blockers[0] if blockers else None,
            "blockers": blockers,
        }
    target, outcome = {
        "reconciled_submitted": (
            ExchangeCommandState.RECONCILED_SUBMITTED,
            ExchangeCommandOutcomeClass.RECONCILED_EXCHANGE_TRUTH,
        ),
        "reconciled_absent": (
            ExchangeCommandState.RECONCILED_ABSENT,
            ExchangeCommandOutcomeClass.RECONCILED_ABSENCE,
        ),
        "hard_stopped": (
            ExchangeCommandState.HARD_STOPPED,
            ExchangeCommandOutcomeClass.CONTRADICTORY_TRUTH,
        ),
    }[status]
    recorded = record_exchange_command_outcome(
        conn,
        exchange_command_id=str(command["exchange_command_id"]),
        target_state=target,
        outcome_class=outcome,
        exchange_result={
            "exchange_order_id": decision.get("exchange_order_id"),
            "error_message": blockers[0] if blockers else None,
            **_mapping(decision.get("lookup_evidence")),
        },
        now_ms=now_ms,
    )
    if status == "hard_stopped":
        upsert_exchange_command_domain_hold(
            conn,
            command=recorded,
            blockers=blockers or ["exchange_command_hard_stopped"],
            now_ms=now_ms,
        )
    else:
        resolve_netting_domain_hold_source(
            conn,
            netting_domain_key=str(recorded.get("netting_domain_key") or ""),
            source_kind="exchange_command",
            source_id=str(recorded.get("exchange_command_id") or ""),
            resolution_source=f"exchange_command_{status}",
            now_ms=now_ms,
        )
        if status == "reconciled_submitted":
            apply_completed_lifecycle_exchange_sources(
                conn,
                now_ms=now_ms,
                source_command_id=str(recorded.get("source_command_id") or ""),
            )
    return {
        "status": status,
        "exchange_command_id": recorded.get("exchange_command_id"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }


def _gateway_identity_blockers(
    command: dict[str, Any],
    gateway: Any,
) -> list[str]:
    blockers: list[str] = []
    if str(getattr(gateway, "runtime_account_id", "") or "") != str(
        command.get("account_id") or ""
    ):
        blockers.append("exchange_command_gateway_account_mismatch")
    if str(getattr(gateway, "runtime_exchange_id", "") or "") != str(
        command.get("exchange_id") or ""
    ):
        blockers.append("exchange_command_gateway_exchange_mismatch")
    return blockers


async def reconcile_unknown_exchange_commands(
    conn: sa.engine.Connection,
    *,
    gateway: Any,
    now_ms: int,
    max_commands: int,
) -> dict[str, Any]:
    table = sa.Table(
        "brc_ticket_bound_exchange_commands",
        sa.MetaData(),
        autoload_with=conn,
    )
    rows = list(
        conn.execute(
            sa.select(table)
            .where(table.c.command_state == "outcome_unknown")
            .order_by(table.c.updated_at_ms.asc())
            .limit(max(0, max_commands))
        ).mappings()
    )
    counts = {
        "reconciled_submitted": 0,
        "reconciled_absent": 0,
        "pending_visibility": 0,
        "hard_stopped": 0,
        "lookup_failed": 0,
    }
    results: list[dict[str, Any]] = []
    for raw in rows:
        command = dict(raw)
        identity_blockers = _gateway_identity_blockers(command, gateway)
        decision = (
            {
                "status": "hard_stopped",
                "exchange_order_id": None,
                "blockers": identity_blockers,
            }
            if identity_blockers
            else await lookup_unknown_exchange_command(
                command=command,
                gateway=gateway,
                now_ms=now_ms,
            )
        )
        applied = apply_unknown_exchange_command_decision(
            conn,
            command=command,
            decision=decision,
            now_ms=now_ms,
        )
        status = str(applied["status"])
        counts[status] += 1
        results.append(
            _item(
                command,
                status=status,
                blocker=str(applied.get("first_blocker") or ""),
            )
        )

    blockers: list[str] = []
    if counts["hard_stopped"]:
        blockers.append("exchange_command_hard_stopped")
    if counts["lookup_failed"]:
        blockers.append("exchange_command_lookup_failed")
    if counts["pending_visibility"]:
        blockers.append("exchange_command_visibility_window_active")
    return {
        "schema": "brc.ticket_bound_exchange_command_reconciliation.v1",
        "status": "reconciliation_complete" if rows else "no_unknown_commands",
        "selected_count": len(rows),
        **counts,
        "results": results,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "next_action": (
            "repair_or_continue_unknown_exchange_command_reconciliation"
            if blockers
            else "continue_ticket_bound_lifecycle_from_reconciled_truth"
        ),
        "exchange_read_called": bool(rows),
        "exchange_write_called": False,
        "automatic_resubmit_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _lookup_request_from_command(
    command: dict[str, Any],
) -> ExchangeOrderLookupRequest:
    return ExchangeOrderLookupRequest(
        exchange_id=str(command.get("exchange_id") or ""),
        gateway_symbol=str(command.get("gateway_symbol") or ""),
        command_kind=str(command.get("command_kind") or ""),
        order_role=str(command.get("order_role") or ""),
        order_type=str(command.get("order_type") or ""),
        client_order_id=str(command.get("client_order_id") or ""),
        target_exchange_order_id=(
            str(command["target_exchange_order_id"])
            if command.get("target_exchange_order_id")
            else None
        ),
    )


def _lookup_evidence(
    result: ExchangeOrderLookupResult,
    *,
    visibility_window_elapsed: bool,
) -> dict[str, Any]:
    return {
        "lookup_status": result.status.value,
        "lookup_view": result.lookup_view.value,
        "identity_kind": result.identity_kind,
        "client_order_id": result.client_order_id,
        "gateway_symbol": result.gateway_symbol,
        "observed_at_ms": result.observed_at_ms,
        "visibility_window_elapsed": visibility_window_elapsed,
        "exchange_status": result.exchange_status,
    }


def _order_contains_exchange_id(order: Any, target_exchange_order_id: str) -> bool:
    raw = _mapping(order)
    info = _mapping(raw.get("info"))
    candidates = {
        str(value).strip()
        for value in (
            raw.get("id"),
            raw.get("exchange_order_id"),
            raw.get("orderId"),
            info.get("orderId"),
            info.get("algoId"),
            info.get("triggerOrderId"),
        )
        if value is not None and str(value).strip()
    }
    return target_exchange_order_id in candidates


def _item(
    command: dict[str, Any],
    *,
    status: str,
    blocker: str,
) -> dict[str, Any]:
    return {
        "exchange_command_id": command.get("exchange_command_id"),
        "client_order_id": command.get("client_order_id"),
        "status": status,
        "blockers": [blocker] if blocker else [],
    }
