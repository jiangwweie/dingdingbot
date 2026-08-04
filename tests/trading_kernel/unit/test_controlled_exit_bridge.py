from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.trading_kernel import request_controlled_exit_0002_bridge as bridge
from scripts.trading_kernel.deploy_tokyo_release import SshTokyoReleaseBackend

SOURCE_REVISION = "0002_sor_v3_strategy_group_capacity"
TARGET_COMMIT = "a" * 40


def test_0002_bridge_accepts_exact_source_policy_with_entry_submit_enabled() -> None:
    bound = bridge._source_policy_ticket_bound(
        {
            "enabled": True,
            "new_entry_submit_enabled": True,
            "max_concurrent_tickets": 3,
        }
    )

    assert bound == 3


def test_0002_bridge_rejects_source_policy_identity_drift() -> None:
    with pytest.raises(ValueError, match="source Owner Policy differs"):
        bridge._source_policy_ticket_bound(
            {
                "enabled": True,
                "new_entry_submit_enabled": False,
                "max_concurrent_tickets": 3,
            }
        )


def test_0002_bridge_is_streamed_to_the_exact_current_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"status": "eligible", "active_ticket_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        backend,
        "probe_exchange",
        lambda _release: {
            "venue_id": "binance-usdm",
            "account_position_mode": "independent_sides",
            "account_margin_mode": "cross",
            "non_flat_domain_count": 1,
            "open_order_domain_count": 1,
        },
    )

    result = backend.inspect_deployment_drain(
        "/opt/brc/current",
        SOURCE_REVISION,
        TARGET_COMMIT,
    )

    assert result["status"] == "eligible"
    argv = captured["argv"]
    assert isinstance(argv, tuple)
    assert argv[-2] == "--"
    remote_command = str(argv[-1])
    assert "/opt/brc/current/.venv/bin/python -" in remote_command
    assert "--inspect-only" in remote_command
    source = str(captured["input"])
    assert "request_exit" in source
    assert "CcxtVenueAdapter" not in source


def test_0002_bridge_inspection_blocks_internal_exchange_contradiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"status": "eligible", "active_ticket_count": 1}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )
    monkeypatch.setattr(
        backend,
        "probe_exchange",
        lambda _release: {
            "venue_id": "binance-usdm",
            "account_position_mode": "independent_sides",
            "account_margin_mode": "cross",
            "non_flat_domain_count": 0,
            "open_order_domain_count": 0,
        },
    )

    result = backend.inspect_deployment_drain(
        "/opt/brc/current",
        SOURCE_REVISION,
        TARGET_COMMIT,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "internal_exchange_position_contradiction"


def test_0002_bridge_request_carries_only_audit_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"status": "requested"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    backend = SshTokyoReleaseBackend(
        target="tokyo",
        repo_root=Path("."),
        timeout_seconds=30,
    )

    backend.request_deployment_drain(
        "/opt/brc/current",
        SOURCE_REVISION,
        "deploy-20260804-01",
        TARGET_COMMIT,
    )

    remote_command = str(captured["argv"][-1])
    assert "--authorization-id deploy-20260804-01" in remote_command
    assert f"--target-commit {TARGET_COMMIT}" in remote_command
    assert "--ticket" not in remote_command
    assert "--quantity" not in remote_command
