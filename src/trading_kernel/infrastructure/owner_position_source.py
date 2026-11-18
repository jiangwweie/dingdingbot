"""Exact bounded GET observations shared by phone previews and persistent operations."""

from collections.abc import Callable
from decimal import Decimal

from src.trading_kernel.application.owner_operation_facts import (
    OwnerOrderObservation,
    OwnerPositionObservation,
)
from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.commands import ExchangeCommand, OrderCommandPayload
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.owner_reduction import OwnerReductionFacts
from src.trading_kernel.domain.readonly_closure import ClosureFill
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_rest_order,
)
from src.trading_kernel.infrastructure.readonly_closure_source import ClosureReader


async def collect_owner_position(
    reader: ClosureReader,
    *,
    aggregate: TradeAggregate,
    commands: tuple[ExchangeCommand, ...],
    accepted_order_ids: dict[str, str],
    operation_id: str | None,
    clock_ms: Callable[[], int],
) -> OwnerPositionObservation:
    a, d = aggregate, aggregate.identity.netting_domain
    symbol = parse_binance_usdm_instrument_id(d.exchange_instrument_id).symbol
    start = clock_ms()
    if len(commands) > 128:
        raise ValueError("owner_order_bound")
    wanted = {a.active_stop_exchange_order_id, a.tp1_exchange_order_id}
    selected = [
        c
        for c in commands
        if isinstance(c.payload, OrderCommandPayload)
        and c.command_id in accepted_order_ids
        and (
            accepted_order_ids[c.command_id] in wanted
            or operation_id is not None
            and c.payload.owner_operation_id == operation_id
        )
    ]
    if len(selected) > 16:
        raise ValueError("owner_current_order_bound")
    observations = []
    for command in selected:
        payload = command.payload
        assert isinstance(payload, OrderCommandPayload)
        oid = accepted_order_ids[command.command_id]
        conditional = payload.order_type in {"stop_market", "take_profit_market"}
        raw = await reader.read(
            "algo_order" if conditional else "order",
            {"algoId": oid} if conditional else {"symbol": symbol, "orderId": oid},
        )
        if not isinstance(raw, dict):
            raise TypeError("owner_order_protocol")
        evidence = parse_rest_order(
            raw,
            account_id=d.account_id,
            conditional=conditional,
            received_at_ms=clock_ms(),
            coverage_complete=True,
        )
        t = evidence.terms
        if (
            t.identity[:4]
            != (d.venue_id, d.account_id, d.exchange_instrument_id, d.position_side)
            or t.exchange_order_id != oid
            or t.client_order_id != command.venue_client_order_id
            or t.side != payload.side
            or t.order_type != payload.order_type.upper()
            or t.quantity != payload.venue_quantity
            or t.close_position != payload.close_position
            or t.price != payload.limit_price
            or t.trigger_price != payload.stop_price
            or t.working_type not in {None, "CONTRACT_PRICE"}
            or t.price_protect
            or evidence.exchange_event_at_ms < command.created_at_ms
        ):
            raise ValueError("owner_order_terms_or_identity_differs")
        status = str(raw["algoStatus" if conditional else "status"])
        fills = []
        if not conditional and evidence.executed_quantity > 0:
            rows = await reader.read(
                "trades",
                {
                    "symbol": symbol,
                    "orderId": oid,
                    "limit": 1000,
                    "startTime": command.created_at_ms,
                    "endTime": clock_ms(),
                },
            )
            if not isinstance(rows, list) or len(rows) >= 1000:
                raise ValueError("owner_fill_bound")
            ids = set()
            for row in rows:
                if (
                    str(row["orderId"]) != oid
                    or row["symbol"] != symbol
                    or row["positionSide"].lower() != d.position_side
                    or row["side"].lower() != payload.side
                    or not command.created_at_ms <= int(row["time"]) <= clock_ms()
                    or str(row["id"]) in ids
                ):
                    raise ValueError("owner_fill_identity_differs")
                ids.add(str(row["id"]))
                fills.append(
                    ClosureFill(
                        trade_id=str(row["id"]),
                        order_id=oid,
                        quantity=Decimal(row["qty"]),
                        price=Decimal(row["price"]),
                        occurred_at_ms=int(row["time"]),
                    )
                )
            if (
                sum((f.quantity for f in fills), Decimal(0))
                != evidence.executed_quantity
            ):
                raise ValueError("owner_fill_incomplete")
        observations.append(
            OwnerOrderObservation(
                command_id=command.command_id,
                evidence=evidence,
                status=status,
                fills=tuple(fills),
            )
        )
    regular_orders = await reader.read("orders", {"symbol": symbol})
    conditional_orders = await reader.read("algos", {"symbol": symbol})
    if (
        not isinstance(regular_orders, list)
        or not isinstance(conditional_orders, list)
        or len(regular_orders) >= 100
        or len(conditional_orders) >= 100
    ):
        raise ValueError("owner_open_orders_incomplete")
    accepted = {
        (
            "conditional"
            if isinstance(c.payload, OrderCommandPayload)
            and c.payload.order_type in {"stop_market", "take_profit_market"}
            else "regular",
            accepted_order_ids[c.command_id],
        )
        for c in commands
        if c.command_id in accepted_order_ids
    }
    for raw in [*regular_orders, *conditional_orders]:
        if (
            not isinstance(raw, dict)
            or raw.get("symbol") != symbol
            or raw.get("positionSide", "").lower() != d.position_side
            or (
                "conditional" if "algoId" in raw else "regular",
                str(raw.get("orderId") or raw.get("algoId")),
            )
            not in accepted
        ):
            raise ValueError("owner_unowned_or_opposite_order")
    mode = await reader.read("mode", {})
    positions = await reader.read("positions", {"symbol": symbol})
    ticker = await reader.read("ticker", {"symbol": symbol})
    now = clock_ms()
    if (
        mode != {"dualSidePosition": True}
        or not isinstance(positions, list)
        or not 1 <= len(positions) <= 2
        or not isinstance(ticker, dict)
        or ticker.get("symbol") != symbol
        or not now - 30000 <= int(ticker.get("time", 0)) <= now
        or now - start >= 30000
    ):
        raise ValueError("owner_current_facts_incomplete")
    own = [
        p
        for p in positions
        if p.get("symbol") == symbol
        and p.get("positionSide", "").lower() == d.position_side
    ]
    if (
        len(own) != 1
        or any(
            p.get("symbol") != symbol or p.get("positionSide") not in {"LONG", "SHORT"}
            for p in positions
        )
        or any(Decimal(p["positionAmt"]) != 0 for p in positions if p not in own)
    ):
        raise ValueError("owner_position_scope_differs")
    quantity = abs(Decimal(own[0]["positionAmt"]))
    stop = next(
        (
            o
            for o in observations
            if o.evidence.terms.exchange_order_id == a.active_stop_exchange_order_id
        ),
        None,
    )
    tp = next(
        (
            o
            for o in observations
            if o.evidence.terms.exchange_order_id == a.tp1_exchange_order_id
        ),
        None,
    )
    tp_fill = Decimal(0) if tp is None else tp.evidence.executed_quantity
    tp_state = (
        "absent"
        if tp is None
        else "filled"
        if tp.status == "FILLED"
        else "cancelled"
        if tp.status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
        else "partial"
        if tp_fill > 0
        else "open"
        if tp.status == "NEW"
        else "unknown"
    )
    stop_live = (
        stop is not None
        and stop.status == "NEW"
        and stop.evidence.executed_quantity == 0
    )
    if stop_live and stop is not None:
        from src.trading_kernel.infrastructure.owner_stop_snapshot import (
            require_current_stop_snapshot,
        )

        stop_command = next(c for c in selected if c.command_id == stop.command_id)
        assert isinstance(stop_command.payload, OrderCommandPayload)
        require_current_stop_snapshot(
            conditional_orders,
            payload=stop_command.payload,
            domain=d,
            order_id=stop.evidence.terms.exchange_order_id,
            client_id=str(stop_command.venue_client_order_id),
            previous_updated_at_ms=stop.evidence.exchange_event_at_ms,
            observed_at_ms=now,
        )
    close_position = stop is not None and stop.evidence.terms.close_position
    protected = (
        quantity
        if stop_live and close_position
        else stop.evidence.terms.quantity
        if stop_live and stop is not None
        else Decimal(0)
    )
    unresolved = any(
        c.status in {S.PREPARED, S.CLAIMED, S.OUTCOME_UNKNOWN}
        and (
            operation_id is None
            or getattr(c.payload, "owner_operation_id", None) != operation_id
        )
        for c in commands
    )
    return OwnerPositionObservation(
        facts=OwnerReductionFacts.model_validate(
            {
                "ticket_id": a.identity.ticket_id,
                "management_revision": a.management_revision,
                "management_mode": a.management_mode,
                "observed_at_ms": now,
                "valid_until_ms": start + 30000,
                "position_quantity": quantity,
                "current_price": Decimal(ticker["price"]),
                "protection_order_id": a.active_stop_exchange_order_id,
                "protected_quantity": protected,
                "stop_price": None
                if stop is None
                else stop.evidence.terms.trigger_price,
                "tp_order_id": a.tp1_exchange_order_id,
                "tp_filled_quantity": tp_fill,
                "tp_state": tp_state,
                "reduction_state": "not_sent",
                "reduction_filled_quantity": Decimal(0),
                "unresolved_other_command": unresolved,
                "stop_triggered": not stop_live,
                "residual_orders": True,
            }
        ),
        orders=tuple(observations),
        protection_close_position=close_position,
    )
