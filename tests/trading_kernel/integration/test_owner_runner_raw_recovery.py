"""Real PG Runner state traverses raw readers, signed mobile intent and dispatch."""

from decimal import Decimal as D

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.advance_owner_position_operation import (
    advance_owner_position_operation,
)
from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.domain.owner_position_intent import INTENT_PATH
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    runtime_capabilities_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    reach_runner_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.mobile_owner import mobile_client
from tests.trading_kernel.support.owner_device import sign
from tests.trading_kernel.support.owner_raw_protocol import RawOwnerProtocol
from tests.trading_kernel.support.owner_roles import apply_owner_control_grants


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "fault"),
    [
        ("runner", None),
        ("runner", "missing_stop"),
        ("pre_tp", None),
        ("tp_pending_close", None),
        ("tp_pending_reduce", None),
    ],
)
async def test_signed_mobile_intent_through_raw_protocol_and_durable_ledger(
    head_template_engine, stage, fault
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    if stage == "runner":
        await reach_runner_protected(e, t)
    else:
        await reach_position_protected(
            e, t, install_tp=not stage.startswith("tp_pending")
        )
    factory = lambda: PostgresKernelUnitOfWork(e)
    async with factory() as u:
        before = await u.aggregates.get(t.identity.ticket_id)
        if stage == "runner":
            assert before.status.value == "runner_protected"
            assert before.tp1_exchange_order_id is None and before.tp1_filled_qty > 0
        elif stage == "pre_tp":
            assert before.status.value == "position_protected"
            assert (
                before.tp1_exchange_order_id is not None and before.tp1_filled_qty == 0
            )
        else:
            assert before.status.value == "tp1_pending"
            assert before.tp1_exchange_order_id is None
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
        if stage.startswith("tp_pending"):
            await c.execute(
                sa.update(exchange_commands)
                .where(
                    exchange_commands.c.ticket_id == t.identity.ticket_id,
                    exchange_commands.c.command_kind == K.TAKE_PROFIT.value,
                )
                .values(deadline_at_ms=5000)
            )
    from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket

    async with factory() as u:
        await u.signals.upsert_instrument_rules(
            venue_id=t.identity.netting_domain.venue_id,
            exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
            quantity_step=D(".0001"),
            price_tick=D(".1"),
            min_quantity=D(".0001"),
            min_notional=D(1),
            exchange_max_leverage=10,
            maintenance_margin_brackets=(
                MaintenanceMarginBracket(
                    bracket_id="test:1",
                    notional_floor=D(0),
                    notional_cap=None,
                    maintenance_margin_rate=D(".004"),
                    maintenance_amount=D(0),
                ),
            ),
            maintenance_margin_brackets_digest="sha256:" + "5" * 64,
            notional_coefficient=D(1),
            notional_coefficient_certified=True,
            observed_at_ms=5000,
            valid_until_ms=100000,
        )
    source = RawOwnerProtocol(e, before.position_qty)
    source.fault = fault
    await apply_owner_control_grants(e)
    control = create_async_engine(
        e.url, connect_args={"server_settings": {"role": "brc_owner_control"}}
    )
    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        stack.push_async_callback(control.dispose)
        client, app, key, device = await stack.enter_async_context(
            mobile_client(e, at_ms=6000, control_engine=control)
        )
        app.state.owner_console_settings.account_id = (
            t.identity.netting_domain.account_id
        )
        from types import SimpleNamespace

        app.state.owner_console_settings.auth = SimpleNamespace(
            session_signing_key="plan-test-key"
        )
        headers = {"origin": "https://owner.test"}
        position = (await client.get("/api/owner/v1/mobile/positions")).json()["items"][
            0
        ]
        payload = {
            "kind": "position_reduce",
            "ticket_id": t.identity.ticket_id,
            "quantity": str(before.position_qty / 2),
            "basis_quantity": position["position_qty"],
            "basis_version": position["version"],
            "basis_token": position["reduction_basis_token"],
        }
        if stage == "tp_pending_close":
            payload = {"kind": "position_close", "ticket_id": t.identity.ticket_id}
        nonce = (
            await client.post("/api/owner/v1/mobile/nonces", json={}, headers=headers)
        ).json()
        proof = DeviceWriteProof(
            device_id=device["device_id"],
            device_epoch=1,
            method="POST",
            path=INTENT_PATH,
            body_digest=canonical_digest(payload),
            nonce_id=nonce["nonce_id"],
            idempotency_key="runner-submit",
            issued_at_ms=nonce["issued_at_ms"],
            expires_at_ms=nonce["expires_at_ms"],
        )
        response = await client.post(
            INTENT_PATH,
            json={
                "proof": proof.model_dump(mode="json"),
                "signature": sign(key, proof),
                "payload": payload,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        op = response.json()
        assert op["state"] == "accepted"

        async def tick(at):
            source.at = at
            return await advance_owner_position_operation(
                factory,
                source,
                now_ms=at,
                timeout_seconds=2,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
            )

        outcome = await tick(7000)
        async with factory() as u:
            op = await u.owner_position_operations.get(op["operation_id"])
        if stage == "tp_pending_close":
            assert outcome == "closure_pending", op["first_blocker"]
            source.at = 7100
            result = await dispatch_one_command(
                factory,
                source,
                DispatchCommandRequest(
                    worker_id="test-owner-close",
                    ticket_id=t.identity.ticket_id,
                    now_ms=7100,
                    lease_until_ms=12100,
                    timeout_seconds=1,
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    admission_snapshot_validity_ms=1000,
                ),
                clock_ms=lambda: 7100,
            )
            assert result.status.value == "accepted"
            assert await tick(12000) == "closure_pending"
            async with factory() as u:
                commands = await u.exchange_commands.list_for_ticket(
                    t.identity.ticket_id
                )
                assert (
                    next(c for c in commands if c.kind is K.TAKE_PROFIT).status.value
                    == "superseded"
                )
                row = await u.owner_position_operations.get(op["operation_id"])
                assert D(row["payload"]["result"]["executed_quantity"]) == t.quantity
                assert row["payload"]["result"]["cleanup_state"] == "pending"
            assert [x.kind for x in source.writes] == [K.EXIT]
            return
        if fault:
            assert outcome == "rejected" and op["completed_at_ms"] is not None
            assert op["first_blocker"].startswith("owner_stop_snapshot")
            assert not source.writes
            async with factory() as u:
                assert not [
                    c
                    for c in await u.exchange_commands.list_for_ticket(
                        t.identity.ticket_id
                    )
                    if c.kind is K.OWNER_REDUCE
                ]
            return
        assert outcome in {"intent_planned", "reduction_pending"}, op["first_blocker"]
        assert op["payload"]["preview"]["continue_runner"] == (stage == "runner")
        assert (
            D(op["payload"]["preview"]["source_tp_filled_quantity"])
            == before.tp1_filled_qty
        )
        for at in range(8000, 16000, 1000):
            outcome = await tick(at)
            async with factory() as u:
                commands = await u.exchange_commands.list_for_ticket(
                    t.identity.ticket_id
                )
                pending = [
                    c
                    for c in commands
                    if c.status.value == "prepared"
                    and not (stage == "tp_pending_reduce" and c.kind is K.TAKE_PROFIT)
                ]
            for _ in pending:
                source.at = at + 100
                await dispatch_for_ticket(
                    e, source, t.identity.ticket_id, now_ms=source.at
                )
            if outcome == "completed":
                break
        async with factory() as u:
            after = await u.aggregates.get(t.identity.ticket_id)
            op = await u.owner_position_operations.get(op["operation_id"])
            commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            assert outcome == "completed" and op["state"] == (
                "runner_continuing" if stage == "runner" else "wait_price"
            ), op["first_blocker"]
            assert op["completed_at_ms"] is not None
            assert after.status.value == (
                "runner_protected" if stage == "runner" else "position_protected"
            )
            assert after.management_mode.value == "AUTO"
            assert after.tp1_filled_qty == before.tp1_filled_qty
            assert after.position_qty == source.quantity < before.position_qty
            assert (
                after.protected_qty == after.position_qty
                and after.active_stop_close_position
            )
            assert after.tp1_exchange_order_id is None
            assert (
                D(op["payload"]["result"]["executed_quantity"])
                == before.position_qty - after.position_qty
            )
            assert len([c for c in commands if c.kind is K.OWNER_REDUCE]) == 1
        assert await tick(16000) is None
        assert len([r for r in source.writes if r.kind is K.OWNER_REDUCE]) == 1
