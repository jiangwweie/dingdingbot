from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_order_lifecycle_adapter_enablement_packet.py"
)
PRE_LIVE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "verify_runtime_submit_rehearsal_pre_live_packet.py"
)
LOCAL_HEAD = "6a39509565471aa56be7945f8b04ce8d5e18460a"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_order_lifecycle_adapter_enablement_packet",
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
            return pre_live_module.CommandResult("6a395095", 0)
        raise AssertionError(f"unexpected command: {command}")

    return run


@pytest.mark.asyncio
async def test_adapter_enablement_packet_allows_non_executing_implementation_task_only():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
        runner=_runner(pre_live),
    )

    packet = module.build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=pre_live_packet
    )

    assert (
        packet["status"]
        == "ready_for_non_executing_order_lifecycle_adapter_implementation_task"
    )
    assert packet["readiness_summary"]["technical_rehearsal_ready"] is True
    assert packet["readiness_summary"]["registration_draft_chain_ready"] is True
    assert packet["readiness_summary"]["protection_failure_policy_ready"] is True
    assert packet["readiness_summary"]["entry_registration_draft_ready"] is True
    assert packet["readiness_summary"]["hard_stop_registration_draft_ready"] is True
    assert packet["checks"]["ready_for_non_executing_implementation_task"] is True
    assert packet["checks"]["ready_for_runtime_adapter_enablement"] is False
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["local_registration_result_status_implemented"]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["first_real_submit_local_registration_gate_implemented"]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["first_real_submit_local_registration_enablement_decision_implemented"]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["execution_intent_local_order_linkage_implemented"]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["exchange_stage_protection_failure_policy_gate_implemented"]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "local_registration_requires_first_real_submit_gate"
        ]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "local_registration_requires_first_real_submit_enablement_decision"
        ]
        is True
    )
    assert (
        packet["adapter_enablement_gate"]["current_state"][
            "protection_failure_policy_status"
        ]
        == "ready_for_first_real_submit_confirmation"
    )
    assert packet["registration_draft_evidence"][
        "protection_failure_policy_id"
    ].startswith("runtime-protection-failure-policy-")
    assert "order_lifecycle_adapter_invocation_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_order_registration_write_path_not_enabled" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "persistent_duplicate_submit_lock_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "execution_intent_status_transition_after_registration_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_registration_result_status_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "first_real_submit_local_registration_gate_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "first_real_submit_local_registration_enablement_decision_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "execution_intent_local_order_linkage_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "protection_order_failure_recovery_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "exchange_stage_protection_failure_policy_gate_not_implemented" not in (
        packet["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "owner_real_submit_authorization_missing" in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["exchange_called"] is False
    assert packet["safety_invariants"]["order_created"] is False


@pytest.mark.asyncio
async def test_adapter_enablement_packet_still_blocks_runtime_enablement_with_owner_flags():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )

    packet = module.build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=pre_live_packet
    )

    assert packet["checks"]["ready_for_non_executing_implementation_task"] is True
    assert packet["checks"]["ready_for_runtime_adapter_enablement"] is False
    assert packet["owner_gate"]["owner_real_submit_authorized"] is True
    assert packet["owner_gate"]["owner_live_runtime_enablement_authorized"] is True
    assert "owner_real_submit_authorization_missing" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "runtime_live_enablement_not_ready" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "order_lifecycle_adapter_disabled" in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "order_lifecycle_adapter_invocation_not_implemented" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "persistent_duplicate_submit_lock_not_implemented" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "execution_intent_status_transition_after_registration_not_implemented" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "local_registration_result_status_not_implemented" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "protection_order_failure_recovery_not_implemented" not in (
        packet["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )


@pytest.mark.asyncio
async def test_adapter_enablement_packet_blocks_when_hard_stop_draft_is_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_packet)
    registration_preview = mutated["registration_draft_chain"][
        "order_registration_draft_preview"
    ]
    registration_preview["local_order_registration_drafts"] = [
        draft
        for draft in registration_preview["local_order_registration_drafts"]
        if draft["order_role"] == "ENTRY"
    ]
    registration_preview["protection_registration_draft_count"] = 0
    registration_preview["registration_draft_count"] = 1

    packet = module.build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=mutated
    )

    assert (
        packet["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert packet["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "hard_stop_registration_draft_missing" in packet["checks"]["blockers"]


@pytest.mark.asyncio
async def test_adapter_enablement_packet_blocks_when_protection_failure_policy_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_packet)
    mutated["checks"]["protection_failure_policy_passed"] = False
    mutated["checks"]["protection_failure_policy_blockers"] = [
        "require_reduce_only_recovery_mode_missing"
    ]
    mutated["registration_draft_chain"].pop("protection_failure_policy", None)

    packet = module.build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=mutated
    )

    assert (
        packet["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert packet["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "protection_failure_policy_not_ready" in packet["checks"]["blockers"]
    assert "require_reduce_only_recovery_mode_missing" in (
        packet["checks"]["blockers"]
    )


@pytest.mark.asyncio
async def test_adapter_enablement_packet_blocks_on_forbidden_execution_flags():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_packet = await pre_live.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_packet)
    mutated["checks"]["forbidden_execution_flags"] = ["order_created"]

    packet = module.build_order_lifecycle_adapter_enablement_packet(
        pre_live_packet=mutated
    )

    assert (
        packet["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert packet["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "order_created" in packet["checks"]["blockers"]
    assert "technical_rehearsal_not_ready" in packet["checks"]["blockers"]
