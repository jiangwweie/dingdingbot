"""Read-only aggregation for runtime submit readiness.

RuntimeExecutionSubmitRehearsal explains whether the current recorded runtime
submit chain has enough evidence for Owner live-action review. It is not an
ExecutionIntent transition, not OrderLifecycle authority, and not exchange
submit authority.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_gateway_readiness import (
    DEFAULT_RUNTIME_EXCHANGE_GATEWAY_READINESS_MAX_AGE_MS,
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitGateStatus,
)


class RuntimeExecutionSubmitRehearsalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionSubmitRehearsalStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_LIVE_ACTION_REVIEW = "ready_for_owner_live_action_review"


class RuntimeExecutionSubmitRehearsalChecklistItem(
    RuntimeExecutionSubmitRehearsalModel
):
    key: str = Field(min_length=1, max_length=120)
    evidence_id: Optional[str] = Field(default=None, max_length=560)
    ready: bool = False
    blockers: list[str] = Field(default_factory=list)


class RuntimeExecutionSubmitRehearsal(RuntimeExecutionSubmitRehearsalModel):
    rehearsal_id: str = Field(min_length=1, max_length=560)
    authorization_id: str = Field(min_length=1, max_length=220)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    source_type: Optional[str] = Field(default=None, max_length=64)
    source_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    status: RuntimeExecutionSubmitRehearsalStatus
    exchange_submit_enablement_decision_id: str = Field(min_length=1, max_length=500)
    deployment_readiness_evidence_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    trusted_submit_fact_snapshot_id: Optional[str] = Field(
        default=None,
        max_length=240,
    )
    submit_idempotency_policy_id: Optional[str] = Field(default=None, max_length=240)
    attempt_outcome_policy_id: Optional[str] = Field(default=None, max_length=360)
    protection_creation_failure_policy_id: Optional[str] = Field(
        default=None,
        max_length=300,
    )
    local_registration_enablement_decision_id: Optional[str] = Field(
        default=None,
        max_length=300,
    )
    owner_real_submit_authorization_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    order_lifecycle_submit_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    exchange_submit_adapter_enablement_id: Optional[str] = Field(
        default=None,
        max_length=220,
    )
    exchange_submit_action_authorization_id: Optional[str] = Field(
        default=None,
        max_length=360,
    )
    evidence_checklist: list[
        RuntimeExecutionSubmitRehearsalChecklistItem
    ] = Field(default_factory=list)
    exchange_submit_enablement_ready: bool = False
    runtime_gateway_readiness_ready: bool = False
    runtime_gateway_readiness_fresh: bool = False
    runtime_gateway_readiness_age_ms: Optional[int] = Field(default=None, ge=0)
    runtime_gateway_readiness_max_age_ms: Optional[int] = Field(default=None, ge=0)
    no_blocking_recovery_tasks: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_live_action_authorization: Literal[True] = True
    not_exchange_submit_authority: Literal[True] = True
    not_order_lifecycle_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    order_created: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_rehearsal(self) -> "RuntimeExecutionSubmitRehearsal":
        _reject_forbidden_execution_fields(
            "runtime submit rehearsal",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionSubmitRehearsalStatus.READY_FOR_OWNER_LIVE_ACTION_REVIEW
            and self.blockers
        ):
            raise ValueError("ready submit rehearsal cannot have blockers")
        if (
            self.execution_intent_status_changed
            or self.order_created
            or self.order_lifecycle_called
            or self.exchange_called
            or self.exchange_order_submitted
            or self.owner_bounded_execution_called
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError("runtime submit rehearsal cannot perform execution")
        return self


def build_runtime_execution_submit_rehearsal(
    *,
    exchange_submit_enablement_decision: Any,
    runtime_exchange_gateway_readiness: Any | None = None,
    blocking_recovery_task_ids: list[str] | None = None,
    additional_blockers: list[str] | None = None,
    additional_warnings: list[str] | None = None,
    runtime_gateway_readiness_max_age_ms: int | None = (
        DEFAULT_RUNTIME_EXCHANGE_GATEWAY_READINESS_MAX_AGE_MS
    ),
    now_ms: int,
) -> RuntimeExecutionSubmitRehearsal:
    blockers = list(getattr(exchange_submit_enablement_decision, "blockers", []))
    warnings = list(getattr(exchange_submit_enablement_decision, "warnings", []))
    blockers.extend(additional_blockers or [])
    warnings.extend(additional_warnings or [])
    authorization_id = getattr(exchange_submit_enablement_decision, "authorization_id")
    decision_id = getattr(exchange_submit_enablement_decision, "decision_id")
    execution_intent_id = getattr(
        exchange_submit_enablement_decision,
        "execution_intent_id",
    )
    runtime_instance_id = getattr(
        exchange_submit_enablement_decision,
        "runtime_instance_id",
    )

    exchange_submit_ready = getattr(
        exchange_submit_enablement_decision,
        "status",
        None,
    ) == RuntimeExecutionExchangeSubmitGateStatus.READY_FOR_EXCHANGE_SUBMIT_ACTION
    if not exchange_submit_ready:
        blockers.append("exchange_submit_enablement_not_ready")
    _append_forbidden_side_effect_blockers(
        "exchange_submit_enablement",
        exchange_submit_enablement_decision,
        blockers,
    )

    gateway_ready = False
    gateway_fresh = False
    gateway_age_ms: int | None = None
    deployment_readiness_evidence_id = getattr(
        exchange_submit_enablement_decision,
        "deployment_readiness_evidence_id",
        None,
    )
    if runtime_exchange_gateway_readiness is None:
        blockers.append("runtime_exchange_gateway_readiness_missing")
    else:
        gateway_ready = getattr(
            runtime_exchange_gateway_readiness,
            "status",
            None,
        ) == (
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        )
        if not gateway_ready:
            blockers.append("runtime_exchange_gateway_readiness_not_ready")
        freshness_blockers, gateway_age_ms = (
            _runtime_gateway_readiness_freshness_blockers(
                runtime_exchange_gateway_readiness,
                now_ms=now_ms,
                max_age_ms=runtime_gateway_readiness_max_age_ms,
            )
        )
        gateway_fresh = not freshness_blockers
        blockers.extend(freshness_blockers)
        readiness_id = getattr(
            runtime_exchange_gateway_readiness,
            "readiness_id",
            None,
        )
        if (
            deployment_readiness_evidence_id
            and readiness_id
            and readiness_id != deployment_readiness_evidence_id
        ):
            blockers.append("runtime_exchange_gateway_readiness_id_mismatch")
        blockers.extend(
            f"runtime_exchange_gateway_readiness:{blocker}"
            for blocker in getattr(runtime_exchange_gateway_readiness, "blockers", [])
        )
        warnings.extend(
            f"runtime_exchange_gateway_readiness:{warning}"
            for warning in getattr(runtime_exchange_gateway_readiness, "warnings", [])
        )
        _append_forbidden_side_effect_blockers(
            "runtime_exchange_gateway_readiness",
            runtime_exchange_gateway_readiness,
            blockers,
        )

    recovery_check_unavailable = any(
        blocker
        in {
            "execution_recovery_repository_unavailable",
            "execution_recovery_blocking_check_unavailable",
        }
        for blocker in blockers
    )
    recovery_task_ids = list(blocking_recovery_task_ids or [])
    if recovery_task_ids:
        blockers.append("execution_recovery_blocking_tasks_open")
        warnings.extend(
            f"execution_recovery_blocking_task:{task_id}"
            for task_id in recovery_task_ids
        )
    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)

    status = (
        RuntimeExecutionSubmitRehearsalStatus.BLOCKED
        if blockers
        else RuntimeExecutionSubmitRehearsalStatus
        .READY_FOR_OWNER_LIVE_ACTION_REVIEW
    )
    evidence_checklist = _build_evidence_checklist(
        decision_id=decision_id,
        exchange_submit_enablement_ready=exchange_submit_ready,
        deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        runtime_gateway_readiness_ready=gateway_ready and gateway_fresh,
        no_blocking_recovery_tasks=(
            not recovery_task_ids and not recovery_check_unavailable
        ),
        exchange_submit_enablement_decision=exchange_submit_enablement_decision,
        blockers=blockers,
    )
    return RuntimeExecutionSubmitRehearsal(
        rehearsal_id=f"runtime-submit-rehearsal-{authorization_id}",
        authorization_id=authorization_id,
        execution_intent_id=execution_intent_id,
        runtime_instance_id=runtime_instance_id,
        source_type=getattr(exchange_submit_enablement_decision, "source_type", None),
        source_id=getattr(exchange_submit_enablement_decision, "source_id", None),
        semantic_ids=getattr(exchange_submit_enablement_decision, "semantic_ids"),
        status=status,
        exchange_submit_enablement_decision_id=decision_id,
        deployment_readiness_evidence_id=deployment_readiness_evidence_id,
        trusted_submit_fact_snapshot_id=getattr(
            exchange_submit_enablement_decision,
            "trusted_submit_fact_snapshot_id",
            None,
        ),
        submit_idempotency_policy_id=getattr(
            exchange_submit_enablement_decision,
            "submit_idempotency_policy_id",
            None,
        ),
        attempt_outcome_policy_id=getattr(
            exchange_submit_enablement_decision,
            "attempt_outcome_policy_id",
            None,
        ),
        protection_creation_failure_policy_id=getattr(
            exchange_submit_enablement_decision,
            "protection_creation_failure_policy_id",
            None,
        ),
        local_registration_enablement_decision_id=getattr(
            exchange_submit_enablement_decision,
            "local_registration_enablement_decision_id",
            None,
        ),
        owner_real_submit_authorization_id=getattr(
            exchange_submit_enablement_decision,
            "owner_real_submit_authorization_id",
            None,
        ),
        order_lifecycle_submit_enablement_id=getattr(
            exchange_submit_enablement_decision,
            "order_lifecycle_submit_enablement_id",
            None,
        ),
        exchange_submit_adapter_enablement_id=getattr(
            exchange_submit_enablement_decision,
            "exchange_submit_adapter_enablement_id",
            None,
        ),
        exchange_submit_action_authorization_id=getattr(
            exchange_submit_enablement_decision,
            "exchange_submit_action_authorization_id",
            None,
        ),
        evidence_checklist=evidence_checklist,
        exchange_submit_enablement_ready=exchange_submit_ready,
        runtime_gateway_readiness_ready=gateway_ready and gateway_fresh,
        runtime_gateway_readiness_fresh=gateway_fresh,
        runtime_gateway_readiness_age_ms=gateway_age_ms,
        runtime_gateway_readiness_max_age_ms=(
            runtime_gateway_readiness_max_age_ms
        ),
        no_blocking_recovery_tasks=(
            not recovery_task_ids and not recovery_check_unavailable
        ),
        blockers=blockers,
        warnings=warnings,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_submit_rehearsal",
            "read_only_aggregation": True,
            "first_real_submit_checklist": True,
            "evidence_checklist_keys": [
                item.key for item in evidence_checklist
            ],
            "runtime_gateway_readiness_age_ms": gateway_age_ms,
            "runtime_gateway_readiness_max_age_ms": (
                runtime_gateway_readiness_max_age_ms
            ),
            "not_live_action_authorization": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange": True,
        },
    )


def _build_evidence_checklist(
    *,
    decision_id: str,
    exchange_submit_enablement_ready: bool,
    deployment_readiness_evidence_id: str | None,
    runtime_gateway_readiness_ready: bool,
    no_blocking_recovery_tasks: bool,
    exchange_submit_enablement_decision: Any,
    blockers: list[str],
) -> list[RuntimeExecutionSubmitRehearsalChecklistItem]:
    items = [
        _checklist_item(
            key="exchange_submit_enablement_decision",
            evidence_id=decision_id,
            ready=exchange_submit_enablement_ready,
            blockers=blockers,
            prefixes=("exchange_submit_enablement", "exchange_submit_gate"),
        ),
        _checklist_item(
            key="trusted_submit_facts",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "trusted_submit_fact_snapshot_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "trusted_submit_fact_snapshot_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("trusted_submit_fact",),
        ),
        _checklist_item(
            key="submit_idempotency",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "submit_idempotency_policy_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "submit_idempotency_policy_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("submit_idempotency",),
        ),
        _checklist_item(
            key="attempt_outcome_policy",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "attempt_outcome_policy_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "attempt_outcome_policy_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("attempt_outcome_policy",),
        ),
        _checklist_item(
            key="protection_failure_policy",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "protection_creation_failure_policy_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "protection_creation_failure_policy_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=(
                "protection_failure_policy",
                "protection_creation_failure_policy",
            ),
        ),
        _checklist_item(
            key="local_registration_enablement",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "local_registration_enablement_decision_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "local_registration_enablement_decision_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("local_registration_enablement",),
        ),
        _checklist_item(
            key="owner_real_submit_authorization",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "owner_real_submit_authorization_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "owner_real_submit_authorization_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("owner_real_submit",),
        ),
        _checklist_item(
            key="order_lifecycle_submit_enablement",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "order_lifecycle_submit_enablement_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "order_lifecycle_submit_enablement_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("order_lifecycle_submit",),
        ),
        _checklist_item(
            key="exchange_submit_adapter_enablement",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "exchange_submit_adapter_enablement_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "exchange_submit_adapter_enablement_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("exchange_submit_adapter",),
        ),
        _checklist_item(
            key="exchange_submit_action_authorization",
            evidence_id=getattr(
                exchange_submit_enablement_decision,
                "exchange_submit_action_authorization_id",
                None,
            ),
            ready=_present(
                getattr(
                    exchange_submit_enablement_decision,
                    "exchange_submit_action_authorization_id",
                    None,
                )
            ),
            blockers=blockers,
            prefixes=("exchange_submit_action_authorization",),
        ),
        _checklist_item(
            key="runtime_exchange_gateway_readiness",
            evidence_id=deployment_readiness_evidence_id,
            ready=runtime_gateway_readiness_ready,
            blockers=blockers,
            prefixes=(
                "runtime_exchange_gateway_readiness",
                "deployment_readiness_evidence",
            ),
        ),
        _checklist_item(
            key="no_blocking_recovery_tasks",
            evidence_id=None,
            ready=no_blocking_recovery_tasks,
            blockers=blockers,
            prefixes=("execution_recovery",),
        ),
    ]
    return items


def runtime_gateway_readiness_freshness_blockers(
    runtime_exchange_gateway_readiness: Any,
    *,
    now_ms: int,
    max_age_ms: int | None = DEFAULT_RUNTIME_EXCHANGE_GATEWAY_READINESS_MAX_AGE_MS,
) -> tuple[list[str], int | None]:
    return _runtime_gateway_readiness_freshness_blockers(
        runtime_exchange_gateway_readiness,
        now_ms=now_ms,
        max_age_ms=max_age_ms,
    )


def _runtime_gateway_readiness_freshness_blockers(
    runtime_exchange_gateway_readiness: Any,
    *,
    now_ms: int,
    max_age_ms: int | None,
) -> tuple[list[str], int | None]:
    if max_age_ms is None:
        return [], None
    created_at = getattr(runtime_exchange_gateway_readiness, "created_at_ms", None)
    if created_at is None:
        return ["runtime_exchange_gateway_readiness_created_at_missing"], None
    try:
        created_at_ms = int(created_at)
    except (TypeError, ValueError):
        return ["runtime_exchange_gateway_readiness_created_at_invalid"], None
    if created_at_ms > now_ms:
        return ["runtime_exchange_gateway_readiness_created_in_future"], None
    age_ms = now_ms - created_at_ms
    if age_ms > max_age_ms:
        return ["runtime_exchange_gateway_readiness_stale"], age_ms
    return [], age_ms


def _checklist_item(
    *,
    key: str,
    evidence_id: str | None,
    ready: bool,
    blockers: list[str],
    prefixes: tuple[str, ...],
) -> RuntimeExecutionSubmitRehearsalChecklistItem:
    item_blockers = [
        blocker
        for blocker in blockers
        if any(blocker.startswith(prefix) for prefix in prefixes)
    ]
    return RuntimeExecutionSubmitRehearsalChecklistItem(
        key=key,
        evidence_id=_optional_str(evidence_id),
        ready=ready and not item_blockers,
        blockers=item_blockers,
    )


def _append_forbidden_side_effect_blockers(
    prefix: str,
    artifact: Any,
    blockers: list[str],
) -> None:
    checks = {
        "execution_intent_status_changed": "changed_intent_status",
        "order_created": "created_order",
        "order_lifecycle_called": "called_order_lifecycle",
        "order_lifecycle_submit_called": "called_order_lifecycle_submit",
        "exchange_called": "called_exchange",
        "exchange_order_submitted": "submitted_exchange_order",
        "owner_bounded_execution_called": "called_owner_bounded_execution",
        "withdrawal_or_transfer_created": "created_withdrawal_or_transfer",
    }
    for attr, suffix in checks.items():
        if getattr(artifact, attr, False):
            blockers.append(f"{prefix}_{suffix}")


def _reject_forbidden_execution_fields(scope: str, value: dict[str, Any]) -> None:
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


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _present(value: str | None) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
