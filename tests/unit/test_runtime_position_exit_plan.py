from __future__ import annotations

import json
import sys

from scripts import runtime_position_exit_plan


def test_position_exit_plan_cli_uses_artifact_builder(monkeypatch, capsys):
    calls = []

    async def fake_build_artifact(args):
        calls.append(args)
        return {
            "scope": "runtime_position_exit_plan",
            "status": "ready",
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "position_closed": False,
            },
        }

    monkeypatch.setattr(
        runtime_position_exit_plan,
        "_build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_position_exit_plan.py",
            "--runtime-instance-id",
            "runtime-1",
            "--skip-exchange",
            "--skip-reconciliation",
        ],
    )

    assert runtime_position_exit_plan.main() == 0

    captured = capsys.readouterr()
    artifact = json.loads(captured.out)
    assert artifact["scope"] == "runtime_position_exit_plan"
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert calls[0].runtime_instance_id == "runtime-1"


def test_position_exit_plan_legacy_packet_builder_absent():
    assert not hasattr(runtime_position_exit_plan, "_build_packet")
