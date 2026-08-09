from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.owner_console.export_server_dml_snapshot import (
    build_remote_dump_command,
    validate_schema_column_names,
)
from scripts.owner_console.restore_local_dml_snapshot import (
    validate_local_target,
    verify_snapshot_metadata,
)


def test_export_is_single_job_consistent_data_only_dml() -> None:
    command = build_remote_dump_command(database_name="brc")

    assert "pg_dump" in command
    assert "--data-only" in command
    assert "--inserts" in command
    assert "--rows-per-insert=100" in command
    assert "--serializable-deferrable" in command
    assert "--lock-wait-timeout=3000" in command
    assert "--schema=public" in command
    assert "--exclude-table=alembic_version" in command
    assert "--jobs" not in command


def test_export_rejects_credential_columns_but_allows_runtime_claim_token() -> None:
    validate_schema_column_names(("claim_token", "ticket_id", "review_id"))

    with pytest.raises(ValueError, match="credential-like"):
        validate_schema_column_names(("owner_password_hash",))
    with pytest.raises(ValueError, match="credential-like"):
        validate_schema_column_names(("exchange_api_key",))


def test_restore_rejects_remote_or_unscoped_database() -> None:
    with pytest.raises(ValueError):
        validate_local_target(host="tokyo", database_name="brc")
    with pytest.raises(ValueError):
        validate_local_target(host="127.0.0.1", database_name="brc")

    validate_local_target(
        host="127.0.0.1",
        database_name="brc_owner_console_test_012345abcdef",
    )


def test_snapshot_metadata_checksum_is_verified_before_restore(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.sql.gz"
    snapshot.write_bytes(b"compressed snapshot bytes")
    metadata = tmp_path / "snapshot.json"
    metadata.write_text(
        json.dumps(
            {
                "captured_at_utc": "2026-08-09T00:00:00Z",
                "ssh_host": "tokyo",
                "database_name": "brc",
                "postgresql_version": "16.4",
                "alembic_revision": "0003_portfolio_admission_observability",
                "compressed_bytes": snapshot.stat().st_size,
                "sha256": "0" * 64,
                "parity_counts": {
                    "brc_signal_events": 1,
                    "brc_trade_tickets": 1,
                    "brc_trade_aggregates": 1,
                    "brc_trade_reviews": 1,
                    "open_brc_runtime_incidents": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA-256"):
        verify_snapshot_metadata(snapshot_path=snapshot, metadata_path=metadata)


def test_snapshot_directory_is_ignored() -> None:
    assert ".local/owner-console-snapshots/" in Path(".gitignore").read_text(
        encoding="utf-8"
    )
