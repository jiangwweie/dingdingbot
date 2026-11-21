"""Real read/control roles across the authenticated Console configuration flow."""
from decimal import Decimal

import pyotp
import pytest
import sqlalchemy as sa
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
)
from src.trading_kernel.interfaces.owner_console_http.app import (
    OwnerConsoleSettings,
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings
from tests.trading_kernel.support.exit_configuration import intent
from tests.trading_kernel.support.owner_roles import apply_owner_control_grants


@pytest.mark.asyncio
async def test_upgrade_refreshes_declared_read_grants_without_adding_write_authority(
    head_template_engine,
):
    from scripts.trading_kernel import manual_same_schema_upgrade as upgrade

    engine = head_template_engine
    await apply_owner_control_grants(engine)
    async with engine.begin() as c:
        await c.execute(sa.text("REVOKE SELECT ON brc_btc_ma50_current,brc_post_fill_exit_plans FROM brc_owner_control"))
        writes = (await c.execute(sa.text("SELECT table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee='brc_owner_control' AND privilege_type<>'SELECT' ORDER BY table_name,privilege_type"))).all()
    await upgrade.refresh_owner_read_grants(engine)
    async with engine.connect() as c:
        for table in ("brc_btc_ma50_current", "brc_post_fill_exit_plans"):
            assert await c.scalar(sa.text("SELECT has_table_privilege('brc_owner_control',:table,'SELECT')"), {"table": table})
        assert writes == (await c.execute(sa.text("SELECT table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee='brc_owner_control' AND privilege_type<>'SELECT' ORDER BY table_name,privilege_type"))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("control_available", [True, False])
@pytest.mark.parametrize("directional_sor", [False, True])
async def test_configuration_get_uses_readonly_role_then_real_control_flow(
    head_template_engine, control_available, directional_sor
):
    engine = head_template_engine
    await intent(engine)
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_DIRECTIONAL_EVENTS,
        ORB_DIRECTIONAL_LONG_EVENT,
    )
    if directional_sor:
        from src.trading_kernel.domain.strategy_registry import (
            registered_strategy_contracts,
        )
        from src.trading_kernel.infrastructure.pg_unit_of_work import (
            PostgresKernelUnitOfWork,
        )
        from src.trading_kernel.infrastructure.strategy_registry_seed import (
            seed_strategy_registry,
        )

        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1500, contracts=tuple(
                contract for contract in registered_strategy_contracts(include_sor_split=True)
                if contract.event_spec_id in ORB_DIRECTIONAL_EVENTS
            ))
    await apply_owner_control_grants(engine)
    async with engine.begin() as c:
        await c.execute(sa.text("""DO $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='brc_owner_console') THEN
            CREATE ROLE brc_owner_console NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
            END IF; END $$"""))
        await c.execute(sa.text("GRANT USAGE ON SCHEMA public TO brc_owner_console"))
        await c.execute(sa.text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO brc_owner_console"))
        # Exact upgraded-production privilege shape: controls can mutate config,
        # but the market snapshot is readable through the Console read role only.
        await c.execute(sa.text("REVOKE SELECT ON brc_btc_ma50_current FROM brc_owner_control"))
        assert not await c.scalar(sa.text("SELECT has_table_privilege('brc_owner_control','brc_btc_ma50_current','SELECT')"))
        before = (await c.execute(sa.text("SELECT * FROM brc_owner_policy_current"))).mappings().all()

    read = create_owner_read_engine(engine.url.render_as_string(hide_password=False))
    control = create_async_engine(engine.url) if control_available else None

    def use_role(target, role):
        @sa.event.listens_for(target.sync_engine, "connect")
        def set_role(connection, _):
            cursor = connection.cursor()
            cursor.execute("SET ROLE " + role)
            cursor.close()

    use_role(read, "brc_owner_console")
    if control is not None:
        use_role(control, "brc_owner_control")
    now = 1_800_000_000_000
    seed = "JBSWY3DPEHPK3PXP"
    settings = OwnerConsoleSettings(
        database_dsn="postgresql+asyncpg://unused",
        control_database_dsn="postgresql+asyncpg://unused" if control else None,
        account_id="manual-account",
        public_origin="https://owner.example.test",
        public_host="owner.example.test",
        auth=OwnerAuthSettings(
            username="owner",
            password_hash=PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1).hash("test-password"),
            totp_seed=seed,
            session_signing_key="test-signing-key-with-enough-random-looking-material",
        ),
    )

    class Market:
        async def close(self):
            pass

    app = create_owner_console_app(settings, engine=read, control_engine=control,
        market_data=Market(), clock_ms=lambda: now)
    headers = {"origin": settings.public_origin}
    path = "/api/owner/v1/controls/exit-configuration"
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url=settings.public_origin,
    ) as client:
        assert (await client.get(path)).status_code == 401
        login = await client.post("/api/owner/v1/auth/login", json={
            "username": "owner", "password": "test-password",
            "totp_code": pyotp.TOTP(seed).at(now // 1000),
        })
        assert login.status_code == 204
        response = await client.get(path)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["current"] is None and len(view["intent"]["events"]) == 6
        assert view["ma50_snapshot"] is None
        for item in view["intent"]["events"][:4]:
            assert Decimal(item["target_fraction"]) == Decimal(".05")
        if directional_sor:
            parameters = {item["event_spec_id"]: item for item in view["intent"]["events"]}
            assert parameters[ORB_DIRECTIONAL_LONG_EVENT]["ma50_enabled"] is True
            assert parameters[ORB_DIRECTIONAL_EVENTS[1]]["ma50_enabled"] is False
            parameters[ORB_DIRECTIONAL_LONG_EVENT]["ma50_enabled"] = False
        if control_available:
            preview = await client.post(path + "/preview", headers=headers,
                json={"intent": view["intent"]})
            assert preview.status_code == 200, preview.text
            facts = preview.json()
            body = {"intent": view["intent"], "expected_version": 0,
                "preview_digest": facts["preview_digest"],
                "preview_valid_until_ms": facts["valid_until_ms"],
                "reason": "reviewed six exits and three gates", "idempotency_key": "roles-exit-config"}
            assert (await client.post(path, headers=headers, json=body)).status_code == 403
            now += 30_000
            body["totp_code"] = pyotp.TOTP(seed).at(now // 1000)
            activated = await client.post(path, headers=headers, json=body)
            assert activated.status_code == 200, activated.text
            readback = await client.get(path)
            assert readback.status_code == 200, readback.text
            assert readback.json()["current"]["revision"] == 1
            if directional_sor:
                saved = next(item for item in readback.json()["intent"]["events"]
                             if item["event_spec_id"] == ORB_DIRECTIONAL_LONG_EVENT)
                assert saved["ma50_enabled"] is False
            receipt = await client.get(path + "/requests/roles-exit-config")
            assert receipt.status_code == 200
            assert receipt.json()["configuration_id"] == activated.json()["configuration_id"]
    async with engine.connect() as c:
        assert before == (await c.execute(sa.text("SELECT * FROM brc_owner_policy_current"))).mappings().all()
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_exit_configurations")) == int(control_available)
