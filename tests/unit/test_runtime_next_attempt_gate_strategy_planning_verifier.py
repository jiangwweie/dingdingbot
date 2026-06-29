import json
import subprocess
import sys

import pytest

from scripts import verify_runtime_next_attempt_gate_strategy_planning as verifier
from scripts.verify_runtime_next_attempt_gate_strategy_planning import (
    build_next_attempt_gate_strategy_planning_report,
)


@pytest.mark.asyncio
async def test_next_attempt_gate_strategy_planning_report_covers_ready_block_wait():
    report = await build_next_attempt_gate_strategy_planning_report()

    assert report["status"] == "rtf049_next_attempt_gate_strategy_planning_passed"
    assert report["scenario_count"] == 3
    assert report["safety_summary"] == {
        "local_in_memory_only": True,
        "database_connected": False,
        "http_network_called": False,
        "exchange_write_called": False,
        "pre_submit_rehearsal_called": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "order_created": False,
        "withdrawal_or_transfer_created": False,
    }

    scenarios = {item["scenario_id"]: item for item in report["scenarios"]}
    assert set(scenarios) == {
        "ready-cpm-long",
        "blocked-active-position",
        "waiting-rmr-observe-only",
    }

    ready = scenarios["ready-cpm-long"]
    assert ready["strategy_planning_status"] == "ready_for_final_gate_preflight"
    assert ready["next_attempt_gate_status"] == "ready_for_fresh_signal"
    assert ready["planner_calls"] == 1
    assert ready["order_candidate_id"] is not None
    assert ready["checks"]["shadow_candidate_created"] is True
    assert ready["checks"]["fresh_authorization_required_before_submit"] is True
    assert ready["checks"]["consumed_authorization_replay_only"] is True

    blocked = scenarios["blocked-active-position"]
    assert blocked["strategy_planning_status"] == "blocked_by_post_submit_gate"
    assert blocked["next_attempt_gate_status"] == "blocked"
    assert blocked["planner_calls"] == 0
    assert blocked["order_candidate_id"] is None
    assert "runtime_active_position_slot_in_use" in blocked["blockers"]

    waiting = scenarios["waiting-rmr-observe-only"]
    assert waiting["strategy_planning_status"] == "waiting_for_signal"
    assert waiting["planner_calls"] == 1
    assert waiting["order_candidate_id"] is None
    assert "strategy_candidate_mode_not_runtime_candidate:regime_classifier_only" in (
        waiting["blockers"]
    )

    for item in scenarios.values():
        assert item["status"] == "passed"
        assert item["checks"]["no_execution_side_effects"] is True
        assert item["checks"]["pre_submit_rehearsal_retry_disallowed"] is True
        assert "strategy_planning_packet" not in item
        assert "strategy_planning_artifact" in item


def test_next_attempt_gate_strategy_planning_script_writes_json(tmp_path):
    output_path = tmp_path / "rtf049-next-attempt-gate-strategy-planning.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_runtime_next_attempt_gate_strategy_planning.py",
            "--output-json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "rtf049_next_attempt_gate_strategy_planning_passed"
    assert file_payload["status"] == stdout_payload["status"]
    assert file_payload["scenario_count"] == 3


def test_next_attempt_gate_strategy_planning_uses_payload_helper_boundary():
    assert hasattr(verifier, "_finalize_payload")
    assert not hasattr(verifier, "_finalize_packet")
    assert "runtime packet" not in (verifier.__doc__ or "")
    assert "runtime payload" in (verifier.__doc__ or "")
