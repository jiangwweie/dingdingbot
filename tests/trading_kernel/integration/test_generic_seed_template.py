from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.parametrize("excluded", [None,"CPM-RO-001","MPG-001","MI-001","BRF2-001"])
async def test_seeded_clones_equal_fresh_setup_and_remain_isolated(excluded: str | None) -> None:
    from tests.trading_kernel.support.generic_seed_template import (
        GenericSeedTemplateHarness,
        seed_generic_database,
    )
    from tests.trading_kernel.support.postgres import HeadTemplateCloneHarness

    fresh_harness=HeadTemplateCloneHarness()
    fast_harness=GenericSeedTemplateHarness(excluded_group=excluded)
    fresh_name,fresh_url=await fresh_harness.create_clone()
    fast_name,fast_url=await fast_harness.create_clone()
    fresh=create_async_engine(fresh_url)
    fast=create_async_engine(fast_url)
    third=None
    try:
        await seed_generic_database(fresh,excluded_group=excluded)
        async with fresh.connect() as conn:
            expected=await _all_current_rows_digest(conn)
        async with fast.connect() as conn:
            actual=await _all_current_rows_digest(conn)
            assert actual == expected
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_specs WHERE selection_kind='generic_dynamic_v1'")) == (4 if excluded is None else 3)
        async with fast.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true"))
        third_name,third_url=await fast_harness.create_clone()
        third=create_async_engine(third_url)
        async with third.connect() as conn:
            assert await conn.scalar(sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")) is False
            assert await _all_current_rows_digest(conn) == expected
    finally:
        await fresh.dispose(); await fast.dispose()
        await fresh_harness.drop_clone(fresh_name); await fast_harness.drop_clone(fast_name)
        if third is not None:
            await third.dispose(); await fast_harness.drop_clone(third_name)


async def _all_current_rows_digest(connection) -> str:
    from scripts.trading_kernel.verify_schema import _row_manifest, _sha256_json
    from src.trading_kernel.infrastructure.pg_models import metadata
    tables = {}
    for table in sorted(metadata.tables.values(), key=lambda row: row.name):
        rows = (await connection.execute(sa.select(table))).mappings().all()
        tables[table.name] = sorted(_row_manifest(tuple(table.c.keys()),dict(row))["digest"] for row in rows)
    return _sha256_json(tables)
