from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.domain.account_entry_health import classify_account_entry_health
from src.trading_kernel.domain.capacity import (
    CapacityClaim,
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
    build_capacity_claim_digest,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOwnership,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.ticket import EntryOrderType


def test_capacity_claim_freezes_configured_leverage_and_demand_based_margin() -> None:
    snapshot, decision = _build_decision()

    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim is not None
    claim = decision.claim
    assert claim.selected_leverage == 5
    assert claim.planned_stop_risk_budget == Decimal(30)
    assert claim.max_ticket_stop_risk_fraction == Decimal("0.03")
    assert claim.max_gross_stop_risk_fraction == Decimal("0.06")
    assert claim.max_ticket_initial_margin_fraction == Decimal("0.45")
    assert claim.max_gross_initial_margin_utilization == Decimal("0.90")
    assert claim.post_fill_stop_risk_limit == Decimal(33)
    assert claim.reserved_margin == Decimal(240)
    assert claim.cross_margin_stress_evidence.proof.status == "passed"
    assert (
        claim.cross_margin_stress_evidence.proof.proof_digest
        == claim.to_ticket().claim_stress_proof_digest
    )
    assert claim.entry_admission_snapshot_digest == snapshot.digest()
    assert claim.account_capacity_domain_key == "binance-usdm:experiment-1"
    assert claim.leverage_domain_key == "binance-usdm:experiment-1:binance-usdm:BTCUSDT:perpetual"
    assert claim.leverage_change_required is False
    assert claim.ticket_identity.exposure_episode_id == _long_signal().exposure_episode_id
    assert claim.exit_policy_id.startswith("exit-policy:SOR-001:SOR-LONG:")
    assert claim.exit_policy_semantic_hash.startswith("sha256:")
    assert claim.pre_tp1_reclaim_price == Decimal(102)
    assert claim.exposure_session_end_ms == 86_401_000
    ticket = claim.to_ticket()
    assert ticket.selected_leverage == 5
    assert (
        claim.universe_version_id
        == ticket.universe_version_id
        == _long_signal().universe_version_id
    )
    assert (
        claim.universe_semantic_digest
        == ticket.universe_semantic_digest
        == _long_signal().universe_semantic_digest
    )


def test_capacity_claim_rejects_reserved_margin_above_its_frozen_ticket_budget() -> None:
    _, decision = _build_decision()
    assert decision.claim is not None
    claim = decision.claim
    payload = {
        name: getattr(claim, name)
        for name in CapacityClaim.model_fields
    }
    payload["reserved_margin"] = claim.ticket_margin_budget + Decimal(1)
    provisional = CapacityClaim.model_construct(**payload)
    decision_digest = build_capacity_claim_digest(provisional)
    payload["decision_digest"] = decision_digest
    payload["capacity_claim_id"] = (
        f"claim:{decision_digest.removeprefix('sha256:')[:32]}"
    )

    with pytest.raises(ValidationError, match="reserved margin exceeds"):
        CapacityClaim.model_validate(payload)


def _build_decision():
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
            gross_notional=Decimal(0),
            gross_risk_at_stop=Decimal(0),
            current_reserved_margin=Decimal(0),
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
    return snapshot, decision


def _long_signal():
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_id == "SOR-LONG"
    )
    values = {
        "opening_range_defined_v3": True,
        "breakout_edge_crossed_v3": True,
        "opening_range_high_reference_v3": "102",
        "opening_range_low_reference_v3": "97.5",
        "session_start_ms_v3": "1000",
        "session_end_ms_v3": "86401000",
    }
    facts = tuple(
        SignalFactSnapshot(
            fact_definition_id=requirement.fact_definition_id,
            role=requirement.role,
            value=values[requirement.fact_name],
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        )
        for requirement in contract.required_facts
    )
    return StrategySignal(
        signal_event_id="signal-capacity-long",
        exposure_episode_id="episode:" + "c" * 64,
        runtime_scope_id="scope-sor-btc-long",
        runtime_scope_version=1,
        strategy_group_id=contract.strategy_group_id,
        strategy_version_id=contract.strategy_version_id,
        event_spec_id=contract.event_spec_id,
        universe_version_id="universe:SOR-LONG:3",
        universe_semantic_digest="sha256:" + "a" * 64,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        fact_digest=build_signal_fact_digest(facts),
        occurred_at_ms=1_000,
        observed_at_ms=1_005,
        expires_at_ms=2_000,
        facts=facts,
    )


def _policy() -> CapacityPolicy:
    return CapacityPolicy(
        owner_policy_id="policy-main",
        policy_version=7,
        max_concurrent_tickets=3,
        max_ticket_stop_risk_fraction=Decimal("0.03"),
        max_gross_stop_risk_fraction=Decimal("0.06"),
        max_ticket_initial_margin_fraction=Decimal("0.45"),
        max_gross_initial_margin_utilization=Decimal("0.90"),
        max_leverage=10,
        supported_margin_mode="cross",
        post_stop_stress_multiple=Decimal(2),
        max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
    )


def _rules() -> CapacityInstrumentRules:
    brackets = (
        MaintenanceMarginBracket(
            bracket_id="binance-usdm:BTCUSDT:1",
            notional_floor=Decimal(0),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )
    return CapacityInstrumentRules(
        venue_id="binance-usdm",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        quantity_step=Decimal("0.1"),
        price_tick=Decimal("0.1"),
        min_quantity=Decimal("0.1"),
        min_notional=Decimal(5),
        exchange_max_leverage=10,
        maintenance_margin_brackets=brackets,
        maintenance_margin_brackets_digest=canonical_digest(brackets),
        notional_coefficient=Decimal(1),
        notional_coefficient_certified=True,
        projection_version=3,
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )


def _snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="experiment-1",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            mark_price=Decimal(100),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=1_008,
            valid_until_ms=1_020,
        ),
        best_bid_price=Decimal("99.9"),
        best_ask_price=Decimal(100),
        open_orders=(),
        observed_at_ms=1_008,
        valid_until_ms=1_020,
    )
