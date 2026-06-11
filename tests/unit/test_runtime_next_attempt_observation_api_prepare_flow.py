from __future__ import annotations

import argparse
import os
import sys

from scripts import runtime_next_attempt_observation_api_prepare_flow


def _args(**overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "env_file": None,
        "api_base": "http://unit",
        "source": "sample",
        "include_exchange": False,
        "symbol": None,
        "side": None,
        "family": None,
        "strategy_family_id": None,
        "carrier_id": None,
        "quantity": None,
        "target_notional_usdt": None,
        "max_notional": None,
        "leverage": None,
        "max_attempts": None,
        "protection_mode": None,
        "review_requirement": None,
        "evaluation_id": None,
        "playbook_id": None,
        "one_hour_limit": 25,
        "four_hour_limit": 12,
        "timeout_seconds": 10.0,
        "signal_output_json": None,
        "output_dir": "output/runtime-next-attempt-observation-api-prepare-flow",
        "allow_prepare_records": False,
        "candidate_id": None,
        "context_id": None,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
        "reason": "unit observation api prepare",
        "next_attempt_symbol": None,
        "next_attempt_side": None,
        "next_attempt_family": None,
        "next_attempt_strategy_family_id": None,
        "next_attempt_carrier_id": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {"http_status": 200, "body": self.payload}


def _waiting_payload():
    return {
        "status": "waiting_for_signal",
        "blocked_stage": "strategy_signal",
        "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": [],
        "operator_command_plan": {"next_step": "observe_only_or_wait_for_next_closed_bar"},
        "signal_packet": {
            "signal_input": {
                "evaluation_id": "eval-1",
                "strategy_family_id": "BTPC-001",
            }
        },
    }


def _ready_payload():
    return {
        "status": "ready_for_prepare",
        "blockers": [],
        "warnings": [],
        "operator_command_plan": {"next_step": "run_official_runtime_next_attempt_prepare_api_flow"},
        "signal_packet": {
            "signal_input": {
                "evaluation_id": "eval-ready",
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
            }
        },
    }


def test_observation_api_prepare_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("RUNTIME_NEXT_ATTEMPT_OBSERVATION_API_BASE=http://unit")
    monkeypatch.setenv("RUNTIME_NEXT_ATTEMPT_OBSERVATION_API_BASE", "")

    runtime_next_attempt_observation_api_prepare_flow._load_env_file(str(env_file))

    assert os.environ["RUNTIME_NEXT_ATTEMPT_OBSERVATION_API_BASE"] == "http://unit"


def test_observation_api_prepare_waits_without_prepare(monkeypatch, tmp_path):
    def fail_prepare(args, *, signal_input_json):
        raise AssertionError("prepare flow must not run while waiting for signal")

    monkeypatch.setattr(
        runtime_next_attempt_observation_api_prepare_flow,
        "_run_prepare_flow",
        fail_prepare,
    )
    payload = runtime_next_attempt_observation_api_prepare_flow._build_packet(
        _args(signal_output_json=str(tmp_path / "signal.json")),
        client=_Client(_waiting_payload()),
    )

    assert payload["status"] == "waiting_for_signal"
    assert payload["signal_input_json"].endswith("signal.json")
    assert payload["operator_command_plan"]["creates_shadow_candidate"] is False
    assert payload["safety_invariants"]["prepare_records_created"] is False
    assert payload["safety_invariants"]["order_created"] is False


def test_observation_api_prepare_ready_writes_signal_without_records(monkeypatch, tmp_path):
    def fail_prepare(args, *, signal_input_json):
        raise AssertionError("prepare flow must require explicit flag")

    monkeypatch.setattr(
        runtime_next_attempt_observation_api_prepare_flow,
        "_run_prepare_flow",
        fail_prepare,
    )
    signal_path = tmp_path / "ready-signal.json"
    payload = runtime_next_attempt_observation_api_prepare_flow._build_packet(
        _args(signal_output_json=str(signal_path)),
        client=_Client(_ready_payload()),
    )

    assert payload["status"] == "ready_for_prepare"
    assert payload["signal_input_json"] == str(signal_path)
    assert signal_path.exists()
    assert payload["operator_command_plan"]["next_step"] == (
        "rerun_with_allow_prepare_records_after_owner_review"
    )
    assert payload["operator_command_plan"]["creates_execution_intent"] is False
    assert payload["safety_invariants"]["prepare_records_created"] is False


def test_observation_api_prepare_runs_prepare_only_with_explicit_flag(monkeypatch, tmp_path):
    signal_path = tmp_path / "ready-signal.json"

    def fake_prepare(args, *, signal_input_json):
        assert signal_input_json == str(signal_path)
        return {
            "status": "ready_for_final_gate_preflight",
            "blockers": [],
            "warnings": [],
            "operator_command_plan": {
                "prepared_authorization_id": "auth-1",
            },
        }

    monkeypatch.setattr(
        runtime_next_attempt_observation_api_prepare_flow,
        "_run_prepare_flow",
        fake_prepare,
    )
    payload = runtime_next_attempt_observation_api_prepare_flow._build_packet(
        _args(
            allow_prepare_records=True,
            signal_output_json=str(signal_path),
        ),
        client=_Client(_ready_payload()),
    )

    assert payload["status"] == "ready_for_final_gate_preflight"
    assert payload["operator_command_plan"]["prepared_authorization_id"] == "auth-1"
    assert payload["operator_command_plan"]["live_submit_allowed"] is False
    assert payload["safety_invariants"]["prepare_records_created"] is True
    assert payload["safety_invariants"]["exchange_write_called"] is False
    assert payload["safety_invariants"]["order_lifecycle_called"] is False


def test_observation_api_prepare_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_packet(args):
        print("inner noisy observation")
        return {"status": "ready_for_prepare", "ok": True}

    monkeypatch.setattr(
        runtime_next_attempt_observation_api_prepare_flow,
        "_build_packet",
        fake_build_packet,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_next_attempt_observation_api_prepare_flow.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_next_attempt_observation_api_prepare_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy observation" not in captured.out
    assert "inner noisy observation" in captured.err
