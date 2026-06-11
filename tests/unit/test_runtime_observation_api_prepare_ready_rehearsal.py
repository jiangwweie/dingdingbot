from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verify_runtime_observation_api_prepare_ready_rehearsal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_runtime_observation_api_prepare_ready_rehearsal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_rehearsal_reaches_prepare_without_execution():
    module = _load_module()

    report = module.build_rehearsal_report()

    assert report["status"] == "rehearsal_passed"
    assert report["checks"]["ready_without_allow_stops_before_prepare"] is True
    assert report["checks"]["allow_prepare_reaches_final_gate_preflight"] is True
    assert report["checks"]["prepared_authorization_id_present"] is True
    assert report["checks"]["forbidden_execution_flags"] == []
    assert report["dry_run_payload"]["status"] == "ready_for_prepare"
    assert report["dry_run_payload"]["prepare_packet"] is None
    assert report["allow_prepare_payload"]["status"] == "ready_for_final_gate_preflight"
    assert report["summary"]["prepared_authorization_id"] == "auth-ready-rehearsal"
    assert report["summary"]["real_submit_authorized"] is False
    assert report["operator_command_plan"]["places_order"] is False
    assert report["operator_command_plan"]["calls_order_lifecycle"] is False
    assert "run_disabled_first_real_submit_smoke" in report["operator_command_plan"][
        "allowed_after_real_ready_signal"
    ]
    assert "exchange order placement" in report["owner_gate"]["does_not_authorize"]
    assert report["owner_gate"]["rehearsal_only"] is True
    assert report["right_tail_objective_context"]["small_bounded_losses_allowed"] is True
    assert (
        report["right_tail_objective_context"]["unbounded_or_unreviewable_execution_forbidden"]
        is True
    )
    assert (
        report["allow_prepare_payload"]["prepare_packet"]["created_records"][
            "attempt_mutation_created"
        ]
        is False
    )
    assert all(value is False for key, value in report["safety_invariants"].items() if key != "local_in_memory_only")


def test_ready_rehearsal_cli_can_write_owner_review_json(tmp_path, capsys):
    module = _load_module()
    output_path = tmp_path / "ready-rehearsal.json"

    exit_code = module.main(["--output-json", str(output_path)])

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert file_payload["status"] == "rehearsal_passed"
    assert file_payload["owner_gate"]["rehearsal_only"] is True
    assert file_payload["operator_command_plan"]["places_order"] is False
