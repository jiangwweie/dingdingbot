"""Global PG ownership classification for one exchange snapshot."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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


def lifecycle_ownership_blockers_after_flat_position(
    *,
    ownership: list[ExchangeOrderOwnership],
    open_orders: list[dict[str, Any]],
    current_scope: TicketBoundExchangeScope,
) -> tuple[list[str], list[str]]:
    """Separate safe external manual exits from lifecycle-owned protection.

    The caller must already have proved that the exchange position is flat.
    Returned manual order ids remain visible exchange facts, but they are not
    adopted or made eligible for Ticket-bound cancellation.
    """

    by_exchange_id = {
        str(order.get("exchange_order_id") or "").strip(): order
        for order in open_orders
        if str(order.get("exchange_order_id") or "").strip()
    }
    blockers: list[str] = []
    external_manual_order_ids: list[str] = []
    for item in ownership:
        if not item.blocks_current_domain or not item.blocker:
            continue
        order = by_exchange_id.get(str(item.exchange_order_id or "").strip(), {})
        if _is_external_manual_reduce_only_exit_order(
            ownership=item,
            order=order,
            current_scope=current_scope,
        ):
            external_manual_order_ids.append(item.exchange_order_id)
        else:
            blockers.append(str(item.blocker))
    return _dedupe(blockers), _dedupe(external_manual_order_ids)


def _is_external_manual_reduce_only_exit_order(
    *,
    ownership: ExchangeOrderOwnership,
    order: dict[str, Any],
    current_scope: TicketBoundExchangeScope,
) -> bool:
    if ownership.ownership_class != "unowned_same_domain":
        return False
    client_order_id = str(order.get("client_order_id") or "").strip().lower()
    if client_order_id.startswith("brc-"):
        return False
    if not (
        order.get("reduce_only") is True
        or order.get("close_position") is True
    ):
        return False
    expected_side = "sell" if current_scope.side == "long" else "buy"
    if str(order.get("side") or "").strip().lower() != expected_side:
        return False
    if current_scope.position_mode == "hedge":
        if (
            str(order.get("position_side") or "").strip().upper()
            != current_scope.position_side
        ):
            return False
    elif str(order.get("position_side") or "").strip().upper() not in {"", "BOTH"}:
        return False
    return _decimal(order.get("qty") or order.get("amount")) > 0


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


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))
