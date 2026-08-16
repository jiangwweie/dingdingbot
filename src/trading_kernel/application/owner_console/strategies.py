"""Deterministic StrategyVersion evaluation summaries for the Owner Console."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from src.trading_kernel.application.owner_console.exit_attribution import (
    is_controlled_exit,
)
from src.trading_kernel.application.owner_console.models import (
    ChartAnnotation,
    EvidenceRef,
    MoneyMetric,
    PageCursor,
    StrategyObservationFacts,
    StrategyObservationListItem,
    StrategyObservationListPage,
    StrategyObservationPageFacts,
    StrategyPageFacts,
    StrategySummaryPage,
    StrategyTicketFacts,
    StrategyTicketListItem,
    StrategyTicketListPage,
    StrategyTicketPageFacts,
    StrategyVersionFacts,
    StrategyVersionSummary,
    TradeItemFacts,
    encode_cursor,
)
from src.trading_kernel.application.owner_console.trades import build_trade_item


class StrategyFactsContradiction(RuntimeError):
    """The version-isolated read facts cannot support an Owner conclusion."""


def build_strategy_page(facts: StrategyPageFacts) -> StrategySummaryPage:
    """Summarize each StrategyVersion without mixing version or exit scope."""

    items = tuple(_build_version_summary(version) for version in facts.versions)
    return StrategySummaryPage(
        from_ms=facts.from_ms,
        to_ms=facts.to_ms,
        view=facts.view,
        items=items,
        evidence=_deduplicate_evidence(
            evidence for version in items for evidence in version.evidence
        ),
    )


def strategy_ticket_path(
    ticket: StrategyTicketFacts,
) -> Literal["tp1_reached", "tp1_not_reached", "controlled_exit", "not_terminal"]:
    """Classify a Ticket using its frozen exit reason and TP1 event fact."""

    if not _is_natural_terminal(ticket):
        return "controlled_exit" if _is_controlled_exit(ticket) else "not_terminal"
    return "tp1_reached" if ticket.tp1_reached else "tp1_not_reached"


def build_strategy_ticket_page(
    facts: StrategyTicketPageFacts,
) -> StrategyTicketListPage:
    """Build a bounded modal Ticket page with the exact requested path."""

    if len(facts.items) > facts.requested_limit + 1:
        raise StrategyFactsContradiction("Strategy Ticket page exceeded limit+1 bound")
    page_facts = facts.items[: facts.requested_limit]
    items = tuple(_strategy_ticket_list_item(item) for item in page_facts)
    next_cursor = None
    if len(facts.items) > facts.requested_limit and page_facts:
        boundary = page_facts[-1]
        next_cursor = encode_cursor(
            PageCursor(sort_ms=boundary.issued_at_ms, identity=boundary.ticket_id)
        )
    return StrategyTicketListPage(items=items, next_cursor=next_cursor)


def build_strategy_observation_page(
    facts: StrategyObservationPageFacts,
) -> StrategyObservationListPage:
    """Build one bounded Observation modal page with frozen price annotations."""

    if len(facts.items) > facts.requested_limit + 1:
        raise StrategyFactsContradiction(
            "Strategy Observation page exceeded limit+1 bound"
        )
    page_facts = facts.items[: facts.requested_limit]
    items = tuple(_strategy_observation_item(item) for item in page_facts)
    next_cursor = None
    if len(facts.items) > facts.requested_limit and page_facts:
        boundary = page_facts[-1]
        next_cursor = encode_cursor(
            PageCursor(
                sort_ms=boundary.occurred_at_ms,
                identity=boundary.shadow_outcome_id,
            )
        )
    return StrategyObservationListPage(items=items, next_cursor=next_cursor)


def _build_version_summary(facts: StrategyVersionFacts) -> StrategyVersionSummary:
    natural = tuple(ticket for ticket in facts.tickets if _is_natural_terminal(ticket))
    confirmed = tuple(
        ticket for ticket in natural if _has_complete_natural_review(ticket)
    )
    for ticket in confirmed:
        _require_complete_economics(ticket)

    net_pnl = _summary_metric(
        (ticket.net_pnl.value for ticket in confirmed),
        unit="USDT",
    )
    net_r = _summary_metric(
        (ticket.net_r.value for ticket in confirmed),
        unit="R",
    )
    evidence = _deduplicate_evidence(
        evidence
        for source in (
            facts.evidence,
            *(ticket.evidence for ticket in facts.tickets),
            *(observation.evidence for observation in facts.observations),
        )
        for evidence in source
    )
    completed_observations = tuple(
        item for item in facts.observations if item.status == "completed"
    )
    return StrategyVersionSummary(
        strategy_group_id=facts.strategy_group_id,
        strategy_group_display_name=facts.strategy_group_display_name,
        strategy_version_id=facts.strategy_version_id,
        version=facts.version,
        strategy_version_status=facts.strategy_version_status,
        is_current=facts.is_current,
        ticket_count=len(facts.tickets),
        natural_terminal_count=len(natural),
        confirmed_natural_review_count=len(confirmed),
        pending_natural_review_count=len(natural) - len(confirmed),
        controlled_exit_count=sum(
            1 for ticket in facts.tickets if _is_controlled_exit(ticket)
        ),
        tp1_reached_count=sum(1 for ticket in natural if ticket.tp1_reached),
        tp1_not_reached_count=sum(1 for ticket in natural if not ticket.tp1_reached),
        win_count=sum(
            1
            for ticket in confirmed
            if ticket.net_pnl.value is not None and ticket.net_pnl.value > 0
        ),
        loss_count=sum(
            1
            for ticket in confirmed
            if ticket.net_pnl.value is not None and ticket.net_pnl.value < 0
        ),
        net_pnl=net_pnl,
        net_r=net_r,
        observation_count=len(facts.observations),
        completed_observation_count=len(completed_observations),
        unavailable_observation_count=sum(
            1 for item in facts.observations if item.status == "unavailable"
        ),
        tp1_first_count=_observation_path_count(facts, "tp1_first"),
        initial_stop_first_count=_observation_path_count(
            facts,
            "initial_stop_first",
        ),
        opening_range_failure_count=_observation_path_count(
            facts,
            "opening_range_failure",
        ),
        ambiguous_observation_count=_observation_path_count(
            facts,
            "ambiguous_same_bar",
        ),
        time_stop_count=_observation_path_count(facts, "time_stop"),
        session_exit_count=_observation_path_count(facts, "session_exit"),
        median_mfe_r=_median_decimal(
            item.mfe_r for item in completed_observations
        ),
        median_mae_r=_median_decimal(
            item.mae_r for item in completed_observations
        ),
        median_spread_bps=_median_decimal(
            item.spread_bps for item in facts.observations
        ),
        evidence=evidence,
        product_events=facts.product_events,
    )


def _observation_path_count(
    facts: StrategyVersionFacts,
    path: str,
) -> int:
    return sum(1 for item in facts.observations if item.first_path == path)


def _median_decimal(values: Iterable[Decimal | None]) -> Decimal | None:
    exact = sorted(item for item in values if item is not None)
    if not exact:
        return None
    midpoint = len(exact) // 2
    if len(exact) % 2:
        return exact[midpoint]
    return (exact[midpoint - 1] + exact[midpoint]) / Decimal(2)


def _strategy_observation_item(
    facts: StrategyObservationFacts,
) -> StrategyObservationListItem:
    annotations: list[ChartAnnotation] = []
    if facts.entry_reference_price is not None:
        annotations.append(
            ChartAnnotation(
                kind="signal",
                occurred_at_ms=facts.occurred_at_ms,
                price=facts.entry_reference_price,
                label="OBSERVATION SIGNAL",
                evidence=facts.evidence,
            )
        )
    if facts.first_path_at_ms is not None:
        if facts.first_path in {"tp1_first", "ambiguous_same_bar"} and (
            facts.take_profit_price is not None
        ):
            annotations.append(
                ChartAnnotation(
                    kind="take_profit",
                    occurred_at_ms=facts.first_path_at_ms,
                    price=facts.take_profit_price,
                    label="TP1 OBSERVED",
                    evidence=facts.evidence,
                )
            )
        if facts.first_path in {"initial_stop_first", "ambiguous_same_bar"} and (
            facts.initial_stop_price is not None
        ):
            annotations.append(
                ChartAnnotation(
                    kind="stop",
                    occurred_at_ms=facts.first_path_at_ms,
                    price=facts.initial_stop_price,
                    label="STOP OBSERVED",
                    evidence=facts.evidence,
                )
            )
        if (
            facts.first_path == "opening_range_failure"
            and facts.opening_range_boundary_price is not None
        ):
            annotations.append(
                ChartAnnotation(
                    kind="exit",
                    occurred_at_ms=facts.first_path_at_ms,
                    price=facts.opening_range_boundary_price,
                    label="OPENING RANGE FAILURE",
                    evidence=facts.evidence,
                )
            )
    return StrategyObservationListItem(
        **facts.model_dump(mode="python"),
        annotations=tuple(annotations),
    )


def _is_controlled_exit(ticket: StrategyTicketFacts) -> bool:
    return is_controlled_exit(ticket.exit_reason)


def _is_natural_terminal(ticket: StrategyTicketFacts) -> bool:
    return (
        ticket.ticket_status == "terminal"
        and ticket.aggregate_status == "terminal"
        and ticket.terminal_at_ms is not None
        and not _is_controlled_exit(ticket)
    )


def _has_complete_natural_review(ticket: StrategyTicketFacts) -> bool:
    return (
        ticket.economics_completeness == "complete"
        and ticket.review_id is not None
        and ticket.review_created_at_ms is not None
    )


def _require_complete_economics(ticket: StrategyTicketFacts) -> None:
    if (
        ticket.net_pnl.unit != "USDT"
        or ticket.net_r.unit != "R"
        or ticket.net_pnl.value is None
        or ticket.net_r.value is None
        or ticket.net_pnl.unavailable_reason is not None
        or ticket.net_r.unavailable_reason is not None
    ):
        raise StrategyFactsContradiction(
            "complete StrategyVersion Review has incomplete economics"
        )


def _strategy_ticket_list_item(facts: TradeItemFacts) -> StrategyTicketListItem:
    trade = build_trade_item(facts)
    path: Literal[
        "tp1_reached",
        "tp1_not_reached",
        "controlled_exit",
        "not_terminal",
    ]
    if not (
        facts.ticket_status == "terminal"
        and facts.aggregate_status == "terminal"
        and facts.terminal_at_ms is not None
    ):
        path = "not_terminal"
    elif is_controlled_exit(trade.exit_reason):
        path = "controlled_exit"
    else:
        path = "tp1_reached" if facts.tp1_reached else "tp1_not_reached"
    return StrategyTicketListItem(
        **trade.model_dump(mode="python"),
        evaluation_path=path,
    )


def _summary_metric(
    values: Iterable[Decimal | None],
    *,
    unit: str,
) -> MoneyMetric:
    exact_values = tuple(value for value in values if value is not None)
    if not exact_values:
        return MoneyMetric(
            value=None,
            unit=unit,  # type: ignore[arg-type]
            unavailable_reason="no_confirmed_natural_review",
        )
    return MoneyMetric(
        value=sum(exact_values, Decimal(0)),
        unit=unit,  # type: ignore[arg-type]
    )


def _deduplicate_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int]] = set()
    exact: list[EvidenceRef] = []
    for item in evidence:
        key = (item.kind, item.identity, item.occurred_at_ms)
        if key not in seen:
            seen.add(key)
            exact.append(item)
    return tuple(exact)
