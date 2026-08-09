"""Owner Control API PostgreSQL engine with one bounded write connection."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_owner_control_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "application_name": "brc_owner_control",
                "statement_timeout": "3000",
            }
        },
    )
