from __future__ import annotations

import pytest

from src.trading_kernel.application.owner_console.causality import (
    ContradictoryFacts,
    build_trade_causality,
)
from src.trading_kernel.application.owner_console.models import (
    TradeCausalityFacts,
)
from tests.trading_kernel.unit.owner_console.factories import (
    trade_causality_facts,
)


def test_causality_has_eight_business_stages_and_ordered_raw_evidence() -> None:
    detail = build_trade_causality(
        trade_causality_facts(
            event_types=(
                "TicketIssued",
                "EntryFilled",
                "InitialStopConfirmed",
                "TakeProfitFilled",
                "ExitRequested",
                "PositionFlatConfirmed",
                "BudgetSettled",
                "ReviewRecorded",
            )
        )
    )

    assert [stage.key for stage in detail.stages] == [
        "signal",
        "admission",
        "entry",
        "protection",
        "tp_runner",
        "exit",
        "reconciliation",
        "review",
    ]
    assert [event.sequence for event in detail.raw_events] == sorted(
        event.sequence for event in detail.raw_events
    )


def test_exit_reason_comes_from_exit_event_not_candle_shape() -> None:
    detail = build_trade_causality(
        trade_causality_facts(
            exit_requested_reason="initial_stop_triggered",
            candle_pattern_hint="failed_breakout",
        )
    )

    assert detail.exit_reason is not None
    assert detail.exit_reason.label == "Initial Stop"
    assert all(ref.kind == "event" for ref in detail.exit_reason.evidence)


def test_unknown_persisted_event_remains_visible_at_aggregate_fallback() -> None:
    detail = build_trade_causality(
        trade_causality_facts(
            event_types=("TicketIssued", "FutureLifecycleEvent"),
            aggregate_status="runner_protected",
            ticket_status="issued",
            terminal_at_ms=None,
            review=None,
        )
    )

    assert [(event.event_type, event.classification, event.stage) for event in detail.raw_events] == [
        ("TicketIssued", "mapped", "entry"),
        ("FutureLifecycleEvent", "unmapped", "tp_runner"),
    ]


def test_chart_annotations_use_only_exact_authoritative_prices() -> None:
    detail = build_trade_causality(trade_causality_facts())

    document = detail.model_dump(mode="json")
    assert [(item["kind"], item["price"]) for item in document["annotations"]] == [
        ("signal", "100.00"),
        ("stop", "99.00"),
        ("entry", "100.10"),
        ("stop", "99.00"),
        ("take_profit", "102.00"),
        ("stop", "100.20"),
        ("exit", "103.00"),
    ]
    assert all(item.evidence for item in detail.annotations)
    assert detail.annotations[-1].evidence[0].kind == "review"


def test_causality_rejects_event_payload_identity_disagreement() -> None:
    facts = trade_causality_facts()
    entry = facts.events[1]
    events = (
        facts.events[0],
        entry.model_copy(
            update={
                "payload": {
                    **entry.payload,
                    "ticket_id": "ticket:other",
                }
            }
        ),
        *facts.events[2:],
    )

    with pytest.raises(ContradictoryFacts, match="Event payload identity"):
        build_trade_causality(facts.model_copy(update={"events": events}))


@pytest.mark.parametrize(
    ("fact_name", "message"),
    (
        ("aggregate", "Ticket and Aggregate identity mismatch"),
        ("signal", "Ticket and Signal identity mismatch"),
        ("admission", "Ticket and AdmissionDecision identity mismatch"),
        ("review", "current Review identity mismatch"),
    ),
)
def test_causality_identity_matrix_fails_closed(
    fact_name: str,
    message: str,
) -> None:
    facts = trade_causality_facts()
    replacements = {
        "aggregate": facts.aggregate.model_copy(
            update={"ticket_id": "ticket:other"}
        ),
        "signal": facts.signal.model_copy(
            update={"signal_event_id": "signal:other"}
        ),
        "admission": facts.admission.model_copy(
            update={"ticket_id": "ticket:other"}
        ),
        "review": facts.review.model_copy(
            update={"ticket_id": "ticket:other"}
        ),
    }

    with pytest.raises(ContradictoryFacts, match=message):
        build_trade_causality(
            facts.model_copy(update={fact_name: replacements[fact_name]})
        )


def test_causality_fact_boundary_rejects_candles_and_history_over_caps() -> None:
    facts = trade_causality_facts()
    with pytest.raises(ValueError):
        TradeCausalityFacts.model_validate(
            {**facts.model_dump(mode="python"), "candles": ()}
        )

    repeated = tuple(
        facts.events[0].model_copy(
            update={
                "event_id": f"event:cap:{sequence}",
                "sequence": sequence,
                "occurred_at_ms": 1_800_000_000_000 + sequence,
                "payload": {
                    **facts.events[0].payload,
                    "event_id": f"event:cap:{sequence}",
                    "sequence": sequence,
                    "occurred_at_ms": 1_800_000_000_000 + sequence,
                },
            }
        )
        for sequence in range(1, 514)
    )
    with pytest.raises(ValueError):
        facts.model_copy(update={"events": repeated}).model_validate(
            facts.model_copy(update={"events": repeated}).model_dump(mode="python")
        )

    commands = tuple(
        facts.commands[0].model_copy(
            update={
                "command_id": f"command:cap:{generation}",
                "generation": generation,
                "created_at_ms": 1_800_000_000_000 + generation,
            }
        )
        for generation in range(1, 130)
    )
    with pytest.raises(ValueError):
        TradeCausalityFacts.model_validate(
            facts.model_copy(update={"commands": commands}).model_dump(
                mode="python"
            )
        )

    incident = {
        "incident_id": "incident:cap:1",
        "ticket_id": "ticket:1",
        "incident_kind": "test",
        "status": "resolved",
        "first_blocker": "test",
        "details": {},
        "opened_at_ms": 1_800_000_000_001,
        "resolved_at_ms": 1_800_000_000_002,
    }
    incidents = tuple(
        {**incident, "incident_id": f"incident:cap:{index}"}
        for index in range(1, 66)
    )
    with pytest.raises(ValueError):
        TradeCausalityFacts.model_validate(
            {**facts.model_dump(mode="python"), "incidents": incidents}
        )
