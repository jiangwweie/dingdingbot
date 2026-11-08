from __future__ import annotations

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


@pytest.mark.parametrize("method", ["inspect_deployment_drain", "request_deployment_drain"])
def test_manual_product_refuses_inherited_tokyo_bridge(monkeypatch, method):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    backend = SshTokyoReleaseBackend(target="tokyo", repo_root=Path("."), timeout_seconds=30)
    args = ("/opt/brc/current", SOURCE_REVISION)
    args += (TARGET_COMMIT,) if method == "inspect_deployment_drain" else ("owner-audit", TARGET_COMMIT)
    with pytest.raises(ValueError, match="manual product"):
        getattr(backend, method)(*args)
    assert calls == []
