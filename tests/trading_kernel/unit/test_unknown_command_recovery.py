from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryStatus,
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
    decide_unknown_recovery,
)
from tests.trading_kernel.integration.test_issue_ticket import _issue_request
from tests.trading_kernel.unit.test_ticket import _ticket


def test_visible_matching_order_resolves_unknown_as_submitted() -> None:
    command = _entry_command()
    result = decide_unknown_recovery(
        command,
        _truth(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id="venue-entry-1",
                venue_client_order_id=command.venue_client_order_id,
                exchange_instrument_id=(
                    command.ticket_identity.netting_domain.exchange_instrument_id
                ),
                position_side="long",
                order_side="buy",
                quantity=command.payload.quantity,
                reduce_only=False,
            ),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED
    assert result.exchange_order_id == "venue-entry-1"


def test_identity_contradiction_opens_hard_incident() -> None:
    command = _entry_command()
    result = decide_unknown_recovery(
        command,
        _truth(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id="venue-entry-wrong",
                venue_client_order_id=command.venue_client_order_id,
                exchange_instrument_id=(
                    command.ticket_identity.netting_domain.exchange_instrument_id
                ),
                position_side="short",
                order_side="sell",
                quantity=command.payload.quantity,
                reduce_only=False,
            ),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.IDENTITY_CONTRADICTION
    assert result.reason == "position_side_mismatch"


def test_absence_waits_for_visibility_then_becomes_authoritative() -> None:
    command = _entry_command()

    pending = decide_unknown_recovery(
        command,
        _truth(lookup_status=VenueLookupStatus.ABSENT, observed_at_ms=1_500),
        visibility_deadline_ms=2_000,
    )
    absent = decide_unknown_recovery(
        command,
        _truth(lookup_status=VenueLookupStatus.ABSENT, observed_at_ms=2_000),
        visibility_deadline_ms=2_000,
    )

    assert pending.status is UnknownRecoveryStatus.PENDING_VISIBILITY
    assert absent.status is UnknownRecoveryStatus.RECONCILED_ABSENT


def test_absent_lookup_with_position_or_fill_evidence_never_claims_absence() -> None:
    command = _entry_command()
    result = decide_unknown_recovery(
        command,
        _truth(
            lookup_status=VenueLookupStatus.ABSENT,
            observed_at_ms=2_500,
            position_quantity=Decimal("0.001"),
            matching_fill_quantity=Decimal("0.001"),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.PENDING_VISIBILITY
    assert result.reason == "submission_evidence_without_order_identity"


def test_lookup_failure_remains_unknown() -> None:
    result = decide_unknown_recovery(
        _entry_command(),
        _truth(
            lookup_status=VenueLookupStatus.LOOKUP_FAILED,
            reason="venue_timeout",
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.LOOKUP_FAILED
    assert result.reason == "venue_timeout"


def test_visible_cancel_target_remains_pending_instead_of_claiming_cancel_success() -> None:
    command = _cancel_command()
    result = decide_unknown_recovery(
        command,
        _truth(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id=command.payload.exchange_order_id,
                venue_client_order_id="brc-original-stop",
                exchange_instrument_id=(
                    command.ticket_identity.netting_domain.exchange_instrument_id
                ),
                position_side="long",
                order_side="sell",
                quantity=Decimal("0.001"),
                reduce_only=True,
            ),
            observed_at_ms=2_500,
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.PENDING_VISIBILITY
    assert result.reason == "cancel_target_still_visible"


def test_cancel_target_absence_is_authoritative_even_while_position_exists() -> None:
    result = decide_unknown_recovery(
        _cancel_command(),
        _truth(
            lookup_status=VenueLookupStatus.ABSENT,
            observed_at_ms=2_500,
            position_quantity=Decimal("0.001"),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT


def test_visible_wrong_cancel_target_is_identity_contradiction() -> None:
    command = _cancel_command()
    result = decide_unknown_recovery(
        command,
        _truth(
            lookup_status=VenueLookupStatus.VISIBLE,
            order=VenueOrderTruth(
                exchange_order_id="wrong-target-order",
                venue_client_order_id="brc-original-stop",
                exchange_instrument_id=(
                    command.ticket_identity.netting_domain.exchange_instrument_id
                ),
                position_side="long",
                order_side="sell",
                quantity=Decimal("0.001"),
                reduce_only=True,
            ),
            observed_at_ms=2_500,
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.IDENTITY_CONTRADICTION
    assert result.reason == "cancel_target_order_id_mismatch"


def test_initial_stop_absence_is_not_hidden_by_open_position_quantity() -> None:
    result = decide_unknown_recovery(
        _reduce_only_command(ExchangeCommandKind.INITIAL_STOP),
        _truth(
            lookup_status=VenueLookupStatus.ABSENT,
            observed_at_ms=2_500,
            position_quantity=Decimal("0.001"),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT


def test_exit_absence_is_not_hidden_by_still_open_position_quantity() -> None:
    result = decide_unknown_recovery(
        _reduce_only_command(ExchangeCommandKind.EXIT),
        _truth(
            lookup_status=VenueLookupStatus.ABSENT,
            observed_at_ms=2_500,
            position_quantity=Decimal("0.001"),
        ),
        visibility_deadline_ms=2_000,
    )

    assert result.status is UnknownRecoveryStatus.RECONCILED_ABSENT


def _entry_command():
    claim = _issue_request(
        ticket=_ticket(),
        now_ms=1_001,
        claim_owner="unit-test",
    ).capacity_claim
    ticket = claim.to_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side="buy",
            quantity=ticket.quantity,
            order_type="market",
            reduce_only=False,
            required_configured_leverage=ticket.selected_leverage,
            leverage_verification_digest=ticket.decision_digest(),
        ),
        status="outcome_unknown",
        created_at_ms=1_001,
        deadline_at_ms=31_000,
    )


def _cancel_command() -> ExchangeCommand:
    ticket = _issue_request(
        ticket=_ticket(),
        now_ms=1_001,
        claim_owner="unit-test",
    ).capacity_claim.to_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=CancelCommandPayload(exchange_order_id="venue-stop-1"),
        status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
        created_at_ms=1_001,
        deadline_at_ms=31_000,
    )


def _reduce_only_command(kind: ExchangeCommandKind) -> ExchangeCommand:
    ticket = _issue_request(
        ticket=_ticket(),
        now_ms=1_001,
        claim_owner="unit-test",
    ).capacity_claim.to_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=kind,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=kind,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side="sell",
            quantity=ticket.quantity,
            order_type="stop_market" if kind is ExchangeCommandKind.INITIAL_STOP else "market",
            reduce_only=True,
            stop_price=(
                ticket.initial_stop_price
                if kind is ExchangeCommandKind.INITIAL_STOP
                else None
            ),
        ),
        status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
        created_at_ms=1_001,
        deadline_at_ms=31_000,
    )


def _truth(
    *,
    lookup_status: VenueLookupStatus,
    order: VenueOrderTruth | None = None,
    observed_at_ms: int = 1_500,
    position_quantity: Decimal = Decimal("0"),
    matching_fill_quantity: Decimal = Decimal("0"),
    reason: str | None = None,
) -> VenueTruthSnapshot:
    return VenueTruthSnapshot(
        lookup_status=lookup_status,
        order=order,
        position_quantity=position_quantity,
        matching_fill_quantity=matching_fill_quantity,
        regular_open_client_order_ids=(),
        conditional_open_client_order_ids=(),
        observed_at_ms=observed_at_ms,
        reason=reason,
    )
