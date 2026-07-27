from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.corporate_events import CorporateEventAdmission
from src.trading_kernel.domain.product_admission import (
    ProductAdmissionPolicy,
    ProductMarketFacts,
    ProductProfile,
    evaluate_product_admission,
)
from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USMarketCalendarSession,
)


NY = ZoneInfo("America/New_York")
INSTRUMENT = "binance-usdm:NVDAUSDT:perpetual"


def test_regular_product_admission_accepts_exact_product_and_liquidity() -> None:
    now_ms = int(
        datetime(2026, 7, 6, 10, 0, tzinfo=NY).timestamp() * 1000
    )
    decision = evaluate_product_admission(
        action_time_ms=now_ms,
        order_notional=Decimal("1000"),
        profile=_profile(now_ms),
        market_facts=_facts(now_ms),
        calendar=_calendar(),
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="corporate_event_clear",
        ),
        policy=ProductAdmissionPolicy.initial_us_equity_policy(),
    )

    assert decision.allowed is True
    assert decision.session_code == "US_REGULAR"
    assert decision.session_multiplier == Decimal("1")
    assert decision.spread_bps == Decimal("10")
    assert decision.product_admission_digest.startswith("sha256:")


def test_product_admission_fails_closed_for_product_spread_basis_and_depth() -> None:
    now_ms = int(
        datetime(2026, 7, 6, 10, 0, tzinfo=NY).timestamp() * 1000
    )
    policy = ProductAdmissionPolicy.initial_us_equity_policy()
    profile = _profile(now_ms)
    facts = _facts(now_ms)

    wrong_product = evaluate_product_admission(
        action_time_ms=now_ms,
        order_notional=Decimal("1000"),
        profile=profile.model_copy(update={"contract_type": "PERPETUAL"}),
        market_facts=facts,
        calendar=_calendar(),
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="clear",
        ),
        policy=policy,
    )
    wide_spread = evaluate_product_admission(
        action_time_ms=now_ms,
        order_notional=Decimal("1000"),
        profile=profile,
        market_facts=facts.model_copy(
            update={"best_bid": Decimal("99"), "best_ask": Decimal("101")}
        ),
        calendar=_calendar(),
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="clear",
        ),
        policy=policy,
    )
    basis = evaluate_product_admission(
        action_time_ms=now_ms,
        order_notional=Decimal("1000"),
        profile=profile,
        market_facts=facts.model_copy(update={"mark_price": Decimal("101")}),
        calendar=_calendar(),
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="clear",
        ),
        policy=policy,
    )
    shallow = evaluate_product_admission(
        action_time_ms=now_ms,
        order_notional=Decimal("1000"),
        profile=profile,
        market_facts=facts.model_copy(
            update={"top5_bid_depth": Decimal("4999")}
        ),
        calendar=_calendar(),
        corporate_event_admission=CorporateEventAdmission(
            allowed=True,
            reason_code="clear",
        ),
        policy=policy,
    )

    assert wrong_product.reason_code == "product_identity_ineligible"
    assert wide_spread.reason_code == "spread_limit_exceeded"
    assert basis.reason_code == "mark_index_deviation_exceeded"
    assert shallow.reason_code == "top5_depth_insufficient"


def _profile(now_ms: int) -> ProductProfile:
    return ProductProfile(
        product_profile_id="product-profile:nvda:v1",
        exchange_instrument_id=INSTRUMENT,
        venue_id="binance-usdm",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        product_status="TRADING",
        configured_leverage=5,
        margin_mode="cross",
        observed_at_ms=now_ms - 1_000,
        valid_until_ms=now_ms + 60_000,
        semantic_digest="sha256:" + "3" * 64,
    )


def _facts(now_ms: int) -> ProductMarketFacts:
    return ProductMarketFacts(
        exchange_instrument_id=INSTRUMENT,
        best_bid=Decimal("99.95"),
        best_ask=Decimal("100.05"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        top5_bid_depth=Decimal("6000"),
        top5_ask_depth=Decimal("7000"),
        funding_rate=Decimal("0.0001"),
        funding_observed_at_ms=now_ms - 1_000,
        observed_at_ms=now_ms - 500,
    )


def _calendar() -> USMarketCalendar:
    return USMarketCalendar(
        calendar_version_id="calendar:v1",
        timezone_name="America/New_York",
        horizon_start_date=date(2026, 1, 1),
        horizon_end_date=date(2028, 12, 31),
        semantic_digest="sha256:" + "4" * 64,
        sessions=(
            USMarketCalendarSession.regular(
                session_date=date(2026, 7, 6),
                timezone_name="America/New_York",
                source_ref="NYSE-2026",
            ),
        ),
    )
