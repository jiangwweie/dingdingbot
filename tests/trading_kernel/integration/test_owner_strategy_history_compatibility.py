"""Read-only historical strategy metadata must not require live product authority."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.owner_console.causality import ContradictoryFacts
from src.trading_kernel.application.owner_console.models import StrategySummaryQuery
from src.trading_kernel.application.owner_console.strategies import build_strategy_page
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)


async def seed_missing_event(engine, *, make_current: bool):
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("""
            INSERT INTO brc_strategy_versions
                (strategy_version_id,strategy_group_id,version,semantics,status,created_at_ms)
            SELECT 'sgv:CPM-RO-001:v99',strategy_group_id,99,semantics,'retired',1800000000000
            FROM brc_strategy_versions WHERE strategy_version_id=(
                SELECT active_version_id FROM brc_strategy_groups WHERE strategy_group_id='CPM-RO-001')
        """)
        )
        await connection.execute(
            sa.text("""
            INSERT INTO brc_event_specs
            SELECT 'event_spec:CPM-history-test', 'sgv:CPM-RO-001:v99',event_id,position_side,
                   timeframe,freshness_window_ms,event_time_authority,entry_order_type,
                   protection_reference_fact_definition_id,exit_policy_id,execution_semantics,
                   'retired',1800000000000
            FROM brc_event_specs WHERE strategy_version_id=(
                SELECT active_version_id FROM brc_strategy_groups WHERE strategy_group_id='CPM-RO-001') LIMIT 1
        """)
        )
        if make_current:
            await connection.execute(
                sa.text(
                    "UPDATE brc_strategy_groups SET active_version_id='sgv:CPM-RO-001:v99' WHERE strategy_group_id='CPM-RO-001'"
                )
            )


@pytest.mark.asyncio
async def test_history_missing_product_is_explicit_without_fabrication(
    head_template_engine,
):
    await seed_missing_event(head_template_engine, make_current=False)
    async with head_template_engine.connect() as connection:
        await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
        repository = PostgresOwnerReadRepository(connection)
        page = build_strategy_page(
            await repository.read_strategy_page_facts(
                StrategySummaryQuery(
                    from_ms=1_799_999_000_000, to_ms=1_800_000_100_000, view="all"
                )
            )
        )
        historical = next(
            x for x in page.items if x.strategy_version_id == "sgv:CPM-RO-001:v99"
        )
        assert not historical.is_current
        assert historical.strategy_version_status == "retired"
        assert len(historical.product_events) == 1
        missing = historical.product_events[0]
        assert missing.event_spec_id == "event_spec:CPM-history-test"
        assert missing.product_family is None
        assert (
            missing.product_compatibility_unavailable_reason
            == "historical_product_compatibility_not_recorded"
        )
        assert missing.runtime_profile_id is None and missing.owner_policy_id is None
        assert missing.active_universe_version_id is None
        current = build_strategy_page(
            await repository.read_strategy_page_facts(
                StrategySummaryQuery(
                    from_ms=1_799_999_000_000, to_ms=1_800_000_100_000, view="current"
                )
            )
        )
        assert all(x.strategy_version_id != "sgv:CPM-RO-001:v99" for x in current.items)
        await connection.rollback()


@pytest.mark.asyncio
async def test_current_pointer_missing_product_still_fails_closed(head_template_engine):
    await seed_missing_event(head_template_engine, make_current=True)
    async with head_template_engine.connect() as connection:
        await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
        with pytest.raises(ContradictoryFacts, match="Product Compatibility"):
            await PostgresOwnerReadRepository(connection).read_strategy_page_facts(
                StrategySummaryQuery(
                    from_ms=1_799_999_000_000, to_ms=1_800_000_100_000, view="all"
                )
            )
        await connection.rollback()


@pytest.mark.asyncio
async def test_nonretired_event_on_history_missing_product_still_fails(
    head_template_engine,
):
    await seed_missing_event(head_template_engine, make_current=False)
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_event_specs SET status='active' WHERE event_spec_id='event_spec:CPM-history-test'"
            )
        )
    async with head_template_engine.connect() as connection:
        await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
        with pytest.raises(ContradictoryFacts, match="Product Compatibility"):
            await PostgresOwnerReadRepository(connection).read_strategy_page_facts(
                StrategySummaryQuery(
                    from_ms=1_799_999_000_000, to_ms=1_800_000_100_000, view="all"
                )
            )
        await connection.rollback()
