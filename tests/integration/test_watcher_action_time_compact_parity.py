from __future__ import annotations

from scripts import runtime_active_observation_monitor as watcher
from src.interfaces.api_trading_console import (
    _runtime_next_attempt_observation_safety,
    _runtime_observation_response_projection,
)


def _payload() -> dict:
    raw_marker = "multi-megabyte-review-only-marker" * 20_000
    output = {
        "signal_type": "entry",
        "signal_grade": "observe_only_signal",
        "required_execution_mode": "observe_only",
        "side": "long",
        "reason_codes": ["breakout_pending"],
        "human_summary": "waiting",
        "confidence": "0.9",
        "timestamp_ms": 100,
        "time_authority": "trigger_candle_close_time_ms",
        "trigger_candle_close_time_ms": 90,
        "data_quality": {"status": "valid"},
        "signal_snapshot": {
            "logic_version": "v1",
            "context_tags": {"regime": "trend"},
        },
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
        "review_only_trace": raw_marker,
    }
    return {
        "scope": "runtime_next_attempt_observation_cycle_api",
        "status": "waiting_for_opportunity",
        "blocked_stage": None,
        "runtime_instance_id": "runtime-1",
        "owner_action_scope": {},
        "include_exchange": False,
        "next_attempt_gate": {"trace": raw_marker},
        "just_in_time_lifecycle_audit": {"trace": raw_marker},
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
                "evaluator_id": "evaluator-v1",
                "evaluated_at_ms": 100,
                "valid_until_ms": 200,
                "can_call_semantic_binding": True,
                "semantics_binding_found": True,
                "strategy_candidate_mode": "observe",
                "signal": output,
            },
        },
        "action_time_ticket": None,
        "blockers": [],
        "warnings": [],
        "observation_cycle_plan": {"next_step": "wait"},
        "safety_invariants": _runtime_next_attempt_observation_safety(),
    }


def test_full_and_compact_preserve_watcher_action_time_decision_semantics():
    payload = _payload()
    full = _runtime_observation_response_projection(
        payload,
        response_projection="full",
    )
    compact = _runtime_observation_response_projection(
        payload,
        response_projection="watcher_compact",
    )

    assert watcher._signal_summary(full) == watcher._signal_summary(compact)
    assert "multi-megabyte-review-only-marker" in str(full)
    assert "multi-megabyte-review-only-marker" not in str(compact)
    assert compact["safety_invariants"] == {
        key: payload["safety_invariants"][key]
        for key in compact["safety_invariants"]
    }
