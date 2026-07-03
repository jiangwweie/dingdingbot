from __future__ import annotations

import os
import sys

from scripts import runtime_next_attempt_prepare_api_flow


def test_next_attempt_prepare_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("RUNTIME_NEXT_ATTEMPT_PREPARE_API_BASE=http://unit")
    monkeypatch.setenv("RUNTIME_NEXT_ATTEMPT_PREPARE_API_BASE", "")

    runtime_next_attempt_prepare_api_flow._load_env_file(str(env_file))

    assert os.environ["RUNTIME_NEXT_ATTEMPT_PREPARE_API_BASE"] == "http://unit"


def test_next_attempt_prepare_requires_candidate_or_signal_input(capsys):
    exit_code = runtime_next_attempt_prepare_api_flow.main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "runtime_next_attempt_prepare_artifact" in captured.out
    assert "runtime_next_attempt_prepare_packet" not in captured.out
    assert "order_candidate_id_or_signal_input_json_required" in captured.out
    assert "order_lifecycle_called" in captured.out


def test_next_attempt_prepare_summary_is_final_gate_preflight_only():
    report = {
        "ids": {
            "runtime_execution_intent_draft_id": "draft-1",
            "execution_intent_id": "intent-1",
            "authorization_id": "auth-1",
            "protection_plan_id": "protection-1",
        },
        "steps": [
            {"name": "verify_next_attempt_gate"},
            {"name": "record_intent_draft"},
            {"name": "record_execution_intent"},
            {"name": "record_protection_plan"},
            {"name": "record_submit_authorization"},
        ],
        "blockers": [],
        "warnings": [],
        "next_attempt_gate": {
            "status": "clear_for_preflight",
            "gate": "clear_for_next_preflight",
            "next_attempt_allowed_by_lifecycle": True,
        },
    }

    payload = runtime_next_attempt_prepare_api_flow._summarize_prepare_report(report)

    assert payload["scope"] == "runtime_next_attempt_prepare_artifact"
    assert payload["status"] == "ready_for_final_gate_preflight"
    assert "operator_command_plan" not in payload
    assert payload["prepare_artifact_plan"]["prepared_authorization_id"] == "auth-1"
    assert payload["prepare_artifact_plan"]["live_submit_allowed"] is False
    assert payload["created_records"]["execution_intent_created"] is True
    assert payload["created_records"]["submit_authorization_created"] is True
    assert payload["created_records"]["attempt_mutation_created"] is False
    assert payload["safety_invariants"]["exchange_write_called"] is False
    assert payload["safety_invariants"]["order_lifecycle_called"] is False


def test_next_attempt_prepare_summary_blocks_without_authorization():
    report = {
        "ids": {
            "runtime_execution_intent_draft_id": "draft-1",
            "execution_intent_id": "intent-1",
        },
        "steps": [{"name": "verify_next_attempt_gate"}],
        "blockers": ["authorization_id_missing"],
        "warnings": [],
        "next_attempt_gate": {"status": "clear_for_preflight"},
    }

    payload = runtime_next_attempt_prepare_api_flow._summarize_prepare_report(report)

    assert payload["status"] == "blocked"
    assert "operator_command_plan" not in payload
    assert payload["prepare_artifact_plan"]["next_step"] == "resolve_prepare_blockers"
    assert payload["blockers"] == ["authorization_id_missing"]


def test_next_attempt_prepare_summary_does_not_infer_shadow_candidate_from_observe_only_step():
    report = {
        "ids": {},
        "steps": [
            {
                "name": "create_shadow_candidate_from_signal_input",
                "status": "observe_only",
            }
        ],
        "blockers": ["order_candidate_id_or_authorization_id_required"],
        "warnings": ["runtime_live_execution_enabled_operation_layer_handoff"],
        "next_attempt_gate": {"status": "clear_for_preflight"},
    }

    payload = runtime_next_attempt_prepare_api_flow._summarize_prepare_report(report)

    assert payload["status"] == "blocked"
    assert payload["created_records"]["shadow_candidate_created"] is False
    assert payload["created_records"]["runtime_execution_intent_draft_created"] is False
    assert payload["created_records"]["submit_authorization_created"] is False


def test_next_attempt_prepare_cli_redirects_inner_report_stdout(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, *, api_base):
            self.api_base = api_base

    class FakeFlow:
        def __init__(self, *, client, config):
            self.client = client
            self.config = config

        def run(self):
            print("inner noisy report")
            return {
                "ids": {
                    "runtime_execution_intent_draft_id": "draft-1",
                    "execution_intent_id": "intent-1",
                    "authorization_id": "auth-1",
                },
                "steps": [{"name": "record_submit_authorization"}],
                "blockers": [],
                "warnings": [],
                "next_attempt_gate": {"status": "clear_for_preflight"},
            }

    monkeypatch.setattr(runtime_next_attempt_prepare_api_flow, "UrlLibApiClient", FakeClient)
    monkeypatch.setattr(runtime_next_attempt_prepare_api_flow, "FirstRealSubmitApiFlow", FakeFlow)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_prepare_api_flow.py",
            "--order-candidate-id",
            "candidate-1",
        ],
    )

    assert runtime_next_attempt_prepare_api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy report" not in captured.out
    assert "inner noisy report" in captured.err
