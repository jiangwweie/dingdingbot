from __future__ import annotations

import os

from scripts import runtime_owner_reduce_only_close_flow


def test_owner_reduce_only_close_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "PG_DATABASE_URL=postgresql+asyncpg://close-flow",
                "EXCHANGE_API_KEY=key",
            ]
        )
    )
    monkeypatch.setenv("PG_DATABASE_URL", "")
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)

    runtime_owner_reduce_only_close_flow._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://close-flow"
    assert os.environ["EXCHANGE_API_KEY"] == "key"
