"""Economic windows use verified execution times, not an earlier flat observation."""

from decimal import Decimal

import pytest

from src.trading_kernel.application.review_window import _review_window
from src.trading_kernel.domain.events import (
    EntryFilled,
    EntryPartiallyFilled,
    ExternalFlatDetected,
    PositionFlatConfirmed,
    VerifiedExitClosed,
)
from src.trading_kernel.domain.verified_exit_closure import VerifiedExitClosureProof
from tests.trading_kernel.support.reducer_states import position_protected_aggregate
from tests.trading_kernel.support.verified_closure import proof_payload


@pytest.mark.parametrize('flat_kind', [PositionFlatConfirmed, ExternalFlatDetected])
@pytest.mark.parametrize('proof_first', [False, True])
def test_verified_execution_endpoint_supersedes_an_earlier_flat_observation(flat_kind, proof_first):
    proof = VerifiedExitClosureProof.model_validate(proof_payload())
    entry = EntryPartiallyFilled(event_id='entry', ticket_id=proof.ticket_id,
        sequence=2, occurred_at_ms=2000, filled_qty=proof.entry_quantity,
        requested_qty=proof.entry_quantity * 2, average_fill_price=Decimal(60000))
    flat = flat_kind(event_id='flat', ticket_id=proof.ticket_id,
        sequence=3, occurred_at_ms=2500)
    verified = VerifiedExitClosed(event_id='verified', ticket_id=proof.ticket_id,
        sequence=4, occurred_at_ms=4000, proof=proof)
    events = [entry, verified, flat] if proof_first else [entry, flat, verified]
    window = _review_window(events, exposure_started_at_ms=1000)
    assert window is not None
    assert window.entry_time_ms == 1000
    assert window.exit_time_ms == 3000
    assert window.executed_entry_quantity == proof.entry_quantity
    assert not window.external_flat


def test_without_verified_execution_uses_earliest_flat_and_keeps_missing_economics_boundary():
    entry = EntryPartiallyFilled(event_id='entry', ticket_id='ticket', sequence=2,
        occurred_at_ms=2000, filled_qty=Decimal(1), requested_qty=Decimal(2),
        average_fill_price=Decimal(100))
    flat = ExternalFlatDetected(event_id='flat', ticket_id='ticket', sequence=3,
        occurred_at_ms=3000)
    late = PositionFlatConfirmed(event_id='later', ticket_id='ticket', sequence=4,
        occurred_at_ms=6000)
    window = _review_window([entry, flat, late], exposure_started_at_ms=1000)
    assert window is not None and window.exit_time_ms == 3000 and window.external_flat


@pytest.mark.parametrize('entry_kind', [EntryFilled, EntryPartiallyFilled])
@pytest.mark.parametrize('confirmation_ms', [3500, 4500])
def test_verified_window_accepts_entry_confirmed_after_real_exit(entry_kind, confirmation_ms):
    proof = VerifiedExitClosureProof.model_validate(proof_payload())
    if entry_kind is EntryFilled:
        from src.trading_kernel.domain.post_fill_risk import (
            PostFillRiskRequest,
            assess_post_fill_risk,
        )

        a = position_protected_aggregate()
        fields = {'venue_reported_liquidation_price': None,
            'position_observed_at_ms': confirmation_ms,
            'post_fill_risk': assess_post_fill_risk(PostFillRiskRequest(
                position_side=proof.domain.position_side, filled_quantity=proof.entry_quantity,
                average_fill_price=Decimal(60000), initial_stop_price=a.ticket.initial_stop_price,
                planned_stop_risk_budget=a.ticket.planned_stop_risk_budget,
                post_fill_stop_risk_limit=a.ticket.post_fill_stop_risk_limit))}
    else:
        fields = {'requested_qty': proof.entry_quantity * 2}
    entry = entry_kind(event_id='late-entry', ticket_id=proof.ticket_id,
        sequence=2, occurred_at_ms=confirmation_ms, filled_qty=proof.entry_quantity,
        average_fill_price=Decimal(60000), **fields)
    verified = VerifiedExitClosed(event_id='verified', ticket_id=proof.ticket_id,
        sequence=3, occurred_at_ms=5000, proof=proof)

    window = _review_window([entry, verified], exposure_started_at_ms=1000)
    assert window is not None
    assert window.entry_time_ms == 1000
    assert window.exit_time_ms == 3000
    assert window.executed_entry_quantity == proof.entry_quantity
    assert not window.external_flat


@pytest.mark.parametrize('mismatch', ['entry_ticket', 'entry_quantity'])
def test_delayed_confirmation_does_not_allow_unrelated_verified_proof(mismatch):
    proof = VerifiedExitClosureProof.model_validate(proof_payload())
    entry = EntryPartiallyFilled(event_id='late-entry',
        ticket_id='another-ticket' if mismatch == 'entry_ticket' else proof.ticket_id,
        sequence=2, occurred_at_ms=3500,
        filled_qty=proof.entry_quantity / 2 if mismatch == 'entry_quantity' else proof.entry_quantity,
        requested_qty=proof.entry_quantity * 2, average_fill_price=Decimal(60000))
    verified = VerifiedExitClosed(event_id='verified', ticket_id=proof.ticket_id,
        sequence=3, occurred_at_ms=5000, proof=proof)
    with pytest.raises(ValueError, match='differs from entry lineage'):
        _review_window([entry, verified], exposure_started_at_ms=1000)


def test_actual_fill_reversal_remains_invalid_before_review_window():
    payload = proof_payload()
    payload['entry_fills'][0]['occurred_at_ms'] = 3500
    with pytest.raises(ValueError, match='closure execution chronology differs'):
        VerifiedExitClosureProof.model_validate(payload)
