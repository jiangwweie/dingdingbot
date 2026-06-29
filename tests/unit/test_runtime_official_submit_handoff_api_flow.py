from __future__ import annotations

import json
import sys

from scripts import runtime_official_submit_handoff_api_flow
from tests.unit.test_runtime_official_submit_handoff_from_readiness import (
    _readiness_payload,
)


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or {
            "status": "ready_for_official_submit_call",
            "blockers": [],
            "warnings": ["unit"],
            "ready_for_official_submit_call": True,
            "official_endpoint_method": "POST",
            "official_endpoint_path": (
                "/api/trading-console/runtime-execution-first-real-submit-actions/"
                "authorizations/fresh-auth-1"
            ),
            "official_query": {
                "owner_confirmed_for_first_real_submit_action": False,
            },
            "mode": "disabled_smoke",
        }
        self.calls: list[dict] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {"http_status": self.http_status, "body": self.body}


def _write_inputs(tmp_path):
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(json.dumps(_readiness_payload()), encoding="utf-8")
    return readiness_path


def _args(tmp_path, **overrides):
    readiness_path = _write_inputs(tmp_path)
    values = {
        "runtime_instance_id": "runtime-1",
        "readiness_json": str(readiness_path),
        "fresh_submit_authorization_id": "fresh-auth-1",
        "mode": "disabled_smoke",
        "owner_confirmed_for_real_submit_action": False,
        "additional_warning": None,
        "additional_blocker": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_official_submit_handoff_api_flow_posts_handoff_request(tmp_path):
    client = _Client()

    artifact = runtime_official_submit_handoff_api_flow._build_artifact(
        _args(tmp_path),
        client=client,
    )

    assert artifact["status"] == "ready_for_official_submit_call"
    assert artifact["operator_action_preview"]["ready_for_call"] is True
    assert artifact["safety_invariants"]["calls_official_submit_endpoint"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-1/"
        "official-submit-handoff-previews"
    )
    assert call["body"]["readiness_artifact"]["artifact_id"] == "readiness-1"
    assert call["body"]["fresh_submit_authorization_id"] == "fresh-auth-1"
    assert call["body"]["metadata"]["runtime_official_submit_handoff_api_flow"] is True
    assert call["body"]["non_executing"] is True


def test_official_submit_handoff_api_flow_keeps_http_errors(tmp_path):
    artifact = runtime_official_submit_handoff_api_flow._build_artifact(
        _args(tmp_path),
        client=_Client(http_status=400, body={"detail": "bad"}),
    )

    assert artifact["status"] == "blocked"
    assert artifact["blocked_stage"] == "official_submit_handoff_api"
    assert "official_submit_handoff_api_http_400" in artifact["blockers"]
    assert artifact["safety_invariants"]["execution_intent_created"] is False


def test_official_submit_handoff_api_flow_cli_stdout_is_json_only(
    monkeypatch,
    capsys,
):
    def fake_build_artifact(args):
        print("inner noisy handoff api flow")
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(
        runtime_official_submit_handoff_api_flow,
        "_build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_official_submit_handoff_api_flow.py",
            "--runtime-instance-id",
            "runtime-1",
            "--readiness-json",
            "readiness.json",
            "--fresh-submit-authorization-id",
            "fresh-auth-1",
        ],
    )

    assert runtime_official_submit_handoff_api_flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy handoff api flow" not in captured.out
    assert "inner noisy handoff api flow" in captured.err
