from __future__ import annotations

import os

from scripts import build_runtime_post_close_followup_packet


def test_post_close_followup_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://followup")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    build_runtime_post_close_followup_packet._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://followup"
