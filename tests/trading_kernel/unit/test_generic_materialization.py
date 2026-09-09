import pytest

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
    MaterializationEventBaseline,
)
from src.trading_kernel.domain.generic_selection_core import compute_generic_selection
from src.trading_kernel.domain.selection_authority import selected_member_set_digest
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR, inputs


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
def test_generation_has_exact_single_event_and_snapshot_epoch(group: str) -> None:
    source = inputs(group)
    snapshot = compute_generic_selection(source)
    comparison = group in {"MPG-001", "MI-001"}
    prior = MaterializationEventBaseline(event_spec_id=source.spec.event_spec_id, position_side=source.spec.position_side,
        grant_state="ACTIVE", universe_version_id="universe:previous", member_set_digest=selected_member_set_digest(source.spec.candidate_ids[:1]),
        comparison_universe_id="comparison:previous" if comparison else None, comparison_transition_revision=0 if comparison else None)
    generation = GenericMaterializationGeneration.build(snapshot=snapshot, previous_events=(prior,), selection_control_version=2,
        created_at_ms=CUTOFF+HOUR+1)
    assert generation.selection_epoch_id == snapshot.selection_epoch_id
    assert generation.period_anchor_ms == CUTOFF
    assert generation.desired_member_count == len(snapshot.selected_members)
    assert generation.materialization_generation_id == "generation:" + canonical_digest({"snapshot": snapshot.selection_snapshot_id})[7:]
    assert generation.semantic_digest == type(generation).model_validate(generation.model_dump()).semantic_digest
    for field, value in (("selection_epoch_id", "other"), ("selection_snapshot_id", "wrong"), ("previous_events", ()), ("created_at_ms", CUTOFF)):
        with pytest.raises(ValueError):
            type(generation).model_validate(generation.model_copy(update={field: value}).model_dump())


def test_valid_empty_has_no_materialization_generation() -> None:
    from tests.trading_kernel.support.generic_selection import qualify_window
    source = inputs("CPM-RO-001")
    source = source.model_copy(update={"member_windows": tuple(qualify_window(w, False) for w in source.member_windows)})
    with pytest.raises(ValueError, match="empty"):
        GenericMaterializationGeneration.build(snapshot=compute_generic_selection(source), previous_events=(), selection_control_version=2,
            created_at_ms=CUTOFF+HOUR+1)
