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
    assert report["checks"]["implementation_blockers"] == []
    assert report["checks"]["staged_submit_chain_available"] is True
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
        "exchange_submit_enablement_not_ready",
        "runtime_exchange_gateway_readiness_missing",
    }.issubset(set(report["checks"]["exchange_submit_rehearsal_blockers"]))
    assert "trusted_submit_fact_snapshot_id_missing" not in (
        report["checks"]["exchange_submit_rehearsal_blockers"]
    )
    assert "submit_idempotency_policy_id_missing" not in (
        report["checks"]["exchange_submit_rehearsal_blockers"]
    )
    assert report["checks"]["machine_evidence_preparation_status"] == (
        "prepared_packet_blocked"
    )
    assert {
        "submit_idempotency_policy_id",
        "trusted_submit_fact_snapshot_id",
        "protection_creation_failure_policy_id",
    }.issubset(set(report["checks"]["machine_evidence_prepared_ids"]))
    assert "attempt_outcome_policy_id" in (
        report["checks"]["machine_evidence_available_ids"]
    )
    assert (
        report["checks"]["machine_evidence_available_ids"][
            "post_submit_budget_settlement_persistence_evidence_id"
        ]
        == module.POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
    )
    assert (
        "local_registration_action_authorization_not_auto_created"
        in report["checks"]["machine_evidence_skipped"]
    )
    assert report["checks"]["machine_evidence_blockers"] == []
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
    assert report["checks"]["implementation_blockers"] == []
    assert report["checks"]["staged_submit_chain_available"] is True
    assert report["checks"]["live_enablement_blockers"] == [
        "promotion_gate_first_real_submit_deployment_readiness_evidence_id_missing",
        "promotion_gate_first_real_submit_local_registration_enablement_decision_id_missing",
        "promotion_gate_first_real_submit_owner_real_submit_authorization_id_missing",
        "promotion_gate_not_ready_for_first_real_submit",
    ]
    assert report["checks"]["ready_for_live_runtime_enablement_mutation_design"] is False
    assert report["promotion_gate"]["status"] == "blocked"
    assert {
        "first_real_submit_deployment_readiness_evidence_id_missing",
        "first_real_submit_local_registration_enablement_decision_id_missing",
        "first_real_submit_owner_real_submit_authorization_id_missing",
    }.issubset(set(report["promotion_gate"]["blockers"]))
    assert "first_real_submit_attempt_outcome_policy_id_missing" not in (
        report["promotion_gate"]["blockers"]
    )
    assert "first_real_submit_trusted_submit_fact_snapshot_id_missing" not in (
        report["promotion_gate"]["blockers"]
    )
    assert "first_real_submit_submit_idempotency_policy_id_missing" not in (
        report["promotion_gate"]["blockers"]
    )
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["checks"]["machine_evidence_preparation_status"] == (
        "prepared_packet_blocked"
    )
    assert "attempt_outcome_policy_id" in (
        report["checks"]["machine_evidence_available_ids"]
    )
    assert (
        report["checks"]["machine_evidence_available_ids"][
            "post_submit_budget_settlement_persistence_evidence_id"
        ]
        == module.POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
    )
    assert report["first_real_submit_packet"]["status"] == "blocked"
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


@pytest.mark.asyncio
async def test_pre_live_packet_can_exercise_local_registration_before_exchange_submit():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_local_registration_pre_exchange=True,
        runner=_runner(module),
    )

    local_rehearsal = report["local_registration_rehearsal"]
    adapter_result = local_rehearsal["adapter_result"]
    binding = local_rehearsal["intent_local_order_binding"]
    packet_preview = local_rehearsal["exchange_submit_packet_preview"]

    assert report["status"] == "blocked_before_first_real_submit"
    assert report["checks"]["local_registration_pre_exchange_exercised"] is True
    assert report["checks"]["local_registration_pre_exchange_ready"] is True
    assert report["checks"]["ready_for_live_runtime_enablement_mutation_design"] is True
    assert report["checks"]["ready_for_first_real_submit"] is False
    assert report["checks"]["live_enablement_blockers"] == []
    assert report["promotion_gate"]["status"] == "ready_for_first_real_submit_gate_review"
    assert adapter_result["status"] == "registered_created_local_orders"
    assert adapter_result["local_order_registration_executed"] is True
    assert adapter_result["order_lifecycle_called"] is True
    assert adapter_result["exchange_called"] is False
    assert len(adapter_result["local_order_ids"]) == 2
    assert len(adapter_result["entry_order_ids"]) == 1
    assert len(adapter_result["protection_order_ids"]) == 1
    assert binding["status"] == "ready_for_exchange_submit_design"
    assert binding["execution_intent_status_changed"] is False
    assert packet_preview["status"] == "ready_for_exchange_submit_adapter_design"
    assert packet_preview["exchange_called"] is False
    assert packet_preview["exchange_order_submitted"] is False
    assert "local_orders_not_registered" not in (
        report["checks"]["exchange_submit_rehearsal_blockers"]
    )
    assert "exchange_submit_action_authorization_missing" in (
        report["checks"]["exchange_submit_rehearsal_blockers"]
    )
    assert "runtime_exchange_gateway_readiness_missing" in (
        report["checks"]["exchange_submit_rehearsal_blockers"]
    )
    assert report["safety_invariants"]["local_order_registration_executed"] is True
    assert (
        report["safety_invariants"]["local_registration_order_lifecycle_called"]
        is True
    )
    assert report["safety_invariants"]["exchange_called"] is False
    assert report["safety_invariants"]["execution_intent_status_changed"] is False


@pytest.mark.asyncio
async def test_pre_live_packet_can_reach_exchange_submit_adapter_pre_execution_boundary():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_exchange_submit_adapter_pre_execution=True,
        runner=_runner(module),
    )

    exchange_rehearsal = report["exchange_submit_adapter_rehearsal"]
    action_authorization = exchange_rehearsal["action_authorization"]
    enablement_decision = exchange_rehearsal["enablement_decision"]
    gateway_readiness = exchange_rehearsal["gateway_readiness"]
    adapter_result = exchange_rehearsal["adapter_result"]
    disabled_execution_result = exchange_rehearsal["disabled_execution_result"]
    blockers = report["checks"]["exchange_submit_rehearsal_blockers"]

    assert report["status"] == "ready_for_owner_controlled_first_real_submit_review"
    assert report["checks"]["local_registration_pre_exchange_exercised"] is True
    assert report["checks"]["local_registration_pre_exchange_ready"] is True
    assert (
        report["checks"]["exchange_submit_adapter_pre_execution_exercised"]
        is True
    )
    assert report["checks"]["exchange_submit_adapter_pre_execution_ready"] is True
    assert report["checks"]["ready_for_live_runtime_enablement_mutation_design"] is True
    assert report["checks"]["ready_for_first_real_submit"] is True
    assert report["checks"]["live_enablement_blockers"] == []
    assert report["rehearsal"]["status"] == "ready_for_owner_live_action_review"
    assert action_authorization["status"] == "approved_for_exchange_submit_action"
    assert enablement_decision["status"] == "ready_for_exchange_submit_action"
    assert gateway_readiness["status"] == "ready_for_manual_gateway_binding"
    assert adapter_result["status"] == "exchange_submit_adapter_armed"
    assert adapter_result["blockers"] == []
    assert adapter_result["duplicate_submit_lock_acquired"] is True
    assert adapter_result["exchange_called"] is False
    assert adapter_result["order_lifecycle_submit_called"] is False
    assert adapter_result["exchange_order_submitted"] is False
    assert disabled_execution_result["status"] == "exchange_submit_execution_disabled"
    assert disabled_execution_result["exchange_submit_execution_enabled"] is False
    assert disabled_execution_result["exchange_called"] is False
    assert disabled_execution_result["order_lifecycle_submit_called"] is False
    assert disabled_execution_result["exchange_order_submitted"] is False
    assert (
        disabled_execution_result["real_exchange_submit_adapter_executed"]
        is False
    )
    assert "exchange_submit_adapter_not_implemented" not in blockers
    assert "exchange_submit_action_authorization_missing" not in blockers
    assert "runtime_exchange_gateway_readiness_missing" not in blockers
    assert "runtime_exchange_gateway_readiness_repository_unavailable" not in blockers
    assert report["safety_invariants"]["exchange_called"] is False
    assert (
        report["safety_invariants"]["exchange_submit_adapter_exchange_called"]
        is False
    )
    assert (
        report["safety_invariants"][
            "exchange_submit_adapter_order_lifecycle_submit_called"
        ]
        is False
    )
    assert (
        report["safety_invariants"]["exchange_submit_adapter_exchange_order_submitted"]
        is False
    )
    assert (
        report["safety_invariants"][
            "exchange_submit_disabled_execution_exchange_called"
        ]
        is False
    )
    assert (
        report["safety_invariants"][
            "exchange_submit_disabled_execution_order_lifecycle_submit_called"
        ]
        is False
    )
    assert (
        report["safety_invariants"][
            "exchange_submit_disabled_execution_exchange_order_submitted"
        ]
        is False
    )
    assert (
        report["safety_invariants"][
            "exchange_submit_disabled_execution_real_adapter_executed"
        ]
        is False
    )


@pytest.mark.asyncio
async def test_pre_live_packet_can_simulate_enabled_exchange_execution_in_memory():
    module = _load_module()

    report = await module.build_pre_live_packet(
        deployed_head=LOCAL_HEAD,
        owner_real_submit_authorized=True,
        owner_live_runtime_enablement_authorized=True,
        exercise_in_memory_exchange_execution_simulation=True,
        runner=_runner(module),
    )

    exchange_rehearsal = report["exchange_submit_adapter_rehearsal"]
    simulation = exchange_rehearsal["in_memory_execution_simulation"]
    blockers = report["checks"]["exchange_submit_rehearsal_blockers"]

    assert report["status"] == "ready_for_owner_controlled_first_real_submit_review"
    assert report["checks"]["exchange_submit_adapter_pre_execution_ready"] is True
    assert (
        report["checks"]["in_memory_exchange_execution_simulation_exercised"]
        is True
    )
    assert (
        report["checks"]["in_memory_exchange_execution_simulation_submitted"]
        is True
    )
    assert report["checks"]["ready_for_first_real_submit"] is True
    assert simulation["status"] == "exchange_submit_orders_submitted"
    assert simulation["exchange_submit_execution_enabled"] is True
    assert simulation["exchange_called"] is True
    assert simulation["exchange_order_submitted"] is True
    assert simulation["order_lifecycle_submit_called"] is True
    assert simulation["real_exchange_submit_adapter_executed"] is True
    assert simulation["exchange_call_count"] == 2
    assert simulation["order_lifecycle_submit_call_count"] == 2
    assert simulation["entry_exchange_order_id"].startswith(
        "in-memory-exchange-runtime-order-draft-"
    )
    assert simulation["entry_exchange_order_id"].endswith("-entry")
    assert len(simulation["protection_exchange_order_ids"]) == 1
    assert simulation["execution_intent_status_changed"] is False
    assert simulation["owner_bounded_execution_called"] is False
    assert simulation["withdrawal_or_transfer_created"] is False
    assert "exchange_submit_adapter_not_implemented" not in blockers
    assert (
        report["safety_invariants"][
            "in_memory_exchange_execution_simulation_exchange_called"
        ]
        is True
    )
    assert (
        report["safety_invariants"][
            "in_memory_exchange_execution_simulation_order_lifecycle_submit_called"
        ]
        is True
    )
    assert (
        report["safety_invariants"][
            "in_memory_exchange_execution_simulation_exchange_order_submitted"
        ]
        is True
    )
    assert (
        report["safety_invariants"][
            "in_memory_exchange_execution_simulation_real_adapter_executed"
        ]
        is True
    )
