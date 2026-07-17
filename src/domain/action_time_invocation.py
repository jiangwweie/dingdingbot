"""Typed causal context for one exact fresh-signal Action-Time attempt."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.runtime_lane_identity import RuntimeLaneIdentity


class ActionTimeInvocation(BaseModel):
    """Immutable signal lineage plus mutable exact fact references.

    This model is deliberately not a trade lifecycle. It exists only before a
    Ticket and cannot represent an order, position, protection, or settlement
    state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_time_invocation_id: str = Field(min_length=1, max_length=192)
    signal_event_id: str = Field(min_length=1, max_length=192)
    lane_identity: RuntimeLaneIdentity
    source_watermark: str = Field(min_length=1, max_length=256)
    opened_at_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    account_safe_fact_snapshot_id: str | None = Field(default=None, max_length=256)
    account_capacity_base_fact_snapshot_id: str | None = Field(
        default=None, max_length=256
    )
    account_mode_fact_snapshot_id: str | None = Field(default=None, max_length=256)
    action_time_fact_snapshot_id: str | None = Field(default=None, max_length=256)
    ticket_id: str | None = Field(default=None, max_length=192)
    closed_at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_time_bounds(self) -> "ActionTimeInvocation":
        if self.expires_at_ms <= self.opened_at_ms:
            raise ValueError("action_time_invocation_deadline_not_after_opening")
        if self.closed_at_ms is not None and self.closed_at_ms < self.opened_at_ms:
            raise ValueError("action_time_invocation_close_before_opening")
        if (
            self.account_safe_fact_snapshot_id is not None
            and self.account_capacity_base_fact_snapshot_id is not None
        ):
            raise ValueError("action_time_invocation_account_fact_pair_ambiguous")
        return self


class ActionTimeInvocationEvidence(BaseModel):
    """The exact, stage-local inputs allowed to reach promotion.

    This is transient typed evidence, not another current projection and not a
    business lifecycle.  Its references are durable PG rows owned by the
    invocation; the model simply prevents the Action-Time path from falling
    back to a generic Candidate Pool readiness row.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    invocation: ActionTimeInvocation
    stage_at_ms: int = Field(ge=0)
    public_fact_snapshot_id: str = Field(min_length=1, max_length=256)
    account_safe_fact_snapshot_id: str | None = Field(default=None, max_length=256)
    account_capacity_base_fact_snapshot_id: str | None = Field(
        default=None, max_length=256
    )
    account_mode_fact_snapshot_id: str = Field(min_length=1, max_length=256)
    action_time_fact_snapshot_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_stage_and_deadline(self) -> "ActionTimeInvocationEvidence":
        if self.stage_at_ms < self.invocation.opened_at_ms:
            raise ValueError("action_time_invocation_stage_before_opening")
        if self.stage_at_ms >= self.invocation.expires_at_ms:
            raise ValueError("action_time_invocation_stage_expired")
        if (
            self.account_safe_fact_snapshot_id is None
            and self.account_capacity_base_fact_snapshot_id is None
        ) or (
            self.account_safe_fact_snapshot_id is not None
            and self.account_capacity_base_fact_snapshot_id is not None
        ):
            raise ValueError("action_time_invocation_account_fact_pair_invalid")
        return self

    @property
    def account_capacity_fact_surface(self) -> str:
        return (
            "account_capacity_base"
            if self.account_capacity_base_fact_snapshot_id is not None
            else "account_safe"
        )

    @property
    def account_capacity_fact_snapshot_id(self) -> str:
        return (
            self.account_capacity_base_fact_snapshot_id
            or self.account_safe_fact_snapshot_id
            or ""
        )


class ActionTimeInvocationBlocked(ValueError):
    """A typed, non-order blocker while entering Action-Time."""

    def __init__(self, blocker: str) -> None:
        super().__init__(blocker)
        self.blocker = blocker
