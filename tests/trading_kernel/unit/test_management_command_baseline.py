from decimal import Decimal

from src.trading_kernel.application.management_intents import system_intents_for
from src.trading_kernel.domain.trade_management import (
    OrderAction,
    OrderEvidence,
    OrderTerms,
    classify_order_evidence,
)


def terms(**changes):
    return OrderTerms.model_validate(
        dict(
            venue_id="binance-usdm",
            account_id="account",
            exchange_instrument_id="binance-usdm:BNBUSDT:perpetual",
            position_side="short",
            order_namespace="conditional",
            exchange_order_id="11",
            client_order_id="brc-exact",
            side="buy",
            order_type="STOP_MARKET",
            quantity="2",
            price=None,
            trigger_price="700",
            close_position=False,
            reduce_only=True,
            time_in_force="GTC",
            working_type="CONTRACT_PRICE",
            price_protect=False,
            activation_price=None,
            callback_rate=None,
            price_match="NONE",
            self_trade_prevention_mode="EXPIRE_MAKER",
            good_till_date_ms=0,
            **changes,
        )
    )


def row():
    return {
        "command_id": "command",
        "command_kind": "initial_stop",
        "status": "accepted",
        "venue_client_order_id": "brc-exact",
        "created_at_ms": 1000,
        "completed_at_ms": 1100,
        "request_payload": {
            "side": "buy",
            "quantity": "2",
            "order_type": "stop_market",
            "stop_price": "700",
            "limit_price": None,
            "time_in_force": None,
            "reduce_only": True,
        },
        "result_payload": {"exchange_order_id": "11"},
    }


def test_confirmed_creation_uses_effective_exchange_terms_without_false_takeover():
    event = OrderEvidence(
        evidence_id="own-new",
        terms=terms(),
        action=OrderAction.NEW,
        exchange_event_at_ms=1050,
        received_at_ms=1200,
        created_at_ms=1050,
        executed_quantity=Decimal(0),
        coverage_complete=True,
        known_command_outcome_pending=False,
    )
    intents = system_intents_for(event, [row()])
    assert (
        classify_order_evidence(event, system_intents=intents).decision.value
        == "system"
    )


def test_modified_first_observation_cannot_become_baseline():
    base = terms()
    event = OrderEvidence(
        evidence_id="later-change",
        terms=base.model_copy(update={"trigger_price": Decimal(701)}),
        action=OrderAction.AMENDMENT,
        exchange_event_at_ms=2000,
        received_at_ms=2100,
        created_at_ms=1050,
        executed_quantity=Decimal(0),
        coverage_complete=True,
        known_command_outcome_pending=False,
        before_terms=base,
    )
    # Absence of an original baseline is UNKNOWN, not proof that an amended
    # observation is itself system-created or externally attributable.
    assert not system_intents_for(event, [row()])


def test_confirmed_baseline_detects_later_exact_order_amendment():
    command = row()
    command["result_payload"]["management_baseline"] = terms().model_dump(mode="json")
    event = OrderEvidence(
        evidence_id="amend",
        terms=terms().model_copy(update={"trigger_price": Decimal(701)}),
        action=OrderAction.AMENDMENT,
        exchange_event_at_ms=2000,
        received_at_ms=2100,
        created_at_ms=1050,
        executed_quantity=Decimal(0),
        coverage_complete=True,
        known_command_outcome_pending=False,
        before_terms=terms(),
    )
    assert (
        classify_order_evidence(
            event, system_intents=system_intents_for(event, [command])
        ).decision.value
        == "external"
    )


def test_algo_creation_without_order_create_time_is_bound_to_exact_acceptance_window():
    event = OrderEvidence(
        evidence_id="algo-new",
        terms=terms(),
        action=OrderAction.NEW,
        exchange_event_at_ms=1050,
        received_at_ms=1200,
        created_at_ms=None,
        executed_quantity=Decimal(0),
        coverage_complete=True,
        known_command_outcome_pending=False,
    )
    assert (
        classify_order_evidence(
            event, system_intents=system_intents_for(event, [row()])
        ).decision.value
        == "system"
    )
