"""Own venue truth, position reconciliation, settlement, and review closure."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    UnitOfWorkFactory,
    VenueTruthPort,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.application.recover_unknown_command import (
    RecoverUnknownCommandRequest,
    recover_unknown_command,
)
from src.trading_kernel.application.runtime_facts import (
    PositionSnapshotRequest,
    PositionSnapshotSource,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus


_POSITION_RECONCILIATION_STATUSES = (
    AggregateStatus.ENTRY_ACCEPTED,
    AggregateStatus.PARTIAL_FILL_INCIDENT,
    AggregateStatus.PARTIAL_FILL_CANCEL_REJECTED,
    AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN,
    AggregateStatus.PROTECTION_PENDING,
    AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN,
    AggregateStatus.TP1_PENDING,
    AggregateStatus.TP1_REJECTED,
    AggregateStatus.TP1_OUTCOME_UNKNOWN,
    AggregateStatus.POSITION_PROTECTED,
    AggregateStatus.RUNNER_REPLACEMENT_PENDING,
    AggregateStatus.RUNNER_REPLACEMENT_REJECTED,
    AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
    AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
    AggregateStatus.RUNNER_OLD_STOP_CANCEL_REJECTED,
    AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
    AggregateStatus.RUNNER_PROTECTED,
    AggregateStatus.EXIT_PENDING,
    AggregateStatus.EXIT_ACCEPTED,
    AggregateStatus.EXIT_REJECTED,
    AggregateStatus.EXIT_OUTCOME_UNKNOWN,
    AggregateStatus.CONTROLLED_FLATTEN_PENDING,
    AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
    AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
    AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
    AggregateStatus.RECONCILIATION_PENDING,
    AggregateStatus.CANCEL_REJECTED,
    AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
)


class ReconciliationWorkerStatus(StrEnum):
    NO_WORK = "no_work"
    UNKNOWN_RECOVERED = "unknown_recovered"
    POSITION_RECONCILED = "position_reconciled"
    FACTS_UNAVAILABLE = "facts_unavailable"
    SETTLED = "settled"
    REVIEWED = "reviewed"


class ReconciliationWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    now_ms: int
    timeout_seconds: float
    unknown_visibility_grace_ms: int
    idle_poll_interval_ms: int

    @field_validator("worker_id", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("reconciliation worker identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "ReconciliationWorkerRequest":
        if (
            self.now_ms <= 0
            or self.timeout_seconds <= 0
            or self.unknown_visibility_grace_ms <= 0
            or self.idle_poll_interval_ms <= 0
        ):
            raise ValueError("reconciliation worker windows must be positive")
        return self


class ReconciliationWorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReconciliationWorkerStatus
    ticket_id: str | None = None
    command_id: str | None = None
    reconciliation_status: ReconcileTicketStatus | None = None
    detail: str | None = None


async def run_reconciliation_worker_once(
    uow_factory: UnitOfWorkFactory,
    venue_truth: VenueTruthPort,
    position_source: PositionSnapshotSource,
    request: ReconciliationWorkerRequest,
) -> ReconciliationWorkerResult:
    async with uow_factory() as uow:
        unknown = await uow.exchange_commands.get_one_unknown()
    if unknown is not None:
        decision = await recover_unknown_command(
            uow_factory,
            venue_truth,
            RecoverUnknownCommandRequest(
                command_id=unknown.command_id,
                now_ms=request.now_ms,
                visibility_deadline_ms=(
                    unknown.deadline_at_ms + request.unknown_visibility_grace_ms
                ),
                timeout_seconds=request.timeout_seconds,
            ),
        )
        return ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.UNKNOWN_RECOVERED,
            ticket_id=unknown.ticket_identity.ticket_id,
            command_id=unknown.command_id,
            detail=decision.status.value,
        )

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get_next_for_statuses(
            _POSITION_RECONCILIATION_STATUSES,
            work_kind="reconciliation",
            now_ms=request.now_ms,
        )
    if aggregate is not None:
        snapshot_request = PositionSnapshotRequest(
            ticket_id=aggregate.identity.ticket_id,
            netting_domain=aggregate.identity.netting_domain,
            observed_at_ms=request.now_ms,
        )
        try:
            snapshot = await asyncio.wait_for(
                position_source.read_position_snapshot(snapshot_request),
                timeout=request.timeout_seconds,
            )
        except Exception as exc:
            async with uow_factory() as uow:
                await uow.aggregates.schedule_next_check(
                    aggregate.identity.ticket_id,
                    work_kind="reconciliation",
                    due_at_ms=request.now_ms + request.idle_poll_interval_ms,
                )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                ticket_id=aggregate.identity.ticket_id,
                detail=f"position_snapshot:{type(exc).__name__}",
            )
        async with uow_factory() as uow:
            reconciled = await reconcile_ticket(
                uow,
                ReconcileTicketRequest(
                    ticket_id=aggregate.identity.ticket_id,
                    snapshot=snapshot,
                ),
            )
            await uow.aggregates.schedule_next_check(
                aggregate.identity.ticket_id,
                work_kind="reconciliation",
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
        return ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.POSITION_RECONCILED,
            ticket_id=aggregate.identity.ticket_id,
            reconciliation_status=reconciled.status,
        )

    async with uow_factory() as uow:
        settlement = await uow.aggregates.get_next_for_statuses(
            (AggregateStatus.SETTLEMENT_PENDING,)
        )
        if settlement is not None:
            await settle_ticket(
                uow,
                SettleTicketRequest(
                    ticket_id=settlement.identity.ticket_id,
                    settled_at_ms=request.now_ms,
                ),
            )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.SETTLED,
                ticket_id=settlement.identity.ticket_id,
            )

        review = await uow.aggregates.get_next_for_statuses(
            (AggregateStatus.REVIEW_PENDING,)
        )
        if review is not None:
            await record_trade_review(
                uow,
                RecordTradeReviewRequest(
                    ticket_id=review.identity.ticket_id,
                    review_id=f"review:{review.identity.ticket_id}",
                    outcome="terminal_flat",
                    metrics={
                        "signal_event_id": review.identity.signal_event_id,
                        "event_spec_id": review.identity.runtime.event_spec_id,
                        "entry_quantity": str(review.ticket.quantity),
                        "entry_average_price": str(review.average_fill_price),
                        "risk_at_stop": str(review.ticket.risk_at_stop),
                    },
                    decision_impact={"status": "recorded"},
                    recorded_at_ms=request.now_ms,
                ),
            )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.REVIEWED,
                ticket_id=review.identity.ticket_id,
            )

    return ReconciliationWorkerResult(status=ReconciliationWorkerStatus.NO_WORK)
