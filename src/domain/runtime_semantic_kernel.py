"""Stable, pure runtime semantics shared by execution-chain consumers.

The kernel deliberately owns only the small vocabulary that must agree across
Signal/Invocation/Ticket/Command/Lifecycle and current read models.  Product
specific status strings remain at their owning aggregate; they are translated
at the boundary instead of being copied into another global status enum.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuntimePhase(str, Enum):
    OBSERVATION = "observation"
    SELECTION = "selection"
    PRE_SUBMIT = "pre_submit"
    SUBMITTED = "submitted"
    PROTECTED = "protected"
    EXIT = "exit"
    CLOSURE = "closure"


class RuntimeState(str, Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    TERMINAL = "terminal"
    OUTCOME_UNKNOWN = "outcome_unknown"


class TerminalKind(str, Enum):
    SELECTED = "selected"
    NOT_SELECTED = "not_selected"
    EXPIRED = "expired"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RuntimeSemanticState:
    """One aggregate-neutral current-state classification.

    ``outcome_unknown`` is intentionally active and operationally relevant:
    it conserves capacity and requires reconciliation.  It must never be
    mistaken for a harmless terminal result.
    """

    phase: RuntimePhase
    state: RuntimeState
    reason_code: str = ""
    terminal_kind: TerminalKind | None = None

    def __post_init__(self) -> None:
        if self.state is RuntimeState.TERMINAL and self.terminal_kind is None:
            raise ValueError("terminal_runtime_state_requires_terminal_kind")
        if self.state is not RuntimeState.TERMINAL and self.terminal_kind is not None:
            raise ValueError("nonterminal_runtime_state_forbids_terminal_kind")
        if self.state is RuntimeState.OUTCOME_UNKNOWN and not self.reason_code:
            raise ValueError("outcome_unknown_requires_reason_code")

    @property
    def is_terminal(self) -> bool:
        return self.state is RuntimeState.TERMINAL

    @property
    def is_active(self) -> bool:
        return not self.is_terminal

    @property
    def is_current(self) -> bool:
        """Whether this state still belongs in the operational current view."""

        return self.is_active

    @property
    def is_operationally_relevant(self) -> bool:
        """Whether operators/reducers must continue to act on this state."""

        return self.state in {
            RuntimeState.RUNNING,
            RuntimeState.BLOCKED,
            RuntimeState.OUTCOME_UNKNOWN,
        }


def require_legal_runtime_transition(
    current: RuntimeSemanticState | None,
    target: RuntimeSemanticState,
) -> RuntimeSemanticState:
    """Validate the only cross-aggregate invariant: terminal is irreversible.

    Aggregate-specific transition graphs remain local.  This avoids turning the
    kernel into a universal lifecycle while still preventing a completed or
    rejected Signal/Ticket/Command from being silently reopened by a stale
    projector.
    """

    if current is None:
        return target
    if current.is_terminal and target != current:
        raise ValueError("runtime_semantic_terminal_transition_forbidden")
    return target


def semantic_state_for_process_outcome(
    *,
    process_state: str,
    reason_code: str = "",
) -> RuntimeSemanticState:
    """Translate the runtime-process contract without duplicating status sets."""

    normalized = str(process_state or "").strip()
    if normalized in {"succeeded", "noop"}:
        return RuntimeSemanticState(
            phase=RuntimePhase.OBSERVATION,
            state=RuntimeState.RUNNING,
            reason_code=reason_code,
        )
    if normalized == "business_blocked":
        return RuntimeSemanticState(
            phase=RuntimePhase.SELECTION,
            state=RuntimeState.BLOCKED,
            reason_code=reason_code,
        )
    if normalized in {"retryable_failure", "hard_failure"}:
        return RuntimeSemanticState(
            phase=RuntimePhase.SELECTION,
            state=RuntimeState.BLOCKED,
            reason_code=reason_code or normalized,
        )
    raise ValueError(f"unsupported_runtime_process_state:{normalized or 'missing'}")
