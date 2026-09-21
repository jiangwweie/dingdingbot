import pytest

from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    GenericSelectionAuthority,
    selected_member_set_digest,
)


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
def test_generic_authority_binds_exact_event_period_and_precommitted_close(group):
    spec = generic_selection_spec(group)
    period = build_generic_selection_period(feature_cutoff_at_ms=100*3_600_000,cadence_hours=spec.cadence_hours)
    grant = period.scheduled_effective_at_ms+8_000
    binding = AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        grant_state="ACTIVE",universe_version_id="universe:target",member_set_digest=selected_member_set_digest(spec.candidate_ids[:1]))
    proof = CurrentFinalCloseGrantProof(selection_snapshot_id="snapshot:test",selection_committed_at_ms=period.feature_cutoff_at_ms+1,
        source_snapshot_cutoff_at_ms=period.feature_cutoff_at_ms,period=period,
        current_final_close_time_ms=period.scheduled_effective_at_ms,authority_granted_at_ms=grant,observation_cursor_version=1)
    authority = GenericSelectionAuthority(selection_authority_id="authority:test",selection_spec_id=spec.selection_spec_id,
        strategy_group_id=group,selection_epoch_id="epoch:1",selection_snapshot_id="snapshot:test",
        materialization_generation_id="generation:test",
        authority_sequence=1,owner_control_version=1,selection_control_version=1,
        comparison_universe_id=("comparison:"+canonical_digest({"exchange_instrument_ids":spec.candidate_ids})[7:] if group in {"MPG-001","MI-001"} else None),
        comparison_transition_revision=1 if group in {"MPG-001","MI-001"} else None,
        period=period,authority_outcome="ACTIVE_NEW",event_binding=binding,current_close_proof=proof,
        membership_freshness=build_dynamic_membership_freshness(source_snapshot_id="snapshot:test",
            source_member_set_digest=binding.member_set_digest,period=period),
        effective_from_ms=grant,created_at_ms=grant)
    assert authority.first_eligible_close_time_ms == period.scheduled_effective_at_ms
    for changes in ({"selection_snapshot_id":"snapshot:other"}, {"effective_from_ms":grant+1},
                    {"current_close_proof":None}, {"materialization_generation_id":None},
                    {"authority_outcome":"FALLBACK_PREVIOUS"},
                    {"membership_freshness":authority.membership_freshness.model_copy(update={"source_snapshot_id":"snapshot:old"})},
                    {"event_binding":binding.model_copy(update={"position_side":"short" if spec.position_side=="long" else "long"})}):
        with pytest.raises(ValueError):
            GenericSelectionAuthority.model_validate({**authority.model_dump(),**changes})
    empty = GenericSelectionAuthority.model_validate({**authority.model_dump(),"authority_outcome":"VALID_EMPTY",
        "materialization_generation_id":None,
        "event_binding":AuthorityEventBinding.empty(event_spec_id=spec.event_spec_id,position_side=spec.position_side),
        "current_close_proof":None,"membership_freshness":None})
    assert empty.blocks_new_entry and empty.first_eligible_close_time_ms is None
    with pytest.raises(ValueError):
        GenericSelectionAuthority.model_validate({**empty.model_dump(),"event_binding":binding})
    with pytest.raises(ValueError, match="Generation"):
        GenericSelectionAuthority.model_validate({**empty.model_dump(),"materialization_generation_id":"generation:wrong"})
