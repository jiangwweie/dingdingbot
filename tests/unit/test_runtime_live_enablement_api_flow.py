from __future__ import annotations

from scripts.runtime_live_enablement_api_flow import (
    APPLY_CONFIRMATION_PHRASE,
    build_runtime_live_enablement_api_packet,
)


class _FakeClient:
    def __init__(self, *, preview_status: str, preview_blockers: list[str] | None = None):
        self.preview_status = preview_status
        self.preview_blockers = list(preview_blockers or [])
        self.calls: list[dict[str, object]] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        if path.endswith("/live-enablement-preview"):
            return {
                "http_status": 200,
                "body": {
                    "status": self.preview_status,
                    "blockers": self.preview_blockers,
                    "warnings": [],
                    "not_execution_authority": True,
                    "runtime_state_mutated": False,
                    "execution_intent_created": False,
                    "order_created": False,
                    "exchange_called": False,
                    "owner_bounded_execution_called": False,
                    "order_lifecycle_called": False,
                },
            }
        if path.endswith("/live-enablement-mutations"):
            return {
                "http_status": 200,
                "body": {
                    "status": "applied",
                    "runtime_state_mutated": True,
                    "not_order_authority": True,
                    "execution_intent_created": False,
                    "order_created": False,
                    "exchange_called": False,
                    "owner_bounded_execution_called": False,
                    "order_lifecycle_called": False,
                },
            }
        return {
            "http_status": 200,
            "body": {
                "runtime_instance_id": "runtime-1",
                "execution_enabled": False,
                "shadow_mode": True,
                "execution_mode": "shadow_disabled",
            },
        }


def test_live_enablement_api_flow_inspects_ready_preview_without_mutation():
    client = _FakeClient(
        preview_status="ready_for_live_runtime_enablement_mutation_design",
    )

    packet = build_runtime_live_enablement_api_packet(
        client=client,
        runtime_instance_id="runtime-1",
        query={"current_head_deployed": True},
    )

    assert packet["status"] == "ready_for_live_runtime_enablement_mutation_review"
    assert packet["checks"]["preview_ready"] is True
    assert packet["checks"]["mutation_applied"] is False
    assert packet["safety_invariants"]["runtime_state_mutated"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert [call["method"] for call in client.calls] == ["GET", "GET"]


def test_live_enablement_api_flow_blocks_apply_without_confirmation_phrase():
    client = _FakeClient(
        preview_status="ready_for_live_runtime_enablement_mutation_design",
    )

    packet = build_runtime_live_enablement_api_packet(
        client=client,
        runtime_instance_id="runtime-1",
        query={},
        apply_mutation=True,
        confirmation_phrase="wrong",
        owner_live_runtime_enablement_authorization_id="owner-live-1",
        owner_real_submit_authorization_id="owner-submit-1",
    )

    assert packet["status"] == "blocked_before_live_runtime_enablement_mutation"
    assert "apply_confirmation_phrase_missing_or_invalid" in (
        packet["checks"]["blockers"]
    )
    assert packet["checks"]["mutation_applied"] is False
    assert [call["method"] for call in client.calls] == ["GET", "GET"]


def test_live_enablement_api_flow_applies_mutation_only_after_ready_confirmation():
    client = _FakeClient(
        preview_status="ready_for_live_runtime_enablement_mutation_design",
    )

    packet = build_runtime_live_enablement_api_packet(
        client=client,
        runtime_instance_id="runtime-1",
        query={},
        apply_mutation=True,
        confirmation_phrase=APPLY_CONFIRMATION_PHRASE,
        owner_live_runtime_enablement_authorization_id="owner-live-1",
        owner_real_submit_authorization_id="owner-submit-1",
    )

    assert packet["status"] == "live_runtime_enablement_mutation_applied"
    assert packet["checks"]["mutation_applied"] is True
    assert packet["safety_invariants"]["runtime_state_mutated"] is True
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["exchange_called"] is False
    assert [call["method"] for call in client.calls] == ["GET", "GET", "POST"]
    mutation_body = client.calls[-1]["body"]
    assert mutation_body["owner_live_runtime_enablement_authorization_id"] == (
        "owner-live-1"
    )
    assert mutation_body["owner_real_submit_authorization_id"] == "owner-submit-1"


def test_live_enablement_api_flow_keeps_blocked_preview_non_mutating():
    client = _FakeClient(
        preview_status="blocked",
        preview_blockers=["current_head_not_deployed_to_tokyo"],
    )

    packet = build_runtime_live_enablement_api_packet(
        client=client,
        runtime_instance_id="runtime-1",
        query={},
        apply_mutation=True,
        confirmation_phrase=APPLY_CONFIRMATION_PHRASE,
        owner_live_runtime_enablement_authorization_id="owner-live-1",
        owner_real_submit_authorization_id="owner-submit-1",
    )

    assert packet["status"] == "blocked_before_live_runtime_enablement_mutation"
    assert "preview_current_head_not_deployed_to_tokyo" in (
        packet["checks"]["blockers"]
    )
    assert "preview_not_ready_for_apply" in packet["checks"]["blockers"]
    assert [call["method"] for call in client.calls] == ["GET", "GET"]
