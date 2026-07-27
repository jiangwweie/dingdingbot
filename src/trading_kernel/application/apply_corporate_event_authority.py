"""Persist corporate-event authority and freeze effective reprofile scopes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.corporate_events import (
    CorporateEvent,
    CorporateEventCoverage,
    CorporateEventKind,
    corporate_action_reprofile_boundary_ms,
)


class ApplyCorporateEventAuthorityRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    coverage: CorporateEventCoverage
    events: tuple[CorporateEvent, ...]
    observed_at_ms: int

    @field_validator("source_name", mode="before")
    @classmethod
    def _require_source(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("corporate-event source must be non-blank")
        return normalized

    @field_validator("observed_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("corporate-event observation time must be positive")
        return value


async def apply_corporate_event_authority(
    uow: KernelUnitOfWork,
    request: ApplyCorporateEventAuthorityRequest,
) -> tuple[str, ...]:
    await uow.product_admission.replace_corporate_event_authority(
        coverage=request.coverage,
        events=request.events,
        source_name=request.source_name,
        observed_at_ms=request.observed_at_ms,
    )
    authority = await uow.product_admission.load_current_authority(
        request.coverage.exchange_instrument_id
    )
    if authority is None:
        return ()
    required_boundaries = tuple(
        corporate_action_reprofile_boundary_ms(event)
        for event in request.events
        if (
            event.status == "active"
            and event.event_kind
            in {
                CorporateEventKind.SPLIT,
                CorporateEventKind.CONTRACT_ADJUSTMENT,
            }
            and corporate_action_reprofile_boundary_ms(event)
            <= request.observed_at_ms
            and authority.profile.observed_at_ms
            <= corporate_action_reprofile_boundary_ms(event)
        )
    )
    if not required_boundaries:
        return ()
    return await uow.strategy_universes.freeze_for_corporate_action(
        exchange_instrument_id=request.coverage.exchange_instrument_id,
        required_at_ms=max(required_boundaries),
    )
