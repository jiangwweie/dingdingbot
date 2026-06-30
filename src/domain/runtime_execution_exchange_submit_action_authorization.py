"""Scoped Owner action authorization for runtime exchange submit.

This is evidence that the Owner explicitly confirmed a future exchange-submit
action for one runtime authorization scope. It is not an order, not an
ExecutionIntent state transition, not an OrderLifecycle submit call, and not
exchange authority by itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_preview import (
    RuntimeExecutionExchangeSubmitPreview,
    RuntimeExecutionExchangeSubmitPreviewStatus,
)


class RuntimeExecutionExchangeSubmitActionAuthorizationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitActionAuthorizationStatus(str, Enum):
    BLOCKED = "blocked"
    APPROVED_FOR_EXCHANGE_SUBMIT_ACTION = (
        "approved_for_exchange_submit_action"
    )


class RuntimeExecutionExchangeSubmitActionAuthorization(
    RuntimeExecutionExchangeSubmitActionAuthorizationModel
):
    action_authorization_id: str = Field(min_length=1, max_length=360)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionExchangeSubmitActionAuthorizationStatus
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    local_registration_enablement_decision_id: str = Field(
        min_length=1,
        max_length=300,
    )
    trusted_submit_fact_snapshot_id: str = Field(min_length=1, max_length=240)
    submit_idempotency_policy_id: str = Field(min_length=1, max_length=240)
    attempt_outcome_policy_id: str = Field(min_length=1, max_length=360)
    protection_creation_failure_policy_id: str = Field(
        min_length=1,
        max_length=300,
    )
    owner_real_submit_authorization_id: str = Field(min_length=1, max_length=220)
    order_lifecycle_submit_enablement_id: str = Field(
        min_length=1,
        max_length=220,
    )
    exchange_submit_adapter_enablement_id: str = Field(
        min_length=1,
        max_length=220,
    )
    deployment_readiness_evidence_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    submit_preview_id: str = Field(min_length=1, max_length=460)
    binding_id: str = Field(min_length=1, max_length=460)
    local_registration_adapter_result_id: str = Field(
        min_length=1,
        max_length=420,
    )
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    local_order_ids: list[str] = Field(default_factory=list)
    protection_order_ids: list[str] = Field(default_factory=list)
    submit_request_count: int = Field(ge=0)
    entry_submit_request_count: int = Field(ge=0)
    protection_submit_request_count: int = Field(ge=0)
    owner_confirmed_for_exchange_submit_action: bool
    owner_operator_id: str = Field(min_length=1, max_length=128)
    owner_confirmation_reference: Optional[str] = Field(
        default=None,
        max_length=240,
    )
    reason: str = Field(min_length=1, max_length=500)
    expires_at_ms: Optional[int] = Field(default=None, ge=0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_exchange_submit_authority: Literal[True] = True
    order_lifecycle_submit_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_authorization(
        self,
    ) -> "RuntimeExecutionExchangeSubmitActionAuthorization":
        _reject_forbidden_execution_fields(
            "exchange submit action authorization",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionExchangeSubmitActionAuthorizationStatus
            .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
            and self.blockers
        ):
            raise ValueError(
                "approved exchange submit action authorization cannot have blockers"
            )
        if not self.owner_confirmed_for_exchange_submit_action and (
            self.status
            == RuntimeExecutionExchangeSubmitActionAuthorizationStatus
            .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
        ):
            raise ValueError(
                "approved exchange submit action authorization requires Owner "
                "confirmation"
            )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError(
                "exchange submit action authorization cannot call exchange"
            )
        if self.order_lifecycle_submit_called:
            raise ValueError(
                "exchange submit action authorization cannot call "
                "OrderLifecycle.submit_order"
            )
        if self.execution_intent_status_changed:
            raise ValueError(
                "exchange submit action authorization cannot change intent status"
            )
        if self.owner_bounded_execution_called:
            raise ValueError(
                "exchange submit action authorization cannot call "
                "OwnerBoundedExecution"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "exchange submit action authorization cannot create "
                "withdrawal/transfer"
            )
        return self


def build_runtime_execution_exchange_submit_action_authorization(
    *,
    submit_preview: RuntimeExecutionExchangeSubmitPreview,
    trusted_submit_fact_snapshot_id: str | None,
    submit_idempotency_policy_id: str | None,
    attempt_outcome_policy_id: str | None,
    protection_creation_failure_policy_id: str | None,
    local_registration_enablement_decision_id: str | None,
    owner_real_submit_authorization_id: str | None,
    order_lifecycle_submit_enablement_id: str | None,
    exchange_submit_adapter_enablement_id: str | None,
    owner_confirmed_for_exchange_submit_action: bool,
    owner_operator_id: str,
    reason: str,
    now_ms: int,
    deployment_readiness_evidence_id: str | None = None,
    owner_confirmation_reference: str | None = None,
    expires_at_ms: int | None = None,
) -> RuntimeExecutionExchangeSubmitActionAuthorization:
    blockers = list(submit_preview.blockers)
    warnings = list(submit_preview.warnings)
    if (
        submit_preview.status
        != RuntimeExecutionExchangeSubmitPreviewStatus
        .READY_FOR_EXCHANGE_SUBMIT_ADAPTER_DESIGN
    ):
        blockers.append("exchange_submit_preview_not_ready")
    if not submit_preview.entry_submit_request_preview:
        blockers.append("entry_exchange_submit_request_preview_missing")
    if not submit_preview.protection_submit_request_previews:
        blockers.append("protection_exchange_submit_request_previews_missing")
    if not _present(trusted_submit_fact_snapshot_id):
        blockers.append("trusted_submit_fact_snapshot_id_missing")
    if not _present(submit_idempotency_policy_id):
        blockers.append("submit_idempotency_policy_id_missing")
    if not _present(attempt_outcome_policy_id):
        blockers.append("attempt_outcome_policy_id_missing")
    if not _present(protection_creation_failure_policy_id):
        blockers.append("protection_creation_failure_policy_id_missing")
    if not _present(local_registration_enablement_decision_id):
        blockers.append("local_registration_enablement_decision_id_missing")
    if not _present(owner_real_submit_authorization_id):
        blockers.append("owner_real_submit_authorization_id_missing")
    if not _present(order_lifecycle_submit_enablement_id):
        blockers.append("order_lifecycle_submit_enablement_id_missing")
    if not _present(exchange_submit_adapter_enablement_id):
        blockers.append("exchange_submit_adapter_enablement_id_missing")
    if not owner_confirmed_for_exchange_submit_action:
        blockers.append("owner_exchange_submit_action_confirmation_missing")
    if not str(owner_operator_id or "").strip():
        blockers.append("owner_operator_id_missing")
    if not str(reason or "").strip():
        blockers.append("owner_exchange_submit_action_reason_missing")
    if expires_at_ms is not None and expires_at_ms <= now_ms:
        blockers.append("exchange_submit_action_authorization_expired")
    if not _present(deployment_readiness_evidence_id):
        warnings.append("deployment_readiness_evidence_id_missing")

    status = (
        RuntimeExecutionExchangeSubmitActionAuthorizationStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeSubmitActionAuthorizationStatus
        .APPROVED_FOR_EXCHANGE_SUBMIT_ACTION
    )
    request_previews = [
        request.model_dump(mode="json")
        for request in submit_preview.submit_request_previews
    ]
    entry_request = submit_preview.entry_submit_request_preview
    side = entry_request.direction.value if entry_request is not None else None
    return RuntimeExecutionExchangeSubmitActionAuthorization(
        action_authorization_id=(
            "runtime-exchange-submit-action-authorization-"
            f"{submit_preview.authorization_id}"
        ),
        authorization_id=submit_preview.authorization_id,
        execution_intent_id=submit_preview.execution_intent_id,
        runtime_instance_id=submit_preview.runtime_instance_id,
        source_type=submit_preview.source_type,
        source_id=submit_preview.source_id,
        semantic_ids=submit_preview.semantic_ids,
        status=status,
        symbol=submit_preview.symbol,
        side=side,
        local_registration_enablement_decision_id=_required_str(
            local_registration_enablement_decision_id,
            "local-registration-enable-placeholder",
        ),
        trusted_submit_fact_snapshot_id=_required_str(
            trusted_submit_fact_snapshot_id,
            "trusted-submit-facts-placeholder",
        ),
        submit_idempotency_policy_id=_required_str(
            submit_idempotency_policy_id,
            "submit-idempotency-placeholder",
        ),
        attempt_outcome_policy_id=_required_str(
            attempt_outcome_policy_id,
            "attempt-outcome-placeholder",
        ),
        protection_creation_failure_policy_id=_required_str(
            protection_creation_failure_policy_id,
            "protection-failure-placeholder",
        ),
        owner_real_submit_authorization_id=_required_str(
            owner_real_submit_authorization_id,
            "owner-real-submit-auth-placeholder",
        ),
        order_lifecycle_submit_enablement_id=_required_str(
            order_lifecycle_submit_enablement_id,
            "order-lifecycle-submit-enable-placeholder",
        ),
        exchange_submit_adapter_enablement_id=_required_str(
            exchange_submit_adapter_enablement_id,
            "exchange-submit-adapter-enable-placeholder",
        ),
        deployment_readiness_evidence_id=_optional_str(
            deployment_readiness_evidence_id
        ),
        submit_preview_id=submit_preview.submit_preview_id,
        binding_id=submit_preview.binding_id,
        local_registration_adapter_result_id=submit_preview.adapter_result_id,
        entry_order_id=submit_preview.entry_order_id,
        local_order_ids=list(submit_preview.local_order_ids),
        protection_order_ids=list(submit_preview.protection_order_ids),
        submit_request_count=len(request_previews),
        entry_submit_request_count=submit_preview.entry_submit_request_count,
        protection_submit_request_count=(
            submit_preview.protection_submit_request_count
        ),
        owner_confirmed_for_exchange_submit_action=(
            owner_confirmed_for_exchange_submit_action
        ),
        owner_operator_id=str(owner_operator_id or "").strip() or "unknown",
        owner_confirmation_reference=_optional_str(owner_confirmation_reference),
        reason=str(reason or "").strip() or "missing_reason",
        expires_at_ms=expires_at_ms,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_submit_action_authorization",
            "scope_bound_owner_exchange_submit_action_confirmation": True,
            "not_exchange_submit_authority": True,
            "local_order_ids": list(submit_preview.local_order_ids),
            "entry_order_id": submit_preview.entry_order_id,
            "protection_order_ids": list(submit_preview.protection_order_ids),
            "submit_request_previews": request_previews,
            "does_not_call_order_lifecycle_submit": True,
            "does_not_change_execution_intent_status": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_exchange": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _required_str(value: str | None, placeholder: str) -> str:
    return _optional_str(value) or placeholder


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_execution_fields(
    scope: str,
    value: dict[str, Any],
) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "place_order",
        "submit_order",
        "transfer_payload",
        "withdrawal_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{scope} contains forbidden execution field: {key}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
