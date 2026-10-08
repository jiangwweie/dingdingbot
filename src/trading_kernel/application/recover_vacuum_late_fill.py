"""Recover an exactly attributed post-absence fill on the original Ticket."""

from __future__ import annotations

import asyncio
import math
from enum import StrEnum
from time import monotonic
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
    UnitOfWorkFactory,
    VenueTruthPort,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    PositionSnapshotRequest,
    PositionSnapshotSource,
)
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    VacuumLateFillAttributed,
    VacuumPostAbsenceNoFillVerified,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuumState
from src.trading_kernel.domain.vacuum_late_fill import (
    VacuumLateFillAttributionInput,
    VacuumLateFillAttributionStatus,
    decide_vacuum_late_fill_attribution,
)


class RecoverVacuumLateFillStatus(StrEnum):
    NO_CHANGE = "no_change"
    UNVERIFIED = "unverified"
    ATTRIBUTED = "attributed"
    NO_FILL_CLOSED = "no_fill_closed"


class RecoverVacuumLateFillRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    worker_id: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    timeout_seconds: float

    @field_validator(
        "ticket_id", "worker_id", "runtime_commit", "schema_revision", mode="before",
    )
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("late fill recovery requires Ticket identity")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> RecoverVacuumLateFillRequest:
        if (
            self.now_ms <= 0
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("late fill recovery window must be positive")
        return self


class RecoverVacuumLateFillResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RecoverVacuumLateFillStatus
    reason_code: str
    event_id: str | None = None


class _AttributionEventFields(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int
    entry_vacuum_id: str
    entry_command_id: str
    exchange_order_id: str
    venue_client_order_id: str
    position_observed_at_ms: int
    venue_observed_at_ms: int


async def recover_vacuum_late_fill(
    uow_factory: UnitOfWorkFactory,
    position_source: PositionSnapshotSource,
    venue_truth: VenueTruthPort,
    request: RecoverVacuumLateFillRequest,
) -> RecoverVacuumLateFillResult:
    """Read external truth outside PostgreSQL, then commit one exact reduction."""

    started_monotonic = monotonic()
    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(request.ticket_id)
        incident = await uow.incidents.get_open_for_ticket_kind(
            request.ticket_id, "vacuum_post_absence_contradiction",
        )
        if (
            aggregate is None
            or aggregate.status is not AggregateStatus.ENTRY_VACUUM_CANCELLED
            or aggregate.position_qty != 0
            or aggregate.entry_vacuum_id is None
            or aggregate.entry_exchange_order_id is None
            or incident is None
        ):
            return _result(RecoverVacuumLateFillStatus.NO_CHANGE, "not_recoverable")
        commands = await uow.exchange_commands.list_for_ticket(request.ticket_id)
        if any(command.status in {
            ExchangeCommandStatus.PREPARED,
            ExchangeCommandStatus.CLAIMED,
            ExchangeCommandStatus.OUTCOME_UNKNOWN,
        } for command in commands):
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "command_outcome_unresolved")
        entries = tuple(command for command in commands if command.kind is ExchangeCommandKind.ENTRY)
        if len(entries) != 1 or entries[0].venue_client_order_id is None:
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "entry_command_missing")
        command = entries[0]
        client_id = command.venue_client_order_id
        assert client_id is not None
        domain = aggregate.identity.netting_domain
        original_version = aggregate.version

    try:
        position = await asyncio.wait_for(
            position_source.read_position_snapshot(PositionSnapshotRequest(
                ticket_id=request.ticket_id,
                netting_domain=domain,
                observed_at_ms=request.now_ms,
            )),
            timeout=request.timeout_seconds,
        )
        truth = await asyncio.wait_for(
            venue_truth.lookup_command_truth(VenueTruthRequest(
                command_id=command.command_id,
                kind=command.kind,
                venue_id=domain.venue_id,
                account_id=domain.account_id,
                exchange_instrument_id=domain.exchange_instrument_id,
                position_side=domain.position_side,
                venue_client_order_id=client_id,
                payload=command.payload,
                observed_at_ms=request.now_ms,
            )),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - ambiguous external truth stays fenced.
        return _result(
            RecoverVacuumLateFillStatus.UNVERIFIED,
            f"source_unavailable:{type(exc).__name__}",
        )

    decision = decide_vacuum_late_fill_attribution(VacuumLateFillAttributionInput(
        ticket=aggregate.ticket,
        entry_command=command,
        entry_exchange_order_id=aggregate.entry_exchange_order_id or "",
        position=position,
        venue_truth=truth,
        contradiction_observed_at_ms=incident.opened_at_ms,
    ))
    if decision.status is VacuumLateFillAttributionStatus.UNVERIFIED:
        return _result(RecoverVacuumLateFillStatus.UNVERIFIED, decision.reason_code)
    if not late_fill_commit_window_open(
        started_monotonic=started_monotonic,
        current_monotonic=monotonic(),
        timeout_seconds=request.timeout_seconds,
    ):
        return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "source_window_elapsed")

    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=request.worker_id,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        observed_at_ms=request.now_ms,
    ):
        return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "runtime_fenced")

    async with uow_factory() as uow:
        capability = await uow.signals.get_runtime_capability(
            "exchange_commands", for_update=True,
        )
        if (
            capability is None
            or not capability.enabled
            or capability.certified_commit != request.runtime_commit
            or capability.schema_revision != request.schema_revision
        ):
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "runtime_fenced")
        if not late_fill_commit_window_open(
            started_monotonic=started_monotonic,
            current_monotonic=monotonic(),
            timeout_seconds=request.timeout_seconds,
        ):
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "source_window_elapsed")
        vacuum = await uow.instrument_selection.get_entry_vacuum_by_id(
            aggregate.entry_vacuum_id, for_update=True,
        )
        current = await uow.aggregates.get_for_update(request.ticket_id)
        active_incident = await uow.incidents.get_open_for_ticket_kind(
            request.ticket_id, "vacuum_post_absence_contradiction",
        )
        if (
            current is None
            or current.version != original_version
            or current.status is not AggregateStatus.ENTRY_VACUUM_CANCELLED
            or current.position_qty != 0
            or current.entry_vacuum_id != aggregate.entry_vacuum_id
            or active_incident is None
            or active_incident.incident_id != incident.incident_id
            or vacuum is None
            or vacuum.entry_vacuum_id != current.entry_vacuum_id
            or vacuum.strategy_group_id != current.identity.runtime.strategy_group_id
            or vacuum.state is not StrategyEntryVacuumState.DRAINING_ENTRY
        ):
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "authority_changed")
        current_command = await uow.exchange_commands.get(command.command_id)
        prior_position = await uow.positions.get(domain.key())
        if (
            current_command != command
            or prior_position is None
            or position.observed_at_ms <= prior_position.observed_at_ms
            or position.observed_at_ms < request.now_ms
            or truth.observed_at_ms > request.now_ms + int(request.timeout_seconds * 2_000) + 2_000
        ):
            return _result(RecoverVacuumLateFillStatus.UNVERIFIED, "source_or_command_changed")
        assert decision.proof_digest is not None
        common: _AttributionEventFields = {
            "event_id": f"event:{request.ticket_id}:{current.last_event_sequence + 1}",
            "ticket_id": request.ticket_id,
            "sequence": current.last_event_sequence + 1,
            "occurred_at_ms": truth.observed_at_ms,
            "entry_vacuum_id": current.entry_vacuum_id,
            "entry_command_id": command.command_id,
            "exchange_order_id": current.entry_exchange_order_id or "",
            "venue_client_order_id": client_id,
            "position_observed_at_ms": position.observed_at_ms,
            "venue_observed_at_ms": truth.observed_at_ms,
        }
        event: VacuumLateFillAttributed | VacuumPostAbsenceNoFillVerified
        if decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED:
            event = VacuumPostAbsenceNoFillVerified(
                **common,
                proof_digest=decision.proof_digest,
            )
        else:
            assert decision.filled_qty is not None
            assert decision.average_fill_price is not None
            event = VacuumLateFillAttributed(
                **common,
                filled_qty=decision.filled_qty,
                average_fill_price=decision.average_fill_price,
                attribution_digest=decision.proof_digest,
            )
        await uow.positions.upsert(ticket_id=request.ticket_id, snapshot=position)
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(current, event),
            expected_version=current.version,
        )
        await uow.monitors.save_if_changed(
            MonitorStateRecord(
                monitor_key=f"vacuum-post-absence:{request.ticket_id}",
                owner_status=(
                    MonitorOwnerStatus.COMPLETED
                    if decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
                    else MonitorOwnerStatus.PROCESSING
                ),
                summary=(
                    "Exact original ENTRY truth proves no fill and terminal closure"
                    if decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
                    else "Exact original ENTRY fill attributed; protection or flatten pending"
                ),
                intervention=(
                    "none"
                    if decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
                    else "Continue original Ticket lifecycle until external-flat closure"
                ),
                ticket_id=request.ticket_id,
                incident_id=(
                    None if decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
                    else active_incident.incident_id
                ),
                updated_at_ms=truth.observed_at_ms,
            )
        )
        retry_monitor = await uow.monitors.get(
            f"vacuum-late-fill-retry:{request.ticket_id}"
        )
        if retry_monitor is not None:
            await uow.monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key=retry_monitor.monitor_key,
                    owner_status=MonitorOwnerStatus.COMPLETED,
                    summary="Exact original ENTRY truth recovered",
                    intervention="none",
                    ticket_id=request.ticket_id,
                    updated_at_ms=truth.observed_at_ms,
                )
            )
    no_fill = decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
    return RecoverVacuumLateFillResult(
        status=(RecoverVacuumLateFillStatus.NO_FILL_CLOSED if no_fill
            else RecoverVacuumLateFillStatus.ATTRIBUTED),
        reason_code=("exact_original_entry_no_fill" if no_fill
            else "exact_original_entry_fill"),
        event_id=event.event_id,
    )


def _result(status: RecoverVacuumLateFillStatus, reason_code: str) -> RecoverVacuumLateFillResult:
    return RecoverVacuumLateFillResult(status=status, reason_code=reason_code)


def late_fill_commit_window_open(
    *, started_monotonic: float, current_monotonic: float, timeout_seconds: float,
) -> bool:
    return (
        math.isfinite(started_monotonic)
        and math.isfinite(current_monotonic)
        and math.isfinite(timeout_seconds)
        and timeout_seconds > 0
        and started_monotonic <= current_monotonic
        and current_monotonic - started_monotonic <= 2 * timeout_seconds + 1
    )
