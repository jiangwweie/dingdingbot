"""Bind observed terms to exact durable commands; prefixes are never authority."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.trade_management import (
    OrderAction,
    OrderEvidence,
    OrderTerms,
    SystemOrderIntent,
)


def accepted_order_identities(rows: list[dict]) -> frozenset[tuple[str, str]]:
    """Order IDs are unique only within a venue namespace."""
    identities = set()
    for row in rows:
        order_id = (row["result_payload"] or {}).get("exchange_order_id")
        if row["status"] not in ("accepted", "reconciled_accepted") or order_id is None:
            continue
        payload = row["request_payload"]
        namespace = payload.get("order_namespace") if row["command_kind"] == "cancel_order" else (
            "conditional" if payload.get("order_type") in ("stop_market", "take_profit_market") else "regular"
        )
        if namespace not in ("regular", "conditional"):
            raise ValueError("accepted order namespace missing")
        identities.add((str(namespace), str(order_id)))
    return frozenset(identities)


def system_intents_for(
    evidence: OrderEvidence, rows: list[dict]
) -> tuple[SystemOrderIntent, ...]:
    result = []
    t = evidence.terms
    for row in rows:
        if row["status"] not in ("accepted", "reconciled_accepted"):
            continue
        payload = row["request_payload"]
        response = row["result_payload"] or {}
        if not row["created_at_ms"] <= evidence.exchange_event_at_ms:
            continue
        if row["command_kind"] == "cancel_order":
            if (
                payload.get("exchange_order_id") == t.exchange_order_id
                and payload.get("order_namespace") == t.order_namespace
            ):
                completed = row.get("completed_at_ms")
                if (
                    completed is not None
                    and row["created_at_ms"]
                    <= evidence.exchange_event_at_ms
                    <= completed
                ):
                    result.append(
                        SystemOrderIntent(
                            command_id=row["command_id"],
                            action=OrderAction.CANCEL,
                            terms=t,
                            exchange_event_at_ms=evidence.exchange_event_at_ms,
                        )
                    )
            continue
        if (
            response.get("exchange_order_id") != t.exchange_order_id
            or row["venue_client_order_id"] != t.client_order_id
        ):
            continue
        namespace = (
            "conditional"
            if payload.get("order_type") in ("stop_market", "take_profit_market")
            else "regular"
        )
        if namespace != t.order_namespace:
            continue
        expected = OrderTerms.model_validate(
            {
                **t.model_dump(),
                "side": payload["side"],
                "order_type": payload["order_type"].upper(),
                "quantity": Decimal(payload["quantity"]),
                "price": payload.get("limit_price"),
                "trigger_price": payload.get("stop_price"),
                "time_in_force": payload.get("time_in_force") or "GTC",
                "close_position": False,
                "reduce_only": False,
                "working_type": "CONTRACT_PRICE",
                "price_protect": False,
                "activation_price": None,
                "callback_rate": None,
                "price_match": "NONE",
                "self_trade_prevention_mode": "NONE",
                "good_till_date_ms": 0,
            }
        )
        result.append(
            SystemOrderIntent(
                command_id=row["command_id"],
                action=OrderAction.NEW,
                terms=expected,
                exchange_event_at_ms=evidence.exchange_event_at_ms
                if evidence.action is OrderAction.NEW
                and row.get("completed_at_ms") is not None
                and evidence.exchange_event_at_ms <= row["completed_at_ms"]
                else evidence.created_at_ms or row["created_at_ms"],
            )
        )
    return tuple(result)
