"""Application service for first-real-submit enablement review packets."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
)
from src.domain.runtime_execution_first_real_submit_enablement_packet import (
    RuntimeExecutionFirstRealSubmitEnablementPacket,
    build_runtime_execution_first_real_submit_enablement_packet,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)


class RuntimeExecutionFirstRealSubmitEnablementPacketService:
    """Build a read-only Owner/Codex packet before any first real submit.

    The service orchestrates existing preview/readiness services only. It does
    not persist records, create orders, mutate runtime state, call
    OrderLifecycle, call exchange, or authorize real live action.
    """

    def __init__(
        self,
        *,
        runtime_execution_intent_adapter_service: object,
        promotion_gate_service: StrategyRuntimePromotionGateService | None = None,
    ) -> None:
        self._adapter_service = runtime_execution_intent_adapter_service
        self._promotion_gate_service = (
            promotion_gate_service or StrategyRuntimePromotionGateService()
        )

    async def preview_for_authorization(
        self,
        authorization_id: str,
        *,
        trusted_submit_fact_snapshot_id: str | None = None,
        submit_idempotency_policy_id: str | None = None,
        attempt_outcome_policy_id: str | None = None,
        protection_creation_failure_policy_id: str | None = None,
        local_registration_enablement_decision_id: str | None = None,
        exchange_submit_enablement_decision_id: str | None = None,
        owner_real_submit_authorization_id: str | None = None,
        order_lifecycle_submit_enablement_id: str | None = None,
        exchange_submit_adapter_enablement_id: str | None = None,
        exchange_submit_action_authorization_id: str | None = None,
        runtime_submit_rehearsal_id: str | None = None,
        deployment_readiness_evidence_id: str | None = None,
        budget_release_or_consume_rule_confirmed: bool = False,
        protection_creation_failure_policy_confirmed: bool = False,
        duplicate_submit_policy_confirmed: bool = False,
        deployment_readiness_confirmed: bool = False,
        explicit_owner_real_submit_authorization: bool = False,
        semantic_confirmations: StrategySemanticsConfirmationFacts | None = None,
        runtime_confirmations: RuntimeExecutionConfirmationFacts | None = None,
    ) -> RuntimeExecutionFirstRealSubmitEnablementPacket:
        enablement = await (
            self._adapter_service.exchange_submit_enablement_decision_for_authorization(
                authorization_id,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
                local_registration_enablement_decision_id=(
                    local_registration_enablement_decision_id
                ),
                owner_real_submit_authorization_id=(
                    owner_real_submit_authorization_id
                ),
                order_lifecycle_submit_enablement_id=(
                    order_lifecycle_submit_enablement_id
                ),
                exchange_submit_adapter_enablement_id=(
                    exchange_submit_adapter_enablement_id
                ),
                exchange_submit_action_authorization_id=(
                    exchange_submit_action_authorization_id
                ),
                deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            )
        )
        submit_rehearsal = await (
            self._adapter_service.submit_rehearsal_for_authorization(
                authorization_id,
                exchange_submit_enablement_decision=enablement,
            )
        )
        additional_blockers: list[str] = []
        duplicate_submit_replay_proof = None
        proof_method = getattr(
            self._adapter_service,
            "duplicate_submit_replay_proof_for_authorization",
            None,
        )
        if callable(proof_method):
            duplicate_submit_replay_proof = await proof_method(
                authorization_id,
                exchange_submit_enablement_decision=enablement,
                submit_idempotency_policy_id=submit_idempotency_policy_id,
            )
        else:
            additional_blockers.append("duplicate_submit_replay_proof_unavailable")
        prerequisite_evidence_proof = None
        prerequisite_proof_method = getattr(
            self._adapter_service,
            "submit_prerequisite_evidence_proof_for_authorization",
            None,
        )
        if callable(prerequisite_proof_method):
            prerequisite_evidence_proof = await prerequisite_proof_method(
                authorization_id,
                exchange_submit_enablement_decision=enablement,
                trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
                attempt_outcome_policy_id=attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    protection_creation_failure_policy_id
                ),
            )
        else:
            additional_blockers.append("prerequisite_evidence_proof_unavailable")
        actual_exchange_submit_enablement_decision_id = getattr(
            enablement,
            "decision_id",
            None,
        )
        actual_runtime_submit_rehearsal_id = getattr(
            submit_rehearsal,
            "rehearsal_id",
            None,
        )
        if (
            exchange_submit_enablement_decision_id
            and actual_exchange_submit_enablement_decision_id
            and exchange_submit_enablement_decision_id
            != actual_exchange_submit_enablement_decision_id
        ):
            additional_blockers.append(
                "exchange_submit_enablement_decision_id_mismatch"
            )
        if (
            runtime_submit_rehearsal_id
            and actual_runtime_submit_rehearsal_id
            and runtime_submit_rehearsal_id != actual_runtime_submit_rehearsal_id
        ):
            additional_blockers.append("runtime_submit_rehearsal_id_mismatch")
        _append_evidence_id_mismatches(
            additional_blockers,
            expected={
                "trusted_submit_fact_snapshot_id": trusted_submit_fact_snapshot_id,
                "submit_idempotency_policy_id": submit_idempotency_policy_id,
                "attempt_outcome_policy_id": attempt_outcome_policy_id,
                "protection_creation_failure_policy_id": (
                    protection_creation_failure_policy_id
                ),
                "local_registration_enablement_decision_id": (
                    local_registration_enablement_decision_id
                ),
                "owner_real_submit_authorization_id": (
                    owner_real_submit_authorization_id
                ),
                "order_lifecycle_submit_enablement_id": (
                    order_lifecycle_submit_enablement_id
                ),
                "exchange_submit_adapter_enablement_id": (
                    exchange_submit_adapter_enablement_id
                ),
                "exchange_submit_action_authorization_id": (
                    exchange_submit_action_authorization_id
                ),
                "deployment_readiness_evidence_id": (
                    deployment_readiness_evidence_id
                ),
            },
            artifacts=(enablement, submit_rehearsal),
        )
        first_real_submit_confirmations = FirstRealSubmitConfirmationFacts(
            budget_release_or_consume_rule_confirmed=(
                budget_release_or_consume_rule_confirmed
            ),
            attempt_outcome_policy_id=attempt_outcome_policy_id,
            protection_creation_failure_policy_confirmed=(
                protection_creation_failure_policy_confirmed
            ),
            protection_creation_failure_policy_id=(
                protection_creation_failure_policy_id
            ),
            duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
            submit_idempotency_policy_id=submit_idempotency_policy_id,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            local_registration_enablement_decision_id=(
                local_registration_enablement_decision_id
            ),
            exchange_submit_enablement_decision_id=(
                exchange_submit_enablement_decision_id
                or actual_exchange_submit_enablement_decision_id
            ),
            runtime_submit_rehearsal_id=(
                runtime_submit_rehearsal_id
                or actual_runtime_submit_rehearsal_id
            ),
            deployment_readiness_evidence_id=deployment_readiness_evidence_id,
            owner_real_submit_authorization_id=(
                owner_real_submit_authorization_id
            ),
            deployment_readiness_confirmed=deployment_readiness_confirmed,
            explicit_owner_real_submit_authorization=(
                explicit_owner_real_submit_authorization
            ),
        )

        promotion_gate_result: StrategyRuntimePromotionGateResult | None = None
        promotion_gate_error: str | None = None
        semantic_ids = submit_rehearsal.semantic_ids
        if not semantic_ids.strategy_family_id or not semantic_ids.strategy_family_version_id:
            promotion_gate_error = "strategy_semantic_ids_missing"
        else:
            try:
                promotion_gate_result = self._promotion_gate_service.preview(
                    strategy_family_id=semantic_ids.strategy_family_id,
                    strategy_family_version_id=(
                        semantic_ids.strategy_family_version_id
                    ),
                    scope=(
                        StrategyRuntimePromotionScope
                        .FIRST_REAL_SUBMIT_GATE_REVIEW
                    ),
                    semantic_confirmations=(
                        semantic_confirmations
                        or StrategySemanticsConfirmationFacts()
                    ),
                    runtime_confirmations=(
                        runtime_confirmations
                        or RuntimeExecutionConfirmationFacts()
                    ),
                    first_real_submit_confirmations=(
                        first_real_submit_confirmations
                    ),
                )
            except Exception as exc:
                promotion_gate_error = str(exc)

        return build_runtime_execution_first_real_submit_enablement_packet(
            submit_rehearsal=submit_rehearsal,
            first_real_submit_confirmations=first_real_submit_confirmations,
            promotion_gate_result=promotion_gate_result,
            duplicate_submit_replay_proof=duplicate_submit_replay_proof,
            prerequisite_evidence_proof=prerequisite_evidence_proof,
            promotion_gate_error=promotion_gate_error,
            additional_blockers=additional_blockers,
            now_ms=_now_ms(),
        )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _append_evidence_id_mismatches(
    blockers: list[str],
    *,
    expected: dict[str, str | None],
    artifacts: tuple[object, ...],
) -> None:
    for field_name, expected_value in expected.items():
        normalized_expected = _normalized_optional(expected_value)
        if not normalized_expected:
            continue
        for artifact in artifacts:
            actual = _normalized_optional(getattr(artifact, field_name, None))
            if actual != normalized_expected:
                blockers.append(f"{field_name}_mismatch")
                break


def _normalized_optional(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
