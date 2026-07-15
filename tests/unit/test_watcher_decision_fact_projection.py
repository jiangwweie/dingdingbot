from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.readmodels.watcher_decision_fact_projection import (
    ActionTimeDecisionFactProjection,
    WATCHER_SAFETY_BOOLEAN_KEYS,
    WatcherRuntimeEffect,
)
from src.interfaces.api_trading_console import (
    _runtime_observation_response_projection,
    _runtime_next_attempt_observation_safety,
)


def _safety():
    return {key: False for key in WATCHER_SAFETY_BOOLEAN_KEYS}


def test_watcher_runtime_effect_rejects_non_boolean_without_coercion():
    safety = _safety()
    safety["exchange_write_called"] = 0

    with pytest.raises(
        ValueError,
        match="watcher_safety_projection_invalid:exchange_write_called",
    ):
        WatcherRuntimeEffect.model_validate(
            {"status": "waiting_for_opportunity", "safety_invariants": safety}
        )


def test_decision_projection_preserves_typed_fact_observation():
    projection = ActionTimeDecisionFactProjection.model_validate(
        {
            "signal_snapshot": {"logic_version": "v1"},
            "evidence_payload": {"breakout": True},
            "action_time_fact_values": {"mark_price": "100"},
            "fact_observations": [
                {
                    "fact_key": "leader_strength",
                    "observed_value": Decimal("0.90"),
                    "observed_at_ms": 100,
                    "valid_until_ms": 200,
                    "source_ref": "unit",
                }
            ],
        }
    )

    assert projection.fact_observations[0].observed_value == Decimal("0.90")


def test_decision_projection_rejects_oversized_map():
    with pytest.raises(
        ValueError,
        match="watcher_compact_projection_oversize:signal_snapshot",
    ):
        ActionTimeDecisionFactProjection.model_validate(
            {"signal_snapshot": {"raw": "x" * (64 * 1024)}}
        )


def test_compact_observation_drops_raw_artifacts_and_preserves_decision_facts():
    raw_marker = "raw-candles-marker" * 10_000
    payload = {
        "scope": "runtime_next_attempt_observation_cycle_api",
        "status": "waiting_for_opportunity",
        "runtime_instance_id": "runtime-1",
        "owner_action_scope": {},
        "include_exchange": False,
        "next_attempt_gate": {"raw": raw_marker},
        "just_in_time_lifecycle_audit": {"raw": raw_marker},
        "signal_artifact": {
            "scope": "signal",
            "status": "waiting_for_opportunity",
            "runtime_instance_id": "runtime-1",
            "strategy_family_id": "SG-1",
            "strategy_family_version_id": "v1",
            "symbol": "ETHUSDT",
            "side": "long",
            "lane_identity": None,
            "lane_identity_key": None,
            "can_materialize_live_signal_event": False,
            "source": "unit",
            "source_type": "read_only",
            "signal_input": {"candles": raw_marker},
            "evaluation_result": {
                "status": "computed_not_satisfied",
                "signal": {
                    "reason_codes": ["waiting"],
                    "signal_snapshot": {"logic_version": "v1"},
                    "evidence_payload": {"breakout": False},
                    "fact_observations": [
                        {
                            "fact_key": "breakout",
                            "observed_value": False,
                            "observed_at_ms": 100,
                            "valid_until_ms": 200,
                            "source_ref": "unit",
                        }
                    ],
                },
            },
        },
        "action_time_ticket": None,
        "blockers": [],
        "warnings": [],
        "observation_cycle_plan": {"next_step": "wait"},
        "safety_invariants": _runtime_next_attempt_observation_safety(),
    }

    compact = _runtime_observation_response_projection(
        payload,
        response_projection="watcher_compact",
    )

    encoded = str(compact)
    assert raw_marker not in encoded
    output = compact["signal_artifact"]["evaluation_result"]["signal"]
    assert output["signal_snapshot"] == {"logic_version": "v1"}
    assert output["evidence_payload"] == {"breakout": False}
    assert output["action_time_fact_values"] == {"breakout": False}
