"""Bounded Binance REST order/amendment backfill, paired with position truth.

Regular amendments are preserved individually; missing conditional history is
reported as a gap, never silently treated as absence of manual intervention.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from src.trading_kernel.domain.management_observation import (
    ManagementScan,
    ManagementScanRequest,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.trade_management import (
    OrderAction,
    OrderEvidence,
    OrderTerms,
)
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_order_update,
    parse_rest_order,
    read_order_amendments,
)


async def collect_management_scan(
    exchange, request: ManagementScanRequest, position: PositionSnapshot
) -> ManagementScan:
    now = request.now_ms
    start = request.since_ms
    if now - start >= 3 * 86400000:
        return ManagementScan(
            ticket_id=request.ticket_id,
            snapshot=position,
            orders=(),
            evidence=(),
            complete=False,
            reason="management_history_retention_gap",
            covered_until_ms=start,
        )
    symbol = request.domain.exchange_instrument_id.split(":")[1]
    async def history(method,key):
        query={"symbol":symbol,"startTime":start,"endTime":now,"limit":100}
        combined=[]
        for _ in range(2):
            page=await method(query)
            if not isinstance(page,list) or len(page)>100:raise ValueError("invalid history page")
            if any(r.get('symbol')!=symbol for r in page):raise ValueError("history symbol mismatch")
            combined.extend(page)
            if len(page)<100:return combined,True
            identifiers=[int(r[key]) for r in page]
            if identifiers!=sorted(set(identifiers)):raise ValueError("history cursor order ambiguous")
            query={**query,key:max(identifiers)+1}
        return combined,False
    collected=await asyncio.gather(history(exchange.fapiPrivateGetAllOrders,"orderId"),history(exchange.fapiPrivateGetAllAlgoOrders,"algoId"))
    rows=[r[0] for r in collected]
    page_complete=all(r[1] for r in collected)
    # Add exact lookups for currently open orders created before this window.
    # Historical endpoints filter creation time, not every later modification.
    for order in position.open_orders:
        ns = 1 if order.order_namespace == "conditional" else 0
        if not any(
            str(r.get("algoId" if ns else "orderId")) == order.exchange_order_id
            for r in rows[ns]
        ):
            method = (
                exchange.fapiPrivateGetAlgoOrder if ns else exchange.fapiPrivateGetOrder
            )
            row = await method(
                {
                    "symbol": symbol,
                    "algoId" if ns else "orderId": int(order.exchange_order_id),
                }
            )
            rows[ns].append(row)
    for known in request.known_orders:
        ns = 1 if known.order_namespace == "conditional" else 0
        if not any(
            str(r.get("algoId" if ns else "orderId")) == known.exchange_order_id
            for r in rows[ns]
        ):
            method = (
                exchange.fapiPrivateGetAlgoOrder if ns else exchange.fapiPrivateGetOrder
            )
            row = await method(
                {
                    "symbol": symbol,
                    "algoId" if ns else "orderId": int(known.exchange_order_id),
                }
            )
            rows[ns].append(row)
    complete = page_complete
    reason = None if page_complete else "management_history_page_full"
    events = []
    open_terms = []
    amendment_reads = 0
    remaining = {}
    lost=getattr(exchange,"management_lost_before_ms",None)
    if type(lost) is int and lost>=start:
        complete=False;reason="management_stream_buffer_gap"
    previous = {t.identity: t for t in request.known_orders}
    triggered_children = {
        str(row.get("actualOrderId")): row
        for row in rows[1]
        if row.get("actualOrderId") not in (None, "", 0, "0")
    }

    for conditional, page in zip((False, True), rows, strict=True):
        if not isinstance(page, list):
            raise TypeError("management order page invalid")
        for raw in page:
            if raw["symbol"] != symbol:
                raise ValueError("management instrument mismatch")
            if str(raw["positionSide"]).lower() != request.domain.position_side:
                continue
            if not conditional and str(raw["orderId"]) in triggered_children:
                parent = triggered_children[str(raw["orderId"])]
                if any(
                    raw[key] != parent[key]
                    for key in ("symbol", "side", "positionSide")
                ):
                    complete = False
                    reason = "conditional_child_identity_mismatch"
                else:
                    continue
            e = parse_rest_order(
                raw,
                account_id=request.domain.account_id,
                conditional=conditional,
                received_at_ms=now,
                coverage_complete=True,
            )
            before = previous.get(e.terms.identity)
            if before is not None and before != e.terms:
                e = e.model_copy(
                    update={"action": OrderAction.AMENDMENT, "before_terms": before}
                )
            status = str(raw["algoStatus"] if conditional else raw["status"])
            if status in ("NEW", "PARTIALLY_FILLED", "TRIGGERING"):
                open_terms.append(e.terms)
                remaining[(e.terms.order_namespace, e.terms.exchange_order_id)] = (
                    None
                    if e.terms.quantity is None
                    else max(Decimal(0), e.terms.quantity - e.executed_quantity)
                )
            if (
                conditional
                and status == "NEW"
                and raw["updateTime"] > raw["createTime"]
                and (before is None or before == e.terms)
                and e.terms.order_type != "TRAILING_STOP_MARKET"
            ):
                # No conditional amendment journal is documented. A changed-back order
                # cannot be declared untouched solely from the final identical terms.
                complete = False
                reason = "conditional_revision_history_unproven"
            if start <= e.exchange_event_at_ms <= now:
                events.append(e)
            if (
                e.created_at_ms is not None
                and start <= e.created_at_ms <= now
                and e.exchange_event_at_ms != e.created_at_ms
                and not (e.terms.client_order_id or "").startswith("brc-")
            ):
                events.append(
                    e.model_copy(
                        update={
                            "evidence_id": e.evidence_id + ":external-history",
                            "action": OrderAction.NEW,
                            "before_terms": None,
                        }
                    )
                )
            if not conditional and e.terms.order_type == "LIMIT" and (e.terms.client_order_id or "").startswith("brc-"):
                if amendment_reads >= 16:
                    complete = False
                    reason = "management_amendment_budget_exhausted"
                    continue
                amendment_reads += 1
                amendments = await read_order_amendments(
                    exchange,
                    symbol=symbol,
                    order_id=e.terms.exchange_order_id,
                    start_ms=start,
                    end_ms=now,
                )
                if amendments.possibly_truncated:
                    complete = False
                    reason = "management_amendment_page_full"
                for change in amendments.rows:
                    old = OrderTerms.model_validate(
                        {
                            **e.terms.model_dump(),
                            "price": change.before_price,
                            "quantity": change.before_quantity,
                        }
                    )
                    new = OrderTerms.model_validate(
                        {
                            **e.terms.model_dump(),
                            "price": change.after_price,
                            "quantity": change.after_quantity,
                        }
                    )
                    events.append(
                        OrderEvidence(
                            evidence_id=f"amend:{request.domain.account_id}:{symbol}:{change.order_id}:{change.amendment_id}",
                            terms=new,
                            action=OrderAction.AMENDMENT,
                            exchange_event_at_ms=change.at_ms,
                            received_at_ms=now,
                            created_at_ms=e.created_at_ms,
                            executed_quantity=Decimal(0),
                            coverage_complete=True,
                            known_command_outcome_pending=False,
                            before_terms=old,
                        )
                    )
    # Open-order snapshots contain old orders whose creation precedes the history
    # window. Merge exact known terms, but never infer their unknown amendments.
    by_id = {(t.order_namespace, t.exchange_order_id): t for t in open_terms}
    enriched = []
    for order in position.open_orders:
        key = (order.order_namespace, order.exchange_order_id)
        terms = by_id.get(key)
        if terms is None:
            terms = next(
                (
                    t
                    for t in request.known_orders
                    if (t.order_namespace, t.exchange_order_id) == key
                ),
                None,
            )
            if terms is None:
                complete = False
                reason = "management_open_order_not_in_history"
        enriched.append(
            order.model_copy(
                update={"terms": terms, "remaining_quantity": remaining.get(key)}
            )
        )
    # An update stream or venue-confirmed amend coverage is still required to
    # prove absence of same-ID conditional mutations. Mark suspected NEW updates
    # without previous terms as unresolved rather than claiming a manual actor.
    stream = getattr(exchange, "management_events", None)
    if (
        callable(stream)
        and getattr(exchange, "management_started_ms", None) is not None
    ):
        for received, raw in stream(
            symbol=symbol, side=request.domain.position_side, start_ms=start, end_ms=now
        ):
            if (
                raw.get("e") == "ORDER_TRADE_UPDATE"
                and str(raw.get("o", {}).get("i")) in triggered_children
            ):
                continue
            streamed = parse_order_update(
                raw,
                account_id=request.domain.account_id,
                received_at_ms=received,
                coverage_complete=True,
            )
            if streamed.action is OrderAction.AMENDMENT:
                before = previous.get(streamed.terms.identity)
                if before is not None and before != streamed.terms:
                    streamed = streamed.model_copy(update={"before_terms": before})
            events.append(streamed)
    events = sorted(
        {e.evidence_id: e for e in events}.values(),
        key=lambda e: (e.exchange_event_at_ms, e.evidence_id),
    )
    return ManagementScan(
        ticket_id=request.ticket_id,
        snapshot=position.model_copy(
            update={
                "open_orders": tuple(enriched),
                "orders_complete": complete and position.orders_complete,
            }
        ),
        orders=tuple(t for t in (o.terms for o in enriched) if t is not None),
        evidence=tuple(
            e.model_copy(update={"coverage_complete": complete}) for e in events
        ),
        complete=complete,
        reason=reason,
        covered_until_ms=now if complete else start,
    )
