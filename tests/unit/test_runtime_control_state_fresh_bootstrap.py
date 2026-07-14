from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
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


def test_fresh_bootstrap_runs_106_seed_baseline_then_head() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        install_runtime_control_state_schema(conn, through_revision="106")
        from tests.support.runtime_control_state_schema import seed_runtime_control_state

        seed_runtime_control_state(conn, migration_baseline_revision="106")
        install_runtime_control_state_schema(
            conn,
            after_revision="106",
            through_revision="111",
        )
        current_events = conn.execute(
            text(
                """
                SELECT event_spec_id
                FROM brc_strategy_side_event_specs
                WHERE status='current' AND execution_eligibility_enabled = true
                ORDER BY event_spec_id
                """
            )
        ).scalars().all()
        current_versions = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM brc_strategy_group_versions
                WHERE status='current' AND version=2
                """
            )
        ).scalar_one()
    engine.dispose()

    assert len(current_events) == 6
    assert current_versions == 5
    assert all(event_id.endswith(":v2") for event_id in current_events)
