"""Signed phone intents use production-equivalent role privileges."""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.manual_profit_plan import ManualProfitPlan
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.domain.owner_position_intent import INTENT_PATH
from src.trading_kernel.infrastructure.pg_models import (
    runtime_capabilities_current,
    trade_aggregates,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.routes.mobile import (
    COOKIE,
    router,
)
from tests.trading_kernel.support.owner_device import sign
from tests.trading_kernel.support.owner_reduction import setup_operation
from tests.trading_kernel.support.owner_roles import apply_owner_control_grants


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "terms"),
    [
        ("position_reduce", {"quantity": ".0005"}),
        ("protection_tighten", {"price": "59500"}),
        ("manual_tp_set", {"price": "63000", "quantity": ".0002"}),
        ("manual_tp_cancel", {}),
        ("position_close", {}),
    ],
)
async def test_signed_intent_accepts_under_actual_api_role(
    head_template_engine, kind, terms
):
    engine = head_template_engine
    ticket, device, _, key = await setup_operation(engine)
    await apply_owner_control_grants(engine)
    async with PostgresKernelUnitOfWork(engine) as u:
        a = await u.aggregates.get(ticket.identity.ticket_id)
        assert a is not None
    async with engine.begin() as c:
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
        if kind == "manual_tp_cancel":
            plan = ManualProfitPlan(
                operation_id="prior",
                command_id="prior",
                exchange_order_id=a.tp1_exchange_order_id,
                price=a.ticket.take_profit_prices[0],
                target_quantity=a.tp1_target_qty,
                prior_tp_filled_quantity=a.tp1_filled_qty,
                started_from_runner=False,
            )
            await c.execute(
                sa.update(trade_aggregates)
                .where(trade_aggregates.c.ticket_id == a.identity.ticket_id)
                .values(manual_profit_plan=plan.model_dump(mode="json"))
            )
    api_engine = create_async_engine(
        engine.url, connect_args={"server_settings": {"role": "brc_owner_control"}}
    )
    try:
        app = FastAPI()
        domain = ticket.identity.netting_domain
        app.state.owner_console_settings = SimpleNamespace(
            public_host="owner.test",
            public_origin="https://owner.test",
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            auth=SimpleNamespace(session_signing_key="basis-test-key"),
        )
        app.state.owner_control_engine = api_engine
        app.state.owner_clock_ms = lambda: 6500
        app.include_router(router)
        headers = {"origin": "https://owner.test"}
        async with api_engine.connect() as c:
            assert await c.scalar(sa.text("SELECT current_user")) == "brc_owner_control"
            assert not await c.scalar(
                sa.text(
                    "SELECT has_column_privilege(current_user, 'brc_trade_aggregates', 'position_qty', 'UPDATE')"
                )
            )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://owner.test"
        ) as client:
            client.cookies.set(
                COOKIE, device["session_token"], domain="owner.test", path="/"
            )
            assert (
                await client.post(
                    "/api/owner/v1/mobile/operations/preview", headers=headers
                )
            ).status_code == 410
            positions = (await client.get("/api/owner/v1/mobile/positions")).json()[
                "items"
            ]
            payload = {"kind": kind, "ticket_id": a.identity.ticket_id, **terms}
            if kind == "position_reduce":
                payload.update(
                    basis_version=positions[0]["version"],
                    basis_quantity=positions[0]["position_qty"],
                    basis_token=positions[0]["reduction_basis_token"],
                )
            if kind in {"manual_tp_set", "manual_tp_cancel"}:
                payload["tp_order_id"] = positions[0]["tp1_exchange_order_id"]
            nonce = (
                await client.post(
                    "/api/owner/v1/mobile/nonces", json={}, headers=headers
                )
            ).json()
            proof = DeviceWriteProof(
                device_id=device["device_id"],
                device_epoch=1,
                method="POST",
                path=INTENT_PATH,
                body_digest=canonical_digest(payload),
                nonce_id=nonce["nonce_id"],
                idempotency_key="phone-intent",
                issued_at_ms=nonce["issued_at_ms"],
                expires_at_ms=nonce["expires_at_ms"],
            )
            packet = {
                "proof": proof.model_dump(mode="json"),
                "signature": sign(key, proof),
                "payload": payload,
            }
            if kind == "position_reduce":
                forged = {**payload, "basis_quantity": "100"}
                denied = await client.post(
                    INTENT_PATH, json={**packet, "payload": forged}, headers=headers
                )
                assert denied.status_code == 409
                assert denied.json()["detail"] == "reduction_basis_invalid"
            result = await client.post(INTENT_PATH, json=packet, headers=headers)
            assert result.status_code == 200, result.text
            receipt = result.json()
            assert receipt["state"] == "accepted" and receipt["kind"] == kind
            replay = await client.post(INTENT_PATH, json=packet, headers=headers)
            assert replay.json() == receipt
            recovered = await client.get(
                "/api/owner/v1/mobile/requests/phone-intent",
                params={"nonce_id": nonce["nonce_id"]},
            )
            assert recovered.json() == {"state": "completed", "result": receipt}
            async with PostgresKernelUnitOfWork(engine) as u:
                op = await u.owner_position_operations.get(receipt["operation_id"])
                assert (
                    op["payload"]["intent"] == payload
                    and op["payload"]["preview"] is None
                )
                assert op["payload"]["start_deadline_ms"] == 66500
                assert not any(
                    getattr(c.payload, "owner_operation_id", None)
                    for c in await u.exchange_commands.list_for_ticket(
                        a.identity.ticket_id
                    )
                )
            if kind == "position_reduce":
                from src.trading_kernel.application.advance_owner_position_operation import (
                    advance_owner_position_operation,
                )
                from src.trading_kernel.infrastructure.runtime_identity import (
                    CURRENT_SCHEMA_REVISION,
                )

                class NoVenueRead:
                    async def read_owner_position(self, **kwargs):
                        raise AssertionError("An expired intent cannot read the venue")

                outcome = await advance_owner_position_operation(
                    lambda: PostgresKernelUnitOfWork(engine),
                    NoVenueRead(),
                    now_ms=66500,
                    timeout_seconds=1,
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                )
                assert outcome == "expired"
                expired = (
                    await client.get(
                        "/api/owner/v1/mobile/operations/" + receipt["operation_id"]
                    )
                ).json()
                assert expired["first_blocker"] == "owner_start_window_expired"
                assert expired["completed_at_ms"] == 66500
    finally:
        await api_engine.dispose()
