from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.runtime_execution_first_real_submit_enablement_evidence_service import (
    RuntimeExecutionFirstRealSubmitEnablementEvidenceService,
)
from src.application.runtime_execution_first_real_submit_evidence_preparation_service import (
    RuntimeExecutionFirstRealSubmitEvidencePreparationService,
)
from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitGateStatus,
)
from src.domain.runtime_execution_first_real_submit_enablement_evidence import (
    RuntimeExecutionFirstRealSubmitEnablementEvidence,
    RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus,
    build_runtime_execution_first_real_submit_enablement_evidence,
)
from src.domain.runtime_execution_first_real_submit_evidence_preparation import (
    RuntimeExecutionFirstRealSubmitEvidencePreparationStatus,
)
from src.domain.runtime_execution_duplicate_submit_replay_proof import (
    RuntimeExecutionDuplicateSubmitReplayProofStatus,
    build_runtime_execution_duplicate_submit_replay_proof,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsalStatus,
    build_runtime_execution_submit_rehearsal,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
    RuntimeExecutionSubmitIdempotencyStatus,
)
from src.domain.runtime_execution_submit_prerequisite_evidence_proof import (
    RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus,
    build_runtime_execution_submit_prerequisite_evidence_proof,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsStatus,
)
from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomeKind,
    RuntimeExecutionAttemptOutcomePolicyStatus,
)
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicyStatus,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)
from src.interfaces import api_trading_console as trading_console_api


NOW_MS = 1781000000000
POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID = (
    "runtime-post-submit-budget-settlement-persistence-084"
)


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )


def _decision(**overrides):
    fields = {
        "decision_id": "runtime-exchange-submit-enable-auth-1",
        "authorization_id": "auth-1",
        "execution_intent_id": "intent-1",
        "runtime_instance_id": "runtime-1",
        "source_type": "brc_runtime_order_candidate",
        "source_id": "candidate-1",
        "semantic_ids": _semantic_ids(),
        "status": (
            RuntimeExecutionExchangeSubmitGateStatus
            .READY_FOR_EXCHANGE_SUBMIT_ACTION
        ),
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-auth-1",
        "submit_idempotency_policy_id": "submit-idempotency-auth-1",
        "attempt_outcome_policy_id": "attempt-outcome-auth-1",
        "protection_creation_failure_policy_id": "protection-failure-auth-1",
        "local_registration_enablement_decision_id": (
            "local-registration-enable-auth-1"
        ),
        "owner_real_submit_authorization_id": "owner-real-submit-auth-1",
        "order_lifecycle_submit_enablement_id": "lifecycle-submit-enable-auth-1",
        "exchange_submit_adapter_enablement_id": "adapter-enable-auth-1",
        "exchange_submit_action_authorization_id": "exchange-action-auth-1",
        "deployment_readiness_evidence_id": "runtime-gateway-readiness-auth-1",
        "blockers": [],
        "warnings": [],
        "execution_intent_status_changed": False,
        "order_lifecycle_submit_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _gateway_readiness(**overrides):
    fields = {
        "readiness_id": "runtime-gateway-readiness-auth-1",
        "status": (
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        ),
        "blockers": [],
        "warnings": ["not_live_action_authorization"],
        "created_at_ms": NOW_MS - 1_000,
        "gateway_injected": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_submit_called": False,
        "execution_intent_status_changed": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _submit_rehearsal(decision=None, gateway=None):
    return build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=decision or _decision(),
        runtime_exchange_gateway_readiness=gateway or _gateway_readiness(),
        now_ms=NOW_MS,
    )


def _idempotency_snapshot(**overrides):
    fields = {
        "submit_idempotency_policy_id": "submit-idempotency-auth-1",
        "authorization_id": "auth-1",
        "execution_intent_id": "intent-1",
        "runtime_instance_id": "runtime-1",
        "source_type": "brc_runtime_order_candidate",
        "source_id": "candidate-1",
        "semantic_ids": _semantic_ids(),
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "status": (
            RuntimeExecutionSubmitIdempotencyStatus
            .READY_FOR_NON_EXECUTING_POLICY_CONFIRMATION
        ),
        "stable_submit_key": "runtime-submit:auth-1",
        "replay_lock_key": "auth-1",
        "created_at_ms": NOW_MS,
    }
    fields.update(overrides)
    return RuntimeExecutionSubmitIdempotencySnapshot(**fields)


def _duplicate_replay_proof(decision=None, **overrides):
    decision = decision or _decision()
    kwargs = {
        "enablement_decision": decision,
        "submit_idempotency_snapshot": _idempotency_snapshot(
            submit_idempotency_policy_id=decision.submit_idempotency_policy_id,
            authorization_id=decision.authorization_id,
            execution_intent_id=decision.execution_intent_id,
            runtime_instance_id=decision.runtime_instance_id,
        ),
        "existing_adapter_result": None,
        "existing_execution_result": None,
        "adapter_result_repository_available": True,
        "execution_result_repository_available": True,
        "now_ms": NOW_MS,
    }
    kwargs.update(overrides)
    return build_runtime_execution_duplicate_submit_replay_proof(**kwargs)


def _trusted_submit_facts(decision=None, **overrides):
    decision = decision or _decision()
    fields = {
        "status": (
            RuntimeExecutionTrustedSubmitFactsStatus
            .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
        ),
        "execution_intent_id": decision.execution_intent_id,
        "runtime_instance_id": decision.runtime_instance_id,
        "symbol": "BNB/USDT:USDT",
        "facts_fresh_enough": True,
        "read_only_sources_only": True,
        "owner_supplied_allow_facts_rejected": True,
        "missing_or_stale_facts_block": True,
        "warnings": [],
        "not_execution_authority": True,
        "execution_intent_status_changed": False,
        "runtime_state_mutated": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "withdrawal_instruction_created": False,
        "transfer_instruction_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _attempt_outcome_policy(decision=None, **overrides):
    decision = decision or _decision()
    fields = {
        "status": (
            RuntimeExecutionAttemptOutcomePolicyStatus
            .READY_FOR_ATTEMPT_BUDGET_OUTCOME_ACCOUNTING
        ),
        "outcome_kind": (
            RuntimeExecutionAttemptOutcomeKind
            .ENTRY_FILLED_PROTECTION_CREATION_FAILED
        ),
        "authorization_id": decision.authorization_id,
        "execution_intent_id": decision.execution_intent_id,
        "runtime_instance_id": decision.runtime_instance_id,
        "symbol": "BNB/USDT:USDT",
        "protection_creation_failed": True,
        "attempt_should_be_consumed": True,
        "partial_fill_counts_as_attempt": True,
        "reserved_budget_should_remain_held": True,
        "blocks_new_entries_until_resolved": True,
        "requires_owner_recovery_review": True,
        "requires_reduce_only_recovery_mode": True,
        "requires_reconciliation_before_retry": True,
        "warnings": [],
        "not_execution_authority": True,
        "execution_intent_status_changed": False,
        "runtime_state_mutated": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "owner_bounded_execution_called": False,
        "withdrawal_instruction_created": False,
        "transfer_instruction_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _protection_failure_policy(decision=None, **overrides):
    decision = decision or _decision()
    fields = {
        "status": (
            RuntimeExecutionProtectionFailurePolicyStatus
            .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
        ),
        "execution_intent_id": decision.execution_intent_id,
        "runtime_instance_id": decision.runtime_instance_id,
        "symbol": "BNB/USDT:USDT",
        "block_new_entries_until_resolved": True,
        "mark_position_unprotected_until_verified": True,
        "require_owner_recovery_review": True,
        "require_reduce_only_recovery_mode": True,
        "require_reconciliation_before_retry": True,
        "consume_attempt_on_any_fill": True,
        "hold_or_reconcile_budget_until_position_resolved": True,
        "warnings": [],
        "not_execution_authority": True,
        "execution_intent_status_changed": False,
        "runtime_state_mutated": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "owner_bounded_execution_called": False,
        "withdrawal_instruction_created": False,
        "transfer_instruction_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _prerequisite_evidence_proof(decision=None, **overrides):
    decision = decision or _decision()
    kwargs = {
        "enablement_decision": decision,
        "trusted_submit_facts": _trusted_submit_facts(decision),
        "attempt_outcome_policy": _attempt_outcome_policy(decision),
        "protection_failure_policy": _protection_failure_policy(decision),
        "trusted_submit_facts_repository_available": True,
        "attempt_outcome_policy_repository_available": True,
        "protection_failure_policy_repository_available": True,
        "now_ms": NOW_MS,
    }
    kwargs.update(overrides)
    return build_runtime_execution_submit_prerequisite_evidence_proof(**kwargs)


def _semantic_confirmed() -> StrategySemanticsConfirmationFacts:
    return StrategySemanticsConfirmationFacts(
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
    )


def _runtime_confirmed() -> RuntimeExecutionConfirmationFacts:
    return RuntimeExecutionConfirmationFacts(
        runtime_profile_confirmed=True,
        owner_confirmation_mode_confirmed=True,
        symbol_side_boundary_confirmed=True,
        max_loss_budget_confirmed=True,
        max_notional_boundary_confirmed=True,
        max_active_positions_boundary_confirmed=True,
        max_leverage_boundary_confirmed=True,
        margin_usage_boundary_confirmed=True,
        liquidation_buffer_boundary_confirmed=True,
        protection_readiness_source_confirmed=True,
        stale_fact_behavior_confirmed=True,
        attempt_consumption_rule_confirmed=True,
        budget_reservation_rule_confirmed=True,
        trusted_active_position_source_confirmed=True,
        trusted_account_fact_source_confirmed=True,
    )


def _first_submit_confirmed(**overrides) -> FirstRealSubmitConfirmationFacts:
    fields = {
        "budget_release_or_consume_rule_confirmed": True,
        "post_submit_budget_settlement_persistence_confirmed": True,
        "post_submit_budget_settlement_persistence_evidence_id": (
            POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
        ),
        "attempt_outcome_policy_id": "attempt-outcome-auth-1",
        "protection_creation_failure_policy_confirmed": True,
        "protection_creation_failure_policy_id": "protection-failure-auth-1",
        "duplicate_submit_policy_confirmed": True,
        "submit_idempotency_policy_id": "submit-idempotency-auth-1",
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-auth-1",
        "local_registration_enablement_decision_id": (
            "local-registration-enable-auth-1"
        ),
        "exchange_submit_enablement_decision_id": (
            "runtime-exchange-submit-enable-auth-1"
        ),
        "runtime_submit_rehearsal_id": "runtime-submit-rehearsal-auth-1",
        "deployment_readiness_evidence_id": "runtime-gateway-readiness-auth-1",
        "owner_real_submit_authorization_id": "owner-real-submit-auth-1",
        "deployment_readiness_confirmed": True,
        "explicit_owner_real_submit_authorization": True,
    }
    fields.update(overrides)
    return FirstRealSubmitConfirmationFacts(**fields)


def _promotion_gate(first_submit=None):
    return StrategyRuntimePromotionGateService().preview(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        first_real_submit_confirmations=(
            first_submit or _first_submit_confirmed()
        ),
    )


async def _fake_duplicate_replay_proof(
    authorization_id,
    *,
    exchange_submit_enablement_decision,
    submit_idempotency_policy_id=None,
):
    assert authorization_id == exchange_submit_enablement_decision.authorization_id
    return _duplicate_replay_proof(
        exchange_submit_enablement_decision,
        submit_idempotency_snapshot=_idempotency_snapshot(
            submit_idempotency_policy_id=(
                submit_idempotency_policy_id
                or exchange_submit_enablement_decision.submit_idempotency_policy_id
            ),
            authorization_id=exchange_submit_enablement_decision.authorization_id,
            execution_intent_id=exchange_submit_enablement_decision.execution_intent_id,
            runtime_instance_id=exchange_submit_enablement_decision.runtime_instance_id,
        ),
    )


async def _fake_prerequisite_evidence_proof(
    authorization_id,
    *,
    exchange_submit_enablement_decision,
    trusted_submit_fact_snapshot_id=None,
    attempt_outcome_policy_id=None,
    protection_creation_failure_policy_id=None,
):
    assert authorization_id == exchange_submit_enablement_decision.authorization_id
    assert (
        trusted_submit_fact_snapshot_id
        or exchange_submit_enablement_decision.trusted_submit_fact_snapshot_id
    )
    assert (
        attempt_outcome_policy_id
        or exchange_submit_enablement_decision.attempt_outcome_policy_id
    )
    assert (
        protection_creation_failure_policy_id
        or exchange_submit_enablement_decision.protection_creation_failure_policy_id
    )
    return _prerequisite_evidence_proof(exchange_submit_enablement_decision)


def test_first_real_submit_enablement_evidence_can_be_ready_without_authority():
    first_submit = _first_submit_confirmed()
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(),
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        prerequisite_evidence_proof=_prerequisite_evidence_proof(),
        now_ms=NOW_MS,
    )

    assert (
        evidence.status
        == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    )
    assert evidence.blockers == []
    assert evidence.promotion_gate_ready is True
    assert evidence.submit_rehearsal_ready is True
    assert evidence.duplicate_submit_replay_proof_ready is True
    assert evidence.duplicate_submit_replay_proof is not None
    assert evidence.duplicate_submit_replay_proof.status == (
        RuntimeExecutionDuplicateSubmitReplayProofStatus
        .READY_FOR_FIRST_REAL_SUBMIT_REPLAY_GUARD
    )
    assert evidence.prerequisite_evidence_proof_ready is True
    assert evidence.prerequisite_evidence_proof is not None
    assert evidence.prerequisite_evidence_proof.status == (
        RuntimeExecutionSubmitPrerequisiteEvidenceProofStatus
        .READY_FOR_FIRST_REAL_SUBMIT_PREREQUISITE_REVIEW
    )
    assert evidence.first_real_submit_confirmations.owner_real_submit_authorization_id == (
        "owner-real-submit-auth-1"
    )
    assert evidence.not_live_action_authorization is True
    assert evidence.not_exchange_submit_authority is True
    assert evidence.not_order_lifecycle_authority is True
    assert evidence.execution_intent_status_changed is False
    assert evidence.order_created is False
    assert evidence.order_lifecycle_called is False
    assert evidence.exchange_called is False
    assert evidence.exchange_order_submitted is False
    assert evidence.owner_bounded_execution_called is False
    assert evidence.runtime_state_mutated is False
    assert evidence.withdrawal_or_transfer_created is False


def test_first_real_submit_enablement_evidence_blocks_missing_owner_evidence():
    first_submit = _first_submit_confirmed(
        owner_real_submit_authorization_id=None,
        explicit_owner_real_submit_authorization=False,
    )
    rehearsal = _submit_rehearsal(
        decision=_decision(
            owner_real_submit_authorization_id=None,
            status=RuntimeExecutionExchangeSubmitGateStatus.BLOCKED,
            blockers=["owner_real_submit_authorization_id_missing"],
        )
    )

    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=rehearsal,
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        prerequisite_evidence_proof=_prerequisite_evidence_proof(),
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "submit_rehearsal_not_ready" in evidence.blockers
    assert (
        "promotion_gate:first_real_submit_owner_real_submit_authorization_id_missing"
        in evidence.blockers
    )
    assert (
        "promotion_gate:first_real_submit_explicit_owner_real_submit_authorization_missing"
        in evidence.blockers
    )


def test_first_real_submit_enablement_evidence_blocks_stale_gateway_readiness():
    first_submit = _first_submit_confirmed()
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(
            gateway=_gateway_readiness(created_at_ms=NOW_MS - 900_001),
        ),
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        prerequisite_evidence_proof=_prerequisite_evidence_proof(),
        now_ms=NOW_MS,
    )

    assert evidence.duplicate_submit_replay_proof_ready is True
    assert evidence.prerequisite_evidence_proof_ready is True

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "submit_rehearsal_not_ready" in evidence.blockers
    assert (
        "submit_rehearsal:runtime_exchange_gateway_readiness_stale"
        in evidence.blockers
    )
    assert evidence.submit_rehearsal_ready is False
    assert evidence.exchange_called is False


def test_first_real_submit_enablement_evidence_blocks_missing_duplicate_replay_proof():
    first_submit = _first_submit_confirmed()
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(),
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        prerequisite_evidence_proof=_prerequisite_evidence_proof(),
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "duplicate_submit_replay_proof_missing" in evidence.blockers
    assert evidence.duplicate_submit_replay_proof_ready is False
    assert evidence.exchange_called is False


def test_first_real_submit_enablement_evidence_blocks_missing_prerequisite_proof():
    first_submit = _first_submit_confirmed()
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(),
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "prerequisite_evidence_proof_missing" in evidence.blockers
    assert evidence.prerequisite_evidence_proof_ready is False
    assert evidence.exchange_called is False


def test_first_real_submit_enablement_evidence_blocks_unready_prerequisite_proof():
    first_submit = _first_submit_confirmed()
    proof = _prerequisite_evidence_proof(
        trusted_submit_facts=_trusted_submit_facts(facts_fresh_enough=False),
    )
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(),
        first_real_submit_confirmations=first_submit,
        promotion_gate_result=_promotion_gate(first_submit),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        prerequisite_evidence_proof=proof,
        now_ms=NOW_MS,
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "prerequisite_evidence_proof_not_ready" in evidence.blockers
    assert (
        "prerequisite_evidence_proof:trusted_submit_fact_snapshot_not_fresh_enough"
        in evidence.blockers
    )
    assert evidence.exchange_called is False


def test_first_real_submit_enablement_evidence_rejects_execution_metadata():
    evidence = build_runtime_execution_first_real_submit_enablement_evidence(
        submit_rehearsal=_submit_rehearsal(),
        first_real_submit_confirmations=_first_submit_confirmed(),
        promotion_gate_result=_promotion_gate(),
        duplicate_submit_replay_proof=_duplicate_replay_proof(),
        prerequisite_evidence_proof=_prerequisite_evidence_proof(),
        now_ms=NOW_MS,
    )
    payload = evidence.model_dump(mode="python")
    payload["metadata"] = {"exchange_payload": {"symbol": "BNB/USDT:USDT"}}

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionFirstRealSubmitEnablementEvidence.model_validate(payload)


@pytest.mark.asyncio
async def test_first_real_submit_enablement_evidence_service_defaults_evidence_ids():
    calls: list[dict] = []

    class FakeAdapterService:
        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            calls.append({"method": "enablement", "kwargs": kwargs})
            return _decision(authorization_id=authorization_id)

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            calls.append(
                {
                    "method": "rehearsal",
                    "decision": exchange_submit_enablement_decision,
                }
            )
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )
        submit_prerequisite_evidence_proof_for_authorization = staticmethod(
            _fake_prerequisite_evidence_proof
        )

    service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
    )

    evidence = await service.preview_for_authorization(
        "auth-1",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
        submit_idempotency_policy_id="submit-idempotency-auth-1",
        attempt_outcome_policy_id="attempt-outcome-auth-1",
        protection_creation_failure_policy_id="protection-failure-auth-1",
        local_registration_enablement_decision_id="local-registration-enable-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="lifecycle-submit-enable-auth-1",
        exchange_submit_adapter_enablement_id="adapter-enable-auth-1",
        exchange_submit_action_authorization_id="exchange-action-auth-1",
        deployment_readiness_evidence_id="runtime-gateway-readiness-auth-1",
        post_submit_budget_settlement_persistence_evidence_id=(
            POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
        ),
        budget_release_or_consume_rule_confirmed=True,
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert calls[0]["method"] == "enablement"
    assert calls[1]["method"] == "rehearsal"
    assert evidence.status == (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    )
    assert evidence.first_real_submit_confirmations.exchange_submit_enablement_decision_id == (
        "runtime-exchange-submit-enable-auth-1"
    )
    assert evidence.first_real_submit_confirmations.runtime_submit_rehearsal_id == (
        "runtime-submit-rehearsal-auth-1"
    )
    assert evidence.order_created is False
    assert evidence.exchange_called is False
    assert evidence.duplicate_submit_replay_proof_ready is True
    assert evidence.prerequisite_evidence_proof_ready is True


@pytest.mark.asyncio
async def test_first_real_submit_enablement_evidence_service_uses_decision_evidence_ids():
    calls: list[dict] = []

    class FakeAdapterService:
        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            calls.append({"method": "enablement", "kwargs": kwargs})
            assert kwargs["trusted_submit_fact_snapshot_id"] is None
            assert kwargs["submit_idempotency_policy_id"] is None
            assert kwargs["attempt_outcome_policy_id"] is None
            return _decision(authorization_id=authorization_id)

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            calls.append(
                {
                    "method": "rehearsal",
                    "decision": exchange_submit_enablement_decision,
                }
            )
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        async def duplicate_submit_replay_proof_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
            submit_idempotency_policy_id=None,
        ):
            calls.append(
                {
                    "method": "duplicate",
                    "submit_idempotency_policy_id": submit_idempotency_policy_id,
                }
            )
            return _duplicate_replay_proof(
                exchange_submit_enablement_decision,
                submit_idempotency_snapshot=_idempotency_snapshot(
                    submit_idempotency_policy_id=submit_idempotency_policy_id,
                    authorization_id=authorization_id,
                    execution_intent_id=(
                        exchange_submit_enablement_decision.execution_intent_id
                    ),
                    runtime_instance_id=(
                        exchange_submit_enablement_decision.runtime_instance_id
                    ),
                ),
            )

        async def submit_prerequisite_evidence_proof_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
            trusted_submit_fact_snapshot_id=None,
            attempt_outcome_policy_id=None,
            protection_creation_failure_policy_id=None,
        ):
            calls.append(
                {
                    "method": "prerequisite",
                    "trusted_submit_fact_snapshot_id": (
                        trusted_submit_fact_snapshot_id
                    ),
                    "attempt_outcome_policy_id": attempt_outcome_policy_id,
                    "protection_creation_failure_policy_id": (
                        protection_creation_failure_policy_id
                    ),
                }
            )
            return _prerequisite_evidence_proof(
                exchange_submit_enablement_decision
            )

    service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
    )

    evidence = await service.preview_for_authorization(
        "auth-1",
        budget_release_or_consume_rule_confirmed=True,
        post_submit_budget_settlement_persistence_evidence_id=(
            POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
        ),
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert calls[2] == {
        "method": "duplicate",
        "submit_idempotency_policy_id": "submit-idempotency-auth-1",
    }
    assert calls[3] == {
        "method": "prerequisite",
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-auth-1",
        "attempt_outcome_policy_id": "attempt-outcome-auth-1",
        "protection_creation_failure_policy_id": "protection-failure-auth-1",
    }
    assert evidence.status == (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    )
    assert evidence.first_real_submit_confirmations.trusted_submit_fact_snapshot_id == (
        "trusted-submit-facts-auth-1"
    )
    assert evidence.first_real_submit_confirmations.submit_idempotency_policy_id == (
        "submit-idempotency-auth-1"
    )
    assert evidence.first_real_submit_confirmations.attempt_outcome_policy_id == (
        "attempt-outcome-auth-1"
    )
    assert evidence.first_real_submit_confirmations.protection_creation_failure_policy_id == (
        "protection-failure-auth-1"
    )
    assert evidence.first_real_submit_confirmations.local_registration_enablement_decision_id == (
        "local-registration-enable-auth-1"
    )
    assert evidence.first_real_submit_confirmations.deployment_readiness_evidence_id == (
        "runtime-gateway-readiness-auth-1"
    )
    assert evidence.first_real_submit_confirmations.owner_real_submit_authorization_id == (
        "owner-real-submit-auth-1"
    )
    assert evidence.order_created is False
    assert evidence.exchange_called is False


@pytest.mark.asyncio
async def test_first_real_submit_enablement_evidence_service_resolves_recorded_evidence_ids():
    calls: list[dict] = []

    class FakeAdapterService:
        async def resolve_first_real_submit_evidence_ids_for_authorization(
            self,
            authorization_id,
        ):
            calls.append({"method": "resolve", "authorization_id": authorization_id})
            return {
                "trusted_submit_fact_snapshot_id": "trusted-submit-facts-auth-1",
                "submit_idempotency_policy_id": "submit-idempotency-auth-1",
                "attempt_outcome_policy_id": "attempt-outcome-auth-1",
                "post_submit_budget_settlement_persistence_evidence_id": (
                    POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
                ),
                "protection_creation_failure_policy_id": "protection-failure-auth-1",
            }

        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            calls.append({"method": "enablement", "kwargs": kwargs})
            assert kwargs["trusted_submit_fact_snapshot_id"] == (
                "trusted-submit-facts-auth-1"
            )
            assert kwargs["submit_idempotency_policy_id"] == (
                "submit-idempotency-auth-1"
            )
            assert kwargs["attempt_outcome_policy_id"] == "attempt-outcome-auth-1"
            assert kwargs["protection_creation_failure_policy_id"] == (
                "protection-failure-auth-1"
            )
            return _decision(authorization_id=authorization_id)

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            calls.append({"method": "rehearsal"})
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )
        submit_prerequisite_evidence_proof_for_authorization = staticmethod(
            _fake_prerequisite_evidence_proof
        )

    service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
    )

    evidence = await service.preview_for_authorization(
        "auth-1",
        budget_release_or_consume_rule_confirmed=True,
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert [call["method"] for call in calls[:3]] == [
        "resolve",
        "enablement",
        "rehearsal",
    ]
    assert evidence.status == (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    )
    assert evidence.first_real_submit_confirmations.trusted_submit_fact_snapshot_id == (
        "trusted-submit-facts-auth-1"
    )
    assert (
        evidence.first_real_submit_confirmations
        .post_submit_budget_settlement_persistence_evidence_id
        == POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
    )
    assert evidence.order_created is False
    assert evidence.exchange_called is False


@pytest.mark.asyncio
async def test_runtime_adapter_resolves_only_existing_deterministic_evidence_ids():
    class _DraftRepo:
        async def get(self, _draft_id):
            return None

    class _AuthorizationRepo:
        async def get(self, authorization_id):
            assert authorization_id == "auth-1"
            return SimpleNamespace(execution_intent_id="intent-1")

    class _Repo:
        def __init__(self, existing):
            self.existing = set(existing)
            self.requested: list[str] = []

        async def get(self, item_id):
            self.requested.append(item_id)
            if item_id not in self.existing:
                return None
            return SimpleNamespace(execution_intent_id="intent-1")

    trusted_repo = _Repo({"trusted-submit-facts-intent-1"})
    idempotency_repo = _Repo({"runtime-submit-idempotency-auth-1"})
    attempt_repo = _Repo(
        {
            "runtime-attempt-outcome-policy-runtime-attempt-reservation-auth-1-"
            "entry_filled_protection_creation_failed"
        }
    )
    protection_repo = _Repo({"runtime-protection-failure-policy-intent-1"})
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        submit_authorization_repository=_AuthorizationRepo(),
        trusted_submit_facts_repository=trusted_repo,
        submit_idempotency_repository=idempotency_repo,
        attempt_outcome_policy_repository=attempt_repo,
        post_submit_budget_settlement_repository=object(),
        protection_failure_policy_repository=protection_repo,
    )

    resolved = await service.resolve_first_real_submit_evidence_ids_for_authorization(
        "auth-1"
    )

    assert resolved == {
        "submit_idempotency_policy_id": "runtime-submit-idempotency-auth-1",
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-intent-1",
        "attempt_outcome_policy_id": (
            "runtime-attempt-outcome-policy-runtime-attempt-reservation-auth-1-"
            "entry_filled_protection_creation_failed"
        ),
        "post_submit_budget_settlement_persistence_evidence_id": (
            POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
        ),
        "protection_creation_failure_policy_id": (
            "runtime-protection-failure-policy-intent-1"
        ),
    }


@pytest.mark.asyncio
async def test_first_real_submit_evidence_preparation_records_machine_evidence_only():
    calls: list[dict] = []

    class FakeAdapterService:
        async def controlled_submit_plan_for_authorization(self, authorization_id):
            calls.append({"method": "plan", "authorization_id": authorization_id})
            return SimpleNamespace(
                plan_id="runtime-controlled-submit-plan-auth-1",
                execution_intent_id="intent-1",
                runtime_instance_id="runtime-1",
                source_id="candidate-1",
                semantic_ids=_semantic_ids(),
                symbol="BNB/USDT:USDT",
                side="long",
            )

        async def record_submit_idempotency_snapshot_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            calls.append(
                {
                    "method": "idempotency",
                    "authorization_id": authorization_id,
                    "kwargs": kwargs,
                }
            )
            return SimpleNamespace(
                submit_idempotency_policy_id="submit-idempotency-auth-1",
                warnings=[],
            )

        async def record_protection_failure_policy_for_intent(
            self,
            execution_intent_id,
        ):
            calls.append(
                {
                    "method": "protection_failure",
                    "execution_intent_id": execution_intent_id,
                }
            )
            return SimpleNamespace(
                policy_id="protection-failure-auth-1",
                warnings=[],
            )

        async def resolve_first_real_submit_evidence_ids_for_authorization(
            self,
            authorization_id,
        ):
            calls.append({"method": "resolve", "authorization_id": authorization_id})
            return {
                "post_submit_budget_settlement_persistence_evidence_id": (
                    POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
                )
            }

        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            calls.append({"method": "enablement", "kwargs": kwargs})
            return _decision(
                authorization_id=authorization_id,
                trusted_submit_fact_snapshot_id=(
                    kwargs["trusted_submit_fact_snapshot_id"]
                ),
                submit_idempotency_policy_id=(
                    kwargs["submit_idempotency_policy_id"]
                ),
                attempt_outcome_policy_id=kwargs["attempt_outcome_policy_id"],
                protection_creation_failure_policy_id=(
                    kwargs["protection_creation_failure_policy_id"]
                ),
                owner_real_submit_authorization_id=None,
                deployment_readiness_evidence_id=None,
            )

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            calls.append({"method": "rehearsal"})
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )

        async def submit_prerequisite_evidence_proof_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
            trusted_submit_fact_snapshot_id=None,
            attempt_outcome_policy_id=None,
            protection_creation_failure_policy_id=None,
        ):
            calls.append(
                {
                    "method": "prerequisite",
                    "attempt_outcome_policy_id": attempt_outcome_policy_id,
                }
            )
            return build_runtime_execution_submit_prerequisite_evidence_proof(
                enablement_decision=exchange_submit_enablement_decision,
                trusted_submit_facts=_trusted_submit_facts(
                    exchange_submit_enablement_decision
                ),
                attempt_outcome_policy=None,
                protection_failure_policy=_protection_failure_policy(
                    exchange_submit_enablement_decision
                ),
                trusted_submit_facts_repository_available=True,
                attempt_outcome_policy_repository_available=True,
                protection_failure_policy_repository_available=True,
                now_ms=NOW_MS,
            )

    class FakeTrustedFactsAssembly:
        async def assemble_and_record_snapshot_for_controlled_submit_plan(
            self,
            *,
            plan,
            now_ms,
            metadata=None,
        ):
            calls.append(
                {
                    "method": "trusted_facts",
                    "plan_id": plan.plan_id,
                    "metadata": metadata,
                }
            )
            return SimpleNamespace(
                trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
                warnings=[],
            )

    service = RuntimeExecutionFirstRealSubmitEvidencePreparationService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
        trusted_submit_facts_assembly_service=FakeTrustedFactsAssembly(),
    )

    preparation = await service.prepare_for_authorization("auth-1")

    assert preparation.status == (
        RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
        .PREPARED_EVIDENCE_BLOCKED
    )
    assert preparation.prepared_evidence_ids == {
        "submit_idempotency_policy_id": "submit-idempotency-auth-1",
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-auth-1",
        "protection_creation_failure_policy_id": "protection-failure-auth-1",
    }
    assert "attempt_outcome_policy_id" not in preparation.prepared_evidence_ids
    assert (
        "attempt_outcome_policy_not_auto_prepared_requires_existing_attempt_"
        "reservation_or_submit_outcome_review"
    ) in preparation.skipped_evidence
    assert "owner_real_submit_authorization_not_auto_created" in (
        preparation.skipped_evidence
    )
    assert "deployment_readiness_evidence_not_auto_created" in (
        preparation.skipped_evidence
    )
    assert preparation.not_live_action_authorization is True
    assert preparation.order_created is False
    assert preparation.order_lifecycle_called is False
    assert preparation.exchange_called is False
    assert preparation.enablement_evidence is not None
    assert preparation.enablement_evidence.status == (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    )
    assert preparation.enablement_evidence.exchange_called is False
    assert [call["method"] for call in calls[:5]] == [
        "plan",
        "idempotency",
        "trusted_facts",
        "protection_failure",
        "resolve",
    ]
    assert "attempt_outcome_policy" not in [call["method"] for call in calls]


@pytest.mark.asyncio
async def test_first_real_submit_enablement_evidence_blocks_mismatched_evidence_ids():
    class FakeAdapterService:
        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **_kwargs,
        ):
            return _decision(authorization_id=authorization_id)

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )
        submit_prerequisite_evidence_proof_for_authorization = staticmethod(
            _fake_prerequisite_evidence_proof
        )

    service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
    )

    evidence = await service.preview_for_authorization(
        "auth-1",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
        submit_idempotency_policy_id="submit-idempotency-auth-1",
        attempt_outcome_policy_id="attempt-outcome-auth-1",
        protection_creation_failure_policy_id="protection-failure-auth-1",
        local_registration_enablement_decision_id="local-registration-enable-auth-1",
        exchange_submit_enablement_decision_id="wrong-exchange-submit-enable",
        runtime_submit_rehearsal_id="wrong-runtime-submit-rehearsal",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="lifecycle-submit-enable-auth-1",
        exchange_submit_adapter_enablement_id="adapter-enable-auth-1",
        exchange_submit_action_authorization_id="exchange-action-auth-1",
        deployment_readiness_evidence_id="runtime-gateway-readiness-auth-1",
        budget_release_or_consume_rule_confirmed=True,
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "exchange_submit_enablement_decision_id_mismatch" in evidence.blockers
    assert "runtime_submit_rehearsal_id_mismatch" in evidence.blockers
    assert evidence.order_created is False
    assert evidence.order_lifecycle_called is False
    assert evidence.exchange_called is False
    assert evidence.withdrawal_or_transfer_created is False


@pytest.mark.asyncio
async def test_first_real_submit_enablement_evidence_blocks_underlying_evidence_mismatch():
    class FakeAdapterService:
        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **_kwargs,
        ):
            return _decision(
                authorization_id=authorization_id,
                trusted_submit_fact_snapshot_id="trusted-submit-facts-other",
            )

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )
        submit_prerequisite_evidence_proof_for_authorization = staticmethod(
            _fake_prerequisite_evidence_proof
        )

    service = RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
        runtime_execution_intent_adapter_service=FakeAdapterService(),
    )

    evidence = await service.preview_for_authorization(
        "auth-1",
        trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
        submit_idempotency_policy_id="submit-idempotency-auth-1",
        attempt_outcome_policy_id="attempt-outcome-auth-1",
        protection_creation_failure_policy_id="protection-failure-auth-1",
        local_registration_enablement_decision_id="local-registration-enable-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        order_lifecycle_submit_enablement_id="lifecycle-submit-enable-auth-1",
        exchange_submit_adapter_enablement_id="adapter-enable-auth-1",
        exchange_submit_action_authorization_id="exchange-action-auth-1",
        deployment_readiness_evidence_id="runtime-gateway-readiness-auth-1",
        budget_release_or_consume_rule_confirmed=True,
        protection_creation_failure_policy_confirmed=True,
        duplicate_submit_policy_confirmed=True,
        deployment_readiness_confirmed=True,
        explicit_owner_real_submit_authorization=True,
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
    )

    assert evidence.status == RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus.BLOCKED
    assert "trusted_submit_fact_snapshot_id_mismatch" in evidence.blockers
    assert evidence.submit_rehearsal.trusted_submit_fact_snapshot_id == (
        "trusted-submit-facts-other"
    )
    assert evidence.order_created is False
    assert evidence.order_lifecycle_called is False
    assert evidence.exchange_called is False


@pytest.mark.asyncio
async def test_trading_console_first_real_submit_packet_api(monkeypatch):
    class FakeAdapterService:
        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **_kwargs,
        ):
            return _decision(authorization_id=authorization_id)

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )
        submit_prerequisite_evidence_proof_for_authorization = staticmethod(
            _fake_prerequisite_evidence_proof
        )

    async def fake_adapter_factory(*, include_runtime_exchange_gateway=False):
        assert include_runtime_exchange_gateway is False
        return FakeAdapterService()

    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_intent_adapter_service",
        fake_adapter_factory,
    )

    evidence = await (
        trading_console_api
        .runtime_execution_first_real_submit_enablement_evidence_for_authorization(
            "auth-1",
            strategy_family_confirmed=True,
            implementation_source_confirmed=True,
            required_facts_confirmed=True,
            entry_policy_confirmed=True,
            exit_policy_confirmed=True,
            protection_policy_confirmed=True,
            eligible_for_runtime_execution_confirmed=True,
            right_tail_review_metrics_confirmed=True,
            runtime_profile_confirmed=True,
            owner_confirmation_mode_confirmed=True,
            symbol_side_boundary_confirmed=True,
            max_loss_budget_confirmed=True,
            max_notional_boundary_confirmed=True,
            max_active_positions_boundary_confirmed=True,
            max_leverage_boundary_confirmed=True,
            margin_usage_boundary_confirmed=True,
            liquidation_buffer_boundary_confirmed=True,
            protection_readiness_source_confirmed=True,
            stale_fact_behavior_confirmed=True,
            attempt_consumption_rule_confirmed=True,
            budget_reservation_rule_confirmed=True,
            trusted_active_position_source_confirmed=True,
            trusted_account_fact_source_confirmed=True,
            budget_release_or_consume_rule_confirmed=True,
            post_submit_budget_settlement_persistence_evidence_id=(
                POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
            ),
            attempt_outcome_policy_id="attempt-outcome-auth-1",
            protection_creation_failure_policy_confirmed=True,
            protection_creation_failure_policy_id="protection-failure-auth-1",
            duplicate_submit_policy_confirmed=True,
            submit_idempotency_policy_id="submit-idempotency-auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
            local_registration_enablement_decision_id=(
                "local-registration-enable-auth-1"
            ),
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
            order_lifecycle_submit_enablement_id="lifecycle-submit-enable-auth-1",
            exchange_submit_adapter_enablement_id="adapter-enable-auth-1",
            exchange_submit_action_authorization_id="exchange-action-auth-1",
            deployment_readiness_evidence_id="runtime-gateway-readiness-auth-1",
            deployment_readiness_confirmed=True,
            explicit_owner_real_submit_authorization=True,
        )
    )

    assert evidence.authorization_id == "auth-1"
    assert evidence.status == (
        RuntimeExecutionFirstRealSubmitEnablementEvidenceStatus
        .READY_FOR_OWNER_FINAL_REVIEW
    )
    assert evidence.promotion_gate_result is not None
    assert evidence.promotion_gate_result.not_execution_authority is True
    assert evidence.submit_rehearsal.not_live_action_authorization is True
    assert evidence.exchange_called is False


@pytest.mark.asyncio
async def test_trading_console_first_real_submit_evidence_preparation_api(
    monkeypatch,
):
    class FakeAdapterService:
        async def controlled_submit_plan_for_authorization(self, authorization_id):
            return SimpleNamespace(
                plan_id="runtime-controlled-submit-plan-auth-1",
                execution_intent_id="intent-1",
                runtime_instance_id="runtime-1",
                source_id="candidate-1",
                semantic_ids=_semantic_ids(),
                symbol="BNB/USDT:USDT",
                side="long",
            )

        async def record_submit_idempotency_snapshot_for_authorization(
            self,
            authorization_id,
            **_kwargs,
        ):
            return SimpleNamespace(
                submit_idempotency_policy_id="submit-idempotency-auth-1",
                warnings=[],
            )

        async def record_protection_failure_policy_for_intent(
            self,
            execution_intent_id,
        ):
            return SimpleNamespace(
                policy_id="protection-failure-auth-1",
                warnings=[],
            )

        async def resolve_first_real_submit_evidence_ids_for_authorization(
            self,
            authorization_id,
        ):
            return {
                "post_submit_budget_settlement_persistence_evidence_id": (
                    POST_SUBMIT_BUDGET_SETTLEMENT_PERSISTENCE_EVIDENCE_ID
                )
            }

        async def exchange_submit_enablement_decision_for_authorization(
            self,
            authorization_id,
            **kwargs,
        ):
            return _decision(
                authorization_id=authorization_id,
                trusted_submit_fact_snapshot_id=(
                    kwargs["trusted_submit_fact_snapshot_id"]
                ),
                submit_idempotency_policy_id=(
                    kwargs["submit_idempotency_policy_id"]
                ),
                attempt_outcome_policy_id=kwargs["attempt_outcome_policy_id"],
                protection_creation_failure_policy_id=(
                    kwargs["protection_creation_failure_policy_id"]
                ),
            )

        async def submit_rehearsal_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
        ):
            return _submit_rehearsal(decision=exchange_submit_enablement_decision)

        duplicate_submit_replay_proof_for_authorization = staticmethod(
            _fake_duplicate_replay_proof
        )

        async def submit_prerequisite_evidence_proof_for_authorization(
            self,
            authorization_id,
            *,
            exchange_submit_enablement_decision,
            trusted_submit_fact_snapshot_id=None,
            attempt_outcome_policy_id=None,
            protection_creation_failure_policy_id=None,
        ):
            return build_runtime_execution_submit_prerequisite_evidence_proof(
                enablement_decision=exchange_submit_enablement_decision,
                trusted_submit_facts=_trusted_submit_facts(
                    exchange_submit_enablement_decision
                ),
                attempt_outcome_policy=None,
                protection_failure_policy=_protection_failure_policy(
                    exchange_submit_enablement_decision
                ),
                trusted_submit_facts_repository_available=True,
                attempt_outcome_policy_repository_available=True,
                protection_failure_policy_repository_available=True,
                now_ms=NOW_MS,
            )

    class FakeTrustedFactsAssembly:
        async def assemble_and_record_snapshot_for_controlled_submit_plan(
            self,
            *,
            plan,
            now_ms,
            metadata=None,
        ):
            return SimpleNamespace(
                trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
                warnings=[],
            )

    async def fake_adapter_factory(*, include_runtime_exchange_gateway=False):
        assert include_runtime_exchange_gateway is False
        return FakeAdapterService()

    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_intent_adapter_service",
        fake_adapter_factory,
    )
    monkeypatch.setattr(
        trading_console_api,
        "_runtime_execution_trusted_submit_facts_assembly_service",
        lambda: FakeTrustedFactsAssembly(),
    )

    preparation = await (
        trading_console_api
        .runtime_execution_first_real_submit_evidence_preparation_for_authorization(
            "auth-1",
        )
    )

    assert preparation.authorization_id == "auth-1"
    assert preparation.status == (
        RuntimeExecutionFirstRealSubmitEvidencePreparationStatus
        .PREPARED_EVIDENCE_BLOCKED
    )
    assert preparation.prepared_evidence_ids[
        "trusted_submit_fact_snapshot_id"
    ] == "trusted-submit-facts-auth-1"
    assert preparation.not_exchange_submit_authority is True
    assert preparation.order_created is False
    assert preparation.exchange_called is False
