"""Deterministic Ticket causality assembly from bounded PostgreSQL facts."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import ValidationError

from src.trading_kernel.application.owner_console.exit_attribution import (
    canonical_exit_attribution,
)
from src.trading_kernel.application.owner_console.models import (
    CausalityExitReason,
    ChartAnnotation,
    EvidenceRef,
    LifecycleStageKey,
    LifecycleStageView,
    RawExchangeCommandView,
    RawIncidentView,
    RawTradeEventView,
    TradeCausalityDetail,
    TradeCausalityEventFacts,
    TradeCausalityFacts,
    TradePricePlanView,
)
from src.trading_kernel.application.owner_console.trades import (
    TradeFactsContradiction,
    aggregate_stage,
    build_trade_item,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import (
    PERSISTED_TRADE_EVENT_MODELS,
    TicketIssued,
)
from src.trading_kernel.domain.strategy_registry import (
    registered_strategy_contracts,
    strategy_contract_for,
)
from src.trading_kernel.domain.ticket import TicketStatus, TradeTicket


class ContradictoryFacts(TradeFactsContradiction):
    """Exact Ticket causality identities or bounded histories disagree."""


_STAGE_ORDER: tuple[LifecycleStageKey, ...] = (
    "signal",
    "admission",
    "entry",
    "protection",
    "tp_runner",
    "exit",
    "reconciliation",
    "review",
)
_STAGE_LABELS: dict[LifecycleStageKey, str] = {
    "signal": "Signal",
    "admission": "Admission",
    "entry": "Entry",
    "protection": "Protection",
    "tp_runner": "TP / Runner",
    "exit": "Exit",
    "reconciliation": "Reconciliation / Settlement",
    "review": "Review",
}

_ENTRY_EVENTS = {
    "TicketIssued",
    "LeverageConfirmed",
    "LeverageRejected",
    "LeverageOutcomeUnknown",
    "EntryAccepted",
    "EntryRejected",
    "EntryOutcomeUnknown",
    "EntryAbsenceConfirmed",
    "EntryFilled",
    "EntryPartiallyFilled",
    "EntryRemainderCancelConfirmed",
    "EntryRemainderCancelRejected",
    "EntryRemainderCancelOutcomeUnknown",
    "EntryVacuumSuperseded",
    "EntryVacuumCancelRequested",
    "EntryVacuumCancelConfirmed",
    "EntryVacuumCancelRejected",
    "EntryVacuumCancelOutcomeUnknown",
    "EntryVacuumOrderAbsenceConfirmed",
    "EntryVacuumAbsenceConfirmed",
    "VacuumPartialRetained",
    "VacuumPartialFlattenRequired",
}
_PROTECTION_EVENTS = {
    "InitialStopConfirmed",
    "PostFillStressAssessed",
    "InitialStopRejected",
    "InitialStopOutcomeUnknown",
    "InitialStopAbsenceConfirmed",
}
_TP_RUNNER_EVENTS = {
    "TakeProfitConfirmed",
    "TakeProfitRejected",
    "TakeProfitOutcomeUnknown",
    "TakeProfitAbsenceConfirmed",
    "TakeProfitFilled",
    "RunnerStopRequested",
    "ProtectionReplacementConfirmed",
    "ProtectionReplacementRejected",
    "ProtectionReplacementOutcomeUnknown",
    "ProtectionReplacementAbsenceConfirmed",
}
_EXIT_EVENTS = {
    "ExitRequested",
    "ExitAccepted",
    "ExitRejected",
    "ExitOutcomeUnknown",
    "ExitAbsenceConfirmed",
    "ControlledFlattenAccepted",
    "ControlledFlattenRejected",
    "ControlledFlattenOutcomeUnknown",
    "ControlledFlattenAbsenceConfirmed",
}
_RECONCILIATION_EVENTS = {
    "PositionFlatConfirmed",
    "ExternalFlatDetected",
    "OwnedOrphanOrderDetected",
    "OwnedOrderAbsenceConfirmed",
    "UnownedOrderDetected",
    "ProtectionCancelConfirmed",
    "ProtectionCancelRejected",
    "ProtectionCancelOutcomeUnknown",
    "ProtectionCancelAbsenceConfirmed",
    "OwnedOrphanCancelConfirmed",
    "CancelOrderRejected",
    "CancelOrderOutcomeUnknown",
    "CancelOrderAbsenceConfirmed",
    "CancelOrderStillOpenConfirmed",
    "ReconciliationMatched",
    "BudgetSettled",
}
_REVIEW_EVENTS = {"ReviewRecorded", "ReviewRevised"}

EVENT_STAGE: dict[str, LifecycleStageKey] = {
    **{name: "entry" for name in _ENTRY_EVENTS},
    **{name: "protection" for name in _PROTECTION_EVENTS},
    **{name: "tp_runner" for name in _TP_RUNNER_EVENTS},
    **{name: "exit" for name in _EXIT_EVENTS},
    **{name: "reconciliation" for name in _RECONCILIATION_EVENTS},
    **{name: "review" for name in _REVIEW_EVENTS},
}
_PERSISTED_EVENT_TYPES = {
    model.__name__ for model in PERSISTED_TRADE_EVENT_MODELS
}
if set(EVENT_STAGE) != _PERSISTED_EVENT_TYPES:
    missing = sorted(_PERSISTED_EVENT_TYPES.difference(EVENT_STAGE))
    extra = sorted(set(EVENT_STAGE).difference(_PERSISTED_EVENT_TYPES))
    raise RuntimeError(
        f"Trade Event stage mapping mismatch; missing={missing}, extra={extra}"
    )

_TERMINAL_REJECTION_STATUSES = {
    TicketStatus.LEVERAGE_REJECTED.value,
    TicketStatus.ENTRY_REJECTED.value,
    TicketStatus.ENTRY_RECONCILED_ABSENT.value,
}
_EXIT_ATTRIBUTION_COMMAND_KINDS = {
    ExchangeCommandKind.INITIAL_STOP.value,
    ExchangeCommandKind.TAKE_PROFIT.value,
    ExchangeCommandKind.EXIT.value,
    ExchangeCommandKind.REPLACE_PROTECTION.value,
    ExchangeCommandKind.CONTROLLED_FLATTEN.value,
}
_ACCEPTED_ATTRIBUTION_COMMAND_STATUSES = {
    ExchangeCommandStatus.ACCEPTED.value,
    ExchangeCommandStatus.RECONCILED_ACCEPTED.value,
}


def build_trade_causality(facts: TradeCausalityFacts) -> TradeCausalityDetail:
    """Build one exact, evidence-linked causality workbench."""

    try:
        current_stage = aggregate_stage(facts.aggregate.aggregate_status)
        trade = build_trade_item(facts.trade)
    except TradeFactsContradiction as exc:
        raise ContradictoryFacts(str(exc)) from exc
    _validate_identities(facts)
    ordered_events = _ordered_events(facts)
    raw_events = _raw_events(ordered_events, fallback=current_stage)
    raw_commands = _raw_commands(facts)
    raw_incidents = _raw_incidents(facts)
    exit_reason = _exit_reason(ordered_events)
    annotations = _annotations(facts, ordered_events)
    stages = _stages(
        facts,
        current_stage=current_stage,
        raw_events=raw_events,
    )
    signal_evidence = (
        EvidenceRef(
            kind="signal",
            identity=facts.signal.signal_event_id,
            occurred_at_ms=facts.signal.occurred_at_ms,
        ),
    )
    order_evidence = tuple(
        item.evidence[0] for item in raw_commands
    )
    incident_evidence = tuple(
        item.evidence[0] for item in raw_incidents
    )
    event_evidence = tuple(item.evidence[0] for item in raw_events)
    settlement_evidence = tuple(
        item.evidence[0]
        for item in raw_events
        if item.event_type in {"BudgetSettled", "ReconciliationMatched"}
    )
    review_evidence = _review_evidence(facts, raw_events)
    evidence = _deduplicate_evidence(
        (
            *trade.evidence,
            *signal_evidence,
            EvidenceRef(
                kind="aggregate",
                identity=facts.aggregate.ticket_id,
                occurred_at_ms=facts.aggregate.updated_at_ms,
            ),
            EvidenceRef(
                kind="admission",
                identity=facts.admission.admission_decision_id,
                occurred_at_ms=facts.admission.decided_at_ms,
            ),
            *order_evidence,
            *incident_evidence,
            *event_evidence,
            *review_evidence,
        )
    )
    current_view = stages[_STAGE_ORDER.index(current_stage)]
    return TradeCausalityDetail(
        trade=trade,
        price_plan=_price_plan(facts, ordered_events),
        current_stage=current_stage,
        current_stage_summary=current_view.summary,
        stages=stages,
        annotations=annotations,
        exit_reason=exit_reason,
        raw_events=raw_events,
        raw_commands=raw_commands,
        raw_incidents=raw_incidents,
        signal_evidence=signal_evidence,
        order_evidence=order_evidence,
        incident_evidence=incident_evidence,
        event_evidence=event_evidence,
        settlement_evidence=settlement_evidence,
        review_evidence=review_evidence,
        evidence=evidence,
    )


def _price_plan(
    facts: TradeCausalityFacts,
    events: tuple[TradeCausalityEventFacts, ...],
) -> TradePricePlanView:
    """Project one frozen plan without asking the browser to infer trade facts."""

    entry_price = facts.aggregate.average_fill_price
    entry_events = [event for event in events if event.event_type == "EntryFilled"]
    if len(entry_events) > 1:
        raise ContradictoryFacts("Ticket has multiple EntryFilled events")
    if entry_events:
        event_price = _decimal_string(
            entry_events[0].payload.get("average_fill_price"),
            context="EntryFilled.average_fill_price",
        )
        if entry_price is not None and entry_price != event_price:
            raise ContradictoryFacts("Aggregate and EntryFilled price disagree")
        entry_price = event_price

    basis = entry_price or facts.ticket.entry_reference_price
    tp1_price = (
        facts.ticket.take_profit_prices[0]
        if facts.ticket.take_profit_prices
        else None
    )
    tp1_target_quantity = (
        facts.ticket.take_profit_quantities[0]
        if facts.ticket.take_profit_quantities
        else None
    )
    return TradePricePlanView(
        strategy_timeframe=_strategy_timeframe(facts),
        entry_reference_price=facts.ticket.entry_reference_price,
        entry_limit_price=facts.ticket.entry_limit_price,
        actual_entry_price=entry_price,
        initial_stop_price=facts.ticket.initial_stop_price,
        active_stop_price=facts.aggregate.active_stop_price,
        tp1_price=tp1_price,
        ticket_quantity=facts.ticket.quantity,
        tp1_target_quantity=tp1_target_quantity,
        tp1_filled_quantity=facts.aggregate.tp1_filled_qty,
        initial_stop_distance_percent=_signed_distance_percent(
            basis,
            facts.ticket.initial_stop_price,
            side=facts.ticket.identity.netting_domain.position_side,
            target="stop",
        ),
        tp1_distance_percent=(
            None
            if tp1_price is None
            else _signed_distance_percent(
                basis,
                tp1_price,
                side=facts.ticket.identity.netting_domain.position_side,
                target="take_profit",
            )
        ),
        tp1_reward_r=(
            None
            if tp1_price is None
            else _reward_r(basis, facts.ticket.initial_stop_price, tp1_price)
        ),
    )


def _strategy_timeframe(
    facts: TradeCausalityFacts,
) -> Literal["15m", "1h"] | None:
    """Resolve exact Event semantics, then a single-timeframe StrategyGroup history."""

    try:
        return strategy_contract_for(
            facts.ticket.identity.runtime.event_spec_id
        ).timeframe
    except ValueError:
        candidates = {
            contract.timeframe
            for contract in registered_strategy_contracts()
            if contract.strategy_group_id
            == facts.ticket.identity.runtime.strategy_group_id
        }
        return next(iter(candidates)) if len(candidates) == 1 else None


def _signed_distance_percent(
    basis: Decimal,
    price: Decimal,
    *,
    side: Literal["long", "short"],
    target: Literal["stop", "take_profit"],
) -> Decimal | None:
    if basis <= 0:
        return None
    difference = price - basis if side == "long" else basis - price
    if target == "stop":
        difference = -abs(difference)
    else:
        difference = abs(difference)
    return difference / basis * Decimal(100)


def _reward_r(entry: Decimal, stop: Decimal, target: Decimal) -> Decimal | None:
    risk_distance = abs(entry - stop)
    if risk_distance == 0:
        return None
    return abs(target - entry) / risk_distance


def _validate_identities(facts: TradeCausalityFacts) -> None:
    ticket = facts.ticket
    identity = ticket.identity
    runtime = identity.runtime
    domain = identity.netting_domain
    aggregate = facts.aggregate
    signal = facts.signal
    admission = facts.admission
    trade = facts.trade
    if aggregate.ticket_id != identity.ticket_id:
        raise ContradictoryFacts("Ticket and Aggregate identity mismatch")
    if (
        trade.ticket_id != identity.ticket_id
        or trade.strategy_group_id != runtime.strategy_group_id
        or trade.event_spec_id != runtime.event_spec_id
        or trade.exchange_instrument_id != domain.exchange_instrument_id
        or trade.position_side != domain.position_side
        or trade.aggregate_status != aggregate.aggregate_status
        or trade.issued_at_ms != ticket.created_at_ms
        or trade.aggregate_review_id != aggregate.review_id
    ):
        raise ContradictoryFacts("Trade and Ticket causality facts disagree")
    ticket_signal_pairs = (
        (identity.signal_event_id, signal.signal_event_id),
        (identity.exposure_episode_id, signal.exposure_episode_id),
        (runtime.strategy_group_id, signal.strategy_group_id),
        (runtime.strategy_version_id, signal.strategy_version_id),
        (runtime.event_spec_id, signal.event_spec_id),
        (ticket.universe_version_id, signal.universe_version_id),
        (ticket.universe_semantic_digest, signal.universe_semantic_digest),
        (ticket.runtime_scope_id, signal.runtime_scope_id),
        (ticket.runtime_scope_version, signal.runtime_scope_version),
        (domain.exchange_instrument_id, signal.exchange_instrument_id),
        (domain.position_side, signal.position_side),
    )
    if any(left != right for left, right in ticket_signal_pairs):
        raise ContradictoryFacts("Ticket and Signal identity mismatch")
    ticket_admission_pairs = (
        (identity.ticket_id, admission.ticket_id),
        (identity.signal_event_id, admission.signal_event_id),
        (identity.exposure_episode_id, admission.exposure_episode_id),
        (runtime.strategy_group_id, admission.strategy_group_id),
        (runtime.strategy_version_id, admission.strategy_version_id),
        (runtime.event_spec_id, admission.event_spec_id),
        (ticket.universe_version_id, admission.universe_version_id),
        (ticket.universe_semantic_digest, admission.universe_semantic_digest),
        (runtime.runtime_profile_id, admission.runtime_profile_id),
        (ticket.runtime_scope_id, admission.runtime_scope_id),
        (ticket.runtime_scope_version, admission.runtime_scope_version),
        (ticket.owner_policy_id, admission.owner_policy_id),
        (ticket.owner_policy_version, admission.owner_policy_version),
        (ticket.capacity_claim_id, admission.capacity_claim_id),
        (domain.venue_id, admission.venue_id),
        (domain.account_id, admission.account_id),
        (domain.exchange_instrument_id, admission.exchange_instrument_id),
        (domain.position_side, admission.position_side),
    )
    if (
        admission.decision_status != "admitted"
        or any(left != right for left, right in ticket_admission_pairs)
    ):
        raise ContradictoryFacts("Ticket and AdmissionDecision identity mismatch")
    review = facts.review
    if review is None:
        if aggregate.review_id is not None and trade.review_id is not None:
            raise ContradictoryFacts("current Review row is missing")
        return
    if (
        aggregate.review_id != review.review_id
        or review.ticket_id != identity.ticket_id
        or trade.review_id != review.review_id
        or trade.review_ticket_id != review.ticket_id
        or trade.review_revision != review.revision
        or trade.review_created_at_ms != review.created_at_ms
        or trade.review_metrics != review.metrics
    ):
        raise ContradictoryFacts("current Review identity mismatch")


def _ordered_events(
    facts: TradeCausalityFacts,
) -> tuple[TradeCausalityEventFacts, ...]:
    ordered = tuple(sorted(facts.events, key=lambda item: item.sequence))
    sequences = tuple(item.sequence for item in ordered)
    expected = tuple(range(1, facts.aggregate.last_event_sequence + 1))
    if sequences != expected:
        raise ContradictoryFacts("Event sequence disagrees with Aggregate")
    for event in ordered:
        if event.ticket_id != facts.ticket.identity.ticket_id:
            raise ContradictoryFacts("Event Ticket identity mismatch")
        _validate_event_payload(event, ticket=facts.ticket)
    return ordered


def _validate_event_payload(
    event: TradeCausalityEventFacts,
    *,
    ticket: TradeTicket,
) -> None:
    payload = event.payload
    if (
        payload.get("event_id") != event.event_id
        or payload.get("sequence") != event.sequence
        or payload.get("occurred_at_ms") != event.occurred_at_ms
    ):
        raise ContradictoryFacts("Event payload identity mismatch")
    if event.event_type == "TicketIssued":
        try:
            issued = TicketIssued.model_validate(payload)
        except ValidationError as exc:
            raise ContradictoryFacts("TicketIssued snapshot is invalid") from exc
        if issued.ticket.model_dump(mode="python", exclude={"status"}) != (
            ticket.model_dump(mode="python", exclude={"status"})
        ):
            raise ContradictoryFacts("TicketIssued snapshot disagrees with Ticket")
        if issued.ticket.identity.ticket_id != ticket.identity.ticket_id:
            raise ContradictoryFacts("Event payload identity mismatch")
        return
    payload_ticket_id = payload.get("ticket_id")
    if payload_ticket_id != ticket.identity.ticket_id:
        raise ContradictoryFacts("Event payload identity mismatch")


def _raw_events(
    events: tuple[TradeCausalityEventFacts, ...],
    *,
    fallback: LifecycleStageKey,
) -> tuple[RawTradeEventView, ...]:
    rows: list[RawTradeEventView] = []
    for event in events:
        mapped_stage = EVENT_STAGE.get(event.event_type)
        evidence = (
            EvidenceRef(
                kind="event",
                identity=event.event_id,
                occurred_at_ms=event.occurred_at_ms,
            ),
        )
        rows.append(
            RawTradeEventView(
                event_id=event.event_id,
                ticket_id=event.ticket_id,
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at_ms=event.occurred_at_ms,
                stage=fallback if mapped_stage is None else mapped_stage,
                classification=(
                    "unmapped" if mapped_stage is None else "mapped"
                ),
                evidence=evidence,
            )
        )
    return tuple(rows)


def _raw_commands(
    facts: TradeCausalityFacts,
) -> tuple[RawExchangeCommandView, ...]:
    ordered = tuple(
        sorted(facts.commands, key=lambda item: (item.created_at_ms, item.command_id))
    )
    if ordered != facts.commands:
        raise ContradictoryFacts("Exchange Commands are not in exact order")
    if len({item.command_id for item in ordered}) != len(ordered):
        raise ContradictoryFacts("duplicate Exchange Command identity")
    rows: list[RawExchangeCommandView] = []
    for command in ordered:
        if command.ticket_id != facts.ticket.identity.ticket_id:
            raise ContradictoryFacts("Exchange Command Ticket identity mismatch")
        evidence = (
            EvidenceRef(
                kind="command",
                identity=command.command_id,
                occurred_at_ms=command.created_at_ms,
            ),
        )
        rows.append(
            RawExchangeCommandView(
                command_id=command.command_id,
                ticket_id=command.ticket_id,
                command_kind=command.command_kind,
                generation=command.generation,
                status=command.status,
                request_payload=command.request_payload,
                result_payload=command.result_payload,
                created_at_ms=command.created_at_ms,
                completed_at_ms=command.completed_at_ms,
                evidence=evidence,
            )
        )
    return tuple(rows)


def _raw_incidents(
    facts: TradeCausalityFacts,
) -> tuple[RawIncidentView, ...]:
    ordered = tuple(
        sorted(facts.incidents, key=lambda item: (item.opened_at_ms, item.incident_id))
    )
    if ordered != facts.incidents:
        raise ContradictoryFacts("Incidents are not in exact order")
    if len({item.incident_id for item in ordered}) != len(ordered):
        raise ContradictoryFacts("duplicate Incident identity")
    rows: list[RawIncidentView] = []
    for incident in ordered:
        if incident.ticket_id != facts.ticket.identity.ticket_id:
            raise ContradictoryFacts("Incident Ticket identity mismatch")
        evidence = (
            EvidenceRef(
                kind="incident",
                identity=incident.incident_id,
                occurred_at_ms=incident.opened_at_ms,
            ),
        )
        rows.append(
            RawIncidentView(
                incident_id=incident.incident_id,
                ticket_id=incident.ticket_id,
                incident_kind=incident.incident_kind,
                status=incident.status,
                first_blocker=incident.first_blocker,
                details=incident.details,
                opened_at_ms=incident.opened_at_ms,
                resolved_at_ms=incident.resolved_at_ms,
                evidence=evidence,
            )
        )
    return tuple(rows)


def _exit_reason(
    events: tuple[TradeCausalityEventFacts, ...],
) -> CausalityExitReason | None:
    event = next(
        (item for item in events if item.event_type == "ExitRequested"),
        None,
    )
    if event is None:
        return None
    reason = event.payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ContradictoryFacts("ExitRequested reason is missing")
    attribution = canonical_exit_attribution(reason)
    return CausalityExitReason(
        code=attribution.code,
        label=attribution.label,
        evidence=(
            EvidenceRef(
                kind="event",
                identity=event.event_id,
                occurred_at_ms=event.occurred_at_ms,
            ),
        ),
    )


def _annotations(
    facts: TradeCausalityFacts,
    events: tuple[TradeCausalityEventFacts, ...],
) -> tuple[ChartAnnotation, ...]:
    ticket_evidence = EvidenceRef(
        kind="ticket",
        identity=facts.ticket.identity.ticket_id,
        occurred_at_ms=facts.ticket.created_at_ms,
    )
    signal_evidence = EvidenceRef(
        kind="signal",
        identity=facts.signal.signal_event_id,
        occurred_at_ms=facts.signal.occurred_at_ms,
    )
    annotations = [
        ChartAnnotation(
            kind="signal",
            occurred_at_ms=facts.signal.occurred_at_ms,
            price=facts.ticket.entry_reference_price,
            label="Signal Reference",
            evidence=(signal_evidence, ticket_evidence),
        ),
        ChartAnnotation(
            kind="stop",
            occurred_at_ms=facts.signal.occurred_at_ms,
            price=facts.ticket.initial_stop_price,
            label="Frozen Initial Stop Plan",
            evidence=(signal_evidence, ticket_evidence),
        ),
    ]
    for event in events:
        event_evidence = EvidenceRef(
            kind="event",
            identity=event.event_id,
            occurred_at_ms=event.occurred_at_ms,
        )
        if event.event_type == "EntryFilled":
            annotations.append(
                ChartAnnotation(
                    kind="entry",
                    occurred_at_ms=event.occurred_at_ms,
                    price=_decimal_string(
                        event.payload.get("average_fill_price"),
                        context="EntryFilled.average_fill_price",
                    ),
                    label="ENTRY Fill",
                    evidence=(event_evidence,),
                )
            )
        elif event.event_type == "InitialStopConfirmed":
            annotations.append(
                ChartAnnotation(
                    kind="stop",
                    occurred_at_ms=event.occurred_at_ms,
                    price=facts.ticket.initial_stop_price,
                    label="Initial Stop Confirmed",
                    evidence=(event_evidence, ticket_evidence),
                )
            )
        elif event.event_type == "TakeProfitFilled":
            annotations.append(
                ChartAnnotation(
                    kind="take_profit",
                    occurred_at_ms=event.occurred_at_ms,
                    price=_decimal_string(
                        event.payload.get("average_fill_price"),
                        context="TakeProfitFilled.average_fill_price",
                    ),
                    label="Take Profit Fill",
                    evidence=(event_evidence,),
                )
            )
        elif event.event_type == "ProtectionReplacementConfirmed":
            annotations.append(
                ChartAnnotation(
                    kind="stop",
                    occurred_at_ms=event.occurred_at_ms,
                    price=_decimal_string(
                        event.payload.get("stop_price"),
                        context="ProtectionReplacementConfirmed.stop_price",
                    ),
                    label="Protection Replacement",
                    evidence=(event_evidence,),
                )
            )
    annotations.extend(_review_exit_annotations(facts))
    return tuple(
        sorted(
            annotations,
            key=lambda item: (item.occurred_at_ms, _annotation_order(item.kind)),
        )
    )


def _review_exit_annotations(
    facts: TradeCausalityFacts,
) -> tuple[ChartAnnotation, ...]:
    review = facts.review
    if review is None:
        return ()
    raw_attribution = review.metrics.get("order_attribution")
    if raw_attribution is None:
        return ()
    if not isinstance(raw_attribution, list):
        raise ContradictoryFacts("current Review order attribution is malformed")
    commands = {command.command_id: command for command in facts.commands}
    review_evidence = EvidenceRef(
        kind="review",
        identity=review.review_id,
        occurred_at_ms=review.created_at_ms,
    )
    annotations: list[ChartAnnotation] = []
    for raw_row in raw_attribution:
        if not isinstance(raw_row, dict):
            raise ContradictoryFacts("current Review order attribution is malformed")
        role = raw_row.get("role")
        if role not in {"entry", "exit"}:
            raise ContradictoryFacts("current Review order attribution role is invalid")
        if role != "exit":
            continue
        command_id = raw_row.get("command_id")
        if not isinstance(command_id, str) or command_id not in commands:
            raise ContradictoryFacts("current Review order attribution identity mismatch")
        command = commands[command_id]
        if (
            command.command_kind not in _EXIT_ATTRIBUTION_COMMAND_KINDS
            or command.status not in _ACCEPTED_ATTRIBUTION_COMMAND_STATUSES
        ):
            raise ContradictoryFacts(
                "current Review exit Command is not attributable"
            )
        occurred_at_ms = raw_row.get("occurred_at_ms")
        if (
            isinstance(occurred_at_ms, bool)
            or not isinstance(occurred_at_ms, int)
            or occurred_at_ms <= 0
        ):
            raise ContradictoryFacts("current Review exit fill time is invalid")
        annotations.append(
            ChartAnnotation(
                kind="exit",
                occurred_at_ms=occurred_at_ms,
                price=_decimal_string(
                    raw_row.get("price"),
                    context="current Review exit fill price",
                ),
                label="Exit Fill",
                evidence=(
                    review_evidence,
                    EvidenceRef(
                        kind="command",
                        identity=command.command_id,
                        occurred_at_ms=command.created_at_ms,
                    ),
                ),
            )
        )
    return tuple(annotations)


def _stages(
    facts: TradeCausalityFacts,
    *,
    current_stage: LifecycleStageKey,
    raw_events: tuple[RawTradeEventView, ...],
) -> tuple[LifecycleStageView, ...]:
    stage_evidence: dict[LifecycleStageKey, list[EvidenceRef]] = {
        stage: [] for stage in _STAGE_ORDER
    }
    stage_evidence["signal"].append(
        EvidenceRef(
            kind="signal",
            identity=facts.signal.signal_event_id,
            occurred_at_ms=facts.signal.occurred_at_ms,
        )
    )
    stage_evidence["admission"].append(
        EvidenceRef(
            kind="admission",
            identity=facts.admission.admission_decision_id,
            occurred_at_ms=facts.admission.decided_at_ms,
        )
    )
    for event in raw_events:
        if event.classification == "mapped":
            stage_evidence[event.stage].append(event.evidence[0])
    if facts.review is not None:
        stage_evidence["review"].append(
            EvidenceRef(
                kind="review",
                identity=facts.review.review_id,
                occurred_at_ms=facts.review.created_at_ms,
            )
        )
    current_index = _STAGE_ORDER.index(current_stage)
    terminal = facts.aggregate.aggregate_status == "terminal"
    terminal_rejection = facts.trade.ticket_status in _TERMINAL_REJECTION_STATUSES
    aggregate_evidence = EvidenceRef(
        kind="aggregate",
        identity=facts.aggregate.ticket_id,
        occurred_at_ms=facts.aggregate.updated_at_ms,
    )
    stages: list[LifecycleStageView] = []
    for index, key in enumerate(_STAGE_ORDER):
        business_evidence = _deduplicate_evidence(stage_evidence[key])
        display_evidence = list(business_evidence)
        if key == current_stage:
            display_evidence.append(aggregate_evidence)
            display_evidence.extend(
                event.evidence[0]
                for event in raw_events
                if event.stage == key and event.classification == "unmapped"
            )
        evidence = _deduplicate_evidence(display_evidence)
        times = [
            item.occurred_at_ms
            for item in business_evidence
        ]
        if terminal:
            status: Literal[
                "pending",
                "current",
                "complete",
                "unavailable",
                "skipped",
            ] = "complete" if business_evidence else "unavailable"
        elif terminal_rejection and index > current_index:
            status = "skipped"
        elif terminal_rejection or index < current_index:
            status = "complete" if business_evidence else "unavailable"
        elif index == current_index:
            status = "current" if business_evidence else "unavailable"
        else:
            status = "pending"
        started_at_ms = min(times) if times else None
        completed_at_ms = (
            max(times) if status == "complete" and times else None
        )
        stages.append(
            LifecycleStageView(
                key=key,
                label=_STAGE_LABELS[key],
                status=status,
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                duration_ms=(
                    None
                    if started_at_ms is None or completed_at_ms is None
                    else completed_at_ms - started_at_ms
                ),
                summary=_stage_summary(key, status),
                evidence=evidence,
            )
        )
    return tuple(stages)


def _review_evidence(
    facts: TradeCausalityFacts,
    raw_events: tuple[RawTradeEventView, ...],
) -> tuple[EvidenceRef, ...]:
    evidence = [
        event.evidence[0]
        for event in raw_events
        if event.event_type in _REVIEW_EVENTS
    ]
    if facts.review is not None:
        evidence.append(
            EvidenceRef(
                kind="review",
                identity=facts.review.review_id,
                occurred_at_ms=facts.review.created_at_ms,
            )
        )
    return _deduplicate_evidence(evidence)


def _decimal_string(value: object, *, context: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ContradictoryFacts(f"{context} is not an exact Decimal string")
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ContradictoryFacts(
            f"{context} is not an exact Decimal string"
        ) from exc
    if not decimal.is_finite() or decimal <= 0:
        raise ContradictoryFacts(f"{context} must be finite and positive")
    return decimal


def _annotation_order(kind: str) -> int:
    return {
        "signal": 0,
        "stop": 1,
        "entry": 2,
        "take_profit": 3,
        "exit": 4,
    }[kind]


def _stage_summary(
    key: LifecycleStageKey,
    status: Literal[
        "pending",
        "current",
        "complete",
        "unavailable",
        "skipped",
    ],
) -> str:
    return f"{_STAGE_LABELS[key]}: {status}"


def _deduplicate_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    unique: dict[tuple[str, str, int], EvidenceRef] = {}
    for item in evidence:
        unique[(item.kind, item.identity, item.occurred_at_ms)] = item
    return tuple(unique.values())
