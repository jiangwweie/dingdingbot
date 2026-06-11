from __future__ import annotations

import argparse
import os
import sys

from scripts import build_runtime_post_close_followup_packet


def test_post_close_followup_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://followup")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    build_runtime_post_close_followup_packet._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://followup"


def test_post_close_followup_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_packet(args: argparse.Namespace):
        print("noisy library log")
        return {"status": "post_close_complete", "packet": {"ok": True}}

    monkeypatch.setattr(build_runtime_post_close_followup_packet, "_build_packet", fake_build_packet)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_runtime_post_close_followup_packet.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert build_runtime_post_close_followup_packet.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy library log" not in captured.out
    assert "noisy library log" in captured.err
