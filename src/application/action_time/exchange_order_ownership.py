"""Global PG ownership classification for one exchange snapshot."""

from __future__ import annotations

from typing import Any, Literal

import json

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.application.action_time.exchange_scope import (
    TicketBoundExchangeScope,
    resolve_ticket_bound_exchange_scope,
)


OwnershipClass = Literal[
    "owned_by_current_ticket",
    "owned_elsewhere_same_domain",
    "owned_elsewhere_other_domain",
    "unowned_same_domain",
    "unowned_other_domain",
    "identity_conflict",
    "mode_or_side_ambiguous",
]


class ExchangeOrderOwnership(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange_order_id: str
    client_order_id: str
    ownership_class: OwnershipClass
    owner_ticket_id: str | None = None
    owner_netting_domain_key: str | None = None
    blocks_current_domain: bool
    blocker: str | None = None


def classify_exchange_order_ownership(
    conn: sa.engine.Connection,
    *,
    current_scope: TicketBoundExchangeScope,
    open_orders: list[dict[str, Any]],
    now_ms: int,
) -> list[ExchangeOrderOwnership]:
    identities = _pg_order_identities(conn)
    results: list[ExchangeOrderOwnership] = []
    for order in open_orders:
        exchange_id = str(order.get("exchange_order_id") or "").strip()
        client_id = str(order.get("client_order_id") or "").strip()
        exchange_owners = identities["exchange"].get(exchange_id, set()) if exchange_id else set()
        client_owners = identities["client"].get(client_id, set()) if client_id else set()
        if exchange_owners and client_owners and exchange_owners != client_owners:
            results.append(
                ExchangeOrderOwnership(
                    exchange_order_id=exchange_id,
                    client_order_id=client_id,
                    ownership_class="identity_conflict",
                    blocks_current_domain=True,
                    blocker="exchange_order_identity_conflict",
                )
            )
            continue
        owners = exchange_owners | client_owners
        if len(owners) > 1:
            results.append(
                ExchangeOrderOwnership(
                    exchange_order_id=exchange_id,
                    client_order_id=client_id,
                    ownership_class="identity_conflict",
                    blocks_current_domain=True,
                    blocker="exchange_order_multiple_pg_owners",
                )
            )
            continue
        if owners:
            owner_ticket_id = next(iter(owners))
            if owner_ticket_id == current_scope.ticket_id:
                results.append(
                    ExchangeOrderOwnership(
                        exchange_order_id=exchange_id,
                        client_order_id=client_id,
                        ownership_class="owned_by_current_ticket",
                        owner_ticket_id=owner_ticket_id,
                        owner_netting_domain_key=current_scope.netting_domain_key,
                        blocks_current_domain=False,
                    )
                )
                continue
            owner_resolution = resolve_ticket_bound_exchange_scope(
                conn,
                ticket_id=owner_ticket_id,
                now_ms=now_ms,
            )
            if owner_resolution.status != "resolved" or owner_resolution.scope is None:
                results.append(
                    ExchangeOrderOwnership(
                        exchange_order_id=exchange_id,
                        client_order_id=client_id,
                        ownership_class="identity_conflict",
                        owner_ticket_id=owner_ticket_id,
                        blocks_current_domain=True,
                        blocker="exchange_order_owner_scope_unresolved",
                    )
                )
                continue
            owner_scope = owner_resolution.scope
            same_domain = owner_scope.netting_domain_key == current_scope.netting_domain_key
            results.append(
                ExchangeOrderOwnership(
                    exchange_order_id=exchange_id,
                    client_order_id=client_id,
                    ownership_class=(
                        "owned_elsewhere_same_domain"
                        if same_domain
                        else "owned_elsewhere_other_domain"
                    ),
                    owner_ticket_id=owner_ticket_id,
                    owner_netting_domain_key=owner_scope.netting_domain_key,
                    blocks_current_domain=same_domain,
                    blocker=("active_position_resolution" if same_domain else None),
                )
            )
            continue

        order_position_side = str(order.get("position_side") or "").upper()
        if current_scope.position_mode == "hedge" and order_position_side not in {
            "LONG",
            "SHORT",
        }:
            results.append(
                ExchangeOrderOwnership(
                    exchange_order_id=exchange_id,
                    client_order_id=client_id,
                    ownership_class="mode_or_side_ambiguous",
                    blocks_current_domain=True,
                    blocker="exchange_order_position_side_ambiguous",
                )
            )
            continue
        same_domain = (
            current_scope.position_mode == "one_way"
            or order_position_side == current_scope.position_side
        )
        results.append(
            ExchangeOrderOwnership(
                exchange_order_id=exchange_id,
                client_order_id=client_id,
                ownership_class=(
                    "unowned_same_domain" if same_domain else "unowned_other_domain"
                ),
                blocks_current_domain=same_domain,
                blocker=("exchange_only_unknown_order" if same_domain else None),
            )
        )
    return results


def _pg_order_identities(
    conn: sa.engine.Connection,
) -> dict[str, dict[str, set[str]]]:
    exchange: dict[str, set[str]] = {}
    client: dict[str, set[str]] = {}
    if sa.inspect(conn).has_table("brc_ticket_bound_exchange_commands"):
        commands = sa.Table(
            "brc_ticket_bound_exchange_commands",
            sa.MetaData(),
            autoload_with=conn,
        )
        rows = conn.execute(
            sa.select(commands).where(
                ~commands.c.command_state.in_(
                    ("confirmed_rejected", "reconciled_absent")
                )
            )
        ).mappings()
        for row in rows:
            _add(exchange, row.get("exchange_order_id"), row.get("ticket_id"))
            _add(client, row.get("client_order_id"), row.get("ticket_id"))
    if sa.inspect(conn).has_table("brc_ticket_bound_exit_protection_orders"):
        orders = sa.Table(
            "brc_ticket_bound_exit_protection_orders",
            sa.MetaData(),
            autoload_with=conn,
        )
        for row in conn.execute(sa.select(orders)).mappings():
            _add(exchange, row.get("exchange_order_id"), row.get("ticket_id"))
    if sa.inspect(conn).has_table("brc_ticket_bound_protected_submit_attempts"):
        attempts = sa.Table(
            "brc_ticket_bound_protected_submit_attempts",
            sa.MetaData(),
            autoload_with=conn,
        )
        for attempt in conn.execute(sa.select(attempts)).mappings():
            payload = _json_object(attempt.get("submit_result"))
            for order in payload.get("submitted_orders", []):
                if not isinstance(order, dict):
                    continue
                _add(
                    exchange,
                    order.get("exchange_order_id"),
                    attempt.get("ticket_id"),
                )
                _add(
                    client,
                    order.get("client_order_id"),
                    attempt.get("ticket_id"),
                )
    return {"exchange": exchange, "client": client}


def _add(target: dict[str, set[str]], identity: Any, ticket_id: Any) -> None:
    identity_text = str(identity or "").strip()
    ticket_text = str(ticket_id or "").strip()
    if identity_text and ticket_text:
        target.setdefault(identity_text, set()).add(ticket_text)


def _json_object(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}
