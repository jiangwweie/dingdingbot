from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.exit_parameter_controls import (
    ExitParameterChange,
    ExitParameterPublishRequest,
    preview_exit_parameters,
    publish_exit_parameters,
)
from src.trading_kernel.application.owner_control import OwnerControlConflict
from src.trading_kernel.domain.entry_regime import REGIME_EVENTS
from src.trading_kernel.domain.exit_policy import registered_event_exit_bindings
from src.trading_kernel.infrastructure.pg_models import (
    entry_regime_current,
    exit_policies,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


async def _seed(engine):
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="exit-experiment",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )


def _request():
    bindings = [
        b
        for b in registered_event_exit_bindings()
        if any(
            g in b.event_spec_id
            for g in ("CPM-RO-001", "MI-001", "MPG-001", "BRF2-001", "SOR-1H-001")
        )
    ]
    changes = []
    for binding in bindings:
        sor = "SOR-1H-001" in binding.event_spec_id
        changes.append(
            ExitParameterChange(
                event_spec_id=binding.event_spec_id,
                expected_version=1,
                expected_binding_id=binding.exit_binding_id,
                reward_multiple=Decimal("1.2" if sor else "1.0"),
                quantity_fraction=Decimal("0.50" if sor else "0.05"),
                max_actual_fraction=None if sor else Decimal("0.50"),
                ma50_enabled=True if binding.event_spec_id in REGIME_EVENTS else None,
                expected_regime_revision=1
                if binding.event_spec_id in REGIME_EVENTS
                else None,
            )
        )
    return ExitParameterPublishRequest(
        expected_version=1,
        reason="owner_confirmed_experiment",
        idempotency_key="owner:exit-params:1",
        owner_identity="owner",
        now_ms=2000,
        venue_id="binance-usdm",
        account_id="exit-experiment",
        changes=tuple(changes),
    )


@pytest.mark.asyncio
async def test_bundle_publishes_six_separate_profiles_and_three_regime_controls_atomically(
    issue_engine,
):
    await _seed(issue_engine)
    request = _request()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        preview = await preview_exit_parameters(uow, request)
        assert len(preview.profiles) == 6
        assert len({p.exit_profile_id for p in preview.profiles}) == 6
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        receipt = await publish_exit_parameters(
            uow, request, authentication_strength="totp_step_up"
        )
    assert len(receipt.bindings) == 6
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        replay = await publish_exit_parameters(
            uow,
            request.model_copy(update={"now_ms": 3000}),
            authentication_strength="totp_step_up",
        )
        assert replay == receipt
        for event in REGIME_EVENTS:
            control = await uow.entry_regimes.get_control(event)
            assert control.enabled is True and control.revision == 2
    async with issue_engine.connect() as c:
        assert (
            await c.scalar(
                sa.select(sa.func.count())
                .select_from(exit_policies)
                .where(exit_policies.c.exit_policy_id.like("exit-profile:owner:%"))
            )
            == 6
        )


@pytest.mark.asyncio
async def test_one_stale_binding_rejects_entire_bundle_without_partial_changes(
    issue_engine,
):
    await _seed(issue_engine)
    request = _request()
    bad = request.changes[-1].model_copy(update={"expected_version": 99})
    request = request.model_copy(update={"changes": (*request.changes[:-1], bad)})
    with pytest.raises(OwnerControlConflict):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await publish_exit_parameters(
                uow, request, authentication_strength="totp_step_up"
            )
    async with issue_engine.connect() as c:
        assert (
            await c.scalar(
                sa.select(sa.func.count())
                .select_from(exit_policies)
                .where(exit_policies.c.exit_policy_id.like("exit-profile:owner:%"))
            )
            == 0
        )
        assert set(
            (await c.execute(sa.select(entry_regime_current.c.revision))).scalars()
        ) == {1}


@pytest.mark.asyncio
async def test_http_preview_is_readonly_and_publish_requires_totp(issue_engine):
    import pyotp
    from argon2 import PasswordHasher
    from httpx import ASGITransport, AsyncClient

    from src.trading_kernel.interfaces.owner_console_http.app import (
        OwnerConsoleSettings,
        create_owner_console_app,
    )
    from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings

    await _seed(issue_engine)
    from src.trading_kernel.infrastructure.pg_owner_read_repository import (
        create_owner_read_engine,
    )

    class Market:
        async def close(self):
            pass

    read_engine = create_owner_read_engine(
        issue_engine.url.render_as_string(hide_password=False)
    )
    now = 1_800_000_000_000
    seed = "JBSWY3DPEHPK3PXP"
    app = create_owner_console_app(
        OwnerConsoleSettings(
            database_dsn="postgresql+asyncpg://unused",
            control_database_dsn="postgresql+asyncpg://unused",
            account_id="exit-experiment",
            public_origin="https://owner.example.test",
            public_host="owner.example.test",
            auth=OwnerAuthSettings(
                username="owner",
                password_hash=PasswordHasher(
                    time_cost=3, memory_cost=65536, parallelism=1
                ).hash("test-password"),
                totp_seed=seed,
                session_signing_key="test-signing-key-for-exit-parameter-controls",
            ),
        ),
        engine=read_engine,
        control_engine=issue_engine,
        market_data=Market(),
        clock_ms=lambda: now,
    )
    headers = {"origin": "https://owner.example.test", "host": "owner.example.test"}
    body = _request().model_dump(
        mode="json", exclude={"owner_identity", "now_ms", "venue_id", "account_id"}
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="https://owner.example.test"
        ) as client,
    ):
        login = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": "test-password",
                "totp_code": pyotp.TOTP(seed).at(now // 1000),
            },
        )
        assert login.status_code == 204
        current = await client.get("/api/owner/v1/controls/exit-parameters")
        assert current.status_code == 200 and len(current.json()["rows"]) == 6
        preview = await client.post(
            "/api/owner/v1/controls/exit-parameters/preview", json=body, headers=headers
        )
        assert preview.status_code == 200, preview.text
        assert all(
            p["tp1"]["price_basis"] == "actual_fill" for p in preview.json()["profiles"]
        )
        missing = await client.post(
            "/api/owner/v1/controls/exit-parameters/publish", json=body, headers=headers
        )
        assert missing.status_code == 403
        applied = await client.post(
            "/api/owner/v1/controls/exit-parameters/publish",
            json={**body, "totp_code": pyotp.TOTP(seed).at(now // 1000)},
            headers=headers,
        )
        assert applied.status_code == 200, applied.text
        assert len(applied.json()["bindings"]) == 6

    await read_engine.dispose()
