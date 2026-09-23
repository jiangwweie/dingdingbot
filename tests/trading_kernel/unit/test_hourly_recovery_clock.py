import pytest

from src.trading_kernel.domain.dynamic_selection_timing import (
    build_current_final_close_grant_proof,
    build_generic_selection_period,
    plan_hourly_recovery_close,
    require_current_close_commit,
    require_hourly_recovery_commit,
)
from src.trading_kernel.domain.exposure_episode import LockedObservationCursor

HOUR = 3600000


@pytest.mark.parametrize("delay_ms", [8000, 30000, 120000])
def test_slow_normal_transition_is_not_reclassified_as_recovery(delay_ms: int) -> None:
    period = build_generic_selection_period(feature_cutoff_at_ms=4*HOUR, cadence_hours=1)
    proof = build_current_final_close_grant_proof(selection_snapshot_id="snapshot:precommitted",
        selection_committed_at_ms=4*HOUR+1000, source_snapshot_cutoff_at_ms=4*HOUR, period=period,
        current_final_close_time_ms=5*HOUR, authority_granted_at_ms=5*HOUR+delay_ms,
        observation_cursors=(LockedObservationCursor(episode_domain_key="episode:test",exchange_instrument_id="instrument:test",
            episode_version=0,comparison_checkpoint_version=0,last_observed_at_ms=None),))
    assert proof.current_final_close_time_ms == 5*HOUR
    require_current_close_commit(proof,committed_at_ms=5*HOUR+delay_ms+1)
    with pytest.raises(ValueError,match="boundary"):
        require_current_close_commit(proof,committed_at_ms=6*HOUR)
    with pytest.raises(ValueError,match="backwards"):
        require_current_close_commit(proof,committed_at_ms=5*HOUR+delay_ms-1)
    recovery = plan_hourly_recovery_close(recovery_id="recovery:gap", recovery_revision=1,
        reason="AUTHORITY_GAP", period=period, evaluated_at_ms=5*HOUR+delay_ms)
    assert recovery.status == "NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY"
    assert recovery.first_eligible_close_time_ms is None


def test_recovery_requires_future_close_and_revalidates_commit_boundary() -> None:
    period = build_generic_selection_period(feature_cutoff_at_ms=4*HOUR, cadence_hours=4)
    plan = plan_hourly_recovery_close(recovery_id="recovery:failure", recovery_revision=2,
        reason="MATERIALIZATION_FAILURE", period=period, evaluated_at_ms=5*HOUR+8000)
    assert plan.first_eligible_close_time_ms == 6*HOUR
    assert plan.episode_rebase_required is True
    require_hourly_recovery_commit(plan, committed_at_ms=5*HOUR+9000)
    for commit in (5*HOUR+7999, 6*HOUR, 9*HOUR):
        with pytest.raises(ValueError):
            require_hourly_recovery_commit(plan, committed_at_ms=commit)


def test_no_future_close_cannot_be_committed_as_authority() -> None:
    period = build_generic_selection_period(feature_cutoff_at_ms=4*HOUR, cadence_hours=1)
    plan = plan_hourly_recovery_close(recovery_id="recovery:stale", recovery_revision=3,
        reason="STALE_SOURCE", period=period, evaluated_at_ms=6*HOUR)
    with pytest.raises(ValueError, match="NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY"):
        require_hourly_recovery_commit(plan, committed_at_ms=6*HOUR+1)


def test_recovery_cannot_extend_a_period_by_copying_its_model() -> None:
    period = build_generic_selection_period(feature_cutoff_at_ms=4*HOUR, cadence_hours=1)
    forged = period.model_copy(update={"period_expires_at_ms": 9*HOUR})
    with pytest.raises(ValueError):
        plan_hourly_recovery_close(recovery_id="recovery:forged",recovery_revision=1,
            reason="AUTHORITY_GAP",period=forged,evaluated_at_ms=5*HOUR+1)
