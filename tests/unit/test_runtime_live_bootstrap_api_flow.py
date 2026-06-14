from __future__ import annotations

from scripts.runtime_live_bootstrap_api_flow import (
    BootstrapConfig,
    RuntimeLiveBootstrapApiFlow,
)


class _FakeClient:
    def __init__(
        self,
        *,
        profile_status: str = "ready_for_owner_codex_confirmation",
        runtime_draft_status: int = 200,
    ) -> None:
        self.calls: list[dict] = []
        self.profile_status = profile_status
        self.runtime_draft_status = runtime_draft_status

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        if (
            method == "GET"
            and "/strategy-families/" in path
            and not path.endswith("/versions")
        ):
            return {"http_status": 404, "body": {"detail": "not found"}, "error": True}
        if method == "GET" and "/strategy-family-versions/" in path:
            return {"http_status": 404, "body": {"detail": "not found"}, "error": True}
        if method == "POST" and path == "/api/brc/strategy-families":
            return {
                "http_status": 200,
                "body": {"strategy_family_id": body["strategy_family_id"]},
            }
        if method == "POST" and path.endswith("/versions"):
            return {
                "http_status": 200,
                "body": {
                    "strategy_family_version_id": body["strategy_family_version_id"]
                },
            }
        if path.endswith("/admissions/evidence-packets"):
            return {"http_status": 200, "body": {"evidence_packet_id": "evidence-1"}}
        if path.endswith("/admissions/owner-regime-inputs"):
            return {
                "http_status": 200,
                "body": {"owner_market_regime_input_id": "regime-1"},
            }
        if path.endswith("/admissions/requests"):
            return {"http_status": 200, "body": {"admission_request_id": "req-1"}}
        if path.endswith("/admissions/requests/req-1/evaluate"):
            return {
                "http_status": 200,
                "body": {
                    "admission_decision_id": "decision-1",
                    "trial_constraint_snapshot_id": "constraint-1",
                    "decision": "admit_with_constraints",
                },
            }
        if path.endswith("/admissions/risk-acceptances"):
            return {
                "http_status": 200,
                "body": {"owner_risk_acceptance_id": "risk-acceptance-1"},
            }
        if path.endswith("/operations/preflight"):
            return {
                "http_status": 200,
                "body": {
                    "operation_id": "operation-1",
                    "preflight_id": "preflight-1",
                    "idempotency_key": "idem-1",
                    "decision": "allow",
                    "risk_summary": {"blockers": []},
                },
            }
        if path.endswith("/operations/operation-1/confirm"):
            return {
                "http_status": 200,
                "body": {
                    "status": "executed",
                    "result_summary": {"binding_id": "binding-1"},
                },
            }
        if path.endswith("/strategy-runtime-profile-proposals"):
            return {
                "http_status": 200,
                "body": {
                    "status": self.profile_status,
                    "proposal_id": "proposal-1",
                    "strategy_family_id": "CPM-001",
                    "strategy_family_version_id": "CPM-001-v0",
                    "symbol": "BNB/USDT:USDT",
                    "side": "long",
                    "min_liquidation_stop_buffer": "25",
                    "boundary": {"min_liquidation_stop_buffer": "25"},
                    "metadata": {},
                },
            }
        if path.endswith("/strategy-runtime-promotion-confirmations"):
            return {
                "http_status": 200,
                "body": {"confirmation": {"confirmation_id": "confirmation-1"}},
            }
        if path.endswith("/runtime-drafts"):
            if self.runtime_draft_status != 200:
                return {
                    "http_status": self.runtime_draft_status,
                    "body": {"detail": "blocked runtime draft"},
                    "error": True,
                }
            return {
                "http_status": 200,
                "body": {"runtime": {"runtime_instance_id": "runtime-1"}},
            }
        if path.endswith("/strategy-runtimes/runtime-1/lifecycle"):
            return {
                "http_status": 200,
                "body": {"runtime": {"runtime_instance_id": "runtime-1", "status": "active"}},
            }
        return {"http_status": 200, "body": {"status": "ok"}}


def test_bootstrap_creates_shadow_runtime_without_submit_endpoints():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="bootstrap",
            account_facts_source="static",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ready_for_shadow_candidate_planning"] is True
    assert report["ids"]["runtime_instance_id"] == "runtime-1"
    assert report["ids"]["runtime_status"] == "active"
    paths = [call["path"] for call in client.calls]
    assert any("strategy-runtime-promotion-confirmations" in path for path in paths)
    assert not any("first-real-submit-actions" in path for path in paths)
    assert not any("exchange-submit" in path for path in paths)
    assert not any("order-candidates" in path for path in paths)


def test_bootstrap_creates_strategy_version_with_selected_supported_symbols():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="binding-only",
            strategy_family_id="MPG-001",
            strategy_family_version_id="MPG-001-v0",
            family_key="mpg-momentum-persistence",
            family_name="MPG Momentum Persistence",
            symbol="INTC/USDT:USDT",
            supported_symbols=[
                "INTC/USDT:USDT",
                "MSTR/USDT:USDT",
                "COIN/USDT:USDT",
            ],
            side="long",
            account_facts_source="static",
            runtime_carrier_id="mpg-runtime-pilot",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    version_calls = [
        call for call in client.calls
        if call["path"].endswith("/strategy-families/MPG-001/versions")
    ]
    assert version_calls
    assert version_calls[0]["body"]["supported_symbols"] == [
        "INTC/USDT:USDT",
        "MSTR/USDT:USDT",
        "COIN/USDT:USDT",
    ]
    assert all(
        call["body"].get("carrier_id") != "first-real-submit-live-bootstrap"
        for call in client.calls
        if isinstance(call.get("body"), dict)
    )


def test_binding_only_stops_after_trial_binding_without_runtime_creation():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="binding-only",
            strategy_family_id="RBR-001",
            strategy_family_version_id="RBR-001-v0",
            family_key="rbr-price-action-reference",
            family_name="RBR Price Action Reference",
            symbol="ADA/USDT:USDT",
            side="short",
            account_facts_source="static",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert report["ready_for_trial_binding"] is True
    assert report["ready_for_shadow_candidate_planning"] is False
    assert report["ids"]["trial_binding_id"] == "binding-1"
    assert "runtime_instance_id" not in report["ids"]
    paths = [call["path"] for call in client.calls]
    assert not any(path.endswith("/strategy-runtime-profile-proposals") for path in paths)
    assert not any(path.endswith("/runtime-drafts") for path in paths)
    assert not any(path.endswith("/lifecycle") for path in paths)
    assert report["safety"]["creates_trial_binding"] is True
    assert report["safety"]["creates_runtime"] is False
    assert report["safety"]["activates_shadow_runtime"] is False
    assert report["safety"]["creates_order"] is False


def test_bootstrap_stops_when_profile_proposal_is_blocked():
    client = _FakeClient(profile_status="blocked")
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="bootstrap",
            account_facts_source="static",
        ),
    )

    report = flow.run()

    assert "profile_proposal_blocked" in report["blockers"]
    paths = [call["path"] for call in client.calls]
    assert not any(path.endswith("/runtime-drafts") for path in paths)
    assert not any(path.endswith("/lifecycle") for path in paths)


def test_short_bootstrap_confirms_conservative_short_profile():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="bootstrap",
            side="short",
            account_facts_source="static",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    promotion_calls = [
        call for call in client.calls if call["path"].endswith("promotion-confirmations")
    ]
    assert promotion_calls
    runtime_confirmations = promotion_calls[0]["body"]["runtime_confirmations"]
    assert runtime_confirmations["short_side_conservative_profile_confirmed"] is True


def test_bootstrap_can_override_liquidation_buffer_for_low_price_symbol():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="bootstrap",
            account_facts_source="static",
            min_liquidation_stop_buffer="0.05",
        ),
    )

    report = flow.run()

    assert report["blockers"] == []
    promotion_calls = [
        call for call in client.calls if call["path"].endswith("promotion-confirmations")
    ]
    snapshot = promotion_calls[0]["body"]["runtime_profile_proposal_snapshot"]
    assert snapshot["min_liquidation_stop_buffer"] == "0.05"
    assert snapshot["boundary"]["min_liquidation_stop_buffer"] == "0.05"
    assert snapshot["metadata"]["owner_runtime_profile_overrides"] == {
        "min_liquidation_stop_buffer": "0.05",
        "reason": "symbol_price_unit_adjustment_for_small_capital_trial",
    }


def test_bootstrap_stops_when_runtime_draft_blocks():
    client = _FakeClient(runtime_draft_status=400)
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(
            api_base="http://unit",
            mode="bootstrap",
            account_facts_source="static",
        ),
    )

    report = flow.run()

    assert "create_runtime_draft_http_400" in report["blockers"]
    paths = [call["path"] for call in client.calls]
    assert not any(path.endswith("/lifecycle") for path in paths)


def test_inspect_only_reads_current_inventory():
    client = _FakeClient()
    flow = RuntimeLiveBootstrapApiFlow(
        client=client,
        config=BootstrapConfig(api_base="http://unit", mode="inspect"),
    )

    report = flow.run()

    assert report["blockers"] == []
    assert [call["method"] for call in client.calls] == ["GET", "GET", "GET", "GET"]
