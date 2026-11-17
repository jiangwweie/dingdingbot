"""Owner cooperation is an additive stopped/flat, preservation-gated upgrade."""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.manual_same_schema_upgrade import (
    preservation_projection_sql,
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
@pytest.mark.parametrize("enabled", [False, True])
async def test_owner_schema_preserves_source_values_and_rejects_enabled_entry(enabled):
    name, url = await create_empty_database()
    e = create_async_engine(url)
    try:
        async with e.begin() as c:
            await c.execute(
                sa.text(
                    "DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='brc_owner_control') THEN CREATE ROLE brc_owner_control NOLOGIN; END IF; END $$"
                )
            )
        run_alembic(url, "upgrade", "0023_management_recovery")
        async with PostgresKernelUnitOfWork(e) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="owner-migration",
                    runtime_commit="a" * 40,
                    schema_revision="0023_management_recovery",
                    seeded_at_ms=1000,
                ),
            )
        async with e.begin() as c:
            if enabled:
                await c.execute(
                    sa.text(
                        "UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true"
                    )
                )
        async with e.connect() as c:
            names = (
                (
                    await c.execute(
                        sa.text(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename"
                        )
                    )
                )
                .scalars()
                .all()
            )
            columns = {
                n: (
                    await c.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:n ORDER BY ordinal_position"
                        ),
                        {"n": n},
                    )
                )
                .scalars()
                .all()
                for n in names
            }
            before = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in names
            }
        if enabled:
            with pytest.raises(AssertionError, match="0024 requires stopped flat"):
                run_alembic(url, "upgrade", "0024_owner_cooperation")
        else:
            run_alembic(url, "upgrade", "0024_owner_cooperation")
        await e.dispose()
        async with e.connect() as c:
            after = {
                n: (
                    await c.execute(sa.text(preservation_projection_sql(n, columns[n])))
                )
                .scalars()
                .all()
                for n in names
            }
            assert before == after
            assert await c.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            ) == ("0023_management_recovery" if enabled else "0024_owner_cooperation")
            if not enabled:
                for table, column, allowed in [
                    ("brc_owner_device_registrations", "public_key", False),
                    ("brc_owner_device_registrations", "revoked_at_ms", True),
                    ("brc_owner_device_write_evidence", "proof", False),
                    ("brc_owner_device_write_evidence", "signature", False),
                    ("brc_owner_device_write_evidence", "authorization_id", True),
                    ("brc_owner_device_write_evidence", "result_payload", True),
                ]:
                    assert (
                        await c.scalar(
                            sa.text(
                                "SELECT has_column_privilege('brc_owner_control',:table,:column,'UPDATE')"
                            ),
                            {"table": table, "column": column},
                        )
                        is allowed
                    )
                assert not await c.scalar(
                    sa.text(
                        "SELECT has_table_privilege('brc_owner_control','brc_management_receive_epochs','INSERT')"
                    )
                )
                assert not await c.scalar(
                    sa.text(
                        "SELECT has_table_privilege('brc_owner_control','brc_owner_binding_grants','INSERT')"
                    )
                )
                for table in [
                    "brc_owner_device_registrations",
                    "brc_owner_device_sessions",
                    "brc_owner_binding_grants",
                    "brc_owner_request_nonces",
                    "brc_owner_position_operations",
                    "brc_owner_position_operation_events",
                    "brc_owner_device_write_evidence",
                    "brc_owner_binding_limits",
                    "brc_management_receive_epochs",
                ]:
                    assert await c.scalar(sa.text("SELECT count(*) FROM " + table)) == 0
    finally:
        await e.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,target",
    [
        ("0022_wallet_margin_allocation", "0023_management_recovery"),
        ("0023_management_recovery", "0024_owner_cooperation"),
    ],
)
@pytest.mark.parametrize("fault", [None, "source_seed", "wrong_account"])
async def test_migration_then_runtime_identity_transition_preserves_owner_controls(
    source, target, fault
):
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        deploy_compatible_upgrade_identity,
    )

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    original = RuntimeAuthoritySeedRequest(
        account_id="identity-upgrade",
        runtime_commit="a" * 40,
        schema_revision=source,
        seeded_at_ms=1000,
    )
    try:
        run_alembic(url, "upgrade", source)
        async with PostgresKernelUnitOfWork(engine) as u:
            await seed_runtime_authority(u, original)
        async with engine.connect() as c:
            before = {
                table: (
                    await c.execute(
                        sa.text(
                            "SELECT to_jsonb(t) FROM "
                            + table
                            + " t ORDER BY to_jsonb(t)::text"
                        )
                    )
                )
                .scalars()
                .all()
                for table in (
                    "brc_owner_policy_current",
                    "brc_owner_policy_events",
                    "brc_strategy_entry_controls_current",
                    "brc_strategy_entry_control_events",
                )
            }
        if fault == "source_seed":
            async with engine.begin() as c:
                await c.execute(
                    sa.text(
                        "UPDATE brc_schema_metadata SET metadata_value='invalid-source-seed' WHERE metadata_key='seed_identity'"
                    )
                )
        run_alembic(url, "upgrade", target)
        await engine.dispose()
        request = original.model_copy(
            update={
                "schema_revision": target,
                "runtime_commit": "b" * 40,
                "seeded_at_ms": 2000,
                **({"account_id": "wrong-account"} if fault == "wrong_account" else {}),
            }
        )
        if fault is not None:
            from src.trading_kernel.infrastructure.runtime_authority_seed import (
                RuntimeAuthorityTransitionRefused,
            )

            with pytest.raises(
                RuntimeAuthorityTransitionRefused, match="source seed identity differs"
            ):
                async with PostgresKernelUnitOfWork(engine) as u:
                    await deploy_compatible_upgrade_identity(u, request)
            async with engine.connect() as c:
                values = dict(
                    (
                        await c.execute(
                            sa.text(
                                "SELECT metadata_key,metadata_value FROM brc_schema_metadata"
                            )
                        )
                    ).all()
                )
                assert (
                    values["schema_revision"] == source
                    and values["runtime_commit"] == "a" * 40
                )
                assert (
                    await c.execute(
                        sa.text(
                            "SELECT count(*) FROM brc_runtime_capabilities_current WHERE certified_commit=:commit AND schema_revision=:schema"
                        ),
                        {"commit": "a" * 40, "schema": source},
                    )
                ).scalar_one() == 2
            return
        async with PostgresKernelUnitOfWork(engine) as u:
            result = await deploy_compatible_upgrade_identity(u, request)
        assert result.schema_revision == target and result.runtime_commit == "b" * 40
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == target
            )
            after = {
                table: (
                    await c.execute(
                        sa.text(
                            "SELECT to_jsonb(t) FROM "
                            + table
                            + " t ORDER BY to_jsonb(t)::text"
                        )
                    )
                )
                .scalars()
                .all()
                for table in before
            }
            assert after == before
            identity = dict(
                (
                    await c.execute(
                        sa.text(
                            "SELECT metadata_key,metadata_value FROM brc_schema_metadata"
                        )
                    )
                ).all()
            )
            assert (
                identity["runtime_commit"] == "b" * 40
                and identity["schema_revision"] == target
            )
            caps = (
                await c.execute(
                    sa.text(
                        "SELECT certified_commit,schema_revision FROM brc_runtime_capabilities_current"
                    )
                )
            ).all()
            assert len(caps) == 2 and all(r == ("b" * 40, target) for r in caps)
        # The same final identity remains idempotent after migration.
        async with PostgresKernelUnitOfWork(engine) as u:
            assert (
                await deploy_compatible_upgrade_identity(u, request)
            ).runtime_commit == "b" * 40
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
