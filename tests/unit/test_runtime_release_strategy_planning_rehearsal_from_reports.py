from __future__ import annotations

import json

from scripts import runtime_release_strategy_planning_rehearsal_from_reports
from tests.unit.test_runtime_next_attempt_release import (
    NOW_MS,
    _blocked_gate,
    _clear_gate,
    _resolution,
)
from tests.unit.test_runtime_next_attempt_strategy_planning import _signal_input

from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionStatus,
)
from src.domain.runtime_next_attempt_release import (
    build_runtime_next_attempt_release_packet,
)


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _release_report(status, gate):
    release = build_runtime_next_attempt_release_packet(
        active_position_resolution=_resolution(status),
        next_attempt_gate_packet=gate,
        now_ms=NOW_MS,
    )
    return {
        "status": release.status.value,
        "packet": release.model_dump(mode="json"),
    }


def test_release_rehearsal_calls_planner_when_release_ready(tmp_path):
    release_path = tmp_path / "next-attempt-release.json"
    signal_path = tmp_path / "signal-input.json"
    _write_json(
        release_path,
        _release_report(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
            _clear_gate(),
        ),
    )
    _write_json(signal_path, {"signal_input": _signal_input().model_dump(mode="json")})

    packet = runtime_release_strategy_planning_rehearsal_from_reports._build_packet(
        type(
            "Args",
            (),
            {
                "next_attempt_release_json": str(release_path),
                "signal_input_json": str(signal_path),
                "planning_status": "shadow_candidate_created",
                "context_id": "ctx-1",
                "expires_at_ms": None,
                "now_ms": NOW_MS,
            },
        )(),
    )

    import asyncio

    result = asyncio.run(packet)
    assert result["status"] == "ready_for_final_gate_preflight"
    assert result["planner_called"] is True
    assert result["packet"]["order_candidate_id"] == "rehearsal-order-candidate-eval-fresh"
    assert result["packet"]["operator_command_plan"]["creates_shadow_candidate"] is True
    assert result["packet"]["operator_command_plan"]["live_submit_allowed"] is False
    assert result["safety_invariants"]["pg_write_called"] is False
    assert result["safety_invariants"]["exchange_write_called"] is False
    assert result["safety_invariants"]["order_lifecycle_called"] is False


def test_release_rehearsal_blocks_before_planner_when_release_blocked(tmp_path):
    release_path = tmp_path / "next-attempt-release.json"
    signal_path = tmp_path / "signal-input.json"
    _write_json(
        release_path,
        _release_report(
            RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
            _blocked_gate(),
        ),
    )
    _write_json(signal_path, _signal_input().model_dump(mode="json"))

    import asyncio

    result = asyncio.run(
        runtime_release_strategy_planning_rehearsal_from_reports._build_packet(
            type(
                "Args",
                (),
                {
                    "next_attempt_release_json": str(release_path),
                    "signal_input_json": str(signal_path),
                    "planning_status": "shadow_candidate_created",
                    "context_id": None,
                    "expires_at_ms": None,
                    "now_ms": NOW_MS,
                },
            )(),
        ),
    )

    assert result["status"] == "blocked_by_release_gate"
    assert result["planner_called"] is False
    assert "next_attempt_release_not_ready_for_strategy_signal" in result["packet"]["blockers"]
    assert result["packet"]["operator_command_plan"]["creates_shadow_candidate"] is False
    assert result["safety_invariants"]["order_created"] is False
