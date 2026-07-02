from __future__ import annotations

import json

from scripts import runtime_next_attempt_release_from_reports
from tests.unit.test_runtime_next_attempt_release import (
    NOW_MS,
    _clear_gate,
    _resolution,
)

from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionStatus,
)


def test_release_from_reports_emits_json_only_projection(tmp_path, capsys):
    resolution = _resolution(
        RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
    )
    resolution_path = tmp_path / "active-position-resolution.json"
    resolution_path.write_text(
        "log line before json\n"
        + json.dumps(
            {
                "status": resolution.status.value,
                "artifact": resolution.model_dump(mode="json"),
            },
        ),
        encoding="utf-8",
    )
    gate_path = tmp_path / "next-attempt-gate.json"
    gate_path.write_text(json.dumps(_clear_gate()), encoding="utf-8")

    code = runtime_next_attempt_release_from_reports.main(
        [
            "--active-position-resolution-json",
            str(resolution_path),
            "--next-attempt-gate-json",
            str(gate_path),
            "--now-ms",
            str(NOW_MS),
        ],
    )

    assert code == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["status"] == "ready_for_strategy_signal"
    assert "release_evidence" in stdout
    assert "packet" not in stdout
    assert "operator_command_plan" not in stdout
    assert stdout["next_attempt_release_plan"]["executable_submit_allowed"] is False
    assert stdout["safety_invariants"]["next_attempt_release_projection_only"] is True
    assert "packet_only" not in stdout["safety_invariants"]
    assert stdout["safety_invariants"]["exchange_write_called"] is False
    assert stdout["safety_invariants"]["execution_intent_created"] is False
    assert stdout["safety_invariants"]["order_lifecycle_called"] is False


def test_release_from_reports_returns_blocked_exit_code_without_gate(tmp_path, capsys):
    resolution = _resolution(
        RuntimeActivePositionResolutionStatus.READY_FOR_NEXT_ATTEMPT_GATE,
    )
    resolution_path = tmp_path / "active-position-resolution.json"
    resolution_path.write_text(
        json.dumps({"artifact": resolution.model_dump(mode="json")}),
        encoding="utf-8",
    )

    code = runtime_next_attempt_release_from_reports.main(
        [
            "--active-position-resolution-json",
            str(resolution_path),
            "--now-ms",
            str(NOW_MS),
        ],
    )

    assert code == 2
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["status"] == "waiting_for_next_attempt_gate"
    assert "release_evidence" in stdout
    assert "packet" not in stdout
    assert "operator_command_plan" not in stdout
    assert stdout["next_attempt_release_plan"]["shadow_candidate_planning_allowed"] is False
