import pytest

from src.trading_kernel.domain.generic_selection_core import (
    compute_generic_selection,
)
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR, inputs


def test_cpm_ranks_ties_by_identity_and_is_deterministic() -> None:
    source=inputs("CPM-RO-001")
    first=compute_generic_selection(source)
    assert first.selected_members==source.spec.candidate_ids[:16]
    assert len(first.members)==24
    assert first==compute_generic_selection(source)
    assert first.effective_from_ms==CUTOFF+HOUR
    assert first.expires_at_ms==CUTOFF+5*HOUR


def test_empty_selection_is_successful_and_does_not_backfill_disqualified_ranks() -> None:
    source=inputs("CPM-RO-001")
    windows=tuple(window.model_copy(update={"qualified":False}) if index<16 else window
                  for index,window in enumerate(source.member_windows))
    result=compute_generic_selection(source.model_copy(update={"member_windows":windows}))
    assert result.selected_members==()
    assert result.ready_count==8
    assert all(not member.selected for member in result.members)


def test_mpg_predecessor_keeps_only_retention_band_and_epoch_is_exact() -> None:
    source=inputs("MPG-001")
    first=compute_generic_selection(source)
    assert len(first.selected_members)==12
    second_source=source.model_copy(update={
        "feature_cutoff_at_ms":CUTOFF+HOUR,"decision_at_ms":CUTOFF+HOUR,
        "source_observed_at_ms":CUTOFF+HOUR+10,"committed_at_ms":CUTOFF+HOUR+20,
        "member_windows":tuple(window.model_copy(update={"closed_at_ms":tuple(t+HOUR for t in window.closed_at_ms)}) for window in source.member_windows),
        "predecessor_snapshot":first,
    })
    second=compute_generic_selection(second_source)
    assert second.predecessor_snapshot_id==first.selection_snapshot_id
    assert 12<=len(second.selected_members)<=16
    with pytest.raises(ValueError,match="epoch"):
        compute_generic_selection(second_source.model_copy(update={"selection_epoch_id":"epoch:2"}))


@pytest.mark.parametrize("defect", ["missing","gap","future","duplicate"])
def test_source_integrity_requires_exact_point_in_time_candidate24(defect: str) -> None:
    source=inputs("CPM-RO-001")
    windows=list(source.member_windows)
    if defect=="missing": windows.pop()
    elif defect=="duplicate": windows[-1]=windows[0]
    else:
        times=list(windows[0].closed_at_ms)
        times[-1]+=HOUR if defect=="future" else -HOUR
        windows[0]=windows[0].model_copy(update={"closed_at_ms":tuple(times)})
    with pytest.raises(ValueError):
        compute_generic_selection(source.model_copy(update={"member_windows":tuple(windows)}))


@pytest.mark.parametrize("defect", ["member_count", "duplicate_rank", "wrong_id", "extra_selected"])
def test_snapshot_cannot_supply_forged_hysteresis_memory(defect: str) -> None:
    source=inputs("MPG-001")
    snapshot=compute_generic_selection(source)
    payload=snapshot.model_dump(mode="python")
    if defect=="member_count": payload["members"]=payload["members"][:-1]
    elif defect=="duplicate_rank": payload["members"][1]["stable_rank"]=1
    elif defect=="wrong_id": payload["selection_snapshot_id"]="selection:forged"
    else: payload["members"][-1]["selected"]=True
    with pytest.raises(ValueError):
        type(snapshot).model_validate(payload)
