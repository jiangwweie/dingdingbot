"""Bounded read-only PostgreSQL access for Owner Console read models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)


def create_owner_read_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=1,
        max_overflow=1,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "application_name": "brc_owner_console",
                "default_transaction_read_only": "on",
                "statement_timeout": "3000",
            }
        },
    )


@asynccontextmanager
async def owner_read_transaction(
    engine: AsyncEngine,
) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as raw:
        connection = await raw.execution_options(
            isolation_level="REPEATABLE READ"
        )
        transaction = await connection.begin()
        try:
            await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            yield connection
            await transaction.commit()
        except BaseException:
            await transaction.rollback()
            raise


class PostgresOwnerReadRepository:
    __slots__ = ("_connection",)

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
