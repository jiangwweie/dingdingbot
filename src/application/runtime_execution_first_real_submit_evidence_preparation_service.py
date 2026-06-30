"""Prepare machine evidence for first-real-submit Owner review evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from src.application.runtime_execution_first_real_submit_enablement_evidence_service import (
    RuntimeExecutionFirstRealSubmitEnablementEvidenceService,
)
from src.application.runtime_execution_trusted_submit_facts_service import (
    RuntimeExecutionTrustedSubmitFactsAssemblyService,
)
from src.domain.runtime_execution_first_real_submit_evidence_preparation import (
    RuntimeExecutionFirstRealSubmitEvidencePreparation,
    build_runtime_execution_first_real_submit_evidence_preparation,
)
from src.domain.strategy_runtime_promotion_gate import (
    RuntimeExecutionConfirmationFacts,
    StrategySemanticsConfirmationFacts,
)


class RuntimeExecutionFirstRealSubmitEvidencePreparationService:
    """Record non-executing evidence that is safe to machine-prepare.

    This service deliberately does not create Owner live authorization,
    deployment readiness, exchange action authorization, orders, exchange calls,
    or runtime attempt mutations. It only prepares evidence records that are
    already modeled as non-executing prerequisites.
    """

    def __init__(
        self,
        *,
        runtime_execution_intent_adapter_service: object,
        trusted_submit_facts_assembly_service: (
            RuntimeExecutionTrustedSubmitFactsAssemblyService | object | None
        ) = None,
        enablement_evidence_service: (
            RuntimeExecutionFirstRealSubmitEnablementEvidenceService | None
        ) = None,
    ) -> None:
        self._adapter_service = runtime_execution_intent_adapter_service
        self._trusted_submit_facts_assembly_service = (
            trusted_submit_facts_assembly_service
        )
        self._evidence_service = (
            enablement_evidence_service
            or RuntimeExecutionFirstRealSubmitEnablementEvidenceService(
                runtime_execution_intent_adapter_service=(
                    runtime_execution_intent_adapter_service
                )
            )
        )

    async def prepare_for_authorization(
        self,
        authorization_id: str,
        *,
        adapter_result_store_implemented: bool = False,
        real_adapter_boundary_implemented: bool = False,
        semantic_confirmations: StrategySemanticsConfirmationFacts | None = None,
        runtime_confirmations: RuntimeExecutionConfirmationFacts | None = None,
    ) -> RuntimeExecutionFirstRealSubmitEvidencePreparation:
        prepared_evidence_ids: dict[str, str] = {}
        available_evidence_ids: dict[str, str] = {}
        blockers: list[str] = []
        warnings: list[str] = []
        skipped_evidence = [
            "attempt_outcome_policy_not_auto_prepared_requires_existing_attempt_"
            "reservation_or_submit_outcome_review",
            "owner_real_submit_authorization_not_auto_created",
            "deployment_readiness_evidence_not_auto_created",
            "local_registration_enablement_decision_not_persisted_by_preparation",
            "local_registration_action_authorization_not_auto_created",
            "exchange_submit_action_authorization_not_auto_created",
        ]

        plan = None
        try:
            plan = await self._adapter_service.controlled_submit_plan_for_authorization(
                authorization_id
            )
        except Exception as exc:
            blockers.append(
                _error_code("controlled_submit_plan_unavailable", exc)
            )

        if plan is not None:
            await self._prepare_submit_idempotency(
                authorization_id,
                prepared_evidence_ids=prepared_evidence_ids,
                warnings=warnings,
                blockers=blockers,
                adapter_result_store_implemented=(
                    adapter_result_store_implemented
                ),
                real_adapter_boundary_implemented=(
                    real_adapter_boundary_implemented
                ),
            )
            await self._prepare_trusted_submit_facts(
                plan,
                prepared_evidence_ids=prepared_evidence_ids,
                warnings=warnings,
                blockers=blockers,
            )
            execution_intent_id = getattr(plan, "execution_intent_id", None)
            if execution_intent_id:
                await self._prepare_protection_failure_policy(
                    str(execution_intent_id),
                    prepared_evidence_ids=prepared_evidence_ids,
                    warnings=warnings,
                    blockers=blockers,
                )
            else:
                blockers.append("execution_intent_id_missing_for_protection_policy")

        resolved_evidence_ids = await self._resolve_available_evidence_ids(
            authorization_id
        )
        available_evidence_ids.update(resolved_evidence_ids)
        available_evidence_ids.update(prepared_evidence_ids)

        enablement_evidence = None
        if plan is not None:
            try:
                enablement_evidence = (
                    await self._evidence_service.preview_for_authorization(
                    authorization_id,
                    trusted_submit_fact_snapshot_id=available_evidence_ids.get(
                        "trusted_submit_fact_snapshot_id"
                    ),
                    submit_idempotency_policy_id=available_evidence_ids.get(
                        "submit_idempotency_policy_id"
                    ),
                    attempt_outcome_policy_id=available_evidence_ids.get(
                        "attempt_outcome_policy_id"
                    ),
                    post_submit_budget_settlement_persistence_evidence_id=(
                        available_evidence_ids.get(
                            "post_submit_budget_settlement_persistence_evidence_id"
                        )
                    ),
                    protection_creation_failure_policy_id=(
                        available_evidence_ids.get(
                            "protection_creation_failure_policy_id"
                        )
                    ),
                    semantic_confirmations=semantic_confirmations,
                    runtime_confirmations=runtime_confirmations,
                    )
                )
            except Exception as exc:
                blockers.append(
                    _error_code("first_real_submit_evidence_unavailable", exc)
                )

        return build_runtime_execution_first_real_submit_evidence_preparation(
            authorization_id=authorization_id,
            prepared_evidence_ids=prepared_evidence_ids,
            available_evidence_ids=available_evidence_ids,
            skipped_evidence=skipped_evidence,
            blockers=blockers,
            warnings=warnings,
            enablement_evidence=enablement_evidence,
            now_ms=_now_ms(),
        )

    async def _prepare_submit_idempotency(
        self,
        authorization_id: str,
        *,
        prepared_evidence_ids: dict[str, str],
        warnings: list[str],
        blockers: list[str],
        adapter_result_store_implemented: bool,
        real_adapter_boundary_implemented: bool,
    ) -> None:
        recorder = getattr(
            self._adapter_service,
            "record_submit_idempotency_snapshot_for_authorization",
            None,
        )
        if not callable(recorder):
            blockers.append("submit_idempotency_preparation_unavailable")
            return
        try:
            snapshot = await recorder(
                authorization_id,
                adapter_result_store_implemented=(
                    adapter_result_store_implemented
                ),
                real_adapter_boundary_implemented=(
                    real_adapter_boundary_implemented
                ),
            )
        except Exception as exc:
            blockers.append(_error_code("submit_idempotency_prepare_failed", exc))
            return
        policy_id = _normalized_optional(
            getattr(snapshot, "submit_idempotency_policy_id", None)
        )
        if policy_id:
            prepared_evidence_ids["submit_idempotency_policy_id"] = policy_id
        warnings.extend(
            f"submit_idempotency:{warning}"
            for warning in list(getattr(snapshot, "warnings", []) or [])
        )

    async def _prepare_trusted_submit_facts(
        self,
        plan: object,
        *,
        prepared_evidence_ids: dict[str, str],
        warnings: list[str],
        blockers: list[str],
    ) -> None:
        assembly_service = self._trusted_submit_facts_assembly_service
        recorder = getattr(
            assembly_service,
            "assemble_and_record_snapshot_for_controlled_submit_plan",
            None,
        )
        if not callable(recorder):
            blockers.append("trusted_submit_facts_preparation_unavailable")
            return
        try:
            snapshot = await recorder(
                plan=plan,
                now_ms=_now_ms(),
                metadata={
                    "api": "first_real_submit_evidence_preparation",
                    "owner_supplied_allow_facts_accepted": False,
                },
            )
        except Exception as exc:
            blockers.append(
                _error_code("trusted_submit_facts_prepare_failed", exc)
            )
            return
        snapshot_id = _normalized_optional(
            getattr(snapshot, "trusted_submit_fact_snapshot_id", None)
        )
        if snapshot_id:
            prepared_evidence_ids["trusted_submit_fact_snapshot_id"] = (
                snapshot_id
            )
        warnings.extend(
            f"trusted_submit_facts:{warning}"
            for warning in list(getattr(snapshot, "warnings", []) or [])
        )

    async def _prepare_protection_failure_policy(
        self,
        execution_intent_id: str,
        *,
        prepared_evidence_ids: dict[str, str],
        warnings: list[str],
        blockers: list[str],
    ) -> None:
        recorder = getattr(
            self._adapter_service,
            "record_protection_failure_policy_for_intent",
            None,
        )
        if not callable(recorder):
            blockers.append("protection_failure_policy_preparation_unavailable")
            return
        try:
            policy = await recorder(execution_intent_id)
        except Exception as exc:
            blockers.append(
                _error_code("protection_failure_policy_prepare_failed", exc)
            )
            return
        policy_id = _normalized_optional(getattr(policy, "policy_id", None))
        if policy_id:
            prepared_evidence_ids["protection_creation_failure_policy_id"] = (
                policy_id
            )
        warnings.extend(
            f"protection_failure_policy:{warning}"
            for warning in list(getattr(policy, "warnings", []) or [])
        )

    async def _resolve_available_evidence_ids(
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


def _normalized_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _error_code(prefix: str, exc: Exception) -> str:
    message = str(exc).strip().lower().replace(" ", "_")
    if not message:
        message = type(exc).__name__
    return f"{prefix}:{message[:120]}"
