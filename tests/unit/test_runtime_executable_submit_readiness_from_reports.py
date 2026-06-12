import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/runtime_executable_submit_readiness_from_reports.py")


def _strategy_packet(**overrides):
    values = {
        "packet_id": "strategy-plan-1",
        "runtime_instance_id": "runtime-1",
        "source_authorization_id": "consumed-auth-1",
        "source_release_packet_id": "release-1",
        "status": "ready_for_final_gate_preflight",
        "signal_evaluation_id": "signal-eval-1",
        "order_candidate_id": "order-candidate-1",
    }
    values.update(overrides)
    return values


def _evidence(**overrides):
    values = {
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
    }
    values.update(overrides)
    return values


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_script_builds_ready_report(tmp_path):
    strategy_path = _write_json(tmp_path / "strategy.json", _strategy_packet())
    evidence_path = _write_json(tmp_path / "evidence.json", _evidence())
    output_path = tmp_path / "readiness.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--strategy-planning-packet",
            str(strategy_path),
            "--evidence",
            str(evidence_path),
            "--output",
            str(output_path),
            "--now-ms",
            "1765000000000",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["packet"]["status"] == "ready_for_executable_submit"
    assert report["packet"]["executable_submit_ready"] is True
    assert report["safety_invariants"]["exchange_called"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False
    assert report["safety_invariants"]["pg_write"] is False


def test_script_blocks_current_bnb_like_release_gate_state(tmp_path):
    strategy_path = _write_json(
        tmp_path / "strategy.json",
        _strategy_packet(
            status="blocked_by_release_gate",
            order_candidate_id=None,
        ),
    )
    evidence_path = _write_json(tmp_path / "evidence.json", _evidence())

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--strategy-planning-packet",
            str(strategy_path),
            "--evidence",
            str(evidence_path),
            "--now-ms",
            "1765000000000",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["packet"]["status"] == "blocked"
    assert "strategy_planning_not_ready_for_final_gate_preflight" in (
        report["packet"]["blockers"]
    )
    assert "order_candidate_id_missing" in report["packet"]["blockers"]


def test_script_surfaces_legacy_first_real_submit_packet_as_warning(tmp_path):
    strategy_path = _write_json(tmp_path / "strategy.json", _strategy_packet())
    evidence_path = _write_json(tmp_path / "evidence.json", _evidence())
    first_packet_path = _write_json(
        tmp_path / "first-real-submit.json",
        {
            "status": "blocked",
            "blockers": ["submit_rehearsal_not_ready"],
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--strategy-planning-packet",
            str(strategy_path),
            "--evidence",
            str(evidence_path),
            "--first-real-submit-packet",
            str(first_packet_path),
            "--now-ms",
            "1765000000000",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["packet"]["status"] == "ready_for_executable_submit"
    assert (
        "first_real_submit_packet_not_ready_but_runtime_grant_path_used"
        in report["packet"]["warnings"]
    )
