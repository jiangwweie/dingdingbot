"""Versioned New York session classification for 24/7 equity perpetuals."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class USSessionCode(StrEnum):
    REGULAR = "US_REGULAR"
    PREMARKET = "US_PREMARKET"
    AFTERHOURS = "US_AFTERHOURS"
    OVERNIGHT = "US_OVERNIGHT"
    WEEKEND_HOLIDAY = "US_WEEKEND_HOLIDAY"
    UNKNOWN = "UNKNOWN"


_MULTIPLIERS = {
    USSessionCode.REGULAR: Decimal("1"),
    USSessionCode.PREMARKET: Decimal("0.5"),
    USSessionCode.AFTERHOURS: Decimal("0.5"),
    USSessionCode.OVERNIGHT: Decimal("0.25"),
    USSessionCode.WEEKEND_HOLIDAY: Decimal("0.25"),
    USSessionCode.UNKNOWN: Decimal("0"),
}


class USMarketCalendarSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_date: date
    holiday: bool
    regular_open_at_ms: int | None
    regular_close_at_ms: int | None
    early_close: bool
    source_ref: str

    @field_validator("source_ref", mode="before")
    @classmethod
    def _require_source(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("calendar session source must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_shape(self) -> "USMarketCalendarSession":
        if self.holiday:
            if (
                self.regular_open_at_ms is not None
                or self.regular_close_at_ms is not None
                or self.early_close
            ):
                raise ValueError("holiday calendar row cannot carry trading hours")
            return self
        if (
            self.regular_open_at_ms is None
            or self.regular_close_at_ms is None
            or self.regular_close_at_ms <= self.regular_open_at_ms
        ):
            raise ValueError("trading calendar row requires an open/close window")
        return self

    @classmethod
    def regular(
        cls,
        *,
        session_date: date,
        timezone_name: str,
        close_hour: int = 16,
        close_minute: int = 0,
        early_close: bool = False,
        source_ref: str,
    ) -> "USMarketCalendarSession":
        timezone = ZoneInfo(timezone_name)
        opened = datetime.combine(
            session_date,
            time(hour=9, minute=30),
            tzinfo=timezone,
        )
        closed = datetime.combine(
            session_date,
            time(hour=close_hour, minute=close_minute),
            tzinfo=timezone,
        )
        return cls(
            session_date=session_date,
            holiday=False,
            regular_open_at_ms=int(opened.timestamp() * 1_000),
            regular_close_at_ms=int(closed.timestamp() * 1_000),
            early_close=early_close,
            source_ref=source_ref,
        )


class USMarketCalendar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    calendar_version_id: str
    timezone_name: str
    horizon_start_date: date
    horizon_end_date: date
    semantic_digest: str
    sessions: tuple[USMarketCalendarSession, ...]

    @field_validator(
        "calendar_version_id",
        "timezone_name",
        "semantic_digest",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("market calendar identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_calendar(self) -> "USMarketCalendar":
        ZoneInfo(self.timezone_name)
        if self.horizon_end_date < self.horizon_start_date:
            raise ValueError("calendar horizon is inverted")
        dates = [session.session_date for session in self.sessions]
        if len(dates) != len(set(dates)):
            raise ValueError("calendar session dates must be unique")
        if any(
            session_date < self.horizon_start_date
            or session_date > self.horizon_end_date
            for session_date in dates
        ):
            raise ValueError("calendar session lies outside its horizon")
        return self

    def session(self, session_date: date) -> USMarketCalendarSession | None:
        for session in self.sessions:
            if session.session_date == session_date:
                return session
        return None


class USSessionClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_code: USSessionCode
    stop_risk_multiplier: Decimal
    calendar_version_id: str
    calendar_digest: str
    action_time_ms: int


def classify_us_equity_session(
    *,
    calendar: USMarketCalendar,
    action_time_ms: int,
) -> USSessionClassification:
    if action_time_ms <= 0:
        raise ValueError("session action time must be positive")
    timezone = ZoneInfo(calendar.timezone_name)
    local = datetime.fromtimestamp(action_time_ms / 1_000, tz=timezone)
    local_date = local.date()
    if not calendar.horizon_start_date <= local_date <= calendar.horizon_end_date:
        return _classification(calendar, action_time_ms, USSessionCode.UNKNOWN)
    session = calendar.session(local_date)
    if local.weekday() >= 5:
        return _classification(
            calendar,
            action_time_ms,
            USSessionCode.WEEKEND_HOLIDAY,
        )
    if session is None:
        return _classification(calendar, action_time_ms, USSessionCode.UNKNOWN)
    if session.holiday:
        return _classification(
            calendar,
            action_time_ms,
            USSessionCode.WEEKEND_HOLIDAY,
        )
    if (
        session.regular_open_at_ms is None
        or session.regular_close_at_ms is None
    ):
        return _classification(calendar, action_time_ms, USSessionCode.UNKNOWN)
    minute_of_day = local.hour * 60 + local.minute
    if session.regular_open_at_ms <= action_time_ms < session.regular_close_at_ms:
        code = USSessionCode.REGULAR
    elif 4 * 60 <= minute_of_day < 9 * 60 + 30:
        code = USSessionCode.PREMARKET
    elif (
        action_time_ms >= session.regular_close_at_ms
        and minute_of_day < 20 * 60
    ):
        code = USSessionCode.AFTERHOURS
    else:
        code = USSessionCode.OVERNIGHT
    return _classification(calendar, action_time_ms, code)


def _classification(
    calendar: USMarketCalendar,
    action_time_ms: int,
    code: USSessionCode,
) -> USSessionClassification:
    return USSessionClassification(
        session_code=code,
        stop_risk_multiplier=_MULTIPLIERS[code],
        calendar_version_id=calendar.calendar_version_id,
        calendar_digest=calendar.semantic_digest,
        action_time_ms=action_time_ms,
    )
