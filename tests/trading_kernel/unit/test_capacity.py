from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.domain.capacity import (
    ActionTimeFacts,
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
)
from src.trading_kernel.domain.ticket import EntryOrderType
from tests.trading_kernel.unit.test_signal import _signal


def test_capacity_claim_sizes_from_stop_risk_and_freezes_one_ticket() -> None:
    decision = build_capacity_claim(
        signal=_long_signal(),
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        policy=_policy(),
        usage=_usage(),
        instrument_rules=_rules(),
        action_facts=_action_facts(),
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=False,
        now_ms=1_010,
    )

    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim is not None
    claim = decision.claim
    assert claim.quantity == Decimal("10.0")
    assert claim.notional == Decimal("1000.0")
    assert claim.risk_at_stop == Decimal("10.0")
    assert claim.quantity % _rules().quantity_step == 0
    assert claim.risk_at_stop <= _policy().max_ticket_risk_at_stop
    assert claim.initial_stop_price == Decimal("99.0")
    assert claim.take_profit_prices == (Decimal("101.0"),)
    assert claim.take_profit_quantities == (Decimal("5.0"),)
    assert claim.decision_digest.startswith("sha256:")

    ticket = claim.to_ticket()
    assert ticket.identity.ticket_id == claim.ticket_identity.ticket_id
    assert ticket.entry_reference_price == Decimal("100")
    assert ticket.identity.signal_event_id == "signal-capacity-long"
    assert ticket.take_profit_quantities == (Decimal("5.0"),)


def test_capacity_claim_caps_margin_by_current_account_equity() -> None:
    decision = build_capacity_claim(
        signal=_long_signal(),
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        policy=_policy(),
        usage=_usage(),
        instrument_rules=_rules(),
        action_facts=_action_facts().model_copy(
            update={
                "account_equity": Decimal("20"),
                "available_margin": Decimal("1000"),
            }
        ),
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=False,
        now_ms=1_010,
    )

    assert decision.claim is not None
    assert decision.claim.notional == Decimal("100.0")


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stale_action", CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE),
        ("one_way", CapacityClaimStatus.ACCOUNT_MODE_INVALID),
        ("occupied", CapacityClaimStatus.NETTING_DOMAIN_OCCUPIED),
        ("stop_wrong_side", CapacityClaimStatus.PROTECTION_UNAVAILABLE),
        ("no_margin", CapacityClaimStatus.BUDGET_EXHAUSTED),
        ("rules_stale", CapacityClaimStatus.INSTRUMENT_RULES_INVALID),
    ],
)
def test_capacity_claim_fails_closed_for_each_action_time_boundary(
    case: str,
    expected: CapacityClaimStatus,
) -> None:
    action = _action_facts()
    signal = _long_signal()
    position_mode = "independent_sides"
    occupied = False
    rules = _rules()

    if case == "stale_action":
        action = action.model_copy(update={"valid_until_ms": 1_010})
    elif case == "one_way":
        position_mode = "one_way"
    elif case == "occupied":
        occupied = True
    elif case == "stop_wrong_side":
        signal = _long_signal(stop_reference="101")
    elif case == "no_margin":
        action = action.model_copy(update={"available_margin": Decimal("0")})
    elif case == "rules_stale":
        rules = rules.model_copy(update={"valid_until_ms": 1_010})

    decision = build_capacity_claim(
        signal=signal,
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode=position_mode,
        policy=_policy(),
        usage=_usage(),
        instrument_rules=rules,
        action_facts=action,
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=occupied,
        now_ms=1_010,
    )

    assert decision.status is expected
    assert decision.claim is None


def _long_signal(*, stop_reference: str = "99"):
    base = _signal(
        signal_event_id="signal-capacity-long",
        occurred_at_ms=1_000,
        observed_at_ms=1_005,
        expires_at_ms=2_000,
    )
    facts = tuple(
        fact.model_copy(update={"value": stop_reference})
        if fact.role == "protection_reference"
        else fact
        for fact in base.facts
    )
    from src.trading_kernel.domain.signal import build_signal_fact_digest

    return base.model_copy(
        update={
            "runtime_scope_id": "scope-sor-btc-long",
            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
            "position_side": "long",
            "facts": facts,
            "fact_digest": build_signal_fact_digest(facts),
        }
    )


def _policy() -> CapacityPolicy:
    return CapacityPolicy(
        owner_policy_id="policy-main",
        policy_version=7,
        max_concurrent_tickets=8,
        max_gross_notional=Decimal("1000"),
        max_gross_risk_at_stop=Decimal("50"),
        max_ticket_risk_at_stop=Decimal("10"),
        target_leverage=Decimal("5"),
    )


def _usage() -> CapacityUsage:
    return CapacityUsage(
        gross_notional=Decimal("0"),
        gross_risk_at_stop=Decimal("0"),
        active_ticket_count=0,
    )


def _rules() -> CapacityInstrumentRules:
    return CapacityInstrumentRules(
        quantity_step=Decimal("0.1"),
        price_tick=Decimal("0.1"),
        min_quantity=Decimal("0.1"),
        min_notional=Decimal("5"),
        projection_version=3,
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )


def _action_facts() -> ActionTimeFacts:
    return ActionTimeFacts(
        signal_event_id="signal-capacity-long",
        runtime_scope_id="scope-sor-btc-long",
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        best_bid_price=Decimal("99.9"),
        best_ask_price=Decimal("100"),
        account_equity=Decimal("1000"),
        available_margin=Decimal("1000"),
        netting_domain_position_qty=Decimal("0"),
        netting_domain_open_order_count=0,
        observed_at_ms=1_008,
        valid_until_ms=1_020,
    )
