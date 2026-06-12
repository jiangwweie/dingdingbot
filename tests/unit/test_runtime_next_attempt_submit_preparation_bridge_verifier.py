import json
import subprocess
import sys

import pytest

from scripts.verify_runtime_next_attempt_submit_preparation_bridge import (
    build_next_attempt_submit_preparation_bridge_report,
)


@pytest.mark.asyncio
async def test_next_attempt_submit_preparation_bridge_covers_ready_and_blocks():
    report = await build_next_attempt_submit_preparation_bridge_report()

    assert report["status"] == "rtf050_next_attempt_submit_preparation_bridge_passed"
    assert report["source_planning_report_status"] == (
        "rtf049_next_attempt_gate_strategy_planning_passed"
    )
    assert report["scenario_count"] == 3
    assert report["safety_summary"] == {
        "local_in_memory_only": True,
        "database_connected": False,
        "http_network_called": False,
        "official_submit_endpoint_called": False,
        "exchange_write_called": False,
        "pre_submit_rehearsal_called": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
    }

    scenarios = {item["scenario_id"]: item for item in report["scenarios"]}
    assert set(scenarios) == {
        "ready-cpm-long-submit-preparation",
        "blocked-active-position-submit-preparation-blocked",
        "waiting-rmr-observe-only-submit-preparation-blocked",
    }

    ready = scenarios["ready-cpm-long-submit-preparation"]
    assert ready["status"] == "passed"
    assert ready["strategy_planning_status"] == "ready_for_final_gate_preflight"
    assert ready["readiness_status"] == "ready_for_executable_submit"
    assert ready["missing_auth_handoff_status"] == "blocked"
    assert ready["disabled_handoff_status"] == "ready_for_official_submit_call"
    assert ready["real_mode_handoff_status"] == "ready_for_official_submit_call"
    assert ready["official_endpoint_path"].startswith(
        "/api/trading-console/runtime-execution-first-real-submit-actions/"
    )
    assert ready["official_query"]["owner_confirmed_for_first_real_submit_action"] is False
    assert ready["checks"]["fresh_auth_is_not_consumed_authorization"] is True
    assert ready["checks"]["official_endpoint_not_called"] is True
    assert ready["checks"]["no_execution_side_effects"] is True
    assert ready["checks"]["legacy_pre_attempt_rehearsal_not_required"] is True
    assert ready["checks"]["durable_execution_result_is_post_submit_evidence_only"] is True

    active_block = scenarios["blocked-active-position-submit-preparation-blocked"]
    assert active_block["status"] == "passed"
    assert active_block["readiness_status"] == "not_run"
    assert "runtime_active_position_slot_in_use" in active_block["blockers"]
    assert active_block["checks"]["handoff_not_run"] is True

    observe_only = scenarios["waiting-rmr-observe-only-submit-preparation-blocked"]
    assert observe_only["status"] == "passed"
    assert observe_only["readiness_status"] == "not_run"
    assert "strategy_candidate_mode_not_runtime_candidate:regime_classifier_only" in (
        observe_only["blockers"]
    )
    assert observe_only["checks"]["handoff_not_run"] is True


def test_next_attempt_submit_preparation_bridge_script_writes_json(tmp_path):
    output_path = tmp_path / "rtf050-next-attempt-submit-preparation-bridge.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_runtime_next_attempt_submit_preparation_bridge.py",
            "--output-json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == (
        "rtf050_next_attempt_submit_preparation_bridge_passed"
    )
    assert file_payload["status"] == stdout_payload["status"]
    assert file_payload["scenario_count"] == 3
