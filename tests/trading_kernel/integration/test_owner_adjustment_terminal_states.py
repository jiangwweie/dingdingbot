"""Old price intent and proven unstarted commands cannot retain a live operation."""

from decimal import Decimal as D

import pytest

from src.trading_kernel.application.advance_owner_adjustment import (
    advance_owner_adjustment,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind as K,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandStatus as S,
)
from src.trading_kernel.domain.owner_position_operation import (
    preview_position_operation,
)
from src.trading_kernel.infrastructure.pg_owner_position_operations import (
    PostgresOwnerPositionOperations,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
from tests.trading_kernel.support.owner_delay_scenarios import (
    DelayedSource,
    accepted_operation,
)
from tests.trading_kernel.support.owner_operation_source import OwnerOperationVenue


async def advance(engine, source, op_id, now):
    source.at = now
    factory = lambda: PostgresKernelUnitOfWork(engine)
    async with factory() as u:
        row = await u.owner_position_operations.get(op_id)
    return await advance_owner_adjustment(
        factory, source, row, now_ms=now, timeout_seconds=1
    )


async def reach_tp_preparation(engine, ticket, op_id, source):
    venue = OwnerOperationVenue()
    assert await advance(engine, source, op_id, 7000) == "protection_pending"
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=7100)
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=7200)
    assert await advance(engine, source, op_id, 8000) == "tp_cancelling"
    await dispatch_for_ticket(engine, venue, ticket.identity.ticket_id, now_ms=8100)


@pytest.mark.asyncio
async def test_crossed_tp_becomes_terminal_and_new_intent_requires_a_new_confirmation(
    head_template_engine,
):
    e = head_template_engine
    t, op, device, key = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002"), return_owner=True
    )

    class Source(DelayedSource):
        price = D(60000)

        async def read_owner_position(self, **kwargs):
            o = await super().read_owner_position(**kwargs)
            return o.model_copy(
                update={
                    "facts": o.facts.model_copy(update={"current_price": self.price})
                }
            )

    source = Source()
    await reach_tp_preparation(e, t, op["operation_id"], source)
    source.price = D(64000)
    assert await advance(e, source, op["operation_id"], 9000) == "repreview_required"
    source.price = D(62000)
    assert await advance(e, source, op["operation_id"], 50000) == "repreview_required"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        old = await u.owner_position_operations.get(op["operation_id"])
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        assert old["completed_at_ms"] == 9000
        assert old["payload"]["actual_effects"]["retired_tp_order_id"] is not None
        assert (
            a.tp1_exchange_order_id is None
            and a.active_stop_exchange_order_id is not None
        )
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )
        assert not [
            c
            for c in commands
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]
        observations = await source.read_owner_position(
            aggregate=a,
            commands=tuple(commands),
            operation_id=None,
            accepted_order_ids={
                r.command_id: r.submitted_exchange_order_id
                for r in await u.exchange_commands.list_order_references(
                    t.identity.ticket_id
                )
            },
        )
        new = preview_position_operation(
            aggregate=a,
            facts=observations.facts,
            kind="manual_tp_set",
            price=D(65000),
            quantity=D(".0002"),
            quantity_step=D(".0001"),
            price_tick=D(".1"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            now_ms=50000,
        )
    async with e.begin() as c:
        new_op = await PostgresOwnerPositionOperations(c).create_preview(
            preview=new,
            owner_identity=op["owner_identity"],
            device_id=op["device_id"],
            device_epoch=op["device_epoch"],
            idempotency_key="new-price-intent",
            now_ms=50000,
        )
        assert (
            new_op["operation_id"] != op["operation_id"]
            and new_op["authorization_id"] is None
        )
        from tests.trading_kernel.support.owner_reduction import accept_signed_operation

        accepted, _ = await accept_signed_operation(
            c,
            device,
            key,
            new_op,
            now_ms=50001,
            idempotency_key="new-price-confirmation",
        )
    assert await advance(e, source, accepted["operation_id"], 51000) == "tp_pending"
    async with PostgresKernelUnitOfWork(e) as u:
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        new_orders = [
            c
            for c in commands
            if c.kind is K.TAKE_PROFIT and c.payload.owner_operation_id is not None
        ]
        assert (
            len(new_orders) == 1
            and new_orders[0].payload.owner_operation_id == accepted["operation_id"]
        )

    await dispatch_for_ticket(
        e, OwnerOperationVenue(), t.identity.ticket_id, now_ms=51100
    )
    assert await advance(e, source, accepted["operation_id"], 52000) == "completed"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.manual_profit_plan.price == D(65000)
            and a.manual_profit_plan.source_kind == "manual"
        )
        assert (await u.owner_position_operations.get(op["operation_id"]))[
            "completed_at_ms"
        ] == 9000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,params",
    [
        ("protection_tighten", {"price": D(59500)}),
        ("manual_tp_set", {"price": D(63000), "quantity": D(".0002")}),
    ],
)
async def test_expired_never_sent_adjustment_reaches_terminal_and_releases_lane(
    head_template_engine, kind, params
):
    e = head_template_engine
    t, op = await accepted_operation(e, kind, **params)
    source = DelayedSource()
    if kind == "manual_tp_set":
        await reach_tp_preparation(e, t, op["operation_id"], source)
        assert await advance(e, source, op["operation_id"], 9000) == "tp_pending"
        at = 40000
    else:
        assert (
            await advance(e, source, op["operation_id"], 7000) == "protection_pending"
        )
        at = 38000
    assert (
        await advance(e, source, op["operation_id"], at) == "unstarted_commands_expired"
    )
    assert await advance(e, source, op["operation_id"], at + 1000) == "failed"
    assert await advance(e, source, op["operation_id"], at + 2000) == "failed"
    async with PostgresKernelUnitOfWork(e) as u:
        row = await u.owner_position_operations.get(op["operation_id"])
        a = await u.aggregates.get(t.identity.ticket_id)
        assert row["completed_at_ms"] == at + 1000
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )
        own = [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if getattr(c.payload, "owner_operation_id", None) == op["operation_id"]
        ]
        target = next(
            c
            for c in own
            if c.kind
            is (K.REPLACE_PROTECTION if kind == "protection_tighten" else K.TAKE_PROFIT)
        )
        assert target.status is S.SUPERSEDED
        assert a.active_stop_exchange_order_id is not None
        if kind == "protection_tighten":
            assert (
                a.active_stop_price == D(59000) and a.tp1_exchange_order_id is not None
            )
            assert row["payload"]["actual_effects"]["retired_tp_order_id"] is None
        else:
            assert a.tp1_exchange_order_id is None
            assert row["payload"]["actual_effects"]["retired_tp_order_id"] is not None


@pytest.mark.asyncio
async def test_pending_unknown_cancellation_does_not_erase_irreversible_repreview_intent(
    head_template_engine,
):
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.application.finish_owner_adjustment import (
        finish_owner_adjustment,
    )
    from src.trading_kernel.application.ports import VenueCommandRequest
    from src.trading_kernel.domain.commands import ExchangeCommandResult

    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )
    source = DelayedSource()
    venue = OwnerOperationVenue()
    assert await advance(e, source, op["operation_id"], 7000) == "protection_pending"
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7100)
    await dispatch_for_ticket(e, venue, t.identity.ticket_id, now_ms=7200)
    assert await advance(e, source, op["operation_id"], 8000) == "tp_cancelling"

    class UnknownVenue:
        async def execute(self, request: VenueCommandRequest):
            return ExchangeCommandResult(
                status=S.OUTCOME_UNKNOWN,
                reason="fixture_lost_result",
                observed_at_ms=8101,
            )

    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(e),
        UnknownVenue(),
        DispatchCommandRequest(
            worker_id="outage",
            ticket_id=t.identity.ticket_id,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=8100,
            lease_until_ms=9100,
            timeout_seconds=1,
        ),
        clock_ms=lambda: 8100,
    )
    source.at = 9000
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        commands = tuple(
            await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        )
        o = await source.read_owner_position(
            aggregate=a,
            commands=commands,
            operation_id=op["operation_id"],
            accepted_order_ids={
                r.command_id: r.submitted_exchange_order_id
                for r in await u.exchange_commands.list_order_references(
                    t.identity.ticket_id
                )
            },
        )
        assert (
            await finish_owner_adjustment(
                u,
                aggregate=a,
                row=row,
                commands=commands,
                observation=o,
                state="repreview_required",
                reason="owner_tp_target_crossed_repreview_required",
                now_ms=9000,
            )
            == "review_required"
        )
    assert await advance(e, source, op["operation_id"], 50000) == "review_required"
    async with PostgresKernelUnitOfWork(e) as u:
        row = await u.owner_position_operations.get(op["operation_id"])
        assert (
            row["completed_at_ms"] is None
            and row["payload"]["end_requested"]["state"] == "repreview_required"
        )
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is not None
        )
        cmds = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        assert any(
            c.kind is K.CANCEL_ORDER and c.status is S.OUTCOME_UNKNOWN for c in cmds
        )
        assert not [
            c
            for c in cmds
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]

        pending = next(
            c
            for c in cmds
            if c.kind is K.CANCEL_ORDER and c.status is S.OUTCOME_UNKNOWN
        )
        old_tp = next(c for c in cmds if c.kind is K.TAKE_PROFIT)
    from src.trading_kernel.application.recover_unknown_command import (
        recover_unknown_command,
        RecoverUnknownCommandRequest,
    )
    from src.trading_kernel.domain.venue_truth import (
        VenueTruthSnapshot,
        VenueLookupStatus,
        VenueOrderTruth,
    )

    class ExactCancelTruth:
        async def lookup_command_truth(self, request):
            return VenueTruthSnapshot(
                lookup_status=VenueLookupStatus.VISIBLE,
                position_quantity=t.quantity,
                matching_fill_quantity=0,
                regular_open_client_order_ids=(),
                conditional_open_client_order_ids=(),
                observed_at_ms=51000,
                order=VenueOrderTruth(
                    exchange_order_id=pending.payload.exchange_order_id,
                    venue_client_order_id=old_tp.venue_client_order_id,
                    exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
                    position_side="long",
                    order_side="sell",
                    quantity=old_tp.payload.quantity,
                    reduce_only=True,
                    order_namespace="regular",
                    is_open=False,
                ),
            )

    await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(e),
        ExactCancelTruth(),
        RecoverUnknownCommandRequest(
            command_id=pending.command_id,
            now_ms=51000,
            visibility_deadline_ms=30000,
            timeout_seconds=1,
        ),
    )
    assert await advance(e, source, op["operation_id"], 52000) == "repreview_required"
    async with PostgresKernelUnitOfWork(e) as u:
        resolved = await u.owner_position_operations.get(op["operation_id"])
        assert (
            resolved["completed_at_ms"] == 52000
            and resolved["payload"]["end_requested"]["requested_at_ms"] == 9000
        )
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )
        assert not [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [S.CLAIMED, S.OUTCOME_UNKNOWN])
async def test_sent_or_claimed_protection_keeps_adjustment_occupation(
    head_template_engine, state
):
    e = head_template_engine
    t, op = await accepted_operation(e, "protection_tighten", price=D(59500))
    source = DelayedSource()
    assert await advance(e, source, op["operation_id"], 7000) == "protection_pending"
    async with PostgresKernelUnitOfWork(e) as u:
        command = await u.exchange_commands.claim_one_prepared(
            worker_id="claimed-operation",
            now_ms=7100,
            lease_until_ms=70000,
            ticket_id=t.identity.ticket_id,
            command_kinds=(K.REPLACE_PROTECTION,),
        )
        if state is S.OUTCOME_UNKNOWN:
            from src.trading_kernel.domain.commands import ExchangeCommandResult

            await u.exchange_commands.record_result(
                command_id=command.command_id,
                worker_id="claimed-operation",
                result=ExchangeCommandResult(
                    status=S.OUTCOME_UNKNOWN,
                    reason="fixture_lost_result",
                    observed_at_ms=7101,
                ),
            )
    assert await advance(e, source, op["operation_id"], 38000) == "protection_pending"
    async with PostgresKernelUnitOfWork(e) as u:
        row = await u.owner_position_operations.get(op["operation_id"])
        assert row["completed_at_ms"] is None
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is not None
        )
        assert (await u.exchange_commands.get(command.command_id)).status is state


@pytest.mark.asyncio
async def test_prepared_but_unsent_tp_is_cancelled_permanently_when_price_crosses(
    head_template_engine,
):
    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )

    class Source(DelayedSource):
        price = D(60000)

        async def read_owner_position(self, **kwargs):
            o = await super().read_owner_position(**kwargs)
            return o.model_copy(
                update={
                    "facts": o.facts.model_copy(update={"current_price": self.price})
                }
            )

    source = Source()
    await reach_tp_preparation(e, t, op["operation_id"], source)
    assert await advance(e, source, op["operation_id"], 9000) == "tp_pending"
    source.price = D(64000)
    assert await advance(e, source, op["operation_id"], 10000) == "repreview_required"
    source.price = D(62000)
    assert await advance(e, source, op["operation_id"], 11000) == "repreview_required"
    async with PostgresKernelUnitOfWork(e) as u:
        own = [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]
        assert len(own) == 1 and own[0].status is S.SUPERSEDED
        assert (await u.owner_position_operations.get(op["operation_id"]))[
            "completed_at_ms"
        ] == 10000


@pytest.mark.asyncio
async def test_retired_old_tp_keeps_original_failure_exit_without_restoring_quantity_plan(
    head_template_engine,
):
    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts

    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )

    class Source(DelayedSource):
        async def read_owner_position(self, **kwargs):
            o = await super().read_owner_position(**kwargs)
            price = D(64000) if self.at >= 9000 else D(60000)
            return o.model_copy(
                update={"facts": o.facts.model_copy(update={"current_price": price})}
            )

    source = Source()
    await reach_tp_preparation(e, t, op["operation_id"], source)
    assert await advance(e, source, op["operation_id"], 9000) == "repreview_required"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.manual_profit_plan.cancelled
            and a.manual_profit_plan.source_kind == "retired_automatic"
        )
        assert a.tp1_exchange_order_id is None and a.tp1_filled_qty == 0
        at = a.ticket.exposure_session_end_ms + 1000
        result = await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                now_ms=at,
                facts=TicketLifecycleFacts(
                    position_quantity=a.position_qty,
                    tp1_filled_quantity=0,
                    tp1_average_fill_price=None,
                    allocated_entry_fee_quote=D(".01"),
                    exit_taker_fee_rate=D(".0005"),
                    price_tick=D(".1"),
                    active_stop_quantity=a.position_qty,
                    current_market_price=D(64000),
                    market_facts=LifecycleMarketFacts(
                        watermark_ms=at - 1,
                        is_final_closed_candle=True,
                        latest_close=D(64000),
                        structure_reference=D(62000),
                        atr=D(100),
                        holding_bars=1,
                    ),
                    observed_at_ms=at,
                ),
            ),
        )
        assert result.status.value == "exit_requested"
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        assert (
            len(
                [
                    c
                    for c in commands
                    if c.kind is K.EXIT and c.payload.owner_operation_id is None
                ]
            )
            == 1
        )
        assert not [
            c for c in commands if c.kind is K.TAKE_PROFIT and c.status is S.PREPARED
        ]


@pytest.mark.asyncio
async def test_expired_initial_tp_protection_conversion_ends_without_cancelling_old_tp(
    head_template_engine,
):
    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )
    source = DelayedSource()
    assert await advance(e, source, op["operation_id"], 7000) == "protection_pending"
    assert (
        await advance(e, source, op["operation_id"], 38000)
        == "unstarted_commands_expired"
    )
    assert await advance(e, source, op["operation_id"], 39000) == "failed"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        row = await u.owner_position_operations.get(op["operation_id"])
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        assert a.tp1_exchange_order_id is not None and a.active_stop_price == D(59000)
        assert row["payload"]["actual_effects"]["old_tp_still_active"]
        assert not [c for c in commands if c.kind is K.CANCEL_ORDER]
        assert (
            await u.owner_position_operations.active_for_ticket(t.identity.ticket_id)
            is None
        )


@pytest.mark.asyncio
async def test_failed_tighten_releases_serialization_for_normal_runner_replacement(
    head_template_engine,
):
    from src.trading_kernel.domain.commands import ExchangeCommand, OrderCommandPayload

    e = head_template_engine
    t, op = await accepted_operation(e, "protection_tighten", price=D(59500))
    source = DelayedSource()
    await advance(e, source, op["operation_id"], 7000)
    await advance(e, source, op["operation_id"], 38000)
    assert await advance(e, source, op["operation_id"], 39000) == "failed"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        normal = ExchangeCommand(
            command_id="normal-runner",
            ticket_identity=a.identity,
            management_revision=a.management_revision,
            kind=K.REPLACE_PROTECTION,
            generation=2,
            idempotency_key="normal-runner",
            venue_client_order_id="normal-runner-client",
            payload=OrderCommandPayload(
                side="sell",
                quantity=a.position_qty,
                order_type="stop_market",
                reduce_only=True,
                stop_price=D(60050),
                replaces_exchange_order_id=a.active_stop_exchange_order_id,
                source_watermark_ms=40000,
            ),
            status=S.PREPARED,
            created_at_ms=40000,
            deadline_at_ms=70000,
        )
        assert (
            await u.owner_position_operations.command_send_blocker(
                normal, a, now_ms=40100
            )
            is None
        )


@pytest.mark.asyncio
async def test_repreview_marker_alone_cannot_revive_old_intent_on_a_later_price(
    head_template_engine,
):
    e = head_template_engine
    t, op = await accepted_operation(
        e, "manual_tp_set", price=D(63000), quantity=D(".0002")
    )
    source = DelayedSource()
    await reach_tp_preparation(e, t, op["operation_id"], source)
    async with e.begin() as c:
        repo = PostgresOwnerPositionOperations(c)
        row = await repo.get(op["operation_id"])
        await repo.transition(
            operation_id=op["operation_id"],
            expected_version=row["version"],
            state="review_required",
            payload=row["payload"],
            reason="owner_tp_target_crossed_repreview_required",
            now_ms=9000,
        )
    assert await advance(e, source, op["operation_id"], 50000) == "repreview_required"
    async with PostgresKernelUnitOfWork(e) as u:
        row = await u.owner_position_operations.get(op["operation_id"])
        assert (
            row["completed_at_ms"] == 50000
            and row["payload"]["actual_effects"]["retired_tp_order_id"] is not None
        )
        assert not [
            c
            for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            if c.kind is K.TAKE_PROFIT
            and c.payload.owner_operation_id == op["operation_id"]
        ]
