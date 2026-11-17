from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.exit_execution import EntryFill
from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def proof(**changes):
    a = position_protected_aggregate()
    return OwnerReductionProof(
        source_stage="pre_tp",
        source_tp_filled_quantity=D(0),
        operation_id="op-1",
        ticket_id=a.identity.ticket_id,
        domain=a.identity.netting_domain,
        authorization_id="auth-1",
        command_id="cmd-1",
        exchange_order_id="venue-1",
        venue_client_order_id="client-1",
        order_status="FILLED",
        requested_quantity=D(".0005"),
        executed_quantity=D(".0005"),
        source_quantity=D(".001"),
        remaining_quantity=D(".0005"),
        fills=(EntryFill(trade_id="trade-1", quantity=D(".0005"), price=D(60000)),),
        original_tp_order_id="tp-1",
        original_tp_cancelled=True,
        original_tp_filled_quantity=D(0),
        protection_order_id="stop-remaining",
        protection_price=D(59000),
        protected_quantity=D(".0005"),
        observed_at_ms=5000,
        valid_until_ms=35000,
        **changes,
    )


def test_verified_reduction_is_exact_and_hashable():
    p = proof()
    assert p.average_price == 60000 and p.digest().startswith("sha256:")


@pytest.mark.parametrize(
    "field,value",
    [
        ("remaining_quantity", D(".0004")),
        ("protected_quantity", D(".001")),
        ("original_tp_cancelled", False),
        ("original_tp_filled_quantity", D(".0001")),
        ("executed_quantity", D(".001")),
    ],
)
def test_quantity_or_unretired_tp_facts_never_prove_continuation(field, value):
    p = proof().model_dump()
    p[field] = value
    with pytest.raises(ValidationError):
        OwnerReductionProof.model_validate(p)


def test_duplicate_fill_ids_cannot_account_for_quantity_twice():
    p = proof().model_dump()
    p["fills"] = [p["fills"][0], p["fills"][0]]
    with pytest.raises(ValidationError):
        OwnerReductionProof.model_validate(p)


@pytest.mark.parametrize("stage,tp_qty", [("runner", D(".0001")), ("wait_price", D(0))])
def test_reduction_proof_accepts_existing_tp_history_without_repeated_cancel(
    stage, tp_qty
):
    values = proof().model_dump()
    values.update(
        source_stage=stage,
        source_tp_filled_quantity=tp_qty,
        original_tp_order_id=None,
        original_tp_cancelled=False,
        original_tp_filled_quantity=tp_qty,
    )
    result = OwnerReductionProof.model_validate(values)
    assert result.original_tp_filled_quantity == tp_qty


def test_reduction_proof_does_not_erase_tp_history_or_invent_retired_stop():
    values = proof().model_dump()
    values.update(
        source_stage="runner",
        source_tp_filled_quantity=D(".0001"),
        original_tp_order_id=None,
        original_tp_cancelled=False,
        original_tp_filled_quantity=D(0),
    )
    with pytest.raises(ValidationError):
        OwnerReductionProof.model_validate(values)
