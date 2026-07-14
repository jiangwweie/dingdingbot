from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
RETENTION_PATH = REPO_ROOT / "scripts" / "run_runtime_control_state_retention.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_runtime_control_state_retention", RETENTION_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _engine(tmp_path: Path) -> sa.Engine:
    return sa.create_engine(f"sqlite:///{tmp_path / 'retention.db'}", future=True)


def _create_tables(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_runtime_fact_snapshots (
              fact_snapshot_id TEXT PRIMARY KEY,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_live_signal_events (
              signal_event_id TEXT PRIMARY KEY,
              fact_snapshot_id TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_action_time_tickets (
              ticket_id TEXT PRIMARY KEY,
              public_fact_snapshot_id TEXT,
              action_time_fact_snapshot_id TEXT,
              account_safe_fact_snapshot_id TEXT,
              account_mode_snapshot_id TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_watcher_runtime_coverage (
              runtime_coverage_id TEXT PRIMARY KEY,
              is_current BOOLEAN NOT NULL,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_server_monitor_runs (
              monitor_run_id TEXT PRIMARY KEY,
              created_at_ms INTEGER NOT NULL
            )
            """
        )
    )


def _seed_rows(conn: sa.Connection, now_ms: int) -> None:
    old_20d = now_ms - 20 * 86_400_000
    old_100d = now_ms - 100 * 86_400_000
    fresh_1d = now_ms - 86_400_000
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_runtime_fact_snapshots (fact_snapshot_id, created_at_ms)
            VALUES
              ('fact-old-unreferenced', :old_20d),
              ('fact-old-signal-ref', :old_20d),
              ('fact-old-ticket-ref', :old_20d),
              ('fact-fresh', :fresh_1d)
            """
        ),
        {"old_20d": old_20d, "fresh_1d": fresh_1d},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_live_signal_events (signal_event_id, fact_snapshot_id)
            VALUES ('signal-1', 'fact-old-signal-ref')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_action_time_tickets (
              ticket_id,
              public_fact_snapshot_id,
              action_time_fact_snapshot_id,
              account_safe_fact_snapshot_id,
              account_mode_snapshot_id
            ) VALUES (
              'ticket-1',
              'fact-old-ticket-ref',
              'fact-old-ticket-ref',
              'fact-old-ticket-ref',
              'fact-old-ticket-ref'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_watcher_runtime_coverage (
              runtime_coverage_id,
              is_current,
              created_at_ms
            ) VALUES
              ('coverage-old-historical', false, :old_20d),
              ('coverage-old-current', true, :old_20d),
              ('coverage-fresh-historical', false, :fresh_1d)
            """
        ),
        {"old_20d": old_20d, "fresh_1d": fresh_1d},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_server_monitor_runs (monitor_run_id, created_at_ms)
            VALUES
              ('monitor-old', :old_100d),
              ('monitor-fresh', :fresh_1d)
            """
        ),
        {"old_100d": old_100d, "fresh_1d": fresh_1d},
    )


def _ids(conn: sa.Connection, table: str, column: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(sa.text(f"SELECT {column} FROM {table}")).all()
    }


def test_retention_dry_run_records_without_deleting(tmp_path: Path):
    retention = _load_module()
    engine = _engine(tmp_path)
    now_ms = 1_800_000_000_000
    with engine.begin() as conn:
        _create_tables(conn)
        _seed_rows(conn, now_ms)

        payload = retention.run_retention(
            conn,
            now_ms=now_ms,
            apply=False,
            batch_size=100,
        )

        assert payload["status"] == "retention_dry_run"
        assert payload["eligible_total"] == 3
        assert payload["deleted_total"] == 0
        assert _ids(conn, "brc_runtime_fact_snapshots", "fact_snapshot_id") == {
            "fact-old-unreferenced",
            "fact-old-signal-ref",
            "fact-old-ticket-ref",
            "fact-fresh",
        }
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM brc_runtime_retention_runs")).scalar()
            == 1
        )


def test_retention_apply_deletes_only_allowlisted_unreferenced_noise(tmp_path: Path):
    retention = _load_module()
    engine = _engine(tmp_path)
    now_ms = 1_800_000_000_000
    with engine.begin() as conn:
        _create_tables(conn)
        _seed_rows(conn, now_ms)

        payload = retention.run_retention(
            conn,
            now_ms=now_ms,
            apply=True,
            batch_size=100,
        )

        assert payload["status"] == "retention_applied"
        assert payload["eligible_total"] == 3
        assert payload["deleted_total"] == 3
        assert _ids(conn, "brc_runtime_fact_snapshots", "fact_snapshot_id") == {
            "fact-old-signal-ref",
            "fact-old-ticket-ref",
            "fact-fresh",
        }
        assert _ids(
            conn,
            "brc_watcher_runtime_coverage",
            "runtime_coverage_id",
        ) == {"coverage-old-current", "coverage-fresh-historical"}
        assert _ids(conn, "brc_server_monitor_runs", "monitor_run_id") == {
            "monitor-fresh"
        }
        audit = conn.execute(
            sa.text(
                """
                SELECT status, apply_mode, eligible_total, deleted_total
                FROM brc_runtime_retention_runs
                """
            )
        ).one()
        assert audit.status == "retention_applied"
        assert bool(audit.apply_mode) is True
        assert audit.eligible_total == 3
        assert audit.deleted_total == 3
