import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/runtime_official_submit_handoff_from_readiness.py")


def _readiness_payload(*, status="ready_for_executable_submit"):
    blockers = [] if status == "ready_for_executable_submit" else ["blocked"]
    return {
        "status": status,
        "api_payload": {
            "artifact_id": "readiness-1",
            "runtime_instance_id": "runtime-1",
            "source_strategy_planning_artifact_id": "strategy-plan-1",
            "source_authorization_id": "consumed-auth-1",
            "signal_evaluation_id": "signal-eval-1",
            "order_candidate_id": (
                "order-candidate-1"
                if status == "ready_for_executable_submit"
                else None
            ),
            "strategy_planning_status": (
                "ready_for_final_gate_preflight"
                if status == "ready_for_executable_submit"
                else "blocked_by_release_gate"
            ),
            "status": status,
            "evidence": {
                "final_gate_preview_id": "final-gate-preview-1",
                "final_gate_passed": True,
                "runtime_grant_authorization_id": "runtime-grant-1",
                "trusted_submit_fact_snapshot_id": "trusted-facts-1",
                "submit_idempotency_policy_id": "idem-1",
                "attempt_outcome_policy_id": "attempt-policy-1",
                "protection_creation_failure_policy_id": "protection-failure-1",
                "local_registration_enablement_decision_id": "local-enable-1",
                "exchange_submit_enablement_decision_id": "exchange-enable-1",
                "exchange_submit_action_authorization_id": "exchange-action-auth-1",
                "order_lifecycle_submit_enablement_id": "ol-submit-enable-1",
                "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-1",
                "deployment_readiness_evidence_id": "deploy-ready-1",
                "protection_required_and_ready": True,
                "active_position_source_trusted": True,
                "account_facts_fresh": True,
                "duplicate_submit_guard_ready": True,
            },
            "blockers": blockers,
            "warnings": [],
            "executable_submit_ready": status == "ready_for_executable_submit",
            "requires_official_order_lifecycle_path": True,
            "requires_current_final_gate_pass": True,
            "requires_fresh_strategy_candidate": True,
            "legacy_pre_attempt_rehearsal_required": False,
            "consumed_authorization_replay_only": True,
            "not_exchange_submit_execution": True,
            "not_order_lifecycle_authority": True,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
            "created_at_ms": 1765000000000,
            "metadata": {},
        },
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_script_builds_ready_handoff_report(tmp_path):
    readiness_path = _write_json(tmp_path / "readiness.json", _readiness_payload())
    output_path = tmp_path / "handoff.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--readiness-json",
            str(readiness_path),
            "--fresh-submit-authorization-id",
            "fresh-auth-1",
            "--output",
            str(output_path),
            "--now-ms",
            "1765000000001",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["handoff_artifact"]["status"] == "ready_for_official_submit_call"
    assert report["operator_action_preview"]["ready_for_call"] is True
    assert report["safety_invariants"]["calls_official_endpoint"] is False
    assert report["safety_invariants"]["exchange_called"] is False


def test_script_real_gateway_handoff_defaults_to_standing_authorization(tmp_path):
    readiness_path = _write_json(tmp_path / "readiness.json", _readiness_payload())

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--readiness-json",
            str(readiness_path),
            "--fresh-submit-authorization-id",
            "fresh-auth-1",
            "--mode",
            "real_gateway_action",
            "--now-ms",
            "1765000000001",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["handoff_artifact"]["status"] == "ready_for_official_submit_call"
    assert report["handoff_artifact"]["official_query"][
        "owner_confirmed_for_first_real_submit_action"
    ] is True
    assert "owner_real_submit_action_confirmation_missing" not in (
        report["handoff_artifact"]["blockers"]
    )


def test_script_blocks_consumed_authorization_reuse(tmp_path):
    readiness_path = _write_json(tmp_path / "readiness.json", _readiness_payload())

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--readiness-json",
            str(readiness_path),
            "--fresh-submit-authorization-id",
            "consumed-auth-1",
            "--now-ms",
            "1765000000001",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["handoff_artifact"]["status"] == "blocked"
    assert "fresh_submit_authorization_reuses_consumed_authorization" in (
        report["handoff_artifact"]["blockers"]
    )


def test_script_blocks_unready_readiness(tmp_path):
    readiness_path = _write_json(
        tmp_path / "readiness.json",
        _readiness_payload(status="blocked"),
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--readiness-json",
            str(readiness_path),
            "--fresh-submit-authorization-id",
            "fresh-auth-1",
            "--now-ms",
            "1765000000001",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["handoff_artifact"]["status"] == "blocked"
    assert "readiness_not_ready_for_executable_submit" in report[
        "handoff_artifact"
    ]["blockers"]
