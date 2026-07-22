"""One bounded trading-kernel runtime action plus current Owner projection."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
    UnitOfWorkFactory,
    VenuePort,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate


class RuntimeActionStatus(StrEnum):
    NO_COMMAND = "no_command"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"


class RuntimeTickRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    monitor_key: str
    owner_policy_id: str
    ticket_id: str | None = None
    worker_id: str
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float

    @field_validator("monitor_key", "owner_policy_id", "worker_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runtime identities must be non-blank")
        return normalized

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _normalize_optional_ticket(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("ticket_id must be non-blank when supplied")
        return normalized

    @model_validator(mode="after")
    def _validate_runtime_window(self) -> "RuntimeTickRequest":
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("runtime lease must end after a positive tick time")
        if self.timeout_seconds <= 0:
            raise ValueError("runtime timeout must be positive")
        return self


class RuntimeTickResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_status: RuntimeActionStatus
    command_id: str | None = None
    monitor: MonitorStateRecord


async def run_runtime_once(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: RuntimeTickRequest,
) -> RuntimeTickResult:
    dispatch = await dispatch_one_command(
        uow_factory,
        venue,
        DispatchCommandRequest(
            worker_id=request.worker_id,
            ticket_id=request.ticket_id,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
            timeout_seconds=request.timeout_seconds,
        ),
    )

    ticket_id = request.ticket_id
    async with uow_factory() as uow:
        if dispatch.command_id is not None:
            command = await uow.exchange_commands.get(dispatch.command_id)
            if command is None:
                raise RuntimeError("dispatched command is missing from current state")
            command_ticket_id = command.ticket_identity.ticket_id
            if ticket_id is not None and ticket_id != command_ticket_id:
                raise RuntimeError("monitor Ticket differs from dispatched command")
            ticket_id = command_ticket_id

        policy = await uow.entry_admission.get_owner_policy(request.owner_policy_id)
        aggregate = None if ticket_id is None else await uow.aggregates.get(ticket_id)
        incident = (
            None
            if ticket_id is None
            else await uow.incidents.get_open_for_ticket(ticket_id)
        )
        desired = derive_monitor_state(
            monitor_key=request.monitor_key,
            policy_enabled=bool(policy and policy.enabled),
            aggregate=aggregate,
            incident_id=None if incident is None else incident.incident_id,
            ticket_id=ticket_id,
            updated_at_ms=request.now_ms,
        )
        monitor = await uow.monitors.save_if_changed(desired)

    return RuntimeTickResult(
        action_status=RuntimeActionStatus(dispatch.status.value),
        command_id=dispatch.command_id,
        monitor=monitor,
    )


def derive_monitor_state(
    *,
    monitor_key: str,
    policy_enabled: bool,
    aggregate: TradeAggregate | None,
    incident_id: str | None,
    ticket_id: str | None,
    updated_at_ms: int,
) -> MonitorStateRecord:
    if incident_id is not None:
        owner_status = MonitorOwnerStatus.NEEDS_INTERVENTION
        summary = "订单或持仓状态异常，等待系统处理"
        intervention = "需要介入"
    elif not policy_enabled:
        owner_status = MonitorOwnerStatus.PAUSED
        summary = "策略已暂停"
        intervention = "无需操作"
    elif aggregate is None:
        owner_status = MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY
        summary = "运行中，等待机会"
        intervention = "无需操作"
    elif aggregate.status in {AggregateStatus.TERMINAL, AggregateStatus.ENTRY_REJECTED}:
        owner_status = MonitorOwnerStatus.COMPLETED
        summary = "本次交易已完成"
        intervention = "无需操作"
    else:
        owner_status = MonitorOwnerStatus.PROCESSING
        summary = "系统自动处理中"
        intervention = "无需操作"

    return MonitorStateRecord(
        monitor_key=monitor_key,
        owner_status=owner_status,
        summary=summary,
        intervention=intervention,
        ticket_id=ticket_id,
        incident_id=incident_id,
        updated_at_ms=updated_at_ms,
    )
