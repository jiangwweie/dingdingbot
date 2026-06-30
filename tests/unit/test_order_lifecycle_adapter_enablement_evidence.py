from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_order_lifecycle_adapter_enablement_evidence.py"
)
PRE_LIVE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "verify_runtime_submit_rehearsal_pre_live_evidence.py"
)
LOCAL_HEAD = "6a39509565471aa56be7945f8b04ce8d5e18460a"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_order_lifecycle_adapter_enablement_evidence",
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
        "verify_runtime_submit_rehearsal_pre_live_evidence",
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
async def test_adapter_enablement_evidence_allows_non_executing_implementation_task_only():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
        runner=_runner(pre_live),
    )

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert (
        evidence["status"]
        == "ready_for_non_executing_order_lifecycle_adapter_implementation_task"
    )
    assert evidence["readiness_summary"]["technical_rehearsal_ready"] is True
    assert evidence["readiness_summary"]["registration_draft_chain_ready"] is True
    assert evidence["readiness_summary"]["protection_failure_policy_ready"] is True
    assert evidence["readiness_summary"]["entry_registration_draft_ready"] is True
    assert evidence["readiness_summary"]["hard_stop_registration_draft_ready"] is True
    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is True
    assert evidence["checks"]["ready_for_runtime_adapter_enablement"] is False
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["local_registration_result_status_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["first_real_submit_local_registration_gate_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["first_real_submit_local_registration_enablement_decision_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["scoped_local_registration_action_authorization_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["execution_intent_local_order_linkage_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "adapter_implementation_capabilities"
        ]["exchange_stage_protection_failure_policy_gate_implemented"]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "local_registration_requires_first_real_submit_gate"
        ]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "local_registration_requires_first_real_submit_enablement_decision"
        ]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "local_registration_requires_scoped_action_authorization"
        ]
        is True
    )
    assert (
        evidence["adapter_enablement_gate"]["current_state"][
            "protection_failure_policy_status"
        ]
        == "ready_for_first_real_submit_confirmation"
    )
    assert evidence["registration_draft_evidence"][
        "protection_failure_policy_id"
    ].startswith("runtime-protection-failure-policy-")
    assert "order_lifecycle_adapter_invocation_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_order_registration_write_path_not_enabled" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "persistent_duplicate_submit_lock_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "execution_intent_status_transition_after_registration_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_registration_result_status_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "first_real_submit_local_registration_gate_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "first_real_submit_local_registration_enablement_decision_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "scoped_local_registration_action_authorization_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "execution_intent_local_order_linkage_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "protection_order_failure_recovery_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "exchange_stage_protection_failure_policy_gate_not_implemented" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "owner_real_submit_authorization_missing" in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "local_registration_pre_exchange_not_ready" in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "order_lifecycle_adapter_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_order_registration_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert evidence["safety_invariants"]["order_lifecycle_called"] is False
    assert evidence["safety_invariants"]["exchange_called"] is False
    assert evidence["safety_invariants"]["order_created"] is False


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_still_blocks_runtime_enablement_with_owner_flags():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is True
    assert evidence["checks"]["ready_for_runtime_adapter_enablement"] is False
    assert evidence["owner_gate"]["owner_real_submit_authorized"] is True
    assert evidence["owner_gate"]["owner_live_runtime_enablement_authorized"] is True
    assert "owner_real_submit_authorization_missing" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "runtime_live_enablement_not_ready" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "order_lifecycle_adapter_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "local_order_registration_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "local_registration_pre_exchange_not_ready" in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "order_lifecycle_adapter_invocation_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "persistent_duplicate_submit_lock_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "execution_intent_status_transition_after_registration_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "local_registration_result_status_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert "scoped_local_registration_action_authorization_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_surfaces_local_registration_rehearsal_flags():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_local_registration_pre_exchange=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=pre_live_evidence
    )

    current_state = evidence["adapter_enablement_gate"]["current_state"]
    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is True
    assert evidence["checks"]["ready_for_runtime_adapter_enablement"] is True
    assert current_state["local_registration_pre_exchange_exercised"] is True
    assert current_state["local_registration_pre_exchange_ready"] is True
    assert current_state["local_registration_rehearsal_enabled"] is True
    assert (
        current_state["local_registration_adapter_result_status"]
        == "registered_created_local_orders"
    )
    assert (
        current_state["local_registration_adapter_result_order_lifecycle_enabled"]
        is True
    )
    assert (
        current_state["local_registration_adapter_result_registration_enabled"]
        is True
    )
    assert "order_lifecycle_adapter_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_order_registration_runtime_enablement_disabled" not in (
        evidence["adapter_enablement_gate"]["implementation_work_items"]
    )
    assert "local_registration_pre_exchange_not_ready" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )
    assert evidence["safety_invariants"]["order_lifecycle_called"] is False
    assert evidence["safety_invariants"]["exchange_called"] is False


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_surfaces_exchange_simulation_evidence():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_in_memory_exchange_execution_simulation=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is True
    assert evidence["checks"]["ready_for_runtime_adapter_enablement"] is True
    assert evidence["readiness_summary"]["exchange_submit_adapter_pre_execution_ready"] is True
    assert (
        evidence["readiness_summary"]["exchange_submit_execution_disabled_proved"]
        is True
    )
    assert (
        evidence["readiness_summary"][
            "in_memory_exchange_execution_simulation_submitted"
        ]
        is True
    )
    assert evidence["exchange_submit_evidence"]["pre_execution_ready"] is True
    assert evidence["exchange_submit_evidence"]["adapter_result_status"] == (
        "exchange_submit_adapter_armed"
    )
    assert evidence["exchange_submit_evidence"][
        "disabled_execution_result_status"
    ] == "exchange_submit_execution_disabled"
    assert evidence["exchange_submit_evidence"][
        "disabled_execution_mode"
    ] == "disabled"
    assert evidence["exchange_submit_evidence"][
        "in_memory_simulation_status"
    ] == "exchange_submit_orders_submitted"
    assert evidence["exchange_submit_evidence"][
        "in_memory_simulation_execution_mode"
    ] == "in_memory_simulation"
    assert evidence["exchange_submit_evidence"][
        "in_memory_simulation_is_fake_gateway_only"
    ] is True
    assert evidence["exchange_submit_evidence"]["does_not_authorize_live_action"] is True
    assert evidence["safety_invariants"]["exchange_called"] is False
    assert evidence["source_pre_live_evidence"]["safety_invariants"][
        "in_memory_exchange_execution_simulation_exchange_called"
    ] is True
    assert "protection_order_failure_recovery_not_implemented" not in (
        evidence["adapter_enablement_gate"]["runtime_enablement_blockers"]
    )


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_blocks_when_hard_stop_draft_is_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_evidence)
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

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=mutated
    )

    assert (
        evidence["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "hard_stop_registration_draft_missing" in evidence["checks"]["blockers"]


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_blocks_when_protection_failure_policy_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_evidence)
    mutated["checks"]["protection_failure_policy_passed"] = False
    mutated["checks"]["protection_failure_policy_blockers"] = [
        "require_reduce_only_recovery_mode_missing"
    ]
    mutated["registration_draft_chain"].pop("protection_failure_policy", None)

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=mutated
    )

    assert (
        evidence["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "protection_failure_policy_not_ready" in evidence["checks"]["blockers"]
    assert "require_reduce_only_recovery_mode_missing" in (
        evidence["checks"]["blockers"]
    )


@pytest.mark.asyncio
async def test_adapter_enablement_evidence_blocks_on_forbidden_execution_flags():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )
    mutated = copy.deepcopy(pre_live_evidence)
    mutated["checks"]["forbidden_execution_flags"] = ["order_created"]

    evidence = module.build_order_lifecycle_adapter_enablement_evidence(
        pre_live_evidence=mutated
    )

    assert (
        evidence["status"]
        == "blocked_before_order_lifecycle_adapter_implementation_task"
    )
    assert evidence["checks"]["ready_for_non_executing_implementation_task"] is False
    assert "order_created" in evidence["checks"]["blockers"]
    assert "technical_rehearsal_not_ready" in evidence["checks"]["blockers"]
