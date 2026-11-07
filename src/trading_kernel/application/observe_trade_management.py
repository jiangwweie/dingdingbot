"""Apply a scoped, validated external-order observation through the existing UoW.

The runtime event collector is not wired yet. No network I/O or venue mutation
is performed by this use case, including on repeated evidence.
"""

from __future__ import annotations

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.domain.commands import ExchangeCommandStatus
from src.trading_kernel.domain.events import (
    ManagementReviewRequired,
    ManualTakeoverConfirmed,
)
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import (
    ManagementMode,
    OrderEvidence,
    TradeManagement,
    transition_management,
)


async def observe_trade_management(
    uow: KernelUnitOfWork, *, ticket_id: str, evidence: OrderEvidence, now_ms: int
) -> TradeManagement:
    aggregate = await uow.aggregates.get_for_update(ticket_id)
    if aggregate is None:
        raise ValueError("management Ticket missing")
    domain = aggregate.identity.netting_domain
    expected = (
        domain.venue_id,
        domain.account_id,
        domain.exchange_instrument_id,
        domain.position_side,
    )
    if evidence.terms.identity[:4] != expected:
        raise ValueError("management evidence scope differs")
    if not aggregate.ticket.created_at_ms <= evidence.exchange_event_at_ms <= now_ms:
        raise ValueError("management evidence outside Ticket time window")
    if not evidence.exchange_event_at_ms <= evidence.received_at_ms <= now_ms:
        raise ValueError("management evidence clock differs")
    state = TradeManagement(
        ticket_id=ticket_id,
        mode=aggregate.management_mode,
        revision=aggregate.management_revision,
        reason=aggregate.management_reason,
        takeover_evidence_id=aggregate.management_evidence_id
        if aggregate.management_mode is ManagementMode.MANUAL
        else None,
        takeover_detected_at_ms=aggregate.manual_takeover_at_ms,
    )
    await uow.management.save_evidence(ticket_id,evidence)
    if state.mode is ManagementMode.MANUAL:
        return state
    commands = await uow.exchange_commands.list_for_ticket(ticket_id)
    # Never trust a caller's negative flag when the durable ledger has unknown
    # or in-flight work. Own orders are bound to scoped durable command results;
    # an ID prefix alone cannot establish automatic ownership.
    pending = any(
        c.status
        in {ExchangeCommandStatus.CLAIMED, ExchangeCommandStatus.OUTCOME_UNKNOWN}
        for c in commands
    )
    verified = OrderEvidence.model_validate(
        {
            **evidence.model_dump(),
            "known_command_outcome_pending": evidence.known_command_outcome_pending
            or pending,
        }
    )
    from src.trading_kernel.application.management_intents import system_intents_for
    intents=system_intents_for(verified,await uow.management.command_rows(ticket_id))
    after = transition_management(
        state,
        verified,
        system_intents=intents,
        initial_protection_confirmed=aggregate.active_stop_exchange_order_id is not None and aggregate.post_fill_stress_status=="passed",
    )
    if after == state:
        return state
    event_type: type[ManualTakeoverConfirmed | ManagementReviewRequired] = (
        ManualTakeoverConfirmed
        if after.mode is ManagementMode.MANUAL
        else ManagementReviewRequired
    )
    event = event_type(
        event_id=f"management:{ticket_id}:{after.revision}",
        ticket_id=ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=after.takeover_detected_at_ms or now_ms,
        evidence_id=evidence.evidence_id,
        reason=after.reason or "management_unresolved",
        observation=verified,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    for command in commands:
        if after.mode is ManagementMode.MANUAL and command.status is ExchangeCommandStatus.PREPARED:
            await uow.exchange_commands.mark_prepared_superseded(
                command_id=command.command_id,
                observed_at_ms=now_ms,
                reason=f"trade_management:{after.mode.value}",
            )
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=f"management:{ticket_id}",
            owner_status=MonitorOwnerStatus.RUNNING
            if after.mode is ManagementMode.MANUAL
            else MonitorOwnerStatus.NEEDS_INTERVENTION,
            summary="人工管理；现存交易所订单保留，程序不再管理退出"
            if after.mode is ManagementMode.MANUAL
            else "订单归属待核实；自动处置已暂停",
            intervention="none"
            if after.mode is ManagementMode.MANUAL
            else "verify_external_order_history",
            ticket_id=ticket_id,
            updated_at_ms=now_ms,
        )
    )
    return after
