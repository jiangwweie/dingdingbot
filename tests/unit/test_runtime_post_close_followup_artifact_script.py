from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace

import pytest

from scripts import build_runtime_post_close_followup_artifact


def test_post_close_followup_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://followup")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    build_runtime_post_close_followup_artifact._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://followup"


def test_post_close_followup_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_artifact(args: argparse.Namespace):
        print("noisy library log")
        return {"status": "post_close_complete", "artifact": {"ok": True}}

    monkeypatch.setattr(build_runtime_post_close_followup_artifact, "_build_artifact", fake_build_artifact)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_runtime_post_close_followup_artifact.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert build_runtime_post_close_followup_artifact.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy library log" not in captured.out
    assert "noisy library log" in captured.err


def test_post_close_followup_cli_help_uses_artifact_wording(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_runtime_post_close_followup_artifact.py", "--help"],
    )

    with pytest.raises(SystemExit) as exc:
        build_runtime_post_close_followup_artifact.main()

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "post-close follow-up artifact" in captured.out
    assert "post-close follow-up packet" not in captured.out


def test_post_close_followup_plan_is_non_executing():
    artifact = SimpleNamespace(
        owner_close_approval_env="OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE",
        owner_close_approval_value="runtime-close-approved",
        closed_review_command_args=[
            "scripts/create_runtime_closed_trade_review.py",
            "--runtime-instance-id",
            "runtime-1",
            "--entry-order-id",
            "entry-1",
            "--exit-order-id",
            "exit-1",
        ],
    )

    plan = build_runtime_post_close_followup_artifact._post_close_followup_plan(
        runtime_instance_id="runtime-1",
        env_file="/tmp/runtime.env",
        artifact=artifact,
    )

    assert plan["not_executed"] is True
    assert "packet_status" not in plan
    assert plan["requires_explicit_owner_approval_before_execute"] is True
    assert plan["owner_close_approval_env"] == "OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE"
    assert plan["owner_close_approval_value"] == "runtime-close-approved"
    assert plan["owner_close_dry_run_command_args"] == [
        "scripts/runtime_owner_reduce_only_close_flow.py",
        "--runtime-instance-id",
        "runtime-1",
        "--env-file",
        "/tmp/runtime.env",
    ]
    assert plan["owner_close_execute_command_args"] == [
        "scripts/runtime_owner_reduce_only_close_flow.py",
        "--runtime-instance-id",
        "runtime-1",
        "--env-file",
        "/tmp/runtime.env",
        "--execute-real-close",
    ]
    assert plan["closed_review_command_args"][-1] == "exit-1"
    assert (
        plan["safety_invariants"]["post_close_command_plan_projection_only"]
        is True
    )
    assert "packet_only" not in plan["safety_invariants"]
    assert plan["safety_invariants"]["exchange_write_called"] is False
    assert plan["safety_invariants"]["review_record_created"] is False


def test_post_close_followup_plan_omits_review_command_when_complete():
    artifact = SimpleNamespace(
        status=SimpleNamespace(value="post_close_complete"),
        owner_close_approval_env=None,
        owner_close_approval_value=None,
        required_steps=["verify_next_attempt_gate"],
        closed_review_command_args=[
            "scripts/create_runtime_closed_trade_review.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    plan = build_runtime_post_close_followup_artifact._post_close_followup_plan(
        runtime_instance_id="runtime-1",
        env_file="/tmp/runtime.env",
        artifact=artifact,
    )

    assert plan["owner_close_dry_run_command_args"] == []
    assert plan["owner_close_execute_command_args"] == []
    assert "packet_status" not in plan
    assert plan["closed_review_command_args"] == []
    assert plan["post_close_required_sequence"] == ["verify_next_attempt_gate"]


def test_post_close_followup_top_level_safety_is_projection_only():
    safety = build_runtime_post_close_followup_artifact._post_close_followup_safety_invariants(
        exchange_read_only=True,
    )

    assert safety["post_close_followup_projection_only"] is True
    assert "packet_only" not in safety
    assert safety["exchange_read_only"] is True
    assert safety["exchange_write_called"] is False
    assert safety["review_record_created"] is False
