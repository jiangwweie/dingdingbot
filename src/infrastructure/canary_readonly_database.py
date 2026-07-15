"""Privilege-reduced PostgreSQL access for the loopback deployment canary."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from typing import Any, AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


CANARY_ROLE = "pg_read_all_data"
RUNTIME_TABLE = "strategy_runtime_instances"


def _async_dsn(value: str) -> str:
    dsn = value.strip()
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + dsn.split("://", 1)[1]
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn.split("://", 1)[1]
    raise ValueError("canary_requires_postgresql_database_url")


class CanaryReadonlyDatabase:
    """Owns a dedicated NullPool engine and never falls back to global state."""

    def __init__(self, database_url: str | None = None) -> None:
        resolved = str(database_url or os.getenv("PG_DATABASE_URL") or "").strip()
        if not resolved:
            raise ValueError("canary_requires_postgresql_database_url")
        self._engine: AsyncEngine = create_async_engine(
            _async_dsn(resolved),
            poolclass=NullPool,
            connect_args={"command_timeout": 15},
        )

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        async with self._engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET LOCAL ROLE pg_read_all_data"))
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await self._verify(conn)
                yield conn

    async def _verify(self, conn: AsyncConnection) -> dict[str, Any]:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT current_user AS current_user,
                           current_setting('transaction_read_only') AS transaction_read_only,
                           has_table_privilege(current_user, :table_name, 'SELECT') AS can_select,
                           has_table_privilege(current_user, :table_name, 'INSERT') AS can_insert,
                           has_table_privilege(current_user, :table_name, 'UPDATE') AS can_update,
                           has_table_privilege(current_user, :table_name, 'DELETE') AS can_delete,
                           has_table_privilege(current_user, :table_name, 'TRUNCATE') AS can_truncate
                    """
                ),
                {"table_name": RUNTIME_TABLE},
            )
        ).mappings().one()
        if (
            row["current_user"] != CANARY_ROLE
            or row["transaction_read_only"] != "on"
            or row["can_select"] is not True
            or any(
                row[key] is not False
                for key in (
                    "can_insert",
                    "can_update",
                    "can_delete",
                    "can_truncate",
                )
            )
        ):
            raise RuntimeError("canary_readonly_privilege_verification_failed")
        return dict(row)

    async def verify_startup(self) -> dict[str, Any]:
        async with self.connection() as conn:
            return await self._verify(conn)

    async def close(self) -> None:
        await self._engine.dispose()

