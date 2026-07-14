from __future__ import annotations

import pytest

from src.application.action_time.identity_conservation import (
    RuntimeLaneLineage,
    require_runtime_lane_identity_match,
    require_runtime_lane_lineage_match,
    runtime_lane_identity_from_live_signal,
    runtime_lane_lineage_from_record,
)
from src.domain.runtime_lane_identity import (
    RuntimeLaneIdentity,
    RuntimeLaneIdentityMismatch,
)


def _identity(*, side: str = "long") -> RuntimeLaneIdentity:
    return RuntimeLaneIdentity(
        candidate_scope_id="scope:CPM-RO-001:ETHUSDT:long",
        candidate_scope_event_binding_id="binding:CPM-RO-001:ETHUSDT:long:CPM-LONG",
        runtime_scope_binding_id="runtime-scope:CPM-RO-001:ETHUSDT:long",
        runtime_instance_id="runtime:CPM-RO-001:ETHUSDT:long",
        runtime_profile_id="runtime-profile:pilot",
        policy_current_id="policy:CPM-RO-001:ETHUSDT:long",
        strategy_group_id="CPM-RO-001",
        strategy_group_version_id="sgv:CPM-RO-001:v2",
        symbol="ETHUSDT",
        asset_class="crypto_perpetual",
        side=side,
        event_spec_id="event-spec:CPM-RO-001:CPM-LONG:v2",
        event_spec_version="v2",
        event_id="CPM-LONG",
        timeframe="1h",
        time_authority="trigger_candle_close_time_ms",
    )


def _lineage(*, source_watermark: str = "runtime:1") -> RuntimeLaneLineage:
    return RuntimeLaneLineage(
        lane_identity_key=_identity().identity_key,
        signal_event_id="signal:CPM-RO-001:ETHUSDT:long:1",
        source_watermark=source_watermark,
    )


def test_identity_guard_accepts_the_exact_resolved_lane() -> None:
    identity = _identity()

    require_runtime_lane_identity_match(
        expected=identity,
        actual=identity,
        boundary="signal_to_promotion",
    )


def test_identity_guard_rejects_cross_side_lane_at_first_boundary() -> None:
    with pytest.raises(RuntimeLaneIdentityMismatch) as raised:
        require_runtime_lane_identity_match(
            expected=_identity(),
            actual=_identity(side="short"),
            boundary="signal_to_promotion",
        )

    assert str(raised.value) == "runtime_lane_identity_mismatch:signal_to_promotion"
    assert raised.value.expected.side == "long"
    assert raised.value.actual.side == "short"


def test_lineage_guard_rejects_a_different_source_watermark_for_same_lane() -> None:
    with pytest.raises(RuntimeLaneIdentityMismatch) as raised:
        require_runtime_lane_lineage_match(
            expected=_lineage(source_watermark="runtime:1"),
            actual=_lineage(source_watermark="runtime:2"),
            boundary="promotion_to_action_time_lane",
        )

    assert str(raised.value) == (
        "runtime_lane_identity_mismatch:promotion_to_action_time_lane"
    )


def test_typed_live_signal_rehydrates_identity_and_source_lineage() -> None:
    identity = _identity()
    row = {
        **identity.model_dump(mode="json"),
        "lane_identity_key": identity.identity_key,
        "signal_event_id": "signal:CPM-RO-001:ETHUSDT:long:1",
        "source_watermark": "runtime:1",
    }

    assert runtime_lane_identity_from_live_signal(row) == identity
    assert runtime_lane_lineage_from_record(row) == _lineage()
