"""Persist real-shaped Owner reduction facts without pretending TP filled."""

from decimal import Decimal as D

import pytest

from src.trading_kernel.application.record_owner_reduction import record_owner_reduction
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.exit_execution import EntryFill
from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.infrastructure.pg_owner_position_operations import (
    PostgresOwnerPositionOperations,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.owner_reduction import facts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition",
    [
        "waiting",
        "reached",
        "stale",
        "stop_mismatch",
        "failure",
        "adapter_v1",
        "adapter_v2",
        "runner",
        "missing_retirement",
    ],
)
async def test_exact_accepted_reduction_persists_context_and_is_idempotent(
    head_template_engine, condition
):
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec

    e = head_template_engine
    t = registered_sor_long_ticket()
    if condition == "runner":
        from tests.trading_kernel.support.lifecycle import reach_runner_protected

        await reach_runner_protected(e, t)
    else:
        await reach_position_protected(e, t)
    key = ec.generate_private_key(ec.SECP256R1())
    n = key.public_key().public_numbers()
    enc = lambda n: (
        base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()
    )
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        g = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=4000
        )
        device = await r.bind(
            token=g,
            public_key={"kty": "EC", "crv": "P-256", "x": enc(n.x), "y": enc(n.y)},
            now_ms=4001,
        )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        p = preview_owner_reduction(
            aggregate=a,
            facts=facts(
                a,
                observed_at_ms=5000,
                valid_until_ms=8000,
                **(
                    {
                        "tp_order_id": None,
                        "tp_state": "filled",
                        "current_price": D(63000),
                    }
                    if condition == "runner"
                    else {}
                ),
            ),
            requested_quantity=a.position_qty / 2,
            quantity_step=D(".0001"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            now_ms=5000,
        )
        repo = PostgresOwnerPositionOperations(u._require_connection())
        op = await repo.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=device["device_id"],
            device_epoch=1,
            idempotency_key="p1",
            now_ms=5000,
        )
        from tests.trading_kernel.support.owner_reduction import accept_signed_operation

        op, _ = await accept_signed_operation(
            u._require_connection(), device, key, op, now_ms=5001, idempotency_key="s1"
        )
        cid = build_command_id(
            ticket_id=t.identity.ticket_id,
            kind=ExchangeCommandKind.OWNER_REDUCE,
            generation=1,
        )
        client = build_venue_client_order_id(cid)
        command = ExchangeCommand(
            command_id=cid,
            ticket_identity=t.identity,
            kind=ExchangeCommandKind.OWNER_REDUCE,
            generation=1,
            idempotency_key=cid,
            venue_client_order_id=client,
            payload=OrderCommandPayload(
                side="sell",
                quantity=p.reduction_quantity,
                order_type="market",
                reduce_only=True,
                owner_operation_id=op["operation_id"],
            ),
            status=ExchangeCommandStatus.PREPARED,
            created_at_ms=5001,
            deadline_at_ms=35001,
        )
        await u.exchange_commands.add(command)
    async with PostgresKernelUnitOfWork(e) as u:
        claimed = await u.exchange_commands.claim_one_prepared(
            worker_id="test",
            now_ms=5002,
            lease_until_ms=10000,
            ticket_id=t.identity.ticket_id,
            command_kinds=(ExchangeCommandKind.OWNER_REDUCE,),
        )
        assert claimed.command_id == cid
        await u.exchange_commands.record_result(
            command_id=cid,
            worker_id="test",
            result=ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=5003,
                exchange_order_id="owner-reduce-order",
            ),
        )
    async with PostgresKernelUnitOfWork(e) as u:
        from src.trading_kernel.domain.trade_management import OrderEvidence
        from tests.trading_kernel.support.manual_management import app_order

        refs = await u.exchange_commands.list_order_references(t.identity.ticket_id)
        original_stop_client = next(
            r.venue_client_order_id
            for r in refs
            if r.submitted_exchange_order_id == p.protection_order_id
        )
        terms = app_order(
            t,
            order_namespace="conditional",
            exchange_order_id=p.protection_order_id,
            client_order_id=original_stop_client,
            order_type="STOP_MARKET",
            quantity=p.source_quantity,
            price=None,
            trigger_price=p.stop_price,
        )
        await u.management.save_evidence(
            t.identity.ticket_id,
            OrderEvidence(
                evidence_id="retired-original-stop",
                terms=terms,
                action="cancel",
                exchange_event_at_ms=6000,
                received_at_ms=6000,
                created_at_ms=3000,
                executed_quantity=D(0),
                coverage_complete=True,
                known_command_outcome_pending=False,
                source_kind="rest",
            ),
        )
    proof = OwnerReductionProof(
        source_stage="runner" if condition == "runner" else "pre_tp",
        source_tp_filled_quantity=p.source_tp_filled_quantity,
        retired_protections=(
            {
                "evidence_id": "retired-original-stop",
                "exchange_order_id": p.protection_order_id,
                "client_order_id": original_stop_client,
                "status": "CANCELED",
                "executed_quantity": "0",
                "observed_at_ms": 6000,
            },
        ),
        authorization_id=op["authorization_id"],
        operation_id=op["operation_id"],
        ticket_id=t.identity.ticket_id,
        domain=t.identity.netting_domain,
        command_id=cid,
        exchange_order_id="owner-reduce-order",
        venue_client_order_id=client,
        order_status="FILLED",
        requested_quantity=p.reduction_quantity,
        executed_quantity=p.reduction_quantity,
        source_quantity=p.source_quantity,
        remaining_quantity=p.remaining_quantity,
        fills=(
            EntryFill(
                trade_id="reduce-fill", quantity=p.reduction_quantity, price=D(60000)
            ),
        ),
        original_tp_order_id=p.cancel_tp_order_id,
        original_tp_cancelled=condition != "runner",
        original_tp_filled_quantity=p.source_tp_filled_quantity,
        protection_order_id="remaining-stop",
        protection_price=p.stop_price,
        protected_quantity=p.remaining_quantity,
        observed_at_ms=6000,
        valid_until_ms=36000,
    )
    if condition == "missing_retirement":
        from src.trading_kernel.domain.owner_reduction_proof import (
            RetiredProtectionProof,
        )
        from src.trading_kernel.infrastructure.pg_unit_of_work import (
            UnsupportedKernelEffect,
        )

        bad = proof.model_copy(
            update={
                "retired_protections": (
                    RetiredProtectionProof(
                        **{
                            **proof.retired_protections[0].model_dump(),
                            "evidence_id": "missing",
                        }
                    ),
                )
            }
        )
        async with PostgresKernelUnitOfWork(e) as u:
            with pytest.raises(
                UnsupportedKernelEffect, match="durable terminal evidence"
            ):
                await record_owner_reduction(u, proof=bad, now_ms=6000)
        return
    async with PostgresKernelUnitOfWork(e) as u:
        assert await record_owner_reduction(u, proof=proof, now_ms=6000) == "recorded"
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        assert (
            a.position_qty == p.remaining_quantity
            and a.tp1_filled_qty == p.source_tp_filled_quantity
        )
        assert a.owner_reduction_context.original_tp_price == p.tp_trigger_price
        assert a.initial_stop_exchange_order_id is None
        if condition == "runner":
            assert (
                a.status.value == "runner_protected"
                and a.break_even_floor_price is not None
            )
        assert (
            await record_owner_reduction(u, proof=proof, now_ms=6001)
            == "already_recorded"
        )

    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.domain.events import (
        OwnerReductionPriceSatisfied,
        TakeProfitFilled,
    )
    from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts

    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        market = (
            LifecycleMarketFacts(
                watermark_ms=3599999,
                is_final_closed_candle=True,
                latest_close=D(59000),
                structure_reference=D(59000),
                atr=D(100),
                holding_bars=1,
            )
            if condition == "failure"
            else None
        )
        lifecycle_facts = TicketLifecycleFacts(
            position_quantity=p.remaining_quantity,
            tp1_filled_quantity=D(0),
            tp1_average_fill_price=None,
            allocated_entry_fee_quote=D(".01"),
            exit_taker_fee_rate=D(".001"),
            price_tick=D(".1"),
            market_facts=market,
            observed_at_ms=3600000 if condition == "failure" else 7000,
            current_market_price=D(62500),
            active_stop_quantity=D(0)
            if condition == "stop_mismatch"
            else p.remaining_quantity,
            contract_market_price=p.tp_trigger_price
            if condition != "waiting"
            else D(60000),
            contract_price_observed_at_ms=6001,
            contract_price_valid_until_ms=6999 if condition == "stale" else 36001,
        )
        if condition in {"adapter_v1", "adapter_v2"}:
            from src.trading_kernel.application.runtime_facts import (
                LifecycleFactsRequest,
            )
            from src.trading_kernel.domain.order_attribution import (
                ConditionalOrderExpectation,
                OrderNamespace,
                OrderRole,
                TicketOrderReference,
            )
            from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
            from tests.trading_kernel.support.venue_adapter import (
                OwnerContinuationExchange,
            )

            references = await u.exchange_commands.list_order_references(
                t.identity.ticket_id
            )
            entry = next(r for r in references if r.role is OrderRole.ENTRY)
            source = OwnerContinuationExchange(
                quantity=p.remaining_quantity,
                stop_price=p.stop_price,
                stop_id="remaining-stop",
                entry_id=entry.submitted_exchange_order_id,
                now_ms=7000,
            )
            adapter = CcxtVenueAdapter(
                exchanges={
                    (
                        t.identity.netting_domain.venue_id,
                        t.identity.netting_domain.account_id,
                    ): source
                },
                default_settlement_asset="USDT",
                default_taker_fee_rate=D(".001"),
                clock_ms=lambda: 7000,
            )
            lifecycle_facts = await adapter.read_lifecycle_facts(
                LifecycleFactsRequest(
                    ticket_id=t.identity.ticket_id,
                    netting_domain=t.identity.netting_domain,
                    event_spec_id=t.identity.runtime.event_spec_id,
                    timeframe="1h",
                    entry_quantity=t.quantity,
                    expected_position_quantity=p.remaining_quantity,
                    entry_order_reference=entry,
                    tp1_exchange_order_id=None,
                    active_stop_reference=TicketOrderReference(
                        command_id="protection-command",
                        command_kind=ExchangeCommandKind.REPLACE_PROTECTION,
                        role=OrderRole.EXIT,
                        namespace=OrderNamespace.CONDITIONAL,
                        venue_client_order_id="stop-client",
                        submitted_exchange_order_id="remaining-stop",
                        command_created_at_ms=3000,
                        conditional_expectation=ConditionalOrderExpectation(
                            exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
                            position_side="long",
                            side="sell",
                            order_type="stop_market",
                            quantity=p.remaining_quantity,
                        ),
                    ),
                    expected_active_stop_price=p.stop_price,
                    entry_fill_window_started_at_ms=entry.command_created_at_ms,
                    price_tick=D(".1"),
                    structure_window_bars=4,
                    atr_period=14,
                    runner_market_required=False,
                    owner_reduction_price_required=True,
                    exact_tp_fills_required=condition == "adapter_v2",
                    observed_at_ms=7000,
                )
            )
            assert lifecycle_facts.active_stop_quantity == p.remaining_quantity
        result = await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                facts=lifecycle_facts,
                now_ms=3600000 if condition == "failure" else 7000,
            ),
        )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        events = await u.events.list_for_ticket(t.identity.ticket_id)
        assert (
            a.position_qty == p.remaining_quantity
            and a.tp1_filled_qty == p.source_tp_filled_quantity
        )
        if condition != "runner":
            assert not any(isinstance(event, TakeProfitFilled) for event in events)
        if condition in {"reached", "adapter_v1", "adapter_v2"}:
            assert result.status.value == "break_even_requested"
            assert (
                sum(isinstance(event, OwnerReductionPriceSatisfied) for event in events)
                == 1
            )
        elif condition == "failure":
            assert result.status.value == "exit_requested"
        else:
            assert result.status.value == "no_change"
            assert not any(
                isinstance(event, OwnerReductionPriceSatisfied) for event in events
            )
