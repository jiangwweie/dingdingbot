from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import sqlalchemy as sa


SCRIPT = Path("scripts/ops/query_runtime_signal_forensics.py")


def test_cli_emits_stdout_only_json_and_masks_database_configuration(tmp_path: Path) -> None:
    database = tmp_path / "runtime.db"
    engine = sa.create_engine(f"sqlite+pysqlite:///{database}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE brc_live_signal_events "
                "(signal_event_id TEXT PRIMARY KEY, observed_at_ms BIGINT)"
            )
        )
    engine.dispose()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            f"sqlite+pysqlite:///{database}",
            "--start",
            "2026-07-11T00:00:00+08:00",
            "--end",
            "2026-07-12T00:00:00+08:00",
            "--allow-non-postgres-for-test",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "brc.runtime_signal_forensics.v1"
    assert payload["conclusion_code"] == "runtime_data_gap"
    assert payload["configuration"] == {"database_configured": True}
    assert str(database) not in completed.stdout
    assert list(tmp_path.iterdir()) == [database]


def test_cli_rejects_reversed_window_and_exposes_no_mutating_flags() -> None:
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "--output" not in help_result.stdout
    assert "--apply" not in help_result.stdout
    assert "--live-submit" not in help_result.stdout

    reversed_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            "postgresql+psycopg://masked@localhost/brc",
            "--start",
            "2026-07-12T00:00:00+08:00",
            "--end",
            "2026-07-11T00:00:00+08:00",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert reversed_result.returncode != 0
    assert "later than" in reversed_result.stderr
