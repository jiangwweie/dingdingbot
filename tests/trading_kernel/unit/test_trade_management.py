from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.trade_management import (
    ManagementDecision,
    ManagementMode,
    OrderAction,
    OrderEvidence,
    OrderTerms,
    SystemOrderIntent,
    TradeManagement,
    classify_order_evidence,
    transition_management,
)


def terms(**changes):
    return OrderTerms.model_validate(
        {
            "venue_id": "binance-usdm",
            "account_id": "test",
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "position_side": "long",
            "order_namespace": "regular",
            "exchange_order_id": "1",
            "client_order_id": "brc-one",
            "side": "sell",
            "order_type": "LIMIT",
            "quantity": "1",
            "price": "110",
            "trigger_price": None,
            "close_position": False,
            "reduce_only": False,
            "time_in_force": "GTC",
            "working_type": None,
            "price_protect": False,
            "activation_price": None,
            "callback_rate": None,
            "price_match": "NONE",
            "self_trade_prevention_mode": "NONE",
            "good_till_date_ms": 0,
            **changes,
        }
    )


def evidence(**changes):
    return OrderEvidence.model_validate(
        {
            "evidence_id": "e1",
            "terms": terms(),
            "action": "amendment",
            "exchange_event_at_ms": 2000,
            "received_at_ms": 2001,
            "created_at_ms": 1000,
            "executed_quantity": "0",
            "coverage_complete": True,
            "known_command_outcome_pending": False,
            "before_terms": terms(price="109"),
            **changes,
        }
    )


def test_unfilled_same_id_amendment_is_external():
    result = classify_order_evidence(evidence(), system_intents=())
    assert result.decision is ManagementDecision.EXTERNAL
    assert result.reason == "external_order_amendment"


def test_changed_back_price_does_not_erase_prior_amendment():
    state = TradeManagement(ticket_id="t1")
    state = transition_management(
        state, evidence(), system_intents=(), initial_protection_confirmed=True
    )
    restored = evidence(
        evidence_id="e2",
        terms=terms(price="109"),
        before_terms=terms(),
        exchange_event_at_ms=2002,
        received_at_ms=2003,
    )
    assert (
        transition_management(
            state, restored, system_intents=(), initial_protection_confirmed=True
        )
        == state
    )
    assert state.mode is ManagementMode.MANUAL


@pytest.mark.parametrize("action", ["new", "cancel", "trade"])
def test_external_action_does_not_require_fill(action):
    e = evidence(
        action=action,
        terms=terms(client_order_id="app-one"),
        before_terms=None,
        executed_quantity="0.2" if action == "trade" else "0",
    )
    assert (
        classify_order_evidence(e, system_intents=()).decision
        is ManagementDecision.EXTERNAL
    )


def test_exact_system_create_is_not_takeover():
    e = evidence(action="new", before_terms=None)
    intent = SystemOrderIntent(
        command_id="c1",
        action=OrderAction.NEW,
        terms=e.terms,
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(intent,)).decision
        is ManagementDecision.SYSTEM
    )


def test_system_prefix_alone_does_not_prove_ownership():
    assert (
        classify_order_evidence(
            evidence(action="new", before_terms=None), system_intents=()
        ).decision
        is ManagementDecision.UNRESOLVED
    )


def test_original_system_tp_fill_is_natural():
    e = evidence(action="trade", before_terms=None, executed_quantity="0.2")
    intent = SystemOrderIntent(
        command_id="c1",
        action=OrderAction.NEW,
        terms=e.terms,
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(intent,)).decision
        is ManagementDecision.NATURAL
    )


def test_system_created_order_external_cancel_takes_over():
    e = evidence(action="cancel", before_terms=None)
    create = SystemOrderIntent(
        command_id="c1",
        action=OrderAction.NEW,
        terms=e.terms,
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(create,)).decision
        is ManagementDecision.EXTERNAL
    )


def test_exact_system_cancel_not_takeover():
    e = evidence(action="cancel", before_terms=None)
    cancel = SystemOrderIntent(
        command_id="c1",
        action=OrderAction.CANCEL,
        terms=e.terms,
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(cancel,)).decision
        is ManagementDecision.SYSTEM
    )


@pytest.mark.parametrize("action", ["expired", "triggered", "rejected", "status"])
def test_natural_status_is_not_owner_action(action):
    e = evidence(action=action, before_terms=None)
    intent = SystemOrderIntent(
        command_id="c1",
        action=OrderAction.NEW,
        terms=e.terms,
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(intent,)).decision
        is ManagementDecision.NATURAL
    )


def test_unexplained_order_disappearance_is_not_cancel():
    assert (
        classify_order_evidence(
            evidence(action="missing", before_terms=None), system_intents=()
        ).decision
        is ManagementDecision.UNRESOLVED
    )


@pytest.mark.parametrize(
    "changes", [{"coverage_complete": False}, {"known_command_outcome_pending": True}]
)
def test_incomplete_facts_never_grant_takeover_or_automatic_resume(changes):
    e = evidence(**changes)
    state = transition_management(
        TradeManagement(ticket_id="t"),
        e,
        system_intents=(),
        initial_protection_confirmed=True,
    )
    assert state.mode is ManagementMode.REVIEW_REQUIRED
    assert not state.permits_automatic_mutation


def test_takeover_is_idempotent_and_irreversible():
    state = transition_management(
        TradeManagement(ticket_id="t"),
        evidence(),
        system_intents=(),
        initial_protection_confirmed=True,
    )
    assert state.mode is ManagementMode.MANUAL
    assert state.revision == 2 and state.takeover_evidence_id == "e1"
    assert not state.permits_automatic_mutation
    assert (
        transition_management(
            state, evidence(), system_intents=(), initial_protection_confirmed=True
        )
        == state
    )
    assert (
        transition_management(
            state,
            evidence(coverage_complete=False),
            system_intents=(),
            initial_protection_confirmed=True,
        )
        == state
    )


def test_pre_protection_intervention_is_not_successful_handover():
    state = transition_management(
        TradeManagement(ticket_id="t"),
        evidence(),
        system_intents=(),
        initial_protection_confirmed=False,
    )
    assert state.mode is ManagementMode.REVIEW_REQUIRED
    assert state.reason == "intervention_before_initial_protection"


def test_review_not_cleared_by_one_later_natural_event():
    state = transition_management(
        TradeManagement(ticket_id="t"),
        evidence(coverage_complete=False),
        system_intents=(),
        initial_protection_confirmed=True,
    )
    e = evidence(action="trade", before_terms=None, executed_quantity="0.2")
    intent = SystemOrderIntent(
        command_id="c", action=OrderAction.NEW, terms=e.terms, exchange_event_at_ms=2000
    )
    assert (
        transition_management(
            state, e, system_intents=(intent,), initial_protection_confirmed=True
        )
        == state
    )


@pytest.mark.parametrize("side,position_side", [("buy", "long"), ("sell", "short")])
def test_increasing_order_is_out_of_scope(side, position_side):
    e = evidence(
        terms=terms(side=side, position_side=position_side),
        before_terms=None,
        action="new",
    )
    assert (
        classify_order_evidence(e, system_intents=()).decision
        is ManagementDecision.OUT_OF_SCOPE
    )


def test_same_order_number_different_namespace_not_system_identity():
    e = evidence(
        terms=terms(
            order_namespace="conditional",
            order_type="STOP_MARKET",
            price=None,
            trigger_price="95",
        ),
        before_terms=None,
    )
    intent = SystemOrderIntent(
        command_id="c",
        action=OrderAction.AMENDMENT,
        terms=terms(),
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(intent,)).decision
        is not ManagementDecision.SYSTEM
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "NaN"},
        {"price": "Infinity"},
        {"quantity": "-1"},
        {"close_position": True, "quantity": "1"},
        {"order_type": "STOP_MARKET", "trigger_price": None},
        {"side": "unknown"},
        {"account_id": ""},
    ],
)
def test_invalid_terms_rejected(changes):
    with pytest.raises(ValidationError):
        terms(**changes)


def test_close_all_order_can_omit_quantity():
    t = terms(
        order_namespace="conditional",
        order_type="STOP_MARKET",
        quantity=None,
        price=None,
        trigger_price="90",
        close_position=True,
    )
    assert t.quantity is None and t.reduces_position


def test_all_user_modifiable_terms_affect_signature():
    original = terms()
    assert original.terms_digest() != terms(price=Decimal(111)).terms_digest()
    assert original.terms_digest() != terms(quantity="0.8").terms_digest()
    assert original.terms_digest() == terms(price="110.000").terms_digest()


def test_manual_state_requires_evidence():
    with pytest.raises(ValidationError):
        TradeManagement(ticket_id="t", mode=ManagementMode.MANUAL)


def test_stale_system_amendment_cannot_mask_new_manual_change():
    e = evidence()
    old = SystemOrderIntent(
        command_id="old",
        action=OrderAction.AMENDMENT,
        terms=e.terms,
        exchange_event_at_ms=1500,
    )
    assert (
        classify_order_evidence(e, system_intents=(old,)).decision
        is ManagementDecision.EXTERNAL
    )


def test_other_account_intent_never_claims_current_order():
    e = evidence()
    other = SystemOrderIntent(
        command_id="other",
        action=OrderAction.AMENDMENT,
        terms=terms(account_id="another"),
        exchange_event_at_ms=2000,
    )
    assert (
        classify_order_evidence(e, system_intents=(other,)).decision
        is ManagementDecision.EXTERNAL
    )


def test_evidence_with_another_before_identity_rejected():
    with pytest.raises(ValidationError):
        evidence(before_terms=terms(account_id="another"))


def test_observed_external_terms_drift_is_decisive_even_with_history_gap():
    e=evidence(coverage_complete=False,terms=terms(price='112'))
    own=SystemOrderIntent(command_id='original',action=OrderAction.NEW,terms=terms(price='110'),exchange_event_at_ms=1000)
    assert classify_order_evidence(e,system_intents=(own,)).decision is ManagementDecision.EXTERNAL
