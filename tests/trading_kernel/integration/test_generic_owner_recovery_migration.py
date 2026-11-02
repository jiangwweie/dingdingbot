"""0015 changes recovery predicates only, preserving exact 0014 runtime rows."""

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.verify_schema import (
    _generic_owner_recovery_preservation_manifest,
)
from src.trading_kernel.domain.risk_budget import RiskBudgetChangeRequest
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
async def test_generic_owner_recovery_migration_preserves_all_rows_and_owner_budget():
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(
            run_alembic, url, "upgrade", "0014_dynamic_risk_budget_v1"
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="test",
                    runtime_commit="a" * 40,
                    schema_revision="0014_dynamic_risk_budget_v1",
                    seeded_at_ms=1000,
                ),
            )
            policy = (
                await uow._connection.execute(
                    sa.text(
                        "SELECT owner_policy_id,policy_version FROM brc_owner_policy_current"
                    )
                )
            ).one()
            direction = await uow.directional_risk.get("binance-usdm", "test")
            result = await uow.directional_risk.request_budget_change(
                RiskBudgetChangeRequest(
                    venue_id="binance-usdm",
                    account_id="test",
                    owner_policy_id=policy.owner_policy_id,
                    expected_policy_version=policy.policy_version,
                    expected_directional_version=direction.version,
                    baseline=Decimal(".03"),
                    owner_identity="owner",
                    reason="Owner selected baseline",
                    idempotency_key="migration-budget",
                    requested_at_ms=2000,
                )
            )
            assert result.status == "effective"
        async with engine.connect() as c:
            before = await _generic_owner_recovery_preservation_manifest(c)
            assert before["row_count"] > 0
        await asyncio.to_thread(run_alembic, url, "upgrade", "head")
        async with engine.connect() as c:
            after = await _generic_owner_recovery_preservation_manifest(c)
            assert before == after
            row = (
                await c.execute(
                    sa.text(
                        "SELECT max_ticket_stop_risk_fraction,max_gross_stop_risk_fraction,"
                        "directional_stop_risk_limit_fraction,min_materialization_ratio,new_entry_submit_enabled "
                        "FROM brc_owner_policy_current"
                    )
                )
            ).one()
            assert tuple(row) == (
                Decimal(".03"),
                Decimal(".09"),
                Decimal(".06"),
                Decimal(".50"),
                False,
            )
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
