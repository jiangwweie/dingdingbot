from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.corporate_events import (
    CorporateEvent,
    CorporateEventCertainty,
    CorporateEventCoverage,
    CorporateEventKind,
    evaluate_corporate_event_admission,
)


NY = ZoneInfo("America/New_York")
INSTRUMENT = "binance-usdm:NVDAUSDT:perpetual"


def test_exact_earnings_blocks_four_hours_before_and_two_closed_bars_after() -> None:
    effective_ms = _ms(datetime(2026, 8, 20, 16, 5, tzinfo=NY))
    event = CorporateEvent(
        corporate_event_version_id="event:nvda:earnings:2026q2",
        exchange_instrument_id=INSTRUMENT,
        event_kind=CorporateEventKind.EARNINGS,
        certainty=CorporateEventCertainty.EXACT_TIME,
        event_date=date(2026, 8, 20),
        effective_at_ms=effective_ms,
        status="active",
    )
    coverage = _coverage(effective_ms)

    before = evaluate_corporate_event_admission(
        action_time_ms=effective_ms - 3 * 3_600_000,
        exchange_instrument_id=INSTRUMENT,
        coverage=coverage,
        events=(event,),
        closed_15m_bars_after_event=0,
    )
    one_bar = evaluate_corporate_event_admission(
        action_time_ms=effective_ms + 20 * 60_000,
        exchange_instrument_id=INSTRUMENT,
        coverage=coverage,
        events=(event,),
        closed_15m_bars_after_event=1,
    )
    two_bars = evaluate_corporate_event_admission(
        action_time_ms=effective_ms + 31 * 60_000,
        exchange_instrument_id=INSTRUMENT,
        coverage=coverage,
        events=(event,),
        closed_15m_bars_after_event=2,
    )

    assert before.allowed is False
    assert before.reason_code == "earnings_blackout_pre_release"
    assert one_bar.reason_code == "earnings_waiting_closed_bars"
    assert two_bars.allowed is True


def test_date_only_earnings_blocks_the_complete_new_york_date() -> None:
    action = datetime(2026, 8, 20, 8, 0, tzinfo=NY)
    event = CorporateEvent(
        corporate_event_version_id="event:nvda:earnings:date-only",
        exchange_instrument_id=INSTRUMENT,
        event_kind=CorporateEventKind.EARNINGS,
        certainty=CorporateEventCertainty.DATE_ONLY,
        event_date=action.date(),
        effective_at_ms=None,
        status="active",
    )

    result = evaluate_corporate_event_admission(
        action_time_ms=_ms(action),
        exchange_instrument_id=INSTRUMENT,
        coverage=_coverage(_ms(action)),
        events=(event,),
        closed_15m_bars_after_event=0,
    )

    assert result.allowed is False
    assert result.reason_code == "earnings_date_only_blackout"


def test_missing_coverage_and_split_fail_closed() -> None:
    action_ms = _ms(datetime(2026, 8, 20, 8, 0, tzinfo=NY))
    missing = evaluate_corporate_event_admission(
        action_time_ms=action_ms,
        exchange_instrument_id=INSTRUMENT,
        coverage=None,
        events=(),
        closed_15m_bars_after_event=0,
    )
    split = CorporateEvent(
        corporate_event_version_id="event:nvda:split",
        exchange_instrument_id=INSTRUMENT,
        event_kind=CorporateEventKind.SPLIT,
        certainty=CorporateEventCertainty.EXACT_TIME,
        event_date=date(2026, 8, 20),
        effective_at_ms=action_ms,
        status="active",
    )
    blocked = evaluate_corporate_event_admission(
        action_time_ms=action_ms,
        exchange_instrument_id=INSTRUMENT,
        coverage=_coverage(action_ms),
        events=(split,),
        closed_15m_bars_after_event=0,
    )

    assert missing.reason_code == "corporate_event_coverage_missing"
    assert blocked.reason_code == "corporate_action_reprofile_required"

    refreshed = evaluate_corporate_event_admission(
        action_time_ms=action_ms,
        exchange_instrument_id=INSTRUMENT,
        coverage=_coverage(action_ms),
        events=(split,),
        closed_15m_bars_after_event=0,
        product_profile_observed_at_ms=action_ms + 1,
    )
    assert refreshed.allowed is True


def _coverage(now_ms: int) -> CorporateEventCoverage:
    return CorporateEventCoverage(
        coverage_id="coverage:nvda",
        exchange_instrument_id=INSTRUMENT,
        coverage_start_ms=now_ms - 86_400_000,
        coverage_end_ms=now_ms + 86_400_000,
        coverage_status="complete",
        valid_until_ms=now_ms + 86_400_000,
        coverage_digest="sha256:" + "2" * 64,
    )


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)
