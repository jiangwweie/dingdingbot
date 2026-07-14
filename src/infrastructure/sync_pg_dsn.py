"""Helpers for synchronous SQLAlchemy PostgreSQL connection URLs."""

from __future__ import annotations


ASYNC_PG_DSN_PREFIX = "postgresql+asyncpg://"
BARE_PG_DSN_PREFIX = "postgresql://"
SYNC_PG_DSN_PREFIX = "postgresql+psycopg://"
POSTGRES_DRIVER_PREFIX = "postgresql+"


def normalize_sync_postgres_dsn(database_url: str) -> str:
    """Return a PostgreSQL DSN usable by SQLAlchemy's synchronous engine."""

    url = str(database_url or "").strip()
    if url.startswith(ASYNC_PG_DSN_PREFIX):
        return SYNC_PG_DSN_PREFIX + url[len(ASYNC_PG_DSN_PREFIX) :]
    if url.startswith(BARE_PG_DSN_PREFIX):
        return SYNC_PG_DSN_PREFIX + url[len(BARE_PG_DSN_PREFIX) :]
    return url


def normalize_libpq_postgres_dsn(database_url: str) -> str:
    """Return a libpq-compatible PostgreSQL URL for tools such as pg_dump."""

    url = str(database_url or "").strip()
    if url.startswith(ASYNC_PG_DSN_PREFIX):
        return BARE_PG_DSN_PREFIX + url[len(ASYNC_PG_DSN_PREFIX) :]
    if url.startswith(SYNC_PG_DSN_PREFIX):
        return BARE_PG_DSN_PREFIX + url[len(SYNC_PG_DSN_PREFIX) :]
    return url


def is_sync_postgres_dsn(database_url: str) -> bool:
    """Return True when the URL can be opened by a synchronous PG engine."""

    return normalize_sync_postgres_dsn(database_url).startswith(SYNC_PG_DSN_PREFIX)
