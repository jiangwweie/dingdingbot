from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USMarketCalendarSession,
    USSessionCode,
    classify_us_equity_session,
)


NY = ZoneInfo("America/New_York")


def test_session_classifier_covers_all_owner_approved_windows() -> None:
    calendar = _calendar()

    expected = {
        datetime(2026, 7, 6, 10, 0, tzinfo=NY): (
            USSessionCode.REGULAR,
            Decimal("1"),
        ),
        datetime(2026, 7, 6, 8, 0, tzinfo=NY): (
            USSessionCode.PREMARKET,
            Decimal("0.5"),
        ),
        datetime(2026, 7, 6, 18, 0, tzinfo=NY): (
            USSessionCode.AFTERHOURS,
            Decimal("0.5"),
        ),
        datetime(2026, 7, 6, 22, 0, tzinfo=NY): (
            USSessionCode.OVERNIGHT,
            Decimal("0.25"),
        ),
        datetime(2026, 7, 4, 10, 0, tzinfo=NY): (
            USSessionCode.WEEKEND_HOLIDAY,
            Decimal("0.25"),
        ),
    }
    for local_time, (session, multiplier) in expected.items():
        classified = classify_us_equity_session(
            calendar=calendar,
            action_time_ms=int(local_time.timestamp() * 1000),
        )
        assert classified.session_code is session
        assert classified.stop_risk_multiplier == multiplier


def test_early_close_and_dst_use_new_york_calendar_authority() -> None:
    calendar = _calendar()

    before_close = classify_us_equity_session(
        calendar=calendar,
        action_time_ms=int(
            datetime(2026, 11, 27, 12, 59, tzinfo=NY).timestamp() * 1000
        ),
    )
    after_close = classify_us_equity_session(
        calendar=calendar,
        action_time_ms=int(
            datetime(2026, 11, 27, 13, 1, tzinfo=NY).timestamp() * 1000
        ),
    )
    summer_utc = datetime.fromtimestamp(
        int(
            datetime(2026, 7, 6, 9, 30, tzinfo=NY).timestamp()
        ),
        tz=ZoneInfo("UTC"),
    )
    winter_utc = datetime.fromtimestamp(
        int(
            datetime(2026, 12, 7, 9, 30, tzinfo=NY).timestamp()
        ),
        tz=ZoneInfo("UTC"),
    )

    assert before_close.session_code is USSessionCode.REGULAR
    assert after_close.session_code is USSessionCode.AFTERHOURS
    assert summer_utc.hour == 13
    assert winter_utc.hour == 14


def test_missing_or_out_of_horizon_calendar_is_unknown_and_blocks() -> None:
    calendar = _calendar()

    missing = classify_us_equity_session(
        calendar=calendar,
        action_time_ms=int(
            datetime(2026, 7, 7, 10, 0, tzinfo=NY).timestamp() * 1000
        ),
    )
    outside = classify_us_equity_session(
        calendar=calendar,
        action_time_ms=int(
            datetime(2029, 1, 2, 10, 0, tzinfo=NY).timestamp() * 1000
        ),
    )

    assert missing.session_code is USSessionCode.UNKNOWN
    assert outside.session_code is USSessionCode.UNKNOWN
    assert missing.stop_risk_multiplier == 0
    assert outside.stop_risk_multiplier == 0


def _calendar() -> USMarketCalendar:
    return USMarketCalendar(
        calendar_version_id="us-market-calendar:2026-test",
        timezone_name="America/New_York",
        horizon_start_date=date(2026, 1, 1),
        horizon_end_date=date(2028, 12, 31),
        semantic_digest="sha256:" + "1" * 64,
        sessions=(
            USMarketCalendarSession(
                session_date=date(2026, 7, 4),
                holiday=True,
                regular_open_at_ms=None,
                regular_close_at_ms=None,
                early_close=False,
                source_ref="NYSE-2026",
            ),
            USMarketCalendarSession.regular(
                session_date=date(2026, 7, 6),
                timezone_name="America/New_York",
                source_ref="NYSE-2026",
            ),
            USMarketCalendarSession.regular(
                session_date=date(2026, 11, 27),
                timezone_name="America/New_York",
                close_hour=13,
                early_close=True,
                source_ref="NYSE-2026",
            ),
            USMarketCalendarSession.regular(
                session_date=date(2026, 12, 7),
                timezone_name="America/New_York",
                source_ref="NYSE-2026",
            ),
        ),
    )
