import json
import subprocess
import sys

import pytest

from scripts.verify_runtime_post_submit_finalize_loop import (
    build_post_submit_finalize_loop_report,
)


@pytest.mark.asyncio
async def test_post_submit_finalize_loop_report_covers_runtime_level_paths():
    report = await build_post_submit_finalize_loop_report()

    assert report["status"] == "rtf048_runtime_post_submit_finalize_loop_passed"
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
        "latest-result-ready-for-fresh-signal",
        "latest-result-active-position-blocks-next-attempt",
        "latest-result-missing-blocks-finalize",
    }

    ready = scenarios["latest-result-ready-for-fresh-signal"]
    assert ready["packet_status"] == "finalized_ready_for_next_attempt"
    assert ready["next_attempt_gate_status"] == "ready_for_fresh_signal"
    assert ready["checks"]["latest_result_resolved_without_manual_authorization"] is True
    assert ready["checks"]["old_authorization_replay_only"] is True
    assert ready["checks"]["pre_submit_rehearsal_retry_disallowed"] is True
    assert ready["checks"]["local_created_order_requirement_retired"] is True
    assert ready["checks"]["requires_fresh_signal_and_authorization"] is True
    assert ready["checks"]["no_execution_side_effects"] is True

    active_position = scenarios["latest-result-active-position-blocks-next-attempt"]
    assert active_position["packet_status"] == "finalized_next_attempt_blocked"
    assert active_position["blockers"] == []
    assert active_position["next_attempt_gate_status"] == "blocked"
    assert "runtime_active_position_slot_in_use" in (
        active_position["next_attempt_blockers"]
    )

    missing = scenarios["latest-result-missing-blocks-finalize"]
    assert missing["packet_status"] == "blocked"
    assert "latest_exchange_submit_execution_result_not_found" in missing["blockers"]
    assert "trusted_active_positions_count_missing" in missing["next_attempt_blockers"]
    assert missing["checks"]["adapter_not_used_to_create_missing_facts"] is True


def test_post_submit_finalize_loop_script_writes_json(tmp_path):
    output_path = tmp_path / "rtf048-post-submit-finalize-loop.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_runtime_post_submit_finalize_loop.py",
            "--output-json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "rtf048_runtime_post_submit_finalize_loop_passed"
    assert file_payload["status"] == stdout_payload["status"]
    assert file_payload["scenario_count"] == 3
