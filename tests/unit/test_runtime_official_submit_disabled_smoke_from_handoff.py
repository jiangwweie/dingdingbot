from __future__ import annotations

import json
import sys

from scripts import runtime_official_submit_disabled_smoke_from_handoff as flow
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffPacket,
)
from tests.unit.test_runtime_official_submit_handoff import _readiness
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    build_runtime_official_submit_handoff_packet,
)


class _Client:
    def __init__(self, *, http_status: int = 200, body: dict | None = None) -> None:
        self.http_status = http_status
        self.body = body or {
            "status": "exchange_submit_execution_disabled",
            "exchange_submit_execution_enabled": False,
            "exchange_submit_execution_mode": "disabled",
            "execution_result_id": "disabled-result-1",
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


def _handoff_payload(**overrides) -> dict:
    handoff = build_runtime_official_submit_handoff_packet(
        readiness_packet=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        now_ms=1_765_000_000_001,
        **overrides,
    )
    return handoff.model_dump(mode="json")


def _args(tmp_path, payload: dict, **overrides):
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps({"packet": payload}), encoding="utf-8")
    values = {
        "handoff_json": str(path),
        "output": None,
        "env_file": None,
        "api_base": "http://unit",
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_disabled_smoke_from_handoff_calls_official_endpoint(tmp_path):
    client = _Client()

    report = flow._build_report(
        _args(tmp_path, _handoff_payload()),
        client=client,
    )

    assert report["status"] == "disabled_smoke_passed"
    assert report["http_status"] == 200
    assert report["safety_invariants"]["calls_official_submit_endpoint"] is True
    assert report["safety_invariants"]["requests_real_gateway_action"] is False
    assert report["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"].endswith(
        "/runtime-execution-first-real-submit-actions/authorizations/fresh-auth-1"
    )
    assert call["query"]["owner_confirmed_for_first_real_submit_action"] is False
    assert call["query"]["trusted_submit_fact_snapshot_id"] == "trusted-facts-1"
    assert call["body"] is None


def test_disabled_smoke_from_handoff_blocks_unready_handoff_without_call(tmp_path):
    payload = _handoff_payload()
    payload["status"] = "blocked"
    payload["ready_for_official_submit_call"] = False
    payload["blockers"] = ["handoff-blocked"]
    client = _Client()

    report = flow._build_report(_args(tmp_path, payload), client=client)

    assert report["status"] == "blocked"
    assert report["blocked_stage"] == "handoff_precondition"
    assert "handoff_not_ready_for_official_submit_call" in report["blockers"]
    assert "handoff:handoff-blocked" in report["blockers"]
    assert client.calls == []


def test_disabled_smoke_from_handoff_refuses_real_gateway_handoff(tmp_path):
    payload = _handoff_payload(
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=True,
    )
    handoff = RuntimeOfficialSubmitHandoffPacket.model_validate(payload)
    assert handoff.ready_for_official_submit_call is True
    client = _Client()

    report = flow._build_report(_args(tmp_path, payload), client=client)

    assert report["status"] == "blocked"
    assert "disabled_smoke_refuses_real_gateway_handoff" in report["blockers"]
    assert client.calls == []


def test_disabled_smoke_from_handoff_blocks_unexpected_official_status(tmp_path):
    client = _Client(body={"status": "ready_for_real_gateway_action"})

    report = flow._build_report(
        _args(tmp_path, _handoff_payload()),
        client=client,
    )

    assert report["status"] == "blocked"
    assert report["blocked_stage"] == "official_first_real_submit_action"
    assert (
        "disabled_official_submit_unexpected_status:ready_for_real_gateway_action"
        in report["blockers"]
    )
    assert len(client.calls) == 1


def test_disabled_smoke_from_handoff_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build_report(args):
        print("inner noisy disabled smoke")
        return {"status": "blocked", "ok": True}

    monkeypatch.setattr(flow, "_build_report", fake_build_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_official_submit_disabled_smoke_from_handoff.py",
            "--handoff-json",
            "handoff.json",
        ],
    )

    assert flow.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "inner noisy disabled smoke" not in captured.out
    assert "inner noisy disabled smoke" in captured.err
