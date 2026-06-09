"""Strategy runtime governance domain models.

These models are shadow-path governance records. They do not place orders,
create execution intents, call FinalGate, or connect to an exchange.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyRuntimeInstanceStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CLOSED = "closed"
    REVIEWED = "reviewed"


TERMINAL_RUNTIME_STATUSES = {
    StrategyRuntimeInstanceStatus.EXHAUSTED,
    StrategyRuntimeInstanceStatus.EXPIRED,
    StrategyRuntimeInstanceStatus.REVOKED,
    StrategyRuntimeInstanceStatus.CLOSED,
    StrategyRuntimeInstanceStatus.REVIEWED,
}


ALLOWED_RUNTIME_TRANSITIONS: dict[
    StrategyRuntimeInstanceStatus,
    set[StrategyRuntimeInstanceStatus],
] = {
    StrategyRuntimeInstanceStatus.DRAFT: {
        StrategyRuntimeInstanceStatus.ACTIVE,
        StrategyRuntimeInstanceStatus.EXPIRED,
        StrategyRuntimeInstanceStatus.REVOKED,
        StrategyRuntimeInstanceStatus.CLOSED,
    },
    StrategyRuntimeInstanceStatus.ACTIVE: {
        StrategyRuntimeInstanceStatus.PAUSED,
        StrategyRuntimeInstanceStatus.EXHAUSTED,
        StrategyRuntimeInstanceStatus.EXPIRED,
        StrategyRuntimeInstanceStatus.REVOKED,
        StrategyRuntimeInstanceStatus.CLOSED,
    },
    StrategyRuntimeInstanceStatus.PAUSED: {
        StrategyRuntimeInstanceStatus.ACTIVE,
        StrategyRuntimeInstanceStatus.EXPIRED,
        StrategyRuntimeInstanceStatus.REVOKED,
        StrategyRuntimeInstanceStatus.CLOSED,
    },
    StrategyRuntimeInstanceStatus.EXHAUSTED: {
        StrategyRuntimeInstanceStatus.REVIEWED,
    },
    StrategyRuntimeInstanceStatus.EXPIRED: {
        StrategyRuntimeInstanceStatus.REVIEWED,
    },
    StrategyRuntimeInstanceStatus.REVOKED: {
        StrategyRuntimeInstanceStatus.REVIEWED,
    },
    StrategyRuntimeInstanceStatus.CLOSED: {
        StrategyRuntimeInstanceStatus.REVIEWED,
    },
    StrategyRuntimeInstanceStatus.REVIEWED: set(),
}


class StrategyRuntimeBoundary(StrategyRuntimeModel):
    max_attempts: int = Field(ge=1)
    attempts_used: int = Field(default=0, ge=0)
    max_active_positions: int = Field(default=1, ge=0)
    max_notional_per_attempt: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    total_budget: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[str] = Field(default_factory=list)
    max_leverage: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    requires_protection: bool = True
    requires_review: bool = True

    @model_validator(mode="after")
    def _attempts_cannot_exceed_max(self) -> "StrategyRuntimeBoundary":
        if self.attempts_used > self.max_attempts:
            raise ValueError("attempts_used cannot exceed max_attempts")
        return self

    @property
    def attempts_remaining(self) -> int:
        return max(self.max_attempts - self.attempts_used, 0)

    @property
    def budget_remaining(self) -> Optional[Decimal]:
        if self.total_budget is None:
            return None
        if self.max_notional_per_attempt is None:
            return self.total_budget
        used = self.max_notional_per_attempt * Decimal(self.attempts_used)
        return max(self.total_budget - used, Decimal("0"))


class StrategyRuntimePolicySnapshot(StrategyRuntimeModel):
    risk_policy_snapshot: dict[str, Any] = Field(default_factory=dict)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    playbook_snapshot: dict[str, Any] = Field(default_factory=dict)
    admission_execution_mode: Optional[str] = Field(default=None, max_length=64)
    source: str = Field(default="admission_trial_binding", max_length=128)


class StrategyRuntimeAttemptSummary(StrategyRuntimeModel):
    max_attempts: int = Field(ge=1)
    attempts_used: int = Field(ge=0)
    attempts_remaining: int = Field(ge=0)


class StrategyRuntimeReviewRequirement(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NOT_REQUIRED = "not_required"


class StrategyRuntimeEvent(StrategyRuntimeModel):
    event_id: str
    runtime_instance_id: str
    event_type: str = Field(min_length=1, max_length=128)
    previous_status: Optional[StrategyRuntimeInstanceStatus] = None
    next_status: StrategyRuntimeInstanceStatus
    actor: str = Field(default="system", max_length=128)
    reason: str = Field(default="", max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int


class StrategyRuntimeInstance(StrategyRuntimeModel):
    runtime_instance_id: str
    trial_binding_id: str
    admission_decision_id: str
    strategy_family_id: str
    strategy_family_version_id: str
    owner_risk_acceptance_id: Optional[str] = None
    carrier_id: Optional[str] = None
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    status: StrategyRuntimeInstanceStatus
    boundary: StrategyRuntimeBoundary
    policy_snapshot: StrategyRuntimePolicySnapshot = Field(
        default_factory=StrategyRuntimePolicySnapshot
    )
    review_requirement: StrategyRuntimeReviewRequirement = (
        StrategyRuntimeReviewRequirement.REQUIRED
    )
    execution_enabled: bool = False
    shadow_mode: bool = True
    created_at_ms: int
    updated_at_ms: int
    activated_at_ms: Optional[int] = None
    expires_at_ms: Optional[int] = None
    revoked_at_ms: Optional[int] = None
    closed_at_ms: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _shadow_runtime_cannot_execute(self) -> "StrategyRuntimeInstance":
        if self.execution_enabled:
            raise ValueError("StrategyRuntimeInstance shadow path cannot enable execution")
        if not self.shadow_mode:
            raise ValueError("StrategyRuntimeInstance must remain shadow_mode in TD-1")
        normalized_side = self.side.lower()
        if self.boundary.allowed_sides and normalized_side not in {
            item.lower() for item in self.boundary.allowed_sides
        }:
            raise ValueError("runtime side must be allowed by boundary")
        if self.boundary.allowed_symbols and self.symbol not in self.boundary.allowed_symbols:
            raise ValueError("runtime symbol must be allowed by boundary")
        return self

    @property
    def attempts_remaining(self) -> int:
        return self.boundary.attempts_remaining

    @property
    def budget_remaining(self) -> Optional[Decimal]:
        return self.boundary.budget_remaining

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUNTIME_STATUSES

    def transition_to(
        self,
        next_status: StrategyRuntimeInstanceStatus,
        *,
        now_ms: int,
        reason: str = "",
    ) -> "StrategyRuntimeInstance":
        assert_runtime_transition_allowed(self.status, next_status)
        values = self.model_dump()
        values["status"] = next_status
        values["updated_at_ms"] = now_ms
        metadata = dict(self.metadata)
        if reason:
            metadata["last_transition_reason"] = reason
        values["metadata"] = metadata
        if next_status == StrategyRuntimeInstanceStatus.ACTIVE and self.activated_at_ms is None:
            values["activated_at_ms"] = now_ms
        elif next_status == StrategyRuntimeInstanceStatus.REVOKED:
            values["revoked_at_ms"] = now_ms
        elif next_status == StrategyRuntimeInstanceStatus.CLOSED:
            values["closed_at_ms"] = now_ms
        return StrategyRuntimeInstance.model_validate(values)


def assert_runtime_transition_allowed(
    current: StrategyRuntimeInstanceStatus,
    target: StrategyRuntimeInstanceStatus,
) -> None:
    if target not in ALLOWED_RUNTIME_TRANSITIONS[current]:
        raise ValueError(f"invalid runtime status transition: {current.value} -> {target.value}")
