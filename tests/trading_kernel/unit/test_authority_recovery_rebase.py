import pytest

from src.trading_kernel.domain.authority_recovery_rebase import (
    advance_authority_recovery_rebase,
    advance_recovery_bound_exposure_episode,
    recovery_rebase_entry_rejection,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import advance_exposure_episode
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

HOUR = 3600000


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
    kwargs = {"contract":contract,"exchange_instrument_id":member,"recovery_id":"recovery:1","recovery_revision":1,
        "effective_from_ms":5*HOUR+1,"first_eligible_close_time_ms":6*HOUR,
        "comparison_binding_digest":canonical_digest({"exchange_instrument_ids":spec.candidate_ids}) if comparative else None,
        "comparison_transition_revision":1 if comparative else None}
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
        changed_comparison = advance_recovery_bound_exposure_episode(**{**kwargs,"comparison_transition_revision":2},
            current_episode=armed.episode_transition.current,current_recovery=armed.recovery_checkpoint,
            current_comparison=armed.comparison_checkpoint,detector_status=DetectorStatus.TRIGGERED,
            occurred_at_ms=8*HOUR,observed_at_ms=8*HOUR)
        assert changed_comparison.suppression_reason == "COMPARISON_REBASE_REQUIRED"
        assert not changed_comparison.signal_eligible and changed_comparison.episode_transition is None
        with pytest.raises(ValueError,match="comparison barrier"):
            type(triggered).model_validate({**triggered.model_dump(),"comparison_checkpoint":changed_comparison.comparison_checkpoint})
