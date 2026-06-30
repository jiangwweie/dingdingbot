from __future__ import annotations

import json
import sys

from scripts import runtime_live_signal_shadow_planning_projection as script


def test_projection_waits_without_calling_planning(tmp_path):
    calls = []
    operator_path = _write_json(
        tmp_path / "operator.json",
        _operator_evidence(
            "waiting_for_runtime_compatible_signal",
            blockers=["runtime_strategy_signal_not_found_in_strategy_shelf"],
        ),
    )
    post_submit_path = _write_json(tmp_path / "post-submit.json", {"status": "ready"})

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=lambda args: calls.append(args),
    )

    assert projection["status"] == "waiting_for_signal"
    assert "operator_command_plan" not in projection
    assert projection["shadow_planning_plan"]["not_execution_authority"] is True
    assert projection["shadow_planning_plan"]["next_step"] == (
        "continue_live_signal_operator_supervision"
    )
    assert projection["shadow_planning_plan"]["creates_shadow_candidate"] is False
    assert projection["strategy_planning_flow"] is None
    assert calls == []
    assert projection["safety_invariants"]["uses_official_strategy_planning_api"] is False
    assert projection["safety_invariants"]["order_created"] is False


def test_projection_stops_for_profile_review_without_planning(tmp_path):
    calls = []
    operator_path = _write_json(
        tmp_path / "operator.json",
        _operator_evidence("ready_for_owner_runtime_profile_decision"),
    )
    post_submit_path = _write_json(tmp_path / "post-submit.json", {"status": "ready"})

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=lambda args: calls.append(args),
    )

    assert projection["status"] == "profile_review_required"
    assert projection["shadow_planning_plan"]["next_step"] == (
        "review_runtime_profile_proposal_before_shadow_planning"
    )
    assert projection["shadow_planning_plan"]["creates_shadow_candidate"] is False
    assert calls == []


def test_projection_calls_strategy_planning_for_ready_operator_signal(tmp_path):
    calls = []
    signal_path = _write_json(tmp_path / "signal.json", {"evaluation_id": "eval-ready"})
    operator_path = _write_json(
        tmp_path / "operator.json",
        _operator_evidence("ready_for_prepare", signal_input_json=str(signal_path)),
    )
    post_submit_path = _write_json(
        tmp_path / "post-submit.json",
        {"packet_id": "post-submit-1", "status": "finalized_ready_for_next_attempt"},
    )

    def planning_builder(args):
        calls.append(args)
        return _planning_artifact()

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=planning_builder,
    )

    assert projection["status"] == "ready_for_final_gate_preflight"
    assert projection["signal_input_json"] == str(signal_path)
    assert projection["signal_evaluation_id"] == "eval-ready"
    assert projection["order_candidate_id"] == "order-candidate-ready"
    assert projection["shadow_planning_plan"]["creates_shadow_candidate"] is True
    assert projection["shadow_planning_plan"]["creates_execution_intent"] is False
    assert projection["shadow_planning_plan"]["creates_submit_authorization"] is False
    assert projection["shadow_planning_plan"]["places_order"] is False
    assert projection["shadow_planning_plan"]["calls_order_lifecycle"] is False
    assert projection["safety_invariants"]["uses_official_strategy_planning_api"] is True
    assert projection["safety_invariants"]["exchange_write_called"] is False
    assert projection["safety_invariants"]["order_lifecycle_called"] is False
    assert len(calls) == 1
    assert calls[0].signal_input_json == str(signal_path)
    assert calls[0].post_submit_finalize_payload_json == str(post_submit_path)
    metadata = json.loads(calls[0].metadata_json)
    assert metadata["runtime_live_signal_shadow_planning_projection"] is True
    assert metadata["source_operator_evidence_json"] == str(operator_path)
    assert "source_operator_packet_json" not in metadata


def test_projection_extracts_ready_signal_from_supervisor_latest_cycle(tmp_path):
    signal_path = _write_json(tmp_path / "signal.json", {"evaluation_id": "eval-supervisor"})
    operator_path = _write_json(
        tmp_path / "supervisor.json",
        {
            "scope": "runtime_live_signal_operator_supervisor",
            "status": "supervisor_prepare_review_required",
            "runtime_instance_id": "runtime-1",
            "cycle_summaries": [
                {
                    "cycle_index": 1,
                    "status": "ready_for_prepare",
                    "signal_input_json": str(signal_path),
                    "forbidden_effects": [],
                }
            ],
            "blockers": [],
            "warnings": [],
            "safety_invariants": {"cycles_have_forbidden_effects": False},
        },
    )
    post_submit_path = _write_json(tmp_path / "post-submit.json", {"status": "ready"})

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=lambda args: _planning_artifact(),
    )

    assert projection["status"] == "ready_for_final_gate_preflight"
    assert projection["source_operator_evidence_status"] == (
        "supervisor_prepare_review_required"
    )
    assert projection["source_operator_evidence_scope"] == (
        "runtime_live_signal_operator_supervisor"
    )
    assert "packet_status" not in projection
    assert "source_operator_packet_status" not in projection
    assert "source_operator_packet_scope" not in projection
    assert projection["signal_input_json"] == str(signal_path)


def test_projection_blocks_for_missing_signal_input_on_ready_operator_signal(tmp_path):
    calls = []
    operator_path = _write_json(
        tmp_path / "operator.json",
        _operator_evidence("ready_for_prepare", signal_input_json=None),
    )
    post_submit_path = _write_json(tmp_path / "post-submit.json", {"status": "ready"})

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=lambda args: calls.append(args),
    )

    assert projection["status"] == "blocked"
    assert projection["blocked_stage"] == "signal_input_json"
    assert "ready_operator_signal_input_json_missing" in projection["blockers"]
    assert calls == []


def test_projection_blocks_for_forbidden_operator_effect(tmp_path):
    calls = []
    operator_path = _write_json(
        tmp_path / "operator.json",
        _operator_evidence(
            "ready_for_prepare",
            signal_input_json=str(tmp_path / "signal.json"),
            safety={"order_created": True},
        ),
    )
    post_submit_path = _write_json(tmp_path / "post-submit.json", {"status": "ready"})

    projection = script._build_projection(
        _args(tmp_path, operator_path=operator_path, post_submit_path=post_submit_path),
        planning_builder=lambda args: calls.append(args),
    )

    assert projection["status"] == "blocked"
    assert projection["blocked_stage"] == "operator_evidence"
    assert "order_created" in projection["blockers"]
    assert projection["safety_invariants"]["source_forbidden_effects"] == ["order_created"]
    assert calls == []


def test_projection_cli_stdout_is_json_only(monkeypatch, capsys, tmp_path):
    def fake_build_projection(args):
        print("inner noisy projection")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(script, "_build_projection", fake_build_projection)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_live_signal_shadow_planning_projection.py",
            "--runtime-instance-id",
            "runtime-1",
            "--operator-evidence-json",
            "operator.json",
            "--post-submit-finalize-artifact-json",
            "post.json",
        ],
    )

    assert script.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_signal"
    assert "inner noisy projection" not in captured.out
    assert "inner noisy projection" in captured.err


def _args(tmp_path, *, operator_path, post_submit_path):
    return type(
        "Args",
        (),
        {
            "runtime_instance_id": "runtime-1",
            "operator_evidence_json": str(operator_path),
            "post_submit_finalize_artifact_json": str(post_submit_path),
            "env_file": None,
            "api_base": "http://unit",
            "context_id": "context-1",
            "expires_at_ms": None,
            "metadata_json": '{"owner":"unit"}',
            "output_dir": str(tmp_path / "projection-output"),
            "flow_id": "projection-1",
            "output_json": None,
        },
    )()


def _operator_evidence(
    status,
    *,
    signal_input_json=None,
    blockers=None,
    safety=None,
):
    source_safety = {
        "runtime_created": False,
        "runtime_profile_mutated": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }
    source_safety.update(safety or {})
    return {
        "scope": "runtime_live_signal_operator_cycle",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "signal_input_json": signal_input_json,
        "blockers": blockers or [],
        "warnings": [],
        "safety_invariants": source_safety,
    }


def _planning_artifact():
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": "ready_for_final_gate_preflight",
        "api_payload": {
            "status": "ready_for_final_gate_preflight",
            "signal_evaluation_id": "eval-ready",
            "order_candidate_id": "order-candidate-ready",
            "strategy_planning_plan": {"creates_shadow_candidate": True},
        },
        "blockers": [],
        "warnings": [],
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
