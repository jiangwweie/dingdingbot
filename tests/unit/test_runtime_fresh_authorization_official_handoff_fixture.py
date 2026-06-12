from __future__ import annotations

import json
import sys

from scripts import runtime_fresh_authorization_official_handoff_fixture as script


def test_fresh_authorization_official_handoff_fixture_reaches_disabled_smoke(tmp_path):
    report = script._build_report(_args(tmp_path))

    assert report["status"] == "ready_fresh_authorization_official_handoff_fixture"
    assert report["stage_statuses"] == {
        "initial_handoff": "blocked",
        "binding": "created_intent_and_authorization",
        "final_handoff": "ready_for_official_submit_call",
        "disabled_smoke": "disabled_smoke_passed",
    }
    assert report["fresh_submit_authorization_id"] == "fresh-submit-auth-rtf059"
    assert report["api_call_counts"] == {"binding": 1, "disabled_smoke": 1}
    assert any("fresh-authorizations/bind" in path for path in report["api_paths"]["binding"])
    assert any(
        "runtime-execution-first-real-submit-actions/authorizations/"
        "fresh-submit-auth-rtf059" in path
        for path in report["api_paths"]["disabled_smoke"]
    )
    assert report["safety_invariants"]["official_submit_endpoint_called_only_disabled_smoke"] is True
    assert report["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert report["safety_invariants"]["order_created"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False


def test_final_handoff_uses_fresh_authorization_not_consumed_authorization(tmp_path):
    report = script._build_report(_args(tmp_path))

    final_packet = report["final_handoff"]["packet"]
    assert final_packet["fresh_submit_authorization_id"] == "fresh-submit-auth-rtf059"
    assert final_packet["source_consumed_authorization_id"] == (
        "consumed-submit-auth-rtf059"
    )
    assert final_packet["fresh_submit_authorization_id"] != (
        final_packet["source_consumed_authorization_id"]
    )
    assert final_packet["official_query"][
        "owner_confirmed_for_first_real_submit_action"
    ] is False


def test_fixture_writes_stage_artifacts_and_output(tmp_path):
    output = tmp_path / "fixture-report.json"

    report = script._build_report(_args(tmp_path, output=str(output)))

    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["status"] == "ready_fresh_authorization_official_handoff_fixture"
    for path in report["artifact_paths"].values():
        assert path
    assert (tmp_path / "artifacts" / "00-readiness-ready.json").exists()
    assert (tmp_path / "artifacts" / "02-fresh-authorization-binding.json").exists()
    assert (tmp_path / "artifacts" / "04-disabled-smoke.json").exists()


def test_fixture_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_report(args):
        print("inner noisy rtf059")
        return {
            "status": "ready_fresh_authorization_official_handoff_fixture",
            "ok": True,
        }

    monkeypatch.setattr(script, "_build_report", fake_build_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_fresh_authorization_official_handoff_fixture.py",
            "--artifact-dir",
            "output/rtf059-fixture",
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy rtf059" not in captured.out
    assert "inner noisy rtf059" in captured.err


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf059",
        "runtime_grant_authorization_id": "grant-rtf059",
        "fixture_fresh_authorization_id": "fresh-submit-auth-rtf059",
        "requested_fresh_submit_authorization_id": None,
        "api_base": "http://fixture",
        "artifact_dir": str(tmp_path / "artifacts"),
        "output": None,
    }
    values.update(overrides)
    return type("Args", (), values)()
