from __future__ import annotations

import json
import sys

from scripts import runtime_dry_run_audit_chain as audit_chain


def test_runtime_dry_run_audit_chain_covers_required_scenarios(tmp_path):
    packet = audit_chain.build_audit_chain(tmp_path)

    assert packet["status"] == "passed"
    assert packet["checks"]["scenario_count"] == 4
    assert packet["checks"]["all_scenarios_passed"] is True
    assert packet["checks"]["dangerous_effects_absent"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert packet["safety_invariants"]["disabled_smoke_is_real_execution_proof"] is False

    scenarios = {item["name"]: item for item in packet["scenarios"]}
    assert set(scenarios) == {
        "no_signal",
        "mock_fresh_signal_dry_run_pass",
        "required_facts_missing",
        "active_position_or_open_order_conflict",
    }
    assert scenarios["no_signal"]["artifacts"]["resume_dispatch"]["command_plan"] is None
    assert (
        scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
            "operation_layer_evidence_prep"
        ]["status"]
        == "operation_layer_ready"
    )
    assert (
        scenarios["mock_fresh_signal_dry_run_pass"]["artifacts"][
            "disabled_submit_smoke"
        ]["status"]
        == "disabled_smoke_passed"
    )
    assert scenarios["required_facts_missing"]["artifacts"]["readiness_bridge"][
        "status"
    ] == "ready_for_readiness_evidence"
    assert scenarios["active_position_or_open_order_conflict"]["artifacts"][
        "resume_dispatch"
    ]["blocker_class"] == "active_position_resolution"


def test_runtime_dry_run_audit_chain_cli_writes_packet(tmp_path, monkeypatch, capsys):
    output_json = tmp_path / "runtime-dry-run-audit-chain.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_dry_run_audit_chain.py",
            "--output-dir",
            str(tmp_path),
            "--output-json",
            str(output_json),
        ],
    )

    assert audit_chain.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "passed"
    assert packet["checks"]["required_scenarios_present"] is True
