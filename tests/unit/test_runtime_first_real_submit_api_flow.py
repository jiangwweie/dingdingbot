from __future__ import annotations

import os

from scripts.runtime_first_real_submit_api_flow import (
    APPROVAL_ENV,
    FirstRealSubmitApiFlow,
    FlowConfig,
    _approval_value,
)


class _FakeClient:
    def __init__(
        self,
        *,
        existing_attempt_policy: bool = False,
        next_attempt_gate_status: str = "clear_for_preflight",
        next_attempt_gate_name: str = "clear_for_next_preflight",
        candidate_reusable: bool | None = True,
        candidate_usage_status: str = "unused",
        evidence_blockers: list[str] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.existing_attempt_policy = existing_attempt_policy
        self.next_attempt_gate_status = next_attempt_gate_status
        self.next_attempt_gate_name = next_attempt_gate_name
        self.candidate_reusable = candidate_reusable
        self.candidate_usage_status = candidate_usage_status
        self.evidence_blockers = evidence_blockers or []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        if "owner-action-flow" in path:
            blocked = self.next_attempt_gate_status != "clear_for_preflight"
            return {
                "http_status": 200,
                "body": {
                    "data": {
                        "post_action_state": {
                            "next_attempt_gate": {
                                "gate": self.next_attempt_gate_name,
                                "status": self.next_attempt_gate_status,
                                "next_attempt_allowed_by_lifecycle": not blocked,
                                "blockers": (
                                    [
                                        {
                                            "id": "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED",
                                        }
                                    ]
                                    if blocked
                                    else []
                                ),
                            }
                        }
                    }
                },
            }
        if "/api/trading-console/order-candidates/" in path:
            return {
                "http_status": 200,
                "body": {
                    "order_candidate_id": path.rsplit("/", 1)[-1],
                    "candidate_reusable_for_new_attempt": self.candidate_reusable,
                    "candidate_usage_status": self.candidate_usage_status,
                    "reuse_blocker": (
                        None
                        if self.candidate_reusable
                        else "order_candidate_already_has_submit_authorization"
                    ),
                },
            }
        if "runtime-execution-intent-drafts" in path:
            return {"http_status": 200, "body": {"draft_id": "draft-1", "status": "ready_for_intent_creation"}}
        if "runtime-execution-intents/drafts" in path:
            return {"http_status": 200, "body": {"id": "intent-1", "status": "recorded"}}
        if "runtime-execution-controlled-submit-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "execution_intent_id": "intent-1",
                    "runtime_execution_intent_draft_id": "draft-1",
                    "source_id": "candidate-1",
                    "semantic_ids": {
                        "order_candidate_id": "candidate-1",
                        "runtime_instance_id": "runtime-1",
                        "signal_evaluation_id": "signal-1",
                    },
                    "status": "ready_for_controlled_submit_adapter",
                },
            }
        if "runtime-execution-protection-plans" in path:
            return {
                "http_status": 200,
                "body": {
                    "protection_plan_id": "protection-plan-1",
                    "status": "ready_for_submit_adapter",
                    "order_created": False,
                    "exchange_called": False,
                },
            }
        if "runtime-execution-submit-authorizations" in path:
            return {"http_status": 200, "body": {"authorization_id": "auth-1", "status": "approved_pending_controlled_submit"}}
        if "runtime-execution-first-real-submit-evidence-preparations" in path:
            available = {
                "trusted_submit_fact_snapshot_id": "facts-1",
                "submit_idempotency_policy_id": "idem-1",
                "protection_creation_failure_policy_id": "protect-fail-1",
            }
            if self.existing_attempt_policy:
                available["attempt_outcome_policy_id"] = (
                    "runtime-attempt-outcome-policy-"
                    "runtime-attempt-reservation-auth-1-"
                    "entry_filled_protection_creation_failed"
                )
            return {
                "http_status": 200,
                "body": {
                    "status": "prepared_packet_blocked",
                    "available_evidence_ids": available,
                    "blockers": [
                        "first_real_submit_packet_unavailable:"
                        "runtimeexecutionorderlifecycleadapterresult_not_found"
                    ]
                    + self.evidence_blockers,
                },
            }
        if "runtime-execution-attempt-reservations" in path:
            return {"http_status": 200, "body": {"reservation_id": "reserve-1", "status": "pending_runtime_mutation"}}
        if "runtime-execution-attempt-mutations" in path:
            return {"http_status": 200, "body": {"mutation_id": "mutation-1", "status": "applied"}}
        if "runtime-execution-attempt-outcome-policies" in path:
            return {"http_status": 200, "body": {"policy_id": "policy-1", "status": "ready_for_attempt_budget_outcome_accounting"}}
        if "runtime-execution-order-lifecycle-handoff-drafts" in path:
            return {"http_status": 200, "body": {"handoff_draft_id": "handoff-1", "status": "ready_for_order_lifecycle_adapter"}}
        if "runtime-execution-local-registration-action-authorizations" in path:
            return {"http_status": 200, "body": {"action_authorization_id": "local-action-1", "status": "approved_for_local_registration_action"}}
        if "runtime-execution-local-registration-enablements" in path:
            return {"http_status": 200, "body": {"decision_id": "local-enable-1", "status": "ready_for_local_registration_action"}}
        if "runtime-execution-order-lifecycle-adapter-results" in path:
            return {"http_status": 200, "body": {"adapter_result_id": "local-result-1", "status": "registered_created_local_orders"}}
        if "runtime-execution-exchange-gateway-readiness" in path:
            return {"http_status": 200, "body": {"readiness_id": "gateway-ready-1", "status": "ready_for_manual_gateway_binding"}}
        if "runtime-execution-exchange-submit-action-authorizations" in path:
            return {"http_status": 200, "body": {"action_authorization_id": "exchange-action-1", "status": "approved_for_exchange_submit_action"}}
        if "runtime-execution-exchange-submit-enablements" in path:
            return {"http_status": 200, "body": {"decision_id": "exchange-enable-1", "status": "ready_for_exchange_submit_action"}}
        if "runtime-execution-exchange-submit-adapter-results" in path:
            return {"http_status": 200, "body": {"adapter_result_id": "exchange-adapter-1", "status": "exchange_submit_adapter_armed"}}
        if "runtime-execution-first-real-submit-enablement-packets" in path:
            return {"http_status": 200, "body": {"status": "ready_for_owner_final_review"}}
        if "runtime-execution-first-real-submit-actions" in path:
            return {"http_status": 200, "body": {"execution_result_id": "exec-1", "status": "exchange_submit_orders_submitted"}}
        if "runtime-execution-submit-outcome-reviews" in path:
            return {"http_status": 200, "body": {"review_id": "review-1", "status": "ready_for_attempt_outcome_policy"}}
        if "runtime-execution-first-real-submit-outcome-accounting" in path:
            return {"http_status": 200, "body": {"accounting_id": "accounting-1", "status": "recorded"}}
        if "runtime-execution-post-submit-budget-settlements" in path:
            return {"http_status": 200, "body": {"settlement_id": "settlement-1", "status": "settled"}}
        return {"http_status": 200, "body": {"status": "ok"}}


def test_prepare_from_order_candidate_stops_before_local_registration():
    client = _FakeClient()
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="prepare",
            order_candidate_id="candidate-1",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ids"]["authorization_id"] == "auth-1"
    paths = [call["path"] for call in client.calls]
    assert any("runtime-execution-protection-plans" in path for path in paths)
    protection_index = next(
        index
        for index, path in enumerate(paths)
        if "runtime-execution-protection-plans" in path
    )
    authorization_index = next(
        index
        for index, path in enumerate(paths)
        if "runtime-execution-submit-authorizations" in path
    )
    assert protection_index < authorization_index
    assert not any("attempt-mutations" in path for path in paths)
    assert not any("attempt-outcome-policies" in path for path in paths)
    assert not any("first-real-submit-actions" in path for path in paths)
    assert not any("exchange-submit-action-authorizations" in path for path in paths)


def test_prepare_checks_next_attempt_gate_when_symbol_is_provided():
    client = _FakeClient()
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="prepare",
            order_candidate_id="candidate-1",
            next_attempt_symbol="AVAX/USDT:USDT",
            next_attempt_side="short",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["next_attempt_gate"]["status"] == "clear_for_preflight"
    assert report["ids"]["authorization_id"] == "auth-1"
    owner_flow_call = client.calls[0]
    assert owner_flow_call["path"] == "/api/trading-console/owner-action-flow"
    assert owner_flow_call["query"]["symbol"] == "AVAX/USDT:USDT"
    assert owner_flow_call["query"]["side"] == "short"


def test_prepare_blocks_before_draft_when_next_attempt_gate_is_not_clear():
    client = _FakeClient(
        next_attempt_gate_status="blocked",
        next_attempt_gate_name="closed_trade_review_required",
    )
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="prepare",
            order_candidate_id="candidate-1",
            next_attempt_symbol="AVAX/USDT:USDT",
        ),
    )

    report = flow.run()

    assert "next_attempt_gate_not_clear:closed_trade_review_required" in report["blockers"]
    assert (
        "next_attempt_gate:NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED"
        in report["blockers"]
    )
    paths = [call["path"] for call in client.calls]
    assert paths == ["/api/trading-console/owner-action-flow"]
    assert "authorization_id" not in report["ids"]


def test_prepare_blocks_before_draft_when_order_candidate_is_already_used():
    client = _FakeClient(
        candidate_reusable=False,
        candidate_usage_status="submit_authorization_recorded",
    )
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="prepare",
            order_candidate_id="candidate-1",
        ),
    )

    report = flow.run()

    assert (
        "order_candidate_not_reusable:submit_authorization_recorded"
        in report["blockers"]
    )
    assert "order_candidate_already_has_submit_authorization" in report["blockers"]
    paths = [call["path"] for call in client.calls]
    assert paths == ["/api/trading-console/order-candidates/candidate-1"]
    assert "authorization_id" not in report["ids"]


def test_arm_records_local_and_exchange_submit_evidence_without_real_submit():
    client = _FakeClient()
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="arm",
            order_candidate_id="candidate-1",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ids"]["local_registration_enablement_decision_id"] == "local-enable-1"
    assert report["ids"]["exchange_submit_enablement_decision_id"] == "exchange-enable-1"
    paths = [call["path"] for call in client.calls]
    assert any("runtime-execution-controlled-submit-plans" in path for path in paths)
    assert any("runtime-execution-protection-plans" in path for path in paths)
    assert any("exchange-submit-adapter-results" in path for path in paths)
    assert not any("first-real-submit-actions" in path for path in paths)


def test_arm_blocks_before_attempt_mutation_when_submit_facts_are_stale():
    client = _FakeClient(
        evidence_blockers=[
            "trusted_reconciliation_fact_stale",
            "trusted_submit_facts_not_fresh_enough",
        ],
    )
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="arm",
            order_candidate_id="candidate-1",
        ),
    )

    report = flow.run()

    assert "trusted_reconciliation_fact_stale" in report["blockers"]
    assert "trusted_submit_facts_not_fresh_enough" in report["blockers"]
    assert not any(
        "runtimeexecutionorderlifecycleadapterresult_not_found" in blocker
        for blocker in report["blockers"]
    )
    paths = [call["path"] for call in client.calls]
    assert not any("runtime-execution-attempt-reservations" in path for path in paths)
    assert not any("runtime-execution-attempt-mutations" in path for path in paths)
    assert not any("runtime-execution-local-registration-action-authorizations" in path for path in paths)
    assert not any("runtime-execution-exchange-submit-action-authorizations" in path for path in paths)


def test_arm_existing_authorization_reuses_existing_attempt_policy():
    client = _FakeClient(existing_attempt_policy=True)
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="arm",
            authorization_id="auth-1",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ids"]["reservation_id"] == "runtime-attempt-reservation-auth-1"
    assert (
        "existing_attempt_outcome_policy_reused_no_new_attempt_mutation"
        in report["warnings"]
    )
    paths = [call["path"] for call in client.calls]
    assert any("runtime-execution-controlled-submit-plans" in path for path in paths)
    assert not any("runtime-execution-attempt-mutations" in path for path in paths)


def test_execute_requires_exact_env_confirmation(monkeypatch):
    monkeypatch.delenv(APPROVAL_ENV, raising=False)
    client = _FakeClient()
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="execute",
            order_candidate_id="candidate-1",
            execute_real_submit=True,
        ),
    )

    report = flow.run()

    assert "owner_runtime_first_real_submit_env_confirmation_missing" in report["blockers"]
    paths = [call["path"] for call in client.calls]
    assert not any("attempt-mutations" in path for path in paths)
    assert not any("exchange-submit-action-authorizations" in path for path in paths)
    assert not any("first-real-submit-actions" in path for path in paths)


def test_execute_calls_real_submit_when_env_guard_matches(monkeypatch):
    monkeypatch.setenv(APPROVAL_ENV, _approval_value("auth-1"))
    client = _FakeClient()
    flow = FirstRealSubmitApiFlow(
        client=client,
        config=FlowConfig(
            api_base="http://unit",
            mode="execute",
            order_candidate_id="candidate-1",
            execute_real_submit=True,
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ids"]["execution_result_id"] == "exec-1"
    assert os.environ[APPROVAL_ENV] == "auth-1:first-real-submit:real_gateway_action"
    paths = [call["path"] for call in client.calls]
    assert any("first-real-submit-actions" in path for path in paths)
