from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
    owner_read_transaction,
)
from tests.trading_kernel.integration.owner_console_support import owner_read_dsn

__all__ = ["owner_read_dsn"]


async def test_owner_read_transaction_is_repeatable_read_and_read_only(
    owner_read_dsn: str,
) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            read_only = await connection.scalar(
                sa.text("SHOW transaction_read_only")
            )
            isolation = await connection.scalar(
                sa.text("SHOW transaction_isolation")
            )
            timeout = await connection.scalar(sa.text("SHOW statement_timeout"))
        assert read_only == "on"
        assert isolation == "repeatable read"
        assert timeout == "3s"
    finally:
        await engine.dispose()


async def test_owner_read_role_cannot_insert(owner_read_dsn: str) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        with pytest.raises(DBAPIError):
            async with owner_read_transaction(engine) as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO brc_monitor_current "
                        "(monitor_key, owner_status, summary, intervention, "
                        "updated_at_ms, projection_version) "
                        "VALUES ('forbidden', 'running', 'x', 'x', 1, 1)"
                    )
                )
    finally:
        await engine.dispose()
