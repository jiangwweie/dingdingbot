"""Pure negative new-ENTRY fence for StrategyUniverse reconfiguration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)

from src.trading_kernel.domain.instrument_selection import DAY_MS


class StrategyEntryVacuumState(StrEnum):
    OPEN = "OPEN"
    DRAINING_ENTRY = "DRAINING_ENTRY"
    RECONFIGURING = "RECONFIGURING"
    RESOLVED_ACTIVE = "RESOLVED_ACTIVE"
    RESOLVED_FALLBACK = "RESOLVED_FALLBACK"
    VALID_EMPTY = "VALID_EMPTY"
    OWNER_PAUSED = "OWNER_PAUSED"
    SUPERSEDED = "SUPERSEDED"
    FAILED_CLOSED = "FAILED_CLOSED"


class StrategyEntryVacuum(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_vacuum_id: str
    strategy_group_id: str
    selection_spec_id: str
    session_start_ms: int
    source_generation_id: str | None
    state: StrategyEntryVacuumState
    fenced_at_ms: int
    drained_at_ms: int | None
    resolved_at_ms: int | None
    first_blocker: str
    projection_version: int

    @field_validator(
        "entry_vacuum_id",
        "strategy_group_id",
        "selection_spec_id",
        "first_blocker",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Strategy Entry Vacuum identity must be non-blank")
        return normalized

    @field_validator("source_generation_id", mode="before")
    @classmethod
    def _normalize_generation(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @property
    def blocks_new_entry(self) -> bool:
        return self.state not in {
            StrategyEntryVacuumState.RESOLVED_ACTIVE,
            StrategyEntryVacuumState.RESOLVED_FALLBACK,
        }

    @property
    def blocks_existing_ticket_lifecycle(self) -> bool:
        return False

    @property
    def rewrites_existing_lineage(self) -> bool:
        return False

    @model_validator(mode="after")
    def _validate_vacuum(self) -> StrategyEntryVacuum:
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("Strategy Entry Vacuum session must be exact 00:00 UTC")
        if self.fenced_at_ms <= 0 or self.projection_version <= 0:
            raise ValueError("Vacuum fence time and projection version must be positive")
        if self.drained_at_ms is not None and self.drained_at_ms < self.fenced_at_ms:
            raise ValueError("Vacuum drain cannot precede its fence")
        if self.resolved_at_ms is not None and (
            self.drained_at_ms is None or self.resolved_at_ms < self.drained_at_ms
        ):
            raise ValueError("Vacuum resolution requires completed ENTRY drain")
        if self.state in _TERMINAL_STATES and self.resolved_at_ms is None:
            raise ValueError("terminal Vacuum requires resolution time")
        if self.state in _DRAINED_STATES and self.drained_at_ms is None:
            raise ValueError("post-drain Vacuum state requires drain time")
        if self.state not in _TERMINAL_STATES and self.resolved_at_ms is not None:
            raise ValueError("non-terminal Vacuum cannot have resolution time")
        if (
            self.state
            in {
                StrategyEntryVacuumState.RECONFIGURING,
                StrategyEntryVacuumState.RESOLVED_ACTIVE,
                StrategyEntryVacuumState.RESOLVED_FALLBACK,
            }
            and self.source_generation_id is None
        ):
            raise ValueError("materialization Vacuum state requires source Generation")
        return self


_TERMINAL_STATES = frozenset(
    {
        StrategyEntryVacuumState.RESOLVED_ACTIVE,
        StrategyEntryVacuumState.RESOLVED_FALLBACK,
        StrategyEntryVacuumState.VALID_EMPTY,
        StrategyEntryVacuumState.FAILED_CLOSED,
    }
)
_DRAINED_STATES = _TERMINAL_STATES | {
    StrategyEntryVacuumState.RECONFIGURING,
}

_LEGAL_TRANSITIONS: dict[
    StrategyEntryVacuumState,
    frozenset[StrategyEntryVacuumState],
] = {
    StrategyEntryVacuumState.OPEN: frozenset(
        {
            StrategyEntryVacuumState.DRAINING_ENTRY,
            StrategyEntryVacuumState.OWNER_PAUSED,
            StrategyEntryVacuumState.SUPERSEDED,
            StrategyEntryVacuumState.FAILED_CLOSED,
        }
    ),
    StrategyEntryVacuumState.DRAINING_ENTRY: frozenset(
        {
            StrategyEntryVacuumState.RECONFIGURING,
            StrategyEntryVacuumState.VALID_EMPTY,
            StrategyEntryVacuumState.OWNER_PAUSED,
            StrategyEntryVacuumState.SUPERSEDED,
            StrategyEntryVacuumState.FAILED_CLOSED,
        }
    ),
    StrategyEntryVacuumState.RECONFIGURING: frozenset(
        {
            StrategyEntryVacuumState.RESOLVED_ACTIVE,
            StrategyEntryVacuumState.RESOLVED_FALLBACK,
            StrategyEntryVacuumState.OWNER_PAUSED,
            StrategyEntryVacuumState.SUPERSEDED,
            StrategyEntryVacuumState.FAILED_CLOSED,
        }
    ),
    StrategyEntryVacuumState.OWNER_PAUSED: frozenset(
        {
            StrategyEntryVacuumState.RECONFIGURING,
            StrategyEntryVacuumState.VALID_EMPTY,
            StrategyEntryVacuumState.SUPERSEDED,
            StrategyEntryVacuumState.FAILED_CLOSED,
        }
    ),
    StrategyEntryVacuumState.SUPERSEDED: frozenset(
        {
            StrategyEntryVacuumState.DRAINING_ENTRY,
            StrategyEntryVacuumState.RECONFIGURING,
            StrategyEntryVacuumState.VALID_EMPTY,
            StrategyEntryVacuumState.OWNER_PAUSED,
            StrategyEntryVacuumState.FAILED_CLOSED,
        }
    ),
}


def transition_strategy_entry_vacuum(
    current: StrategyEntryVacuumState,
    target: StrategyEntryVacuumState,
) -> StrategyEntryVacuumState:
    if current is target:
        return current
    if target not in _LEGAL_TRANSITIONS.get(current, frozenset()):
        raise ValueError(
            f"invalid Strategy Entry Vacuum transition: {current.value} -> {target.value}"
        )
    return target
