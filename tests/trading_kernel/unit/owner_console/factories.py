"""Named, complete Owner Console facts for unit tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypeVar, cast

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    Freshness,
    MoneyMetric,
    OverviewFacts,
    ProgrammaticReviewFacts,
    SignalDetailFacts,
    SignalFactSnapshotFacts,
    SignalItemFacts,
    TradeCausalityAdmissionFacts,
    TradeCausalityAggregateFacts,
    TradeCausalityCommandFacts,
    TradeCausalityEventFacts,
    TradeCausalityFacts,
    TradeCausalityReviewFacts,
    TradeCausalitySignalFacts,
    TradeItemFacts,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.ticket import TicketStatus, TradeTicket

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
        exit_event_id=None,
        exit_event_type=None,
        exit_event_payload=None,
        exit_event_occurred_at_ms=None,
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
    event_types = tuple(
        overrides.pop(
            "event_types",
            (
                "TicketIssued",
                "EntryFilled",
                "InitialStopConfirmed",
                "TakeProfitFilled",
                "ProtectionReplacementConfirmed",
                "ExitRequested",
                "PositionFlatConfirmed",
                "BudgetSettled",
                "ReviewRecorded",
            ),
        )
    )
    exit_requested_reason = str(
        overrides.pop("exit_requested_reason", "initial_stop_triggered")
    )
    # Accepted only by this test factory to prove it never crosses the facts
    # boundary into build_trade_causality.
    overrides.pop("candle_pattern_hint", None)
    aggregate_status = str(overrides.pop("aggregate_status", "terminal"))
    ticket_status = str(overrides.pop("ticket_status", "terminal"))
    terminal_at_ms = overrides.pop("terminal_at_ms", 1_800_000_000_000)
    review_override = overrides.pop("review", "default")
    ticket = _causality_trade_ticket().model_copy(
        update={"status": TicketStatus(ticket_status)}
    )
    events = tuple(
        _causality_event(
            event_type,
            sequence=sequence,
            exit_requested_reason=exit_requested_reason,
            ticket=ticket,
        )
        for sequence, event_type in enumerate(event_types, start=1)
    )
    review_metrics = {
        "economics_completeness": "complete",
        "gross_realized_pnl_quote": "4.0000",
        "trading_fees_quote": "0.4000",
        "funding_quote": "-0.0900",
        "net_pnl_quote": "3.5100",
        "planned_r_multiple": "0.4800",
        "order_attribution": [
            {
                "exchange_trade_id": "trade:exit:1",
                "exchange_order_id": "exchange:exit:1",
                "command_id": "command:exit:1",
                "role": "exit",
                "quantity": "1",
                "price": "103.00",
                "fee": {},
                "realized_pnl_quote": "3.00",
                "occurred_at_ms": 1_799_999_990_000,
            }
        ],
    }
    review = (
        TradeCausalityReviewFacts(
            review_id="review:1",
            ticket_id="ticket:1",
            revision=1,
            metrics=review_metrics,
            created_at_ms=1_800_000_000_000,
        )
        if review_override == "default"
        else review_override
    )
    trade_review_values = (
        {
            "aggregate_review_id": None,
            "review_id": None,
            "review_ticket_id": None,
            "review_revision": None,
            "review_created_at_ms": None,
            "review_metrics": None,
        }
        if review is None
        else {
            "aggregate_review_id": review.review_id,
            "review_id": review.review_id,
            "review_ticket_id": review.ticket_id,
            "review_revision": review.revision,
            "review_created_at_ms": review.created_at_ms,
            "review_metrics": review.metrics,
        }
    )
    exit_event = next(
        (event for event in events if event.event_type == "ExitRequested"),
        None,
    )
    facts = TradeCausalityFacts(
        trade=trade_item_facts(
            strategy_group_id="CPM-RO-001",
            event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v3",
            ticket_status=ticket_status,
            aggregate_status=aggregate_status,
            terminal_at_ms=terminal_at_ms,
            exit_event_id=(None if exit_event is None else exit_event.event_id),
            exit_event_type=(None if exit_event is None else exit_event.event_type),
            exit_event_payload=(None if exit_event is None else exit_event.payload),
            exit_event_occurred_at_ms=(
                None if exit_event is None else exit_event.occurred_at_ms
            ),
            **trade_review_values,
        ),
        ticket=ticket,
        aggregate=TradeCausalityAggregateFacts(
            ticket_id="ticket:1",
            aggregate_status=aggregate_status,
            last_event_sequence=len(events),
            review_id=None if review is None else review.review_id,
            position_qty=Decimal("0.5"),
            average_fill_price=Decimal("100.10"),
            active_stop_price=Decimal("100.20"),
            tp1_target_qty=Decimal("0.5"),
            tp1_filled_qty=Decimal("0.5"),
            updated_at_ms=1_800_000_000_000,
        ),
        signal=TradeCausalitySignalFacts(
            signal_event_id="signal:1",
            exposure_episode_id="episode:1",
            runtime_scope_id="scope:1",
            runtime_scope_version=1,
            strategy_group_id="CPM-RO-001",
            strategy_version_id="sgv:CPM-RO-001:v3",
            event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v3",
            universe_version_id="universe:1",
            universe_semantic_digest="sha256:" + "a" * 64,
            exchange_instrument_id="BTCUSDT",
            position_side="long",
            occurred_at_ms=1_799_999_800_000,
        ),
        admission=TradeCausalityAdmissionFacts(
            admission_decision_id="admission:1",
            signal_event_id="signal:1",
            exposure_episode_id="episode:1",
            strategy_group_id="CPM-RO-001",
            strategy_version_id="sgv:CPM-RO-001:v3",
            event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v3",
            universe_version_id="universe:1",
            universe_semantic_digest="sha256:" + "a" * 64,
            runtime_profile_id="profile:1",
            runtime_scope_id="scope:1",
            runtime_scope_version=1,
            owner_policy_id="policy:1",
            owner_policy_version=1,
            venue_id="binance-usdm",
            account_id="account:1",
            exchange_instrument_id="BTCUSDT",
            position_side="long",
            decision_status="admitted",
            capacity_claim_id="claim:1",
            ticket_id="ticket:1",
            decided_at_ms=1_799_999_900_000,
        ),
        events=events,
        commands=(
            TradeCausalityCommandFacts(
                command_id="command:entry:1",
                ticket_id="ticket:1",
                command_kind="entry",
                generation=1,
                status="accepted",
                request_payload={"quantity": "1"},
                result_payload={"exchange_order_id": "exchange:entry:1"},
                created_at_ms=1_799_999_910_000,
                completed_at_ms=1_799_999_920_000,
            ),
            TradeCausalityCommandFacts(
                command_id="command:exit:1",
                ticket_id="ticket:1",
                command_kind="exit",
                generation=1,
                status="accepted",
                request_payload={"quantity": "1"},
                result_payload={"exchange_order_id": "exchange:exit:1"},
                created_at_ms=1_799_999_980_000,
                completed_at_ms=1_799_999_990_000,
            ),
        ),
        incidents=(),
        review=review,
    )
    return _copy_with_named_overrides(facts, overrides)


def _causality_event(
    event_type: str,
    *,
    sequence: int,
    exit_requested_reason: str,
    ticket: TradeTicket,
) -> TradeCausalityEventFacts:
    event_id = f"event:1:{sequence}"
    occurred_at_ms = 1_799_999_900_000 + sequence * 10_000
    payload: dict[str, Any] = {
        "event_id": event_id,
        "sequence": sequence,
        "occurred_at_ms": occurred_at_ms,
    }
    if event_type == "TicketIssued":
        payload = TicketIssued(
            event_id=event_id,
            sequence=sequence,
            occurred_at_ms=occurred_at_ms,
            ticket=ticket,
        ).model_dump(mode="json")
    else:
        payload["ticket_id"] = "ticket:1"
    if event_type == "EntryFilled":
        payload.update(filled_qty="1", average_fill_price="100.10")
    elif event_type == "InitialStopConfirmed":
        payload.update(exchange_order_id="exchange:stop:1", protected_qty="1")
    elif event_type == "TakeProfitFilled":
        payload.update(
            filled_qty="0.5",
            average_fill_price="102.00",
            runner_floor_price="100.20",
        )
    elif event_type == "ProtectionReplacementConfirmed":
        payload.update(
            exchange_order_id="exchange:stop:2",
            protected_qty="0.5",
            stop_price="100.20",
            replaces_exchange_order_id="exchange:stop:1",
            source_watermark_ms=occurred_at_ms,
        )
    elif event_type == "ExitRequested":
        payload["reason"] = exit_requested_reason
    elif event_type == "ReviewRecorded":
        payload["review_id"] = "review:1"
    return TradeCausalityEventFacts(
        event_id=event_id,
        ticket_id="ticket:1",
        sequence=sequence,
        event_type=event_type,
        payload=payload,
        occurred_at_ms=occurred_at_ms,
    )


def _causality_trade_ticket() -> TradeTicket:
    runtime = RuntimeIdentity(
        runtime_profile_id="profile:1",
        strategy_group_id="CPM-RO-001",
        strategy_version_id="sgv:CPM-RO-001:v3",
        event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v3",
    )
    netting_domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="account:1",
        exchange_instrument_id="BTCUSDT",
        position_side="long",
    )
    return TradeTicket(
        identity=TicketIdentity(
            ticket_id="ticket:1",
            exposure_episode_id="episode:1",
            signal_event_id="signal:1",
            runtime=runtime,
            netting_domain=netting_domain,
        ),
        owner_policy_id="policy:1",
        owner_policy_version=1,
        runtime_scope_id="scope:1",
        runtime_scope_version=1,
        universe_version_id="universe:1",
        universe_semantic_digest="sha256:" + "a" * 64,
        fact_digest="sha256:" + "b" * 64,
        exposure_family="opening_range",
        active_family_ticket_count_at_claim=0,
        family_ticket_limit=2,
        directional_risk_at_stop_at_claim=Decimal(0),
        directional_stop_risk_limit_fraction=Decimal("0.04"),
        min_materialization_ratio=Decimal("0.50"),
        minimum_stop_risk_budget=Decimal(1),
        exit_policy_id="exit-policy:1",
        exit_policy_semantic_hash="sha256:" + "c" * 64,
        capacity_claim_id="claim:1",
        created_at_ms=1_799_999_900_000,
        expires_at_ms=1_800_000_100_000,
        entry_reference_price=Decimal("100.00"),
        quantity=Decimal(1),
        notional=Decimal(100),
        planned_stop_risk_budget=Decimal(1),
        post_fill_stop_risk_limit=Decimal("1.1"),
        selected_leverage=1,
        leverage_change_required=False,
        reserved_margin=Decimal(100),
        risk_reservation_basis="stop_risk",
        margin_mode="cross",
        cross_margin_stress_model_id="cross-margin-stop-stress-v1",
        post_stop_stress_multiple=Decimal(2),
        claim_stress_proof_digest="sha256:" + "d" * 64,
        risk_at_stop=Decimal(1),
        entry_order_type="market",
        entry_limit_price=None,
        initial_stop_price=Decimal("99.00"),
        pre_tp1_reclaim_price=None,
        exposure_session_end_ms=None,
        take_profit_prices=(Decimal("102.00"),),
        take_profit_quantities=(Decimal("0.5"),),
    )


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
