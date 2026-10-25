"""Real Session/TOTP and least-privilege SQL boundary on disposable PostgreSQL."""

import re
from pathlib import Path
from uuid import uuid4

import asyncpg
import pyotp
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
)
from src.trading_kernel.interfaces.owner_console_http.app import (
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    OwnerConsoleSettings,
)
from tests.trading_kernel.support.command_dispatch import seed_policy
from tests.trading_kernel.support.owner_auth import (
    BASE_MS,
    PASSWORD,
    TOTP_SEED,
    auth_settings,
)


async def test_directional_http_preview_step_up_receipt_and_real_control_role(
    head_template_engine,
):
    engine = head_template_engine
    await seed_policy(engine)
    async with engine.begin() as c:
        await PostgresDirectionalRiskRepository(c).initialize(
            venue_id="binance-usdm", account_id="experiment-1", now_ms=BASE_MS - 1000
        )
    role = "brc_odr_control_" + uuid4().hex[:12]
    url = engine.url.render_as_string(hide_password=False)
    admin = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    script = (
        Path(__file__).resolve().parents[3]
        / "deploy/owner-console/postgresql/owner-console-control-role.sql"
    ).read_text()
    script = "\n".join(
        line for line in script.splitlines() if not line.startswith("\\")
    )
    read = create_owner_read_engine(url)
    control = create_async_engine(
        url,
        connect_args={"server_settings": {"role": role, "statement_timeout": "3000"}},
    )
    clock = [BASE_MS]
    try:
        await admin.execute(re.sub(r"\bbrc_owner_control\b", role, script))
        settings = OwnerConsoleSettings(
            database_dsn=url,
            account_id="experiment-1",
            public_origin="https://owner.test",
            public_host="owner.test",
            auth=auth_settings(),
        )
        app = create_owner_console_app(
            settings, engine=read, control_engine=control, clock_ms=lambda: clock[0]
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app), base_url=settings.public_origin
            ) as client,
        ):
            assert (
                await client.get("/api/owner/v1/controls/directional-risk")
            ).status_code == 401
            login = await client.post(
                "/api/owner/v1/auth/login",
                json={
                    "username": "owner",
                    "password": PASSWORD,
                    "totp_code": pyotp.TOTP(TOTP_SEED).at(clock[0] // 1000),
                },
            )
            assert login.status_code == 204
            preview = await client.get("/api/owner/v1/controls/directional-risk")
            assert preview.status_code == 200, preview.text
            assert preview.json()["control"]["view"] == "unset"
            assert preview.json()["wallet_balance_at_last_admission"] is None
            clock[0] += 30_000
            body = {
                "expected_version": 1,
                "view": "bearish",
                "reason": "market outlook",
                "idempotency_key": "http-odr",
                "totp_code": pyotp.TOTP(TOTP_SEED).at(clock[0] // 1000),
            }
            changed = await client.post(
                "/api/owner/v1/controls/directional-risk",
                headers={"origin": settings.public_origin},
                json=body,
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["view"] == "bearish"
            readback = await client.get("/api/owner/v1/controls/directional-risk")
            assert (
                readback.json()["long_limit"] == "0.02"
                and readback.json()["short_limit"] == "0.040000000000000000"
            )
            receipt = await client.get(
                "/api/owner/v1/controls/directional-risk/requests/http-odr"
            )
            assert (
                receipt.status_code == 200
                and receipt.json()["result"]["view"] == "bearish"
            )
            clock[0] += 30_000
            body["totp_code"] = pyotp.TOTP(TOTP_SEED).at(clock[0] // 1000)
            repeated = await client.post(
                "/api/owner/v1/controls/directional-risk",
                headers={"origin": settings.public_origin},
                json=body,
            )
            assert repeated.status_code == 200 and repeated.json()["version"] == 2
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))
                == 0
            )
            assert (
                await c.scalar(
                    sa.text("SELECT count(*) FROM brc_directional_risk_events")
                )
                == 1
            )
    finally:
        await read.dispose()
        await control.dispose()
        if await admin.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", role
        ):
            await admin.execute(f'DROP OWNED BY "{role}"')
            await admin.execute(f'DROP ROLE "{role}"')
        await admin.close()
