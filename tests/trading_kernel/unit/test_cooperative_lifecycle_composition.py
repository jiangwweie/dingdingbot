from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.domain.aggregate import AggregateStatus as A
from src.trading_kernel.domain.exit_execution import EntryFill, TpFillEvidence
from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    LifecycleMarketFacts,
    evaluate_profile_runner_exit,
    registered_exit_profiles,
)
from src.trading_kernel.domain.manual_profit_plan import ManualProfitPlan
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.owner_reduction import aggregate


def fake_uow(a):
    box = {"a": a}
    events = []

    async def commit(*, event, reduction, **kw):
        box["a"] = reduction.aggregate
        events.append(event)

    profile = next(
        p
        for p in registered_exit_profiles()
        if p.exit_profile_id == a.ticket.exit_policy_id
    )
    u = SimpleNamespace(
        aggregates=SimpleNamespace(
            get_for_update=AsyncMock(side_effect=lambda _: box["a"]),
            expedite_reconciliation=AsyncMock(),
        ),
        exit_profiles=SimpleNamespace(
            get_profile=AsyncMock(return_value=SimpleNamespace(profile=profile))
        ),
        owner_position_operations=SimpleNamespace(
            active_for_ticket=AsyncMock(return_value=None)
        ),
        commit_reduction=commit,
    )
    return u, box, events, profile


def facts(a, filled=D(0), market=None):
    return TicketLifecycleFacts(
        position_quantity=a.position_qty - filled,
        tp1_filled_quantity=filled,
        tp1_average_fill_price=D(64000) if filled else None,
        allocated_entry_fee_quote=D(".01"),
        exit_taker_fee_rate=D(".0005"),
        price_tick=D(".1"),
        market_facts=market,
        current_market_price=D(64000),
        active_stop_quantity=a.position_qty - filled,
        observed_at_ms=7000,
        tp_fill_evidence=TpFillEvidence(
            command_id="tp-command",
            exchange_order_id=a.tp1_exchange_order_id,
            fills=(EntryFill(trade_id="fill-1", quantity=filled, price=D(64000)),),
            observed_at_ms=7000,
        )
        if filled
        else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_runner_with_manual_limit_keeps_its_original_runner_evaluation(partial):
    a = aggregate().model_copy(
        update={
            "status": A.RUNNER_PROTECTED,
            "active_stop_price": D(60050),
            "break_even_floor_price": D(60050),
            "runner_stop_watermark_ms": 4000,
            "active_stop_close_position": True,
            "manual_profit_plan": ManualProfitPlan(
                operation_id="plan",
                exchange_order_id="manual-tp",
                command_id="tp-command",
                price=D(65000),
                target_quantity=D(".0004"),
                prior_tp_filled_quantity=0,
                started_from_runner=True,
            ),
            "tp1_exchange_order_id": "manual-tp",
            "tp1_target_qty": D(".0004"),
            "tp1_filled_qty": D(0),
        }
    )
    market = LifecycleMarketFacts(
        watermark_ms=6999,
        is_final_closed_candle=True,
        latest_close=D(64000),
        structure_reference=D(62000),
        atr=D(100),
        holding_bars=1,
    )
    u, box, events, profile = fake_uow(a)
    expected = evaluate_profile_runner_exit(
        profile=profile,
        current_stop=a.active_stop_price,
        break_even_floor=a.break_even_floor_price,
        price_tick=D(".1"),
        last_runner_watermark_ms=4000,
        market_facts=market,
    )
    assert expected.kind is ExitDecisionKind.MOVE_STOP
    result = await maintain_ticket_lifecycle(
        u,
        LifecycleMaintenanceRequest(
            ticket_id=a.identity.ticket_id,
            facts=facts(a, D(".0001") if partial else D(0), market),
            now_ms=7000,
        ),
    )
    assert result.status.value == "runner_move_requested"
    assert box["a"].pending_stop_price == expected.proposed_stop
    assert any(type(e).__name__ == "RunnerStopRequested" for e in events)
    assert box["a"].tp1_exchange_order_id == "manual-tp"
    assert box["a"].position_qty == a.position_qty - (D(".0001") if partial else 0)


@pytest.mark.asyncio
async def test_natural_partial_tp_is_recorded_while_owner_operation_is_pending():
    a = aggregate()
    u, box, events, _ = fake_uow(a)
    await maintain_ticket_lifecycle(
        u,
        LifecycleMaintenanceRequest(
            ticket_id=a.identity.ticket_id,
            facts=facts(a, a.tp1_target_qty / 2),
            now_ms=7000,
            owner_adjustment_pending=True,
        ),
    )
    assert box["a"].tp1_filled_qty == a.tp1_target_qty / 2
    assert box["a"].position_qty == a.position_qty - a.tp1_target_qty / 2
    assert any(type(e).__name__ == "TakeProfitProgressed" for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("complete", [False, True])
async def test_exact_natural_tp_is_accounted_even_when_a_sent_owner_write_is_unknown(
    complete,
):
    a = aggregate()
    u, box, events, _ = fake_uow(a)
    row = {
        "operation_id": "op",
        "version": 3,
        "payload": {"preview": {"source_tp_filled_quantity": "0"}},
        "ticket_id": a.identity.ticket_id,
    }
    u.owner_position_operations.active_for_ticket = AsyncMock(return_value=row)
    u.owner_position_operations.transition = AsyncMock()
    from src.trading_kernel.domain.commands import (
        ExchangeCommandKind as K,
    )
    from src.trading_kernel.domain.commands import (
        ExchangeCommandStatus as S,
    )

    u.exchange_commands = SimpleNamespace(
        list_for_ticket=AsyncMock(
            return_value=[
                SimpleNamespace(
                    command_id="sent",
                    kind=K.OWNER_REDUCE,
                    status=S.OUTCOME_UNKNOWN,
                    payload=SimpleNamespace(owner_operation_id="op"),
                )
            ]
        )
    )
    qty = a.tp1_target_qty if complete else a.tp1_target_qty / 2
    await maintain_ticket_lifecycle(
        u,
        LifecycleMaintenanceRequest(
            ticket_id=a.identity.ticket_id,
            facts=facts(a, qty),
            now_ms=7000,
            owner_adjustment_pending=True,
        ),
    )
    assert (
        box["a"].tp1_filled_qty == qty and box["a"].position_qty == a.position_qty - qty
    )
    assert box["a"].tp1_exchange_order_id == a.tp1_exchange_order_id
    assert (
        u.owner_position_operations.transition.await_args.kwargs["state"]
        == "natural_tp_reconciling"
    )
    assert not any(type(e).__name__ == "TakeProfitFilled" for e in events)


@pytest.mark.asyncio
async def test_runner_manual_tp_preserves_original_absolute_exit():
    from src.trading_kernel.domain.exit_policy import TimeStopMode, TimeStopRule

    a = aggregate().model_copy(
        update={
            "status": A.RUNNER_PROTECTED,
            "active_stop_price": D(60050),
            "break_even_floor_price": D(60050),
            "runner_stop_watermark_ms": 4000,
            "manual_profit_plan": ManualProfitPlan(
                operation_id="plan",
                exchange_order_id="manual-tp",
                command_id="tp-command",
                price=D(65000),
                target_quantity=D(".0004"),
                prior_tp_filled_quantity=0,
                started_from_runner=True,
            ),
            "tp1_exchange_order_id": "manual-tp",
            "tp1_target_qty": D(".0004"),
        }
    )
    market = LifecycleMarketFacts(
        watermark_ms=6999,
        is_final_closed_candle=True,
        latest_close=D(64000),
        structure_reference=D(62000),
        atr=D(100),
        holding_bars=10,
    )
    u, box, events, profile = fake_uow(a)
    profile = profile.model_copy(
        update={
            "time_stop": TimeStopRule(mode=TimeStopMode.ABSOLUTE, max_holding_bars=5)
        }
    )
    u.exit_profiles.get_profile = AsyncMock(
        return_value=SimpleNamespace(profile=profile)
    )
    await maintain_ticket_lifecycle(
        u,
        LifecycleMaintenanceRequest(
            ticket_id=a.identity.ticket_id, facts=facts(a, market=market), now_ms=7000
        ),
    )
    assert box["a"].status is A.EXIT_PENDING
    assert events[-1].reason == "absolute_time_stop_hit"


@pytest.mark.asyncio
async def test_new_fill_invalidates_an_unstarted_owner_protection_request_without_deadlock():
    from src.trading_kernel.domain.events import OwnerProtectionRequested

    a = aggregate()
    ev = OwnerProtectionRequested(
        event_id="req",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=6000,
        operation_id="op",
        stop_price=a.active_stop_price,
        close_position=True,
        source_watermark_ms=6000,
    )
    a = reduce_event(a, ev).aggregate
    u, box, _events, _ = fake_uow(a)
    row = {
        "operation_id": "op",
        "version": 3,
        "ticket_id": a.identity.ticket_id,
        "payload": {"preview": {"source_tp_filled_quantity": "0"}},
    }
    from src.trading_kernel.domain.commands import (
        ExchangeCommandKind as K,
    )
    from src.trading_kernel.domain.commands import (
        ExchangeCommandStatus as S,
    )

    u.exchange_commands = SimpleNamespace(mark_prepared_superseded=AsyncMock())
    u.owner_position_operations.transition = AsyncMock()
    from src.trading_kernel.application.handoff_owner_operation import (
        handoff_natural_tp,
    )

    qty = a.tp1_target_qty / 2
    changed = await handoff_natural_tp(
        u,
        aggregate=a,
        row=row,
        commands=(
            SimpleNamespace(
                command_id="not-sent-stop",
                kind=K.REPLACE_PROTECTION,
                status=S.PREPARED,
                payload=SimpleNamespace(owner_operation_id="op"),
            ),
        ),
        filled_quantity=qty,
        position_quantity=a.position_qty - qty,
        now_ms=7000,
    )
    assert changed
    assert box["a"].status is A.POSITION_PROTECTED
    assert box["a"].active_stop_price == a.active_stop_price


@pytest.mark.asyncio
async def test_unknown_order_blocks_owner_side_effects_but_exact_fill_does_not_repeat():
    from src.trading_kernel.domain.commands import (
        ExchangeCommandKind as K,
    )
    from src.trading_kernel.domain.commands import (
        ExchangeCommandStatus as S,
    )

    a = aggregate()
    u, box, events, _ = fake_uow(a)
    row = {
        "operation_id": "op",
        "version": 3,
        "payload": {"preview": {"source_tp_filled_quantity": "0"}},
        "ticket_id": a.identity.ticket_id,
    }
    u.owner_position_operations.active_for_ticket = AsyncMock(return_value=row)
    u.owner_position_operations.transition = AsyncMock()
    u.exchange_commands = SimpleNamespace(
        list_for_ticket=AsyncMock(
            return_value=[
                SimpleNamespace(
                    command_id="sent",
                    kind=K.OWNER_REDUCE,
                    status=S.OUTCOME_UNKNOWN,
                    payload=SimpleNamespace(owner_operation_id="op"),
                )
            ]
        )
    )
    qty = a.tp1_target_qty / 2
    request = LifecycleMaintenanceRequest(
        ticket_id=a.identity.ticket_id,
        facts=facts(a, qty),
        now_ms=7000,
        owner_adjustment_pending=True,
    )
    await maintain_ticket_lifecycle(u, request)
    await maintain_ticket_lifecycle(u, request.model_copy(update={"now_ms": 7001}))
    assert (
        len([e for e in events if type(e).__name__ == "NaturalTakeProfitRecorded"]) == 1
    )
    assert box["a"].position_qty == a.position_qty - qty
