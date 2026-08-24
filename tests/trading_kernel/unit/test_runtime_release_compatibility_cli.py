from __future__ import annotations

import json

import pytest

from scripts.trading_kernel import persist_runtime_release_fact as cli
from src.trading_kernel.application.runtime import RuntimeReleaseCompatibilityFact
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    SelectionJobConflict,
)

DATABASE_URL = "postgresql+asyncpg://kernel:secret@localhost/kernel"


def _write_args() -> list[str]:
    return [
        "--database-url",
        DATABASE_URL,
        "write",
        "--release-compatibility-id",
        "release-compatibility:" + "a" * 40 + ":" + "b" * 40,
        "--from-commit",
        "a" * 40,
        "--to-commit",
        "b" * 40,
        "--from-schema-revision",
        "0005_tradfi_instrument_center",
        "--to-schema-revision",
        "0006_sor_dynamic_selection_v0",
        "--classification",
        "COMPATIBLE_RESTART",
        "--reason-code",
        "PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",
        "--compatibility-basis-digest",
        "sha256:" + "c" * 64,
        "--certification-manifest-digest",
        "sha256:" + "d" * 64,
        "--created-at-ms",
        "1775000000000",
    ]


def test_write_cli_persists_one_validated_exact_fact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[RuntimeReleaseCompatibilityFact] = []

    async def fake_write(
        database_url: str,
        fact: RuntimeReleaseCompatibilityFact,
    ) -> tuple[bool, RuntimeReleaseCompatibilityFact]:
        assert database_url == DATABASE_URL
        observed.append(fact)
        return True, fact

    monkeypatch.setattr(cli, "_write", fake_write)

    assert cli.main(_write_args()) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["created"] is True
    assert payload["fact"]["release_compatibility_id"] == (
        "release-compatibility:" + "a" * 40 + ":" + "b" * 40
    )
    assert len(observed) == 1


def test_write_cli_redacts_database_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_write(
        database_url: str,
        fact: RuntimeReleaseCompatibilityFact,
    ) -> tuple[bool, RuntimeReleaseCompatibilityFact]:
        del database_url, fact
        raise SelectionJobConflict("internal row detail")

    monkeypatch.setattr(cli, "_write", fake_write)

    assert cli.main(_write_args()) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "release_compatibility_conflict" in captured.err
    assert "secret" not in captured.err
    assert "internal row detail" not in captured.err


def test_read_cli_reports_exact_absence_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_read(
        database_url: str,
        release_compatibility_id: str,
    ) -> RuntimeReleaseCompatibilityFact | None:
        assert database_url == DATABASE_URL
        assert release_compatibility_id.endswith("b" * 40)
        return None

    monkeypatch.setattr(cli, "_read", fake_read)

    assert (
        cli.main(
            [
                "--database-url",
                DATABASE_URL,
                "read",
                "--release-compatibility-id",
                "release-compatibility:" + "a" * 40 + ":" + "b" * 40,
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {
        "fact": None,
        "status": "not_found",
    }
