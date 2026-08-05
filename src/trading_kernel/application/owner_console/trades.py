"""Deterministic assembly for the unified active and terminal Trade list."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    LifecycleStageKey,
    MoneyMetric,
    PageCursor,
    TradeItemFacts,
    TradeListItem,
    TradeListPage,
    TradePageFacts,
    encode_cursor,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.ticket import TicketStatus


class TradeFactsContradiction(RuntimeError):
    """Persisted Trade identities or lifecycle facts disagree."""


_ENTRY_STATUSES = frozenset(
    {
        AggregateStatus.LEVERAGE_PENDING,
        AggregateStatus.LEVERAGE_CONFIRMED,
        AggregateStatus.LEVERAGE_REJECTED,
        AggregateStatus.LEVERAGE_OUTCOME_UNKNOWN,
        AggregateStatus.ENTRY_PENDING,
        AggregateStatus.ENTRY_ACCEPTED,
        AggregateStatus.ENTRY_REJECTED,
        AggregateStatus.ENTRY_OUTCOME_UNKNOWN,
        AggregateStatus.ENTRY_RECONCILED_ABSENT,
        AggregateStatus.PARTIAL_FILL_INCIDENT,
        AggregateStatus.PARTIAL_FILL_CANCEL_REJECTED,
        AggregateStatus.PARTIAL_FILL_CANCEL_OUTCOME_UNKNOWN,
    }
)
_PROTECTION_STATUSES = frozenset(
    {
        AggregateStatus.PROTECTION_PENDING,
        AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN,
        AggregateStatus.POST_FILL_RISK_PENDING,
        AggregateStatus.POSITION_PROTECTED,
    }
)
_TP_RUNNER_STATUSES = frozenset(
    {
        AggregateStatus.TP1_PENDING,
        AggregateStatus.TP1_REJECTED,
        AggregateStatus.TP1_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_REPLACEMENT_PENDING,
        AggregateStatus.RUNNER_REPLACEMENT_REJECTED,
        AggregateStatus.RUNNER_REPLACEMENT_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_REJECTED,
        AggregateStatus.RUNNER_OLD_STOP_CANCEL_OUTCOME_UNKNOWN,
        AggregateStatus.RUNNER_PROTECTED,
    }
)
_EXIT_STATUSES = frozenset(
    {
        AggregateStatus.EXIT_PENDING,
        AggregateStatus.EXIT_ACCEPTED,
        AggregateStatus.EXIT_REJECTED,
        AggregateStatus.EXIT_OUTCOME_UNKNOWN,
        AggregateStatus.CONTROLLED_FLATTEN_PENDING,
        AggregateStatus.CONTROLLED_FLATTEN_ACCEPTED,
        AggregateStatus.CONTROLLED_FLATTEN_REJECTED,
        AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN,
    }
)
_RECONCILIATION_STATUSES = frozenset(
    {
        AggregateStatus.RECONCILIATION_PENDING,
        AggregateStatus.CANCEL_REJECTED,
        AggregateStatus.CANCEL_OUTCOME_UNKNOWN,
        AggregateStatus.SETTLEMENT_PENDING,
    }
)
_REVIEW_STATUSES = frozenset(
    {AggregateStatus.REVIEW_PENDING, AggregateStatus.TERMINAL}
)

_STATUS_STAGES: tuple[
    tuple[frozenset[AggregateStatus], LifecycleStageKey], ...
] = (
    (_ENTRY_STATUSES, "entry"),
    (_PROTECTION_STATUSES, "protection"),
    (_TP_RUNNER_STATUSES, "tp_runner"),
    (_EXIT_STATUSES, "exit"),
    (_RECONCILIATION_STATUSES, "reconciliation"),
    (_REVIEW_STATUSES, "review"),
)
_MAPPED_STATUSES = frozenset(
    status for statuses, _stage in _STATUS_STAGES for status in statuses
)
if _MAPPED_STATUSES != frozenset(AggregateStatus):
    raise RuntimeError("Aggregate status lifecycle mapping is incomplete")

_COMPLETED_BEFORE_STAGE: dict[LifecycleStageKey, int] = {
    "signal": 0,
    "admission": 1,
    "entry": 2,
    "protection": 3,
    "tp_runner": 4,
    "exit": 5,
    "reconciliation": 6,
    "review": 7,
}

_TERMINAL_TICKET_AGGREGATE = {
    TicketStatus.LEVERAGE_REJECTED: AggregateStatus.LEVERAGE_REJECTED,
    TicketStatus.ENTRY_REJECTED: AggregateStatus.ENTRY_REJECTED,
    TicketStatus.ENTRY_RECONCILED_ABSENT: (
        AggregateStatus.ENTRY_RECONCILED_ABSENT
    ),
    TicketStatus.TERMINAL: AggregateStatus.TERMINAL,
}
_TERMINAL_REJECTION_TICKET_STATUSES = frozenset(
    {
        TicketStatus.LEVERAGE_REJECTED,
        TicketStatus.ENTRY_REJECTED,
        TicketStatus.ENTRY_RECONCILED_ABSENT,
    }
)
_ACTIVE_AGGREGATE_STATUSES = frozenset(AggregateStatus).difference(
    _TERMINAL_TICKET_AGGREGATE.values()
)


def aggregate_stage(status: str) -> LifecycleStageKey:
    """Map every current Aggregate status to one public lifecycle stage."""

    try:
        aggregate_status = AggregateStatus(status)
    except ValueError as exc:
        raise TradeFactsContradiction(
            f"unknown aggregate status: {status}"
        ) from exc
    for statuses, stage in _STATUS_STAGES:
        if aggregate_status in statuses:
            return stage
    raise TradeFactsContradiction(
        f"unknown aggregate status: {status}"
    )


def build_trade_page(facts: TradePageFacts) -> TradeListPage:
    """Remove the detector row and encode the exact returned boundary."""

    if len(facts.items) > facts.requested_limit + 1:
        raise TradeFactsContradiction("Trade page exceeded limit+1 bound")
    page_facts = facts.items[: facts.requested_limit]
    items = tuple(build_trade_item(item) for item in page_facts)
    next_cursor = None
    if len(facts.items) > facts.requested_limit and page_facts:
        boundary = page_facts[-1]
        next_cursor = encode_cursor(
            PageCursor(
                sort_ms=boundary.issued_at_ms,
                identity=boundary.ticket_id,
            )
        )
    return TradeListPage(items=items, next_cursor=next_cursor)


def build_trade_item(facts: TradeItemFacts) -> TradeListItem:
    """Build one Trade row without recomputing Review economics."""

    stage = aggregate_stage(facts.aggregate_status)
    active = _validate_lifecycle_shape(facts)
    _validate_review_pointer(facts, active=active)

    evidence = list(facts.evidence)
    if facts.review_id is not None and facts.review_created_at_ms is not None:
        evidence.append(
            EvidenceRef(
                kind="review",
                identity=facts.review_id,
                occurred_at_ms=facts.review_created_at_ms,
            )
        )
    exit_reason, exit_reason_unavailable_reason = _exit_reason(
        facts,
        active=active,
    )
    if (
        facts.exit_event_id is not None
        and facts.exit_event_occurred_at_ms is not None
    ):
        evidence.append(
            EvidenceRef(
                kind="event",
                identity=facts.exit_event_id,
                occurred_at_ms=facts.exit_event_occurred_at_ms,
            )
        )
    for incident_id, opened_at_ms in (
        (facts.open_incident_id, facts.open_incident_opened_at_ms),
        (facts.latest_incident_id, facts.latest_incident_opened_at_ms),
    ):
        if incident_id is not None and opened_at_ms is not None:
            evidence.append(
                EvidenceRef(
                    kind="incident",
                    identity=incident_id,
                    occurred_at_ms=opened_at_ms,
                )
            )

    if active:
        economics = _unavailable_economics("ticket_active")
        completeness = None
    elif facts.review_id is None or facts.review_metrics is None:
        economics = _unavailable_economics("review_missing")
        completeness = None
    else:
        economics, completeness = _review_economics(facts.review_metrics)

    if completeness == "external_exit_unavailable":
        exit_reason = "External Flat / Exit Fills Unavailable"
        exit_reason_unavailable_reason = None

    attention_items = (
        ()
        if facts.open_incident_id is None
        else (f"open_incident:{facts.open_incident_id}",)
    )
    completed_stage_count = (
        8
        if facts.aggregate_status == AggregateStatus.TERMINAL.value
        else _COMPLETED_BEFORE_STAGE[stage]
    )
    return TradeListItem(
        ticket_id=facts.ticket_id,
        strategy_group_id=facts.strategy_group_id,
        event_spec_id=facts.event_spec_id,
        exchange_instrument_id=facts.exchange_instrument_id,
        position_side=facts.position_side,
        ticket_status=facts.ticket_status,
        aggregate_status=facts.aggregate_status,
        lifecycle_stage=stage,
        issued_at_ms=facts.issued_at_ms,
        terminal_at_ms=facts.terminal_at_ms,
        review_id=facts.aggregate_review_id,
        review_revision=facts.review_revision,
        economics_completeness=completeness,
        completed_stage_count=completed_stage_count,
        total_stage_count=8,
        exit_reason=exit_reason,
        exit_reason_unavailable_reason=exit_reason_unavailable_reason,
        gross_pnl=economics[0],
        fees=economics[1],
        funding=economics[2],
        net_pnl=economics[3],
        net_r=economics[4],
        attention_items=attention_items,
        evidence=_deduplicate_evidence(evidence),
    )


def _exit_reason(
    facts: TradeItemFacts,
    *,
    active: bool,
) -> tuple[str | None, str | None]:
    event_facts = (
        facts.exit_event_id,
        facts.exit_event_type,
        facts.exit_event_payload,
        facts.exit_event_occurred_at_ms,
    )
    if facts.exit_event_id is None:
        if any(value is not None for value in event_facts[1:]):
            raise TradeFactsContradiction("partial exit Event row")
    else:
        if any(value is None for value in event_facts[1:]):
            raise TradeFactsContradiction("partial exit Event row")
        if facts.exit_event_type != "ExitRequested":
            raise TradeFactsContradiction("unexpected exit Event type")
        payload = facts.exit_event_payload
        if payload is None:
            raise TradeFactsContradiction("partial exit Event row")
        if (
            payload.get("event_id") != facts.exit_event_id
            or payload.get("ticket_id") != facts.ticket_id
            or payload.get("occurred_at_ms")
            != facts.exit_event_occurred_at_ms
        ):
            raise TradeFactsContradiction("exit Event identity mismatch")
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise TradeFactsContradiction("exit Event reason is missing")
        return reason.strip(), None

    try:
        ticket_status = TicketStatus(facts.ticket_status)
    except ValueError as exc:
        raise TradeFactsContradiction(
            f"unknown Ticket status: {facts.ticket_status}"
        ) from exc
    if ticket_status in _TERMINAL_REJECTION_TICKET_STATUSES:
        return None, "exit_not_applicable"
    if active:
        return None, "ticket_active"
    return None, "exit_reason_evidence_missing"


def _validate_lifecycle_shape(facts: TradeItemFacts) -> bool:
    try:
        ticket_status = TicketStatus(facts.ticket_status)
    except ValueError as exc:
        raise TradeFactsContradiction(
            f"unknown Ticket status: {facts.ticket_status}"
        ) from exc
    aggregate_status = AggregateStatus(facts.aggregate_status)

    if ticket_status is TicketStatus.ISSUED:
        if (
            facts.terminal_at_ms is not None
            or aggregate_status not in _ACTIVE_AGGREGATE_STATUSES
        ):
            raise TradeFactsContradiction(
                "Ticket and Aggregate status mismatch"
            )
        return True

    expected_aggregate = _TERMINAL_TICKET_AGGREGATE.get(ticket_status)
    if (
        expected_aggregate is None
        or aggregate_status is not expected_aggregate
        or facts.terminal_at_ms is None
        or facts.terminal_at_ms < facts.issued_at_ms
    ):
        raise TradeFactsContradiction("Ticket and Aggregate status mismatch")
    if (
        ticket_status in _TERMINAL_REJECTION_TICKET_STATUSES
        and _has_any_review_fact(facts)
    ):
        raise TradeFactsContradiction("terminal rejection has a Review")
    return False


def _has_any_review_fact(facts: TradeItemFacts) -> bool:
    return any(
        value is not None
        for value in (
            facts.aggregate_review_id,
            facts.review_id,
            facts.review_ticket_id,
            facts.review_revision,
            facts.review_created_at_ms,
            facts.review_metrics,
        )
    )


def _validate_review_pointer(facts: TradeItemFacts, *, active: bool) -> None:
    if active and _has_any_review_fact(facts):
        raise TradeFactsContradiction("active Ticket has a current Review")
    if facts.review_id is None:
        if any(
            value is not None
            for value in (
                facts.review_ticket_id,
                facts.review_revision,
                facts.review_created_at_ms,
                facts.review_metrics,
            )
        ):
            raise TradeFactsContradiction("partial current Review row")
        return
    if (
        facts.aggregate_review_id != facts.review_id
        or facts.review_ticket_id != facts.ticket_id
    ):
        raise TradeFactsContradiction("current Review identity mismatch")
    if (
        facts.review_revision is None
        or facts.review_revision <= 0
        or facts.review_created_at_ms is None
        or facts.review_metrics is None
    ):
        raise TradeFactsContradiction("partial current Review row")


Economics = tuple[MoneyMetric, MoneyMetric, MoneyMetric, MoneyMetric, MoneyMetric]
Completeness = Literal[
    "complete", "funding_unavailable", "external_exit_unavailable"
]


def _review_economics(
    metrics: Mapping[str, object],
) -> tuple[Economics, Completeness | None]:
    completeness = metrics.get("economics_completeness")
    if completeness == "complete":
        values = _complete_metric_values(metrics)
        if values is None:
            return _unavailable_economics("incomplete_review_economics"), None
        return (
            (
                MoneyMetric(value=values[0], unit="USDT"),
                MoneyMetric(value=values[1], unit="USDT"),
                MoneyMetric(value=values[2], unit="USDT"),
                MoneyMetric(value=values[3], unit="USDT"),
                MoneyMetric(value=values[4], unit="R"),
            ),
            "complete",
        )
    if completeness == "funding_unavailable":
        gross = _exact_decimal(metrics.get("gross_realized_pnl_quote"))
        fees = _exact_decimal(metrics.get("trading_fees_quote"))
        reason = metrics.get("funding_unavailable_reason")
        unavailable_shape = (
            "funding_quote" in metrics
            and metrics["funding_quote"] is None
            and "net_pnl_quote" in metrics
            and metrics["net_pnl_quote"] is None
            and "planned_r_multiple" in metrics
            and metrics["planned_r_multiple"] is None
            and isinstance(reason, str)
            and bool(reason.strip())
        )
        if gross is None or fees is None or not unavailable_shape:
            return _unavailable_economics("incomplete_review_economics"), None
        reason_code = "funding_unavailable"
        return (
            (
                MoneyMetric(value=gross, unit="USDT"),
                MoneyMetric(value=fees, unit="USDT"),
                MoneyMetric(
                    value=None,
                    unit="USDT",
                    unavailable_reason=reason_code,
                ),
                MoneyMetric(
                    value=None,
                    unit="USDT",
                    unavailable_reason=reason_code,
                ),
                MoneyMetric(
                    value=None,
                    unit="R",
                    unavailable_reason=reason_code,
                ),
            ),
            "funding_unavailable",
        )
    if completeness == "external_exit_unavailable":
        if not _external_exit_shape_is_exact(metrics):
            return _unavailable_economics("incomplete_review_economics"), None
        return (
            _unavailable_economics("external_exit_unavailable"),
            "external_exit_unavailable",
        )
    return _unavailable_economics("incomplete_review_economics"), None


def _complete_metric_values(
    metrics: Mapping[str, object],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal] | None:
    keys = (
        "gross_realized_pnl_quote",
        "trading_fees_quote",
        "funding_quote",
        "net_pnl_quote",
        "planned_r_multiple",
    )
    values = tuple(_exact_decimal(metrics.get(key)) for key in keys)
    if any(value is None for value in values):
        return None
    return cast(tuple[Decimal, Decimal, Decimal, Decimal, Decimal], values)


def _external_exit_shape_is_exact(metrics: Mapping[str, object]) -> bool:
    entry_quantity = _exact_decimal(metrics.get("entry_quantity"))
    return (
        metrics.get("unavailable_reason")
        == "external_flat_exit_fills_unavailable"
        and entry_quantity is not None
        and entry_quantity > 0
        and all(
            _positive_int_metric(metrics, key)
            for key in (
                "entry_time_ms",
                "external_flat_detected_at_ms",
                "visibility_grace_ms",
            )
        )
    )


def _positive_int_metric(metrics: Mapping[str, object], key: str) -> bool:
    value = metrics.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _exact_decimal(value: object) -> Decimal | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _unavailable_economics(reason: str) -> Economics:
    return (
        MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
        MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
        MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
        MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
        MoneyMetric(value=None, unit="R", unavailable_reason=reason),
    )


def _deduplicate_evidence(
    evidence: list[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int]] = set()
    exact: list[EvidenceRef] = []
    for item in evidence:
        key = (item.kind, item.identity, item.occurred_at_ms)
        if key not in seen:
            seen.add(key)
            exact.append(item)
    return tuple(exact)
