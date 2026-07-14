from src.infrastructure.sync_pg_dsn import (
    is_sync_postgres_dsn,
    normalize_libpq_postgres_dsn,
    normalize_sync_postgres_dsn,
)


def test_normalize_sync_postgres_dsn_converts_asyncpg_and_bare_pg():
    assert normalize_sync_postgres_dsn(
        "postgresql+asyncpg://user:pass@localhost:5432/brc"
    ) == "postgresql+psycopg://user:pass@localhost:5432/brc"
    assert normalize_sync_postgres_dsn(
        "postgresql://user:pass@localhost:5432/brc"
    ) == "postgresql+psycopg://user:pass@localhost:5432/brc"
    assert normalize_sync_postgres_dsn(
        "postgresql+psycopg://user:pass@localhost:5432/brc"
    ) == "postgresql+psycopg://user:pass@localhost:5432/brc"


def test_sync_postgres_dsn_rejects_non_pg_after_normalization():
    assert is_sync_postgres_dsn("postgresql+asyncpg://user:pass@localhost/brc")
    assert not is_sync_postgres_dsn("sqlite:///tmp/test.db")


def test_normalize_libpq_postgres_dsn_strips_sqlalchemy_driver():
    assert normalize_libpq_postgres_dsn(
        "postgresql+asyncpg://user:pass@localhost:5432/brc"
    ) == "postgresql://user:pass@localhost:5432/brc"
    assert normalize_libpq_postgres_dsn(
        "postgresql+psycopg://user:pass@localhost:5432/brc"
    ) == "postgresql://user:pass@localhost:5432/brc"
