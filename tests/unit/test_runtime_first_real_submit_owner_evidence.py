from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_runtime_first_real_submit_owner_evidence.py"
PRE_LIVE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "verify_runtime_submit_rehearsal_pre_live_evidence.py"
)
LOCAL_HEAD = "1734b8cc3baaf41f00a3ce8c8c0453a11a1b17c1"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_owner_evidence",
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
            return pre_live_module.CommandResult("1734b8cc", 0)
        raise AssertionError(f"unexpected command: {command}")

    return run


@pytest.mark.asyncio
async def test_owner_evidence_blocks_when_deploy_and_owner_auth_are_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head="old-head",
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
        runner=_runner(pre_live),
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "blocked_before_owner_first_real_submit_decision"
    assert evidence["readiness_summary"]["technical_ready"] is True
    assert evidence["readiness_summary"]["protection_failure_policy_ready"] is True
    assert evidence["readiness_summary"]["deployment_ready"] is False
    assert evidence["readiness_summary"]["implementation_ready"] is True
    assert evidence["checks"]["evidence_ready_for_owner_review"] is False
    assert "current_head_not_deployed_to_tokyo" in evidence["remaining_gates"]["deployment_blockers"]
    assert "Owner real-submit authorization" in evidence["remaining_gates"]["owner_policy_items"]
    assert "Owner live-runtime enablement authorization" in evidence["remaining_gates"]["owner_policy_items"]
    assert evidence["remaining_gates"]["implementation_blockers"] == []
    assert "current_head_not_deployed_to_tokyo" in (
        evidence["remaining_gates"]["non_owner_live_enablement_blockers"]
    )
    assert evidence["readiness_summary"]["machine_evidence_preparation_status"] == (
        "prepared_evidence_blocked"
    )
    assert evidence["evidence_preparation"]["status"] == "prepared_evidence_blocked"
    assert (
        evidence["evidence_preparation"]["prepared_evidence_status"]
        == "blocked"
    )
    assert "packet_status" not in evidence["evidence_preparation"]
    assert "trusted_submit_fact_snapshot_id" in (
        evidence["evidence_preparation"]["prepared_evidence_ids"]
    )
    assert evidence["evidence_preparation"]["does_not_authorize_live_action"] is True
    assert evidence["source_pre_live_evidence"]["status"] == "blocked_before_first_real_submit"
    assert evidence["safety_invariants"]["exchange_called"] is False
    assert evidence["safety_invariants"]["order_lifecycle_called"] is False
    assert evidence["safety_invariants"]["order_created"] is False


@pytest.mark.asyncio
async def test_owner_evidence_reaches_owner_review_when_deployed_and_only_owner_authorization_is_missing():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
        exercise_local_registration_pre_exchange=True,
        exercise_exchange_submit_adapter_pre_execution=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "ready_for_owner_first_real_submit_decision"
    assert evidence["checks"]["evidence_ready_for_owner_review"] is True
    assert evidence["checks"]["ready_for_first_real_submit"] is False
    assert evidence["checks"]["blockers"] == []
    assert evidence["remaining_gates"]["owner_policy_items"] == [
        "Owner live-runtime enablement authorization",
        "Owner real-submit authorization",
    ]
    assert evidence["remaining_gates"]["non_owner_live_enablement_blockers"] == []
    assert evidence["first_real_submit_action_boundary"][
        "ready_for_first_real_submit"
    ] is False
    assert "first_real_submit_action_not_ready" in (
        evidence["first_real_submit_action_boundary"]["remaining_action_blockers"]
    )
    assert evidence["first_real_submit_action_boundary"][
        "does_not_authorize_live_action"
    ] is True
    assert evidence["safety_invariants"]["exchange_called"] is False


@pytest.mark.asyncio
async def test_owner_evidence_still_blocks_when_owner_and_deploy_gates_are_present():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "blocked_before_owner_first_real_submit_decision"
    assert evidence["readiness_summary"]["technical_ready"] is True
    assert evidence["readiness_summary"]["protection_failure_policy_ready"] is True
    assert evidence["readiness_summary"]["deployment_ready"] is True
    assert evidence["readiness_summary"]["implementation_ready"] is True
    assert evidence["remaining_gates"]["owner_policy_items"] == []
    assert evidence["remaining_gates"]["implementation_blockers"] == []
    assert evidence["remaining_gates"]["non_owner_live_enablement_blockers"] == [
        "promotion_gate_first_real_submit_owner_real_submit_authorization_id_missing",
        "promotion_gate_not_ready_for_first_real_submit",
    ]
    assert evidence["evidence_preparation"]["status"] == "prepared_evidence_blocked"
    assert "attempt_outcome_policy_id" in (
        evidence["evidence_preparation"]["available_evidence_ids"]
    )
    assert (
        "local_registration_action_authorization_not_auto_created"
        in evidence["remaining_gates"]["machine_evidence_skipped"]
    )
    assert evidence["checks"]["ready_for_first_real_submit"] is False
    assert evidence["does_not_authorize"] == [
        "real runtime submit",
        "exchange order placement",
        "OrderLifecycle adapter enablement",
        "local order registration",
        "withdrawal or transfer",
        "live runtime profile change",
    ]


@pytest.mark.asyncio
async def test_owner_evidence_surfaces_exchange_pre_execution_evidence():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_exchange_submit_adapter_pre_execution=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "ready_for_owner_controlled_first_real_submit_review"
    assert evidence["checks"]["evidence_ready_for_owner_review"] is True
    assert evidence["checks"]["ready_for_first_real_submit"] is True
    assert evidence["readiness_summary"]["owner_review_scope"] == (
        "owner_controlled_first_real_submit_review"
    )
    assert (
        evidence["readiness_summary"]["local_registration_pre_exchange_ready"]
        is True
    )
    assert (
        evidence["readiness_summary"]["exchange_submit_adapter_pre_execution_ready"]
        is True
    )
    assert (
        evidence["readiness_summary"]["exchange_submit_execution_disabled_proved"]
        is True
    )
    assert (
        evidence["readiness_summary"][
            "in_memory_exchange_execution_simulation_submitted"
        ]
        is False
    )
    assert evidence["exchange_submit_rehearsal"]["ready"] is True
    assert evidence["exchange_submit_rehearsal"]["adapter_result_status"] == (
        "exchange_submit_adapter_armed"
    )
    assert evidence["exchange_submit_rehearsal"][
        "disabled_execution_result_status"
    ] == "exchange_submit_execution_disabled"
    assert evidence["exchange_submit_rehearsal"]["disabled_execution_mode"] == (
        "disabled"
    )
    assert (
        evidence["exchange_submit_rehearsal"][
            "disabled_execution_result_exchange_called"
        ]
        is False
    )
    assert evidence["exchange_submit_rehearsal"][
        "does_not_authorize_live_action"
    ] is True
    assert evidence["local_registration_rehearsal"]["ready"] is True
    assert evidence["local_registration_rehearsal"]["adapter_result_status"] == (
        "registered_created_local_orders"
    )
    assert evidence["local_registration_rehearsal"]["registered_order_count"] == 2
    assert evidence["local_registration_rehearsal"]["order_lifecycle_called"] is True
    assert evidence["local_registration_rehearsal"]["exchange_called"] is False
    assert evidence["first_real_submit_action_boundary"][
        "owner_evidence_ready_for_decision"
    ] is True
    assert evidence["first_real_submit_action_boundary"][
        "ready_for_first_real_submit"
    ] is True
    assert evidence["first_real_submit_action_boundary"][
        "owner_decision_is_submit_authority"
    ] is False
    assert evidence["first_real_submit_action_boundary"][
        "requires_separate_action_authorization"
    ] is True
    assert "exchange_submit_adapter_not_implemented" not in (
        evidence["first_real_submit_action_boundary"]["remaining_action_blockers"]
    )
    assert evidence["first_real_submit_action_boundary"][
        "remaining_action_blockers"
    ] == []


@pytest.mark.asyncio
async def test_owner_evidence_distinguishes_local_registration_ready_from_exchange_submit_ready():
    module = _load_module()
    pre_live = _load_pre_live_module()
    pre_live_evidence = await pre_live.build_pre_live_evidence(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_local_registration_pre_exchange=True,
        runner=_runner(pre_live),
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "ready_for_owner_first_real_submit_decision"
    assert evidence["checks"]["evidence_ready_for_owner_review"] is True
    assert evidence["checks"]["ready_for_first_real_submit"] is False
    assert evidence["readiness_summary"][
        "local_order_registration_adapter_enablement_ready"
    ] is True
    assert (
        evidence["readiness_summary"]["exchange_submit_adapter_pre_execution_ready"]
        is False
    )
    assert evidence["readiness_summary"]["exchange_submit_action_ready"] is False
    assert evidence["readiness_summary"]["owner_review_scope"] == (
        "owner_review_not_submit_authority"
    )
    assert evidence["local_registration_rehearsal"]["ready"] is True
    assert evidence["local_registration_rehearsal"]["adapter_result_status"] == (
        "registered_created_local_orders"
    )
    assert evidence["exchange_submit_rehearsal"]["ready"] is False
    assert evidence["first_real_submit_action_boundary"][
        "local_registration_pre_exchange_ready"
    ] is True
    assert evidence["first_real_submit_action_boundary"][
        "exchange_submit_adapter_pre_execution_ready"
    ] is False
    assert evidence["first_real_submit_action_boundary"][
        "ready_for_first_real_submit"
    ] is False
    assert "exchange_submit_adapter_pre_execution_not_ready" in (
        evidence["first_real_submit_action_boundary"]["remaining_action_blockers"]
    )
    assert "first_real_submit_action_not_ready" in (
        evidence["first_real_submit_action_boundary"]["remaining_action_blockers"]
    )
    assert evidence["first_real_submit_action_boundary"][
        "does_not_authorize_live_action"
    ] is True


def test_owner_evidence_can_be_ready_for_owner_review_when_only_owner_is_missing():
    module = _load_module()
    pre_live_evidence = _minimal_pre_live_evidence(
        operational_blockers=["owner_real_submit_authorization_missing"],
        live_enablement_blockers=[
            "owner_live_runtime_enablement_authorization_missing"
        ],
        owner_real_submit_authorized=False,
        owner_live_runtime_enablement_authorized=False,
    )

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "ready_for_owner_first_real_submit_decision"
    assert evidence["checks"]["evidence_ready_for_owner_review"] is True
    assert evidence["checks"]["ready_for_first_real_submit"] is False
    assert evidence["readiness_summary"]["owner_review_scope"] == (
        "owner_review_not_submit_authority"
    )
    assert evidence["remaining_gates"]["owner_policy_items"] == [
        "Owner live-runtime enablement authorization",
        "Owner real-submit authorization",
    ]
    assert evidence["checks"]["blockers"] == []


def test_owner_evidence_blocks_missing_protection_failure_policy_even_with_owner_flags():
    module = _load_module()
    pre_live_evidence = _minimal_pre_live_evidence(
        operational_blockers=[],
        live_enablement_blockers=[],
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
    )
    pre_live_evidence["checks"]["protection_failure_policy_passed"] = False
    pre_live_evidence["checks"]["protection_failure_policy_blockers"] = [
        "require_reduce_only_recovery_mode_missing"
    ]

    evidence = module.build_first_real_submit_owner_evidence(
        pre_live_evidence=pre_live_evidence
    )

    assert evidence["status"] == "blocked_before_owner_first_real_submit_decision"
    assert evidence["checks"]["evidence_ready_for_owner_review"] is False
    assert "protection_failure_policy_not_ready" in evidence["checks"]["blockers"]
    assert "require_reduce_only_recovery_mode_missing" in (
        evidence["checks"]["blockers"]
    )
    assert evidence["remaining_gates"]["owner_policy_items"] == []


def _minimal_pre_live_evidence(
    *,
    operational_blockers: list[str],
    live_enablement_blockers: list[str],
    owner_real_submit_authorized: bool,
    owner_live_runtime_enablement_authorized: bool,
) -> dict:
    return {
        "status": "blocked_before_first_real_submit",
        "scope": "runtime_submit_rehearsal_pre_live_evidence",
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
            "protection_failure_policy_passed": True,
            "current_head_deployed": True,
            "ready_for_first_real_submit": False,
            "technical_blockers": [],
            "protection_failure_policy_blockers": [],
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
