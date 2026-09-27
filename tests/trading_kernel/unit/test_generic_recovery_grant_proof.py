import pytest

from src.trading_kernel.domain.dynamic_selection_timing import (
    build_dynamic_membership_freshness,
    build_generic_selection_period,
    plan_hourly_recovery_close,
    record_dynamic_selection_miss,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    LockedObservationCursor,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    selected_member_set_digest,
)

HOUR = 3_600_000


def recovery_payload(group, static):
    spec = generic_selection_spec(group)
    source_period = build_generic_selection_period(feature_cutoff_at_ms=100*HOUR,cadence_hours=spec.cadence_hours)
    period = build_generic_selection_period(feature_cutoff_at_ms=(101 if spec.cadence_hours==1 else 100)*HOUR,cadence_hours=spec.cadence_hours)
    now = 101*HOUR+1800_000
    plan = plan_hourly_recovery_close(recovery_id="recovery:vacuum",recovery_revision=1,
        reason="MATERIALIZATION_FAILURE" if static else "AUTHORITY_GAP",period=period,evaluated_at_ms=now)
    members = spec.candidate_ids[:1]
    digest = selected_member_set_digest(members)
    fresh = build_dynamic_membership_freshness(source_snapshot_id="snapshot:previous",source_member_set_digest=digest,period=source_period)
    if period != source_period:
        fresh = record_dynamic_selection_miss(current=fresh,missed_period=period)
    comparative = group in {"MPG-001","MI-001"}
    comparison = "comparison:"+canonical_digest({"exchange_instrument_ids":members if static else spec.candidate_ids})[7:] if comparative else None
    return {
        "selection_spec_id":spec.selection_spec_id,"strategy_group_id":group,"selection_epoch_id":"epoch:attempt",
        "selection_mode":"static_baseline" if static else "dynamic_selection",
        "source_entry_vacuum_id":"vacuum:original","vacuum_fenced_at_ms":101*HOUR+1,
        "materialization_generation_id":"generation:failed" if static else None,
        "source_selection_authority_id":None if static else "authority:previous",
        "failed_activation_authorization_id":"owner:failed-attempt" if static else None,
        "owner_control_version":1,"selection_control_version":3,
        "event_binding":AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
            grant_state="ACTIVE",universe_version_id="universe:previous",member_set_digest=digest),
        "recovery_close_plan":plan,"membership_freshness":None if static else fresh,
        "comparison_universe_id":comparison,"comparison_transition_revision":(0 if static else 1) if comparative else None,
        "observation_cursors":(LockedObservationCursor(episode_domain_key=build_episode_domain_key(event_spec_id=spec.event_spec_id,
            exchange_instrument_id=members[0],position_side=spec.position_side),exchange_instrument_id=members[0],
            episode_version=0,comparison_checkpoint_version=0),),
        "committed_at_ms":now+1,
    }


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("static", [False,True])
def test_recovery_proof_binds_exact_previous_scope_and_future_clock(group, static):
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof
    values = recovery_payload(group,static)
    proof = GenericRecoveryGrantProof(**values)
    assert proof.first_eligible_close_time_ms > proof.committed_at_ms
    assert proof.effective_from_ms <= proof.first_eligible_close_time_ms < proof.expires_at_ms
    assert proof.episode_rebase_required is True
    assert proof.selection_mode == values["selection_mode"]
    assert GenericRecoveryGrantProof.model_validate_json(proof.model_dump_json()) == proof
    mutations = [
        {"observation_cursors":()},
        {"committed_at_ms":proof.first_eligible_close_time_ms},
        {"vacuum_fenced_at_ms":proof.committed_at_ms+1},
        {"event_binding":proof.event_binding.model_copy(update={"member_set_digest":"sha256:"+"0"*64})},
        {"selection_epoch_id":"sor-v0"},
        {"observation_cursors":(proof.observation_cursors[0].model_copy(update={"episode_domain_key":"other"}),)},
    ]
    mutations += [{"source_selection_authority_id":"authority:fake"},{"failed_activation_authorization_id":None}] if static else [
        {"source_selection_authority_id":None},{"membership_freshness":None},{"failed_activation_authorization_id":"owner:fake"}]
    for mutation in mutations:
        with pytest.raises(ValueError):
            GenericRecoveryGrantProof.model_validate({**proof.model_dump(),**mutation})
    assert proof.semantic_digest != GenericRecoveryGrantProof.model_validate({**proof.model_dump(),"owner_control_version":2}).semantic_digest
    if group in {"MPG-001", "MI-001"}:
        with pytest.raises(ValueError,match="comparison"):
            GenericRecoveryGrantProof.model_validate({**proof.model_dump(),"comparison_universe_id":"comparison:wrong"})
    else:
        with pytest.raises(ValueError,match="comparison"):
            GenericRecoveryGrantProof.model_validate({**proof.model_dump(),"comparison_universe_id":"comparison:fake","comparison_transition_revision":1})


def test_static_recovery_preserves_previous_instrument_outside_dynamic_candidate_panel():
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof
    values = recovery_payload("MPG-001",True)
    member = "binance-usdm:UNLISTEDUSDT:perpetual"
    spec = generic_selection_spec("MPG-001")
    values["event_binding"] = values["event_binding"].model_copy(update={"member_set_digest":selected_member_set_digest((member,))})
    values["comparison_universe_id"] = "comparison:"+canonical_digest({"exchange_instrument_ids":(member,)})[7:]
    values["observation_cursors"] = (LockedObservationCursor(episode_domain_key=build_episode_domain_key(event_spec_id=spec.event_spec_id,
        exchange_instrument_id=member,position_side=spec.position_side),exchange_instrument_id=member,episode_version=0,comparison_checkpoint_version=0),)
    proof = GenericRecoveryGrantProof(**values)
    assert proof.selection_mode == "static_baseline"
    # Whether this previous instrument is still tradable must be proved from
    # current DB/venue certification; the Dynamic Candidate panel is not it.
    assert proof.observation_cursors[0].exchange_instrument_id == member


def test_recovery_cannot_refresh_old_membership_past_its_absolute_deadline():
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof
    values = recovery_payload("MPG-001",False)
    old = build_dynamic_membership_freshness(source_snapshot_id="snapshot:older",
        source_member_set_digest=values["event_binding"].member_set_digest,
        period=build_generic_selection_period(feature_cutoff_at_ms=99*HOUR,cadence_hours=1))
    values["membership_freshness"] = record_dynamic_selection_miss(current=old,missed_period=values["recovery_close_plan"].period)
    with pytest.raises(ValueError,match="freshness|deadline"):
        GenericRecoveryGrantProof(**values)


def test_no_eligible_close_is_a_miss_not_a_recovery_grant():
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof
    values = recovery_payload("MI-001",True)
    values["recovery_close_plan"] = plan_hourly_recovery_close(recovery_id="recovery:vacuum",recovery_revision=1,
        reason="MATERIALIZATION_FAILURE",period=build_generic_selection_period(feature_cutoff_at_ms=100*HOUR,cadence_hours=1),
        evaluated_at_ms=values["committed_at_ms"]-1)
    with pytest.raises(ValueError,match="NO_ELIGIBLE"):
        GenericRecoveryGrantProof(**values)
