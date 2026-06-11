"""Owner-reviewed recovery resolution evidence for exchange-submit failures.

This model records that the Owner reviewed an exchange-submit protection
failure and confirmed the recovery block can be cleared. It is evidence only:
it does not create orders, call exchange, call OrderLifecycle, or alter an
ExecutionIntent.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


EXCHANGE_SUBMIT_PROTECTION_FAILED_RECOVERY_TYPE = "exchange_submit_protection_fail"


class RuntimeExecutionExchangeSubmitRecoveryResolutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeSubmitRecoveryResolutionStatus(str, Enum):
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class RuntimeExecutionExchangeSubmitRecoveryResolution(
    RuntimeExecutionExchangeSubmitRecoveryResolutionModel
):
    resolution_id: str = Field(min_length=1, max_length=300)
    recovery_task_id: str = Field(min_length=1, max_length=64)
    recovery_type: str = Field(min_length=1, max_length=64)
    status: RuntimeExecutionExchangeSubmitRecoveryResolutionStatus
    authorization_id: Optional[str] = Field(default=None, max_length=220)
    execution_result_id: Optional[str] = Field(default=None, max_length=540)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    related_order_id: Optional[str] = Field(default=None, max_length=260)
    related_exchange_order_id: Optional[str] = Field(default=None, max_length=260)
    entry_order_id: Optional[str] = Field(default=None, max_length=260)
    entry_exchange_order_id: Optional[str] = Field(default=None, max_length=260)
    failed_protection_order_id: Optional[str] = Field(default=None, max_length=260)
    failed_reason: Optional[str] = Field(default=None, max_length=500)
    owner_operator_id: str = Field(min_length=1, max_length=128)
    owner_confirmation_reference: Optional[str] = Field(
        default=None,
        max_length=240,
    )
    reason: str = Field(min_length=1, max_length=500)
    reconciliation_evidence_id: Optional[str] = Field(default=None, max_length=240)
    owner_confirmed_recovery_resolved: bool
    owner_confirmed_reconciliation_reviewed: bool
    owner_confirmed_no_unprotected_position: bool
    owner_confirmed_no_unresolved_exchange_order: bool
    owner_confirmed_budget_reconciled_or_held: bool
    owner_confirmed_attempt_consumed_or_accounted: bool
    recovery_task_marked_resolved: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_execution_authority: Literal[True] = True
    order_lifecycle_submit_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_resolution(
        self,
    ) -> "RuntimeExecutionExchangeSubmitRecoveryResolution":
        _reject_forbidden_execution_fields(
            "exchange submit recovery resolution",
            {"metadata": self.metadata},
        )
        if self.status == RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.RESOLVED:
            if self.blockers:
                raise ValueError("resolved recovery resolution cannot have blockers")
            required_confirmations = {
                "owner_confirmed_recovery_resolved": (
                    self.owner_confirmed_recovery_resolved
                ),
                "owner_confirmed_reconciliation_reviewed": (
                    self.owner_confirmed_reconciliation_reviewed
                ),
                "owner_confirmed_no_unprotected_position": (
                    self.owner_confirmed_no_unprotected_position
                ),
                "owner_confirmed_no_unresolved_exchange_order": (
                    self.owner_confirmed_no_unresolved_exchange_order
                ),
                "owner_confirmed_budget_reconciled_or_held": (
                    self.owner_confirmed_budget_reconciled_or_held
                ),
                "owner_confirmed_attempt_consumed_or_accounted": (
                    self.owner_confirmed_attempt_consumed_or_accounted
                ),
                "recovery_task_marked_resolved": self.recovery_task_marked_resolved,
            }
            missing = [
                name for name, confirmed in required_confirmations.items()
                if not confirmed
            ]
            if missing:
                raise ValueError(
                    "resolved recovery resolution missing confirmation(s): "
                    f"{', '.join(missing)}"
                )
        if self.exchange_called or self.exchange_order_submitted:
            raise ValueError(
                "exchange submit recovery resolution cannot call exchange"
            )
        if self.order_lifecycle_submit_called:
            raise ValueError(
                "exchange submit recovery resolution cannot call OrderLifecycle"
            )
        if self.execution_intent_status_changed:
            raise ValueError(
                "exchange submit recovery resolution cannot change intent status"
            )
        if self.owner_bounded_execution_called:
            raise ValueError(
                "exchange submit recovery resolution cannot call "
                "OwnerBoundedExecution"
            )
        if self.withdrawal_or_transfer_created:
            raise ValueError(
                "exchange submit recovery resolution cannot create withdrawal/transfer"
            )
        return self


def build_runtime_execution_exchange_submit_recovery_resolution(
    *,
    recovery_task: dict[str, Any],
    owner_operator_id: str,
    reason: str,
    now_ms: int,
    owner_confirmed_recovery_resolved: bool = False,
    owner_confirmed_reconciliation_reviewed: bool = False,
    owner_confirmed_no_unprotected_position: bool = False,
    owner_confirmed_no_unresolved_exchange_order: bool = False,
    owner_confirmed_budget_reconciled_or_held: bool = False,
    owner_confirmed_attempt_consumed_or_accounted: bool = False,
    owner_confirmation_reference: str | None = None,
    reconciliation_evidence_id: str | None = None,
    recovery_task_marked_resolved: bool = False,
) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
    task_id = str(recovery_task.get("id") or "").strip()
    recovery_type = str(recovery_task.get("recovery_type") or "").strip()
    context = recovery_task.get("context_payload") or {}
    blockers: list[str] = []
    warnings: list[str] = []

    if recovery_type != EXCHANGE_SUBMIT_PROTECTION_FAILED_RECOVERY_TYPE:
        blockers.append("recovery_type_not_exchange_submit_protection_fail")
    recovery_task_status = str(recovery_task.get("status") or "").strip()
    if recovery_task_status not in {"pending", "retrying"} and not (
        recovery_task_marked_resolved and recovery_task_status == "resolved"
    ):
        blockers.append("recovery_task_not_pending_or_retrying")
    if not context.get("block_new_entries_until_resolved"):
        blockers.append("recovery_task_blocking_flag_missing")
    if not context.get("require_owner_recovery_review"):
        blockers.append("recovery_task_owner_review_flag_missing")
    if not context.get("require_reduce_only_recovery_mode"):
        blockers.append("recovery_task_reduce_only_flag_missing")
    if not context.get("require_reconciliation_before_retry"):
        blockers.append("recovery_task_reconciliation_flag_missing")
    if not owner_confirmed_recovery_resolved:
        blockers.append("owner_recovery_resolution_confirmation_missing")
    if not owner_confirmed_reconciliation_reviewed:
        blockers.append("owner_reconciliation_review_confirmation_missing")
    if not owner_confirmed_no_unprotected_position:
        blockers.append("owner_no_unprotected_position_confirmation_missing")
    if not owner_confirmed_no_unresolved_exchange_order:
        blockers.append("owner_no_unresolved_exchange_order_confirmation_missing")
    if not owner_confirmed_budget_reconciled_or_held:
        blockers.append("owner_budget_reconciled_or_held_confirmation_missing")
    if not owner_confirmed_attempt_consumed_or_accounted:
        blockers.append("owner_attempt_consumed_or_accounted_confirmation_missing")
    if not _present(owner_operator_id):
        blockers.append("owner_operator_id_missing")
    if not _present(reason):
        blockers.append("owner_recovery_resolution_reason_missing")
    if not _present(reconciliation_evidence_id):
        warnings.append("reconciliation_evidence_id_missing")

    status = (
        RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.RESOLVED
    )
    return RuntimeExecutionExchangeSubmitRecoveryResolution(
        resolution_id=f"runtime-exchange-submit-recovery-resolution-{task_id}",
        recovery_task_id=task_id,
        recovery_type=recovery_type or "unknown",
        status=status,
        authorization_id=_optional_str(context.get("authorization_id")),
        execution_result_id=_optional_str(context.get("execution_result_id")),
        execution_intent_id=_required_str(recovery_task.get("intent_id"), "unknown"),
        runtime_instance_id=_optional_str(context.get("runtime_instance_id")),
        source_type=_optional_str(context.get("source_type")),
        source_id=_optional_str(context.get("source_id")),
        symbol=_required_str(recovery_task.get("symbol"), "unknown"),
        related_order_id=_optional_str(recovery_task.get("related_order_id")),
        related_exchange_order_id=_optional_str(
            recovery_task.get("related_exchange_order_id")
        ),
        entry_order_id=_optional_str(context.get("entry_order_id")),
        entry_exchange_order_id=_optional_str(context.get("entry_exchange_order_id")),
        failed_protection_order_id=_optional_str(
            context.get("failed_protection_order_id")
        ),
        failed_reason=_optional_str(
            context.get("failed_reason") or recovery_task.get("error_message")
        ),
        owner_operator_id=str(owner_operator_id or "").strip() or "unknown",
        owner_confirmation_reference=_optional_str(owner_confirmation_reference),
        reason=str(reason or "").strip() or "missing_reason",
        reconciliation_evidence_id=_optional_str(reconciliation_evidence_id),
        owner_confirmed_recovery_resolved=owner_confirmed_recovery_resolved,
        owner_confirmed_reconciliation_reviewed=(
            owner_confirmed_reconciliation_reviewed
        ),
        owner_confirmed_no_unprotected_position=(
            owner_confirmed_no_unprotected_position
        ),
        owner_confirmed_no_unresolved_exchange_order=(
            owner_confirmed_no_unresolved_exchange_order
        ),
        owner_confirmed_budget_reconciled_or_held=(
            owner_confirmed_budget_reconciled_or_held
        ),
        owner_confirmed_attempt_consumed_or_accounted=(
            owner_confirmed_attempt_consumed_or_accounted
        ),
        recovery_task_marked_resolved=(
            recovery_task_marked_resolved if not blockers else False
        ),
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_exchange_submit_recovery_resolution",
            "owner_reviewed_recovery_task": True,
            "clears_existing_recovery_task_only": True,
            "does_not_create_recovery_order": True,
            "does_not_call_exchange": True,
            "does_not_call_order_lifecycle": True,
            "does_not_change_execution_intent_status": True,
            "does_not_call_owner_bounded_execution": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip()
    return text or None


def _required_str(value: Any, placeholder: str) -> str:
    return _optional_str(value) or placeholder


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_execution_fields(scope: str, value: dict[str, Any]) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "client_order_id",
        "exchange_payload",
        "place_order",
        "submit_order",
        "withdrawal_payload",
        "transfer_payload",
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
