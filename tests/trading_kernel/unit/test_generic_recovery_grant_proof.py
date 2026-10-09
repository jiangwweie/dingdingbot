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


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
def test_recovered_new_target_requires_snapshot_and_future_rebase(group):
    from src.trading_kernel.domain.selection_authority import (
        GenericRecoveryAuthority,
        GenericRecoveryGrantProof,
    )

    values = recovery_payload(group,False)
    fresh = values["membership_freshness"]
    values.update({
        "authority_outcome":"ACTIVE_NEW",
        "target_snapshot_id":fresh.source_snapshot_id,
        "materialization_generation_id":"generation:new-target",
        "event_binding":values["event_binding"].model_copy(update={"universe_version_id":"universe:new-target"}),
    })
    proof = GenericRecoveryGrantProof(**values)
    authority = GenericRecoveryAuthority.build(proof=proof,authority_sequence=1)
    assert authority.authority_outcome == "ACTIVE_NEW"
    assert authority.selection_snapshot_id == proof.target_snapshot_id
    assert authority.first_eligible_close_time_ms > authority.created_at_ms
    assert authority.event_binding.universe_version_id == "universe:new-target"
    assert GenericRecoveryAuthority.model_validate_json(authority.model_dump_json()) == authority
    for changes in (
        {"target_snapshot_id":None},
        {"target_snapshot_id":"snapshot:wrong"},
        {"materialization_generation_id":None},
        {"selection_mode":"static_baseline"},
        {"source_selection_authority_id":None},
        {"recovery_close_plan":proof.recovery_close_plan.model_copy(update={"first_eligible_close_time_ms":proof.committed_at_ms})},
    ):
        with pytest.raises(ValueError):
            GenericRecoveryGrantProof.model_validate({**proof.model_dump(),**changes})


def test_no_eligible_close_is_a_miss_not_a_recovery_grant():
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof
    values = recovery_payload("MI-001",True)
    values["recovery_close_plan"] = plan_hourly_recovery_close(recovery_id="recovery:vacuum",recovery_revision=1,
        reason="MATERIALIZATION_FAILURE",period=build_generic_selection_period(feature_cutoff_at_ms=100*HOUR,cadence_hours=1),
        evaluated_at_ms=values["committed_at_ms"]-1)
    with pytest.raises(ValueError,match="NO_ELIGIBLE"):
        GenericRecoveryGrantProof(**values)


@pytest.mark.parametrize("group", ["CPM-RO-001", "BRF2-001"])
def test_late_continuity_requires_generation_free_gap_rebase(group):
    from src.trading_kernel.domain.selection_authority import (
        GenericRecoveryAuthority,
        GenericRecoveryGrantProof,
    )

    values = recovery_payload(group, False)
    values["authority_outcome"] = "PRE_FENCE_CONTINUITY"
    spec = generic_selection_spec(group)
    assert spec.cadence_hours == 4
    source_period = build_generic_selection_period(feature_cutoff_at_ms=100*HOUR,cadence_hours=4)
    period = build_generic_selection_period(feature_cutoff_at_ms=104*HOUR,cadence_hours=4)
    now = 106*HOUR+1800_000
    values["recovery_close_plan"] = plan_hourly_recovery_close(
        recovery_id="recovery:vacuum",recovery_revision=1,reason="AUTHORITY_GAP",
        period=period,evaluated_at_ms=now)
    values["membership_freshness"] = record_dynamic_selection_miss(
        current=build_dynamic_membership_freshness(
            source_snapshot_id="snapshot:previous",
            source_member_set_digest=values["event_binding"].member_set_digest,
            period=source_period),missed_period=period)
    values["vacuum_fenced_at_ms"] = 106*HOUR+1
    values["committed_at_ms"] = now+1
    proof = GenericRecoveryGrantProof(**values)
    authority = GenericRecoveryAuthority.build(proof=proof, authority_sequence=1)
    assert proof.materialization_generation_id is None
    assert proof.target_snapshot_id is None
    assert proof.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert authority.authority_outcome == "PRE_FENCE_CONTINUITY"
    assert authority.first_eligible_close_time_ms > authority.created_at_ms
    assert authority.selection_snapshot_id == proof.membership_freshness.source_snapshot_id
    assert GenericRecoveryAuthority.model_validate_json(authority.model_dump_json()) == authority
    for mutation in (
        {"materialization_generation_id": "generation:fake"},
        {"target_snapshot_id": "snapshot:fake"},
        {"selection_mode": "static_baseline"},
        {"source_selection_authority_id": None},
        {"membership_freshness": None},
        {"failed_activation_authorization_id": "owner:fake"},
        {"vacuum_fenced_at_ms": period.scheduled_effective_at_ms+1},
        {"recovery_close_plan": proof.recovery_close_plan.model_copy(update={"reason":"MATERIALIZATION_FAILURE"})},
    ):
        with pytest.raises(ValueError):
            GenericRecoveryGrantProof.model_validate({**proof.model_dump(), **mutation})


@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
def test_hourly_gap_after_its_only_close_cannot_create_trading_authority(group):
    from src.trading_kernel.domain.selection_authority import GenericRecoveryGrantProof

    values = recovery_payload(group, False)
    values["authority_outcome"] = "PRE_FENCE_CONTINUITY"
    values["materialization_generation_id"] = None
    period = values["recovery_close_plan"].period
    evaluated = period.scheduled_effective_at_ms+1
    values["recovery_close_plan"] = plan_hourly_recovery_close(
        recovery_id="recovery:vacuum",recovery_revision=1,reason="AUTHORITY_GAP",
        period=period,evaluated_at_ms=evaluated)
    values["vacuum_fenced_at_ms"] = evaluated
    values["committed_at_ms"] = evaluated+1
    with pytest.raises(ValueError,match="NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY"):
        GenericRecoveryGrantProof(**values)


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("static", [False, True])
def test_recovery_authority_uses_exact_proof_and_never_claims_normal_activation(group, static):
    from src.trading_kernel.domain.selection_authority import (
        GenericRecoveryAuthority,
        GenericRecoveryGrantProof,
    )
    proof = GenericRecoveryGrantProof(**recovery_payload(group,static))
    authority = GenericRecoveryAuthority.build(proof=proof,authority_sequence=1)
    from src.trading_kernel.domain.selection_authority import (
        CurrentGenericSelectionAuthority,
    )
    current = CurrentGenericSelectionAuthority(authority=authority,projection_version=1)
    assert current.authority == authority
    restored_current = CurrentGenericSelectionAuthority.model_validate_json(current.model_dump_json())
    assert isinstance(restored_current.authority,GenericRecoveryAuthority)
    assert restored_current == current
    assert authority.authority_outcome == "FALLBACK_PREVIOUS"
    assert authority.selection_spec_id == proof.selection_spec_id
    assert authority.selection_mode == proof.selection_mode
    assert authority.created_at_ms == proof.committed_at_ms
    assert authority.effective_from_ms == proof.effective_from_ms
    assert authority.first_eligible_close_time_ms == proof.first_eligible_close_time_ms
    assert authority.expires_at_ms == proof.expires_at_ms
    assert authority.event_binding == proof.event_binding
    assert authority.allows_existing_ticket_lifecycle and not authority.rewrites_existing_lineage
    assert authority.selection_snapshot_id == (None if static else proof.membership_freshness.source_snapshot_id)
    assert GenericRecoveryAuthority.model_validate_json(authority.model_dump_json()) == authority
    for changes in ({"authority_sequence":0},{"selection_authority_id":"authority:forged"},
                    {"authority_outcome":"ACTIVE_NEW"},{"authority_outcome":"NO_CHANGE"},
                    {"authority_sequence":2},{"current_close_proof":{}}):
        with pytest.raises(ValueError):
            GenericRecoveryAuthority.model_validate({**authority.model_dump(),**changes})
    later = GenericRecoveryAuthority.build(proof=proof,authority_sequence=2)
    assert later.selection_authority_id != authority.selection_authority_id
    assert later.semantic_digest != authority.semantic_digest
    from src.trading_kernel.domain.selection_authority import (
        generic_recovery_entry_rejection,
    )
    args = {"authority":authority,"selection_spec_id":proof.selection_spec_id,
        "selection_epoch_id":None if static else proof.selection_epoch_id,"selection_mode":proof.selection_mode,
        "selection_control_version":proof.selection_control_version,"owner_control_version":proof.owner_control_version,
        "event_spec_id":proof.event_binding.event_spec_id,"position_side":proof.event_binding.position_side,
        "universe_version_id":proof.event_binding.universe_version_id,"exchange_instrument_id":proof.observation_cursors[0].exchange_instrument_id,
        "birth_selection_authority_id":None,"allow_current_as_birth":True,
        "observed_close_time_ms":proof.first_eligible_close_time_ms,"now_ms":proof.first_eligible_close_time_ms+1}
    assert generic_recovery_entry_rejection(**args) is None
    assert generic_recovery_entry_rejection(**{**args,"allow_current_as_birth":False,"birth_selection_authority_id":authority.selection_authority_id}) is None
    for changes in ({"now_ms":proof.expires_at_ms},{"now_ms":proof.effective_from_ms-1},
                    {"observed_close_time_ms":proof.first_eligible_close_time_ms-HOUR},
                    {"observed_close_time_ms":proof.first_eligible_close_time_ms+1},
                    {"allow_current_as_birth":False},{"birth_selection_authority_id":"other"},
                    {"selection_control_version":proof.selection_control_version+1},
                    {"selection_epoch_id":"wrong"},{"exchange_instrument_id":"not-selected"}):
        assert generic_recovery_entry_rejection(**{**args,**changes}) is not None
    from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
        generic_recovery_authority_from_storage,
        generic_recovery_authority_storage_values,
    )
    from src.trading_kernel.infrastructure.pg_models import (
        selection_session_authorities,
    )
    row = generic_recovery_authority_storage_values(authority)
    bindings = ({"selection_authority_id":authority.selection_authority_id,**authority.event_binding.model_dump(mode="json")},)
    spec = generic_selection_spec(group)
    assert set(row) == set(selection_session_authorities.c.keys())
    assert generic_recovery_authority_from_storage(row,spec=spec,event_bindings=bindings) == authority
    for mutation in ({"semantic_digest":"sha256:"+"0"*64},{"selection_mode":"disabled"},
                     {"selection_epoch_id":"wrong"},{"first_eligible_close_time_ms":proof.first_eligible_close_time_ms-HOUR},
                     {"grant_proof_kind":"PRECOMMITTED_SELECTION_CURRENT_CLOSE"},{"recovery_grant_proof":{}},
                     {"effective_from_ms":proof.effective_from_ms-1},{"activation_authorization_id":"owner:fake"}):
        with pytest.raises(ValueError):
            generic_recovery_authority_from_storage({**row,**mutation},spec=spec,event_bindings=bindings)
    with pytest.raises(ValueError):
        generic_recovery_authority_from_storage(row,spec=spec,event_bindings=())
    with pytest.raises(ValueError):
        generic_recovery_authority_from_storage({key:value for key,value in row.items() if key!="selection_job_id"},spec=spec,event_bindings=bindings)


def test_recovery_identity_changes_when_any_frozen_proof_changes():
    from src.trading_kernel.domain.selection_authority import (
        GenericRecoveryAuthority,
        GenericRecoveryGrantProof,
    )
    proof = GenericRecoveryGrantProof(**recovery_payload("CPM-RO-001",True))
    original = GenericRecoveryAuthority.build(proof=proof,authority_sequence=1)
    changed = GenericRecoveryAuthority.build(proof=proof.model_copy(update={"owner_control_version":2}),authority_sequence=1)
    assert changed.selection_authority_id != original.selection_authority_id
    with pytest.raises(ValueError):
        GenericRecoveryAuthority.model_validate({**original.model_dump(),"recovery_proof":changed.recovery_proof})


@pytest.mark.asyncio
@pytest.mark.parametrize("static", [False,True])
@pytest.mark.parametrize("expired", [False,True])
async def test_current_recovery_cannot_fall_through_to_static_or_normal_entry(static, expired):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_entry_authority,
    )
    from src.trading_kernel.domain.selection_authority import (
        CurrentGenericSelectionAuthority,
        GenericRecoveryAuthority,
        GenericRecoveryGrantProof,
        SelectionMode,
    )
    proof = GenericRecoveryGrantProof(**recovery_payload("CPM-RO-001",static))
    authority = GenericRecoveryAuthority.build(proof=proof,authority_sequence=1)
    control = SimpleNamespace(strategy_group_id=proof.strategy_group_id,selection_spec_id=proof.selection_spec_id,
        selection_mode=SelectionMode(proof.selection_mode),selection_epoch_id=None if static else proof.selection_epoch_id,
        control_version=proof.selection_control_version)
    scope = SimpleNamespace(strategy_group_id=proof.strategy_group_id,event_spec_id=proof.event_binding.event_spec_id,
        position_side=proof.event_binding.position_side,runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",
        universe_version_id=proof.event_binding.universe_version_id,universe_semantic_digest="digest:test",exchange_instrument_id=proof.observation_cursors[0].exchange_instrument_id)
    uow = SimpleNamespace(instrument_selection=SimpleNamespace(get_selection_control=AsyncMock(return_value=control),
        get_current_entry_vacuum=AsyncMock(return_value=None),get_current_generic_authority=AsyncMock(return_value=CurrentGenericSelectionAuthority(authority=authority,projection_version=1)),
        get_generic_static_activation_proof_for_universe=AsyncMock(return_value=None)),
        owner_controls=SimpleNamespace(get_strategy_control=AsyncMock(return_value=SimpleNamespace(entry_state=SimpleNamespace(value="enabled"),control_version=proof.owner_control_version))),
        entry_admission=SimpleNamespace(get_owner_policy=AsyncMock(return_value=SimpleNamespace(enabled=True,new_entry_submit_enabled=True,scope=SimpleNamespace(authorizes=lambda **_:True)))),
        strategy_universes=SimpleNamespace(get_current=AsyncMock(return_value=SimpleNamespace(universe_version_id=proof.event_binding.universe_version_id,semantic_digest="digest:test"))),
        signals=SimpleNamespace(get_observation_universe_members=AsyncMock(return_value=SimpleNamespace(lifecycle_state="active",semantic_digest="digest:test",exchange_instrument_ids=(scope.exchange_instrument_id,))),
            selection_authority_was_interrupted=AsyncMock(return_value=False),get_authority_recovery_checkpoint=AsyncMock(return_value=None)))
    result = await resolve_selection_entry_authority(uow,runtime_scope=scope,birth_selection_authority_id=None,
        observed_close_time_ms=authority.first_eligible_close_time_ms,now_ms=authority.expires_at_ms+1 if expired else authority.first_eligible_close_time_ms+1,
        allow_current_as_birth=True)
    assert not result.allowed and result.reason_code == ("selection_recovery_not_effective" if expired else "RECOVERY_REBASE_AUTHORITY_CHANGED")
