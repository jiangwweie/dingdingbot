"""Decimal representation must not change durable order identity or observations."""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.observe_trade_management import (
    observe_trade_management,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.trade_management import OrderAction, OrderEvidence
from src.trading_kernel.infrastructure.pg_models import (
    management_order_evidence,
    order_command_baselines,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.manual_management import app_evidence, app_order


def _creation(ticket, command):
    payload = command["request_payload"]
    return OrderEvidence(
        evidence_id="stop-creation",
        terms=app_order(
            ticket,
            order_namespace="conditional"
            if payload["order_type"] == "stop_market"
            else "regular",
            exchange_order_id=command["result_payload"]["exchange_order_id"],
            client_order_id=command["venue_client_order_id"],
            order_type=payload["order_type"].upper(),
            quantity=payload["quantity"],
            price=payload.get("limit_price"),
            trigger_price=payload.get("stop_price"),
            time_in_force=payload.get("time_in_force") or "GTC",
        ),
        action="new",
        exchange_event_at_ms=command["completed_at_ms"],
        received_at_ms=5000,
        created_at_ms=command["completed_at_ms"],
        executed_quantity="0",
        coverage_complete=True,
        known_command_outcome_pending=False,
    )


def _snapshot(ticket, order, observed_at_ms):
    return PositionSnapshot(
        netting_domain=ticket.identity.netting_domain,
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        open_orders=(order,),
        observed_at_ms=observed_at_ms,
    )


def _rescaled(value):
    return Decimal(format(value, "f") + ("00" if "." in format(value, "f") else ".00"))


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["trigger_price", "quantity", "price"])
async def test_baseline_decimal_scale_is_idempotent_across_repository_reload(
    head_template_engine, field
):
    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_position_protected(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as u:
        rows = await u.management.command_rows(ticket.identity.ticket_id)
        kind = "take_profit" if field == "price" else "initial_stop"
        command = next(r for r in rows if r["command_kind"] == kind)
        original = _creation(ticket, command)
        await u.management.save_baseline(ticket.identity.ticket_id, original, rows)
    changed = original.model_copy(
        update={
            "evidence_id": "rest-stop",
            "received_at_ms": 6000,
            "terms": original.terms.model_copy(
                update={field: _rescaled(getattr(original.terms, field))}
            ),
        }
    )
    assert changed.terms == original.terms
    assert changed.terms.model_dump(mode="json") != original.terms.model_dump(
        mode="json"
    )
    async with PostgresKernelUnitOfWork(engine) as u:
        rows = await u.management.command_rows(ticket.identity.ticket_id)
        await u.management.save_baseline(ticket.identity.ticket_id, changed, rows)
    async with engine.connect() as c:
        stored = (await c.execute(sa.select(order_command_baselines))).mappings().one()
    assert stored["confirmed_terms"] == original.terms.model_dump(mode="json")
    assert stored["evidence_id"] == original.evidence_id
    assert stored["confirmed_at_ms"] == original.received_at_ms


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "price",
        "quantity",
        "trigger_price",
        "activation_price",
        "callback_rate",
        "executed_quantity",
    ],
)
async def test_duplicate_evidence_uses_numeric_values_without_rewriting_history(
    head_template_engine, field
):
    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_position_protected(engine, ticket)
    original = app_evidence(ticket).model_copy(
        update={
            "action": OrderAction.TRADE,
            "executed_quantity": Decimal("0.0005"),
            "terms": app_order(
                ticket,
                order_type="TRAILING_STOP_MARKET",
                trigger_price="64000",
                activation_price="65000",
                callback_rate="0.1",
            ),
        }
    )
    changes = (
        {"executed_quantity": _rescaled(original.executed_quantity)}
        if field == "executed_quantity"
        else {
            "terms": original.terms.model_copy(
                update={field: _rescaled(getattr(original.terms, field))}
            )
        }
    )
    repeated = original.model_copy(update={**changes, "received_at_ms": 6000})
    async with PostgresKernelUnitOfWork(engine) as u:
        assert await u.management.save_evidence(ticket.identity.ticket_id, original)
    async with PostgresKernelUnitOfWork(engine) as u:
        assert not await u.management.save_evidence(ticket.identity.ticket_id, repeated)
    async with engine.connect() as c:
        saved = (await c.execute(sa.select(management_order_evidence))).mappings().one()
    assert saved["payload"] == original.model_dump(mode="json")
    assert saved["observed_at_ms"] == original.received_at_ms


@pytest.mark.asyncio
async def test_manual_order_scale_changes_refresh_facts_without_new_lifecycle_events(
    head_template_engine,
):
    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_position_protected(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as u:
        await observe_trade_management(
            u,
            ticket_id=ticket.identity.ticket_id,
            evidence=app_evidence(ticket),
            now_ms=5001,
        )
    terms = app_order(
        ticket,
        quantity=ticket.quantity,
        price=None,
        order_type="STOP_MARKET",
        order_namespace="conditional",
        trigger_price="59000",
    )
    order = VenueOrderSnapshot(
        exchange_order_id=terms.exchange_order_id,
        venue_client_order_id=terms.client_order_id,
        position_side=terms.position_side,
        reduce_only=terms.reduce_only,
        order_namespace=terms.order_namespace,
        terms=terms,
        remaining_quantity=ticket.quantity,
    )
    async with PostgresKernelUnitOfWork(engine) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=_snapshot(ticket, order, 6000),
            ),
        )
        before = await u.aggregates.get(ticket.identity.ticket_id)
        commands = await u.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    rescaled = order.model_copy(
        update={
            "terms": terms.model_copy(
                update={
                    "quantity": _rescaled(terms.quantity),
                    "trigger_price": Decimal("59000.00"),
                }
            ),
            "remaining_quantity": _rescaled(order.remaining_quantity),
        }
    )
    async with PostgresKernelUnitOfWork(engine) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=_snapshot(ticket, rescaled, 7000),
            ),
        )
        after = await u.aggregates.get(ticket.identity.ticket_id)
        assert after.version == before.version
        assert after.last_event_sequence == before.last_event_sequence
        assert after.management_mode == before.management_mode
        assert after.management_observed_at_ms == 7000
        assert (
            await u.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
            == commands
        )
    # A real change still creates a new observation, without an exchange command.
    actual_change = rescaled.model_copy(
        update={"terms": terms.model_copy(update={"trigger_price": Decimal(58900)})}
    )
    async with PostgresKernelUnitOfWork(engine) as u:
        await reconcile_ticket(
            u,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=_snapshot(ticket, actual_change, 8000),
            ),
        )
        after = await u.aggregates.get(ticket.identity.ticket_id)
        assert after.version == before.version + 1
        assert Decimal(after.management_orders[0]["terms"]["trigger_price"]) == Decimal(
            58900
        )
        assert (
            await u.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
            == commands
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"terms": {"price": "65001"}},
        {"terms": {"quantity": "0.0011"}},
        {"terms": {"exchange_order_id": "other-order"}},
        {"terms": {"account_id": "other-account"}},
        {"terms": {"position_side": "short"}},
        {"terms": {"reduce_only": True}},
        {"terms": {"working_type": "MARK_PRICE"}},
        {"executed_quantity": "0.0006"},
        {"exchange_event_at_ms": 5001},
    ],
)
async def test_duplicate_evidence_rejects_real_numeric_or_identity_changes(
    head_template_engine, change
):
    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_position_protected(engine, ticket)
    original = app_evidence(ticket).model_copy(
        update={"action": OrderAction.TRADE, "executed_quantity": Decimal("0.0005")}
    )
    data = original.model_dump(mode="json")
    for key, value in change.items():
        data[key] = {**data[key], **value} if key == "terms" else value
    conflicting = OrderEvidence.model_validate(data)
    async with PostgresKernelUnitOfWork(engine) as u:
        await u.management.save_evidence(ticket.identity.ticket_id, original)
    with pytest.raises(ValueError, match="management evidence identity collision"):
        async with PostgresKernelUnitOfWork(engine) as u:
            await u.management.save_evidence(ticket.identity.ticket_id, conflicting)
    async with engine.connect() as c:
        stored = (
            (await c.execute(sa.select(management_order_evidence))).mappings().one()
        )
    assert stored["payload"] == original.model_dump(mode="json")


@pytest.mark.asyncio
async def test_evidence_comparison_preserves_digits_beyond_decimal_context(
    head_template_engine,
):
    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    await reach_position_protected(engine, ticket)
    original = app_evidence(ticket, price="2135.900000000000000000000000000001")
    same = original.model_copy(
        update={
            "terms": original.terms.model_copy(
                update={"price": Decimal("2135.90000000000000000000000000000100")}
            )
        }
    )
    different = original.model_copy(
        update={
            "terms": original.terms.model_copy(
                update={"price": Decimal("2135.900000000000000000000000000002")}
            )
        }
    )
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 6
        async with PostgresKernelUnitOfWork(engine) as u:
            assert await u.management.save_evidence(ticket.identity.ticket_id, original)
        async with PostgresKernelUnitOfWork(engine) as u:
            assert not await u.management.save_evidence(ticket.identity.ticket_id, same)
        with pytest.raises(ValueError, match="identity collision"):
            async with PostgresKernelUnitOfWork(engine) as u:
                await u.management.save_evidence(ticket.identity.ticket_id, different)
