from decimal import Decimal

import pytest

from src.trading_kernel.domain.generic_selection_spec import (
    GenericSelectionSpecV1,
    SpecNumericInstallationEvidence,
    generic_selection_spec,
)


@pytest.mark.parametrize("group,entry,retain,cadence,bars", [
    ("CPM-RO-001",16,16,4,25), ("MPG-001",12,16,1,14),
    ("MI-001",16,16,1,13), ("BRF2-001",16,16,4,73),
])
def test_spec_freezes_only_approved_strategy_parameters(group: str,entry: int,retain: int,cadence: int,bars: int) -> None:
    spec = generic_selection_spec(group)
    assert (spec.entry_rank,spec.retain_rank,spec.cadence_hours,spec.window_bars)==(entry,retain,cadence,bars)
    assert spec.delay_ms == 3600000
    assert len(spec.candidate_ids)==24
    assert spec.decimal_precision==38
    with pytest.raises(ValueError):
        GenericSelectionSpecV1.model_validate({**spec.model_dump(), "entry_rank":8})


def test_selector_cannot_be_relabelled_as_another_strategy_or_sor() -> None:
    spec=generic_selection_spec("CPM-RO-001")
    with pytest.raises(ValueError):
        GenericSelectionSpecV1.model_validate({**spec.model_dump(), "strategy_group_id":"MI-001"})
    with pytest.raises(ValueError):
        generic_selection_spec("SOR-001")
    with pytest.raises(ValueError):
        GenericSelectionSpecV1.model_validate({**spec.model_dump(), "activity_floor":Decimal(20000000)})


def test_failed_or_wrong_spec_evidence_cannot_authorize_installation() -> None:
    spec=generic_selection_spec("BRF2-001")
    certificate=SpecNumericInstallationEvidence(selection_spec_id=spec.selection_spec_id,
        algorithm_semantic_digest=spec.algorithm_semantic_digest,checked_cutoffs=463,mismatch_count=0,
        source_archive_count=96,reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",
        common_numeric_authority="PASS",sor_golden="PASS",spec_cert="PASS")
    certificate.require_spec(spec)
    with pytest.raises(ValueError):
        certificate.model_copy(update={"mismatch_count":1}).require_spec(spec)
    with pytest.raises(ValueError):
        certificate.model_copy(update={"checked_cutoffs":462}).require_spec(spec)
    with pytest.raises(ValueError):
        certificate.require_spec(generic_selection_spec("CPM-RO-001"))
