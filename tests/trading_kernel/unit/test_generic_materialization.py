import pytest

from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
    GenericStaticMaterializationGeneration,
    GenericStaticRollbackBaseline,
    GenericStaticRollbackEvent,
    MaterializationEventBaseline,
    generic_input_is_unchanged,
)
from src.trading_kernel.domain.generic_selection_core import compute_generic_selection
from src.trading_kernel.domain.selection_authority import selected_member_set_digest
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR, inputs


@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
def test_static_generation_is_owner_owned_without_synthetic_snapshot(group: str) -> None:
    spec = inputs(group).spec
    auth = "owner-authorization:static-test"
    baseline_id = "rollback-baseline:"+"c"*64
    prior = MaterializationEventBaseline(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        grant_state="ACTIVE",universe_version_id="universe:dynamic-current",
        member_set_digest=selected_member_set_digest(spec.candidate_ids[:1]),
        comparison_universe_id="comparison:dynamic" if group in {"MPG-001","MI-001"} else None,
        comparison_transition_revision=1 if group in {"MPG-001","MI-001"} else None)
    generation = GenericStaticMaterializationGeneration(
        materialization_generation_id=GenericStaticMaterializationGeneration.id_for_authorization(auth),
        selection_spec_id=spec.selection_spec_id,strategy_group_id=group,strategy_version_id=spec.strategy_version_id,
        rollback_baseline_id=baseline_id,authorization_id=auth,effective_period_anchor_ms=CUTOFF,
        selection_epoch_id="epoch:dynamic-original",selection_control_version=3,
        desired_member_count=1,previous_events=(prior,),created_at_ms=CUTOFF+HOUR+1)
    assert generation.selection_snapshot_id is None and generation.period_anchor_ms is None
    assert generation.selection_mode == "static_baseline"
    assert GenericStaticMaterializationGeneration.model_validate(generation.model_dump()).semantic_digest == generation.semantic_digest
    for key,value in (("materialization_generation_id","generation:forged"),("selection_snapshot_id","selection:fake"),
        ("desired_member_count",11),("previous_events",()),("created_at_ms",CUTOFF),
        ("lifecycle_state","STAGED"),("lease_owner","unfenced-worker")):
        with pytest.raises(ValueError):
            GenericStaticMaterializationGeneration.model_validate({**generation.model_dump(),key:value})


@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
def test_static_rollback_identity_freezes_source_refs_and_selection_spec(group: str) -> None:
    spec = inputs(group).spec
    event = GenericStaticRollbackEvent(
        event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        universe_version_id="universe:static-source",universe_semantic_digest="sha256:"+"a"*64,
        member_set_digest=selected_member_set_digest(spec.candidate_ids[:1]),
        comparison_universe_id="comparison:"+"b"*64 if group in {"MPG-001","MI-001"} else None,
    )
    baseline = GenericStaticRollbackBaseline.build(
        strategy_group_id=group,source_event=event,captured_at_ms=CUTOFF-1,
    )
    recaptured = GenericStaticRollbackBaseline.build(
        strategy_group_id=group,source_event=event,captured_at_ms=CUTOFF,
    )
    assert baseline.rollback_baseline_id == recaptured.rollback_baseline_id
    assert baseline.semantic_digest == recaptured.semantic_digest
    assert baseline.selection_algorithm_digest == spec.algorithm_semantic_digest
    assert baseline.source_event == event
    with pytest.raises(ValueError,match="source identity"):
        GenericStaticRollbackBaseline.model_validate(baseline.model_copy(update={
            "selection_algorithm_digest":"sha256:"+"c"*64,
        }).model_dump())
    with pytest.raises(ValueError,match="source identity"):
        GenericStaticRollbackBaseline.model_validate(baseline.model_copy(update={
            "source_event":event.model_copy(update={
                "position_side":"long" if spec.position_side=="short" else "short",
            }),
        }).model_dump())


@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
def test_identical_tradable_members_do_not_hide_comparison_transition(group: str) -> None:
    source = inputs(group)
    snapshot = compute_generic_selection(source)
    # A static single-member set is enough to demonstrate equal tradable sets.
    from tests.trading_kernel.support.generic_selection import qualify_window
    selected = snapshot.selected_members[0]
    source = source.model_copy(update={"member_windows":tuple(qualify_window(w,w.exchange_instrument_id==selected) for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    members = snapshot.selected_members
    digest = canonical_digest({"exchange_instrument_ids":members})
    static = ComparisonUniverseBinding(event_spec_id=source.spec.event_spec_id,comparison_universe_id="comparison:"+digest[7:],
        member_set_digest=digest,exchange_instrument_ids=members,comparison_transition_revision=0,source_static_universe_version_id="static:1")
    assert not generic_input_is_unchanged(snapshot,current_members=members,comparison=static)
    panel_digest = canonical_digest({"exchange_instrument_ids":source.spec.candidate_ids})
    dynamic = ComparisonUniverseBinding(event_spec_id=source.spec.event_spec_id,comparison_universe_id="comparison:"+panel_digest[7:],
        member_set_digest=panel_digest,exchange_instrument_ids=source.spec.candidate_ids,comparison_transition_revision=1,source_static_universe_version_id=None)
    assert generic_input_is_unchanged(snapshot,current_members=members,comparison=dynamic)
    with pytest.raises(ValueError,match="comparison"):
        generic_input_is_unchanged(snapshot,current_members=members,comparison=None)


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


@pytest.mark.parametrize("rule", ["NORMAL_TRANSITION","RECOVERY_TRANSITION"])
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
def test_static_activation_proof_keeps_normal_and_recovery_close_rules_distinct(rule: str, group: str) -> None:
    from src.trading_kernel.domain.exposure_episode import (
        LockedObservationCursor,
        build_episode_domain_key,
    )
    from src.trading_kernel.domain.generic_materialization import (
        GenericStaticActivationProof,
    )
    from src.trading_kernel.domain.selection_authority import AuthorityEventBinding

    spec = inputs(group).spec
    member = spec.candidate_ids[0]
    comparative = group in {"MPG-001","MI-001"}
    prior = MaterializationEventBaseline(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
        grant_state="ACTIVE",universe_version_id="universe:dynamic",member_set_digest=selected_member_set_digest((member,)),
        comparison_universe_id="comparison:"+canonical_digest({"exchange_instrument_ids":spec.candidate_ids})[7:] if comparative else None,
        comparison_transition_revision=1 if comparative else None)
    auth = "owner:static"
    at = CUTOFF+HOUR+8_000
    close = CUTOFF+HOUR if rule=="NORMAL_TRANSITION" else CUTOFF+2*HOUR
    proof = GenericStaticActivationProof(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
        selection_epoch_id="epoch:1",selection_control_version=3,owner_control_version=1,
        authorization_id=auth,owner_authorized_at_ms=CUTOFF-1,rollback_baseline_id="rollback-baseline:"+"a"*64,
        materialization_generation_id=GenericStaticMaterializationGeneration.id_for_authorization(auth),
        effective_period_anchor_ms=CUTOFF,entry_vacuum_id="vacuum:static",vacuum_version=3,
        fenced_at_ms=CUTOFF+HOUR+2,drained_at_ms=CUTOFF+HOUR+3,
        previous_event=prior,source_selection_authority_id="authority:dynamic",target_event=AuthorityEventBinding(event_spec_id=spec.event_spec_id,position_side=spec.position_side,
            grant_state="ACTIVE",universe_version_id="universe:static-new",member_set_digest=prior.member_set_digest),
        transition_rule=rule,recovery_reason=None if rule=="NORMAL_TRANSITION" else "AUTHORITY_GAP",
        first_eligible_close_time_ms=close,prepared_at_ms=at,
        comparison_universe_id="comparison:"+canonical_digest({"exchange_instrument_ids":(member,)})[7:] if comparative else None,
        comparison_transition_revision=2 if comparative else None,
        observation_cursors=(LockedObservationCursor(exchange_instrument_id=member,
            episode_domain_key=build_episode_domain_key(event_spec_id=spec.event_spec_id,
                exchange_instrument_id=member,position_side=spec.position_side),episode_version=0,last_observed_at_ms=None,
            comparison_checkpoint_version=0,authority_recovery_checkpoint_version=0),))
    assert proof.episode_rebase_required is (rule=="RECOVERY_TRANSITION")
    assert proof.comparison_rebase_required is comparative
    assert proof.result_selection_control_version == 4
    wrong_close = CUTOFF+HOUR if rule=="RECOVERY_TRANSITION" else CUTOFF+2*HOUR
    with pytest.raises(ValueError,match="close"):
        GenericStaticActivationProof.model_validate({**proof.model_dump(),"first_eligible_close_time_ms":wrong_close})
    observed = CUTOFF+HOUR
    consumed = proof.observation_cursors[0].model_copy(update={"episode_version":1,"last_observed_at_ms":observed})
    values = {**proof.model_dump(),"observation_cursors":(consumed,)}
    if rule=="NORMAL_TRANSITION":
        with pytest.raises(ValueError,match="consumed"):
            GenericStaticActivationProof.model_validate(values)
    else:
        assert GenericStaticActivationProof.model_validate(values).first_eligible_close_time_ms>observed
    with pytest.raises(ValueError,match="close"):
        GenericStaticActivationProof.model_validate({**proof.model_dump(),"prepared_at_ms":at+HOUR})
