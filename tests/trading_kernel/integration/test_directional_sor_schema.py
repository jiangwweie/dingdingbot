"""Directional hourly ORB keeps strict PostgreSQL identity validation."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_GROUPS,
    OrbSessionSelectionSpec,
    directional_orb_spec,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)

SOURCE = "0024_owner_cooperation"
TARGET = "0025_directional_sor"
NOW = 1_800_000_000_000


@pytest.mark.asyncio
async def test_stopped_upgrade_preserves_legacy_and_accepts_only_exact_directional_specs():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    legacy = OrbSessionSelectionSpec()
    long, short = map(directional_orb_spec, ORB_DIRECTIONAL_GROUPS)
    try:
        run_alembic(url, "upgrade", SOURCE)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_strategy_registry(
                uow,
                seeded_at_ms=NOW,
                contracts=registered_strategy_contracts(),
            )
            await uow.instrument_selection.install_orb_spec(legacy, installed_at_ms=NOW)
        async with engine.connect() as connection:
            original = (
                (
                    await connection.execute(
                        sa.text(
                            "SELECT to_jsonb(t) FROM brc_orb_session_selection_specs_v1 t ORDER BY selection_spec_id"
                        )
                    )
                )
                .scalars()
                .all()
            )
        run_alembic(url, "upgrade", TARGET)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_strategy_registry(
                uow,
                seeded_at_ms=NOW + 1,
                contracts=registered_strategy_contracts(include_sor_split=True),
                compatible_source_registry_semantic_hash=build_registry_semantic_hash(
                    registered_strategy_contracts()
                ),
                preserve_existing_exit_authority=True,
            )
            await uow.instrument_selection.install_orb_spec(
                long, installed_at_ms=NOW + 1
            )
            await uow.instrument_selection.install_orb_spec(
                short, installed_at_ms=NOW + 1
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            for spec in (legacy, long, short):
                assert (
                    await uow.instrument_selection.get_orb_spec(spec.selection_spec_id)
                    == spec
                )
        async with engine.connect() as connection:
            assert (
                await connection.execute(
                    sa.text(
                        "SELECT to_jsonb(t) FROM brc_orb_session_selection_specs_v1 t WHERE selection_spec_id=:sid"
                    ),
                    {"sid": legacy.selection_spec_id},
                )
            ).scalars().all() == original
        with pytest.raises(DBAPIError, match="immutable Selection fact"):
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "UPDATE brc_instrument_selection_specs SET algorithm_semantic_digest=:bad "
                        "WHERE selection_spec_id=:sid"
                    ),
                    {"sid": short.selection_spec_id, "bad": "sha256:" + "f" * 64},
                )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_directional_snapshot_keeps_same_clock_without_sharing_member_rows():
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        build_orb_session_period,
        compute_orb_selection,
    )

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    session = NOW // 86_400_000 * 86_400_000
    period = build_orb_session_period(session)
    cutoff = period.feature_cutoff_at_ms
    long, short = map(directional_orb_spec, ORB_DIRECTIONAL_GROUPS)
    members = tuple(
        SelectionSourceWindow(
            exchange_instrument_id=member,
            input_window_start_ms=cutoff - 86_400_000,
            feature_cutoff_at_ms=cutoff,
            klines=tuple(
                SelectionKline(
                    open_time_ms=cutoff - 86_400_000 + index * 900_000,
                    close_time_ms=cutoff - 86_400_000 + (index + 1) * 900_000,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(101),
                    low=Decimal(99),
                    quote_volume=Decimal(1_000_000),
                )
                for index in range(96)
            ),
        )
        for member in long.candidate_ids
    )
    try:
        run_alembic(url, "upgrade", TARGET)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_strategy_registry(
                uow,
                seeded_at_ms=session - 1,
                contracts=registered_strategy_contracts(include_sor_split=True),
            )
            for spec in (long, short):
                await uow.instrument_selection.install_orb_spec(
                    spec, installed_at_ms=session
                )
        snapshots = [
            compute_orb_selection(
                spec=spec,
                period=period,
                selection_epoch_id="epoch:directional",
                source_windows=members,
                decision_at_ms=cutoff,
                source_observed_at_ms=cutoff + 1,
                created_at_ms=cutoff + 2,
            )
            for spec in (long, short)
        ]
        async with PostgresKernelUnitOfWork(engine) as uow:
            for computation in snapshots:
                await uow.instrument_selection.save_orb_snapshot(computation)
        async with PostgresKernelUnitOfWork(engine) as uow:
            for expected in snapshots:
                actual = await uow.instrument_selection.get_orb_snapshot(
                    expected.snapshot.selection_snapshot_id
                )
                assert actual == expected
        first, second = snapshots
        assert (
            first.snapshot.selection_snapshot_id
            != second.snapshot.selection_snapshot_id
        )
        assert first.snapshot.selected_count == second.snapshot.selected_count == 7
        assert tuple(
            (row.exchange_instrument_id, row.selected) for row in first.member_decisions
        ) == tuple(
            (row.exchange_instrument_id, row.selected)
            for row in second.member_decisions
        )
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM brc_instrument_selection_member_decisions"
                    )
                )
                == 48
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_stopped_directional_cutover_transfers_only_exact_hourly_entry_scope():
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        OwnerControlBlocked,
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_DIRECTIONAL_EVENTS,
        ORB_EVENT_SPEC_IDS,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_compatible_upgrade_identity,
        seed_runtime_authority,
    )

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    source = RuntimeAuthoritySeedRequest(
        account_id="manual-sor-cutover-fixture",
        runtime_commit="a" * 40,
        schema_revision=SOURCE,
        seeded_at_ms=NOW,
    )
    request = source.model_copy(
        update={
            "runtime_commit": "b" * 40,
            "schema_revision": TARGET,
            "seeded_at_ms": NOW + 1,
        }
    )
    try:
        run_alembic(url, "upgrade", SOURCE)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, source)
            await uow.instrument_selection.install_orb_spec(
                OrbSessionSelectionSpec(), installed_at_ms=NOW
            )
        async with engine.connect() as connection:
            old = await connection.scalar(
                sa.text("SELECT to_jsonb(p) FROM brc_owner_policy_current p")
            )
        run_alembic(url, "upgrade", TARGET)
        async with PostgresKernelUnitOfWork(engine) as uow:
            assert (
                await deploy_compatible_upgrade_identity(uow, request)
            ).schema_revision == TARGET
        async with engine.connect() as connection:
            current = await connection.scalar(
                sa.text("SELECT to_jsonb(p) FROM brc_owner_policy_current p")
            )
            assert current["new_entry_submit_enabled"] is False
            expected_ids = {
                row["event_spec_id"] for row in old["scope"]["event_runtime_profiles"]
            }
            expected_ids = (expected_ids - set(ORB_EVENT_SPEC_IDS)) | set(
                ORB_DIRECTIONAL_EVENTS
            )
            assert {
                row["event_spec_id"]
                for row in current["scope"]["event_runtime_profiles"]
            } == expected_ids
            changed = {key for key in current if current[key] != old[key]}
            assert changed == {"scope", "updated_at_ms", "policy_version"}
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT status FROM brc_strategy_groups WHERE strategy_group_id='SOR-1H-001'"
                    )
                )
                == "disabled"
            )
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM brc_strategy_entry_controls_current "
                        "WHERE strategy_group_id IN ('SOR-1H-LONG-001','SOR-1H-SHORT-001') AND entry_state='paused'"
                    )
                )
                == 2
            )
            assert (
                await connection.scalar(
                    sa.text("SELECT count(*) FROM brc_exchange_commands")
                )
                == 0
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            long, short = ORB_DIRECTIONAL_GROUPS
            for version, state in enumerate(
                (StrategyEntryState.ENABLED, StrategyEntryState.PAUSED, StrategyEntryState.ENABLED), start=1
            ):
                effect = await set_strategy_entry_state(
                    uow, strategy_group_id=long, target_state=state,
                    request=ControlMutationRequest(expected_version=version, reason="fixture Owner control",
                        idempotency_key=f"fixture:directional:{version}", owner_identity="fixture-owner",
                        now_ms=NOW+1+version), authentication_strength="totp_step_up",
                )
                assert effect.control_version == version + 1
                opposite = await uow.owner_controls.get_strategy_control(short)
                assert opposite is not None and opposite.entry_state is StrategyEntryState.PAUSED
                assert await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=long, selection_spec_id=directional_orb_spec(long).selection_spec_id
                ) is None
            with pytest.raises(OwnerControlBlocked, match="strategy_group_not_active"):
                await set_strategy_entry_state(
                    uow, strategy_group_id="SOR-1H-001", target_state=StrategyEntryState.ENABLED,
                    request=ControlMutationRequest(expected_version=1, reason="fixture retired check",
                        idempotency_key="fixture:retired", owner_identity="fixture-owner", now_ms=NOW+6),
                    authentication_strength="totp_step_up",
                )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
