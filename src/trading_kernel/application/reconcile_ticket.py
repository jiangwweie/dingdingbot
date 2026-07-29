"""Reconcile one exact Ticket against one typed venue snapshot."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    MonitorOwnerStatus,
    MonitorStateRecord,
    RuntimeIncidentRecord,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    CrossMarginStressStatus,
    StressPosition,
    evaluate_cross_margin_stress,
)
from src.trading_kernel.domain.events import (
    CancelOrderAbsenceConfirmed,
    EntryFilled,
    EntryPartiallyFilled,
    ExitRequested,
    ExternalFlatDetected,
    OwnedOrderAbsenceConfirmed,
    OwnedOrphanOrderDetected,
    PositionFlatConfirmed,
    PostFillStressAssessed,
    ReconciliationMatched,
    TradeEvent,
    UnownedOrderDetected,
)
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.post_fill_risk import (
    PostFillRiskRequest,
    assess_post_fill_risk,
)
from src.trading_kernel.domain.reducer import reduce_event


class ReconcileTicketStatus(StrEnum):
    NO_CHANGE = "no_change"
    ENTRY_FILL_RECORDED = "entry_fill_recorded"
    PARTIAL_FILL_INCIDENT = "partial_fill_incident"
    EXTERNAL_FLAT_INCIDENT = "external_flat_incident"
    POSITION_FLAT_RECORDED = "position_flat_recorded"
    PROTECTION_RESIDUE = "protection_residue"
    CANCEL_ABSENCE_RECORDED = "cancel_absence_recorded"
    OWNED_ORPHAN_CANCEL_REQUESTED = "owned_orphan_cancel_requested"
    UNOWNED_ORDER_INCIDENT = "unowned_order_incident"
    MATCHED = "matched"


class ExitTicketStatus(StrEnum):
    REQUESTED = "requested"


class PostFillStressReconcileStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    FACTS_UNAVAILABLE = "facts_unavailable"
    FACTS_CONTRADICTORY = "facts_contradictory"
    NO_CHANGE = "no_change"


class ReconcileTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    snapshot: PositionSnapshot


class ExitTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    reason: str
    requested_at_ms: int

    @field_validator("reason", mode="before")
    @classmethod
    def _require_reason(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("exit reason must be non-blank")
        return normalized


class ReconcileTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReconcileTicketStatus


class ExitTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExitTicketStatus


class PostFillStressReconcileRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    account_snapshot: AccountRiskSnapshot
    instrument_rules: InstrumentRulesFacts
    assessed_at_ms: int


class PostFillStressReconcileResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PostFillStressReconcileStatus


async def reconcile_ticket(
    uow: KernelUnitOfWork,
    request: ReconcileTicketRequest,
) -> ReconcileTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    snapshot = request.snapshot
    if snapshot.netting_domain != aggregate.identity.netting_domain:
        raise ValueError("position snapshot Netting Domain mismatch")
    await uow.positions.upsert(ticket_id=request.ticket_id, snapshot=snapshot)
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=(
                "venue-liquidation-observation:"
                f"{request.ticket_id}"
            ),
            owner_status=MonitorOwnerStatus.RUNNING,
            summary=(
                "Venue liquidation observation is audit-only: "
                f"{_venue_liquidation_observation_code(snapshot)}"
            ),
            intervention="none",
            ticket_id=request.ticket_id,
            incident_id=None,
            updated_at_ms=snapshot.observed_at_ms,
        )
    )

    event: TradeEvent | None = None
    status = ReconcileTicketStatus.NO_CHANGE
    if aggregate.status is AggregateStatus.ENTRY_ACCEPTED:
        if snapshot.quantity == aggregate.ticket.quantity:
            event = EntryFilled(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                filled_qty=snapshot.quantity,
                average_fill_price=_required_average_entry_price(snapshot),
                post_fill_risk=assess_post_fill_risk(
                    PostFillRiskRequest(
                        position_side=aggregate.identity.netting_domain.position_side,
                        filled_quantity=snapshot.quantity,
                        average_fill_price=_required_average_entry_price(snapshot),
                        initial_stop_price=aggregate.ticket.initial_stop_price,
                        planned_stop_risk_budget=(
                            aggregate.ticket.planned_stop_risk_budget
                        ),
                        post_fill_stop_risk_limit=(
                            aggregate.ticket.post_fill_stop_risk_limit
                        ),
                    )
                ),
                venue_reported_liquidation_price=(
                    snapshot.venue_reported_liquidation_price
                ),
                position_observed_at_ms=snapshot.observed_at_ms,
            )
            status = ReconcileTicketStatus.ENTRY_FILL_RECORDED
        elif 0 < snapshot.quantity < aggregate.ticket.quantity:
            event = EntryPartiallyFilled(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                filled_qty=snapshot.quantity,
                requested_qty=aggregate.ticket.quantity,
                average_fill_price=_required_average_entry_price(snapshot),
            )
            status = ReconcileTicketStatus.PARTIAL_FILL_INCIDENT
    elif aggregate.status in {
        AggregateStatus.EXIT_PENDING,
        AggregateStatus.EXIT_ACCEPTED,
        AggregateStatus.EXIT_REJECTED,
        AggregateStatus.EXIT_OUTCOME_UNKNOWN,
        AggregateStatus.CONTROLLED_FLATTEN_PENDING,
        AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
        AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
        AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
    } and snapshot.quantity == 0:
        event = PositionFlatConfirmed(
            event_id=_event_id(aggregate),
            ticket_id=request.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=snapshot.observed_at_ms,
        )
        status = ReconcileTicketStatus.POSITION_FLAT_RECORDED
    elif aggregate.status in {
        AggregateStatus.TP1_PENDING,
        AggregateStatus.TP1_REJECTED,
        AggregateStatus.TP1_OUTCOME_UNKNOWN,
        AggregateStatus.POST_FILL_RISK_PENDING,
        AggregateStatus.POSITION_PROTECTED,
        AggregateStatus.RUNNER_REPLACEMENT_PENDING,
        AggregateStatus.RUNNER_REPLACEMENT_REJECTED,
        AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_REJECTED,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_PROTECTED,
    } and snapshot.quantity == 0:
        event = ExternalFlatDetected(
            event_id=_event_id(aggregate),
            ticket_id=request.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=snapshot.observed_at_ms,
        )
        status = ReconcileTicketStatus.EXTERNAL_FLAT_INCIDENT
    elif aggregate.status is AggregateStatus.RECONCILIATION_PENDING:
        if aggregate.pending_cancel_exchange_order_id is not None:
            return ReconcileTicketResult(
                status=ReconcileTicketStatus.PROTECTION_RESIDUE
            )
        unowned_order = next(
            (
                order
                for order in snapshot.open_orders
                if not _is_kernel_owned_order(order.venue_client_order_id)
            ),
            None,
        )
        if unowned_order is not None:
            existing_incident = await uow.incidents.get_open_for_ticket(
                request.ticket_id
            )
            if (
                existing_incident is not None
                and existing_incident.incident_kind == "unowned_open_order"
            ):
                return ReconcileTicketResult(
                    status=ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
                )
            event = UnownedOrderDetected(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=unowned_order.exchange_order_id,
            )
            status = ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
        else:
            known_order_id = _next_known_cleanup_order_id(aggregate)
            if known_order_id is not None:
                known_still_open = any(
                    order.exchange_order_id == known_order_id
                    for order in snapshot.open_orders
                )
                if not known_still_open:
                    event = OwnedOrderAbsenceConfirmed(
                        event_id=_event_id(aggregate),
                        ticket_id=request.ticket_id,
                        sequence=aggregate.last_event_sequence + 1,
                        occurred_at_ms=snapshot.observed_at_ms,
                        exchange_order_id=known_order_id,
                    )
                    status = ReconcileTicketStatus.CANCEL_ABSENCE_RECORDED
                else:
                    commands = await uow.exchange_commands.list_for_ticket(
                        request.ticket_id
                    )
                    if _has_cancel_attempt(commands, known_order_id):
                        return ReconcileTicketResult(
                            status=ReconcileTicketStatus.PROTECTION_RESIDUE
                        )
                    event = OwnedOrphanOrderDetected(
                        event_id=_event_id(aggregate),
                        ticket_id=request.ticket_id,
                        sequence=aggregate.last_event_sequence + 1,
                        occurred_at_ms=snapshot.observed_at_ms,
                        exchange_order_id=known_order_id,
                        order_namespace="conditional",
                    )
                    status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
            elif snapshot.open_orders:
                owned_order = snapshot.open_orders[0]
                commands = await uow.exchange_commands.list_for_ticket(request.ticket_id)
                if _has_cancel_attempt(commands, owned_order.exchange_order_id):
                    return ReconcileTicketResult(
                        status=ReconcileTicketStatus.PROTECTION_RESIDUE
                    )
                event = OwnedOrphanOrderDetected(
                    event_id=_event_id(aggregate),
                    ticket_id=request.ticket_id,
                    sequence=aggregate.last_event_sequence + 1,
                    occurred_at_ms=snapshot.observed_at_ms,
                    exchange_order_id=owned_order.exchange_order_id,
                    order_namespace=owned_order.order_namespace,
                )
                status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
            elif snapshot.quantity == 0:
                event = ReconciliationMatched(
                    event_id=_event_id(aggregate),
                    ticket_id=request.ticket_id,
                    sequence=aggregate.last_event_sequence + 1,
                    occurred_at_ms=snapshot.observed_at_ms,
                )
                status = ReconcileTicketStatus.MATCHED
    elif aggregate.status in {
        AggregateStatus.CANCEL_REJECTED,
        AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
    }:
        target_order_id = aggregate.pending_cancel_exchange_order_id
        if target_order_id is None:
            raise RuntimeError("cancel recovery state has no exact order identity")
        target_order = next(
            (
                order
                for order in snapshot.open_orders
                if order.exchange_order_id == target_order_id
            ),
            None,
        )
        if target_order is not None:
            if aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN:
                return ReconcileTicketResult(
                    status=ReconcileTicketStatus.PROTECTION_RESIDUE
                )
            event = OwnedOrphanOrderDetected(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=target_order_id,
                order_namespace=target_order.order_namespace,
            )
            status = ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
        else:
            event = CancelOrderAbsenceConfirmed(
                event_id=_event_id(aggregate),
                ticket_id=request.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=snapshot.observed_at_ms,
                exchange_order_id=target_order_id,
            )
            status = ReconcileTicketStatus.CANCEL_ABSENCE_RECORDED

    if event is not None:
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
    return ReconcileTicketResult(status=status)


async def reconcile_post_fill_stress(
    uow: KernelUnitOfWork,
    request: PostFillStressReconcileRequest,
) -> PostFillStressReconcileResult:
    """Freeze one post-fill result after rechecking exact protected exposure."""

    aggregate = await uow.aggregates.get_for_update(request.ticket_id)
    if (
        aggregate is None
        or aggregate.status is not AggregateStatus.POST_FILL_RISK_PENDING
    ):
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.NO_CHANGE
        )
    account = request.account_snapshot
    rules = request.instrument_rules
    domain = aggregate.identity.netting_domain
    if (
        request.assessed_at_ms < account.observed_at_ms
        or request.assessed_at_ms >= account.valid_until_ms
        or request.assessed_at_ms < rules.observed_at_ms
        or request.assessed_at_ms >= rules.valid_until_ms
    ):
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.FACTS_UNAVAILABLE
        )
    certified = await uow.signals.get_instrument_rules(
        domain.venue_id,
        domain.exchange_instrument_id,
    )
    if (
        certified is None
        or certified.valid_until_ms <= request.assessed_at_ms
    ):
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.FACTS_UNAVAILABLE
        )
    if (
        account.venue_id != domain.venue_id
        or account.account_id != domain.account_id
        or account.exchange_instrument_id != domain.exchange_instrument_id
        or rules.exchange_instrument_id != domain.exchange_instrument_id
        or rules.maintenance_margin_brackets_digest
        != certified.maintenance_margin_brackets_digest
        or rules.notional_coefficient != certified.notional_coefficient
        or rules.notional_coefficient_certified
        != certified.notional_coefficient_certified
    ):
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.FACTS_CONTRADICTORY
        )
    target_positions = tuple(
        position
        for position in account.account_positions
        if position.exchange_instrument_id == domain.exchange_instrument_id
    )
    actual_side = next(
        (
            position
            for position in target_positions
            if position.position_side == domain.position_side
        ),
        None,
    )
    if (
        actual_side is None
        or actual_side.quantity != aggregate.position_qty
        or actual_side.average_entry_price != aggregate.average_fill_price
    ):
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.FACTS_UNAVAILABLE
        )
    assert aggregate.average_fill_price is not None
    evidence = evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=account,
            maintenance_margin_brackets=rules.maintenance_margin_brackets,
            maintenance_margin_brackets_digest=(
                rules.maintenance_margin_brackets_digest
            ),
            notional_coefficient=rules.notional_coefficient,
            notional_coefficient_certified=(
                rules.notional_coefficient_certified
            ),
            evaluated_side=domain.position_side,
            reference_entry_price=aggregate.average_fill_price,
            initial_stop_price=aggregate.ticket.initial_stop_price,
            post_stop_stress_multiple=(
                aggregate.ticket.post_stop_stress_multiple
            ),
            projected_instrument_positions=tuple(
                StressPosition(
                    position_side=position.position_side,
                    quantity=position.quantity,
                    average_entry_price=position.average_entry_price,
                )
                for position in target_positions
            ),
        )
    )
    if evidence.proof.status is CrossMarginStressStatus.FACTS_CONTRADICTORY:
        return PostFillStressReconcileResult(
            status=PostFillStressReconcileStatus.FACTS_CONTRADICTORY
        )
    event_status: Literal["passed", "failed"]
    if evidence.proof.status is CrossMarginStressStatus.PASSED:
        result_status = PostFillStressReconcileStatus.PASSED
        event_status = "passed"
    else:
        result_status = PostFillStressReconcileStatus.FAILED
        event_status = "failed"
    assert aggregate.initial_stop_exchange_order_id is not None
    event = PostFillStressAssessed(
        event_id=_event_id(aggregate),
        ticket_id=request.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=request.assessed_at_ms,
        status=event_status,
        evidence=evidence,
        owner_policy_id=aggregate.ticket.owner_policy_id,
        owner_policy_version=aggregate.ticket.owner_policy_version,
        filled_qty=aggregate.position_qty,
        average_fill_price=aggregate.average_fill_price,
        initial_stop_price=aggregate.ticket.initial_stop_price,
        initial_stop_exchange_order_id=(
            aggregate.initial_stop_exchange_order_id
        ),
    )
    reduction = reduce_event(aggregate, event)
    await uow.commit_reduction(
        event=event,
        reduction=reduction,
        expected_version=aggregate.version,
    )
    await _resolve_post_fill_retry_incidents(
        uow,
        ticket_id=request.ticket_id,
        resolved_at_ms=request.assessed_at_ms,
    )
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=f"post-fill-stress:{request.ticket_id}",
            owner_status=MonitorOwnerStatus.PROCESSING,
            summary=f"Post-fill stress assessed: {result_status.value}",
            intervention="none",
            ticket_id=request.ticket_id,
            incident_id=None,
            updated_at_ms=request.assessed_at_ms,
        )
    )
    return PostFillStressReconcileResult(status=result_status)


async def record_post_fill_stress_retry(
    uow: KernelUnitOfWork,
    *,
    ticket_id: str,
    status: PostFillStressReconcileStatus,
    now_ms: int,
    due_at_ms: int,
) -> None:
    if status not in {
        PostFillStressReconcileStatus.FACTS_UNAVAILABLE,
        PostFillStressReconcileStatus.FACTS_CONTRADICTORY,
    }:
        raise ValueError("post-fill retry requires an unavailable fact status")
    aggregate = await uow.aggregates.get_for_update(ticket_id)
    if (
        aggregate is None
        or aggregate.status is not AggregateStatus.POST_FILL_RISK_PENDING
    ):
        return
    incident_kind = (
        "post_fill_risk_facts_unavailable"
        if status is PostFillStressReconcileStatus.FACTS_UNAVAILABLE
        else "post_fill_risk_facts_contradictory"
    )
    opposite_kind = (
        "post_fill_risk_facts_contradictory"
        if incident_kind == "post_fill_risk_facts_unavailable"
        else "post_fill_risk_facts_unavailable"
    )
    opposite = await uow.incidents.get_open_for_ticket_kind(
        ticket_id,
        opposite_kind,
    )
    if opposite is not None:
        await uow.incidents.resolve(
            opposite.incident_id,
            resolved_at_ms=now_ms,
        )
    existing = await uow.incidents.get_open_for_ticket_kind(
        ticket_id,
        incident_kind,
    )
    incident_id = f"incident:{ticket_id}:{incident_kind}"
    if existing is None:
        domain = aggregate.identity.netting_domain
        await uow.incidents.add(
            RuntimeIncidentRecord(
                incident_id=incident_id,
                ticket_id=ticket_id,
                incident_kind=incident_kind,
                status="open",
                first_blocker=incident_kind,
                entry_block_scope=EntryBlockScope.ACCOUNT_CAPACITY,
                entry_block_key=canonical_entry_block_key(
                    EntryBlockScope.ACCOUNT_CAPACITY,
                    venue_id=domain.venue_id,
                    account_id=domain.account_id,
                    exchange_instrument_id=domain.exchange_instrument_id,
                ),
                details={"aggregate_version": aggregate.version},
                opened_at_ms=now_ms,
            )
        )
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=f"post-fill-stress:{ticket_id}",
            owner_status=(
                MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE
                if status is PostFillStressReconcileStatus.FACTS_UNAVAILABLE
                else MonitorOwnerStatus.NEEDS_INTERVENTION
            ),
            summary=f"Post-fill stress {status.value}",
            intervention=(
                "automatic retry"
                if status is PostFillStressReconcileStatus.FACTS_UNAVAILABLE
                else "Owner review required"
            ),
            ticket_id=ticket_id,
            incident_id=existing.incident_id if existing is not None else incident_id,
            updated_at_ms=now_ms,
        )
    )
    await uow.aggregates.schedule_next_check(
        ticket_id,
        work_kind="reconciliation",
        due_at_ms=due_at_ms,
    )


async def _resolve_post_fill_retry_incidents(
    uow: KernelUnitOfWork,
    *,
    ticket_id: str,
    resolved_at_ms: int,
) -> None:
    for incident_kind in (
        "post_fill_risk_facts_unavailable",
        "post_fill_risk_facts_contradictory",
    ):
        incident = await uow.incidents.get_open_for_ticket_kind(
            ticket_id,
            incident_kind,
        )
        if incident is not None:
            await uow.incidents.resolve(
                incident.incident_id,
                resolved_at_ms=resolved_at_ms,
            )


def _required_average_entry_price(snapshot: PositionSnapshot) -> Decimal:
    price = snapshot.average_entry_price
    if price is None:
        raise RuntimeError("open position snapshot lacks average entry price")
    return price


def _venue_liquidation_observation_code(
    snapshot: PositionSnapshot,
) -> str:
    status = snapshot.venue_reported_liquidation_observation_status
    if status == "invalid":
        return "venue_liquidation_observation_invalid"
    if status == "missing":
        return "venue_liquidation_observation_unavailable"
    price = snapshot.venue_reported_liquidation_price
    if price == 0:
        return "venue_liquidation_observation_zero"
    average_entry_price = snapshot.average_entry_price
    if (
        price is not None
        and average_entry_price is not None
        and (
            (
                snapshot.netting_domain.position_side == "long"
                and price >= average_entry_price
            )
            or (
                snapshot.netting_domain.position_side == "short"
                and price <= average_entry_price
            )
        )
    ):
        return "venue_liquidation_observation_not_side_directional"
    return "venue_liquidation_observation_observed"


async def request_exit(
    uow: KernelUnitOfWork,
    request: ExitTicketRequest,
) -> ExitTicketResult:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("Ticket aggregate does not exist")
    event = ExitRequested(
        event_id=_event_id(aggregate),
        ticket_id=request.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=request.requested_at_ms,
        reason=request.reason,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    return ExitTicketResult(status=ExitTicketStatus.REQUESTED)


def _event_id(aggregate) -> str:
    return (
        f"event:{aggregate.identity.ticket_id}:"
        f"{aggregate.last_event_sequence + 1}"
    )


def _is_kernel_owned_order(venue_client_order_id: str | None) -> bool:
    return str(venue_client_order_id or "").startswith("brc-")


def _has_cancel_attempt(commands, exchange_order_id: str) -> bool:
    non_repeatable = {
        ExchangeCommandStatus.PREPARED,
        ExchangeCommandStatus.CLAIMED,
        ExchangeCommandStatus.ACCEPTED,
        ExchangeCommandStatus.OUTCOME_UNKNOWN,
    }
    return any(
        command.status in non_repeatable
        and isinstance(command.payload, CancelCommandPayload)
        and command.payload.exchange_order_id == exchange_order_id
        for command in commands
    )


def _next_known_cleanup_order_id(aggregate) -> str | None:
    identities: list[str] = []
    for identity in (
        aggregate.tp1_exchange_order_id,
        aggregate.active_stop_exchange_order_id,
        aggregate.initial_stop_exchange_order_id,
    ):
        if identity is not None and identity not in identities:
            identities.append(identity)
    return None if not identities else identities[0]
