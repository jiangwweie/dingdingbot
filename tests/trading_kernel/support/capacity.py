"""Reusable capacity-boundary inputs for pure application tests."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.capacity import (
    CapacityInstrumentRules,
    CapacityPolicy,
    FamilyTicketLimits,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts


def long_signal() -> StrategySignal:
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


def policy() -> CapacityPolicy:
    return CapacityPolicy(
        owner_policy_id="policy-main",
        policy_version=7,
        max_concurrent_tickets=3,
        family_ticket_limits=FamilyTicketLimits(
            long_continuation=1,
            opening_range=2,
            rally_failure_short=1,
        ),
        max_ticket_stop_risk_fraction=Decimal("0.02"),
        max_gross_stop_risk_fraction=Decimal("0.06"),
        max_ticket_initial_margin_fraction=Decimal("0.30"),
        max_gross_initial_margin_utilization=Decimal("0.90"),
        max_leverage=10,
        supported_margin_mode="cross",
        post_stop_stress_multiple=Decimal(2),
        max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
        directional_stop_risk_limit_fraction=Decimal("0.04"),
        min_materialization_ratio=Decimal("0.50"),
    )


def rules() -> CapacityInstrumentRules:
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


def snapshot() -> EntryAdmissionSnapshot:
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
