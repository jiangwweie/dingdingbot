from __future__ import annotations

import importlib
import importlib.util

import pytest


def _payload() -> dict[str, str]:
    return {
        "candidate_scope_id": "scope:CPM-RO-001:SOLUSDT:long",
        "candidate_scope_event_binding_id": "binding:scope:CPM-RO-001:SOLUSDT:long:event:CPM-LONG:v2",
        "runtime_scope_binding_id": "runtime_scope:scope:CPM-RO-001:SOLUSDT:long:pilot",
        "runtime_instance_id": "strategy-runtime-cpm-sol-long",
        "runtime_profile_id": "runtime-profile:pilot",
        "policy_current_id": "policy:CPM-RO-001:SOLUSDT:long",
        "strategy_group_id": "CPM-RO-001",
        "strategy_group_version_id": "sgv:CPM-RO-001:v2",
        "symbol": "SOLUSDT",
        "asset_class": "crypto_perpetual",
        "side": "long",
        "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
        "event_spec_version": "v2",
        "event_id": "CPM-LONG",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
    }


def test_runtime_lane_identity_is_immutable_complete_and_serializable() -> None:
    spec = importlib.util.find_spec("src.domain.runtime_lane_identity")
    assert spec is not None, "RuntimeLaneIdentity module must exist"

    module = importlib.import_module("src.domain.runtime_lane_identity")
    identity = module.RuntimeLaneIdentity.model_validate(_payload())

    assert identity.model_dump() == _payload()
    with pytest.raises((TypeError, ValueError, AttributeError)):
        identity.side = "short"
    with pytest.raises(ValueError):
        module.RuntimeLaneIdentity.model_validate({**_payload(), "side": "flat"})
    with pytest.raises(ValueError):
        module.RuntimeLaneIdentity.model_validate({**_payload(), "event_id": ""})
    with pytest.raises(ValueError):
        module.RuntimeLaneIdentity.model_validate({**_payload(), "unexpected": "value"})
