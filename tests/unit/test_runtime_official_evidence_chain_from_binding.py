from __future__ import annotations

import json

import pytest

from scripts import runtime_official_evidence_chain_from_binding as script


def test_official_evidence_chain_from_binding_prepares_machine_evidence(tmp_path):
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(
        json.dumps(
            {
                "operator_action_preview": {
                    "fresh_submit_authorization_id": "auth-rtf016",
                }
            }
        ),
        encoding="utf-8",
    )
    client = _Client()

    report = script._build_report(
        _args(tmp_path, binding_path=binding_path),
        client=client,
    )

    assert (
        report["status"]
        == "prepared_machine_evidence_blocked_before_local_order_adapter"
    )
    assert report["fresh_submit_authorization_id"] == "auth-rtf016"
    assert report["ids"]["trusted_submit_fact_snapshot_id"] == "facts-rtf016"
    assert report["ids"]["submit_idempotency_policy_id"] == "idem-rtf016"
    assert (
        report["ids"]["protection_creation_failure_policy_id"]
        == "protection-failure-rtf016"
    )
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert report["safety_invariants"]["order_created_by_wrapper"] is False
    assert [call["path"] for call in client.calls] == [
        (
            "/api/trading-console/runtime-execution-first-real-submit-actions/"
            "authorizations/auth-rtf016"
        ),
        (
            "/api/trading-console/runtime-execution-first-real-submit-"
            "evidence-preparations/authorizations/auth-rtf016"
        ),
    ]


def test_official_evidence_chain_from_binding_requires_fresh_authorization(tmp_path):
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")

    with pytest.raises(ValueError, match="fresh_submit_authorization_id_missing"):
        script._build_report(_args(tmp_path, binding_path=binding_path), client=_Client())


def test_official_evidence_chain_ignores_legacy_packet_wrapper_authorization(
    tmp_path,
):
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(
        json.dumps(
            {
                "packet": {
                    "fresh_submit_authorization_id": "auth-legacy-packet",
                }
            }
        ),
        encoding="utf-8",
    )
    client = _Client()

    with pytest.raises(
        ValueError,
        match="fresh_submit_authorization_id_missing_from_binding_report",
    ):
        script._build_report(_args(tmp_path, binding_path=binding_path), client=client)

    assert client.calls == []


class _Client:
    def __init__(self) -> None:
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
        if "runtime-execution-first-real-submit-actions" in path:
            return {
                "http_status": 404,
                "body": {
                    "message": "RuntimeExecutionOrderLifecycleAdapterResult not found",
                },
                "error": True,
            }
        if "runtime-execution-first-real-submit-evidence-preparations" in path:
            return {
                "http_status": 200,
                "body": {
                    "status": "blocked_before_evidence",
                    "available_evidence_ids": {
                        "trusted_submit_fact_snapshot_id": "facts-rtf016",
                        "submit_idempotency_policy_id": "idem-rtf016",
                        "protection_creation_failure_policy_id": (
                            "protection-failure-rtf016"
                        ),
                        "post_submit_budget_settlement_persistence_evidence_id": (
                            "settlement-persistence-rtf016"
                        ),
                    },
                    "blockers": [
                        "first_real_submit_evidence_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    ],
                },
            }
        raise AssertionError(f"unexpected path {path}")


def _args(tmp_path, *, binding_path, **overrides):
    values = {
        "binding_json": str(binding_path),
        "output": None,
        "env_file": None,
        "api_base": "http://unit",
        "skip_evidence_preparation_probe": False,
    }
    values.update(overrides)
    return type("Args", (), values)()
