from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.selection_authority import (
    SelectionControl,
    SelectionMode,
)
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR


@pytest.mark.asyncio
@pytest.mark.parametrize("case,expected", [
    ("due_ready", True), ("source_failed", False), ("future", False),
    ("late_commit", False), ("expired", False), ("other_member", False),
    ("rebase_pending", False), ("no_intent", False), ("failed_generation", False),
])
async def test_static_close_handover_requires_due_precommitted_exact_intent(case: str, expected: bool) -> None:
    from src.trading_kernel.application.ingest_signal import (
        pending_dynamic_close_handover,
    )

    spec = generic_selection_spec("MI-001")
    control = SelectionControl(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,
        selection_mode=SelectionMode.STATIC_BASELINE,pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
        pending_effective_period_anchor_ms=CUTOFF,pending_authorization_id="owner:original",control_version=2,
        rollback_baseline_id="rollback:original",selection_epoch_id="epoch:original",updated_at_ms=CUTOFF-1)
    if case == "no_intent":
        control = control.model_copy(update={"pending_selection_mode":None,"pending_effective_period_anchor_ms":None,"pending_authorization_id":None})
    snapshot = SimpleNamespace(selection_snapshot_id="snapshot:due",selection_spec_id=spec.selection_spec_id,selection_epoch_id=control.selection_epoch_id,
        feature_cutoff_at_ms=CUTOFF,committed_at_ms=CUTOFF+10,effective_from_ms=CUTOFF+HOUR,
        expires_at_ms=CUTOFF+2*HOUR,selected_members=spec.candidate_ids[:1])
    if case == "future": snapshot.effective_from_ms=CUTOFF+2*HOUR
    if case == "late_commit": snapshot.committed_at_ms=CUTOFF+HOUR+1
    if case == "expired": snapshot.expires_at_ms=CUTOFF+HOUR
    member=spec.candidate_ids[1] if case == "other_member" else spec.candidate_ids[0]
    repo=SimpleNamespace(get_selection_job=AsyncMock(return_value=SimpleNamespace(
        state="SOURCE_FAILED" if case == "source_failed" else "SNAPSHOT_READY",selection_snapshot_id="snapshot:due")),
        get_generic_snapshot=AsyncMock(return_value=snapshot),get_generic_materialization_generation=AsyncMock(return_value=
            SimpleNamespace(lifecycle_state=SimpleNamespace(value="FAILED_CLOSED")) if case == "failed_generation" else None),generic_recovery_transition_blocker=AsyncMock(
            return_value="GENERIC_RECOVERY_REBASE_PENDING" if case == "rebase_pending" else None))
    scope=SimpleNamespace(strategy_group_id=spec.strategy_group_id,event_spec_id=spec.event_spec_id,
        exchange_instrument_id=member,lifecycle_state="active")
    result=await pending_dynamic_close_handover(SimpleNamespace(instrument_selection=repo),
        control=control,runtime_scope=scope,observed_close_time_ms=CUTOFF+HOUR,now_ms=CUTOFF+HOUR+1)
    assert result is expected
