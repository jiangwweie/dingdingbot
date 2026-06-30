import json
import subprocess
import sys

import pytest

from scripts.verify_runtime_official_submit_action_time_evidence import (
    build_official_submit_action_time_evidence_report,
)


@pytest.mark.asyncio
async def test_official_submit_action_time_evidence_covers_disabled_and_refusals(tmp_path):
    report = await build_official_submit_action_time_evidence_report(
        work_dir=tmp_path / "action-time-inputs",
    )

    assert report["status"] == "rtf051_official_submit_action_time_evidence_passed"
    assert report["source_submit_preparation_status"] == (
        "rtf050_next_attempt_submit_preparation_evidence_passed"
    )
    assert report["scenario_count"] == 3
    disabled_handoff = json.loads(
        open(report["artifact_paths"]["disabled_handoff"], encoding="utf-8").read()
    )
    real_mode_handoff = json.loads(
        open(report["artifact_paths"]["real_mode_handoff"], encoding="utf-8").read()
    )
    assert "packet" not in disabled_handoff
    assert "packet" not in real_mode_handoff
    assert disabled_handoff["handoff_artifact"]["status"] == (
        "ready_for_official_submit_call"
    )
    assert real_mode_handoff["handoff_artifact"]["status"] == (
        "ready_for_official_submit_call"
    )
    assert report["safety_summary"] == {
        "local_fake_client_only": True,
        "database_connected": False,
        "http_network_called": False,
        "official_submit_endpoint_contract_exercised": True,
        "real_gateway_action_requested": False,
        "owner_confirmed_for_first_real_submit_action": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "order_created": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
    }

    scenarios = {item["scenario_id"]: item for item in report["scenarios"]}
    assert set(scenarios) == {
        "disabled-smoke-action-time-from-rtf050-handoff",
        "real-gateway-handoff-refused-by-disabled-smoke",
        "disabled-smoke-enabled-response-blocked",
    }

    disabled = scenarios["disabled-smoke-action-time-from-rtf050-handoff"]
    assert disabled["status"] == "passed"
    assert disabled["report_status"] == "disabled_smoke_passed"
    assert disabled["call_count"] == 1
    assert disabled["checks"]["method_is_post"] is True
    assert disabled["checks"]["path_is_official_first_real_submit_action"] is True
    assert disabled["checks"]["owner_confirmation_false"] is True
    assert disabled["checks"]["required_query_ids_present"] is True
    assert disabled["checks"]["response_exchange_submit_disabled"] is True
    assert disabled["checks"]["no_real_exchange_effect"] is True
    assert disabled["official_call"]["query"][
        "owner_confirmed_for_first_real_submit_action"
    ] is False

    real_refused = scenarios["real-gateway-handoff-refused-by-disabled-smoke"]
    assert real_refused["status"] == "passed"
    assert real_refused["call_count"] == 0
    assert "disabled_smoke_refuses_real_gateway_handoff" in real_refused["blockers"]
    assert real_refused["checks"]["official_endpoint_not_called"] is True

    enabled_block = scenarios["disabled-smoke-enabled-response-blocked"]
    assert enabled_block["status"] == "passed"
    assert enabled_block["call_count"] == 1
    assert "disabled_smoke_response_enabled_exchange_submit" in (
        enabled_block["blockers"]
    )
    assert "disabled_smoke_response_mode:real_gateway_action" in (
        enabled_block["warnings"]
    )
    assert enabled_block["checks"]["owner_confirmation_still_false"] is True


def test_official_submit_action_time_evidence_script_writes_json(tmp_path):
    output_path = tmp_path / "rtf051-official-submit-action-time-evidence.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_runtime_official_submit_action_time_evidence.py",
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
        "rtf051_official_submit_action_time_evidence_passed"
    )
    assert file_payload["status"] == stdout_payload["status"]
    assert file_payload["scenario_count"] == 3
