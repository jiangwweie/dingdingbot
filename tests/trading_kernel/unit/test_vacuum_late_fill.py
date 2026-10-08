from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from src.trading_kernel.application.recover_vacuum_late_fill import (
    late_fill_commit_window_open,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.vacuum_late_fill import (
    VacuumLateFillAttributionInput,
    VacuumLateFillAttributionStatus,
    decide_vacuum_late_fill_attribution,
)
from src.trading_kernel.domain.venue_truth import (
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from tests.trading_kernel.support.tickets import make_ticket


def _facts() -> VacuumLateFillAttributionInput:
    ticket = make_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    client_id = build_venue_client_order_id(command_id)
    command = ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=client_id,
        payload=OrderCommandPayload(
            side="buy", quantity=ticket.quantity, order_type="market",
            reduce_only=False, required_configured_leverage=5,
            leverage_verification_digest=ticket.decision_digest(),
        ),
        status=ExchangeCommandStatus.ACCEPTED,
        created_at_ms=1_001,
        deadline_at_ms=31_000,
    )
    position = PositionSnapshot(
        netting_domain=ticket.identity.netting_domain,
        quantity=ticket.quantity,
        average_entry_price=ticket.entry_reference_price,
        observed_at_ms=2_001,
    )
    truth = VenueTruthSnapshot(
        lookup_status=VenueLookupStatus.VISIBLE,
        order=VenueOrderTruth(
            exchange_order_id="venue-entry-1",
            venue_client_order_id=client_id,
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            position_side=ticket.identity.netting_domain.position_side,
            order_side="buy",
            quantity=ticket.quantity,
            reduce_only=False,
            is_open=False,
        ),
        position_quantity=ticket.quantity,
        matching_fill_quantity=ticket.quantity,
        matching_fill_average_price=ticket.entry_reference_price,
        matching_fill_complete=True,
        regular_open_client_order_ids=(),
        conditional_open_client_order_ids=(),
        observed_at_ms=2_002,
    )
    return VacuumLateFillAttributionInput(
        ticket=ticket,
        entry_command=command,
        entry_exchange_order_id="venue-entry-1",
        position=position,
        venue_truth=truth,
        contradiction_observed_at_ms=2_000,
    )


def test_exact_closed_entry_fill_is_attributable_and_deterministic() -> None:
    facts = _facts()
    first = decide_vacuum_late_fill_attribution(facts)
    second = decide_vacuum_late_fill_attribution(facts)

    assert first == second
    assert first.status is VacuumLateFillAttributionStatus.ATTRIBUTED
    assert first.filled_qty == facts.ticket.quantity
    assert first.average_fill_price == facts.ticket.entry_reference_price
    assert first.proof_digest is not None and first.proof_digest.startswith("sha256:")


def test_late_fill_proof_is_independent_of_ambient_decimal_precision() -> None:
    facts = _facts()
    price = Decimal("60000.12345678901234567890123456789")
    facts = facts.model_copy(update={
        "position":facts.position.model_copy(update={"average_entry_price":price}),
        "venue_truth":facts.venue_truth.model_copy(update={"matching_fill_average_price":price}),
    })
    with localcontext() as context:
        context.prec = 6
        low = decide_vacuum_late_fill_attribution(facts)
    with localcontext() as context:
        context.prec = 38
        high = decide_vacuum_late_fill_attribution(facts)
    assert low.proof_digest == high.proof_digest


@pytest.mark.parametrize("elapsed,allowed", [
    (0.0,True),(2.5,True),(3.1,False),(-0.1,False),
])
def test_late_fill_commit_rejects_paused_process_after_readonly_proof(
    elapsed: float, allowed: bool,
) -> None:
    assert late_fill_commit_window_open(
        started_monotonic=10.0,
        current_monotonic=10.0+elapsed,
        timeout_seconds=1.0,
    ) is allowed


def test_exact_closed_order_with_zero_fills_proves_no_exposure() -> None:
    facts = _facts()
    flat = facts.position.model_copy(update={
        "quantity": Decimal(0), "average_entry_price": None,
    })
    truth = facts.venue_truth.model_copy(update={
        "position_quantity": Decimal(0),
        "matching_fill_quantity": Decimal(0),
        "matching_fill_average_price": None,
    })

    decision = decide_vacuum_late_fill_attribution(facts.model_copy(update={
        "position": flat, "venue_truth": truth,
    }))

    assert decision.status is VacuumLateFillAttributionStatus.NO_FILL_VERIFIED
    assert decision.proof_digest is not None
    assert decision.filled_qty is None and decision.average_fill_price is None


@pytest.mark.parametrize("reason", ["unresolved_fill", "open_order", "stale_position"])
def test_no_fill_closure_rejects_incomplete_external_proof(reason: str) -> None:
    facts = _facts()
    position = facts.position.model_copy(update={
        "quantity": Decimal(0), "average_entry_price": None,
    })
    truth = facts.venue_truth.model_copy(update={
        "position_quantity": Decimal(0), "matching_fill_quantity": Decimal(0),
        "matching_fill_average_price": None,
    })
    if reason == "unresolved_fill":
        truth = truth.model_copy(update={"matching_fill_quantity": Decimal("0.001")})
    elif reason == "open_order":
        assert truth.order is not None
        truth = truth.model_copy(update={
            "order": truth.order.model_copy(update={"is_open": True}),
        })
    elif reason == "stale_position":
        position = position.model_copy(update={"observed_at_ms": 2_000})

    decision = decide_vacuum_late_fill_attribution(facts.model_copy(update={
        "position": position, "venue_truth": truth,
    }))

    assert decision.status is VacuumLateFillAttributionStatus.UNVERIFIED
    assert decision.proof_digest is None


@pytest.mark.parametrize("change", [
    "wrong_order", "wrong_client", "open_order", "wrong_side", "wrong_quantity",
    "fill_mismatch", "position_mismatch", "stale_position", "stale_truth",
    "excess_fill", "missing_order", "unknown_entry",
    "missing_fill_price", "fill_price_mismatch", "fill_page_truncated",
])
def test_attribution_fails_closed_on_any_identity_or_source_gap(change: str) -> None:
    facts = _facts()
    command = facts.entry_command
    position = facts.position
    truth = facts.venue_truth
    order = truth.order
    assert order is not None
    if change == "wrong_order":
        truth = truth.model_copy(update={"order": order.model_copy(update={"exchange_order_id": "other"})})
    elif change == "wrong_client":
        truth = truth.model_copy(update={"order": order.model_copy(update={"venue_client_order_id": "other"})})
    elif change == "open_order":
        truth = truth.model_copy(update={"order": order.model_copy(update={"is_open": True})})
    elif change == "wrong_side":
        truth = truth.model_copy(update={"order": order.model_copy(update={"position_side": "short"})})
    elif change == "wrong_quantity":
        truth = truth.model_copy(update={"order": order.model_copy(update={"quantity": Decimal("0.002")})})
    elif change == "fill_mismatch":
        truth = truth.model_copy(update={"matching_fill_quantity": Decimal(0)})
    elif change == "position_mismatch":
        truth = truth.model_copy(update={"position_quantity": Decimal(0)})
    elif change == "stale_position":
        position = position.model_copy(update={"observed_at_ms": 2_000})
    elif change == "stale_truth":
        truth = truth.model_copy(update={"observed_at_ms": 2_000})
    elif change == "excess_fill":
        position = position.model_copy(update={"quantity": Decimal("0.002")})
        truth = truth.model_copy(update={"position_quantity": Decimal("0.002"),
            "matching_fill_quantity": Decimal("0.002")})
    elif change == "missing_order":
        truth = VenueTruthSnapshot(
            lookup_status=VenueLookupStatus.ABSENT, order=None,
            position_quantity=position.quantity,
            matching_fill_quantity=Decimal(0),
            regular_open_client_order_ids=(), conditional_open_client_order_ids=(),
            observed_at_ms=2_002,
        )
    elif change == "unknown_entry":
        command = command.model_copy(update={"status": ExchangeCommandStatus.OUTCOME_UNKNOWN})
    elif change == "missing_fill_price":
        truth = truth.model_copy(update={"matching_fill_average_price": None})
    elif change == "fill_price_mismatch":
        truth = truth.model_copy(update={"matching_fill_average_price": Decimal(99)})
    elif change == "fill_page_truncated":
        truth = truth.model_copy(update={"matching_fill_complete": False})

    result = decide_vacuum_late_fill_attribution(facts.model_copy(update={
        "entry_command": command, "position": position, "venue_truth": truth,
    }))
    assert result.status is VacuumLateFillAttributionStatus.UNVERIFIED
    assert result.proof_digest is None
