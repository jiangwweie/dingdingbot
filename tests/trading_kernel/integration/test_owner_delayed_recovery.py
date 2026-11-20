from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.advance_owner_adjustment import (
    advance_owner_adjustment,
)
from src.trading_kernel.application.advance_owner_position_operation import (
    advance_owner_position_operation,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind as K,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandStatus as S,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
from tests.trading_kernel.support.owner_delay_scenarios import (
    DelayedSource,
    accepted_operation,
)
from tests.trading_kernel.support.owner_operation_source import OwnerOperationVenue


@pytest.mark.asyncio
async def test_full_close_refreshes_facts_after_restart_before_dispatch(
    head_template_engine,
):
    e = head_template_engine
    t, op = await accepted_operation(e, "position_close")
    factory = lambda: PostgresKernelUnitOfWork(e)
    source = DelayedSource()
    venue = OwnerOperationVenue()

    async def tick(at):
        source.at = at
        async with factory() as u:
            row = await u.owner_position_operations.get(op["operation_id"])
        return await advance_owner_adjustment(
            factory, source, row, now_ms=at, timeout_seconds=1
        )

    assert await tick(7000) == "tp_cancelling"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7100)
    assert await tick(8000) == "closure_pending"
    restarted = DelayedSource()
    restarted.at = 15000
    async with factory() as u:
        row = await u.owner_position_operations.get(op["operation_id"])
    await advance_owner_adjustment(
        factory, restarted, row, now_ms=15000, timeout_seconds=1
    )
    assert restarted.calls > 0
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        commands = [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.EXIT
        ]
        assert len(commands) == 1
        assert row["payload"]["facts"]["observed_at_ms"] == 15000
        assert (
            await u.owner_position_operations.command_send_blocker(
                commands[0], a, now_ms=15100
            )
            is None
        )
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=15100)

    from decimal import Decimal

    from src.trading_kernel.application.reconcile_ticket import (
        ReconcileTicketRequest,
        reconcile_ticket,
    )
    from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot

    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.tp1_exchange_order_id is None
        stop = a.active_stop_exchange_order_id
        flat = PositionSnapshot(
            netting_domain=t.identity.netting_domain, quantity=Decimal(0),
            average_entry_price=None, observed_at_ms=15200,
            open_orders=(VenueOrderSnapshot(
                exchange_order_id=stop, venue_client_order_id="brc-stop",
                position_side=t.identity.netting_domain.position_side,
                reduce_only=True, order_namespace="conditional",
            ),),
        )
        result = await reconcile_ticket(u, ReconcileTicketRequest(
            ticket_id=t.identity.ticket_id, snapshot=flat
        ))
        assert result.status.value == "position_flat_recorded"
        cancellations = [
            c for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.CANCEL_ORDER
        ]
        assert [(c.payload.purpose, c.payload.order_namespace) for c in cancellations] == [
            ("owner_tp", "regular"), ("reconciliation_cleanup", "conditional")
        ]
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=15300)
    async with factory() as u:
        result = await reconcile_ticket(u, ReconcileTicketRequest(
            ticket_id=t.identity.ticket_id,
            snapshot=flat.model_copy(update={"open_orders": (), "observed_at_ms": 15400})
        ))
        assert result.status.value == "matched"


@pytest.mark.asyncio
async def test_original_tp_restoration_keeps_its_phase_until_delayed_dispatch(
    head_template_engine, monkeypatch
):
    from src.trading_kernel.infrastructure.pg_signal_repository import (
        PostgresSignalRepository,
    )

    monkeypatch.setattr(
        PostgresSignalRepository,
        "get_instrument_rules",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        "src.trading_kernel.application.owner_operation_exit.read_original_operation_exit",
        AsyncMock(return_value=None),
    )
    e = head_template_engine
    t, op = await accepted_operation(e, "position_reduce")
    factory = lambda: PostgresKernelUnitOfWork(e)
    source = DelayedSource()
    venue = OwnerOperationVenue()

    async def tick(at):
        source.at = at
        return await advance_owner_position_operation(
            factory,
            source,
            now_ms=at,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
        )

    assert await tick(7000) == "protection_converting"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7100)
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7200)
    assert await tick(8000) == "tp_cancelling"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=8100)
    assert await tick(9000) == "reduction_pending"

    class Rejected(OwnerOperationVenue):
        async def execute(self, request):
            return ExchangeCommandResult(
                status=S.REJECTED, reason="fixture_reject", observed_at_ms=9101
            )

    # Rejection is an expected result, so dispatch through the actual application.
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )

    await dispatch_one_command(
        factory,
        Rejected(),
        DispatchCommandRequest(
            worker_id="delay",
            ticket_id=t.identity.ticket_id,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=9100,
            lease_until_ms=10100,
            timeout_seconds=1,
        ),
        clock_ms=lambda: 9100,
    )
    assert await tick(10000) == "restore_required"
    assert await tick(11000) == "restoring_original_tp"
    original_reader = source.read_owner_reduction

    async def outage(**kwargs):
        raise TimeoutError()

    source.read_owner_reduction = outage
    assert await tick(12000) == "facts_unavailable"
    async with factory() as u:
        assert (await u.owner_position_operations.get(op["operation_id"]))[
            "state"
        ] == "restoring_original_tp"
    source.read_owner_reduction = original_reader
    await tick(18000)
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        c = await u.exchange_commands.get(row["payload"]["restoration_command_ids"][0])
        assert row["state"] == "restoring_original_tp"
        assert (
            await u.owner_position_operations.command_send_blocker(c, a, now_ms=18100)
            is None
        )
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=18100)
    assert await tick(19000) == "restored"
    async with factory() as u:
        row = await u.owner_position_operations.get(op["operation_id"])
        assert row["completed_at_ms"] == 19000 and row["state"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["position_reduce", "manual_tp_set"])
async def test_natural_partial_tp_hands_back_before_old_owner_size_can_send(
    head_template_engine, monkeypatch, kind
):
    from decimal import Decimal as D

    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.exit_execution import EntryFill, TpFillEvidence

    e = head_template_engine
    t, op = await accepted_operation(
        e,
        kind,
        **(
            {"price": D(65000), "quantity": D(".0002")}
            if kind == "manual_tp_set"
            else {}
        ),
    )
    factory = lambda: PostgresKernelUnitOfWork(e)
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        refs = await u.exchange_commands.list_order_references(t.identity.ticket_id)
        tp = next(r for r in refs if r.command_kind is K.TAKE_PROFIT)
        filled = a.tp1_target_qty / 2
        f = TicketLifecycleFacts(
            position_quantity=a.position_qty - filled,
            tp1_filled_quantity=filled,
            tp1_average_fill_price=D(64000),
            allocated_entry_fee_quote=D(".01"),
            exit_taker_fee_rate=D(".0005"),
            price_tick=D(".1"),
            market_facts=None,
            active_stop_quantity=a.position_qty - filled,
            current_market_price=D(64000),
            observed_at_ms=7000,
            tp_fill_evidence=TpFillEvidence(
                command_id=tp.command_id,
                exchange_order_id=tp.submitted_exchange_order_id,
                fills=(
                    EntryFill(
                        trade_id="natural-partial", quantity=filled, price=D(64000)
                    ),
                ),
                observed_at_ms=7000,
            ),
        )
        await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                facts=f,
                now_ms=7000,
                owner_adjustment_pending=True,
            ),
        )
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        assert a.position_qty == t.quantity - filled and a.tp1_filled_qty == filled
        assert row["state"] == "handed_to_lifecycle" and row["completed_at_ms"] == 7000
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )
        assert not [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.OWNER_REDUCE
        ]


@pytest.mark.asyncio
async def test_pending_unknown_owner_write_keeps_receipt_but_natural_fill_is_durably_recorded(
    head_template_engine,
):
    from decimal import Decimal as D

    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.commands import (
        ExchangeCommand,
        OrderCommandPayload,
        build_command_id,
        build_venue_client_order_id,
    )
    from src.trading_kernel.domain.exit_execution import EntryFill, TpFillEvidence

    e = head_template_engine
    t, op = await accepted_operation(e, "position_reduce")
    factory = lambda: PostgresKernelUnitOfWork(e)
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        cid = build_command_id(
            ticket_id=t.identity.ticket_id, kind=K.OWNER_REDUCE, generation=1
        )
        await u.exchange_commands.add(
            ExchangeCommand(
                command_id=cid,
                ticket_identity=a.identity,
                management_revision=a.management_revision,
                kind=K.OWNER_REDUCE,
                generation=1,
                idempotency_key=cid,
                venue_client_order_id=build_venue_client_order_id(cid),
                payload=OrderCommandPayload(
                    side="sell",
                    quantity=a.position_qty / 2,
                    order_type="market",
                    reduce_only=True,
                    owner_operation_id=op["operation_id"],
                ),
                status=S.OUTCOME_UNKNOWN,
                created_at_ms=6500,
                deadline_at_ms=10000,
            )
        )
        refs = await u.exchange_commands.list_order_references(t.identity.ticket_id)
        tp = next(r for r in refs if r.command_kind is K.TAKE_PROFIT)
        qty = a.tp1_target_qty
        f = TicketLifecycleFacts(
            position_quantity=a.position_qty - qty,
            tp1_filled_quantity=qty,
            tp1_average_fill_price=D(64000),
            allocated_entry_fee_quote=D(".01"),
            exit_taker_fee_rate=D(".0005"),
            price_tick=D(".1"),
            market_facts=None,
            active_stop_quantity=a.position_qty - qty,
            current_market_price=D(64000),
            observed_at_ms=7000,
            tp_fill_evidence=TpFillEvidence(
                command_id=tp.command_id,
                exchange_order_id=tp.submitted_exchange_order_id,
                fills=(
                    EntryFill(
                        trade_id="natural-complete", quantity=qty, price=D(64000)
                    ),
                ),
                observed_at_ms=7000,
            ),
        )
        await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                facts=f,
                now_ms=7000,
                owner_adjustment_pending=True,
            ),
        )
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        assert a.position_qty == t.quantity - qty and a.tp1_filled_qty == qty
        assert (
            row["state"] == "natural_tp_reconciling" and row["completed_at_ms"] is None
        )
        assert (await u.exchange_commands.get(cid)).status is S.OUTCOME_UNKNOWN
        events = await u.events.list_for_ticket(t.identity.ticket_id)
        assert (
            len([e for e in events if type(e).__name__ == "NaturalTakeProfitRecorded"])
            == 1
        )


@pytest.mark.asyncio
async def test_manual_tp_is_not_prepared_after_protection_conversion_crosses_target(
    head_template_engine,
):
    from decimal import Decimal as D

    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )
    factory = lambda: PostgresKernelUnitOfWork(e)
    source = DelayedSource()
    venue = OwnerOperationVenue()

    async def tick(at):
        source.at = at
        async with factory() as u:
            row = await u.owner_position_operations.get(op["operation_id"])
        return await advance_owner_adjustment(
            factory, source, row, now_ms=at, timeout_seconds=1
        )

    assert await tick(7000) == "protection_pending"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7100)
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7200)
    assert await tick(8000) == "tp_cancelling"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=8100)
    original = source.read_owner_position

    async def crossed(**kwargs):
        o = await original(**kwargs)
        return o.model_copy(
            update={"facts": o.facts.model_copy(update={"current_price": D(64000)})}
        )

    source.read_owner_position = crossed
    assert await tick(9000) == "repreview_required"
    async with factory() as u:
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        assert not [
            c
            for c in commands
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]
        row = await u.owner_position_operations.get(op["operation_id"])
        assert row["first_blocker"] == "owner_tp_target_crossed_repreview_required"


@pytest.mark.asyncio
async def test_tp_fill_before_cancel_hands_full_close_back(
    head_template_engine,
):

    e = head_template_engine
    t, op = await accepted_operation(e, "position_close")
    factory = lambda: PostgresKernelUnitOfWork(e)
    source = DelayedSource()

    async def tick(at):
        source.at = at
        async with factory() as u:
            row = await u.owner_position_operations.get(op["operation_id"])
        return await advance_owner_adjustment(
            factory, source, row, now_ms=at, timeout_seconds=1
        )

    await tick(7000)
    original = source.read_owner_position

    async def late_fill(**kwargs):
        o = await original(**kwargs)
        a = kwargs["aggregate"]
        qty = a.tp1_target_qty / 2
        return o.model_copy(
            update={
                "facts": o.facts.model_copy(
                    update={
                        "position_quantity": a.position_qty - qty,
                        "tp_filled_quantity": qty,
                        "protected_quantity": a.position_qty - qty,
                    }
                )
            }
        )

    source.read_owner_position = late_fill
    assert await tick(15000) == "handed_to_lifecycle"
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.status.value == "position_protected"
        exits = [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.EXIT
        ]
        assert not exits
        cancel = next(c for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
                      if c.kind is K.CANCEL_ORDER)
        assert cancel.status is S.SUPERSEDED
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )


@pytest.mark.asyncio
async def test_completed_manual_tp_installation_keeps_real_runner_tracking(
    head_template_engine,
):
    from decimal import Decimal as D

    import sqlalchemy as sa

    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts
    from src.trading_kernel.domain.owner_position_operation import (
        preview_position_operation,
    )
    from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
    from src.trading_kernel.infrastructure.pg_owner_position_operations import (
        PostgresOwnerPositionOperations,
    )
    from tests.trading_kernel.support.owner_reduction import (
        accept_signed_operation,
        facts,
        setup_operation,
    )

    e = head_template_engine
    t, b, _p, key = await setup_operation(e)
    factory = lambda: PostgresKernelUnitOfWork(e)
    venue = OwnerOperationVenue()
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                now_ms=6000,
                facts=TicketLifecycleFacts(
                    position_quantity=a.position_qty - a.tp1_target_qty,
                    tp1_filled_quantity=a.tp1_target_qty,
                    tp1_average_fill_price=D(64000),
                    allocated_entry_fee_quote=D(".01"),
                    exit_taker_fee_rate=D(".0005"),
                    price_tick=D(".1"),
                    market_facts=None,
                    observed_at_ms=6000,
                ),
            ),
        )
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=6100)
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=6200)
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.status.value == "runner_protected"
        p = preview_position_operation(
            aggregate=a,
            facts=facts(
                a,
                current_price=D(64000),
                tp_order_id=None,
                tp_state="absent",
                observed_at_ms=6500,
                valid_until_ms=9500,
            ),
            kind="manual_tp_set",
            price=D(66000),
            quantity=a.position_qty / 2,
            quantity_step=D(".00001"),
            price_tick=D(".1"),
            minimum_quantity=D(".00001"),
            minimum_notional=D(1),
            now_ms=6500,
        )
    async with e.begin() as c:
        await c.execute(
            sa.update(runtime_capabilities_current)
            .where(runtime_capabilities_current.c.capability_key == "exchange_commands")
            .values(
                certification={
                    "product_id": "brc-app-manual-v1",
                    "owner_cooperation": "owner-cooperation-v1",
                }
            )
        )
        r = PostgresOwnerPositionOperations(c)
        op = await r.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=b["device_id"],
            device_epoch=1,
            idempotency_key="runner-manual-tp",
            now_ms=6500,
        )
        op, _ = await accept_signed_operation(c, b, key, op, now_ms=6501)

    class Source(DelayedSource):
        async def read_owner_position(self, **kwargs):
            o = await super().read_owner_position(**kwargs)
            return o.model_copy(
                update={"facts": o.facts.model_copy(update={"current_price": D(64000)})}
            )

    source = Source()
    for at in range(7000, 12000, 1000):
        source.at = at
        async with factory() as u:
            row = await u.owner_position_operations.get(op["operation_id"])
        state = await advance_owner_adjustment(
            factory, source, row, now_ms=at, timeout_seconds=1
        )
        async with factory() as u:
            pending = [
                c
                for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
                if c.status is S.PREPARED
            ]
        for _ in pending:
            await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=at + 100)
        if state == "completed":
            break
    async with factory() as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert a.manual_profit_plan is not None and a.status.value == "runner_protected"
        result = await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                now_ms=13000,
                facts=TicketLifecycleFacts(
                    position_quantity=a.position_qty,
                    tp1_filled_quantity=0,
                    tp1_average_fill_price=None,
                    allocated_entry_fee_quote=D(".01"),
                    exit_taker_fee_rate=D(".0005"),
                    price_tick=D(".1"),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=12999,
                        is_final_closed_candle=True,
                        latest_close=D(64000),
                        structure_reference=D(62000),
                        atr=D(100),
                        holding_bars=1,
                    ),
                    observed_at_ms=13000,
                ),
            ),
        )
        assert result.status.value == "runner_move_requested"
        assert (await u.aggregates.get(t.identity.ticket_id)).pending_stop_price > D(
            61000
        )
