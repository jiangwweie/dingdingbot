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
        namespace = (
            payload.get("order_namespace")
            if row["command_kind"] == "cancel_order"
            else (
                "conditional"
                if payload.get("order_type") in ("stop_market", "take_profit_market")
                else "regular"
            )
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
        baseline = response.get("management_baseline") or response.get(
            "venue_payload", {}
        ).get("management_baseline")
        if baseline is not None:
            expected = OrderTerms.model_validate(baseline)
            if (
                expected.identity != t.identity
                or expected.client_order_id != t.client_order_id
            ):
                continue
        else:
            # Without a confirmed baseline, only an unchanged creation record
            # within the exact dispatch/acceptance interval may establish terms.
            completed = row.get("completed_at_ms")
            creation = (
                evidence.created_at_ms
                if evidence.created_at_ms is not None
                else (
                    evidence.exchange_event_at_ms
                    if evidence.action is OrderAction.NEW
                    else None
                )
            )
            if (
                creation is None
                or completed is None
                or not row["created_at_ms"] <= creation <= completed
            ):
                continue
            if (
                evidence.action not in {OrderAction.NEW, OrderAction.TRADE}
                or evidence.exchange_event_at_ms != creation
            ):
                continue
            if (
                t.side != payload["side"]
                or t.order_type != payload["order_type"].upper()
                or t.close_position != payload.get('close_position',False)
                or t.quantity != (None if payload.get('close_position',False) else Decimal(payload["quantity"]))
                or t.price
                != (
                    None
                    if payload.get("limit_price") is None
                    else Decimal(payload["limit_price"])
                )
                or t.trigger_price
                != (
                    None
                    if payload.get("stop_price") is None
                    else Decimal(payload["stop_price"])
                )
                or t.time_in_force != (payload.get("time_in_force") or "GTC")
            ):
                continue
            expected = t
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
