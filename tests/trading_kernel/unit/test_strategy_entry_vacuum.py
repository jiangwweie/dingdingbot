from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
    transition_strategy_entry_vacuum,
)
from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseLifecycleState,
    StrategyUniverseSourceKind,
    advance_strategy_universe_lifecycle,
    strategy_universe_allows_signal,
)


def test_entry_vacuum_is_a_forward_only_new_entry_fence() -> None:
    vacuum = _vacuum()

    assert vacuum.blocks_new_entry is True
    assert vacuum.blocks_existing_ticket_lifecycle is False
    assert vacuum.rewrites_existing_lineage is False


def test_entry_vacuum_rejects_terminal_state_without_resolution_time() -> None:
    with pytest.raises(ValidationError, match="terminal Vacuum requires resolution time"):
        _vacuum(state=StrategyEntryVacuumState.VALID_EMPTY)


def test_entry_vacuum_transitions_are_explicit_and_terminal() -> None:
    assert transition_strategy_entry_vacuum(
        StrategyEntryVacuumState.OPEN,
        StrategyEntryVacuumState.DRAINING_ENTRY,
    ) is StrategyEntryVacuumState.DRAINING_ENTRY
    assert transition_strategy_entry_vacuum(
        StrategyEntryVacuumState.DRAINING_ENTRY,
        StrategyEntryVacuumState.RECONFIGURING,
    ) is StrategyEntryVacuumState.RECONFIGURING

    with pytest.raises(ValueError, match="invalid Strategy Entry Vacuum transition"):
        transition_strategy_entry_vacuum(
            StrategyEntryVacuumState.VALID_EMPTY,
            StrategyEntryVacuumState.OPEN,
        )


def test_valid_empty_may_preserve_prior_generation_provenance() -> None:
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000",
        strategy_group_id="SOR-001",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=1_704_067_200_000,
        source_generation_id="generation:superseded-before-empty",
        state=StrategyEntryVacuumState.VALID_EMPTY,
        fenced_at_ms=1_704_070_800_000,
        drained_at_ms=1_704_071_000_000,
        resolved_at_ms=1_704_071_100_000,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=3,
    )

    assert vacuum.blocks_new_entry is True
    assert vacuum.source_generation_id == "generation:superseded-before-empty"


def test_dynamic_universe_requires_staged_before_active() -> None:
    assert advance_strategy_universe_lifecycle(
        source_kind=StrategyUniverseSourceKind.DYNAMIC_SELECTION,
        current=StrategyUniverseLifecycleState.WARMING,
        target=StrategyUniverseLifecycleState.STAGED,
    ) is StrategyUniverseLifecycleState.STAGED
    assert advance_strategy_universe_lifecycle(
        source_kind=StrategyUniverseSourceKind.DYNAMIC_SELECTION,
        current=StrategyUniverseLifecycleState.STAGED,
        target=StrategyUniverseLifecycleState.ACTIVE,
    ) is StrategyUniverseLifecycleState.ACTIVE

    with pytest.raises(ValueError, match="invalid dynamic_selection Universe transition"):
        advance_strategy_universe_lifecycle(
            source_kind=StrategyUniverseSourceKind.DYNAMIC_SELECTION,
            current=StrategyUniverseLifecycleState.WARMING,
            target=StrategyUniverseLifecycleState.ACTIVE,
        )


def test_staged_universe_cannot_signal_and_can_be_abandoned() -> None:
    assert not strategy_universe_allows_signal(StrategyUniverseLifecycleState.STAGED)
    assert strategy_universe_allows_signal(StrategyUniverseLifecycleState.ACTIVE)
    assert advance_strategy_universe_lifecycle(
        source_kind=StrategyUniverseSourceKind.DYNAMIC_SELECTION,
        current=StrategyUniverseLifecycleState.STAGED,
        target=StrategyUniverseLifecycleState.ABANDONED,
    ) is StrategyUniverseLifecycleState.ABANDONED


def test_manual_universe_preserves_existing_warming_to_active_path() -> None:
    assert advance_strategy_universe_lifecycle(
        source_kind=StrategyUniverseSourceKind.MANUAL,
        current=StrategyUniverseLifecycleState.WARMING,
        target=StrategyUniverseLifecycleState.ACTIVE,
    ) is StrategyUniverseLifecycleState.ACTIVE


def _vacuum(
    *, state: StrategyEntryVacuumState = StrategyEntryVacuumState.OPEN
) -> StrategyEntryVacuum:
    return StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000",
        strategy_group_id="SOR-001",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=1_704_067_200_000,
        source_generation_id=None,
        state=state,
        fenced_at_ms=1_704_070_800_000,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="SELECTION_RECONFIGURATION",
        projection_version=1,
    )
