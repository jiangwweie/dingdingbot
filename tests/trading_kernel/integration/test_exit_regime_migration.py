import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _exit_regime_source_preservation_manifest,
    _verify_preservation,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_exact_0015_source_rows_preserved_and_installation_keeps_filters_disabled():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(
            run_alembic, url, "upgrade", "0015_generic_owner_recovery_v1"
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="migration",
                    runtime_commit="a" * 40,
                    schema_revision="0015_generic_owner_recovery_v1",
                    seeded_at_ms=1000,
                ),
            )
        from src.trading_kernel.application.owner_control import (
            ExitProfileBindingMutationRequest,
            switch_event_exit_profile,
        )
        from src.trading_kernel.domain.exit_policy import (
            registered_event_exit_bindings,
            registered_exit_profiles,
        )

        source = next(
            b
            for b in registered_event_exit_bindings()
            if "CPM-RO-001" in b.event_spec_id
        )
        target = next(
            p
            for p in registered_exit_profiles()
            if "impulse-decay" in p.exit_profile_id
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            owner_binding = await switch_event_exit_profile(
                uow,
                strategy_group_id="CPM-RO-001",
                event_spec_id=source.event_spec_id,
                request=ExitProfileBindingMutationRequest(
                    expected_version=1,
                    expected_binding_id=source.exit_binding_id,
                    target_exit_profile_id=target.exit_profile_id,
                    target_exit_profile_semantic_hash=target.semantic_hash(),
                    reason="preexisting_owner_choice",
                    idempotency_key="migration-profile-switch",
                    owner_identity="owner",
                    now_ms=1500,
                ),
                authentication_strength="totp_step_up",
            )
        async with engine.connect() as c:
            before = await _exit_regime_source_preservation_manifest(c)
            assert before["row_count"] > 0 and before["table_count"] == 90
        await asyncio.to_thread(run_alembic, url, "upgrade", "head")
        async with engine.connect() as c:
            assert before == await _exit_regime_source_preservation_manifest(c)
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_entry_regime_current"))
                == 3
            )
            assert (
                await c.scalar(
                    sa.text(
                        "SELECT count(*) FROM brc_entry_regime_revisions WHERE enabled"
                    )
                )
                == 0
            )
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_btc_ma50_current"))
                == 0
            )
            assert (
                await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))
                == 0
            )
        verification = await _verify_preservation(
            url,
            source_revision="0015_generic_owner_recovery_v1",
            expected_digest=before["digest"],
        )
        assert verification["status"] == "pass", verification
        from src.trading_kernel.infrastructure.runtime_authority_seed import (
            deploy_compatible_upgrade_identity,
        )
        from src.trading_kernel.infrastructure.runtime_identity import (
            CURRENT_SCHEMA_REVISION,
        )

        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_compatible_upgrade_identity(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="migration",
                    runtime_commit="b" * 40,
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=2000,
                ),
            )
            assert (
                await uow.exit_profiles.get_current_binding(source.event_spec_id)
                == owner_binding
            )

    finally:
        await engine.dispose()
        await drop_disposable_database(name)
