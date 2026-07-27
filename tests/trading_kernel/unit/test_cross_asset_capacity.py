from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.domain.account_entry_health import classify_account_entry_health
from src.trading_kernel.domain.capacity import (
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
)
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.corporate_events import CorporateEventAdmission
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    AdmissionOwnership,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from src.trading_kernel.domain.product_admission import (
    ProductAdmissionContext,
    ProductAdmissionPolicy,
    ProductMarketFacts,
    ProductProfile,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.domain.ticket import EntryOrderType
from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USMarketCalendarSession,
)


EVENT_SPEC_ID = "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"
INSTRUMENT = "binance-usdm:MSTRUSDT:perpetual"
TZ = ZoneInfo("America/New_York")


@pytest.mark.parametrize(
    ("local_time", "expected_code", "expected_risk"),
    [
        ((2026, 7, 6, 10, 0), "US_REGULAR", Decimal("30")),
        ((2026, 7, 6, 8, 0), "US_PREMARKET", Decimal("15")),
        ((2026, 7, 6, 18, 0), "US_AFTERHOURS", Decimal("15")),
        ((2026, 7, 6, 22, 0), "US_OVERNIGHT", Decimal("7.5")),
        ((2026, 7, 5, 10, 0), "US_WEEKEND_HOLIDAY", Decimal("7.5")),
    ],
)
def test_us_session_scales_stop_risk_but_keeps_fixed_five_leverage(
    local_time: tuple[int, int, int, int, int],
    expected_code: str,
    expected_risk: Decimal,
) -> None:
    action_time = _timestamp(local_time)
    decision = _decision(action_time=action_time, gross_risk=Decimal("0"))

    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim is not None
    assert decision.claim.session_code == expected_code
    assert decision.claim.risk_at_stop == expected_risk
    assert decision.claim.selected_leverage == 5
    assert decision.claim.portfolio_stop_risk_after == expected_risk
    assert decision.claim.product_admission_digest is not None


def test_crypto_and_equity_share_nine_percent_portfolio_stop_risk() -> None:
    action_time = _timestamp((2026, 7, 6, 10, 0))

    decision = _decision(action_time=action_time, gross_risk=Decimal("75"))

    assert decision.status is CapacityClaimStatus.BUDGET_EXHAUSTED
    assert decision.claim is None


def test_internal_reservations_reduce_shared_ninety_percent_margin_budget() -> None:
    action_time = _timestamp((2026, 7, 6, 10, 0))

    decision = _decision(
        action_time=action_time,
        gross_risk=Decimal("0"),
        reserved_margin=Decimal("600"),
    )

    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim is not None
    assert decision.claim.total_initial_margin_at_claim == Decimal("600")
    assert (
        decision.claim.reserved_margin + Decimal("600")
        <= Decimal("900")
    )


def _decision(
    *,
    action_time: int,
    gross_risk: Decimal,
    reserved_margin: Decimal = Decimal("0"),
):
    signal = _signal(action_time)
    snapshot = _snapshot(action_time)
    ownership = AdmissionOwnership()
    return build_capacity_claim(
        signal=signal,
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        policy=CapacityPolicy(
            owner_policy_id="policy-main",
            policy_version=1,
            max_concurrent_tickets=3,
            planned_stop_risk_fraction=Decimal("0.03"),
            max_portfolio_stop_risk_fraction=Decimal("0.09"),
            max_initial_margin_utilization=Decimal("0.90"),
            max_leverage=10,
            supported_margin_mode="cross",
            min_liquidation_distance_to_stop_distance_ratio=Decimal("2"),
            max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
        ),
        usage=CapacityUsage(
            gross_notional=Decimal("1000") if gross_risk else Decimal("0"),
            gross_risk_at_stop=gross_risk,
            active_ticket_count=1 if gross_risk else 0,
            reserved_margin=reserved_margin,
        ),
        instrument_rules=_rules(action_time),
        admission_snapshot=snapshot,
        account_entry_health=classify_account_entry_health(snapshot, ownership),
        instrument_entry_health=classify_instrument_entry_health(
            snapshot,
            ownership,
            exchange_instrument_id=INSTRUMENT,
            requested_position_side="long",
        ),
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=False,
        now_ms=action_time,
        product_admission_context=_product_context(action_time),
    )


def _signal(action_time: int) -> StrategySignal:
    facts = (
        SignalFactSnapshot(
            fact_definition_id="fact:rsr-vcb-condition:v1",
            role="condition",
            value=True,
            satisfied=True,
            observed_at_ms=action_time - 100,
            valid_until_ms=action_time + 60_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:rsr-vcb-stop:v1",
            role="protection_reference",
            value="97.5",
            satisfied=True,
            observed_at_ms=action_time - 100,
            valid_until_ms=action_time + 60_000,
            projection_version=1,
        ),
    )
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    return StrategySignal(
        signal_event_id=f"signal:rsr-vcb:{action_time}",
        runtime_scope_id="scope:RSRVCB-LONG-15M:MSTRUSDT:long",
        runtime_scope_version=1,
        strategy_group_id="RSRVCB-001",
        strategy_version_id="sgv:RSRVCB-001:v1",
        event_spec_id=EVENT_SPEC_ID,
        exchange_instrument_id=INSTRUMENT,
        position_side="long",
        fact_digest=build_signal_fact_digest(facts),
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        projection_run_id="projection:" + "1" * 64,
        armed_structure_id="armed:" + "2" * 64,
        occurred_at_ms=action_time - 100,
        observed_at_ms=action_time - 100,
        expires_at_ms=action_time + 60_000,
        facts=facts,
    )


def _snapshot(action_time: int) -> EntryAdmissionSnapshot:
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
                exchange_instrument_id=INSTRUMENT,
                mark_price=Decimal("100"),
                configured_leverage=5,
            ),
        ),
        positions=(),
        open_orders=(),
        observed_at_ms=action_time - 10,
        valid_until_ms=action_time + 60_000,
    )


def _rules(action_time: int) -> CapacityInstrumentRules:
    brackets = (
        MaintenanceMarginBracket(
            bracket_id="mstr:1",
            notional_floor=Decimal("0"),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal("0"),
        ),
    )
    return CapacityInstrumentRules(
        venue_id="binance-usdm",
        exchange_instrument_id=INSTRUMENT,
        quantity_step=Decimal("0.1"),
        price_tick=Decimal("0.1"),
        min_quantity=Decimal("0.1"),
        min_notional=Decimal("5"),
        exchange_max_leverage=10,
        maintenance_margin_brackets=brackets,
        maintenance_margin_brackets_digest=canonical_digest(brackets),
        projection_version=1,
        observed_at_ms=action_time - 10,
        valid_until_ms=action_time + 60_000,
    )


def _product_context(action_time: int) -> ProductAdmissionContext:
    local_date = datetime.fromtimestamp(action_time / 1_000, tz=TZ).date()
    session = USMarketCalendarSession.regular(
        session_date=local_date,
        timezone_name="America/New_York",
        source_ref="NYSE",
    )
    calendar = USMarketCalendar(
        calendar_version_id="calendar:test:v1",
        timezone_name="America/New_York",
        horizon_start_date=date(2026, 1, 1),
        horizon_end_date=date(2028, 12, 31),
        semantic_digest="sha256:" + "3" * 64,
        sessions=(session,),
    )
    return ProductAdmissionContext(
        profile=ProductProfile(
            product_profile_id="product:MSTR:v1",
            exchange_instrument_id=INSTRUMENT,
            venue_id="binance-usdm",
            contract_type="TRADIFI_PERPETUAL",
            underlying_type="EQUITY",
            margin_asset="USDT",
            product_status="TRADING",
            configured_leverage=5,
            margin_mode="cross",
            observed_at_ms=action_time - 10,
            valid_until_ms=action_time + 60_000,
            semantic_digest="sha256:" + "4" * 64,
        ),
        market_facts=ProductMarketFacts(
            exchange_instrument_id=INSTRUMENT,
            best_bid=Decimal("99.9"),
            best_ask=Decimal("100"),
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            top5_bid_depth=Decimal("100000"),
            top5_ask_depth=Decimal("100000"),
            funding_rate=Decimal("0.0001"),
            funding_observed_at_ms=action_time - 10,
            observed_at_ms=action_time - 10,
        ),
        calendar=calendar,
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="corporate_event_clear",
        ),
        policy=ProductAdmissionPolicy.initial_us_equity_policy(),
    )


def _timestamp(parts: tuple[int, int, int, int, int]) -> int:
    return int(datetime(*parts, tzinfo=TZ).timestamp() * 1_000)
