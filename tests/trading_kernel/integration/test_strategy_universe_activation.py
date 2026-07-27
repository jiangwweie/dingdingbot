from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.activate_strategy_universe import (
    ActivateStrategyUniverseRequest,
    activate_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    InstallStrategyUniverseRequest,
    install_strategy_universe,
)
from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    universe_for_event_spec,
)
from src.trading_kernel.infrastructure.pg_models import (
    runtime_scopes_current,
    scope_warm_readiness,
    strategy_universe_activations,
    strategy_universe_current,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (
    seed_strategy_universes,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


EVENT_SPEC_ID = "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"


@pytest.mark.asyncio
async def test_activation_refuses_until_every_candidate_scope_is_warm(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = await _seed_warming_scopes(registry_engine)
    request = ActivateStrategyUniverseRequest(
        event_spec_id=EVENT_SPEC_ID,
        universe_version_id=universe.universe_version_id,
        activated_at_ms=1_800_000_100_000,
    )

    with pytest.raises(ValueError, match="all candidate scopes to be warm"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await activate_strategy_universe(uow, request)

    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == universe.universe_version_id
            )
            .values(warm_ready_at_ms=1_800_000_099_000)
        )
        await _insert_warm_readiness(
            connection,
            universe_version_id=universe.universe_version_id,
            ready_at_ms=1_800_000_099_000,
        )

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        result = await activate_strategy_universe(uow, request)

    assert result.activation_generation == 1
    assert result.activated_scope_count == 13
    assert result.old_universe_version_id is None
    async with registry_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(strategy_universe_current).where(
                    strategy_universe_current.c.event_spec_id == EVENT_SPEC_ID
                )
            )
        ).mappings().one()
        assert current["universe_version_id"] == universe.universe_version_id
        scopes = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.universe_version_id
                    == universe.universe_version_id
                )
            )
        ).mappings().all()
        assert len(scopes) == 13
        assert all(bool(row["observation_enabled"]) for row in scopes)
        assert all(bool(row["entry_enabled"]) for row in scopes)
        assert {str(row["scope_state"]) for row in scopes} == {"active"}
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(
                strategy_universe_activations
            )
        ) == 7


@pytest.mark.asyncio
async def test_activation_replay_is_idempotent(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = await _seed_warming_scopes(registry_engine, ready=True)
    request = ActivateStrategyUniverseRequest(
        event_spec_id=EVENT_SPEC_ID,
        universe_version_id=universe.universe_version_id,
        activated_at_ms=1_800_000_100_000,
    )

    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await activate_strategy_universe(uow, request)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await activate_strategy_universe(
            uow,
            request.model_copy(update={"activated_at_ms": 1_800_000_100_001}),
        )

    assert second == first
    async with registry_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count())
            .select_from(strategy_universe_activations)
            .where(
                strategy_universe_activations.c.event_spec_id == EVENT_SPEC_ID
            )
        ) == 1
        assert await connection.scalar(
            sa.select(strategy_universe_versions.c.lifecycle_state).where(
                strategy_universe_versions.c.universe_version_id
                == universe.universe_version_id
            )
        ) == "active"


@pytest.mark.asyncio
async def test_concurrent_replacements_allow_only_one_expected_current_winner(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    initial = await _seed_warming_scopes(registry_engine, ready=True)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await activate_strategy_universe(
            uow,
            ActivateStrategyUniverseRequest(
                event_spec_id=EVENT_SPEC_ID,
                universe_version_id=initial.universe_version_id,
                expected_current_universe_version_id=None,
                activated_at_ms=1_800_000_100_000,
            ),
        )

    replacements = (
        _replacement_version(initial, version=2),
        _replacement_version(initial, version=3),
    )
    for replacement in replacements:
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await install_strategy_universe(
                uow,
                InstallStrategyUniverseRequest(
                    universe=replacement,
                    position_side="long",
                    installed_at_ms=1_800_000_110_000,
                ),
            )
        await _insert_replacement_scopes(
            registry_engine,
            replacement,
            ready_at_ms=1_800_000_119_000,
        )
        async with registry_engine.connect() as connection:
            replacement_scope_count = await connection.scalar(
                sa.select(sa.func.count())
                .select_from(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == replacement.universe_version_id,
                    runtime_scopes_current.c.scope_state == "warming",
                    runtime_scopes_current.c.entry_enabled.is_(False),
                )
            )
        assert replacement_scope_count == 13

    async def activate(replacement: StrategyUniverseVersion):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            return await activate_strategy_universe(
                uow,
                ActivateStrategyUniverseRequest(
                    event_spec_id=EVENT_SPEC_ID,
                    universe_version_id=replacement.universe_version_id,
                    expected_current_universe_version_id=(
                        initial.universe_version_id
                    ),
                    activated_at_ms=1_800_000_120_000,
                ),
            )

    results = await asyncio.gather(
        *(activate(replacement) for replacement in replacements),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, BaseException) for result in results) == 1
    failures = [
        result for result in results if isinstance(result, BaseException)
    ]
    assert len(failures) == 1
    assert "current Universe changed before activation" in str(failures[0])
    async with registry_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(strategy_universe_current).where(
                    strategy_universe_current.c.event_spec_id == EVENT_SPEC_ID
                )
            )
        ).mappings().one()
        assert int(current["activation_generation"]) == 2
        assert str(current["universe_version_id"]) in {
            replacement.universe_version_id for replacement in replacements
        }
        assert await connection.scalar(
            sa.select(sa.func.count())
            .select_from(strategy_universe_activations)
            .where(
                strategy_universe_activations.c.event_spec_id == EVENT_SPEC_ID
            )
        ) == 2


async def _seed_warming_scopes(
    engine: AsyncEngine,
    *,
    ready: bool = False,
):
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)
    rows = [
        {
            "runtime_scope_id": f"scope:{universe.event_id}:{member.venue_symbol}:long",
            "strategy_group_id": universe.strategy_group_id,
            "strategy_version_id": "sgv:RSRVCB-001:v1",
            "event_spec_id": universe.event_spec_id,
            "runtime_profile_id": "tiny-live-v1",
            "owner_policy_id": "policy-main",
            "exchange_instrument_id": member.exchange_instrument_id,
            "position_side": "long",
            "enabled": True,
            "universe_version_id": universe.universe_version_id,
            "observation_enabled": True,
            "entry_enabled": False,
            "scope_state": "warming",
            "warm_ready_at_ms": 1_800_000_099_000 if ready else None,
            "scope_version": 1,
            "observation_due_at_ms": 1_800_000_000_000,
            "observation_lease_until_ms": None,
            "observation_claim_owner": None,
            "updated_at_ms": 1_800_000_000_000,
        }
        for member in universe.candidate_members
    ]
    async with engine.begin() as connection:
        await connection.execute(sa.insert(runtime_scopes_current), rows)
        if ready:
            await _insert_warm_readiness(
                connection,
                universe_version_id=universe.universe_version_id,
                ready_at_ms=1_800_000_099_000,
            )
    return universe


def _replacement_version(
    universe: StrategyUniverseVersion,
    *,
    version: int,
) -> StrategyUniverseVersion:
    payload = universe.model_dump(mode="python")
    payload.update(
        {
            "universe_version_id": (
                f"universe:{universe.event_spec_id}:v{version}"
            ),
            "universe_version": version,
        }
    )
    return StrategyUniverseVersion.model_validate(payload)


async def _insert_replacement_scopes(
    engine: AsyncEngine,
    universe: StrategyUniverseVersion,
    *,
    ready_at_ms: int,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == universe.universe_version_id
            )
            .values(
                warm_ready_at_ms=ready_at_ms,
                updated_at_ms=ready_at_ms,
            )
        )
        await _insert_warm_readiness(
            connection,
            universe_version_id=universe.universe_version_id,
            ready_at_ms=ready_at_ms,
        )


async def _insert_warm_readiness(
    connection,
    *,
    universe_version_id: str,
    ready_at_ms: int,
) -> None:
    scope_ids = (
        await connection.execute(
            sa.select(runtime_scopes_current.c.runtime_scope_id).where(
                runtime_scopes_current.c.universe_version_id
                == universe_version_id
            )
        )
    ).scalars().all()
    await connection.execute(
        sa.insert(scope_warm_readiness),
        [
            {
                "runtime_scope_id": runtime_scope_id,
                "universe_version_id": universe_version_id,
                "observation_fact_digest": "sha256:" + "1" * 64,
                "product_profile_id": "profile:warm-test",
                "product_profile_digest": "sha256:" + "2" * 64,
                "projection_run_id": "projection:warm-test",
                "readiness_digest": "sha256:" + "3" * 64,
                "ready_at_ms": ready_at_ms,
            }
            for runtime_scope_id in scope_ids
        ],
    )
