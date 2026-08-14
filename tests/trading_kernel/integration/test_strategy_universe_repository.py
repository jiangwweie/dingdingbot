from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
    abandon_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    UniverseInstallStatus,
    install_strategy_universe,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (
    PostgresStrategyUniverseRepository,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    TRADFI_RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

CONTRACT = registered_strategy_contracts()[0]
MEMBERS = (
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:SOLUSDT:perpetual",
)


@pytest_asyncio.fixture
async def universe_engine(
    head_template_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-universe-test",
                runtime_commit="task-5-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1_800_000_000_000,
            ),
        )
    yield head_template_engine


@pytest.mark.asyncio
async def test_install_inserts_one_complete_warming_universe_and_reads_sorted(
    universe_engine: AsyncEngine,
) -> None:
    """Catches partial installation, implicit rank, or an unbounded member read."""

    request = _request(tuple(reversed(MEMBERS)))
    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        result = await install_strategy_universe(uow, request)
    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        current = await uow.strategy_universes.get_current(CONTRACT.event_spec_id)
        assert result.universe is not None
        members = await uow.strategy_universes.get_members(
            result.universe.universe_version_id
        )
    async with universe_engine.connect() as connection:
        counts = {
            table_name: int(
                (
                    await connection.execute(
                        sa.text(f"SELECT count(*) FROM {table_name}")
                    )
                ).scalar_one()
            )
            for table_name in (
                "brc_instruments",
                "brc_strategy_universe_versions",
                "brc_strategy_universe_members",
                "brc_runtime_scopes_current",
            )
        }
        instrument_statuses = tuple(
            (
                await connection.execute(
                    sa.text(
                        "SELECT exchange_instrument_id, status "
                        "FROM brc_instruments ORDER BY exchange_instrument_id "
                        "LIMIT 11"
                    )
                )
            ).all()
        )
        scope_permissions = tuple(
            (
                await connection.execute(
                    sa.text(
                        "SELECT exchange_instrument_id, lifecycle_state, "
                        "observation_enabled, entry_enabled "
                        "FROM brc_runtime_scopes_current "
                        "ORDER BY exchange_instrument_id LIMIT 11"
                    )
                )
            ).all()
        )

    assert result.status is UniverseInstallStatus.INSTALLED
    assert result.universe is not None
    assert result.universe.exchange_instrument_ids == MEMBERS
    assert result.lifecycle_state == "warming"
    assert result.inserted_instrument_count == 2
    assert result.inserted_version_count == 1
    assert result.inserted_member_count == 2
    assert result.inserted_scope_count == 2
    assert counts == {
        "brc_instruments": 2,
        "brc_strategy_universe_versions": 1,
        "brc_strategy_universe_members": 2,
        "brc_runtime_scopes_current": 2,
    }
    assert current is None
    assert members == MEMBERS
    assert "rank" not in type(result).model_fields
    assert instrument_statuses == (
        (MEMBERS[0], "pending_certification"),
        (MEMBERS[1], "pending_certification"),
    )
    assert scope_permissions == (
        (MEMBERS[0], "warming", True, False),
        (MEMBERS[1], "warming", True, False),
    )


@pytest.mark.asyncio
async def test_abandon_exact_warming_universe_releases_the_global_slot(
    universe_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        installed = await install_strategy_universe(uow, _request(MEMBERS))
    assert installed.universe is not None

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        await abandon_strategy_universe(
            uow,
            AbandonStrategyUniverseRequest(
                universe_version_id=installed.universe.universe_version_id,
                reason_code="market_identity_conflict",
                attempted_at_ms=1_800_000_000_100,
            ),
        )
    async with universe_engine.connect() as connection:
        version = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state, activated_at_ms, abandoned_at_ms, "
                    "abandon_reason_code FROM brc_strategy_universe_versions"
                )
            )
        ).one()
        scopes = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state, observation_enabled, entry_enabled, "
                    "lease_owner FROM brc_runtime_scopes_current"
                )
            )
        ).all()

    assert version == (
        "abandoned",
        None,
        1_800_000_000_100,
        "market_identity_conflict",
    )
    assert scopes == [("abandoned", False, False, None)] * len(MEMBERS)

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        replacement = await install_strategy_universe(
            uow,
            _request(MEMBERS, installed_at_ms=1_800_000_000_200),
        )
    assert replacement.status is UniverseInstallStatus.INSTALLED
    assert replacement.universe is not None
    assert replacement.universe.universe_version == 2


@pytest.mark.asyncio
async def test_same_warming_or_active_set_is_zero_row_idempotent(
    universe_engine: AsyncEngine,
) -> None:
    """Catches duplicate versions for an already warming or active member set."""

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        first = await install_strategy_universe(uow, _request(MEMBERS))
    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        warming_repeat = await install_strategy_universe(
            uow,
            _request(tuple(reversed(MEMBERS)), installed_at_ms=1_800_000_000_010),
        )
    assert warming_repeat.status is UniverseInstallStatus.ALREADY_WARMING
    assert warming_repeat.universe == first.universe
    assert warming_repeat.total_inserted_count == 0

    assert first.universe is not None
    await _make_active(
        universe_engine,
        universe_version_id=first.universe.universe_version_id,
        semantic_digest=first.universe.semantic_digest,
    )
    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        active_repeat = await install_strategy_universe(
            uow,
            _request(MEMBERS, installed_at_ms=1_800_000_000_020),
        )
        current = await uow.strategy_universes.get_current(CONTRACT.event_spec_id)

    assert active_repeat.status is UniverseInstallStatus.ALREADY_ACTIVE
    assert active_repeat.universe == first.universe
    assert active_repeat.total_inserted_count == 0
    assert current is not None
    assert current.universe_version_id == first.universe.universe_version_id
    assert current.semantic_digest == first.universe.semantic_digest
    assert current.activation_generation == 1


@pytest.mark.asyncio
async def test_retired_same_set_creates_a_new_version_identity(
    universe_engine: AsyncEngine,
) -> None:
    """Catches accidental reactivation of an immutable retired version."""

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        first = await install_strategy_universe(uow, _request(MEMBERS))
    assert first.universe is not None
    await _make_active(
        universe_engine,
        universe_version_id=first.universe.universe_version_id,
        semantic_digest=first.universe.semantic_digest,
    )
    await _retire_active(universe_engine)

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        replacement = await install_strategy_universe(
            uow,
            _request(MEMBERS, installed_at_ms=1_800_000_000_100),
        )

    assert replacement.status is UniverseInstallStatus.INSTALLED
    assert replacement.universe is not None
    assert replacement.universe.universe_version == 2
    assert replacement.universe.universe_version_id != first.universe.universe_version_id
    assert replacement.universe.semantic_digest == first.universe.semantic_digest


@pytest.mark.asyncio
async def test_concurrent_same_set_converges_without_unique_error(
    universe_engine: AsyncEngine,
) -> None:
    """Catches a leaked unique violation from identical concurrent submissions."""

    same_results = await asyncio.gather(
        _install_in_new_uow(universe_engine, _request(MEMBERS)),
        _install_in_new_uow(
            universe_engine,
            _request(tuple(reversed(MEMBERS)), installed_at_ms=1_800_000_000_001),
        ),
    )

    assert {item.status for item in same_results} == {
        UniverseInstallStatus.INSTALLED,
        UniverseInstallStatus.ALREADY_WARMING,
    }
    assert {
        item.universe.universe_version_id
        for item in same_results
        if item.universe is not None
    } == {same_results[0].universe.universe_version_id}


@pytest.mark.asyncio
async def test_concurrent_different_sets_accepts_one_and_returns_stable_conflict(
    universe_engine: AsyncEngine,
) -> None:
    """Catches partial loser rows or hidden queuing of another warming pool."""

    results = await asyncio.gather(
        _install_in_new_uow(universe_engine, _request(MEMBERS)),
        _install_in_new_uow(
            universe_engine,
            _request(
                (
                    "binance-usdm:ETHUSDT:perpetual",
                    "binance-usdm:SUIUSDT:perpetual",
                ),
                installed_at_ms=1_800_000_000_010,
            ),
        ),
    )
    async with universe_engine.connect() as connection:
        counts = (
            await connection.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM brc_strategy_universe_versions), "
                    "(SELECT count(*) FROM brc_strategy_universe_members), "
                    "(SELECT count(*) FROM brc_runtime_scopes_current), "
                    "(SELECT count(*) FROM brc_instruments)"
                )
            )
        ).one()

    assert {item.status for item in results} == {
        UniverseInstallStatus.INSTALLED,
        UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS,
    }
    conflict = next(
        item
        for item in results
        if item.status is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS
    )
    assert conflict.universe is None
    assert conflict.total_inserted_count == 0
    assert tuple(counts) == (1, 2, 2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("table_name", "trigger_name"),
    (
        ("brc_strategy_universe_members", "fail_task5_member"),
        ("brc_runtime_scopes_current", "fail_task5_scope"),
    ),
)
async def test_member_or_scope_insert_failure_rolls_back_every_install_row(
    universe_engine: AsyncEngine,
    table_name: str,
    trigger_name: str,
) -> None:
    """Catches an orphan version, member, scope, or pending instrument."""

    async with universe_engine.begin() as connection:
        await connection.execute(
            sa.text(
                f"""
                CREATE FUNCTION {trigger_name}()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'task 5 injected insert failure';
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE INSERT ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION {trigger_name}()
                """
            )
        )

    with pytest.raises(DBAPIError, match="task 5 injected insert failure"):
        async with PostgresKernelUnitOfWork(universe_engine) as uow:
            await install_strategy_universe(uow, _request(MEMBERS))

    async with universe_engine.connect() as connection:
        counts = tuple(
            int(value)
            for value in (
                await connection.execute(
                    sa.text(
                        "SELECT "
                        "(SELECT count(*) FROM brc_instruments), "
                        "(SELECT count(*) FROM brc_strategy_universe_versions), "
                        "(SELECT count(*) FROM brc_strategy_universe_members), "
                        "(SELECT count(*) FROM brc_runtime_scopes_current)"
                    )
                )
            ).one()
        )
    assert counts == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_conflicting_canonical_instrument_identity_rejects_atomically(
    universe_engine: AsyncEngine,
) -> None:
    """Catches overwriting a canonical identity or retaining earlier inserts."""

    conflicting_id = "binance-usdm:ZZZUSDT:perpetual"
    async with universe_engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO brc_instruments (
                    exchange_instrument_id, venue_id, asset_class,
                    venue_symbol, contract_kind, status
                ) VALUES (
                    :instrument_id, 'binance-usdm', 'crypto',
                    'WRONGUSDT', 'perpetual', 'pending_certification'
                )
                """
            ),
            {"instrument_id": conflicting_id},
        )

    with pytest.raises(
        RuntimeError,
        match="CANONICAL_INSTRUMENT_IDENTITY_CONFLICT",
    ):
        async with PostgresKernelUnitOfWork(universe_engine) as uow:
            await install_strategy_universe(
                uow,
                _request(
                    (
                        "binance-usdm:AAAUSDT:perpetual",
                        conflicting_id,
                    )
                ),
            )

    async with universe_engine.connect() as connection:
        instrument_ids = tuple(
            str(row[0])
            for row in (
                await connection.execute(
                    sa.text(
                        "SELECT exchange_instrument_id FROM brc_instruments "
                        "ORDER BY exchange_instrument_id LIMIT 11"
                    )
                )
            ).all()
        )
        universe_count = int(
            (
                await connection.execute(
                    sa.text("SELECT count(*) FROM brc_strategy_universe_versions")
                )
            ).scalar_one()
        )
    assert instrument_ids == (conflicting_id,)
    assert universe_count == 0


@pytest.mark.asyncio
async def test_crypto_event_rejects_tradfi_equity_product_profile(
    universe_engine: AsyncEngine,
) -> None:
    with pytest.raises(RuntimeError, match="PRODUCT_COMPATIBILITY_MISMATCH"):
        async with PostgresKernelUnitOfWork(universe_engine) as uow:
            await install_strategy_universe(
                uow,
                _request(("binance-usdm:AAPLUSDT:perpetual",)),
            )


@pytest.mark.asyncio
async def test_tradfi_sor_installs_equity_member_only_into_warming_scope(
    universe_engine: AsyncEngine,
) -> None:
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-US-LONG-15M"
    )
    request = UniverseInstallRequest(
        event_spec_id=contract.event_spec_id,
        runtime_profile_id=TRADFI_RUNTIME_PROFILE_ID,
        owner_policy_id=OWNER_POLICY_ID,
        exchange_instrument_ids=("binance-usdm:AAPLUSDT:perpetual",),
        installed_at_ms=1_800_000_000_000,
    )

    async with PostgresKernelUnitOfWork(universe_engine) as uow:
        result = await install_strategy_universe(uow, request)

    assert result.status is UniverseInstallStatus.INSTALLED
    assert result.lifecycle_state == "warming"
    assert result.inserted_instrument_count == 1
    async with universe_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.text(
                    "SELECT i.asset_class, s.observation_enabled, s.entry_enabled "
                    "FROM brc_instruments i JOIN brc_runtime_scopes_current s "
                    "ON s.exchange_instrument_id = i.exchange_instrument_id "
                    "WHERE i.exchange_instrument_id = 'binance-usdm:AAPLUSDT:perpetual'"
                )
            )
        ).one()
    assert tuple(row) == ("equity", True, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_scope",
    (
        {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "allowed_event_spec_ids": CONTRACT.event_spec_id,
        },
        {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "allowed_event_spec_ids": [CONTRACT.event_spec_id],
            "runtime_scope_ids": ["legacy-scope"],
        },
        {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "allowed_event_spec_ids": [
                CONTRACT.event_spec_id,
                CONTRACT.event_spec_id,
            ],
        },
        {
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "allowed_event_spec_ids": [
                registered_strategy_contracts()[1].event_spec_id,
                CONTRACT.event_spec_id,
            ],
        },
    ),
)
async def test_malformed_or_legacy_policy_scope_rejects_install_without_rows(
    universe_engine: AsyncEngine,
    malformed_scope: dict[str, object],
) -> None:
    """Catches substring authorization, legacy keys, duplicates, and order drift."""

    async with universe_engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                UPDATE brc_owner_policy_current
                SET scope = CAST(:scope AS jsonb)
                WHERE owner_policy_id = :owner_policy_id
                """
            ),
            {
                "owner_policy_id": OWNER_POLICY_ID,
                "scope": json.dumps(malformed_scope, sort_keys=True),
            },
        )

    with pytest.raises(RuntimeError, match="OWNER_POLICY_AUTHORITY_CONFLICT"):
        async with PostgresKernelUnitOfWork(universe_engine) as uow:
            await install_strategy_universe(uow, _request(MEMBERS))

    async with universe_engine.connect() as connection:
        counts = tuple(
            int(value)
            for value in (
                await connection.execute(
                    sa.text(
                        "SELECT "
                        "(SELECT count(*) FROM brc_strategy_universe_versions), "
                        "(SELECT count(*) FROM brc_strategy_universe_members), "
                        "(SELECT count(*) FROM brc_runtime_scopes_current)"
                    )
                )
            ).one()
        )
    assert counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_authority_mutation_waits_for_install_snapshot_locks(
    universe_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a Policy update committing after validation but before install."""

    authority_loaded = asyncio.Event()
    allow_install_to_continue = asyncio.Event()
    original_lookup = (
        PostgresStrategyUniverseRepository._get_current_semantic_version
    )

    async def _barrier_after_authority(
        repository: PostgresStrategyUniverseRepository,
        *,
        event_spec_id: str,
        semantic_digest: str,
    ):
        authority_loaded.set()
        await allow_install_to_continue.wait()
        return await original_lookup(
            repository,
            event_spec_id=event_spec_id,
            semantic_digest=semantic_digest,
        )

    monkeypatch.setattr(
        PostgresStrategyUniverseRepository,
        "_get_current_semantic_version",
        _barrier_after_authority,
    )
    install_task = asyncio.create_task(
        _install_in_new_uow(universe_engine, _request(MEMBERS))
    )
    await asyncio.wait_for(authority_loaded.wait(), timeout=2)

    mutation_task = asyncio.create_task(
        _disable_owner_policy(universe_engine)
    )
    try:
        mutation_waited = await _mutation_waited_on_row_lock(
            universe_engine,
            mutation_task,
        )
    finally:
        allow_install_to_continue.set()
    install_result = await asyncio.wait_for(install_task, timeout=2)
    await asyncio.wait_for(mutation_task, timeout=2)

    assert mutation_waited is True
    assert install_result.status is UniverseInstallStatus.INSTALLED
    async with universe_engine.connect() as connection:
        persisted = (
            await connection.execute(
                sa.text(
                    "SELECT "
                    "(SELECT enabled FROM brc_owner_policy_current "
                    " WHERE owner_policy_id = :owner_policy_id), "
                    "(SELECT count(*) FROM brc_strategy_universe_versions), "
                    "(SELECT count(*) FROM brc_strategy_universe_members), "
                    "(SELECT count(*) FROM brc_runtime_scopes_current)"
                ),
                {"owner_policy_id": OWNER_POLICY_ID},
            )
        ).one()
    assert tuple(persisted) == (False, 1, 2, 2)


def _request(
    members: tuple[str, ...],
    *,
    installed_at_ms: int = 1_800_000_000_000,
) -> UniverseInstallRequest:
    return UniverseInstallRequest(
        event_spec_id=CONTRACT.event_spec_id,
        runtime_profile_id=RUNTIME_PROFILE_ID,
        owner_policy_id=OWNER_POLICY_ID,
        exchange_instrument_ids=members,
        installed_at_ms=installed_at_ms,
    )


async def _install_in_new_uow(
    engine: AsyncEngine,
    request: UniverseInstallRequest,
):
    async with PostgresKernelUnitOfWork(engine) as uow:
        return await install_strategy_universe(uow, request)


async def _disable_owner_policy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                UPDATE /* task5-authority-mutation */
                    brc_owner_policy_current
                SET enabled = false
                WHERE owner_policy_id = :owner_policy_id
                """
            ),
            {"owner_policy_id": OWNER_POLICY_ID},
        )


async def _mutation_waited_on_row_lock(
    engine: AsyncEngine,
    mutation_task: asyncio.Task[None],
) -> bool:
    for _ in range(200):
        if mutation_task.done():
            await mutation_task
            return False
        async with engine.connect() as connection:
            waiting = bool(
                (
                    await connection.execute(
                        sa.text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_stat_activity
                                WHERE datname = current_database()
                                  AND state = 'active'
                                  AND wait_event_type = 'Lock'
                                  AND query LIKE
                                      '%UPDATE /* task5-authority-mutation */%'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )
        if waiting:
            return True
        await asyncio.sleep(0.01)
    raise AssertionError("authority mutation neither committed nor waited on a lock")


async def _make_active(
    engine: AsyncEngine,
    *,
    universe_version_id: str,
    semantic_digest: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                UPDATE brc_runtime_scopes_current
                SET lifecycle_state = 'active',
                    observation_enabled = true,
                    entry_enabled = true,
                    warm_closed_bar_time_ms = 1800000000010,
                    warm_completed_at_ms = 1800000000010,
                    warm_readiness_digest = :digest,
                    warm_valid_until_ms = 1800000060010,
                    updated_at_ms = 1800000000010
                WHERE universe_version_id = :universe_version_id
                """
            ),
            {
                "universe_version_id": universe_version_id,
                "digest": semantic_digest,
            },
        )
        await connection.execute(
            sa.text(
                """
                UPDATE brc_strategy_universe_versions
                SET lifecycle_state = 'active',
                    activated_at_ms = 1800000000010
                WHERE universe_version_id = :universe_version_id
                """
            ),
            {"universe_version_id": universe_version_id},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO brc_strategy_universe_current (
                    event_spec_id, universe_version_id, semantic_digest,
                    activation_generation, activated_at_ms
                ) VALUES (
                    :event_spec_id, :universe_version_id, :digest,
                    1, 1800000000010
                )
                """
            ),
            {
                "event_spec_id": CONTRACT.event_spec_id,
                "universe_version_id": universe_version_id,
                "digest": semantic_digest,
            },
        )


async def _retire_active(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                DELETE FROM brc_strategy_universe_current
                WHERE event_spec_id = :event_spec_id
                """
            ),
            {"event_spec_id": CONTRACT.event_spec_id},
        )
        await connection.execute(
            sa.text(
                """
                UPDATE brc_runtime_scopes_current
                SET lifecycle_state = 'retired',
                    observation_enabled = false,
                    entry_enabled = false,
                    updated_at_ms = 1800000000020
                WHERE event_spec_id = :event_spec_id
                """
            ),
            {"event_spec_id": CONTRACT.event_spec_id},
        )
        await connection.execute(
            sa.text(
                """
                UPDATE brc_strategy_universe_versions
                SET lifecycle_state = 'retired',
                    retired_at_ms = 1800000000020
                WHERE event_spec_id = :event_spec_id
                """
            ),
            {"event_spec_id": CONTRACT.event_spec_id},
        )
