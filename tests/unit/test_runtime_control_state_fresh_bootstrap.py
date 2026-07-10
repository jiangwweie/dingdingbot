from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from tests.support.runtime_control_state_schema import (
    install_runtime_control_state_schema,
)


def test_canonical_schema_installer_includes_execution_eligibility_columns() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        install_runtime_control_state_schema(conn, through_revision="104")
        inspector = inspect(conn)
        assert inspector.has_table("brc_strategy_side_event_specs")
        columns = {
            column["name"]
            for column in inspector.get_columns("brc_strategy_side_event_specs")
        }
    engine.dispose()

    assert {
        "declared_signal_grade",
        "declared_required_execution_mode",
        "execution_eligibility_enabled",
    } <= columns
