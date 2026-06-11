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
    assert report["checks"]["registration_draft_chain_passed"] is True
    assert report["checks"]["protection_failure_policy_passed"] is True
    assert report["checks"]["protection_failure_policy_blockers"] == []
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["checks"]["ready_for_live_runtime_enablement_mutation_design"] is False
    assert report["checks"]["technical_blockers"] == []
    assert report["checks"]["operational_blockers"] == [
        "current_head_not_deployed_to_tokyo",
        "owner_real_submit_authorization_missing",
    ]
    assert report["checks"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "controlled_submit_adapter_not_implemented",
        "order_lifecycle_adapter_disabled",
    ]
    assert "current_head_not_deployed_to_tokyo" in (
        report["checks"]["live_enablement_blockers"]
    )
    assert "owner_live_runtime_enablement_authorization_missing" in (
        report["checks"]["live_enablement_blockers"]
    )
    assert report["live_enablement_preview"]["status"] == "blocked"
    assert report["live_enablement_preview"]["not_execution_authority"] is True
    assert report["live_enablement_preview"]["runtime_state_mutated"] is False
    assert report["live_enablement_preview"]["order_created"] is False
    assert report["live_enablement_preview"]["exchange_called"] is False
    assert report["checks"]["forbidden_execution_flags"] == []
    assert all(value is False for value in report["safety_invariants"].values())
    assert report["pipeline"]["submit_rehearsal_status"] == "blocked"
    assert report["pipeline"]["submit_adapter_preview_status"] == (
        "inputs_ready_adapter_not_implemented"
    )
    assert {
        "local_orders_not_registered",
        "trusted_submit_fact_snapshot_id_missing",
        "submit_idempotency_policy_id_missing",
        "exchange_submit_enablement_not_ready",
        "runtime_exchange_gateway_readiness_missing",
    }.issubset(set(report["checks"]["exchange_submit_rehearsal_blockers"]))
    assert report["pipeline"]["order_lifecycle_handoff_status"] == (
        "ready_for_order_lifecycle_adapter"
    )
    assert report["pipeline"]["order_lifecycle_adapter_preview_status"] == (
        "inputs_ready_registration_not_enabled"
    )
    assert report["pipeline"]["order_registration_draft_preview_status"] == (
        "inputs_ready_registration_draft_only"
    )
    assert report["pipeline"]["protection_failure_policy_status"] == (
        "ready_for_first_real_submit_confirmation"
    )
    assert report["registration_draft_chain"]["in_memory_runtime_mutation_only"] is True
    assert report["registration_draft_chain"]["protection_failure_policy"][
        "status"
    ] == "ready_for_first_real_submit_confirmation"
    assert report["registration_draft_chain"]["protection_failure_policy"][
        "exchange_called"
    ] is False
    assert report["registration_draft_chain"]["attempt_mutation"]["status"] == "applied"
    assert report["registration_draft_chain"]["order_registration_draft_preview"][
        "order_objects_constructed"
    ] is False
    assert report["registration_draft_chain"]["order_registration_draft_preview"][
        "local_order_registration_executed"
    ] is False
    assert report["registration_draft_chain"]["order_registration_draft_preview"][
        "order_created"
    ] is False
    assert report["registration_draft_chain"]["order_registration_draft_preview"][
        "order_lifecycle_called"
    ] is False
    assert report["registration_draft_chain"]["order_registration_draft_preview"][
        "exchange_called"
    ] is False


@pytest.mark.asyncio
async def test_pre_live_packet_still_blocks_when_owner_and_deploy_gates_are_present():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        runner=_runner(module),
    )

    assert report["status"] == "blocked_before_first_real_submit"
    assert report["checks"]["technical_rehearsal_passed"] is True
    assert report["checks"]["registration_draft_chain_passed"] is True
    assert report["checks"]["current_head_deployed"] is True
    assert report["checks"]["owner_real_submit_authorization_present"] is True
    assert report["checks"]["owner_live_runtime_enablement_authorization_present"] is True
    assert report["checks"]["protection_failure_policy_passed"] is True
    assert report["checks"]["operational_blockers"] == []
    assert report["checks"]["implementation_blockers"] == [
        "runtime_not_live_execution_enabled",
        "controlled_submit_adapter_not_implemented",
        "order_lifecycle_adapter_disabled",
    ]
    assert report["checks"]["live_enablement_blockers"] == [
        "controlled_submit_adapter_not_implemented",
        "promotion_gate_first_real_submit_attempt_outcome_policy_id_missing",
        "promotion_gate_first_real_submit_deployment_readiness_evidence_id_missing",
        "promotion_gate_first_real_submit_local_registration_enablement_decision_id_missing",
        "promotion_gate_first_real_submit_owner_real_submit_authorization_id_missing",
        "promotion_gate_first_real_submit_submit_idempotency_policy_id_missing",
        "promotion_gate_first_real_submit_trusted_submit_fact_snapshot_id_missing",
        "promotion_gate_not_ready_for_first_real_submit",
    ]
    assert report["checks"]["ready_for_live_runtime_enablement_mutation_design"] is False
    assert report["promotion_gate"]["status"] == "blocked"
    assert {
        "first_real_submit_attempt_outcome_policy_id_missing",
        "first_real_submit_trusted_submit_fact_snapshot_id_missing",
        "first_real_submit_submit_idempotency_policy_id_missing",
        "first_real_submit_owner_real_submit_authorization_id_missing",
    }.issubset(set(report["promotion_gate"]["blockers"]))
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["pipeline"]["submit_rehearsal_status"] == "blocked"
    assert report["pipeline"]["submit_adapter_preview_status"] == (
        "inputs_ready_adapter_not_implemented"
    )
    assert report["pipeline"]["order_registration_draft_preview_status"] == (
        "inputs_ready_registration_draft_only"
    )
    assert report["pipeline"]["protection_failure_policy_status"] == (
        "ready_for_first_real_submit_confirmation"
    )
    assert report["rehearsal"]["order_created"] is False
    assert report["rehearsal"]["order_lifecycle_called"] is False
    assert report["rehearsal"]["exchange_called"] is False
