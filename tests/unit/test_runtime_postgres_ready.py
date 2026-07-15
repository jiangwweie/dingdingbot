from __future__ import annotations

import json

from scripts.check_runtime_postgres_ready import check_postgres_ready, main


def test_postgres_ready_requires_dsn(monkeypatch, capsys):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["--require-database-url", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_postgres_ready_executes_select_one():
    statements: list[str] = []

    def runner(database_url: str) -> int:
        assert database_url == "postgresql+psycopg://test"
        statements.append("SELECT 1")
        return 1

    report = check_postgres_ready(
        database_url="postgresql+psycopg://test",
        timeout_seconds=1,
        runner=runner,
    )

    assert report == {"status": "ready", "select_one": 1}
    assert statements == ["SELECT 1"]


def test_postgres_ready_rejects_boolean_one():
    report = check_postgres_ready(
        database_url="postgresql+psycopg://test",
        timeout_seconds=0.01,
        runner=lambda _: True,
    )

    assert report["status"] == "unavailable"
    assert report["error"] == "select_one_invalid_result"
