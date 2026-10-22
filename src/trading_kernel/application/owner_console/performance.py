"""One full-window income contract for all Owner read surfaces; no economic writes."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal, localcontext
from hashlib import sha256

from src.trading_kernel.application.owner_console.exit_attribution import classify_exit
from src.trading_kernel.application.owner_console.models import (
    MetricCoverage,
    MoneyMetric,
    PerformanceMetrics,
    PerformanceQuery,
    PerformanceSample,
    PerformanceSummary,
    ReviewEconomicSummary,
    TradeListItem,
)


class PerformanceSnapshotChanged(RuntimeError):
    """An older page must not mix with a newly revised income population."""


def sample_from_trade(trade: TradeListItem, version: str) -> PerformanceSample:
    if trade.terminal_at_ms is None:
        raise ValueError("income sample must be terminal")
    return PerformanceSample(
        ticket_id=trade.ticket_id,
        strategy_group_id=trade.strategy_group_id,
        strategy_version_id=version,
        exchange_instrument_id=trade.exchange_instrument_id,
        position_side=trade.position_side,
        terminal_at_ms=trade.terminal_at_ms,
        review_id=trade.review_id,
        review_revision=trade.review_revision,
        exit_reason=trade.exit_reason,
        economics=ReviewEconomicSummary(
            gross_pnl=trade.gross_pnl,
            fees=trade.fees,
            funding=trade.funding,
            net_pnl=trade.net_pnl,
            net_r=trade.net_r,
        ),
    )


def aggregate_metrics(samples: Iterable[PerformanceSample]) -> PerformanceMetrics:
    items = tuple(samples)
    metrics = {}
    coverage = {}
    for name in ("gross_pnl", "fees", "funding", "net_pnl", "net_r"):
        values = [
            getattr(i.economics, name).value
            for i in items
            if getattr(i.economics, name).value is not None
        ]
        with localcontext() as context:
            context.prec = 80
            value = sum(values, Decimal(0)) if values else None
        metrics[name] = MoneyMetric(
            value=value,
            unit="R" if name == "net_r" else "USDT",
            unavailable_reason=None
            if value is not None
            else "no_confirmed_metric"
            if items
            else "no_review_evidence",
        )
        coverage[name] = MetricCoverage(
            available_count=len(values),
            total_count=len(items),
            missing_ticket_ids=tuple(
                i.ticket_id for i in items if getattr(i.economics, name).value is None
            ),
        )
    net = [
        i.economics.net_pnl.value
        for i in items
        if i.economics.net_pnl.value is not None
    ]
    return PerformanceMetrics(
        sample_count=len(items),
        confirmed_count=len(net),
        unreviewed_count=sum(i.review_id is None for i in items),
        win_count=sum(v > 0 for v in net),
        loss_count=sum(v < 0 for v in net),
        breakeven_count=sum(v == 0 for v in net),
        verified_totals=ReviewEconomicSummary(**metrics),
        metric_coverage=coverage,
    )


def build_performance_summary(
    samples: Iterable[PerformanceSample], query: PerformanceQuery
) -> PerformanceSummary:
    items = tuple(sorted(samples, key=lambda i: i.ticket_id))
    # Whole-source fingerprint also changes when an excluded row changes scope/status.
    identity = {
        "contract": "terminal-income-v1",
        "query": query.model_dump(mode="json", exclude={"limit", "cursor", "snapshot"}),
        "samples": [i.model_dump(mode="json") for i in items],
    }
    snapshot = (
        "profit:"
        + sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    selected = tuple(
        i
        for i in items
        if (
            query.exit_scope == "all"
            or classify_exit(i.exit_reason) == query.exit_scope
        )
    )
    metrics = aggregate_metrics(selected)
    return PerformanceSummary(
        **metrics.model_dump(),
        from_ms=query.from_ms,
        to_ms=query.to_ms,
        snapshot_id=snapshot,
        view=query.view,
        exit_scope=query.exit_scope,
        complete_review_count=sum(i.review_status == "complete" for i in selected),
        incomplete_review_count=sum(i.review_status != "complete" for i in selected),
        attention_count=sum(i.attention_count for i in selected),
        breakdown={
            kind: aggregate_metrics(
                i for i in items if classify_exit(i.exit_reason) == kind
            )
            for kind in ("strategy", "owner", "safety", "unknown")
        },
        by_strategy_group={
            group: aggregate_metrics(
                i for i in selected if i.strategy_group_id == group
            )
            for group in sorted({i.strategy_group_id for i in selected})
        },
    )
