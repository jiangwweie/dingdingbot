"""Named, complete Owner Console facts for unit tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypeVar, cast

from src.trading_kernel.application.owner_console.models import (
    ChartAnnotation,
    EvidenceRef,
    Freshness,
    LifecycleStageView,
    MoneyMetric,
    OverviewFacts,
    ProgrammaticReviewFacts,
    SignalDetailFacts,
    SignalFactSnapshotFacts,
    SignalItemFacts,
    TradeCausalityFacts,
    TradeItemFacts,
)

FactT = TypeVar(
    "FactT",
    bound=(
        OverviewFacts
        | SignalItemFacts
        | SignalDetailFacts
        | TradeItemFacts
        | TradeCausalityFacts
        | ProgrammaticReviewFacts
    ),
)


def _copy_with_named_overrides(model: FactT, overrides: dict[str, Any]) -> FactT:
    unknown = set(overrides).difference(type(model).model_fields)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"unknown fact override(s): {names}")
    copied = model.model_copy(update=overrides)
    merged = {
        field_name: getattr(copied, field_name)
        for field_name in type(model).model_fields
    }
    return cast(FactT, type(model).model_validate(merged))


def _evidence(kind: str, identity: str, occurred_at_ms: int) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,  # type: ignore[arg-type]
        identity=identity,
        occurred_at_ms=occurred_at_ms,
    )


def overview_facts(**overrides: Any) -> OverviewFacts:
    facts = OverviewFacts(
        observed_at_ms=1_800_000_000_000,
        runtime_freshness=Freshness.FRESH,
        freshness_evidence_identity="account:binance-usdm:test",
        freshness_evidence_at_ms=1_800_000_000_000,
        max_concurrent_tickets=3,
        active_ticket_count=1,
        active_ticket_ids=("ticket:1",),
        latest_capacity_claim_id="claim:1",
        latest_wallet_balance_at_claim=Decimal("100.00"),
        latest_available_margin_at_claim=Decimal("70.00"),
        latest_claim_created_at_ms=1_799_999_900_000,
        open_owner_incident_id=None,
        open_owner_incident_opened_at_ms=None,
        attention_incident_ids=(),
        attention_incident_opened_at_ms=(),
        monitor_statuses=("running", "waiting_for_opportunity"),
        monitor_keys=("monitor:runtime", "monitor:opportunity"),
        monitor_updated_at_ms=(
            1_800_000_000_000,
            1_800_000_000_000,
        ),
        needs_intervention_monitor_key=None,
        needs_intervention_monitor_updated_at_ms=None,
        contradictory_fact_reasons=(),
        contradictory_evidence_identity=None,
        evidence_gaps=(),
        today_net_pnl=MoneyMetric(value=Decimal("3.5100"), unit="USDT"),
        today_net_r=MoneyMetric(value=Decimal("0.4800"), unit="R"),
        today_signal_count=4,
        admitted_signal_count=1,
        rejected_signal_count=3,
        execution_incident_count=0,
        evidence=(
            _evidence("ticket", "ticket:1", 1_799_999_950_000),
            _evidence("review", "review:1", 1_800_000_000_000),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)


def signal_item_facts(**overrides: Any) -> SignalItemFacts:
    facts = SignalItemFacts(
        signal_event_id="signal:1",
        exposure_episode_id="episode:1",
        strategy_group_id="strategy-group:opening-range",
        strategy_version_id="strategy-version:1",
        event_spec_id="event:opening-range-breakout",
        exchange_instrument_id="BTCUSDT",
        position_side="long",
        occurred_at_ms=1_799_999_800_000,
        expires_at_ms=1_800_000_100_000,
        admission_decision_id="admission:1",
        decision_status="admitted",
        first_blocker=None,
        binding_constraint="remaining_initial_margin",
        ticket_id="ticket:1",
        decided_at_ms=1_799_999_900_000,
        shadow_outcome_id=None,
        shadow_status=None,
        shadow_mfe_r=None,
        shadow_mae_r=None,
        shadow_completion_reason=None,
        shadow_observed_through_ms=None,
        shadow_completed_at_ms=None,
        evidence=(
            _evidence("signal", "signal:1", 1_799_999_800_000),
            _evidence("admission", "admission:1", 1_799_999_900_000),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)


def signal_detail_facts(**overrides: Any) -> SignalDetailFacts:
    facts = SignalDetailFacts(
        signal=signal_item_facts(),
        fact_snapshots=(
            SignalFactSnapshotFacts(
                signal_event_id="signal:1",
                fact_definition_id="fact:condition",
                role="condition",
                value=True,
                satisfied=True,
                observed_at_ms=1_799_999_800_000,
                valid_until_ms=1_800_000_100_000,
                projection_version=1,
            ),
            SignalFactSnapshotFacts(
                signal_event_id="signal:1",
                fact_definition_id="fact:reference",
                role="protection_reference",
                value="99.125000000000000001",
                satisfied=True,
                observed_at_ms=1_799_999_800_000,
                valid_until_ms=1_800_000_100_000,
                projection_version=1,
            ),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)


def trade_item_facts(**overrides: Any) -> TradeItemFacts:
    facts = TradeItemFacts(
        ticket_id="ticket:1",
        strategy_group_id="strategy-group:opening-range",
        event_spec_id="event:opening-range-breakout",
        exchange_instrument_id="BTCUSDT",
        position_side="long",
        ticket_status="terminal",
        aggregate_status="terminal",
        issued_at_ms=1_799_999_900_000,
        terminal_at_ms=1_800_000_000_000,
        aggregate_review_id="review:1",
        review_id="review:1",
        review_ticket_id="ticket:1",
        review_revision=1,
        review_created_at_ms=1_800_000_000_000,
        review_metrics={
            "economics_completeness": "complete",
            "gross_realized_pnl_quote": "4.0000",
            "trading_fees_quote": "0.4000",
            "funding_quote": "-0.0900",
            "net_pnl_quote": "3.5100",
            "planned_r_multiple": "0.4800",
        },
        exit_reason="TP1 + Runner Exit",
        open_incident_id=None,
        open_incident_opened_at_ms=None,
        latest_incident_id=None,
        latest_incident_opened_at_ms=None,
        evidence=(
            _evidence("ticket", "ticket:1", 1_799_999_900_000),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)


def trade_causality_facts(**overrides: Any) -> TradeCausalityFacts:
    stage_evidence = (_evidence("event", "event:entry", 1_799_999_920_000),)
    facts = TradeCausalityFacts(
        trade=trade_item_facts(),
        current_stage="review",
        stages=(
            LifecycleStageView(
                key="entry",
                label="入场",
                status="complete",
                started_at_ms=1_799_999_920_000,
                completed_at_ms=1_799_999_930_000,
                duration_ms=10_000,
                summary="ENTRY 已成交",
                evidence=stage_evidence,
            ),
        ),
        annotations=(
            ChartAnnotation(
                kind="entry",
                occurred_at_ms=1_799_999_925_000,
                price=Decimal("100.10"),
                label="ENTRY",
                evidence=stage_evidence,
            ),
        ),
        signal_evidence=(
            _evidence("signal", "signal:1", 1_799_999_800_000),
        ),
        order_evidence=(
            _evidence("command", "command:entry:1", 1_799_999_920_000),
        ),
        incident_evidence=(),
        event_evidence=stage_evidence,
        settlement_evidence=(
            _evidence("settlement", "settlement:1", 1_799_999_990_000),
        ),
        review_evidence=(
            _evidence("review", "review:1", 1_800_000_000_000),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)


def programmatic_review_facts(**overrides: Any) -> ProgrammaticReviewFacts:
    facts = ProgrammaticReviewFacts(
        ticket_id="ticket:1",
        ticket_status="terminal",
        settlement_completed=True,
        current_review_id="review:1",
        entry_complete=True,
        protection_complete=True,
        exit_complete=True,
        reconciliation_complete=True,
        review_complete=True,
        incident_ids=(),
        recovered_incident_ids=(),
        economics_completeness="complete",
        gross_pnl=MoneyMetric(value=Decimal("4.0000"), unit="USDT"),
        fees=MoneyMetric(value=Decimal("0.4000"), unit="USDT"),
        funding=MoneyMetric(value=Decimal("-0.0900"), unit="USDT"),
        net_pnl=MoneyMetric(value=Decimal("3.5100"), unit="USDT"),
        net_r=MoneyMetric(value=Decimal("0.4800"), unit="R"),
        frozen_initial_stop_risk=MoneyMetric(value=Decimal("7.3125"), unit="USDT"),
        actual_stop_risk=MoneyMetric(value=Decimal("7.3125"), unit="USDT"),
        exit_reason="TP1 + Runner Exit",
        runner_net_contribution=MoneyMetric(value=Decimal("1.1000"), unit="USDT"),
        evidence=(
            _evidence("ticket", "ticket:1", 1_799_999_900_000),
            _evidence("settlement", "settlement:1", 1_799_999_990_000),
            _evidence("review", "review:1", 1_800_000_000_000),
        ),
    )
    return _copy_with_named_overrides(facts, overrides)
