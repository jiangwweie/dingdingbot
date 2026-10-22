"""Deterministic StrategyVersion evaluation summaries for the Owner Console."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, localcontext
from typing import Literal, cast

from src.trading_kernel.application.owner_console.exit_attribution import (
    classify_exit,
)
from src.trading_kernel.application.owner_console.models import (
    ChartAnnotation,
    EvidenceRef,
    MoneyMetric,
    PageCursor,
    PerformanceSample,
    ReviewEconomicSummary,
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
from src.trading_kernel.application.owner_console.performance import aggregate_metrics
from src.trading_kernel.application.owner_console.trades import build_trade_item


class StrategyFactsContradiction(RuntimeError):
    """The version-isolated read facts cannot support an Owner conclusion."""


def build_strategy_page(facts: StrategyPageFacts) -> StrategySummaryPage:
    """Summarize each StrategyVersion without mixing version or exit scope."""

    items = tuple(
        _build_version_summary(version, exit_scope=facts.exit_scope)
        for version in facts.versions
    )
    return StrategySummaryPage(
        performance=facts.performance,
        from_ms=facts.from_ms,
        to_ms=facts.to_ms,
        view=facts.view,
        items=items,
        evidence=_deduplicate_evidence(
            evidence for version in items for evidence in version.evidence
        ),
    )


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
            PageCursor(
                sort_ms=boundary.terminal_at_ms or boundary.issued_at_ms,
                identity=boundary.ticket_id,
            )
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


def _build_version_summary(
    facts: StrategyVersionFacts, *, exit_scope: str = "all"
) -> StrategyVersionSummary:
    natural = tuple(ticket for ticket in facts.tickets if _is_natural_terminal(ticket))
    confirmed = tuple(
        ticket for ticket in natural if _has_complete_natural_review(ticket)
    )
    for ticket in confirmed:
        _require_complete_economics(ticket)

    terminal = tuple(
        t
        for t in facts.tickets
        if t.ticket_status == "terminal"
        and t.aggregate_status == "terminal"
        and t.terminal_at_ms is not None
    )
    selected = tuple(
        t
        for t in terminal
        if exit_scope == "all" or classify_exit(t.exit_reason) == exit_scope
    )
    unknown = MoneyMetric(
        value=None, unit="USDT", unavailable_reason="no_confirmed_metric"
    )
    samples = tuple(
        PerformanceSample(
            ticket_id=t.ticket_id,
            strategy_group_id=facts.strategy_group_id,
            strategy_version_id=facts.strategy_version_id,
            exchange_instrument_id=t.trade.exchange_instrument_id if t.trade else None,
            position_side=t.trade.position_side if t.trade else None,
            terminal_at_ms=cast(int, t.terminal_at_ms),
            review_id=t.review_id,
            review_revision=None,
            exit_reason=t.exit_reason,
            economics=ReviewEconomicSummary(
                gross_pnl=t.trade.gross_pnl if t.trade else unknown,
                fees=t.trade.fees if t.trade else unknown,
                funding=t.trade.funding if t.trade else unknown,
                net_pnl=t.net_pnl,
                net_r=t.net_r,
            ),
        )
        for t in selected
    )
    income = aggregate_metrics(samples)
    net_pnl = income.verified_totals.net_pnl
    net_r = income.verified_totals.net_r
    if not selected or income.confirmed_count == 0:
        net_pnl = _summary_metric((), unit="USDT")
        net_r = _summary_metric((), unit="R")
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
        selected_terminal_count=len(selected),
        confirmed_review_count=income.confirmed_count,
        safety_exit_count=sum(
            classify_exit(t.exit_reason) == "safety" for t in terminal
        ),
        unknown_exit_count=sum(
            classify_exit(t.exit_reason) == "unknown" for t in terminal
        ),
        metric_coverage=income.metric_coverage,
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
            for ticket in selected
            if ticket.net_pnl.value is not None and ticket.net_pnl.value > 0
        ),
        loss_count=sum(
            1
            for ticket in selected
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
    return classify_exit(ticket.exit_reason) == "owner"


def _is_natural_terminal(ticket: StrategyTicketFacts) -> bool:
    return (
        ticket.ticket_status == "terminal"
        and ticket.aggregate_status == "terminal"
        and ticket.terminal_at_ms is not None
        and classify_exit(ticket.exit_reason) == "strategy"
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
        "safety_exit",
        "unknown_exit",
        "not_terminal",
    ]
    if not (
        facts.ticket_status == "terminal"
        and facts.aggregate_status == "terminal"
        and facts.terminal_at_ms is not None
    ):
        path = "not_terminal"
    elif classify_exit(trade.exit_reason) == "owner":
        path = "controlled_exit"
    elif classify_exit(trade.exit_reason) == "safety":
        path = "safety_exit"
    elif classify_exit(trade.exit_reason) == "unknown":
        path = "unknown_exit"
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
    with localcontext() as context:
        context.prec = 80
        value = sum(exact_values, Decimal(0))
    return MoneyMetric(value=value, unit=unit)  # type: ignore[arg-type]


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
