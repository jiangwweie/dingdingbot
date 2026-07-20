from __future__ import annotations

import pytest

from src.domain.runtime_semantic_kernel import (
    RuntimePhase,
    RuntimeSemanticState,
    RuntimeState,
    TerminalKind,
    require_legal_runtime_transition,
    semantic_state_for_process_outcome,
)


def test_outcome_unknown_is_active_current_and_operationally_relevant():
    state = RuntimeSemanticState(
        phase=RuntimePhase.SUBMITTED,
        state=RuntimeState.OUTCOME_UNKNOWN,
        reason_code="exchange_command_outcome_unknown",
    )

    assert state.is_terminal is False
    assert state.is_active is True
    assert state.is_current is True
    assert state.is_operationally_relevant is True


def test_terminal_state_requires_kind_and_cannot_be_reopened():
    terminal = RuntimeSemanticState(
        phase=RuntimePhase.CLOSURE,
        state=RuntimeState.TERMINAL,
        terminal_kind=TerminalKind.COMPLETED,
    )
    with pytest.raises(ValueError, match="terminal_runtime_state_requires_terminal_kind"):
        RuntimeSemanticState(
            phase=RuntimePhase.CLOSURE,
            state=RuntimeState.TERMINAL,
        )
    with pytest.raises(ValueError, match="runtime_semantic_terminal_transition_forbidden"):
        require_legal_runtime_transition(
            terminal,
            RuntimeSemanticState(
                phase=RuntimePhase.EXIT,
                state=RuntimeState.RUNNING,
            ),
        )


@pytest.mark.parametrize(
    ("process_state", "expected_state"),
    [
        ("succeeded", RuntimeState.RUNNING),
        ("noop", RuntimeState.RUNNING),
        ("business_blocked", RuntimeState.BLOCKED),
        ("retryable_failure", RuntimeState.BLOCKED),
        ("hard_failure", RuntimeState.BLOCKED),
    ],
)
def test_process_outcomes_share_one_semantic_translation(
    process_state: str,
    expected_state: RuntimeState,
):
    state = semantic_state_for_process_outcome(
        process_state=process_state,
        reason_code="typed_reason",
    )

    assert state.state is expected_state
