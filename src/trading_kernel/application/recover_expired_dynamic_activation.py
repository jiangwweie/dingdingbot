"""Recover one expired, Owner-paused first Dynamic activation attempt."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.instrument_selection import (
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.selection_authority import DAY_MS, SelectionMode

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork


class ExpiredDynamicActivationRecoveryStatus(StrEnum):
    RECOVERED = "RECOVERED"


class RecoverExpiredDynamicActivationRequest(BaseModel):
    """Exact identities required to clear one stale first-activation transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    session_start_ms: int
    materialization_generation_id: str
    entry_vacuum_id: str
    authority_gap_audit_id: str
    expected_long_universe_version_id: str
    expected_short_universe_version_id: str
    expected_selection_control_version: int
    expected_owner_control_version: int
    recovered_at_ms: int

    @field_validator(
        "strategy_group_id",
        "selection_spec_id",
        "materialization_generation_id",
        "entry_vacuum_id",
        "authority_gap_audit_id",
        "expected_long_universe_version_id",
        "expected_short_universe_version_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("expired activation recovery identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_request(self) -> RecoverExpiredDynamicActivationRequest:
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("expired activation recovery requires an exact UTC Session")
        if self.recovered_at_ms < self.session_start_ms + DAY_MS:
            raise ValueError("Dynamic activation Session has not expired")
        if (
            self.expected_selection_control_version <= 0
            or self.expected_owner_control_version <= 0
        ):
            raise ValueError("expired activation recovery versions must be positive")
        if (
            self.expected_long_universe_version_id
            == self.expected_short_universe_version_id
        ):
            raise ValueError("expired activation recovery pair must be distinct")
        return self


class RecoverExpiredDynamicActivationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExpiredDynamicActivationRecoveryStatus
    strategy_group_id: str
    selection_spec_id: str
    session_start_ms: int
    materialization_generation_id: str
    selection_control_version: int
    recovered_at_ms: int


class ExpiredDynamicActivationRecoveryBlocked(RuntimeError):
    """The exact failed first-activation shape is not safe to recover."""


async def recover_expired_dynamic_activation(
    uow: KernelUnitOfWork,
    request: RecoverExpiredDynamicActivationRequest,
) -> RecoverExpiredDynamicActivationResult:
    """Clear only the stale pending transition; never create Session Authority."""

    owner_control = await uow.owner_controls.get_strategy_control(
        request.strategy_group_id,
        for_update=True,
    )
    if owner_control is None:
        raise ExpiredDynamicActivationRecoveryBlocked("strategy_control_missing")
    if (
        owner_control.entry_state is not StrategyEntryState.PAUSED
        or owner_control.control_version != request.expected_owner_control_version
    ):
        raise ExpiredDynamicActivationRecoveryBlocked("strategy_not_exactly_paused")

    selection_control = await uow.instrument_selection.get_selection_control(
        request.strategy_group_id,
        for_update=True,
    )
    if selection_control is None:
        raise ExpiredDynamicActivationRecoveryBlocked("selection_control_missing")
    if (
        selection_control.selection_spec_id != request.selection_spec_id
        or selection_control.selection_mode is not SelectionMode.STATIC_BASELINE
        or selection_control.pending_selection_mode is not SelectionMode.DYNAMIC_SELECTION
        or selection_control.pending_effective_session_start_ms
        != request.session_start_ms
        or selection_control.pending_authorization_id is None
        or selection_control.control_version
        != request.expected_selection_control_version
    ):
        raise ExpiredDynamicActivationRecoveryBlocked("selection_control_not_recoverable")

    current_long = await uow.strategy_universes.get_current(SOR_LONG_EVENT_SPEC_ID)
    current_short = await uow.strategy_universes.get_current(SOR_SHORT_EVENT_SPEC_ID)
    if (
        current_long is None
        or current_short is None
        or current_long.universe_version_id
        != request.expected_long_universe_version_id
        or current_short.universe_version_id
        != request.expected_short_universe_version_id
    ):
        raise ExpiredDynamicActivationRecoveryBlocked("current_static_pair_drifted")

    return await uow.instrument_selection.recover_expired_dynamic_activation(request)

