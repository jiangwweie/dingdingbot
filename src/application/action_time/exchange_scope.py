"""Resolve one Ticket into immutable venue identity and current safety truth.

The lifecycle resolver deliberately separates the identity frozen when a Ticket
was created from the current eligibility of opening a new position.  Pausing a
StrategyGroup or retiring a mapping must stop new ENTRY authority without
preventing risk-reducing protection and reconciliation for an existing Ticket.
"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.domain.netting_domain import build_netting_domain_key


PositionMode = Literal["one_way", "hedge"]
PositionBucket = Literal["BOTH", "LONG", "SHORT"]


class TicketBoundExchangeScope(BaseModel):
    """Typed identity boundary consumed by ticket-bound reads and mutations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: str
    strategy_group_id: str
    runtime_profile_id: str
    runtime_scope_binding_id: str
    runtime_scope_status: str
    account_id: str
    canonical_symbol: str
    exchange_instrument_id: str
    exposure_episode_id: str
    exchange_instrument_status: str
    exchange_id: str
    exchange_symbol: str
    asset_class: str
    side: Literal["long", "short"]
    position_mode: PositionMode
    position_side: Literal["LONG", "SHORT"] | None
    position_bucket: PositionBucket
    netting_domain_key: str
    account_mode_snapshot_id: str
    current_account_mode_snapshot_id: str
    current_entry_eligible: bool
    current_entry_blockers: list[str]

    @property
    def position_domain_key(self) -> str:
        """Compatibility alias; new code should use ``netting_domain_key``."""

        return self.netting_domain_key


class TicketBoundExchangeScopeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["resolved", "blocked"]
    scope: TicketBoundExchangeScope | None = None
    blockers: list[str]


def resolve_ticket_bound_exchange_scope(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    now_ms: int | None = None,
) -> TicketBoundExchangeScopeResolution:
    """Resolve lifecycle identity without granting current ENTRY authority."""

    now_ms = int(now_ms or time.time() * 1000)
    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_ticket_id:
        return _blocked("ticket_exchange_scope_ticket_id_required")

    ticket = _row_by_id(
        conn,
        "brc_action_time_tickets",
        "ticket_id",
        normalized_ticket_id,
    )
    if not ticket:
        return _blocked("ticket_exchange_scope_ticket_missing")

    side = str(ticket.get("side") or "").strip().lower()
    if side not in {"long", "short"}:
        return _blocked("ticket_exchange_scope_side_invalid")

    runtime_scope_binding_id = str(
        ticket.get("runtime_scope_binding_id") or ""
    ).strip()
    runtime_scope = _row_by_id(
        conn,
        "brc_runtime_scope_bindings",
        "runtime_scope_binding_id",
        runtime_scope_binding_id,
    )
    if not runtime_scope:
        return _blocked("ticket_exchange_scope_runtime_binding_missing")
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        if str(runtime_scope.get(key) or "") != str(ticket.get(key) or ""):
            return _blocked(f"ticket_exchange_scope_runtime_binding_{key}_mismatch")

    canonical_symbol = str(ticket.get("symbol") or "").strip()
    instrument_id = str(ticket.get("exchange_instrument_id") or "").strip()
    if not canonical_symbol or not instrument_id:
        return _blocked("ticket_exchange_instrument_identity_incomplete")
    candidate_scope = _row_by_id(
        conn,
        "brc_strategy_group_candidate_scope",
        "candidate_scope_id",
        str(ticket.get("candidate_scope_id") or ""),
    )
    if not candidate_scope:
        return _blocked("ticket_exchange_scope_candidate_missing")
    for key in ("strategy_group_id", "symbol", "side"):
        if str(candidate_scope.get(key) or "") != str(ticket.get(key) or ""):
            return _blocked(f"ticket_exchange_scope_candidate_{key}_mismatch")
    if str(candidate_scope.get("exchange_instrument_id") or "") != instrument_id:
        return _blocked("ticket_exchange_scope_candidate_instrument_mismatch")

    instrument = _row_by_id(
        conn,
        "brc_exchange_instruments",
        "exchange_instrument_id",
        instrument_id,
    )
    if not instrument:
        return _blocked("ticket_exchange_instrument_missing")
    exchange_symbol = str(instrument.get("exchange_symbol") or "").strip()
    exchange_id = str(instrument.get("exchange_id") or "").strip()
    if not exchange_symbol or not exchange_id:
        return _blocked("ticket_exchange_instrument_identity_incomplete")

    budget = _row_by_id(
        conn,
        "brc_budget_reservations",
        "budget_reservation_id",
        str(ticket.get("budget_reservation_id") or ""),
    )
    if not budget:
        return _blocked("ticket_exchange_scope_budget_missing")
    account_id = str(budget.get("account_id") or "").strip()
    if not account_id:
        return _blocked("ticket_exchange_scope_account_missing")
    for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
        if str(budget.get(key) or "") != str(ticket.get(key) or ""):
            return _blocked(f"ticket_exchange_scope_budget_{key}_mismatch")
    budget_ticket_id = str(budget.get("ticket_id") or "").strip()
    if budget_ticket_id and budget_ticket_id != normalized_ticket_id:
        return _blocked("ticket_exchange_scope_budget_ticket_id_mismatch")
    ticket_episode_id = str(ticket.get("exposure_episode_id") or "").strip()
    budget_episode_id = str(budget.get("exposure_episode_id") or "").strip()
    if not ticket_episode_id or not budget_episode_id:
        return _blocked("ticket_exchange_scope_exposure_episode_missing")
    if ticket_episode_id != budget_episode_id:
        return _blocked("ticket_exchange_scope_exposure_episode_mismatch")

    frozen_fact_id = str(ticket.get("account_mode_snapshot_id") or "").strip()
    frozen_fact = _row_by_id(
        conn,
        "brc_runtime_fact_snapshots",
        "fact_snapshot_id",
        frozen_fact_id,
    )
    frozen_mode = _validated_account_mode(
        frozen_fact,
        account_id=account_id,
        exchange_id=exchange_id,
    )
    if frozen_mode is None:
        return _blocked("ticket_exchange_scope_frozen_account_mode_invalid")

    current_fact = _latest_current_account_mode_fact(
        conn,
        account_id=account_id,
        exchange_id=exchange_id,
        now_ms=now_ms,
    )
    if not current_fact:
        return _blocked("ticket_exchange_scope_current_account_mode_missing")
    current_mode = _validated_account_mode(
        current_fact,
        account_id=account_id,
        exchange_id=exchange_id,
    )
    if current_mode is None:
        return _blocked("ticket_exchange_scope_current_account_mode_invalid")
    if current_mode != frozen_mode:
        return _blocked("ticket_exchange_scope_account_mode_changed")

    position_side = side.upper() if frozen_mode == "hedge" else None
    position_bucket: PositionBucket = position_side or "BOTH"
    current_entry_blockers = _current_entry_blockers(
        conn,
        ticket=ticket,
        runtime_scope=runtime_scope,
        candidate_scope=candidate_scope,
        instrument=instrument,
        now_ms=now_ms,
    )
    scope = TicketBoundExchangeScope(
        ticket_id=normalized_ticket_id,
        strategy_group_id=str(ticket.get("strategy_group_id") or ""),
        runtime_profile_id=str(ticket.get("runtime_profile_id") or ""),
        runtime_scope_binding_id=runtime_scope_binding_id,
        runtime_scope_status=str(runtime_scope.get("status") or ""),
        account_id=account_id,
        canonical_symbol=canonical_symbol,
        exchange_instrument_id=instrument_id,
        exposure_episode_id=ticket_episode_id,
        exchange_instrument_status=str(instrument.get("status") or ""),
        exchange_id=exchange_id,
        exchange_symbol=exchange_symbol,
        asset_class=str(instrument.get("asset_class") or ""),
        side=side,
        position_mode=frozen_mode,
        position_side=position_side,
        position_bucket=position_bucket,
        netting_domain_key=build_netting_domain_key(
            account_id=account_id,
            exchange_instrument_id=instrument_id,
            position_mode=frozen_mode,
            position_bucket=position_bucket,
        ),
        account_mode_snapshot_id=frozen_fact_id,
        current_account_mode_snapshot_id=str(
            current_fact.get("fact_snapshot_id") or ""
        ),
        current_entry_eligible=not current_entry_blockers,
        current_entry_blockers=current_entry_blockers,
    )
    return TicketBoundExchangeScopeResolution(
        status="resolved",
        scope=scope,
        blockers=[],
    )


def validate_gateway_identity_for_scope(
    scope: TicketBoundExchangeScope,
    *,
    gateway_account_id: Any,
    gateway_exchange_id: Any,
) -> list[str]:
    """Fail before exchange I/O when the credential binding is not this scope."""

    blockers: list[str] = []
    if str(gateway_account_id or "").strip() != scope.account_id:
        blockers.append("ticket_exchange_scope_gateway_account_mismatch")
    if str(gateway_exchange_id or "").strip() != scope.exchange_id:
        blockers.append("ticket_exchange_scope_gateway_exchange_mismatch")
    return blockers


def _current_entry_blockers(
    conn: sa.engine.Connection,
    *,
    ticket: dict[str, Any],
    runtime_scope: dict[str, Any],
    candidate_scope: dict[str, Any],
    instrument: dict[str, Any],
    now_ms: int,
) -> list[str]:
    blockers: list[str] = []
    if str(runtime_scope.get("status") or "") != "active":
        blockers.append("ticket_exchange_scope_runtime_binding_not_active")
    if int(runtime_scope.get("valid_from_ms") or 0) > now_ms or (
        runtime_scope.get("valid_until_ms") is not None
        and int(runtime_scope["valid_until_ms"]) <= now_ms
    ):
        blockers.append("ticket_exchange_scope_runtime_binding_not_current")
    if str(instrument.get("status") or "") != "active":
        blockers.append("ticket_exchange_instrument_not_active")
    if str(candidate_scope.get("status") or "") != "active":
        blockers.append("ticket_exchange_scope_candidate_not_active")
    return _dedupe(blockers)


def _latest_current_account_mode_fact(
    conn: sa.engine.Connection,
    *,
    account_id: str,
    exchange_id: str,
    now_ms: int,
) -> dict[str, Any]:
    current_table_name = "brc_exchange_account_modes_current"
    if sa.inspect(conn).has_table(current_table_name):
        current_table = _table(conn, current_table_name)
        row = conn.execute(
            sa.select(current_table).where(
                current_table.c.account_id == account_id,
                current_table.c.exchange_id == exchange_id,
                current_table.c.status == "current",
                current_table.c.position_mode_safe.is_(True),
                current_table.c.valid_until_ms > now_ms,
            )
        ).mappings().first()
        if not row:
            return {}
        values = dict(row)
        return {
            "fact_snapshot_id": row.get("fact_snapshot_id"),
            "fact_surface": "account_mode",
            "computed": True,
            "satisfied": True,
            "freshness_state": "fresh",
            "observed_at_ms": row.get("observed_at_ms"),
            "valid_until_ms": row.get("valid_until_ms"),
            "fact_values": {
                "account_id": account_id,
                "exchange_id": exchange_id,
                "account_mode": values.get("position_mode"),
                "dual_side_position": values.get("dual_side_position"),
                "position_mode_safe": values.get("position_mode_safe") is True,
                "runtime_profile_id": values.get("runtime_profile_id"),
                "source": values.get("source_ref"),
            },
        }
    table = _table(conn, "brc_runtime_fact_snapshots")
    rows = conn.execute(
        sa.select(table)
        .where(
            table.c.fact_surface == "account_mode",
            table.c.computed.is_(True),
            table.c.satisfied.is_(True),
            table.c.freshness_state == "fresh",
            sa.or_(
                table.c.valid_until_ms.is_(None),
                table.c.valid_until_ms > now_ms,
            ),
        )
        .order_by(table.c.observed_at_ms.desc(), table.c.created_at_ms.desc())
    ).mappings().all()
    for row in rows:
        values = _json_object(row.get("fact_values"))
        if (
            str(values.get("account_id") or "") == account_id
            and str(values.get("exchange_id") or "") == exchange_id
        ):
            return dict(row)
    return {}


def _validated_account_mode(
    fact: dict[str, Any],
    *,
    account_id: str,
    exchange_id: str,
) -> PositionMode | None:
    if (
        not fact
        or str(fact.get("fact_surface") or "") != "account_mode"
        or fact.get("computed") is not True
        or fact.get("satisfied") is not True
        or str(fact.get("freshness_state") or "") != "fresh"
    ):
        return None
    values = _json_object(fact.get("fact_values"))
    if (
        values.get("position_mode_safe") is not True
        or str(values.get("account_id") or "") != account_id
        or str(values.get("exchange_id") or "") != exchange_id
    ):
        return None
    return _position_mode(values.get("account_mode"))


def _position_mode(value: Any) -> PositionMode | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"one_way", "oneway"}:
        return "one_way"
    if normalized in {"hedge", "hedged", "dual_side"}:
        return "hedge"
    return None


def _blocked(blocker: str) -> TicketBoundExchangeScopeResolution:
    return TicketBoundExchangeScopeResolution(
        status="blocked",
        scope=None,
        blockers=[blocker],
    )


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _json_object(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
