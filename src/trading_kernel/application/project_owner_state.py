"""Project one Owner product state without executing trading actions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.domain.aggregate import AggregateStatus


class OwnerProjectionFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_exists: bool
    policy_enabled: bool
    readiness_state: str | None = None
    first_blocker: str | None = None
    aggregate_status: AggregateStatus | None = None
    ticket_id: str | None = None
    incident_id: str | None = None

    @model_validator(mode="after")
    def _validate_policy(self) -> "OwnerProjectionFacts":
        if self.policy_enabled and not self.policy_exists:
            raise ValueError("enabled policy must exist")
        return self


class OwnerProjectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    monitor_key: str
    owner_policy_id: str
    runtime_scope_id: str
    ticket_id: str | None = None
    updated_at_ms: int

    @field_validator(
        "monitor_key",
        "owner_policy_id",
        "runtime_scope_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Owner projection identities must be non-blank")
        return normalized

    @field_validator("updated_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Owner projection time must be positive")
        return value


_INTERVENTION_BLOCKERS = {
    "account_mode_invalid",
    "command_outcome_unknown",
    "hard_safety_stop",
    "protection_unavailable",
    "runtime_incident_open",
}


def derive_owner_projection(
    *,
    monitor_key: str,
    facts: OwnerProjectionFacts,
    updated_at_ms: int,
) -> MonitorStateRecord:
    if facts.incident_id is not None:
        status = MonitorOwnerStatus.NEEDS_INTERVENTION
        summary = "交易状态异常，需要介入"
    elif not facts.policy_exists:
        status = MonitorOwnerStatus.NOT_ENABLED
        summary = "策略尚未启用"
    elif not facts.policy_enabled:
        status = MonitorOwnerStatus.PAUSED
        summary = "策略已暂停"
    elif facts.aggregate_status in {
        AggregateStatus.TERMINAL,
        AggregateStatus.ENTRY_REJECTED,
        AggregateStatus.ENTRY_RECONCILED_ABSENT,
    }:
        status = MonitorOwnerStatus.COMPLETED
        summary = "本次交易已完成"
    elif facts.aggregate_status is not None:
        status = MonitorOwnerStatus.PROCESSING
        summary = "系统自动处理中"
    elif facts.readiness_state in {"candidate_ready", "processing"}:
        status = MonitorOwnerStatus.PROCESSING
        summary = "系统自动处理中"
    elif facts.readiness_state == "signal_absent":
        status = MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY
        summary = "运行中，等待机会"
    elif facts.readiness_state == "blocked":
        if facts.first_blocker in _INTERVENTION_BLOCKERS:
            status = MonitorOwnerStatus.NEEDS_INTERVENTION
            summary = "交易状态异常，需要介入"
        else:
            status = MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE
            summary = "当前暂不可用，系统已阻断执行"
    else:
        status = MonitorOwnerStatus.RUNNING
        summary = "策略观察与运行时正常"

    return MonitorStateRecord(
        monitor_key=monitor_key,
        owner_status=status,
        summary=summary,
        intervention=(
            "需要介入"
            if status is MonitorOwnerStatus.NEEDS_INTERVENTION
            else "无需操作"
        ),
        ticket_id=facts.ticket_id,
        incident_id=facts.incident_id,
        updated_at_ms=updated_at_ms,
    )


async def project_owner_state(
    uow: KernelUnitOfWork,
    request: OwnerProjectionRequest,
) -> MonitorStateRecord:
    policy = await uow.entry_admission.get_owner_policy(request.owner_policy_id)
    readiness = await uow.signals.get_readiness(request.runtime_scope_id)
    aggregate = (
        None
        if request.ticket_id is None
        else await uow.aggregates.get(request.ticket_id)
    )
    incident = (
        None
        if request.ticket_id is None
        else await uow.incidents.get_open_for_ticket(request.ticket_id)
    )
    desired = derive_owner_projection(
        monitor_key=request.monitor_key,
        facts=OwnerProjectionFacts(
            policy_exists=policy is not None,
            policy_enabled=bool(policy and policy.enabled),
            readiness_state=(
                None if readiness is None else readiness.readiness_state
            ),
            first_blocker=None if readiness is None else readiness.first_blocker,
            aggregate_status=None if aggregate is None else aggregate.status,
            ticket_id=request.ticket_id,
            incident_id=None if incident is None else incident.incident_id,
        ),
        updated_at_ms=request.updated_at_ms,
    )
    return await uow.monitors.save_if_changed(desired)
