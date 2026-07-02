from __future__ import annotations

from decimal import Decimal

from scripts import execute_runtime_profile_apply_plan as executor
from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script
from scripts import runtime_profile_confirmation_apply_plan as apply_script
from scripts import runtime_profile_confirmation_record as confirmation_record_script
from scripts import runtime_profile_trial_binding_apply_readiness as readiness_script


class _FakeClient:
    def __init__(self, *, fail_step: str | None = None) -> None:
        self.calls: list[dict] = []
        self.fail_step = fail_step

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": dict(body or {}),
            }
        )
        if self.fail_step and path.endswith(self.fail_step):
            return {"http_status": 400, "body": {"detail": "blocked"}, "error": True}
        if path == "/api/brc/strategy-runtime-promotion-confirmations":
            return {
                "http_status": 200,
                "body": {
                    "confirmation": {
                        "confirmation_id": body["confirmation_id"],
                        "runtime_mutation_created": False,
                    }
                },
            }
        if path.endswith("/runtime-drafts"):
            return {
                "http_status": 200,
                "body": {
                    "runtime": {
                        "runtime_instance_id": "strategy-runtime-rbr-ada-short-1",
                        "execution_enabled": False,
                        "shadow_mode": True,
                    }
                },
            }
        return {"http_status": 404, "body": {"detail": "not found"}, "error": True}


def _selector_artifact(signals: list[dict]) -> dict:
    return {
        "scope": "runtime_live_strategy_signal_selector",
        "status": "would_enter_available_but_not_runtime_compatible",
        "blockers": ["would_enter_signals_not_runtime_compatible"],
        "non_runtime_would_enter_signals": signals,
    }


def _rbr_signal() -> dict:
    return {
        "candidate_id": "RBR-001-ADA-SHORT",
        "strategy_family_id": "RBR-001",
        "strategy_family_version_id": "RBR-001-v0",
        "symbol": "ADA/USDT:USDT",
        "side": "short",
        "signal_type": "would_enter",
        "confidence": "0.57",
        "reason_codes": ["rbr_range_context", "rbr_boundary_rejection_confirmed"],
        "runtime_compatible": False,
        "not_order": True,
        "not_execution_intent": True,
    }


def _binding(binding_id: str = "binding-rbr-1") -> dict:
    return {
        "binding_id": binding_id,
        "admission_decision_id": f"decision-{binding_id}",
        "owner_risk_acceptance_id": f"risk-{binding_id}",
        "trial_constraint_snapshot_id": f"constraint-{binding_id}",
        "strategy_family_version_id": "RBR-001-v0",
        "playbook_id": "PB-BRC-LIVE-RUNTIME-V1",
        "trial_env": "live",
        "trial_stage": "funded_validation",
        "execution_mode": "auto_within_budget",
        "binding_status": "binding_reserved",
        "campaign_id": None,
        "runtime_carrier_id": None,
        "created_by_operation_id": f"op-{binding_id}",
        "created_by_preflight_id": f"preflight-{binding_id}",
        "created_at_ms": 1781283600000,
        "updated_at_ms": 1781283600000,
        "invalidated_at_ms": None,
        "invalidation_reason": None,
    }


def _ready_readiness() -> dict:
    proposal_artifact = proposal_script.build_profile_proposal_artifact(
        selector_artifact=_selector_artifact([_rbr_signal()]),
        capital_base=Decimal("30"),
    )
    confirmation_record = confirmation_record_script.build_record(
        proposal_artifact=proposal_artifact,
        created_at_ms=1781283600000,
    )
    required = apply_script.build_apply_plan(
        confirmation_record=confirmation_record,
    )["owner_confirmation"]["required_value"]
    return readiness_script.build_apply_readiness(
        apply_confirmation_record=confirmation_record,
        trial_bindings_payload={"trial_bindings": [_binding()]},
        owner_confirmation_value=required,
    )


def test_dry_run_reports_plan_without_api_calls() -> None:
    client = _FakeClient()
    report = executor.build_execution_report(
        apply_readiness_artifact=_ready_readiness(),
        mode="dry-run",
        execute=False,
        client=client,
    )

    assert report["status"] == "dry_run_runtime_profile_apply_plan_ready"
    assert report["checks"]["api_called"] is False
    assert report["requests_planned"][0]["path"] == (
        "/api/brc/strategy-runtime-promotion-confirmations"
    )
    assert report["safety_invariants"]["runtime_created"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert client.calls == []


def test_apply_mode_requires_execute_flag() -> None:
    report = executor.build_execution_report(
        apply_readiness_artifact=_ready_readiness(),
        mode="apply",
        execute=False,
        client=_FakeClient(),
    )

    assert report["status"] == "blocked_runtime_profile_apply_plan"
    assert "execute_flag_required_for_apply_mode" in report["blockers"]
    assert report["safety_invariants"]["api_called"] is False


def test_apply_executes_two_official_api_requests_only() -> None:
    client = _FakeClient()
    report = executor.build_execution_report(
        apply_readiness_artifact=_ready_readiness(),
        mode="apply",
        execute=True,
        client=client,
    )

    assert report["status"] == "runtime_profile_apply_plan_applied"
    assert report["checks"]["promotion_confirmation_record_created"] is True
    assert report["checks"]["shadow_runtime_draft_created"] is True
    assert report["ids"]["runtime_instance_id"] == "strategy-runtime-rbr-ada-short-1"
    assert [call["path"] for call in client.calls] == [
        "/api/brc/strategy-runtime-promotion-confirmations",
        (
            "/api/brc/strategy-runtime-promotion-confirmations/"
            "promotion-confirmation-rbr-001-rbr-001-v0-ada-usdt-usdt-short/runtime-drafts"
        ),
    ]
    assert not any("order" in call["path"] for call in client.calls)
    assert report["safety_invariants"]["runtime_enabled"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False


def test_apply_stops_on_api_error() -> None:
    client = _FakeClient(fail_step="/runtime-drafts")
    report = executor.build_execution_report(
        apply_readiness_artifact=_ready_readiness(),
        mode="apply",
        execute=True,
        client=client,
    )

    assert report["status"] == "blocked_runtime_profile_apply_plan"
    assert report["blockers"] == ["create_shadow_runtime_draft_http_error"]
    assert len(client.calls) == 2
    assert report["safety_invariants"]["runtime_created"] is False


def test_blocks_unsafe_apply_request() -> None:
    apply_readiness_artifact = _ready_readiness()
    apply_readiness_artifact["apply_plan"]["api_apply_plan"]["requests"].append(
        {
            "step": "bad_exchange_call",
            "method": "POST",
            "path": "/api/brc/exchange-submit",
            "body": {},
        }
    )

    report = executor.build_execution_report(
        apply_readiness_artifact=apply_readiness_artifact,
        mode="dry-run",
    )

    assert report["status"] == "blocked_runtime_profile_apply_plan"
    assert "api_apply_plan_requires_exactly_two_requests" in report["blockers"]
    assert "api_apply_plan_contains_unsafe_request" in report["blockers"]


def test_blocks_not_ready_readiness_without_noisy_plan_shape_blockers() -> None:
    report = executor.build_execution_report(
        apply_readiness_artifact={
            "status": "waiting_for_matching_trial_binding",
            "apply_plan": None,
        },
        mode="dry-run",
    )

    assert report["status"] == "blocked_runtime_profile_apply_plan"
    assert report["blockers"] == [
        "api_apply_plan_not_ready",
        "rtf038_apply_readiness_not_ready",
    ]


def test_rejects_legacy_packet_kwarg() -> None:
    try:
        executor.build_execution_report(
            packet=_ready_readiness(),
            mode="dry-run",
        )
    except TypeError as exc:
        assert "packet" in str(exc)
    else:
        raise AssertionError("legacy packet kwarg must be rejected")
