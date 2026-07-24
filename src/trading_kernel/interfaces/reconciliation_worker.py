"""Own venue truth, position reconciliation, settlement, and review closure."""

from __future__ import annotations

import asyncio
from decimal import Decimal
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
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.application.recover_unknown_command import (
    RecoverUnknownCommandRequest,
    recover_unknown_command,
)
from src.trading_kernel.application.runtime_facts import (
    PositionSnapshotRequest,
    PositionSnapshotSource,
    ReviewEconomicsRequest,
    ReviewEconomicsSource,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryPartiallyFilled,
    ExternalFlatDetected,
    PositionFlatConfirmed,
    TradeEvent,
)
from src.trading_kernel.domain.review import (
    ReviewEconomicsUnavailable,
    calculate_review_economics,
)


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
    RUNTIME_FENCED = "runtime_fenced"
    UNKNOWN_RECOVERED = "unknown_recovered"
    POSITION_RECONCILED = "position_reconciled"
    FACTS_UNAVAILABLE = "facts_unavailable"
    SETTLED = "settled"
    REVIEWED = "reviewed"


class ReconciliationWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    timeout_seconds: float
    unknown_visibility_grace_ms: int
    idle_poll_interval_ms: int

    @field_validator("worker_id", "runtime_commit", "schema_revision", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("reconciliation worker identities must be non-blank")
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
    *,
    review_economics_source: ReviewEconomicsSource | None = None,
) -> ReconciliationWorkerResult:
    async with uow_factory() as uow:
        unknown = await uow.exchange_commands.get_one_unknown()
    if unknown is not None:
        if not await _runtime_writer_is_certified(uow_factory, request):
            return _runtime_fenced_result(ticket_id=unknown.ticket_identity.ticket_id)
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
        if not await _runtime_writer_is_certified(uow_factory, request):
            return _runtime_fenced_result(ticket_id=aggregate.identity.ticket_id)
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

    if not await _runtime_writer_is_certified(uow_factory, request):
        return _runtime_fenced_result()

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
            (AggregateStatus.REVIEW_PENDING,),
            work_kind="reconciliation",
            now_ms=request.now_ms,
        )
        if review is not None:
            commands = await uow.exchange_commands.list_for_ticket(
                review.identity.ticket_id
            )
            events = await uow.events.list_for_ticket(review.identity.ticket_id)
            review_window = _review_window(events)
            exit_client_ids = _review_exit_client_ids(commands)
            if review_window is None or not exit_client_ids:
                await uow.aggregates.schedule_next_check(
                    review.identity.ticket_id,
                    work_kind="reconciliation",
                    due_at_ms=request.now_ms + request.idle_poll_interval_ms,
                )
                return ReconciliationWorkerResult(
                    status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                    ticket_id=review.identity.ticket_id,
                    detail="review_lineage:incomplete",
                )
            entry_time_ms, exit_time_ms, executed_entry_quantity = review_window
            overlapping_exposure = (
                await uow.tickets.has_other_instrument_ticket_in_window(
                    ticket_id=review.identity.ticket_id,
                    venue_id=review.identity.netting_domain.venue_id,
                    account_id=review.identity.netting_domain.account_id,
                    exchange_instrument_id=(
                        review.identity.netting_domain.exchange_instrument_id
                    ),
                    entry_time_ms=entry_time_ms,
                    exit_time_ms=exit_time_ms,
                )
            )
            entry_client_id = _entry_client_id(commands)
            if entry_client_id is None:
                await uow.aggregates.schedule_next_check(
                    review.identity.ticket_id,
                    work_kind="reconciliation",
                    due_at_ms=request.now_ms + request.idle_poll_interval_ms,
                )
                return ReconciliationWorkerResult(
                    status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                    ticket_id=review.identity.ticket_id,
                    detail="review_entry_command:missing",
                )

    if review is not None:
        assert entry_client_id is not None
        if review_economics_source is None:
            await _schedule_review_retry(
                uow_factory,
                ticket_id=review.identity.ticket_id,
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                ticket_id=review.identity.ticket_id,
                detail="review_economics_source:missing",
            )
        try:
            economics_facts = await asyncio.wait_for(
                review_economics_source.read_review_economics(
                    ReviewEconomicsRequest(
                        ticket_id=review.identity.ticket_id,
                        netting_domain=review.identity.netting_domain,
                        expected_entry_quantity=executed_entry_quantity,
                        entry_venue_client_order_id=entry_client_id,
                        exit_venue_client_order_ids=exit_client_ids,
                        entry_time_ms=entry_time_ms,
                        exit_time_ms=exit_time_ms,
                        funding_attribution_exact=not overlapping_exposure,
                        observed_at_ms=request.now_ms,
                    )
                ),
                timeout=request.timeout_seconds,
            )
            if economics_facts.ticket_id != review.identity.ticket_id:
                raise ReviewEconomicsUnavailable(
                    "review economics Ticket identity mismatch"
                )
            economics = calculate_review_economics(
                facts=economics_facts,
                expected_entry_quantity=executed_entry_quantity,
                position_side=review.identity.netting_domain.position_side,
                planned_risk_at_stop=review.ticket.risk_at_stop,
                actual_risk_at_stop=review.actual_stop_risk,
            )
        except Exception as exc:
            await _schedule_review_retry(
                uow_factory,
                ticket_id=review.identity.ticket_id,
                due_at_ms=request.now_ms + request.idle_poll_interval_ms,
            )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                ticket_id=review.identity.ticket_id,
                detail=f"review_economics:{type(exc).__name__}",
            )

        metrics = {
            "signal_event_id": review.identity.signal_event_id,
            "event_spec_id": review.identity.runtime.event_spec_id,
            "ticket_quantity": str(review.ticket.quantity),
            "executed_entry_quantity": str(executed_entry_quantity),
            **economics.model_dump(mode="json"),
        }
        async with uow_factory() as uow:
            await record_trade_review(
                uow,
                RecordTradeReviewRequest(
                    ticket_id=review.identity.ticket_id,
                    review_id=f"review:{review.identity.ticket_id}",
                    outcome="terminal_flat",
                    metrics=metrics,
                    decision_impact={
                        "status": "recorded",
                        "economics_completeness": (
                            economics.economics_completeness.value
                        ),
                    },
                    recorded_at_ms=request.now_ms,
                ),
            )
        return ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.REVIEWED,
            ticket_id=review.identity.ticket_id,
        )

    return ReconciliationWorkerResult(status=ReconciliationWorkerStatus.NO_WORK)


async def _runtime_writer_is_certified(
    uow_factory: UnitOfWorkFactory,
    request: ReconciliationWorkerRequest,
) -> bool:
    return await runtime_writer_is_certified(
        uow_factory,
        worker_id=request.worker_id,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        observed_at_ms=request.now_ms,
    )


def _runtime_fenced_result(*, ticket_id: str | None = None) -> ReconciliationWorkerResult:
    return ReconciliationWorkerResult(
        status=ReconciliationWorkerStatus.RUNTIME_FENCED,
        ticket_id=ticket_id,
        detail="runtime_identity_mismatch",
    )


def _review_window(
    events: list[TradeEvent],
) -> tuple[int, int, Decimal] | None:
    entry_events = [
        event
        for event in events
        if isinstance(event, (EntryFilled, EntryPartiallyFilled))
    ]
    flat_events = [
        event
        for event in events
        if isinstance(event, (PositionFlatConfirmed, ExternalFlatDetected))
    ]
    if len(entry_events) != 1 or not flat_events:
        return None
    entry = entry_events[0]
    exit_event = min(
        (event for event in flat_events if event.occurred_at_ms >= entry.occurred_at_ms),
        key=lambda event: event.occurred_at_ms,
        default=None,
    )
    if exit_event is None:
        return None
    return entry.occurred_at_ms, exit_event.occurred_at_ms, entry.filled_qty


def _entry_client_id(commands: list[ExchangeCommand]) -> str | None:
    entries = [
        command
        for command in commands
        if command.kind is ExchangeCommandKind.ENTRY
        and command.status
        in {
            ExchangeCommandStatus.ACCEPTED,
            ExchangeCommandStatus.RECONCILED_ACCEPTED,
        }
    ]
    if len(entries) != 1:
        return None
    return entries[0].venue_client_order_id


def _review_exit_client_ids(
    commands: list[ExchangeCommand],
) -> tuple[str, ...]:
    accepted_statuses = {
        ExchangeCommandStatus.ACCEPTED,
        ExchangeCommandStatus.RECONCILED_ACCEPTED,
    }
    identities = (
        command.venue_client_order_id
        for command in commands
        if command.kind
        not in {ExchangeCommandKind.ENTRY, ExchangeCommandKind.CANCEL_ORDER}
        and command.status in accepted_statuses
    )
    return tuple(dict.fromkeys(identities))


async def _schedule_review_retry(
    uow_factory: UnitOfWorkFactory,
    *,
    ticket_id: str,
    due_at_ms: int,
) -> None:
    async with uow_factory() as uow:
        await uow.aggregates.schedule_next_check(
            ticket_id,
            work_kind="reconciliation",
            due_at_ms=due_at_ms,
        )
