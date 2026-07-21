from decimal import Decimal

import pytest

from src.domain.entry_effect import (
    EntryEffectState,
    ProtectionBarrierState,
    classify_entry_effect,
)


@pytest.mark.parametrize(
    ("command_state", "result_complete", "qty", "price", "effect", "barrier"),
    [
        (
            "confirmed_submitted",
            True,
            Decimal("0.25"),
            Decimal("2000"),
            EntryEffectState.ACCEPTED_FILLED,
            ProtectionBarrierState.INITIAL_STOP_PENDING,
        ),
        (
            "confirmed_submitted",
            True,
            Decimal("0"),
            None,
            EntryEffectState.ACCEPTED_ZERO_FILL,
            ProtectionBarrierState.FILL_PENDING,
        ),
        (
            "confirmed_submitted",
            False,
            None,
            None,
            EntryEffectState.OUTCOME_UNKNOWN,
            ProtectionBarrierState.HARD_STOPPED,
        ),
        (
            "outcome_unknown",
            False,
            None,
            None,
            EntryEffectState.OUTCOME_UNKNOWN,
            ProtectionBarrierState.HARD_STOPPED,
        ),
        (
            "confirmed_rejected",
            False,
            None,
            None,
            EntryEffectState.REJECTED,
            ProtectionBarrierState.NOT_STARTED,
        ),
    ],
)
def test_entry_effect_classification_is_typed_and_deterministic(
    command_state,
    result_complete,
    qty,
    price,
    effect,
    barrier,
):
    decision = classify_entry_effect(
        command_state=command_state,
        result_facts_complete=result_complete,
        executed_qty=qty,
        average_exec_price=price,
    )

    assert decision.entry_effect_state is effect
    assert decision.protection_barrier_state is barrier
    assert decision.protection_quantity == (
        qty if effect is EntryEffectState.ACCEPTED_FILLED else None
    )


def test_non_entry_is_not_classified_as_entry_effect():
    assert classify_entry_effect(
        command_state="confirmed_submitted",
        result_facts_complete=True,
        executed_qty=Decimal("1"),
        average_exec_price=Decimal("1"),
        order_role="SL",
    ) is None
