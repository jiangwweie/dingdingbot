from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import asyncpg
import pyotp
import pytest
import sqlalchemy as sa
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.owner_control import (
    ExitProfileBindingMutationRequest,
    ExitProfileRetirementRequest,
    OwnerControlBlocked,
    OwnerControlConflict,
    retire_exit_profile,
    switch_event_exit_profile,
)
from src.trading_kernel.domain.exit_policy import (
    registered_event_exit_bindings,
    registered_exit_profiles,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_exit_profile_repository import (
    PostgresExitProfileAuthorityRepository,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_exit_profile_binding_current,
    event_exit_profile_binding_events,
    event_exit_profile_bindings,
    exit_policies,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    PostgresStrategyRegistryRepository,
)
from src.trading_kernel.interfaces.owner_console_http.app import (
    OwnerConsoleSettings,
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings
from src.trading_kernel.interfaces.readonly_api import (
    ExitProfileAuthorityReadonlyRequest,
    get_exit_profile_authority_view,
)
from tests.trading_kernel.support.postgres import TEST_POSTGRES_ADMIN_DSN

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_concurrent_binding_switches_commit_one_expected_version_sequence() -> (
    None
):
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        targets = [
            item
            for item in registered_exit_profiles()
            if item.position_side == "long"
            and item.exit_profile_id != source.exit_profile_id
        ][:2]

        async def mutate(index: int):
            async with PostgresKernelUnitOfWork(engine) as uow:
                return await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MPG-001",
                    event_spec_id=source.event_spec_id,
                    request=ExitProfileBindingMutationRequest(
                        expected_version=1,
                        expected_binding_id=source.exit_binding_id,
                        target_exit_profile_id=targets[index].exit_profile_id,
                        target_exit_profile_semantic_hash=targets[
                            index
                        ].semantic_hash(),
                        reason=f"concurrent_switch_{index}",
                        idempotency_key=f"owner-request:exit-binding:{index}",
                        owner_identity="owner",
                        now_ms=1_800_000_000_000 + index,
                    ),
                    authentication_strength="totp_step_up",
                )

        results = await asyncio.gather(mutate(0), mutate(1), return_exceptions=True)

        assert sum(not isinstance(item, BaseException) for item in results) == 1
        assert sum(isinstance(item, OwnerControlConflict) for item in results) == 1
        async with engine.connect() as connection:
            current = (
                (
                    await connection.execute(
                        sa.select(event_exit_profile_binding_current).where(
                            event_exit_profile_binding_current.c.event_spec_id
                            == source.event_spec_id
                        )
                    )
                )
                .mappings()
                .one()
            )
        assert int(current["projection_version"]) == 2
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_profile_retire_racing_binding_switch_cannot_create_retired_current() -> (
    None
):
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MI-001" in item.event_spec_id
        )
        target = next(
            item
            for item in registered_exit_profiles()
            if "momentum-tail" in item.exit_profile_id
        )
        target_owner = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        replacement = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=target_owner.event_spec_id,
                request=ExitProfileBindingMutationRequest(
                    expected_version=1,
                    expected_binding_id=target_owner.exit_binding_id,
                    target_exit_profile_id=replacement.exit_profile_id,
                    target_exit_profile_semantic_hash=replacement.semantic_hash(),
                    reason="free_target_profile",
                    idempotency_key="owner-request:retire-race:free-target",
                    owner_identity="owner",
                    now_ms=1_799_999_999_999,
                ),
                authentication_strength="totp_step_up",
            )

        async def bind():
            async with PostgresKernelUnitOfWork(engine) as uow:
                return await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MPG-001",
                    event_spec_id=source.event_spec_id,
                    request=ExitProfileBindingMutationRequest(
                        expected_version=1,
                        expected_binding_id=source.exit_binding_id,
                        target_exit_profile_id=target.exit_profile_id,
                        target_exit_profile_semantic_hash=target.semantic_hash(),
                        reason="retire_race_bind",
                        idempotency_key="owner-request:retire-race:bind",
                        owner_identity="owner",
                        now_ms=1_800_000_000_000,
                    ),
                    authentication_strength="totp_step_up",
                )

        async def retire():
            async with PostgresKernelUnitOfWork(engine) as uow:
                return await retire_exit_profile(
                    uow,
                    request=ExitProfileRetirementRequest(
                        expected_version=1,
                        exit_profile_id=target.exit_profile_id,
                        exit_profile_semantic_hash=target.semantic_hash(),
                        reason="retire_race_retire",
                        idempotency_key="owner-request:retire-race:retire",
                        owner_identity="owner",
                        now_ms=1_800_000_000_001,
                    ),
                    authentication_strength="totp_step_up",
                )

        results = await asyncio.gather(bind(), retire(), return_exceptions=True)
        assert sum(not isinstance(item, BaseException) for item in results) == 1
        assert (
            sum(
                isinstance(item, (OwnerControlBlocked, OwnerControlConflict))
                for item in results
            )
            == 1
        )

        async with engine.connect() as connection:
            status = str(
                await connection.scalar(
                    sa.select(exit_policies.c.status).where(
                        exit_policies.c.exit_policy_id == target.exit_profile_id
                    )
                )
            )
            current_count = int(
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(event_exit_profile_binding_current)
                    .join(
                        event_exit_profile_bindings,
                        event_exit_profile_bindings.c.exit_binding_id
                        == event_exit_profile_binding_current.c.exit_binding_id,
                    )
                    .where(
                        event_exit_profile_bindings.c.exit_profile_id
                        == target.exit_profile_id
                    )
                )
                or 0
            )
        assert not (status == "retired" and current_count > 0)
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_binding_switch_requires_step_up_and_replays_exact_authorization() -> (
    None
):
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        target = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        request = ExitProfileBindingMutationRequest(
            expected_version=1,
            expected_binding_id=source.exit_binding_id,
            target_exit_profile_id=target.exit_profile_id,
            target_exit_profile_semantic_hash=target.semantic_hash(),
            reason="owner_switch_profile",
            idempotency_key="owner-request:binding-replay",
            owner_identity="owner",
            now_ms=1_800_000_000_000,
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            with pytest.raises(
                OwnerControlBlocked,
                match="exit_profile_bind_requires_step_up",
            ):
                await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MPG-001",
                    event_spec_id=source.event_spec_id,
                    request=request,
                    authentication_strength="session",  # type: ignore[arg-type]
                )

        async with PostgresKernelUnitOfWork(engine) as uow:
            committed = await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=source.event_spec_id,
                request=request,
                authentication_strength="totp_step_up",
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            replayed = await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=source.event_spec_id,
                request=request,
                authentication_strength="totp_step_up",
            )
        assert replayed == committed

        second_target = next(
            item
            for item in registered_exit_profiles()
            if "impulse-decay" in item.exit_profile_id
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            later = await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=source.event_spec_id,
                request=ExitProfileBindingMutationRequest(
                    expected_version=2,
                    expected_binding_id=committed.exit_binding_id,
                    target_exit_profile_id=second_target.exit_profile_id,
                    target_exit_profile_semantic_hash=second_target.semantic_hash(),
                    reason="later_profile_switch",
                    idempotency_key="owner-request:binding-later",
                    owner_identity="owner",
                    now_ms=1_800_000_000_001,
                ),
                authentication_strength="totp_step_up",
            )
        assert later.projection_version == 3
        async with PostgresKernelUnitOfWork(engine) as uow:
            replay_after_later_switch = await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=source.event_spec_id,
                request=request.model_copy(update={"now_ms": 1_800_000_000_999}),
                authentication_strength="totp_step_up",
            )
        assert replay_after_later_switch == committed

        mismatched = request.model_copy(update={"reason": "different_payload"})
        async with PostgresKernelUnitOfWork(engine) as uow:
            with pytest.raises(OwnerControlConflict, match="idempotency_key_conflict"):
                await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MPG-001",
                    event_spec_id=source.event_spec_id,
                    request=mismatched,
                    authentication_strength="totp_step_up",
                )
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_binding_switch_rejects_mismatched_strategy_scope() -> None:
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        target = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        with pytest.raises(OwnerControlBlocked, match="event_strategy_scope_mismatch"):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MI-001",
                    event_spec_id=source.event_spec_id,
                    request=ExitProfileBindingMutationRequest(
                        expected_version=1,
                        expected_binding_id=source.exit_binding_id,
                        target_exit_profile_id=target.exit_profile_id,
                        target_exit_profile_semantic_hash=target.semantic_hash(),
                        reason="wrong_strategy_scope",
                        idempotency_key="owner-request:wrong-strategy-scope",
                        owner_identity="owner",
                        now_ms=1_800_000_000_000,
                    ),
                    authentication_strength="totp_step_up",
                )
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_strategy_retirement_removes_only_its_binding_and_preserves_shared_profile() -> (
    None
):
    database_name, engine = await _database()
    try:
        await _seed(engine)
        cpm_contract = next(
            item
            for item in registered_strategy_contracts()
            if item.strategy_group_id == "CPM-RO-001"
        )
        mi_binding = next(
            item
            for item in registered_event_exit_bindings()
            if "MI-001" in item.event_spec_id
        )
        shared_profile = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            mi_shared = await switch_event_exit_profile(
                uow,
                strategy_group_id="MI-001",
                event_spec_id=mi_binding.event_spec_id,
                request=ExitProfileBindingMutationRequest(
                    expected_version=1,
                    expected_binding_id=mi_binding.exit_binding_id,
                    target_exit_profile_id=shared_profile.exit_profile_id,
                    target_exit_profile_semantic_hash=shared_profile.semantic_hash(),
                    reason="share_profile_before_retirement",
                    idempotency_key="owner-request:share-profile-before-retirement",
                    owner_identity="owner",
                    now_ms=1_800_000_000_000,
                ),
                authentication_strength="totp_step_up",
            )

        retired_at_ms = 1_800_000_000_100
        async with engine.begin() as connection:
            await PostgresStrategyRegistryRepository(
                connection
            )._retire_strategy_version(
                strategy_group_id=cpm_contract.strategy_group_id,
                strategy_version_id=cpm_contract.strategy_version_id,
                semantic_version=cpm_contract.semantic_version,
                retired_at_ms=retired_at_ms,
            )

        async with engine.connect() as connection:
            cpm_current = await connection.scalar(
                sa.select(event_exit_profile_binding_current.c.exit_binding_id).where(
                    event_exit_profile_binding_current.c.event_spec_id
                    == cpm_contract.event_spec_id
                )
            )
            mi_current = await connection.scalar(
                sa.select(event_exit_profile_binding_current.c.exit_binding_id).where(
                    event_exit_profile_binding_current.c.event_spec_id
                    == mi_binding.event_spec_id
                )
            )
            profile_status = await connection.scalar(
                sa.select(exit_policies.c.status).where(
                    exit_policies.c.exit_policy_id == shared_profile.exit_profile_id
                )
            )
            retirement_time = await connection.scalar(
                sa.select(event_exit_profile_binding_events.c.created_at_ms)
                .where(
                    event_exit_profile_binding_events.c.event_spec_id
                    == cpm_contract.event_spec_id,
                    event_exit_profile_binding_events.c.operation == "RETIRED",
                )
                .limit(1)
            )
        assert cpm_current is None
        assert mi_current == mi_shared.exit_binding_id
        assert profile_status == "active"
        assert retirement_time == retired_at_ms
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_active_profile_blocks_retirement_and_retired_profile_cannot_bind() -> (
    None
):
    database_name, engine = await _database()
    try:
        await _seed(engine)
        mpg_binding = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        momentum = next(
            item
            for item in registered_exit_profiles()
            if "momentum-tail" in item.exit_profile_id
        )
        trend = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        retirement = ExitProfileRetirementRequest(
            expected_version=1,
            exit_profile_id=momentum.exit_profile_id,
            exit_profile_semantic_hash=momentum.semantic_hash(),
            reason="retire_momentum_profile",
            idempotency_key="owner-request:retire-momentum",
            owner_identity="owner",
            now_ms=1_800_000_000_000,
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            with pytest.raises(
                OwnerControlBlocked,
                match="exit_profile_retire_requires_step_up",
            ):
                await retire_exit_profile(
                    uow,
                    request=retirement,
                    authentication_strength="session",  # type: ignore[arg-type]
                )
        with pytest.raises(
            OwnerControlBlocked,
            match="exit_profile_has_current_binding",
        ):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await retire_exit_profile(
                    uow,
                    request=retirement,
                    authentication_strength="totp_step_up",
                )

        async with PostgresKernelUnitOfWork(engine) as uow:
            await switch_event_exit_profile(
                uow,
                strategy_group_id="MPG-001",
                event_spec_id=mpg_binding.event_spec_id,
                request=ExitProfileBindingMutationRequest(
                    expected_version=1,
                    expected_binding_id=mpg_binding.exit_binding_id,
                    target_exit_profile_id=trend.exit_profile_id,
                    target_exit_profile_semantic_hash=trend.semantic_hash(),
                    reason="release_momentum_profile",
                    idempotency_key="owner-request:release-momentum",
                    owner_identity="owner",
                    now_ms=1_800_000_000_001,
                ),
                authentication_strength="totp_step_up",
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            retired = await retire_exit_profile(
                uow,
                request=retirement.model_copy(update={"now_ms": 1_800_000_000_002}),
                authentication_strength="totp_step_up",
            )
        assert retired.status == "retired"
        async with PostgresKernelUnitOfWork(engine) as uow:
            replayed_retirement = await retire_exit_profile(
                uow,
                request=retirement.model_copy(update={"now_ms": 1_800_000_000_999}),
                authentication_strength="totp_step_up",
            )
        assert replayed_retirement == retired

        with pytest.raises(OwnerControlConflict, match="idempotency_key_conflict"):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await retire_exit_profile(
                    uow,
                    request=retirement.model_copy(
                        update={
                            "reason": "different_retirement_payload",
                            "now_ms": 1_800_000_001_000,
                        }
                    ),
                    authentication_strength="totp_step_up",
                )

        mi_binding = next(
            item
            for item in registered_event_exit_bindings()
            if "MI-001" in item.event_spec_id
        )
        with pytest.raises(OwnerControlBlocked, match="exit_profile_not_active"):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await switch_event_exit_profile(
                    uow,
                    strategy_group_id="MI-001",
                    event_spec_id=mi_binding.event_spec_id,
                    request=ExitProfileBindingMutationRequest(
                        expected_version=1,
                        expected_binding_id=mi_binding.exit_binding_id,
                        target_exit_profile_id=momentum.exit_profile_id,
                        target_exit_profile_semantic_hash=momentum.semantic_hash(),
                        reason="cannot_bind_retired_profile",
                        idempotency_key="owner-request:bind-retired",
                        owner_identity="owner",
                        now_ms=1_800_000_000_003,
                    ),
                    authentication_strength="totp_step_up",
                )
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_exit_profile_readonly_view_is_exact_bounded_and_read_only() -> None:
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            assert await connection.scalar(
                sa.text("SHOW transaction_read_only")
            ) == "on"
            view = await get_exit_profile_authority_view(
                PostgresExitProfileAuthorityRepository(connection),
                ExitProfileAuthorityReadonlyRequest(
                    event_spec_id=source.event_spec_id,
                    event_limit=5,
                ),
            )
            await transaction.rollback()

        assert len(view.profiles) == 8
        assert len(view.current_bindings) == 1
        assert len(view.binding_facts) == 1
        assert len(view.recent_events) == 1
        assert view.current_bindings[0].event_spec_id == source.event_spec_id
        assert view.binding_facts[0].exit_binding_id == source.exit_binding_id
        assert (
            view.binding_facts[0].binding_semantic_hash
            == source.binding_semantic_hash
        )
        assert view.catalog_digest.startswith("sha256:")
    finally:
        await engine.dispose()
        await _drop(database_name)


@pytest.mark.asyncio
async def test_exit_profile_http_requires_totp_and_maps_stale_version_to_409() -> None:
    database_name, engine = await _database()
    try:
        await _seed(engine)
        source = next(
            item
            for item in registered_event_exit_bindings()
            if "MPG-001" in item.event_spec_id
        )
        target = next(
            item
            for item in registered_exit_profiles()
            if "trend-continuation" in item.exit_profile_id
        )
        totp_seed = "JBSWY3DPEHPK3PXP"
        now_ms = 1_800_000_000_000
        read_engine = create_owner_read_engine(
            engine.url.render_as_string(hide_password=False)
        )
        app = create_owner_console_app(
            OwnerConsoleSettings(
                database_dsn="postgresql+asyncpg://unused",
                control_database_dsn="postgresql+asyncpg://unused",
                account_id="exit-profile-authority-test",
                public_origin="https://owner.example.test",
                public_host="owner.example.test",
                auth=OwnerAuthSettings(
                    username="owner",
                    password_hash=PasswordHasher(
                        time_cost=3,
                        memory_cost=65_536,
                        parallelism=1,
                        hash_len=32,
                        salt_len=16,
                    ).hash("test-password"),
                    totp_seed=totp_seed,
                    session_signing_key=(
                        "test-signing-key-with-enough-random-looking-material"
                    ),
                ),
            ),
            engine=read_engine,
            control_engine=engine,
            market_data=_NoopMarketData(),  # type: ignore[arg-type]
            clock_ms=lambda: now_ms,
        )
        headers = {
            "origin": "https://owner.example.test",
            "host": "owner.example.test",
        }
        async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://owner.example.test",
        ) as client:
            login = await client.post(
                "/api/owner/v1/auth/login",
                json={
                    "username": "owner",
                    "password": "test-password",
                    "totp_code": pyotp.TOTP(totp_seed).at(now_ms // 1_000),
                },
            )
            assert login.status_code == 204
            body = {
                "expected_version": 99,
                "expected_binding_id": source.exit_binding_id,
                "target_exit_profile_id": target.exit_profile_id,
                "target_exit_profile_semantic_hash": target.semantic_hash(),
                "reason": "test_stale_http_binding",
                "idempotency_key": "owner-request:http-stale-binding",
            }
            missing_totp = await client.post(
                (
                    "/api/owner/v1/controls/strategies/MPG-001/events/"
                    f"{source.event_spec_id}/exit-profile"
                ),
                json=body,
                headers=headers,
            )
            assert missing_totp.status_code == 401

            stale = await client.post(
                (
                    "/api/owner/v1/controls/strategies/MPG-001/events/"
                    f"{source.event_spec_id}/exit-profile"
                ),
                json={
                    **body,
                    "totp_code": pyotp.TOTP(totp_seed).at(now_ms // 1_000),
                },
                headers=headers,
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "control_conflict"

            readonly = await client.get(
                "/api/owner/v1/controls/exit-profiles",
                params={"event_spec_id": source.event_spec_id},
            )
            assert readonly.status_code == 200
            assert len(readonly.json()["profiles"]) == 8
            assert len(readonly.json()["current_bindings"]) == 1
    finally:
        await engine.dispose()
        await _drop(database_name)


class _NoopMarketData:
    async def close(self) -> None:
        return None


async def _seed(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="exit-profile-authority-test",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1_799_999_999_000,
            ),
        )


async def _database() -> tuple[str, AsyncEngine]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin.close()
    base = TEST_POSTGRES_ADMIN_DSN.rsplit("/", 1)[0]
    database_url = (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"
    )
    engine = create_async_engine(database_url)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "-c",
        "migrations/trading_kernel/alembic.ini",
        "upgrade",
        "head",
        cwd=REPO_ROOT,
        env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    return database_name, engine


async def _drop(database_name: str) -> None:
    admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    try:
        with suppress(asyncpg.UndefinedObjectError):
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database_name,
            )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await admin.close()
