"""Fail-closed earnings and corporate-action ENTRY admission."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, model_validator


class CorporateEventKind(StrEnum):
    EARNINGS = "earnings"
    SPLIT = "split"
    CONTRACT_ADJUSTMENT = "contract_adjustment"


class CorporateEventCertainty(StrEnum):
    EXACT_TIME = "exact_time"
    DATE_ONLY = "date_only"


class CorporateEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    corporate_event_version_id: str
    exchange_instrument_id: str
    event_kind: CorporateEventKind
    certainty: CorporateEventCertainty
    event_date: date
    effective_at_ms: int | None
    status: str

    @model_validator(mode="after")
    def _validate_event(self) -> "CorporateEvent":
        if (
            self.certainty is CorporateEventCertainty.EXACT_TIME
            and (self.effective_at_ms is None or self.effective_at_ms <= 0)
        ):
            raise ValueError("exact-time corporate event requires effective time")
        if (
            self.certainty is CorporateEventCertainty.DATE_ONLY
            and self.effective_at_ms is not None
        ):
            raise ValueError("date-only corporate event forbids effective time")
        return self


class CorporateEventCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_id: str
    exchange_instrument_id: str
    coverage_start_ms: int
    coverage_end_ms: int
    coverage_status: str
    valid_until_ms: int
    coverage_digest: str

    @model_validator(mode="after")
    def _validate_coverage(self) -> "CorporateEventCoverage":
        if (
            self.coverage_start_ms <= 0
            or self.coverage_end_ms <= self.coverage_start_ms
            or self.valid_until_ms <= 0
        ):
            raise ValueError("corporate-event coverage window is invalid")
        return self


class CorporateEventAdmission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason_code: str


def evaluate_corporate_event_admission(
    *,
    action_time_ms: int,
    exchange_instrument_id: str,
    coverage: CorporateEventCoverage | None,
    events: tuple[CorporateEvent, ...],
    closed_15m_bars_after_event: int,
    product_profile_observed_at_ms: int | None = None,
) -> CorporateEventAdmission:
    if action_time_ms <= 0 or closed_15m_bars_after_event < 0:
        raise ValueError("corporate-event admission inputs are invalid")
    if coverage is None:
        return _blocked("corporate_event_coverage_missing")
    if (
        coverage.exchange_instrument_id != exchange_instrument_id
        or coverage.coverage_status != "complete"
        or not coverage.coverage_start_ms
        <= action_time_ms
        <= coverage.coverage_end_ms
        or action_time_ms >= coverage.valid_until_ms
    ):
        return _blocked("corporate_event_coverage_stale_or_incomplete")
    local_date = datetime.fromtimestamp(
        action_time_ms / 1_000,
        tz=ZoneInfo("America/New_York"),
    ).date()
    for event in events:
        if (
            event.exchange_instrument_id != exchange_instrument_id
            or event.status != "active"
        ):
            continue
        if event.event_kind in {
            CorporateEventKind.SPLIT,
            CorporateEventKind.CONTRACT_ADJUSTMENT,
        }:
            reprofile_boundary_ms = corporate_action_reprofile_boundary_ms(
                event
            )
            if (
                action_time_ms >= reprofile_boundary_ms
                and (
                    product_profile_observed_at_ms is None
                    or product_profile_observed_at_ms
                    <= reprofile_boundary_ms
                )
            ):
                return _blocked("corporate_action_reprofile_required")
            continue
        if event.certainty is CorporateEventCertainty.DATE_ONLY:
            if local_date == event.event_date:
                return _blocked("earnings_date_only_blackout")
            continue
        effective_at_ms = event.effective_at_ms
        if effective_at_ms is None:
            return _blocked("corporate_event_identity_invalid")
        if effective_at_ms - 4 * 3_600_000 <= action_time_ms < effective_at_ms:
            return _blocked("earnings_blackout_pre_release")
        if (
            action_time_ms >= effective_at_ms
            and closed_15m_bars_after_event < 2
        ):
            return _blocked("earnings_waiting_closed_bars")
    return CorporateEventAdmission(
        allowed=True,
        reason_code="corporate_event_clear",
    )


def _blocked(reason: str) -> CorporateEventAdmission:
    return CorporateEventAdmission(allowed=False, reason_code=reason)


def corporate_action_reprofile_boundary_ms(event: CorporateEvent) -> int:
    if event.effective_at_ms is not None:
        return event.effective_at_ms
    local_midnight = datetime.combine(
        event.event_date,
        datetime.min.time(),
        tzinfo=ZoneInfo("America/New_York"),
    )
    return int(local_midnight.timestamp() * 1_000)
