"""GET-only collection for a single controlled close, with exact durable identities."""

from collections.abc import Callable
from decimal import Decimal

from src.trading_kernel.application.owner_operation_facts import (
    OwnerReductionObservation,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    OrderCommandPayload,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.exit_execution import EntryFill
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionFacts,
    OwnerReductionState,
)
from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
from src.trading_kernel.infrastructure.readonly_closure_source import ClosureReader


async def collect_owner_reduction(
    reader: ClosureReader,
    *,
    aggregate: TradeAggregate,
    state: OwnerReductionState,
    authorization_id: str,
    commands: tuple[ExchangeCommand, ...],
    accepted_order_ids: dict[str, str],
    clock_ms: Callable[[], int],
) -> OwnerReductionObservation:
    a, p = aggregate, state.preview
    d = a.identity.netting_domain
    symbol = parse_binance_usdm_instrument_id(d.exchange_instrument_id).symbol
    side = "SELL" if d.position_side == "long" else "BUY"
    start = clock_ms()
    if a.identity.ticket_id != p.ticket_id or len(commands) > 128:
        raise ValueError("owner_facts_scope_bound")

    def source(order_id, kind):
        matches = [
            c
            for c in commands
            if c.kind in kind and accepted_order_ids.get(c.command_id) == order_id
        ]
        if len(matches) != 1 or not isinstance(matches[0].payload, OrderCommandPayload):
            raise ValueError("owner_order_source_identity_missing")
        return matches[0]

    def exact(raw, command, order_id, *, conditional):
        payload = command.payload
        assert isinstance(payload, OrderCommandPayload)
        if (
            not isinstance(raw, dict)
            or str(raw.get("algoId" if conditional else "orderId")) != order_id
            or raw.get("symbol") != symbol
            or raw.get("positionSide") != d.position_side.upper()
            or raw.get("side") != side
            or raw.get("clientAlgoId" if conditional else "clientOrderId")
            != command.venue_client_order_id
            or raw.get("orderType" if conditional else "type")
            != payload.order_type.upper()
        ):
            raise ValueError("owner_order_identity_differs")
        qty = Decimal(str(raw.get("quantity" if conditional else "origQty")))
        if conditional:
            if (
                type(raw.get("closePosition")) is not bool
                or raw["closePosition"] != payload.close_position
                or (qty != 0 if payload.close_position else qty != payload.quantity)
                or Decimal(str(raw.get("triggerPrice"))) != payload.stop_price
            ):
                raise ValueError("owner_stop_terms_differs")
        elif qty != payload.quantity:
            raise ValueError("owner_order_quantity_differs")
        if payload.order_type == "limit" and (
            Decimal(str(raw.get("price"))) != payload.limit_price
            or raw.get("timeInForce") != payload.time_in_force
        ):
            raise ValueError("owner_tp_terms_differs")
        return raw

    stop_id = a.active_stop_exchange_order_id
    if stop_id is None:
        raise ValueError("owner_stop_identity_missing")
    stop_cmd = source(stop_id, {K.INITIAL_STOP, K.REPLACE_PROTECTION})
    stop = exact(
        await reader.read("algo_order", {"algoId": stop_id}),
        stop_cmd,
        stop_id,
        conditional=True,
    )
    cp = stop_cmd.payload.close_position
    stop_triggered = (
        stop.get("algoStatus") not in {"NEW"}
        or Decimal(str(stop.get("actualQty") or "0")) != 0
    )
    tp_id = p.cancel_tp_order_id
    tp_fill, tp_state = a.tp1_filled_qty, "absent"
    if tp_id:
        tp_cmd = source(tp_id, {K.TAKE_PROFIT})
        tp = exact(
            await reader.read("order", {"symbol": symbol, "orderId": tp_id}),
            tp_cmd,
            tp_id,
            conditional=False,
        )
        tp_fill = Decimal(str(tp["executedQty"]))
        if not tp_fill.is_finite() or not 0 <= tp_fill <= tp_cmd.payload.quantity:
            raise ValueError("owner_tp_fill_quantity_invalid")
        tp_state = (
            "filled"
            if tp["status"] == "FILLED"
            else "partial"
            if tp_fill > p.source_tp_filled_quantity
            else "cancelled"
            if tp["status"] in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
            else "open"
            if tp["status"] == "NEW"
            else "unknown"
        )
    reductions = [
        c
        for c in commands
        if c.kind is K.OWNER_REDUCE
        and isinstance(c.payload, OrderCommandPayload)
        and c.payload.owner_operation_id == state.operation_id
    ]
    if len(reductions) > 1:
        raise ValueError("owner_duplicate_reduction_commands")
    command = reductions[0] if reductions else None
    fills: tuple[EntryFill, ...] = ()
    reduction_state, executed, order = "not_sent", Decimal(0), None
    if command:
        reduction_id = accepted_order_ids.get(command.command_id)
        if command.status in {S.ACCEPTED, S.RECONCILED_ACCEPTED} and reduction_id:
            order = exact(
                await reader.read("order", {"symbol": symbol, "orderId": reduction_id}),
                command,
                reduction_id,
                conditional=False,
            )
            executed = Decimal(str(order["executedQty"]))
            reduction_state = (
                "terminal"
                if order["status"]
                in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}
                else "working"
            )
            if executed > 0 and reduction_state == "terminal":
                rows = await reader.read(
                    "trades",
                    {
                        "symbol": symbol,
                        "orderId": reduction_id,
                        "startTime": command.created_at_ms,
                        "endTime": clock_ms(),
                        "limit": 1000,
                    },
                )
                if not isinstance(rows, list) or len(rows) >= 1000:
                    raise ValueError("owner_reduction_trade_bound")
                selected: dict[str, EntryFill] = {}
                for row in rows:
                    if (
                        not isinstance(row, dict)
                        or str(row.get("orderId")) != reduction_id
                        or row.get("symbol") != symbol
                        or row.get("side") != side
                        or row.get("positionSide") != d.position_side.upper()
                        or not command.created_at_ms <= int(row["time"]) <= clock_ms()
                    ):
                        raise ValueError("owner_reduction_fill_identity")
                    fill = EntryFill(
                        trade_id=str(row["id"]),
                        quantity=Decimal(row["qty"]),
                        price=Decimal(row["price"]),
                    )
                    if fill.trade_id in selected and selected[fill.trade_id] != fill:
                        raise ValueError("owner_reduction_duplicate_fill_conflict")
                    selected[fill.trade_id] = fill
                fills = tuple(selected.values())
                if sum((f.quantity for f in fills), Decimal(0)) != executed:
                    raise ValueError("owner_reduction_fill_incomplete")
        elif command.status in {S.REJECTED, S.RECONCILED_ABSENT, S.SUPERSEDED}:
            reduction_state = "rejected"
        elif command.status is S.OUTCOME_UNKNOWN:
            reduction_state = "unknown"
        elif command.status is not S.PREPARED:
            reduction_state = "working"
    # Fresh current facts are gathered after historical I/O; do not redate old facts.
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
        or not 1 <= len(positions) <= 3
        or not isinstance(ticker, dict)
        or ticker.get("symbol") != symbol
        or not max(1, now - 30000) <= int(ticker.get("time", 0)) <= now
        or now - start > 30000
    ):
        raise ValueError("owner_current_facts_incomplete")
    selected_positions = [
        r
        for r in positions
        if r.get("symbol") == symbol
        and r.get("positionSide") == d.position_side.upper()
    ]
    if len(selected_positions) != 1 or any(
        r.get("symbol") != symbol or r.get("positionSide") not in {"LONG", "SHORT"}
        for r in positions
    ):
        raise ValueError("owner_position_scope_differs")
    if any(
        Decimal(str(r["positionAmt"])) != 0
        for r in positions
        if r["positionSide"] != d.position_side.upper()
    ):
        raise ValueError("owner_opposite_exposure")
    signed = Decimal(str(selected_positions[0]["positionAmt"]))
    if (
        signed < 0
        and d.position_side == "long"
        or signed > 0
        and d.position_side == "short"
    ):
        raise ValueError("owner_position_sign_differs")
    quantity = abs(signed)
    if not stop_triggered:
        from src.trading_kernel.infrastructure.owner_stop_snapshot import (
            require_current_stop_snapshot,
        )

        require_current_stop_snapshot(
            conditional_orders,
            payload=stop_cmd.payload,
            domain=d,
            order_id=stop_id,
            client_id=stop_cmd.venue_client_order_id,
            previous_updated_at_ms=int(stop["updateTime"]),
            observed_at_ms=now,
        )
    protected = (
        quantity
        if cp and not stop_triggered
        else stop_cmd.payload.quantity
        if not stop_triggered
        else Decimal(0)
    )
    unresolved = any(
        c.status in {S.PREPARED, S.CLAIMED, S.OUTCOME_UNKNOWN}
        and not (
            isinstance(c.payload, OrderCommandPayload)
            and c.payload.owner_operation_id == state.operation_id
        )
        and not (
            isinstance(c.payload, CancelCommandPayload)
            and c.payload.owner_operation_id == state.operation_id
        )
        for c in commands
    )
    facts = OwnerReductionFacts.model_validate(
        {
            "ticket_id": a.identity.ticket_id,
            "management_revision": a.management_revision,
            "management_mode": a.management_mode,
            "observed_at_ms": now,
            "valid_until_ms": start + 30000,
            "position_quantity": quantity,
            "current_price": Decimal(str(ticker["price"])),
            "protection_order_id": stop_id,
            "protected_quantity": protected,
            "stop_price": stop_cmd.payload.stop_price,
            "tp_order_id": tp_id,
            "tp_filled_quantity": tp_fill,
            "tp_state": tp_state,
            "reduction_state": reduction_state,
            "reduction_filled_quantity": executed,
            "reduction_operation_id": state.operation_id if command else None,
            "unresolved_other_command": unresolved,
            "stop_triggered": stop_triggered,
            "residual_orders": True,
        }
    )
    proof = None
    if (
        command
        and isinstance(command.payload, OrderCommandPayload)
        and order
        and executed > 0
        and reduction_state == "terminal"
        and quantity > 0
        and not stop_triggered
    ):
        proof = OwnerReductionProof(
            source_stage="runner"
            if a.status is AggregateStatus.RUNNER_PROTECTED
            else "wait_price"
            if a.owner_reduction_context
            else "pre_tp",
            source_tp_filled_quantity=p.source_tp_filled_quantity,
            authorization_id=authorization_id,
            operation_id=state.operation_id,
            ticket_id=a.identity.ticket_id,
            domain=d,
            command_id=command.command_id,
            exchange_order_id=accepted_order_ids[command.command_id],
            venue_client_order_id=str(command.venue_client_order_id),
            order_status=order["status"],
            requested_quantity=command.payload.quantity,
            executed_quantity=executed,
            source_quantity=p.source_quantity,
            remaining_quantity=quantity,
            fills=fills,
            original_tp_order_id=tp_id,
            original_tp_cancelled=tp_state == "cancelled",
            original_tp_filled_quantity=tp_fill,
            protection_order_id=stop_id,
            protection_price=stop_cmd.payload.stop_price,
            protected_quantity=protected,
            observed_at_ms=now,
            valid_until_ms=start + 30000,
        )
    return OwnerReductionObservation(
        facts=facts, protection_close_position=cp, proof=proof
    )
