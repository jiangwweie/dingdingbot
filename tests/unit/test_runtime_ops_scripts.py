from __future__ import annotations

import os

from scripts import runtime_live_position_monitor, runtime_position_exit_plan


def test_runtime_monitor_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "PG_DATABASE_URL=postgresql+asyncpg://example",
                "EXCHANGE_API_KEY=key-from-file",
            ]
        )
    )
    monkeypatch.setenv("PG_DATABASE_URL", "")
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)

    runtime_live_position_monitor._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://example"
    assert os.environ["EXCHANGE_API_KEY"] == "key-from-file"


def test_runtime_exit_plan_env_loader_preserves_non_empty_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://from-file")
    monkeypatch.setenv("PG_DATABASE_URL", "postgresql+asyncpg://already-set")

    runtime_position_exit_plan._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://already-set"
