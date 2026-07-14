"""Freeze exact versioned exit-policy identity into future Tickets."""

from __future__ import annotations

from typing import Any, Literal

import json

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.ticket_exit_policy import (
    TicketExitPolicySnapshot,
    canonical_payload_hash,
)


CAPABILITY_ID = "ticket_exit_policy_v1"
LEGACY_UNBOUND_SNAPSHOT = {
    "binding_kind": "legacy_unbound",
    "historical_semantics_not_synthesized": True,
}
LEGACY_UNBOUND_HASH = canonical_payload_hash(LEGACY_UNBOUND_SNAPSHOT)


class TicketExitPolicyBindingError(ValueError):
    """Raised when one exact immutable policy binding cannot be proved."""


class TicketExitPolicyBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    binding_kind: Literal["versioned", "legacy_unbound"]
    exit_policy_id: str
    exit_policy_version: str
    exit_policy_snapshot: dict[str, Any]
    exit_policy_hash: str
    snapshot: TicketExitPolicySnapshot | None


def legacy_unbound_ticket_exit_policy_binding() -> TicketExitPolicyBinding:
    return TicketExitPolicyBinding(
        binding_kind="legacy_unbound",
        exit_policy_id="legacy_unbound",
        exit_policy_version="legacy_unbound",
        exit_policy_snapshot=dict(LEGACY_UNBOUND_SNAPSHOT),
        exit_policy_hash=LEGACY_UNBOUND_HASH,
        snapshot=None,
    )


def resolve_ticket_exit_policy_binding_for_ticket(
    conn: sa.engine.Connection,
    *,
    strategy_group_id: str,
    strategy_version: str,
    event_spec_id: str,
    event_spec_version: str,
    side: str,
) -> TicketExitPolicyBinding:
    """Resolve strict policy only when the fail-disabled capability is enabled."""

    if not _capability_enabled(conn):
        return legacy_unbound_ticket_exit_policy_binding()
    return load_ticket_exit_policy_binding(
        conn,
        strategy_group_id=strategy_group_id,
        strategy_version=strategy_version,
        event_spec_id=event_spec_id,
        event_spec_version=event_spec_version,
        side=side,
    )


def load_ticket_exit_policy_binding(
    conn: sa.engine.Connection,
    *,
    strategy_group_id: str,
    strategy_version: str,
    event_spec_id: str,
    event_spec_version: str,
    side: str,
) -> TicketExitPolicyBinding:
    required = {
        "strategy_group_id": strategy_group_id,
        "strategy_version": strategy_version,
        "event_spec_id": event_spec_id,
        "event_spec_version": event_spec_version,
        "side": side,
    }
    if any(not str(value or "").strip() for value in required.values()):
        raise TicketExitPolicyBindingError("exit_policy_binding_identity_missing")
    if not sa.inspect(conn).has_table("brc_strategy_exit_policies"):
        raise TicketExitPolicyBindingError("exit_policy_authority_missing")
    table = _table(conn, "brc_strategy_exit_policies")
    rows = list(
        conn.execute(
            sa.select(table).where(
                table.c.strategy_group_id == strategy_group_id,
                table.c.strategy_version == strategy_version,
                table.c.event_spec_id == event_spec_id,
                table.c.event_spec_version == event_spec_version,
                table.c.side == side,
                table.c.status == "current",
            )
        ).mappings()
    )
    if not rows:
        raise TicketExitPolicyBindingError("current_exit_policy_missing")
    if len(rows) != 1:
        raise TicketExitPolicyBindingError("multiple_current_exit_policies")
    row = dict(rows[0])
    payload = _mapping(row.get("policy_payload"))
    if not payload:
        raise TicketExitPolicyBindingError("exit_policy_payload_invalid")
    try:
        snapshot = TicketExitPolicySnapshot.model_validate(payload)
    except Exception as exc:
        raise TicketExitPolicyBindingError(
            f"exit_policy_payload_invalid:{type(exc).__name__}"
        ) from exc
    identity_pairs = {
        "strategy_group_id": snapshot.strategy_group_id,
        "strategy_version": snapshot.strategy_version,
        "event_spec_id": snapshot.event_spec_id,
        "event_spec_version": snapshot.event_spec_version,
        "side": snapshot.side,
    }
    for key, expected in required.items():
        if str(identity_pairs[key]) != str(expected):
            raise TicketExitPolicyBindingError(f"exit_policy_{key}_mismatch")
        if str(row.get(key) or "") != str(expected):
            raise TicketExitPolicyBindingError(f"exit_policy_row_{key}_mismatch")
    if str(row.get("exit_policy_id") or "") != snapshot.exit_policy_id:
        raise TicketExitPolicyBindingError("exit_policy_id_mismatch")
    if str(row.get("exit_policy_version") or "") != snapshot.exit_policy_version:
        raise TicketExitPolicyBindingError("exit_policy_version_mismatch")
    if str(row.get("policy_family") or "") != snapshot.policy_family.value:
        raise TicketExitPolicyBindingError("exit_policy_family_mismatch")
    if str(row.get("payload_hash") or "") != snapshot.payload_hash:
        raise TicketExitPolicyBindingError("exit_policy_hash_mismatch")
    return TicketExitPolicyBinding(
        binding_kind="versioned",
        exit_policy_id=snapshot.exit_policy_id,
        exit_policy_version=snapshot.exit_policy_version,
        exit_policy_snapshot=snapshot.model_dump(mode="json"),
        exit_policy_hash=snapshot.payload_hash,
        snapshot=snapshot,
    )


def initialize_ticket_exit_policy_projection(
    conn: sa.engine.Connection,
    *,
    ticket: dict[str, Any],
    now_ms: int,
) -> None:
    if str(ticket.get("exit_policy_id") or "") == "legacy_unbound":
        return
    if not sa.inspect(conn).has_table("brc_ticket_exit_policy_current"):
        raise TicketExitPolicyBindingError("ticket_exit_policy_projection_missing")
    table = _table(conn, "brc_ticket_exit_policy_current")
    existing = conn.execute(
        sa.select(table).where(table.c.ticket_id == str(ticket["ticket_id"]))
    ).mappings().first()
    values = {
        "ticket_id": str(ticket["ticket_id"]),
        "exit_protection_set_id": None,
        "exit_policy_id": str(ticket["exit_policy_id"]),
        "exit_policy_version": str(ticket["exit_policy_version"]),
        "exit_policy_hash": str(ticket["exit_policy_hash"]),
        "exit_execution_snapshot": None,
        "exit_execution_hash": None,
        "actual_r_per_unit": None,
        "resolved_tp1_price": None,
        "resolved_tp1_target_qty": None,
        "tp1_cumulative_filled_qty": 0,
        "tp1_completion_state": "unfilled",
        "remaining_position_qty": None,
        "state": "bound",
        "last_evaluated_watermark_ms": None,
        "next_evaluation_not_before_ms": None,
        "last_decision_kind": None,
        "last_reason_code": None,
        "active_runner_order_id": None,
        "active_runner_generation": None,
        "active_runner_stop": None,
        "runner_break_even_floor": None,
        "runner_floor_applied_at_ms": None,
        "pending_runner_order_id": None,
        "pending_generation": None,
        "replaced_runner_order_id": None,
        "first_blocker": None,
        "updated_at_ms": now_ms,
    }
    if existing:
        if (
            str(existing.get("exit_policy_hash") or "")
            != str(ticket["exit_policy_hash"])
        ):
            raise TicketExitPolicyBindingError("ticket_exit_policy_projection_contradiction")
        return
    conn.execute(table.insert().values(**values))


def _capability_enabled(conn: sa.engine.Connection) -> bool:
    if not sa.inspect(conn).has_table("brc_runtime_capabilities_current"):
        return False
    table = _table(conn, "brc_runtime_capabilities_current")
    row = conn.execute(
        sa.select(table.c.status).where(table.c.capability_id == CAPABILITY_ID)
    ).first()
    return bool(row and str(row[0]) == "enabled")


def _mapping(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
