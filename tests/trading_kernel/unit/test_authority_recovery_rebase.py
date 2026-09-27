import pytest

from src.trading_kernel.domain.authority_recovery_rebase import (
    advance_authority_recovery_rebase,
    advance_recovery_bound_exposure_episode,
    recovery_rebase_entry_rejection,
)
from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    ExposureEpisodeState,
    LockedObservationCursor,
    advance_exposure_episode,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

HOUR = 3600000


def test_recovery_can_be_required_before_any_observation_without_fake_close():
    from src.trading_kernel.domain.authority_recovery_rebase import (
        begin_authority_recovery_rebase,
    )
    kwargs = {"episode_domain_key":"episode:existing","recovery_id":"recovery:1","recovery_revision":1,
        "effective_from_ms":5*HOUR+1000,"first_eligible_close_time_ms":6*HOUR}
    pending = begin_authority_recovery_rebase(current=None,latest_consumed_close_time_ms=None,**kwargs)
    assert pending.state == "REBASE_REQUIRED" and pending.armed_at_close_time_ms is None
    assert pending.last_observed_close_time_ms is None and pending.last_detector_status is None
    first = advance(pending,6*HOUR,DetectorStatus.TRIGGERED)
    assert not first.allow_episode_advance and first.checkpoint.projection_version == 2
    armed = advance(first.checkpoint,7*HOUR,DetectorStatus.NOT_TRIGGERED).checkpoint
    assert begin_authority_recovery_rebase(current=armed,latest_consumed_close_time_ms=7*HOUR,**kwargs) == armed
    next_pending = begin_authority_recovery_rebase(current=armed,latest_consumed_close_time_ms=8*HOUR,
        **{**kwargs,"recovery_id":"recovery:2","recovery_revision":2,"effective_from_ms":8*HOUR+1,"first_eligible_close_time_ms":9*HOUR})
    assert next_pending.last_observed_close_time_ms == 8*HOUR
    assert next_pending.last_detector_status is None and next_pending.armed_at_close_time_ms is None
    with pytest.raises(ValueError):
        advance(next_pending,8*HOUR,DetectorStatus.NOT_TRIGGERED,revision=2,effective=8*HOUR+1,first=9*HOUR)
    with pytest.raises(ValueError):
        begin_authority_recovery_rebase(current=next_pending,latest_consumed_close_time_ms=None,**kwargs)


def test_unobserved_recovery_episode_is_not_an_armed_or_consumed_bar():
    spec = generic_selection_spec("CPM-RO-001")
    member = spec.candidate_ids[0]
    key = build_episode_domain_key(event_spec_id=spec.event_spec_id,exchange_instrument_id=member,position_side=spec.position_side)
    pending = ExposureEpisodeState(episode_domain_key=key,event_spec_id=spec.event_spec_id,exchange_instrument_id=member,
        position_side=spec.position_side,state="authority_rebase_required",exposure_episode_id=None,
        triggered_at_ms=None,rearmed_at_ms=None,last_observed_at_ms=None,projection_version=1)
    cursor = LockedObservationCursor(episode_domain_key=key,exchange_instrument_id=member,episode_version=1,
        comparison_checkpoint_version=0,authority_recovery_checkpoint_version=1,last_observed_at_ms=None)
    assert cursor.last_observed_at_ms is None
    with pytest.raises(ValueError,match="rebase"):
        advance_exposure_episode(contract=strategy_contract_for(spec.event_spec_id),current=pending,
            detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=6*HOUR,observed_at_ms=6*HOUR,exchange_instrument_id=member)
    armed = advance_exposure_episode(contract=strategy_contract_for(spec.event_spec_id),current=pending,
        detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,observed_at_ms=6*HOUR,exchange_instrument_id=member)
    assert armed.current.last_observed_at_ms == 6*HOUR and armed.current.rearmed_at_ms == 6*HOUR
    with pytest.raises(ValueError):
        ExposureEpisodeState.model_validate({**pending.model_dump(),"state":"armed"})
    with pytest.raises(ValueError):
        LockedObservationCursor.model_validate({**cursor.model_dump(),"authority_recovery_checkpoint_version":0})


def advance(current, close, status, *, revision=1, effective=5*HOUR+1000, first=6*HOUR):
    return advance_authority_recovery_rebase(current=current,episode_domain_key="episode:existing",
        recovery_id=f"recovery:{revision}",recovery_revision=revision,effective_from_ms=effective,
        first_eligible_close_time_ms=first,observed_close_time_ms=close,detector_status=status)


def test_recovery_requires_future_false_then_later_true_without_comparison_identity() -> None:
    first = advance(None,6*HOUR,DetectorStatus.TRIGGERED)
    assert first.checkpoint.state=="REBASE_REQUIRED" and not first.allow_episode_advance
    second = advance(first.checkpoint,7*HOUR,DetectorStatus.NOT_TRIGGERED)
    assert second.checkpoint.state=="ARMED" and second.allow_episode_advance
    third = advance(second.checkpoint,8*HOUR,DetectorStatus.TRIGGERED)
    assert third.allow_episode_advance
    assert "comparison_transition_revision" not in third.checkpoint.model_dump()
    repeated = advance(third.checkpoint,8*HOUR,DetectorStatus.TRIGGERED)
    assert repeated.checkpoint==third.checkpoint and not repeated.allow_episode_advance


def test_new_recovery_revision_cannot_inherit_previous_arm() -> None:
    armed = advance(None,6*HOUR,DetectorStatus.NOT_TRIGGERED)
    changed = advance(armed.checkpoint,8*HOUR,DetectorStatus.TRIGGERED,revision=2,effective=7*HOUR+1,first=8*HOUR)
    assert changed.checkpoint.state=="REBASE_REQUIRED" and not changed.allow_episode_advance
    with pytest.raises(ValueError):
        advance(changed.checkpoint,9*HOUR,DetectorStatus.NOT_TRIGGERED)


def test_past_invalid_and_same_close_results_cannot_arm_recovery() -> None:
    with pytest.raises(ValueError):
        advance(None,5*HOUR,DetectorStatus.NOT_TRIGGERED)
    with pytest.raises(ValueError):
        advance(None,6*HOUR,DetectorStatus.INVALID)
    first = advance(None,6*HOUR,DetectorStatus.TRIGGERED)
    with pytest.raises(ValueError):
        advance(first.checkpoint,6*HOUR,DetectorStatus.NOT_TRIGGERED)
    with pytest.raises(ValueError):
        advance(first.checkpoint,7*HOUR,DetectorStatus.NOT_TRIGGERED,effective=5*HOUR+2)


def test_trigger_close_cannot_be_forged_into_an_arming_proof() -> None:
    first = advance(None,6*HOUR,DetectorStatus.TRIGGERED)
    payload = first.checkpoint.model_dump()
    payload.update(state="ARMED",armed_at_close_time_ms=6*HOUR)
    with pytest.raises(ValueError):
        type(first.checkpoint).model_validate(payload)
    assert "exposure_episode_id" not in first.checkpoint.model_dump()


def test_entry_rebase_gate_requires_exact_recovery_and_observed_trigger():
    from src.trading_kernel.domain.authority_recovery_rebase import (
        recovery_rebase_entry_rejection,
    )
    args = {"episode_domain_key":"episode:existing","recovery_id":"recovery:1","recovery_revision":1,
        "recovery_committed_at_ms":5*HOUR+1000,"first_eligible_close_time_ms":6*HOUR,"signal_close_time_ms":7*HOUR}
    assert recovery_rebase_entry_rejection(checkpoint=None,**args) == "RECOVERY_REBASE_REQUIRED"
    unarmed = advance(None,6*HOUR,DetectorStatus.TRIGGERED).checkpoint
    assert recovery_rebase_entry_rejection(checkpoint=unarmed,**args) == "RECOVERY_REBASE_REQUIRED"
    armed = advance(None,6*HOUR,DetectorStatus.NOT_TRIGGERED).checkpoint
    assert recovery_rebase_entry_rejection(checkpoint=armed,**args) == "RECOVERY_TRIGGER_NOT_CURRENT"
    triggered = advance(armed,7*HOUR,DetectorStatus.TRIGGERED).checkpoint
    assert recovery_rebase_entry_rejection(checkpoint=triggered,**args) is None
    for changed in ({"episode_domain_key":"other"},{"recovery_id":"other"},{"recovery_revision":2},
                    {"recovery_committed_at_ms":5*HOUR+2000},{"first_eligible_close_time_ms":7*HOUR}):
        assert recovery_rebase_entry_rejection(checkpoint=triggered,**{**args,**changed}) == "RECOVERY_REBASE_AUTHORITY_CHANGED"
    assert recovery_rebase_entry_rejection(checkpoint=triggered,**{**args,"signal_close_time_ms":8*HOUR}) == "RECOVERY_TRIGGER_NOT_CURRENT"


@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("old_state", [None, "armed", "triggered"])
def test_recovery_composes_with_real_episode_and_comparison_barriers(group, old_state):
    spec = generic_selection_spec(group)
    contract = strategy_contract_for(spec.event_spec_id)
    member = spec.candidate_ids[0]
    old = None if old_state is None else advance_exposure_episode(contract=contract,current=None,
        detector_status=DetectorStatus.TRIGGERED if old_state=="triggered" else DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=4*HOUR if old_state=="triggered" else None,observed_at_ms=4*HOUR,exchange_instrument_id=member).current
    comparative = group in {"MPG-001","MI-001"}
    comparison_digest = canonical_digest({"exchange_instrument_ids":spec.candidate_ids})
    binding = ComparisonUniverseBinding(event_spec_id=spec.event_spec_id,comparison_universe_id="comparison:"+comparison_digest[7:],
        member_set_digest=comparison_digest,exchange_instrument_ids=spec.candidate_ids,comparison_transition_revision=1,
        source_static_universe_version_id=None) if comparative else None
    kwargs = {"contract":contract,"exchange_instrument_id":member,"recovery_id":"recovery:1","recovery_revision":1,
        "effective_from_ms":5*HOUR+1,"first_eligible_close_time_ms":6*HOUR,
        "selection_mode":"dynamic_selection","universe_version_id":"universe:current","comparison_binding":binding}
    suppressed = advance_recovery_bound_exposure_episode(**kwargs,current_episode=old,current_recovery=None,current_comparison=None,
        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=6*HOUR,observed_at_ms=6*HOUR)
    assert suppressed.episode_transition is None and not suppressed.signal_eligible
    assert suppressed.suppression_reason == "RECOVERY_REBASE_REQUIRED"
    armed = advance_recovery_bound_exposure_episode(**kwargs,current_episode=old,current_recovery=suppressed.recovery_checkpoint,
        current_comparison=suppressed.comparison_checkpoint,detector_status=DetectorStatus.NOT_TRIGGERED,
        occurred_at_ms=None,observed_at_ms=7*HOUR)
    assert armed.episode_transition.current.state == "armed" and not armed.signal_eligible
    triggered = advance_recovery_bound_exposure_episode(**kwargs,current_episode=armed.episode_transition.current,
        current_recovery=armed.recovery_checkpoint,current_comparison=armed.comparison_checkpoint,
        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=8*HOUR,observed_at_ms=8*HOUR)
    assert triggered.signal_eligible and triggered.episode_transition.created_new_episode
    entry_args = {"episode_domain_key":triggered.recovery_checkpoint.episode_domain_key,
        "recovery_id":kwargs["recovery_id"],"recovery_revision":kwargs["recovery_revision"],
        "recovery_committed_at_ms":kwargs["effective_from_ms"],"first_eligible_close_time_ms":kwargs["first_eligible_close_time_ms"],
        "signal_close_time_ms":8*HOUR}
    assert recovery_rebase_entry_rejection(checkpoint=triggered.recovery_checkpoint,**entry_args) is None
    assert recovery_rebase_entry_rejection(checkpoint=suppressed.recovery_checkpoint,**entry_args) == "RECOVERY_REBASE_REQUIRED"
    assert old is None or triggered.episode_transition.exposure_episode_id != old.exposure_episode_id
    assert triggered.comparison_checkpoint is None if not comparative else triggered.comparison_checkpoint.comparison_transition_revision == 1
    repeated = advance_recovery_bound_exposure_episode(**kwargs,current_episode=triggered.episode_transition.current,
        current_recovery=triggered.recovery_checkpoint,current_comparison=triggered.comparison_checkpoint,
        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=8*HOUR,observed_at_ms=8*HOUR)
    assert not repeated.signal_eligible and repeated.episode_transition is None
    assert repeated.recovery_checkpoint == triggered.recovery_checkpoint
    with pytest.raises(ValueError,match="Signal"):
        type(suppressed).model_validate({**suppressed.model_dump(),"signal_eligible":True})
    for changes in ({"current_episode":armed.episode_transition.current,"observed_at_ms":7*HOUR},
                    {"occurred_at_ms":None}, {"occurred_at_ms":9*HOUR},
                    {"exchange_instrument_id":"binance_usdm:NOT_A_CANDIDATE"}):
        request = {**kwargs,"current_episode":old,"current_recovery":None,"current_comparison":None,
            "detector_status":DetectorStatus.TRIGGERED,"occurred_at_ms":6*HOUR,"observed_at_ms":6*HOUR,**changes}
        with pytest.raises(ValueError):
            advance_recovery_bound_exposure_episode(**request)
    new_recovery = advance_recovery_bound_exposure_episode(**{**kwargs,"recovery_id":"recovery:2","recovery_revision":2,
        "effective_from_ms":9*HOUR+1,"first_eligible_close_time_ms":10*HOUR},
        current_episode=triggered.episode_transition.current,current_recovery=triggered.recovery_checkpoint,
        current_comparison=triggered.comparison_checkpoint,detector_status=DetectorStatus.TRIGGERED,
        occurred_at_ms=10*HOUR,observed_at_ms=10*HOUR)
    assert not new_recovery.signal_eligible and new_recovery.episode_transition is None
    assert new_recovery.comparison_checkpoint == triggered.comparison_checkpoint
    assert new_recovery.recovery_checkpoint.state == "REBASE_REQUIRED"
    if comparative:
        changed_comparison = advance_recovery_bound_exposure_episode(**{**kwargs,"comparison_binding":binding.model_copy(update={"comparison_transition_revision":2})},
            current_episode=armed.episode_transition.current,current_recovery=armed.recovery_checkpoint,
            current_comparison=armed.comparison_checkpoint,detector_status=DetectorStatus.TRIGGERED,
            occurred_at_ms=8*HOUR,observed_at_ms=8*HOUR)
        assert changed_comparison.suppression_reason == "COMPARISON_REBASE_REQUIRED"
        assert not changed_comparison.signal_eligible and changed_comparison.episode_transition is None
        with pytest.raises(ValueError,match="comparison barrier"):
            type(triggered).model_validate({**triggered.model_dump(),"comparison_checkpoint":changed_comparison.comparison_checkpoint})


@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
@pytest.mark.parametrize("revision", [0,2])
def test_static_recovery_keeps_original_comparison_and_requires_real_rebase(group, revision):
    spec = generic_selection_spec(group)
    member = "binance-usdm:OUTSIDEUSDT:perpetual"
    digest = canonical_digest({"exchange_instrument_ids":(member,)})
    binding = ComparisonUniverseBinding(event_spec_id=spec.event_spec_id,comparison_universe_id="comparison:"+digest[7:],
        member_set_digest=digest,exchange_instrument_ids=(member,),comparison_transition_revision=revision,
        source_static_universe_version_id="universe:static")
    args = {"contract":strategy_contract_for(spec.event_spec_id),"exchange_instrument_id":member,
        "selection_mode":"static_baseline","universe_version_id":"universe:static","comparison_binding":binding,
        "recovery_id":"recovery:static","recovery_revision":1,"effective_from_ms":5*HOUR+1,"first_eligible_close_time_ms":6*HOUR}
    suppressed = advance_recovery_bound_exposure_episode(**args,current_episode=None,current_recovery=None,current_comparison=None,
        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=6*HOUR,observed_at_ms=6*HOUR)
    assert not suppressed.signal_eligible and suppressed.episode_transition is None
    armed = advance_recovery_bound_exposure_episode(**args,current_episode=None,current_recovery=suppressed.recovery_checkpoint,
        current_comparison=None,detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,observed_at_ms=7*HOUR)
    triggered = advance_recovery_bound_exposure_episode(**args,current_episode=armed.episode_transition.current,
        current_recovery=armed.recovery_checkpoint,current_comparison=armed.comparison_checkpoint,
        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=8*HOUR,observed_at_ms=8*HOUR)
    assert triggered.signal_eligible
    if revision == 0:
        assert triggered.comparison_checkpoint is None
    else:
        assert triggered.comparison_checkpoint.comparison_transition_revision == revision
    for changes in ({"universe_version_id":"universe:wrong"},{"selection_mode":"dynamic_selection"}):
        with pytest.raises(ValueError):
            advance_recovery_bound_exposure_episode(**{**args,**changes},current_episode=None,current_recovery=None,current_comparison=None,
                detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=6*HOUR,observed_at_ms=6*HOUR)
