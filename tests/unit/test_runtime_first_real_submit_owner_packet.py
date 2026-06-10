from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_runtime_first_real_submit_owner_packet.py"
PRE_LIVE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "verify_runtime_submit_rehearsal_pre_live_packet.py"
)
LOCAL_HEAD = "1734b8cc3baaf41f00a3ce8c8c0453a11a1b17c1"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_owner_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_pre_live_module():
    spec = importlib.util.spec_from_file_location(
        "verify_runtime_submit_rehearsal_pre_live_packet",
        PRE_LIVE_SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runner(pre_live_module):
    def run(command, cwd):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return pre_live_module.CommandResult(str(REPO_ROOT), 0)
        if command == ("git", "rev-parse", "HEAD"):
            return pre_live_module.CommandResult(LOCAL_HEAD, 0)
        if command == ("git", "rev-parse", "--short=8", "HEAD"):
            return pre_live_module.CommandResult("1734b8cc", 0)
        raise AssertionError(f"unexpected command: {command}")

    return run


@pytest.mark.asyncio
async def test_owner_packet_blocks_when_deploy_and_owner_auth_are_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head="old-head",
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
        runner=_runner(pre_live),
    )

    packet = module.build_first_real_submit_owner_packet(
        pre_live_packet=pre_live_packet
    )

    assert packet["status"] == "blocked_before_owner_first_real_submit_decision"
    assert packet["readiness_summary"]["technical_ready"] is True
    assert packet["readiness_summary"]["deployment_ready"] is False
    assert packet["readiness_summary"]["implementation_ready"] is False
    assert packet["checks"]["packet_ready_for_owner_decision"] is False
    assert "current_head_not_deployed_to_tokyo" in packet["remaining_gates"]["deployment_blockers"]
    assert "Owner real-submit authorization" in packet["remaining_gates"]["owner_decision_items"]
    assert "Owner live-runtime enablement authorization" in packet["remaining_gates"]["owner_decision_items"]
    assert packet["remaining_gates"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "order_lifecycle_adapter_disabled",
    ]
    assert packet["source_pre_live_packet"]["status"] == "blocked_before_first_real_submit"
    assert packet["safety_invariants"]["exchange_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["order_created"] is False


@pytest.mark.asyncio
async def test_owner_packet_still_blocks_when_owner_and_deploy_gates_are_present():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )

    packet = module.build_first_real_submit_owner_packet(
        pre_live_packet=pre_live_packet
    )

    assert packet["status"] == "blocked_before_owner_first_real_submit_decision"
    assert packet["readiness_summary"]["technical_ready"] is True
    assert packet["readiness_summary"]["deployment_ready"] is True
    assert packet["readiness_summary"]["implementation_ready"] is False
    assert packet["remaining_gates"]["owner_decision_items"] == []
    assert packet["remaining_gates"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "order_lifecycle_adapter_disabled",
    ]
    assert packet["checks"]["ready_for_first_real_submit"] is False
    assert packet["does_not_authorize"] == [
        "real runtime submit",
        "exchange order placement",
        "OrderLifecycle adapter enablement",
        "local order registration",
        "withdrawal or transfer",
        "live runtime profile change",
    ]


def test_owner_packet_can_be_ready_for_owner_decision_when_only_owner_is_missing():
    module = _load_module()
    pre_live_packet = _minimal_pre_live_packet(
        operational_blockers=["owner_real_submit_authorization_missing"],
        live_enablement_blockers=[
            "owner_live_runtime_enablement_authorization_missing"
        ],
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
    )

    packet = module.build_first_real_submit_owner_packet(
        pre_live_packet=pre_live_packet
    )

    assert packet["status"] == "ready_for_owner_first_real_submit_decision"
    assert packet["checks"]["packet_ready_for_owner_decision"] is True
    assert packet["checks"]["ready_for_first_real_submit"] is False
    assert packet["remaining_gates"]["owner_decision_items"] == [
        "Owner live-runtime enablement authorization",
        "Owner real-submit authorization",
    ]
    assert packet["checks"]["blockers"] == []


def _minimal_pre_live_packet(
    *,
    operational_blockers: list[str],
    live_enablement_blockers: list[str],
    owner_real_submit_authorized: bool,
    owner_live_runtime_enablement_authorized: bool,
) -> dict:
    return {
        "status": "blocked_before_first_real_submit",
        "scope": "runtime_submit_rehearsal_pre_live_packet",
        "local_git": {"head": LOCAL_HEAD, "short_head": "1734b8cc"},
        "deployment_gate": {
            "deployed_head": LOCAL_HEAD,
            "require_current_head_deployed": True,
            "current_head_deployed": True,
        },
        "owner_gate": {
            "owner_real_submit_authorized": owner_real_submit_authorized,
            "owner_live_runtime_enablement_authorized": (
                owner_live_runtime_enablement_authorized
            ),
        },
        "pipeline": {
            "submit_rehearsal_status": "ready_for_non_executing_submit_adapter_boundary",
            "submit_adapter_preview_status": "inputs_ready_dry_run_adapter_only",
            "order_lifecycle_handoff_status": "ready_for_order_lifecycle_adapter",
            "order_lifecycle_adapter_preview_status": "inputs_ready_registration_not_enabled",
            "order_registration_draft_preview_status": "inputs_ready_registration_draft_only",
            "next_required_gate": "owner_real_submit_authorization",
        },
        "checks": {
            "technical_rehearsal_passed": True,
            "registration_draft_chain_passed": True,
            "current_head_deployed": True,
            "ready_for_first_real_submit": False,
            "technical_blockers": [],
            "operational_blockers": operational_blockers,
            "implementation_blockers": [],
            "live_enablement_blockers": live_enablement_blockers,
            "forbidden_execution_flags": [],
        },
        "safety_invariants": {
            "database_connected": False,
            "exchange_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }
