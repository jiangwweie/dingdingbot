from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    LockedObservationCursor,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    GenericSelectionAuthority,
    generic_authority_entry_rejection,
    selected_member_set_digest,
)


def _authority(group):
    spec = generic_selection_spec(group)
    period = build_generic_selection_period(feature_cutoff_at_ms=100*3_600_000,cadence_hours=spec.cadence_hours)
    grant = period.scheduled_effective_at_ms+8_000
    binding = AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        grant_state="ACTIVE",universe_version_id="universe:target",member_set_digest=selected_member_set_digest(spec.candidate_ids[:1]))
    proof = CurrentFinalCloseGrantProof(selection_snapshot_id="snapshot:test",selection_committed_at_ms=period.feature_cutoff_at_ms+1,
        source_snapshot_cutoff_at_ms=period.feature_cutoff_at_ms,period=period,
        current_final_close_time_ms=period.scheduled_effective_at_ms,authority_granted_at_ms=grant,
        observation_cursors=(LockedObservationCursor(episode_domain_key=build_episode_domain_key(event_spec_id=spec.event_spec_id,
            exchange_instrument_id=spec.candidate_ids[0],position_side=spec.position_side),exchange_instrument_id=spec.candidate_ids[0],
            episode_version=0,comparison_checkpoint_version=0,last_observed_at_ms=None),))
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
    return authority


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
def test_generic_authority_binds_exact_event_period_and_precommitted_close(group):
    authority = _authority(group)
    spec = generic_selection_spec(group)
    binding = authority.event_binding
    grant = authority.created_at_ms
    assert authority.first_eligible_close_time_ms == authority.period.scheduled_effective_at_ms
    proof = authority.current_close_proof
    assert proof is not None
    with pytest.raises(ValueError, match="coverage"):
        GenericSelectionAuthority.model_validate({**authority.model_dump(),
            "event_binding":{**binding.model_dump(),"member_set_digest":selected_member_set_digest(spec.candidate_ids[:2])}})
    for cursors in ((), proof.observation_cursors*2,
                    (proof.observation_cursors[0].model_copy(update={"last_observed_at_ms":authority.first_eligible_close_time_ms}),),
                    (proof.observation_cursors[0].model_copy(update={"episode_domain_key":"episode:wrong"}),)):
        with pytest.raises(ValueError):
            GenericSelectionAuthority.model_validate({**authority.model_dump(),
                "current_close_proof":{**proof.model_dump(),"observation_cursors":cursors}})
    for changes in ({"selection_snapshot_id":"snapshot:other"}, {"effective_from_ms":grant+1},
                    {"authority_outcome":"NO_CHANGE"},
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


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("empty", [False, True])
def test_generic_authority_storage_roundtrip_rejects_tampering(group, empty):
    from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
        generic_authority_from_storage,
        generic_authority_storage_values,
    )
    authority = _authority(group)
    if empty:
        authority = GenericSelectionAuthority.model_validate({**authority.model_dump(),
            "authority_outcome":"VALID_EMPTY","materialization_generation_id":None,
            "current_close_proof":None,"membership_freshness":None,
            "event_binding":AuthorityEventBinding.empty(event_spec_id=authority.event_binding.event_spec_id,
                position_side=authority.event_binding.position_side)})
    row = generic_authority_storage_values(authority)
    spec = generic_selection_spec(group)
    bindings = (authority.event_binding.model_dump(mode="json"),)
    assert generic_authority_from_storage(row,spec=spec,event_bindings=bindings) == authority
    persisted_binding = {**bindings[0],"selection_authority_id":authority.selection_authority_id}
    assert generic_authority_from_storage(row,spec=spec,event_bindings=(persisted_binding,)) == authority
    with pytest.raises(ValueError, match="parent"):
        generic_authority_from_storage(row,spec=spec,event_bindings=({**persisted_binding,"selection_authority_id":"another"},))
    for mutation in ({"semantic_digest":"sha256:"+"0"*64}, {"period_anchor_ms":1},
                     {"selection_epoch_id":"different"}, {"first_eligible_close_time_ms":1},
                     {"grant_proof_kind":"AUDITED_AUTHORITY_GAP"},
                     {"continued_from_selection_authority_id":"authority:fake"},
                     {"selection_job_id":"job:unexpected"}, {"reason_code":"changed"}):
        with pytest.raises(ValueError):
            generic_authority_from_storage({**row,**mutation},spec=spec,event_bindings=bindings)
    with pytest.raises(ValueError):
        generic_authority_from_storage(row,spec=spec,event_bindings=())
    with pytest.raises(ValueError):
        generic_authority_from_storage(row,spec=spec,event_bindings=bindings+bindings)
    from src.trading_kernel.infrastructure.pg_models import (
        selection_session_authorities,
    )
    assert set(row) == set(selection_session_authorities.c.keys())


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
def test_generic_positive_grant_requires_exact_birth_event_and_close(group):
    authority = _authority(group)
    args = {"authority": authority, "selection_spec_id": authority.selection_spec_id,
        "selection_epoch_id": authority.selection_epoch_id,"selection_control_version": 1,"owner_control_version": 1,
        "event_spec_id": authority.event_binding.event_spec_id,"position_side": authority.event_binding.position_side,
        "universe_version_id": authority.event_binding.universe_version_id,
        "birth_selection_authority_id": None,"allow_current_as_birth": True,
        "observed_close_time_ms": authority.first_eligible_close_time_ms,"now_ms": authority.created_at_ms}
    assert generic_authority_entry_rejection(**args) is None
    assert generic_authority_entry_rejection(**{**args,"allow_current_as_birth":False}) is not None
    assert generic_authority_entry_rejection(**{**args,"allow_current_as_birth":False,
        "birth_selection_authority_id":authority.selection_authority_id}) is None
    for changes in ({"universe_version_id":"wrong"},{"selection_epoch_id":"wrong"},
                    {"selection_control_version":2},{"owner_control_version":2},
                    {"observed_close_time_ms":authority.first_eligible_close_time_ms-3_600_000},
                    {"observed_close_time_ms":authority.first_eligible_close_time_ms+1},
                    {"now_ms":authority.expires_at_ms},
                    {"birth_selection_authority_id":"authority:stale"}):
        assert generic_authority_entry_rejection(**{**args,**changes}) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_resolver_checks_current_targets_before_allowing(group):
    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_entry_authority,
    )
    from src.trading_kernel.domain.selection_authority import SelectionMode
    authority = _authority(group)
    spec = generic_selection_spec(group)
    member = spec.candidate_ids[0]
    control = SimpleNamespace(strategy_group_id=group,selection_spec_id=spec.selection_spec_id,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,selection_epoch_id=authority.selection_epoch_id,control_version=1)
    scope = SimpleNamespace(strategy_group_id=group,event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",universe_version_id="universe:target",
        universe_semantic_digest="digest:current",exchange_instrument_id=member)
    target = SimpleNamespace(event_spec_id=spec.event_spec_id,universe_version_id="universe:target",
        lifecycle_state=SimpleNamespace(value="active"))
    # Port stubs isolate the shared resolver; not evidence of atomic activation.
    uow = SimpleNamespace(
        instrument_selection=SimpleNamespace(
            get_selection_control=AsyncMock(return_value=control),
            get_current_generic_authority=AsyncMock(return_value=SimpleNamespace(authority=authority)),
            get_current_entry_vacuum=AsyncMock(return_value=None),
            get_generic_snapshot=AsyncMock(return_value=SimpleNamespace(selection_spec_id=spec.selection_spec_id,
                selection_epoch_id=authority.selection_epoch_id,selected_members=(member,),selection_snapshot_id=authority.selection_snapshot_id,
                feature_cutoff_at_ms=authority.period.feature_cutoff_at_ms,committed_at_ms=authority.current_close_proof.selection_committed_at_ms)),
            get_generic_materialization_generation=AsyncMock(return_value=SimpleNamespace(lifecycle_state=SimpleNamespace(value="ACTIVE"),
                selection_snapshot_id=authority.selection_snapshot_id,selection_epoch_id=authority.selection_epoch_id,
                selection_control_version=1,desired_member_count=1,activated_at_ms=authority.effective_from_ms)),
            get_comparison_universe_binding=AsyncMock(return_value=SimpleNamespace(comparison_universe_id=authority.comparison_universe_id,
                comparison_transition_revision=authority.comparison_transition_revision))),
        owner_controls=SimpleNamespace(get_strategy_control=AsyncMock(return_value=SimpleNamespace(entry_state=SimpleNamespace(value="enabled"),control_version=1))),
        entry_admission=SimpleNamespace(get_owner_policy=AsyncMock(return_value=SimpleNamespace(enabled=True,new_entry_submit_enabled=True,
            scope=SimpleNamespace(authorizes=lambda **_:True)))),
        strategy_universes=SimpleNamespace(get_current=AsyncMock(return_value=SimpleNamespace(universe_version_id="universe:target",semantic_digest="digest:current")),
            get_generation_universe_targets=AsyncMock(return_value=(target,))),
        signals=SimpleNamespace(get_observation_universe_members=AsyncMock(return_value=SimpleNamespace(lifecycle_state="active",
            semantic_digest="digest:current",exchange_instrument_ids=(member,))),selection_authority_was_interrupted=AsyncMock(return_value=False)))
    args = {"runtime_scope": scope,"birth_selection_authority_id": None,"observed_close_time_ms": authority.first_eligible_close_time_ms,
        "now_ms": authority.created_at_ms,"allow_current_as_birth": True}
    assert (await resolve_selection_entry_authority(uow,**args)).allowed
    uow.strategy_universes.get_generation_universe_targets.return_value = ()
    result = await resolve_selection_entry_authority(uow,**args)
    assert not result.allowed and result.reason_code == "selection_generation_target_changed"
    uow.strategy_universes.get_generation_universe_targets.return_value = (target,)
    generation = uow.instrument_selection.get_generic_materialization_generation.return_value
    generation.lifecycle_state.value = "STAGED"
    assert not (await resolve_selection_entry_authority(uow,**args)).allowed
    generation.lifecycle_state.value = "ACTIVE"
    snapshot = uow.instrument_selection.get_generic_snapshot.return_value
    snapshot.selected_members = ()
    assert not (await resolve_selection_entry_authority(uow,**args)).allowed
    snapshot.selected_members = (member,)
    if authority.comparison_universe_id is not None:
        comparison = uow.instrument_selection.get_comparison_universe_binding.return_value
        comparison.comparison_transition_revision += 1
        assert not (await resolve_selection_entry_authority(uow,**args)).allowed
        comparison.comparison_transition_revision -= 1
    uow.signals.selection_authority_was_interrupted.return_value = True
    assert not (await resolve_selection_entry_authority(uow,**args)).allowed
