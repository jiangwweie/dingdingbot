from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.domain.account_entry_health import classify_account_entry_health
from src.trading_kernel.domain.capacity import (
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
)
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    AdmissionOwnership,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from src.trading_kernel.domain.ticket import EntryOrderType
from tests.trading_kernel.unit.test_signal import _signal


def test_capacity_claim_freezes_dynamic_budget_and_leverage_evidence() -> None:
    snapshot = _snapshot()
    ownership = AdmissionOwnership()
    decision = build_capacity_claim(
        signal=_long_signal(),
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        policy=_policy(),
        usage=CapacityUsage(
            gross_notional=Decimal("0"),
            gross_risk_at_stop=Decimal("0"),
            active_ticket_count=0,
        ),
        instrument_rules=_rules(),
        admission_snapshot=snapshot,
        account_entry_health=classify_account_entry_health(snapshot, ownership),
        instrument_entry_health=classify_instrument_entry_health(
            snapshot,
            ownership,
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            requested_position_side="long",
        ),
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=False,
        now_ms=1_010,
    )

    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim is not None
    claim = decision.claim
    assert claim.selected_leverage == 4
    assert claim.planned_stop_risk_budget == Decimal("30")
    assert claim.post_fill_stop_risk_limit == Decimal("33")
    assert claim.reserved_margin == Decimal("300")
    assert claim.entry_admission_snapshot_digest == snapshot.digest()
    assert claim.account_capacity_domain_key == "binance-usdm:experiment-1"
    assert claim.leverage_domain_key == "binance-usdm:experiment-1:binance-usdm:BTCUSDT:perpetual"
    assert claim.to_ticket().selected_leverage == 4


def _long_signal():
    base = _signal(
        signal_event_id="signal-capacity-long",
        occurred_at_ms=1_000,
        observed_at_ms=1_005,
        expires_at_ms=2_000,
    )
    facts = tuple(
        fact.model_copy(update={"value": "97.5"})
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
        max_concurrent_tickets=3,
        planned_stop_risk_fraction=Decimal("0.03"),
        max_initial_margin_utilization=Decimal("0.90"),
        max_leverage=10,
        supported_margin_mode="cross",
        min_liquidation_distance_to_stop_distance_ratio=Decimal("2"),
        max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
    )


def _rules() -> CapacityInstrumentRules:
    brackets = (
        MaintenanceMarginBracket(
            bracket_id="binance-usdm:BTCUSDT:1",
            notional_floor=Decimal("0"),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal("0"),
        ),
    )
    return CapacityInstrumentRules(
        venue_id="binance-usdm",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        quantity_step=Decimal("0.1"),
        price_tick=Decimal("0.1"),
        min_quantity=Decimal("0.1"),
        min_notional=Decimal("5"),
        exchange_max_leverage=10,
        maintenance_margin_brackets=brackets,
        maintenance_margin_brackets_digest=canonical_digest(brackets),
        projection_version=3,
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )


def _snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        margin_mode="cross",
        total_wallet_balance=Decimal("1000"),
        total_margin_balance=Decimal("1000"),
        total_initial_margin=Decimal("0"),
        total_maintenance_margin=Decimal("0"),
        available_margin=Decimal("1000"),
        best_bid_price=Decimal("99.9"),
        best_ask_price=Decimal("100"),
        instrument_facts=(
            AdmissionInstrumentFacts(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                mark_price=Decimal("100"),
                configured_leverage=1,
            ),
        ),
        positions=(),
        open_orders=(),
        observed_at_ms=1_008,
        valid_until_ms=1_020,
    )
