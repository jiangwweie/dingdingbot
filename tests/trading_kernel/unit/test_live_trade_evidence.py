from decimal import Decimal, localcontext

import pytest

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.live_trade_evidence import (
    build_review_execution_evidence,
)
from src.trading_kernel.domain.order_attribution import (
    AttributedTradeFill,
    OrderRole,
    attribution_digest,
)
from tests.trading_kernel.support.tickets import make_ticket


def evidence_inputs():
    ticket=make_ticket()
    commands=tuple(ExchangeCommand(command_id=f"command:{role.value}",ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY if role is OrderRole.ENTRY else ExchangeCommandKind.EXIT,generation=1,
        idempotency_key=f"idem:{role.value}",venue_client_order_id=build_venue_client_order_id(f"command:{role.value}"),
        payload=OrderCommandPayload(side="buy" if role is OrderRole.ENTRY else "sell",quantity=ticket.quantity,
            order_type="market",reduce_only=role is OrderRole.EXIT,
            required_configured_leverage=5 if role is OrderRole.ENTRY else None,
            leverage_verification_digest="sha256:"+"a"*64 if role is OrderRole.ENTRY else None),status=ExchangeCommandStatus.ACCEPTED,
        created_at_ms=1,deadline_at_ms=1000) for role in (OrderRole.ENTRY,OrderRole.EXIT))
    fee=value_native_fee(native_fee=NativeFee(asset="USDT",amount=Decimal("0.01")),
        valuation_evidence=FeeValuationEvidence(method="native_usdt",rate_usdt_per_asset=Decimal(1),price_pair=None,observed_at_ms=None,valued_at_ms=25))
    fills=tuple(AttributedTradeFill(exchange_trade_id=f"trade:{role.value}",exchange_order_id=f"order:{role.value}",
        command_id=f"command:{role.value}",role=role,quantity=ticket.quantity,price=ticket.entry_reference_price+Decimal(1),
        fee=fee,realized_pnl_quote=Decimal(0),occurred_at_ms=10 if role is OrderRole.ENTRY else 20) for role in (OrderRole.ENTRY,OrderRole.EXIT))
    metrics={"order_attribution":[f.model_dump(mode="json") for f in fills],"order_attribution_digest":attribution_digest(fills),"executed_entry_quantity":str(fills[0].quantity)}
    return ticket,commands,fills,metrics


def test_exact_fill_times_not_position_observations_and_fixed_initial_stop():
    ticket,commands,fills,metrics=evidence_inputs()
    evidence=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=ticket.identity.ticket_id,metrics=metrics,commands=commands)
    assert evidence.status=="COMPLETE" and evidence.missing==()
    assert evidence.first_entry_fill_at_ms==10 and evidence.last_exit_fill_at_ms==20
    assert evidence.actual_entry_vwap==fills[0].price
    assert evidence.initial_stop_distance==abs(fills[0].price-ticket.initial_stop_price)
    with localcontext() as context:
        context.prec=5
        repeated=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=ticket.identity.ticket_id,metrics=metrics,commands=commands)
    assert repeated==evidence


def test_short_and_partial_exposure_use_actual_filled_quantity_and_frozen_stop():
    ticket,commands,fills,_=evidence_inputs()
    identity=ticket.identity.model_copy(update={"netting_domain":ticket.identity.netting_domain.model_copy(update={"position_side":"short"})})
    ticket=ticket.model_copy(update={"identity":identity,"initial_stop_price":ticket.entry_reference_price+Decimal(10)})
    commands=tuple(c.model_copy(update={"ticket_identity":identity,"payload":c.payload.model_copy(update={"side":"sell" if c.kind is ExchangeCommandKind.ENTRY else "buy"})}) for c in commands)
    fills=tuple(f.model_copy(update={"quantity":f.quantity/2}) for f in fills)
    metrics={"order_attribution":[f.model_dump(mode="json") for f in fills],"order_attribution_digest":attribution_digest(fills),"executed_entry_quantity":str(fills[0].quantity)}
    evidence=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=ticket.identity.ticket_id,metrics=metrics,commands=commands)
    assert evidence.status=="COMPLETE"
    assert evidence.actual_entry_quantity==ticket.quantity/2
    assert evidence.initial_stop_distance==Decimal(9)


def test_fee_validation_and_digest_are_independent_of_ambient_decimal_precision():
    ticket,commands,fills,_=evidence_inputs()
    fee=value_native_fee(native_fee=NativeFee(asset="USDT",amount=Decimal("0.0000000123456789012345")),
        valuation_evidence=FeeValuationEvidence(method="native_usdt",rate_usdt_per_asset=Decimal(1),price_pair=None,observed_at_ms=None,valued_at_ms=25))
    fills=tuple(f.model_copy(update={"fee":fee}) for f in fills)
    metrics={"order_attribution":[f.model_dump(mode="json") for f in fills],"order_attribution_digest":attribution_digest(fills),"executed_entry_quantity":str(fills[0].quantity)}
    expected=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=ticket.identity.ticket_id,metrics=metrics,commands=commands)
    assert expected.status=="COMPLETE"
    with localcontext() as context:
        context.prec=5
        actual=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=ticket.identity.ticket_id,metrics=metrics,commands=commands)
    assert actual==expected


@pytest.mark.parametrize("defect",["missing_rows","missing_price","wrong_digest","wrong_command","duplicate","exit_before_entry","wrong_quantity","wrong_review","bound","unaccepted_command","wrong_stop_geometry","wrong_command_side","truncated_consistent_fills"])
def test_missing_or_contradictory_fill_evidence_is_explicit_never_guessed(defect):
    ticket,commands,fills,metrics=evidence_inputs()
    review_ticket=ticket.identity.ticket_id
    if defect=="missing_rows":
        metrics={"entry_time_ms":10,"entry_average_price":"123","realized_pnl":"1"}
    elif defect=="missing_price":
        metrics["order_attribution"][0].pop("price")
    elif defect=="wrong_digest":
        metrics["order_attribution_digest"]="sha256:forged"
    elif defect=="wrong_review":
        review_ticket="other-ticket"
    elif defect=="bound":
        metrics["order_attribution"]=metrics["order_attribution"]*501
    elif defect=="unaccepted_command":
        commands=(commands[0].model_copy(update={"status":ExchangeCommandStatus.PREPARED}),commands[1])
    elif defect=="wrong_command_side":
        commands=(commands[0].model_copy(update={"payload":commands[0].payload.model_copy(update={"side":"sell"})}),commands[1])
    else:
        if defect=="wrong_command":
            fills=(fills[0].model_copy(update={"command_id":"command:other"}),fills[1])
        elif defect=="duplicate":
            fills=(*fills,fills[0])
        elif defect=="exit_before_entry":
            fills=(fills[0],fills[1].model_copy(update={"occurred_at_ms":2}))
        elif defect=="wrong_quantity":
            fills=(fills[0],fills[1].model_copy(update={"quantity":fills[1].quantity/2}))
        elif defect=="wrong_stop_geometry":
            fills=(fills[0].model_copy(update={"price":ticket.initial_stop_price-Decimal(1)}),fills[1])
        elif defect=="truncated_consistent_fills":
            fills=tuple(f.model_copy(update={"quantity":f.quantity/2}) for f in fills)
        metrics={"order_attribution":[f.model_dump(mode="json") for f in fills],"order_attribution_digest":attribution_digest(fills),"executed_entry_quantity":str(ticket.quantity)}
        if defect=="truncated_consistent_fills":
            metrics["executed_entry_quantity"]=str(ticket.quantity)
    evidence=build_review_execution_evidence(ticket=ticket,review_id="review:1",review_ticket_id=review_ticket,metrics=metrics,commands=commands)
    assert evidence.status=="EVIDENCE_INCOMPLETE" and evidence.missing
    assert evidence.first_entry_fill_at_ms is None and evidence.actual_entry_vwap is None and evidence.entry_fills==()
