from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "verify_runtime_submit_rehearsal_pre_live_packet.py"
)
LOCAL_HEAD = "e004ec39abb8d0bb40ef275a03e07537192e1324"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_runtime_submit_rehearsal_pre_live_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runner(module):
    def run(command, cwd):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return module.CommandResult(str(REPO_ROOT), 0)
        if command == ("git", "rev-parse", "HEAD"):
            return module.CommandResult(LOCAL_HEAD, 0)
        if command == ("git", "rev-parse", "--short=8", "HEAD"):
            return module.CommandResult("e004ec39", 0)
        raise AssertionError(f"unexpected command: {command}")

    return run


@pytest.mark.asyncio
async def test_pre_live_packet_blocks_current_head_not_deployed_and_owner_auth_missing():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        owner_real_submit_authorized=False,
        runner=_runner(module),
    )

    assert report["status"] == "blocked_before_first_real_submit"
    assert report["checks"]["technical_rehearsal_passed"] is True
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["checks"]["technical_blockers"] == []
    assert report["checks"]["operational_blockers"] == [
        "current_head_not_deployed_to_tokyo",
        "owner_real_submit_authorization_missing",
    ]
    assert report["checks"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "controlled_submit_adapter_not_implemented",
    ]
    assert report["checks"]["forbidden_execution_flags"] == []
    assert all(value is False for value in report["safety_invariants"].values())
    assert report["pipeline"]["submit_rehearsal_status"] == (
        "ready_for_non_executing_submit_adapter_boundary"
    )
    assert report["pipeline"]["submit_adapter_preview_status"] == (
        "inputs_ready_adapter_not_implemented"
    )


@pytest.mark.asyncio
async def test_pre_live_packet_still_blocks_when_owner_and_deploy_gates_are_present():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        runner=_runner(module),
    )

    assert report["status"] == "blocked_before_first_real_submit"
    assert report["checks"]["technical_rehearsal_passed"] is True
    assert report["checks"]["current_head_deployed"] is True
    assert report["checks"]["owner_real_submit_authorization_present"] is True
    assert report["checks"]["operational_blockers"] == []
    assert report["checks"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "controlled_submit_adapter_not_implemented",
    ]
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["rehearsal"]["order_created"] is False
    assert report["rehearsal"]["order_lifecycle_called"] is False
    assert report["rehearsal"]["exchange_called"] is False
