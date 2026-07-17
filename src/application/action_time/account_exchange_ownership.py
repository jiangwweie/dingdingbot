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
from src.infrastructure.account_capacity_hot_path_repository import (
    load_current_account_ticket_ids,
    load_current_command_identity_evidence,
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
    exchange_instrument_id: str = ""
    exchange_order_id: str
    algo_id: str
    client_order_id: str
    client_algo_id: str = ""
    position_bucket: str = "BOTH"
    ownership_state: OwnershipState
    purpose: OrderPurpose
    owner_ticket_id: str | None = None
    blocker: str | None = None


class AccountPositionClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_symbol: str
    exchange_instrument_id: str
    asset_class: str | None = None
    instrument_type: str | None = None
    position_bucket: str = "BOTH"
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
    identities, ticket_instruments = _command_identity_evidence(
        conn,
        account_id=snapshot.account_id,
    )
    order_rows = tuple(
        _classify_order(
            conn,
            order,
            exchange_id=snapshot.exchange_id,
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
    position_rows = _apply_opposite_hedge_bucket_hold(
        position_rows,
        position_mode=snapshot.position_mode or "one_way",
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
    conn: sa.Connection,
    order: ExchangeOpenOrderRow,
    *,
    exchange_id: str,
    position_mode: str,
    identities: dict[tuple[str, str, str], set[tuple[str, str]]],
) -> AccountOrderClassification:
    instrument = _instrument_identity(conn, exchange_id, order.exchange_symbol)
    if instrument is None:
        return _order_result(
            order,
            "external_unowned",
            "external_unknown",
            blocker="account_exchange_order_instrument_identity_missing",
        )
    instrument_id, _asset_class, _instrument_type = instrument
    bucket = _position_bucket(position_mode, order.position_side)
    if bucket is None:
        return _order_result(
            order,
            "mode_or_side_ambiguous",
            "external_unknown",
            exchange_instrument_id=instrument_id,
            blocker="account_exchange_order_position_side_ambiguous",
        )
    matched = set()
    for identity_kind, identity in _order_identity_keys(order):
        matched.update(identities.get((instrument_id, identity_kind, identity), set()))
    ticket_ids = {ticket_id for ticket_id, _role in matched}
    if len(ticket_ids) > 1:
        return _order_result(order, "identity_conflict", "external_unknown", exchange_instrument_id=instrument_id, position_bucket=bucket, blocker="account_exchange_order_identity_conflict")
    if len(ticket_ids) == 1:
        ticket_id = next(iter(ticket_ids))
        roles = {role for owner, role in matched if owner == ticket_id}
        if len(roles) != 1 or next(iter(roles)) not in _PURPOSE_BY_ROLE:
            return _order_result(order, "identity_conflict", "external_unknown", exchange_instrument_id=instrument_id, position_bucket=bucket, blocker="account_exchange_order_role_ambiguous")
        role = next(iter(roles))
        return _order_result(
            order,
            "owned_by_ticket",
            _PURPOSE_BY_ROLE[role],
            exchange_instrument_id=instrument_id,
            position_bucket=bucket,
            owner_ticket_id=ticket_id,
        )
    return _order_result(order, "external_unowned", "external_unknown", exchange_instrument_id=instrument_id, position_bucket=bucket, blocker="account_exchange_order_unknown_global_fail_closed")


def _classify_position(
    conn: sa.Connection,
    position: ExchangePositionRow,
    *,
    exchange_id: str,
    position_mode: str,
    ticket_instruments: dict[str, set[str]],
) -> AccountPositionClassification:
    instrument = _instrument_identity(conn, exchange_id, position.exchange_symbol)
    if instrument is None:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id="unresolved",
            ownership_state="external_unowned",
            blocker="account_exchange_instrument_identity_missing",
        )
    instrument_id, asset_class, instrument_type = instrument
    bucket = _position_bucket(position_mode, position.position_side)
    if bucket is None:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id=instrument_id,
            asset_class=asset_class,
            instrument_type=instrument_type,
            position_bucket="BOTH",
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
            asset_class=asset_class,
            instrument_type=instrument_type,
            position_bucket=bucket,
            ownership_state="identity_conflict",
            blocker="account_exchange_position_multiple_ticket_claims",
        )
    if len(owner_tickets) == 1:
        return AccountPositionClassification(
            exchange_symbol=position.exchange_symbol,
            exchange_instrument_id=instrument_id,
            asset_class=asset_class,
            instrument_type=instrument_type,
            position_bucket=bucket,
            ownership_state="owned_by_ticket",
            owner_ticket_id=next(iter(owner_tickets)),
        )
    return AccountPositionClassification(
        exchange_symbol=position.exchange_symbol,
        exchange_instrument_id=instrument_id,
        asset_class=asset_class,
        instrument_type=instrument_type,
        position_bucket=bucket,
        ownership_state="external_unowned",
        blocker="account_exchange_position_unknown_global_fail_closed",
    )


def _command_identity_evidence(
    conn: sa.Connection,
    *,
    account_id: str,
) -> tuple[
    dict[tuple[str, str, str], set[tuple[str, str]]],
    dict[str, set[str]],
]:
    identity_map: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
    ticket_instruments: dict[str, set[str]] = defaultdict(set)
    ticket_ids = load_current_account_ticket_ids(conn, account_id=account_id)
    rows = load_current_command_identity_evidence(
        conn,
        account_id=account_id,
        ticket_ids=ticket_ids,
    )
    for row in rows:
        ticket_id = row.ticket_id
        role = row.order_role
        instrument_id = row.exchange_instrument_id
        if not ticket_id:
            continue
        if instrument_id:
            ticket_instruments[ticket_id].add(instrument_id)
        for identity_kind, identity in (
            ("exchange_order_id", row.exchange_order_id),
            ("client_order_id", row.client_order_id),
            ("parent_order_id", row.parent_order_id),
        ):
            text = str(identity or "").strip()
            if text:
                identity_map[(instrument_id, identity_kind, text)].add((ticket_id, role))
    return dict(identity_map), dict(ticket_instruments)


def _instrument_identity(
    conn: sa.Connection,
    exchange_id: str,
    symbol: str,
) -> tuple[str, str, str] | None:
    rows = conn.execute(
        sa.text(
            """
            SELECT mapping.exchange_instrument_id, instrument.asset_class,
                   instrument.instrument_type
            FROM brc_symbol_instrument_mappings AS mapping
            JOIN brc_exchange_instruments AS instrument
              ON instrument.exchange_instrument_id = mapping.exchange_instrument_id
            WHERE mapping.symbol = :symbol
              AND mapping.status = 'active'
              AND instrument.exchange_id = :exchange_id
              AND instrument.status = 'active'
            ORDER BY mapping.exchange_instrument_id
            LIMIT 2
            """
        ),
        {"symbol": symbol, "exchange_id": exchange_id},
    ).mappings().all()
    if len(rows) != 1:
        return None
    return (
        str(rows[0]["exchange_instrument_id"]),
        str(rows[0]["asset_class"]),
        str(rows[0]["instrument_type"]),
    )


def _apply_opposite_hedge_bucket_hold(
    rows: tuple[AccountPositionClassification, ...],
    *,
    position_mode: str,
) -> tuple[AccountPositionClassification, ...]:
    if position_mode != "hedge":
        return rows
    buckets_by_instrument: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        buckets_by_instrument[row.exchange_instrument_id].add(row.position_bucket)
    conflicting = {
        instrument_id
        for instrument_id, buckets in buckets_by_instrument.items()
        if {"LONG", "SHORT"}.issubset(buckets)
    }
    if not conflicting:
        return rows
    return tuple(
        row.model_copy(
            update={
                "ownership_state": "identity_conflict",
                "owner_ticket_id": None,
                "blocker": "account_exchange_opposite_hedge_bucket_global_fail_closed",
            }
        )
        if row.exchange_instrument_id in conflicting
        else row
        for row in rows
    )


def _position_bucket(position_mode: str, position_side: str) -> str | None:
    if position_mode != "hedge":
        return "BOTH"
    normalized = str(position_side or "").upper()
    return normalized if normalized in {"LONG", "SHORT"} else None


def _order_identity_keys(order: ExchangeOpenOrderRow) -> tuple[tuple[str, str], ...]:
    values = (
        ("exchange_order_id", order.exchange_order_id),
        ("exchange_order_id", order.algo_id),
        ("client_order_id", order.client_order_id),
        ("client_order_id", order.client_algo_id),
    )
    return tuple((kind, value) for kind, value in values if value)


def _order_result(
    order: ExchangeOpenOrderRow,
    ownership_state: OwnershipState,
    purpose: OrderPurpose,
    *,
    exchange_instrument_id: str = "",
    position_bucket: str | None = None,
    owner_ticket_id: str | None = None,
    blocker: str | None = None,
) -> AccountOrderClassification:
    return AccountOrderClassification(
        exchange_symbol=order.exchange_symbol,
        exchange_instrument_id=exchange_instrument_id,
        exchange_order_id=order.exchange_order_id,
        algo_id=order.algo_id,
        client_order_id=order.client_order_id,
        client_algo_id=order.client_algo_id,
        position_bucket=position_bucket or order.position_side,
        ownership_state=ownership_state,
        purpose=purpose,
        owner_ticket_id=owner_ticket_id,
        blocker=blocker,
    )
