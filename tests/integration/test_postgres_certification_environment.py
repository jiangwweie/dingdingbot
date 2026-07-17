"""Assert the explicit disposable PostgreSQL certification contract."""

from __future__ import annotations

import os
import re

import sqlalchemy as sa


_SCHEMA_PATTERN = re.compile(r"brc_remediation_[a-f0-9]{12}")


def test_required_postgres_certification_environment_identity() -> None:
    dsn = os.environ["BRC_LOCAL_TEST_POSTGRES_DSN"]
    schema = os.environ["BRC_LOCAL_TEST_POSTGRES_SCHEMA"]
    assert _SCHEMA_PATTERN.fullmatch(schema)

    engine = sa.create_engine(dsn)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT current_database()")).scalar_one() == (
                "brc_remediation"
            )
            assert conn.execute(sa.text("SELECT current_user")).scalar_one() == "brc_test"
            assert conn.execute(sa.text("SELECT 1")).scalar_one() == 1
            assert conn.execute(
                sa.text("SELECT to_regnamespace(:schema)"), {"schema": schema}
            ).scalar_one() == schema
    finally:
        engine.dispose()
