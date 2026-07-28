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
from src.trading_kernel.domain.aggregate import (
    RECONCILIATION_POSITION_STATUSES,
    AggregateStatus,
)
from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.order_attribution import (
    OrderRole,
    TicketOrderReference,
    attribution_digest,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryPartiallyFilled,
    ExternalFlatDetected,
    PositionFlatConfirmed,
    TradeEvent,
)
from src.trading_kernel.domain.review import (
    ExternalExitUnavailableReview,
    ReviewEconomicsCompleteness,
    ReviewEconomicsUnavailable,
    calculate_review_economics,
)
from src.trading_kernel.domain.venue_truth import UnknownRecoveryStatus


_POSITION_RECONCILIATION_STATUSES = RECONCILIATION_POSITION_STATUSES


class ReconciliationWorkKind(StrEnum):
    POSITION = "position"
    SETTLEMENT = "settlement"
    REVIEW = "review"


class ReconciliationWorkItem(BaseModel):
    """One bounded Reconciliation action selected outside venue I/O."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    kind: ReconciliationWorkKind
    status: AggregateStatus
    due_at_ms: int
    status_entered_at_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("reconciliation work requires Ticket identity")
        return normalized

    @model_validator(mode="after")
    def _validate_kind_and_window(self) -> "ReconciliationWorkItem":
        if self.due_at_ms <= 0 or self.status_entered_at_ms <= 0:
            raise ValueError("reconciliation work times must be positive")
        if self.kind is ReconciliationWorkKind.POSITION:
            if self.status not in _POSITION_RECONCILIATION_STATUSES:
                raise ValueError("position work requires a position reconciliation status")
        elif self.kind is ReconciliationWorkKind.SETTLEMENT:
            if self.status is not AggregateStatus.SETTLEMENT_PENDING:
                raise ValueError("settlement work requires SETTLEMENT_PENDING")
        elif self.status is not AggregateStatus.REVIEW_PENDING:
            raise ValueError("review work requires REVIEW_PENDING")
        return self


def select_reconciliation_work(
    *,
    now_ms: int,
    closure_starvation_limit_ms: int,
    position: ReconciliationWorkItem | None,
    closures: tuple[ReconciliationWorkItem, ...],
) -> ReconciliationWorkItem | None:
    """Select one due item while bounding closure starvation behind positions."""

    if now_ms <= 0 or closure_starvation_limit_ms <= 0:
        raise ValueError("reconciliation selector windows must be positive")
    if position is not None and position.kind is not ReconciliationWorkKind.POSITION:
        raise ValueError("position candidate must use position work kind")
    if any(
        item.kind not in {ReconciliationWorkKind.SETTLEMENT, ReconciliationWorkKind.REVIEW}
        for item in closures
    ):
        raise ValueError("closure candidates must use settlement or review work kinds")

    due_position = position if position is not None and position.due_at_ms <= now_ms else None
    due_closures = tuple(item for item in closures if item.due_at_ms <= now_ms)
    oldest_closure = min(
        due_closures,
        key=lambda item: (item.status_entered_at_ms, item.due_at_ms, item.ticket_id),
        default=None,
    )
    if (
        oldest_closure is not None
        and now_ms - oldest_closure.status_entered_at_ms
        >= closure_starvation_limit_ms
    ):
        return oldest_closure
    if due_position is not None:
        return due_position
    return oldest_closure


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
    closure_starvation_limit_ms: int = 30_000
    closure_retry_interval_ms: int = 30_000
    review_economics_visibility_grace_ms: int = 300_000

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
            or self.closure_starvation_limit_ms <= 0
            or self.closure_retry_interval_ms <= 0
            or self.review_economics_visibility_grace_ms <= 0
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
    pending_unknown_result: ReconciliationWorkerResult | None = None
    external_fallback_without_exit = False
    review: TradeAggregate | None = None
    entry_order_reference: TicketOrderReference | None = None
    exit_order_references: tuple[TicketOrderReference, ...] = ()
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
        recovered_result = ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.UNKNOWN_RECOVERED,
            ticket_id=unknown.ticket_identity.ticket_id,
            command_id=unknown.command_id,
            detail=decision.status.value,
        )
        if decision.status not in {
            UnknownRecoveryStatus.PENDING_VISIBILITY,
            UnknownRecoveryStatus.LOOKUP_FAILED,
        }:
            return recovered_result
        pending_unknown_result = recovered_result

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get_next_reconciliation_work(
            now_ms=request.now_ms,
            closure_starvation_limit_ms=request.closure_starvation_limit_ms,
        )
    if (
        aggregate is not None
        and aggregate.status in _POSITION_RECONCILIATION_STATUSES
    ):
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
        if aggregate is not None and aggregate.status is AggregateStatus.SETTLEMENT_PENDING:
            await settle_ticket(
                uow,
                SettleTicketRequest(
                    ticket_id=aggregate.identity.ticket_id,
                    settled_at_ms=request.now_ms,
                ),
            )
            return ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.SETTLED,
                ticket_id=aggregate.identity.ticket_id,
            )

        if aggregate is not None and aggregate.status is AggregateStatus.REVIEW_PENDING:
            review = aggregate
            order_references = await uow.exchange_commands.list_order_references(
                review.identity.ticket_id
            )
            events = await uow.events.list_for_ticket(review.identity.ticket_id)
            review_window = _review_window(events)
            entry_references = tuple(
                reference
                for reference in order_references
                if reference.role is OrderRole.ENTRY
            )
            exit_order_references = tuple(
                reference
                for reference in order_references
                if reference.role is OrderRole.EXIT
            )
            if review_window is None:
                await uow.aggregates.schedule_next_check(
                    review.identity.ticket_id,
                    work_kind="reconciliation",
                    due_at_ms=request.now_ms + request.closure_retry_interval_ms,
                )
                return ReconciliationWorkerResult(
                    status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                    ticket_id=review.identity.ticket_id,
                    detail="review_lineage:incomplete",
                )
            entry_time_ms = review_window.entry_time_ms
            exit_time_ms = review_window.exit_time_ms
            executed_entry_quantity = review_window.executed_entry_quantity
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
            if len(entry_references) != 1:
                await uow.aggregates.schedule_next_check(
                    review.identity.ticket_id,
                    work_kind="reconciliation",
                    due_at_ms=request.now_ms + request.closure_retry_interval_ms,
                )
                return ReconciliationWorkerResult(
                    status=ReconciliationWorkerStatus.FACTS_UNAVAILABLE,
                    ticket_id=review.identity.ticket_id,
                    detail="review_entry_command:missing",
                )
            entry_order_reference = entry_references[0]
            if not exit_order_references:
                if _external_review_fallback_due(review_window, request):
                    external_fallback_without_exit = True
                else:
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

    if review is not None:
        assert entry_order_reference is not None
        assert review_window is not None
        if external_fallback_without_exit:
            return await _record_external_exit_unavailable_review(
                uow_factory,
                review=review,
                review_window=review_window,
                recorded_at_ms=request.now_ms,
                executed_entry_quantity=executed_entry_quantity,
                visibility_grace_ms=request.review_economics_visibility_grace_ms,
            )
        if review_economics_source is None:
            await _schedule_review_retry(
                uow_factory,
                ticket_id=review.identity.ticket_id,
                due_at_ms=request.now_ms + request.closure_retry_interval_ms,
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
                        entry_order_reference=entry_order_reference,
                        exit_order_references=exit_order_references,
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
            if _external_review_fallback_due(review_window, request):
                return await _record_external_exit_unavailable_review(
                    uow_factory,
                    review=review,
                    review_window=review_window,
                    recorded_at_ms=request.now_ms,
                    executed_entry_quantity=executed_entry_quantity,
                    visibility_grace_ms=(
                        request.review_economics_visibility_grace_ms
                    ),
                )
            await _schedule_review_retry(
                uow_factory,
                ticket_id=review.identity.ticket_id,
                due_at_ms=request.now_ms + request.closure_retry_interval_ms,
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
            "order_attribution": [
                fill.model_dump(mode="json")
                for fill in (*economics_facts.entry_fills, *economics_facts.exit_fills)
            ],
            "order_attribution_digest": attribution_digest(
                tuple(
                    fill.to_attributed_trade_fill()
                    for fill in (
                        *economics_facts.entry_fills,
                        *economics_facts.exit_fills,
                    )
                )
            ),
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

    if pending_unknown_result is not None:
        return pending_unknown_result
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


class _ReviewWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_time_ms: int
    exit_time_ms: int
    executed_entry_quantity: Decimal
    external_flat: bool


def _review_window(events: list[TradeEvent]) -> _ReviewWindow | None:
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
    return _ReviewWindow(
        entry_time_ms=entry.occurred_at_ms,
        exit_time_ms=exit_event.occurred_at_ms,
        executed_entry_quantity=entry.filled_qty,
        external_flat=isinstance(exit_event, ExternalFlatDetected),
    )


def _external_review_fallback_due(
    review_window: _ReviewWindow,
    request: ReconciliationWorkerRequest,
) -> bool:
    return (
        review_window.external_flat
        and request.now_ms
        >= review_window.exit_time_ms + request.review_economics_visibility_grace_ms
    )


async def _record_external_exit_unavailable_review(
    uow_factory: UnitOfWorkFactory,
    *,
    review,
    review_window: _ReviewWindow,
    recorded_at_ms: int,
    executed_entry_quantity: Decimal,
    visibility_grace_ms: int,
) -> ReconciliationWorkerResult:
    unavailable = ExternalExitUnavailableReview(
        economics_completeness=ReviewEconomicsCompleteness.EXTERNAL_EXIT_UNAVAILABLE,
        unavailable_reason="external_flat_exit_fills_unavailable",
        entry_quantity=executed_entry_quantity,
        entry_time_ms=review_window.entry_time_ms,
        external_flat_detected_at_ms=review_window.exit_time_ms,
        visibility_grace_ms=visibility_grace_ms,
    )
    metrics = {
        "signal_event_id": review.identity.signal_event_id,
        "event_spec_id": review.identity.runtime.event_spec_id,
        "ticket_quantity": str(review.ticket.quantity),
        "executed_entry_quantity": str(executed_entry_quantity),
        **unavailable.model_dump(mode="json"),
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
                    "status": "recorded_with_external_exit_unavailable",
                    "economics_completeness": unavailable.economics_completeness.value,
                },
                recorded_at_ms=recorded_at_ms,
            ),
        )
    return ReconciliationWorkerResult(
        status=ReconciliationWorkerStatus.REVIEWED,
        ticket_id=review.identity.ticket_id,
    )


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
