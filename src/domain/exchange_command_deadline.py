"""Pure deadline and protection-reserve decisions for exchange commands."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


ExchangeCommandRole = Literal["ENTRY", "SL", "TP1"]


class ExchangeCommandDeadlineBudget(BaseModel):
    """One immutable lifecycle invocation budget shared by every phase."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    absolute_deadline_at: float = Field(gt=0)
    entry_network_timeout_seconds: float = Field(default=6.0, gt=0)
    initial_stop_network_timeout_seconds: float = Field(default=6.0, gt=0)
    tp1_network_timeout_seconds: float = Field(default=4.0, gt=0)
    deadline_commit_margin_seconds: float = Field(default=5.0, gt=0)
    entry_result_commit_reserve_seconds: float = Field(default=1.0, ge=0)
    initial_stop_result_commit_reserve_seconds: float = Field(default=1.0, ge=0)
    shutdown_reserve_seconds: float = Field(default=1.0, ge=0)

    @computed_field
    @property
    def pre_entry_reserve_seconds(self) -> float:
        return (
            self.entry_network_timeout_seconds
            + self.entry_result_commit_reserve_seconds
            + self.initial_stop_network_timeout_seconds
            + self.initial_stop_result_commit_reserve_seconds
            + self.shutdown_reserve_seconds
        )

    def configured_timeout_seconds(self, role: ExchangeCommandRole) -> float:
        return {
            "ENTRY": self.entry_network_timeout_seconds,
            "SL": self.initial_stop_network_timeout_seconds,
            "TP1": self.tp1_network_timeout_seconds,
        }[role]


class ExchangePhaseDeadlineDecision(BaseModel):
    """Auditable network-I/O decision for one command phase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    role: ExchangeCommandRole
    blocker: str | None = None
    absolute_deadline_at: float
    deadline_remaining_seconds: float
    configured_timeout_seconds: float
    effective_timeout_seconds: float | None = None
    required_lease_ms: int | None = None
    pre_entry_reserve_seconds: float | None = None


def decide_exchange_phase_budget(
    budget: ExchangeCommandDeadlineBudget,
    *,
    role: ExchangeCommandRole,
    monotonic_now: float,
    lease_ms: int,
    legacy_timeout_cap_seconds: float | None,
    require_pre_entry_reserve: bool,
) -> ExchangePhaseDeadlineDecision:
    """Return the one fail-closed phase decision without performing I/O."""

    if lease_ms <= 0:
        raise ValueError("exchange_command_claim_lease_invalid")
    if not math.isfinite(monotonic_now):
        raise ValueError("exchange_command_monotonic_now_invalid")
    if legacy_timeout_cap_seconds is not None and (
        not math.isfinite(legacy_timeout_cap_seconds)
        or legacy_timeout_cap_seconds <= 0
    ):
        raise ValueError("exchange_command_dispatch_timeout_invalid")
    remaining = max(0.0, budget.absolute_deadline_at - monotonic_now)
    configured = budget.configured_timeout_seconds(role)
    base = {
        "role": role,
        "absolute_deadline_at": budget.absolute_deadline_at,
        "deadline_remaining_seconds": remaining,
        "configured_timeout_seconds": configured,
        "pre_entry_reserve_seconds": (
            budget.pre_entry_reserve_seconds
            if require_pre_entry_reserve
            else None
        ),
    }
    if (
        require_pre_entry_reserve
        and remaining < budget.pre_entry_reserve_seconds
    ):
        return ExchangePhaseDeadlineDecision(
            allowed=False,
            blocker="protection_deadline_budget_insufficient_before_entry",
            **base,
        )
    available_for_network = remaining - budget.deadline_commit_margin_seconds
    if available_for_network <= 0:
        return ExchangePhaseDeadlineDecision(
            allowed=False,
            blocker="exchange_command_deadline_budget_exhausted_before_io",
            **base,
        )
    effective = min(configured, available_for_network)
    if legacy_timeout_cap_seconds is not None:
        effective = min(effective, legacy_timeout_cap_seconds)
    if effective <= 0:
        return ExchangePhaseDeadlineDecision(
            allowed=False,
            blocker="exchange_command_deadline_budget_exhausted_before_io",
            **base,
        )
    required_lease_ms = math.ceil(effective * 1000) + math.ceil(
        budget.deadline_commit_margin_seconds * 1000
    )
    if lease_ms < required_lease_ms:
        return ExchangePhaseDeadlineDecision(
            allowed=False,
            blocker="exchange_command_lease_timeout_budget_invalid",
            effective_timeout_seconds=effective,
            required_lease_ms=required_lease_ms,
            **base,
        )
    return ExchangePhaseDeadlineDecision(
        allowed=True,
        effective_timeout_seconds=effective,
        required_lease_ms=required_lease_ms,
        **base,
    )
