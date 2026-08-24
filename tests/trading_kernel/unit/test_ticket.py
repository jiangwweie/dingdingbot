from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.ticket import (
    EntryOrderType,
    build_ticket_id,
)
from tests.trading_kernel.support.tickets import make_ticket, make_ticket_identity


def test_trade_ticket_is_immutable_and_contains_complete_decision() -> None:
    ticket = make_ticket()

    assert ticket.quantity == Decimal("0.001")
    assert ticket.selected_leverage == 5
    assert ticket.capacity_claim_id.startswith("claim:")
    assert ticket.identity.netting_domain.position_side == "long"
    assert ticket.cross_margin_stress_model_id == "cross-margin-stop-stress-v1"
    assert ticket.claim_stress_proof_digest.startswith("sha256:")
    assert ticket.exit_policy_semantic_hash.startswith("sha256:")
    assert ticket.pre_tp1_reclaim_price == Decimal(60100)
    assert ticket.decision_digest().startswith("sha256:")

    with pytest.raises(ValidationError):
        ticket.quantity = Decimal("0.002")  # type: ignore[misc]


def test_trade_ticket_freezes_policy_and_scope_identity_and_version() -> None:
    ticket = make_ticket()

    assert ticket.owner_policy_id == "policy-main"
    assert ticket.owner_policy_version == 7
    assert ticket.runtime_scope_id == "scope-sor-btc-long"
    assert ticket.runtime_scope_version == 4
    assert ticket.universe_version_id == "universe:sor-long:4"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Decimal(0)),
        ("notional", Decimal(-1)),
        ("selected_leverage", 0),
        ("reserved_margin", Decimal(0)),
        ("entry_reference_price", Decimal(0)),
        ("risk_at_stop", Decimal("-0.1")),
        ("initial_stop_price", Decimal(0)),
    ],
)
def test_trade_ticket_rejects_invalid_financial_values(
    field: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        make_ticket(**{field: value})


def test_trade_ticket_requires_future_expiry() -> None:
    with pytest.raises(ValidationError):
        make_ticket(expires_at_ms=1_000)


def test_limit_ticket_requires_limit_price_and_market_ticket_forbids_it() -> None:
    with pytest.raises(ValidationError):
        make_ticket(entry_order_type=EntryOrderType.LIMIT, entry_limit_price=None)

    with pytest.raises(ValidationError):
        make_ticket(
            entry_order_type=EntryOrderType.MARKET,
            entry_limit_price=Decimal(60000),
        )


def test_ticket_requires_pre_tp1_plan_fields_to_be_both_present_or_both_absent() -> None:
    with pytest.raises(ValidationError):
        make_ticket(pre_tp1_reclaim_price=None)
    with pytest.raises(ValidationError):
        make_ticket(exposure_session_end_ms=None)

    non_sor = make_ticket(
        pre_tp1_reclaim_price=None,
        exposure_session_end_ms=None,
    )
    assert non_sor.pre_tp1_reclaim_price is None


def test_ticket_id_is_deterministic_and_causal() -> None:
    identity = make_ticket_identity()
    same = build_ticket_id(
        signal_event_id=identity.signal_event_id,
        runtime=identity.runtime,
        netting_domain=identity.netting_domain,
    )
    different_signal = build_ticket_id(
        signal_event_id="signal-2",
        runtime=identity.runtime,
        netting_domain=identity.netting_domain,
    )

    assert identity.ticket_id == same
    assert identity.ticket_id != different_signal


def test_ticket_digest_binds_optional_selection_authority() -> None:
    static = make_ticket()
    dynamic = make_ticket(selection_authority_id="authority:test:1")

    assert static.selection_authority_id is None
    assert dynamic.selection_authority_id == "authority:test:1"
    assert dynamic.decision_digest() != static.decision_digest()
