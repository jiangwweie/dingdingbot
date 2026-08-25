"""Pure Owner control-plane states and transition rules."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator


class StrategyEntryState(StrEnum):
    ENABLED = "enabled"
    PAUSED = "paused"


class ControlOperationState(StrEnum):
    VALIDATING = "validating"
    PENDING = "pending"
    CLAIMED = "claimed"
    EXITS_REQUESTED = "exits_requested"
    EXIT_IN_PROGRESS = "exit_in_progress"
    RECONCILIATION_PENDING = "reconciliation_pending"
    SETTLEMENT_PENDING = "settlement_pending"
    REVIEW_PENDING = "review_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    NEEDS_INTERVENTION = "needs_intervention"


class StrategyEntryControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    entry_state: StrategyEntryState
    control_version: int
    last_event_id: str
    reason: str
    updated_at_ms: int

    @field_validator("strategy_group_id", "last_event_id", "reason", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("control identity must be non-blank")
        return normalized

    @field_validator("control_version", "updated_at_ms")
    @classmethod
    def _require_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("control version and time must be positive")
        return value


class OwnerAuthorization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    purpose: Literal[
        "strategy_pause",
        "strategy_resume",
        "entry_pause",
        "entry_resume",
        "owner_flatten_all",
        "universe_configure",
        "selection_mode_change",
    ]
    owner_identity: str
    authentication_strength: Literal["session", "totp_step_up"]
    request_digest: str
    target_scope: dict[str, JsonValue]
    idempotency_key: str
    authorized_at_ms: int

    @field_validator(
        "authorization_id",
        "owner_identity",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _require_nonblank(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("authorization identity must be non-blank")
        return normalized

    @field_validator("request_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("request digest must be canonical sha256")
        return value

    @field_validator("authorized_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("authorization time must be positive")
        return value


class OwnerControlOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    operation_kind: Literal["flatten_all"] = "flatten_all"
    state: ControlOperationState
    version: int
    runtime_profile_id: str
    venue_id: str
    account_id: str
    target_ticket_ids: tuple[str, ...] = ()
    snapshot_digest: str
    first_blocker: str | None = None
    claimed_by: str | None = None
    lease_until_ms: int | None = None
    created_at_ms: int
    updated_at_ms: int


def transition_strategy_entry_control(
    current: StrategyEntryControl,
    *,
    target_state: StrategyEntryState,
    event_id: str,
    reason: str,
    now_ms: int,
) -> StrategyEntryControl:
    """Return the next immutable projection, or the same object for a no-op."""

    if current.entry_state is target_state:
        return current
    return StrategyEntryControl(
        strategy_group_id=current.strategy_group_id,
        entry_state=target_state,
        control_version=current.control_version + 1,
        last_event_id=event_id,
        reason=reason,
        updated_at_ms=now_ms,
    )


_ALLOWED_OPERATION_TRANSITIONS = {
    ControlOperationState.VALIDATING: {
        ControlOperationState.PENDING,
        ControlOperationState.BLOCKED,
        ControlOperationState.COMPLETED,
    },
    ControlOperationState.PENDING: {
        ControlOperationState.CLAIMED,
        ControlOperationState.BLOCKED,
    },
    ControlOperationState.CLAIMED: {
        ControlOperationState.EXITS_REQUESTED,
        ControlOperationState.BLOCKED,
    },
    ControlOperationState.EXITS_REQUESTED: {
        ControlOperationState.EXIT_IN_PROGRESS,
        ControlOperationState.RECONCILIATION_PENDING,
        ControlOperationState.NEEDS_INTERVENTION,
    },
    ControlOperationState.EXIT_IN_PROGRESS: {
        ControlOperationState.RECONCILIATION_PENDING,
        ControlOperationState.NEEDS_INTERVENTION,
    },
    ControlOperationState.RECONCILIATION_PENDING: {
        ControlOperationState.SETTLEMENT_PENDING,
        ControlOperationState.NEEDS_INTERVENTION,
    },
    ControlOperationState.SETTLEMENT_PENDING: {
        ControlOperationState.REVIEW_PENDING,
        ControlOperationState.NEEDS_INTERVENTION,
    },
    ControlOperationState.REVIEW_PENDING: {
        ControlOperationState.COMPLETED,
        ControlOperationState.NEEDS_INTERVENTION,
    },
    ControlOperationState.NEEDS_INTERVENTION: {
        ControlOperationState.COMPLETED,
    },
}


def advance_control_operation(
    current: ControlOperationState,
    target: ControlOperationState,
) -> ControlOperationState:
    """Validate one explicit state transition."""

    if current is target:
        return current
    if target not in _ALLOWED_OPERATION_TRANSITIONS.get(current, set()):
        raise ValueError(
            f"invalid control operation transition: {current.value}->{target.value}"
        )
    return target
