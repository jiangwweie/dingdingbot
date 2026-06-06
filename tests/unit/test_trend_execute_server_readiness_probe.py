from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_probe_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe_trend_execute_server_readiness.py"
    spec = importlib.util.spec_from_file_location("probe_trend_execute_server_readiness", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _passed_payload(path: str) -> dict[str, Any]:
    if "execution-state" in path:
        return {"status": 200, "body": {"retry_allowed": True, "retry_blockers": []}}
    if "execute-readiness" in path:
        return {"status": 200, "body": {"ready": True, "blockers": []}}
    if "final-gate-dry-run" in path:
        return {
            "status": 200,
            "body": {
                "result": "passed",
                "final_gate": {
                    "final_preflight_result": "passed",
                    "hard_blockers": [],
                },
            },
        }
    return {"status": 200, "body": {"result": "passed"}}


def test_trend_server_probe_execute_mode_blocks_without_exact_owner_approval(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, cookie: str) -> dict[str, Any]:
        calls.append((method, path))
        return _passed_payload(path)

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.setenv("TREND_EXECUTE_MODE", "execute")
    monkeypatch.setenv("TREND_EXECUTE_AUTHORIZATION_ID", "auth-123")
    monkeypatch.delenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", raising=False)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["execute_allowed_by_probe"] is False
    assert payload["execute"]["status"] == "blocked_by_probe"
    assert "OWNER_APPROVED_TREND_BOUNDED_EXECUTION_missing_or_wrong" in payload["execute"]["body"]["blockers"]
    assert [method for method, _path in calls].count("POST") == 0


def test_trend_server_probe_execute_mode_posts_only_after_all_evidence_passes(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, cookie: str) -> dict[str, Any]:
        calls.append((method, path))
        if method == "POST":
            return {"status": 200, "body": {"operation_id": "op-1", "status": "submitted"}}
        return _passed_payload(path)

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.setenv("TREND_EXECUTE_MODE", "execute")
    monkeypatch.setenv("TREND_EXECUTE_AUTHORIZATION_ID", "auth-123")
    monkeypatch.setenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", probe.APPROVAL_VALUE)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["execute_allowed_by_probe"] is True
    assert payload["execute"]["status"] == 200
    assert calls[-1] == ("POST", "/api/brc/owner-trial-flow/authorizations/auth-123/execute")


def test_trend_server_probe_evidence_mode_never_posts_even_when_evidence_passes(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, cookie: str) -> dict[str, Any]:
        calls.append((method, path))
        return _passed_payload(path)

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.delenv("TREND_EXECUTE_MODE", raising=False)
    monkeypatch.setenv("TREND_EXECUTE_AUTHORIZATION_ID", "auth-123")
    monkeypatch.setenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", probe.APPROVAL_VALUE)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "evidence"
    assert payload["execute_allowed_by_probe"] is False
    assert "execute" not in payload
    assert [method for method, _path in calls].count("POST") == 0


def test_trend_server_probe_prepare_authorization_blocks_without_exact_owner_approval(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, cookie: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((method, path))
        return _passed_payload(path)

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.setenv("TREND_EXECUTE_MODE", "prepare_authorization")
    monkeypatch.delenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", raising=False)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["prepare_authorization"]["status"] == "blocked_by_probe"
    assert "OWNER_APPROVED_TREND_BOUNDED_EXECUTION_missing_or_wrong" in payload["prepare_authorization"]["body"]["blockers"]
    assert [method for method, _path in calls].count("POST") == 0


def test_trend_server_probe_prepare_authorization_creates_metadata_only_after_preflight(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_request(method: str, path: str, *, cookie: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((method, path, body))
        if "exchange-credential-preflight" in path:
            return {"status": 200, "body": {"result": "passed"}}
        if "current" in path:
            return {
                "status": 200,
                "body": {
                    "strategy_warnings": [
                        {"warning_id": "weak_evidence"},
                        {"warning_id": "tiny_live_risk"},
                    ]
                },
            }
        if path == "/api/brc/owner-trial-flow/risk-acknowledgement":
            assert body is not None
            assert body["carrier_id"] == "TF-001-live-readonly-v0"
            return {"status": 200, "body": {"acknowledgement_id": "ack-1"}}
        if path == "/api/brc/owner-trial-flow/authorization-draft":
            assert body is not None
            assert body["linked_acknowledgement_id"] == "ack-1"
            return {"status": 200, "body": {"draft_id": "draft-1"}}
        if path == "/api/brc/owner-trial-flow/authorization-draft/draft-1/activate-live-authorization":
            assert body is not None
            assert body["symbol"] == "SOL/USDT:USDT"
            return {"status": 200, "body": {"authorization_id": "auth-fresh"}}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.setenv("TREND_EXECUTE_MODE", "prepare_authorization")
    monkeypatch.setenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", probe.APPROVAL_VALUE)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["prepare_authorization"] == {
        "status": "prepared",
        "body": {"authorization_id": "auth-fresh"},
    }
    assert payload["safety"]["creates_authorization_metadata"] is True
    assert payload["safety"]["creates_execution_intent"] is False
    assert payload["safety"]["places_order"] is False
    assert [method for method, _path, _body in calls].count("POST") == 3
    assert all(
        not path.endswith("/execute")
        for _method, path, _body in calls
    )


def test_trend_server_probe_execute_mode_blocks_when_execution_state_not_retryable(
    monkeypatch,
    capsys,
):
    probe = _load_probe_module()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, *, cookie: str) -> dict[str, Any]:
        calls.append((method, path))
        if "execution-state" in path:
            return {
                "status": 200,
                "body": {
                    "retry_allowed": False,
                    "retry_blockers": ["previous_intent_has_order_id"],
                },
            }
        return _passed_payload(path)

    monkeypatch.setenv("TREND_EXECUTE_API_BASE", "https://server.example")
    monkeypatch.setenv("TREND_EXECUTE_SESSION_COOKIE", "dummy-session")
    monkeypatch.setenv("TREND_EXECUTE_MODE", "execute")
    monkeypatch.setenv("TREND_EXECUTE_AUTHORIZATION_ID", "auth-f43ecd5901c342deb4b2466c0548ebc4")
    monkeypatch.setenv("OWNER_APPROVED_TREND_BOUNDED_EXECUTION", probe.APPROVAL_VALUE)
    monkeypatch.setattr(probe, "_request_json", fake_request)

    assert probe.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["execute_allowed_by_probe"] is False
    assert payload["execute"]["status"] == "blocked_by_probe"
    assert "execution_state_retry_not_allowed" in payload["execute"]["body"]["blockers"]
    assert [method for method, _path in calls].count("POST") == 0


def test_trend_server_probe_redacts_secrets_without_hiding_authorization_ids():
    probe = _load_probe_module()

    payload = probe._redact(
        {
            "authorization_id": "auth-visible",
            "session_cookie": "secret-cookie",
            "nested": {"api_secret": "secret-value", "prints_secrets": False},
        }
    )

    assert payload["authorization_id"] == "auth-visible"
    assert payload["session_cookie"] == "<redacted>"
    assert payload["nested"]["api_secret"] == "<redacted>"
    assert payload["nested"]["prints_secrets"] is False
