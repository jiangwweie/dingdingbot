from decimal import Decimal as D

from src.trading_kernel.domain.events import ManagementReviewRequired
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.verified_exit_closure import VerifiedExitClosureProof
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


async def protected_proof(engine, *, review=True):
    t = registered_sor_long_ticket()
    await reach_position_protected(engine, t)
    async with PostgresKernelUnitOfWork(engine) as u:
        a = await u.aggregates.get_for_update(t.identity.ticket_id)
        if review:
            event = ManagementReviewRequired(
                event_id="review-natural",
                ticket_id=t.identity.ticket_id,
                sequence=a.last_event_sequence + 1,
                occurred_at_ms=5000,
                evidence_id="tp-terminal",
                reason="tp1_terminal_attribution_unknown",
            )
            await u.commit_reduction(
                event=event,
                reduction=reduce_event(a, event),
                expected_version=a.version,
            )
        a = await u.aggregates.get(t.identity.ticket_id)
        refs = await u.exchange_commands.list_order_references(t.identity.ticket_id)
        rows = await u.management.command_rows(t.identity.ticket_id)
    return t, make_stop_proof(t, a, refs, rows)


def make_stop_proof(t, a, refs, rows):
    from src.trading_kernel.domain.trade_management import OrderTerms

    orders = []
    entry_id = None
    exit_id = "stop-child"
    for ref in refs:
        row = next(r for r in rows if r["command_id"] == ref.command_id)
        p = row["request_payload"]
        kind = ref.command_kind.value
        terms = OrderTerms(
            venue_id=t.identity.netting_domain.venue_id,
            account_id=t.identity.netting_domain.account_id,
            exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
            position_side=t.identity.netting_domain.position_side,
            order_namespace=ref.namespace.value,
            exchange_order_id=ref.submitted_exchange_order_id,
            client_order_id=ref.venue_client_order_id,
            side=p["side"],
            order_type=p["order_type"].upper(),
            quantity=D(p["quantity"]),
            price=None if p.get("limit_price") is None else D(p["limit_price"]),
            trigger_price=None if p.get("stop_price") is None else D(p["stop_price"]),
            close_position=False,
            reduce_only=p["reduce_only"],
            time_in_force=p.get("time_in_force") or "GTC",
            working_type="CONTRACT_PRICE",
            price_protect=False,
            activation_price=None,
            callback_rate=None,
            price_match="NONE",
            self_trade_prevention_mode="EXPIRE_MAKER",
            good_till_date_ms=0,
        )
        if kind == "entry":
            entry_id = ref.submitted_exchange_order_id
        orders.append(
            {
                "reference": ref,
                "terms": terms,
                "status": "FINISHED"
                if kind == "initial_stop"
                else "FILLED"
                if kind == "entry"
                else "EXPIRED",
                "executed_quantity": t.quantity
                if kind in {"entry", "initial_stop"}
                else D(0),
                "actual_order_id": exit_id if kind == "initial_stop" else None,
                "updated_at_ms": 6000,
            }
        )
    proof = VerifiedExitClosureProof(
        ticket_id=t.identity.ticket_id,
        domain=t.identity.netting_domain,
        expected_version=a.version,
        management_revision=a.management_revision,
        entry_quantity=t.quantity,
        orders=orders,
        entry_fills=[
            {
                "trade_id": "entry1",
                "order_id": entry_id,
                "quantity": t.quantity,
                "price": t.entry_reference_price,
                "occurred_at_ms": 3000,
            }
        ],
        exit_fills=[
            {
                "trade_id": "stop1",
                "order_id": exit_id,
                "quantity": t.quantity,
                "price": t.initial_stop_price,
                "occurred_at_ms": 6000,
            }
        ],
        snapshot={
            "netting_domain": t.identity.netting_domain,
            "quantity": D(0),
            "average_entry_price": None,
            "open_orders": [],
            "observed_at_ms": 7000,
        },
        observed_at_ms=7000,
        valid_until_ms=37000,
    )
    return proof

