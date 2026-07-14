"""Classify all exchange account truth before account-capacity decisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.infrastructure.binance_usdm_account_risk_snapshot import (
    ExchangeOpenOrderRow,
    ExchangePositionRow,
    FullAccountRiskSnapshot,
)


OwnershipState = Literal[
    "owned_by_ticket",
    "owned_by_other_known_ticket",
    "external_unowned",
    "identity_conflict",
    "mode_or_side_ambiguous",
]
OrderPurpose = Literal[
    "working_entry",
    "initial_stop",
    "take_profit",
    "runner_stop",
    "final_exit",
    "external_unknown",
]

_TERMINAL_COMMAND_STATES = {"confirmed_rejected", "reconciled_absent"}
_TERMINAL_TICKET_STATUSES = {
    "expired",
    "finalgate_rejected",
    "invalidated",
    "superseded",
    "closed",
}
_PURPOSE_BY_ROLE: dict[str, OrderPurpose] = {
    "ENTRY": "working_entry",
    "SL": "initial_stop",
    "TP1": "take_profit",
    "RUNNER_SL": "runner_stop",
    "FINAL_EXIT": "final_exit",
}


class AccountOrderClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_symbol: str
    exchange_order_id: str
    algo_id: str
    client_order_id: str
    ownership_state: OwnershipState
    purpose: OrderPurpose
    owner_ticket_id: str | None = None
    blocker: str | None = None


class AccountPositionClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_symbol: str
    exchange_instrument_id: str
    ownership_state: OwnershipState
    owner_ticket_id: str | None = None
    blocker: str | None = None


class AccountExchangeTruthClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    orders: tuple[AccountOrderClassification, ...]
    positions: tuple[AccountPositionClassification, ...]
    new_entry_allowed: bool
    blockers: tuple[str, ...]


def classify_account_exchange_truth(
    conn: sa.Connection,
    *,
    snapshot: FullAccountRiskSnapshot,
) -> AccountExchangeTruthClassification:
    """Return one account-wide ownership decision without a current Ticket bias."""

    if not snapshot.snapshot_ready:
        return AccountExchangeTruthClassification(
            orders=(),
            positions=(),
            new_entry_allowed=False,
            blockers=(snapshot.failure_code or "account_risk_snapshot_not_ready",),
        )
    identities, ticket_instruments = _command_identity_evidence(conn)
    order_rows = tuple(
        _classify_order(
            order,
            position_mode=snapshot.position_mode or "one_way",
            identities=identities,
        )
        for order in (*snapshot.regular_open_orders, *snapshot.algo_open_orders)
    )
    position_rows = tuple(
        _classify_position(
            conn,
            position,
            exchange_id=snapshot.exchange_id,
            position_mode=snapshot.position_mode or "one_way",
            ticket_instruments=ticket_instruments,
        )
        for position in snapshot.positions
    )
    blockers = tuple(
        sorted(
            {
                item.blocker
                for item in (*order_rows, *position_rows)
                if item.blocker
            }
        )
    )
    return AccountExchangeTruthClassification(
        orders=order_rows,
        positions=position_rows,
        new_entry_allowed=not blockers,
        blockers=blockers,
    )


def _classify_order(
    order: ExchangeOpenOrderRow,
    *,
    position_mode: str,
    identities: dict[str, set[tuple[str, str]]],
) -> AccountOrderClassification:
    matched = set()
    for identity in (order.exchange_order_id, order.algo_id, order.client_order_id):
        if identity:
            matched.update(identities.get(identity, set()))
    ticket_ids = {ticket_id for ticket_id, _role in matched}
    if len(ticket_ids) > 1:
        return _order_result(order, "identity_conflict", "external_unknown", blocker="account_exchange_order_identity_conflict")
    if len(ticket_ids) == 1:
        ticket_id = next(iter(ticket_ids))
        roles = {role for owner, role in matched if owner == ticket_id}
        if len(roles) != 1 or next(iter(roles)) not in _PURPOSE_BY_ROLE:
            return _order_result(order, "identity_conflict", "external_unknown", blocker="account_exchange_order_role_ambiguous")
        role = next(iter(roles))
        return _order_result(
            order,
            "owned_by_ticket",
            _PURPOSE_BY_ROLE[role],
            owner_ticket_id=ticket_id,
        )
    if position_mode == "hedge" and order.position_side not in {"LONG", "SHORT"}:
        return _order_result(order, "mode_or_side_ambiguous", "external_unknown", blocker="account_exchange_order_position_side_ambiguous")
    return _order_result(order, "external_unowned", "external_unknown", blocker="account_exchange_order_unknown_global_fail_closed")


def _classify_position(
    conn: sa.Connection,
    position: ExchangePositionRow,
    *,
    exchange_id: str,
    position_mode: str,
    ticket_instruments: dict[str, set[str]],
) -> AccountPositionClassification:
    instrument_id = _instrument_id(conn, exchange_id, position.exchange_symbol)
    if instrument_id is None:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id="unresolved",
            ownership_state="external_unowned",
            blocker="account_exchange_instrument_identity_missing",
        )
    if position_mode == "hedge" and position.position_side not in {"LONG", "SHORT"}:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id=instrument_id,
            ownership_state="mode_or_side_ambiguous",
            blocker="account_exchange_position_side_ambiguous",
        )
    owner_tickets = {
        ticket_id
        for ticket_id, instruments in ticket_instruments.items()
        if instrument_id in instruments
    }
    if len(owner_tickets) > 1:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id=instrument_id,
            ownership_state="identity_conflict",
            blocker="account_exchange_position_multiple_ticket_claims",
        )
    if len(owner_tickets) == 1:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id=instrument_id,
            ownership_state="owned_by_ticket",
            owner_ticket_id=next(iter(owner_tickets)),
        )
    return AccountPositionClassification(
        exchange_symbol=position.exchange_symbol,
        exchange_instrument_id=instrument_id,
        ownership_state="external_unowned",
        blocker="account_exchange_position_unknown_global_fail_closed",
    )


def _command_identity_evidence(
    conn: sa.Connection,
) -> tuple[dict[str, set[tuple[str, str]]], dict[str, set[str]]]:
    table = _table_if_present(conn, "brc_ticket_bound_exchange_commands")
    if table is None:
        return {}, {}
    identity_map: dict[str, set[tuple[str, str]]] = defaultdict(set)
    ticket_instruments: dict[str, set[str]] = defaultdict(set)
    columns = table.c
    tickets = _table_if_present(conn, "brc_action_time_tickets")
    statement = sa.select(table)
    if tickets is not None and {"ticket_id", "status"} <= set(tickets.c.keys()):
        statement = (
            statement.join(tickets, tickets.c.ticket_id == table.c.ticket_id)
            .where(tickets.c.status.not_in(_TERMINAL_TICKET_STATUSES))
        )
    rows = conn.execute(statement).mappings()
    for row in rows:
        if str(row.get("command_state") or "") in _TERMINAL_COMMAND_STATES:
            continue
        ticket_id = str(row.get("ticket_id") or "").strip()
        role = str(row.get("order_role") or "").strip()
        instrument_id = str(row.get("exchange_instrument_id") or "").strip()
        if not ticket_id:
            continue
        if instrument_id:
            ticket_instruments[ticket_id].add(instrument_id)
        for identity in (
            row.get("exchange_order_id"),
            row.get("client_order_id"),
            row.get("parent_order_id"),
        ):
            text = str(identity or "").strip()
            if text:
                identity_map[text].add((ticket_id, role))
    return dict(identity_map), dict(ticket_instruments)


def _instrument_id(conn: sa.Connection, exchange_id: str, symbol: str) -> str | None:
    mapping = _table_if_present(conn, "brc_symbol_instrument_mappings")
    instruments = _table_if_present(conn, "brc_exchange_instruments")
    if mapping is None or instruments is None:
        return None
    required_mapping = {"symbol", "exchange_instrument_id", "status"}
    required_instruments = {"exchange_instrument_id", "exchange_id", "status"}
    if not required_mapping <= set(mapping.c.keys()) or not required_instruments <= set(instruments.c.keys()):
        return None
    row = conn.execute(
        sa.select(mapping.c.exchange_instrument_id)
        .join(
            instruments,
            instruments.c.exchange_instrument_id == mapping.c.exchange_instrument_id,
        )
        .where(mapping.c.symbol == symbol)
        .where(mapping.c.status == "active")
        .where(instruments.c.exchange_id == exchange_id)
        .where(instruments.c.status == "active")
    ).scalar_one_or_none()
    return str(row) if row else None


def _table_if_present(conn: sa.Connection, table_name: str) -> sa.Table | None:
    if not sa.inspect(conn).has_table(table_name):
        return None
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _order_result(
    order: ExchangeOpenOrderRow,
    ownership_state: OwnershipState,
    purpose: OrderPurpose,
    *,
    owner_ticket_id: str | None = None,
    blocker: str | None = None,
) -> AccountOrderClassification:
    return AccountOrderClassification(
        exchange_symbol=order.exchange_symbol,
        exchange_order_id=order.exchange_order_id,
        algo_id=order.algo_id,
        client_order_id=order.client_order_id,
        ownership_state=ownership_state,
        purpose=purpose,
        owner_ticket_id=owner_ticket_id,
        blocker=blocker,
    )
