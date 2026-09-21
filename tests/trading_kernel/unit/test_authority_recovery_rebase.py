import pytest

from src.trading_kernel.domain.authority_recovery_rebase import (
    advance_authority_recovery_rebase,
)
from src.trading_kernel.domain.detector import DetectorStatus

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
