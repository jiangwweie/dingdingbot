from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.trading_kernel.support.postgres import HeadTemplateCloneHarness


@pytest.mark.asyncio
async def test_head_template_clones_are_database_isolated() -> None:
    harness = HeadTemplateCloneHarness()
    first_name, first_url = await harness.create_clone()
    second_name, second_url = await harness.create_clone()
    first = create_async_engine(first_url)
    second = create_async_engine(second_url)
    try:
        async with first.begin() as connection:
            await connection.execute(
                sa.text("CREATE TABLE harness_isolation_probe (value integer)")
            )
            await connection.execute(
                sa.text("INSERT INTO harness_isolation_probe (value) VALUES (1)")
            )
        async with second.connect() as connection:
            table_exists = await connection.scalar(
                sa.text("SELECT to_regclass('harness_isolation_probe')")
            )
        assert table_exists is None
    finally:
        await first.dispose()
        await second.dispose()
        await harness.drop_clone(first_name)
        await harness.drop_clone(second_name)
