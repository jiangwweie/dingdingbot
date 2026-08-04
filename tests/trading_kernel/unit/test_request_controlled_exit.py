from __future__ import annotations

import json

import pytest

import scripts.trading_kernel.request_controlled_exit as script
from src.trading_kernel.application.controlled_exit import ControlledExitResult

TARGET_COMMIT = "a" * 40


def test_native_controlled_exit_cli_emits_bounded_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = {}

    async def fake_execute(args):
        captured.update(vars(args))
        return ControlledExitResult(requested_ticket_ids=("ticket:one",))

    monkeypatch.setattr(script, "_execute", fake_execute)

    exit_code = script.main(
        [
            "--purpose",
            "deployment_drain",
            "--authorization-id",
            "deploy-20260804-01",
            "--target-commit",
            TARGET_COMMIT,
            "--requested-at-ms",
            "2000",
        ]
    )

    assert exit_code == 0
    assert captured["target_commit"] == TARGET_COMMIT
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "blocked_ticket_ids": [],
        "in_progress_ticket_ids": [],
        "requested_ticket_ids": ["ticket:one"],
        "schema": "brc.trading_kernel.controlled_exit.v1",
        "status": "requested",
        "terminal_ticket_ids": [],
    }


def test_native_controlled_exit_cli_requires_authorization_identity() -> None:
    with pytest.raises(SystemExit):
        script.main(
            [
                "--purpose",
                "deployment_drain",
                "--target-commit",
                TARGET_COMMIT,
            ]
        )


def test_native_controlled_exit_cli_returns_blocked_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_execute(_args):
        return ControlledExitResult(blocked_ticket_ids=("ticket:block",))

    monkeypatch.setattr(script, "_execute", fake_execute)

    exit_code = script.main(
        [
            "--purpose",
            "deployment_drain",
            "--authorization-id",
            "deploy-20260804-01",
            "--target-commit",
            TARGET_COMMIT,
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["blocked_ticket_ids"] == ["ticket:block"]
