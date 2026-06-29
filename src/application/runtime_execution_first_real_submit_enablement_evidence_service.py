"""Application service for first-real-submit enablement review evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
)
from src.domain.runtime_execution_first_real_submit_enablement_evidence import (
    RuntimeExecutionFirstRealSubmitEnablementEvidence,
    build_runtime_execution_first_real_submit_enablement_evidence,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)


class RuntimeExecutionFirstRealSubmitEnablementEvidenceService:
    """Build read-only Owner/Codex evidence before any first real submit.

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
        post_submit_budget_settlement_persistence_evidence_id: str | None = None,
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
    ) -> RuntimeExecutionFirstRealSubmitEnablementEvidence:
        additional_blockers: list[str] = []
        additional_warnings: list[str] = []
        resolved_evidence_ids = (
            await self._resolve_first_real_submit_evidence_ids(authorization_id)
        )
        effective_trusted_submit_fact_snapshot_id = _first_present(
            trusted_submit_fact_snapshot_id,
            resolved_evidence_ids.get("trusted_submit_fact_snapshot_id"),
        )
        effective_submit_idempotency_policy_id = _first_present(
            submit_idempotency_policy_id,
            resolved_evidence_ids.get("submit_idempotency_policy_id"),
        )
        effective_attempt_outcome_policy_id = _first_present(
            attempt_outcome_policy_id,
            resolved_evidence_ids.get("attempt_outcome_policy_id"),
        )
        effective_post_submit_budget_settlement_persistence_evidence_id = (
            _first_present(
                post_submit_budget_settlement_persistence_evidence_id,
                resolved_evidence_ids.get(
                    "post_submit_budget_settlement_persistence_evidence_id"
                ),
            )
        )
        effective_protection_creation_failure_policy_id = _first_present(
            protection_creation_failure_policy_id,
            resolved_evidence_ids.get("protection_creation_failure_policy_id"),
        )
        enablement = await (
            self._adapter_service.exchange_submit_enablement_decision_for_authorization(
                authorization_id,
                trusted_submit_fact_snapshot_id=(
                    effective_trusted_submit_fact_snapshot_id
                ),
                submit_idempotency_policy_id=(
                    effective_submit_idempotency_policy_id
                ),
                attempt_outcome_policy_id=effective_attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    effective_protection_creation_failure_policy_id
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
        effective_trusted_submit_fact_snapshot_id = _first_present(
            trusted_submit_fact_snapshot_id,
            effective_trusted_submit_fact_snapshot_id,
            getattr(enablement, "trusted_submit_fact_snapshot_id", None),
        )
        effective_submit_idempotency_policy_id = _first_present(
            submit_idempotency_policy_id,
            effective_submit_idempotency_policy_id,
            getattr(enablement, "submit_idempotency_policy_id", None),
        )
        effective_attempt_outcome_policy_id = _first_present(
            attempt_outcome_policy_id,
            effective_attempt_outcome_policy_id,
            getattr(enablement, "attempt_outcome_policy_id", None),
        )
        effective_protection_creation_failure_policy_id = _first_present(
            protection_creation_failure_policy_id,
            effective_protection_creation_failure_policy_id,
            getattr(enablement, "protection_creation_failure_policy_id", None),
        )
        effective_local_registration_enablement_decision_id = _first_present(
            local_registration_enablement_decision_id,
            getattr(enablement, "local_registration_enablement_decision_id", None),
        )
        effective_owner_real_submit_authorization_id = _first_present(
            owner_real_submit_authorization_id,
            getattr(enablement, "owner_real_submit_authorization_id", None),
        )
        effective_deployment_readiness_evidence_id = _first_present(
            deployment_readiness_evidence_id,
            getattr(enablement, "deployment_readiness_evidence_id", None),
        )
        submit_rehearsal = await (
            self._adapter_service.submit_rehearsal_for_authorization(
                authorization_id,
                exchange_submit_enablement_decision=enablement,
            )
        )
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
                submit_idempotency_policy_id=(
                    effective_submit_idempotency_policy_id
                ),
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
                trusted_submit_fact_snapshot_id=(
                    effective_trusted_submit_fact_snapshot_id
                ),
                attempt_outcome_policy_id=effective_attempt_outcome_policy_id,
                protection_creation_failure_policy_id=(
                    effective_protection_creation_failure_policy_id
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
        effective_exchange_submit_enablement_decision_id = _first_present(
            exchange_submit_enablement_decision_id,
            actual_exchange_submit_enablement_decision_id,
        )
        effective_runtime_submit_rehearsal_id = _first_present(
            runtime_submit_rehearsal_id,
            actual_runtime_submit_rehearsal_id,
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
            post_submit_budget_settlement_persistence_confirmed=bool(
                effective_post_submit_budget_settlement_persistence_evidence_id
            ),
            post_submit_budget_settlement_persistence_evidence_id=(
                effective_post_submit_budget_settlement_persistence_evidence_id
            ),
            attempt_outcome_policy_id=effective_attempt_outcome_policy_id,
            protection_creation_failure_policy_confirmed=(
                protection_creation_failure_policy_confirmed
            ),
            protection_creation_failure_policy_id=(
                effective_protection_creation_failure_policy_id
            ),
            duplicate_submit_policy_confirmed=duplicate_submit_policy_confirmed,
            submit_idempotency_policy_id=(
                effective_submit_idempotency_policy_id
            ),
            trusted_submit_fact_snapshot_id=(
                effective_trusted_submit_fact_snapshot_id
            ),
            local_registration_enablement_decision_id=(
                effective_local_registration_enablement_decision_id
            ),
            exchange_submit_enablement_decision_id=(
                effective_exchange_submit_enablement_decision_id
            ),
            runtime_submit_rehearsal_id=effective_runtime_submit_rehearsal_id,
            deployment_readiness_evidence_id=(
                effective_deployment_readiness_evidence_id
            ),
            owner_real_submit_authorization_id=(
                effective_owner_real_submit_authorization_id
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

        return build_runtime_execution_first_real_submit_enablement_evidence(
            submit_rehearsal=submit_rehearsal,
            first_real_submit_confirmations=first_real_submit_confirmations,
            promotion_gate_result=promotion_gate_result,
            duplicate_submit_replay_proof=duplicate_submit_replay_proof,
            prerequisite_evidence_proof=prerequisite_evidence_proof,
            promotion_gate_error=promotion_gate_error,
            additional_blockers=additional_blockers,
            additional_warnings=additional_warnings,
            now_ms=_now_ms(),
        )

    async def _resolve_first_real_submit_evidence_ids(
        self,
        authorization_id: str,
    ) -> dict[str, str]:
        resolver = getattr(
            self._adapter_service,
            "resolve_first_real_submit_evidence_ids_for_authorization",
            None,
        )
        if not callable(resolver):
            return {}
        resolved = await resolver(authorization_id)
        if not isinstance(resolved, Mapping):
            return {}
        result: dict[str, str] = {}
        for key, value in resolved.items():
            normalized = _normalized_optional(value)
            if normalized:
                result[str(key)] = normalized
        return result


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


def _first_present(*values: object) -> str | None:
    for value in values:
        normalized = _normalized_optional(value)
        if normalized:
            return normalized
    return None


def _normalized_optional(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
