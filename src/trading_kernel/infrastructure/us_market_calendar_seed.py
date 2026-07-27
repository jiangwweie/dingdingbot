"""Deterministic 2026-2028 NYSE calendar seed from the official schedule."""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.product_admission import ProductAdmissionPolicy
from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USMarketCalendarSession,
)


NYSE_SOURCE = "https://www.nyse.com/trade/hours-calendars"

_HOLIDAYS = {
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 6, 18),
    date(2027, 7, 5),
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),
    date(2028, 1, 17),
    date(2028, 2, 21),
    date(2028, 4, 14),
    date(2028, 5, 29),
    date(2028, 6, 19),
    date(2028, 7, 4),
    date(2028, 9, 4),
    date(2028, 11, 23),
    date(2028, 12, 25),
}

_EARLY_CLOSES = {
    date(2026, 11, 27),
    date(2026, 12, 24),
    date(2027, 11, 26),
    date(2028, 7, 3),
    date(2028, 11, 24),
}


def initial_us_market_calendar() -> USMarketCalendar:
    start = date(2026, 1, 1)
    end = date(2028, 12, 31)
    sessions: list[USMarketCalendarSession] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            if current in _HOLIDAYS:
                sessions.append(
                    USMarketCalendarSession(
                        session_date=current,
                        holiday=True,
                        regular_open_at_ms=None,
                        regular_close_at_ms=None,
                        early_close=False,
                        source_ref=NYSE_SOURCE,
                    )
                )
            else:
                early = current in _EARLY_CLOSES
                sessions.append(
                    USMarketCalendarSession.regular(
                        session_date=current,
                        timezone_name="America/New_York",
                        close_hour=13 if early else 16,
                        early_close=early,
                        source_ref=NYSE_SOURCE,
                    )
                )
        current += timedelta(days=1)
    calendar_version_id = "us-equity-calendar:nyse:2026-2028:v1"
    timezone_name = "America/New_York"
    payload = {
        "calendar_version_id": calendar_version_id,
        "timezone_name": timezone_name,
        "horizon_start_date": start.isoformat(),
        "horizon_end_date": end.isoformat(),
        "sessions": [session.model_dump(mode="json") for session in sessions],
    }
    digest = f"sha256:{sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}"
    return USMarketCalendar(
        calendar_version_id=calendar_version_id,
        timezone_name=timezone_name,
        horizon_start_date=start,
        horizon_end_date=end,
        semantic_digest=digest,
        sessions=tuple(sessions),
    )


async def seed_us_market_calendar(
    uow: KernelUnitOfWork,
    *,
    seeded_at_ms: int,
) -> int:
    if seeded_at_ms <= 0:
        raise ValueError("calendar seed time must be positive")
    calendar_inserted = await uow.product_admission.seed_calendar(
        initial_us_market_calendar(),
        source_name="NYSE",
        created_at_ms=seeded_at_ms,
    )
    policy_inserted = await uow.product_admission.seed_policy(
        ProductAdmissionPolicy.initial_us_equity_policy(),
        created_at_ms=seeded_at_ms,
    )
    return int(calendar_inserted) + int(policy_inserted)
