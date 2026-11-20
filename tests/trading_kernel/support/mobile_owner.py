"""Drive real mobile control routes with a disposable signed browser identity."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.interfaces.owner_console_http.routes.mobile import router
from tests.trading_kernel.support.owner_device import keypair, sign


@asynccontextmanager
async def mobile_client(engine, *, at_ms, control_engine=None):
    key, jwk = keypair()
    async with engine.begin() as c:
        grant = await PostgresOwnerDeviceRepository(c).issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=at_ms
        )
    app = FastAPI()
    app.state.owner_console_settings = SimpleNamespace(
        public_host="owner.test",
        public_origin="https://owner.test",
        owner_policy_id="policy-main",
        account_id="generic-snapshot",
        venue_id="binance-usdm",
    )
    app.state.owner_control_engine = engine if control_engine is None else control_engine
    app.state.owner_clock_ms = lambda: at_ms
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://owner.test"
    ) as client:
        result = await client.post(
            "/api/owner/v1/mobile/devices/bind",
            json={"token": grant, "public_key": jwk},
            headers={"origin": "https://owner.test"},
        )
        assert result.status_code == 200, result.text
        yield client, app, key, result.json()


async def strategy_control(browser, *, group, enabled, version, at_ms):
    client, app, key, device = browser
    app.state.owner_clock_ms = lambda: at_ms
    nonce = (
        await client.post(
            "/api/owner/v1/mobile/nonces", headers={"origin": "https://owner.test"}
        )
    ).json()
    payload = {
        "strategy_group_id": group,
        "enabled": enabled,
        "expected_version": version,
    }
    proof = DeviceWriteProof(
        device_id=device["device_id"],
        device_epoch=device["device_epoch"],
        method="POST",
        path="/api/owner/v1/mobile/controls/strategy",
        body_digest=canonical_digest(payload),
        nonce_id=nonce["nonce_id"],
        idempotency_key=f"{group}:{version}:{at_ms}",
        issued_at_ms=nonce["issued_at_ms"],
        expires_at_ms=nonce["expires_at_ms"],
    )
    response = await client.post(
        proof.path,
        json={
            "proof": proof.model_dump(mode="json"),
            "signature": sign(key, proof),
            "payload": payload,
        },
        headers={"origin": "https://owner.test"},
    )
    assert response.status_code == 200, response.text
    return response.json()
