from __future__ import annotations

import argparse
import os
import sys

from scripts import build_runtime_closed_trade_review_facts_packet


def test_closed_review_facts_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://review-facts")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    build_runtime_closed_trade_review_facts_packet._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://review-facts"


def test_closed_review_facts_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_packet(args: argparse.Namespace):
        print("noisy library log")
        return {"status": "waiting_for_close", "packet": {"ok": True}}

    monkeypatch.setattr(
        build_runtime_closed_trade_review_facts_packet,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_runtime_closed_trade_review_facts_packet.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert build_runtime_closed_trade_review_facts_packet.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy library log" not in captured.out
    assert "noisy library log" in captured.err
