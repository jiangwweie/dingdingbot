"""Scoped App evidence fixtures shared by management and notification tests."""
from src.trading_kernel.domain.trade_management import OrderEvidence, OrderTerms


def app_order(ticket, **changes):
    d = ticket.identity.netting_domain
    return OrderTerms.model_validate(
        {
            "venue_id": d.venue_id,
            "account_id": d.account_id,
            "exchange_instrument_id": d.exchange_instrument_id,
            "position_side": d.position_side,
            "order_namespace": "regular",
            "exchange_order_id": "app-1",
            "client_order_id": "app-id",
            "side": "sell" if d.position_side == "long" else "buy",
            "order_type": "LIMIT",
            "quantity": "0.001",
            "price": "65000",
            "trigger_price": None,
            "close_position": False,
            "reduce_only": False,
            "time_in_force": "GTC",
            "working_type": "CONTRACT_PRICE",
            "price_protect": False,
            "activation_price": None,
            "callback_rate": None,
            "price_match": "NONE",
            "self_trade_prevention_mode": "NONE",
            "good_till_date_ms": 0,
            **changes,
        }
    )


def app_evidence(ticket, **changes):
    return OrderEvidence(
        evidence_id="external-1",
        terms=app_order(ticket, **changes),
        action="new",
        exchange_event_at_ms=5000,
        received_at_ms=5001,
        created_at_ms=5000,
        executed_quantity="0",
        coverage_complete=True,
        known_command_outcome_pending=False,
    )


