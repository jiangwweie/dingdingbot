from __future__ import annotations

import json

from scripts.refresh_strategygroup_runtime_product_state_artifacts import refresh_product_state_artifacts
from scripts import refresh_strategygroup_runtime_product_state_artifacts as refresh_script


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_refresh_product_state_artifacts_writes_readmodel_artifacts_without_side_effects(tmp_path):
    calls = []
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [
                {"code": "strategy_group_candidate_prerequisites_pending"}
            ],
            "data": {
                "status": (
                    "strategy_group_observe_ready_candidate_prerequisites_pending"
                ),
                "blockers": [],
                "candidate_prepare_blockers": ["MPG-001:budget:missing"],
            },
        },
        "/api/trading-console/owner-console-source-readiness": {
            "freshness_status": "warning",
            "blockers": [],
            "warnings": [{"code": "owner_console_source_readiness_degraded"}],
            "data": {
                "status": "ready",
                "owner_state": {"status": "waiting_for_opportunity"},
                "source_health": {
                    "orders": {"status": "ready_empty"},
                    "positions": {"status": "ready_empty"},
                },
            },
        },
        "/api/trading-console/strategygroup-runtime-pilot-status": {
            "freshness_status": "warning",
            "blockers": [],
            "warnings": [{"code": "strategygroup_runtime_pilot_waiting_for_market"}],
            "data": {
                "status": "waiting_for_market",
                "watcher_scope_alignment": {"status": "expanded_scope"},
            },
        },
    }

    def opener(request, timeout):
        calls.append((request.full_url, timeout, request.headers.get("Cookie")))
        path = request.full_url.replace("http://unit", "")
        return _FakeResponse(payloads[path])

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
    )

    assert artifact["status"] == "refreshed"
    assert [item["status"] for item in artifact["artifacts"]] == [
        "strategy_group_observe_ready_candidate_prerequisites_pending",
        "ready",
        "waiting_for_market",
    ]
    assert "packets" not in artifact
    assert "source_readiness_fallback" not in artifact
    assert (tmp_path / "strategy-group-live-facts-readiness.json").exists()
    assert (tmp_path / "owner-console-source-readiness.json").exists()
    assert (tmp_path / "strategygroup-runtime-pilot-status.json").exists()
    assert all(call[1] == 7 for call in calls)
    assert all(call[2] == "session=test" for call in calls)
    assert artifact["safety_invariants"] == {
        "readmodel_refresh_only": True,
        "optional_signed_get_live_facts_precollect": False,
        "optional_api_readmodel_refresh": True,
        "optional_dry_run_audit_chain_refresh": False,
        "optional_chain_closure_status_refresh": False,
        "optional_live_closure_evidence_refresh": False,
        "optional_goal_status_refresh": False,
        "goal_status_external_pg_projector_required": True,
        "optional_source_readiness_unavailable_evidence": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "places_order": False,
        "mutates_pg": False,
    }


def test_refresh_product_state_artifacts_can_precollect_live_facts_before_readmodel_refresh(tmp_path):
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {
                "status": "strategy_group_live_facts_ready_for_armed_observation",
                "blockers": [],
                "candidate_prepare_blockers": [],
            },
        },
        "/api/trading-console/owner-console-source-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "ready"},
        },
        "/api/trading-console/strategygroup-runtime-pilot-status": {
            "freshness_status": "warning",
            "blockers": [],
            "warnings": [{"code": "strategygroup_runtime_pilot_waiting_for_market"}],
            "data": {"status": "waiting_for_market"},
        },
    }

    def opener(request, timeout):
        path = request.full_url.replace("http://unit", "")
        return _FakeResponse(payloads[path])

    def collect_live_facts(**kwargs):
        assert kwargs["handoff_dir"] == tmp_path / "handoffs"
        assert kwargs["env_file"] == tmp_path / "live-readonly.env"
        assert kwargs["base_url"] == "https://unit-binance.test"
        return {
            "scope": "strategy_group_live_facts_input",
            "status": "ready",
            "collector_errors": {},
            "safety_invariants": {
                "signed_get_only": True,
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
        collect_live_facts_before_refresh=True,
        handoff_dir=tmp_path / "handoffs",
        env_file=tmp_path / "live-readonly.env",
        live_facts_base_url="https://unit-binance.test",
        live_facts_collector=collect_live_facts,
    )

    live_facts_path = tmp_path / "strategy-group-live-facts-input.json"
    assert live_facts_path.exists()
    assert json.loads(live_facts_path.read_text())["status"] == "ready"
    assert artifact["status"] == "refreshed"
    assert artifact["live_facts_precollect"] == {
        "enabled": True,
        "status": "ready",
        "output_json": str(live_facts_path),
        "collector_error_count": 0,
        "signed_get_only": True,
    }
    assert artifact["safety_invariants"]["optional_signed_get_live_facts_precollect"] is True
    assert artifact["safety_invariants"]["optional_dry_run_audit_chain_refresh"] is False
    assert artifact["safety_invariants"]["optional_live_closure_evidence_refresh"] is False
    assert artifact["safety_invariants"]["optional_goal_status_refresh"] is False
    assert artifact["safety_invariants"]["optional_source_readiness_unavailable_evidence"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_refresh_product_state_artifacts_passes_selected_strategygroup_scope_to_pilot_status(tmp_path):
    calls = []
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "ready", "blockers": []},
        },
        (
            "/api/trading-console/owner-console-source-readiness"
            "?selected_strategy_group_id=SOR-001&max_symbols=2&stale_after_seconds=240"
        ): {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {
                "status": "ready",
                "selected_scope_config": {
                    "selected_strategy_group_id": "SOR-001",
                    "max_symbols": 2,
                    "stale_after_seconds": 240,
                },
            },
        },
        (
            "/api/trading-console/strategygroup-runtime-pilot-status"
            "?selected_strategy_group_id=SOR-001&max_symbols=2&stale_after_seconds=240"
        ): {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {
                "status": "waiting_for_market",
                "selected": {"strategy_group_id": "SOR-001"},
            },
        },
    }

    def opener(request, timeout):
        calls.append(request.full_url.replace("http://unit", ""))
        path = request.full_url.replace("http://unit", "")
        return _FakeResponse(payloads[path])

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
        selected_strategy_group_id="SOR-001",
        max_symbols=2,
        stale_after_seconds=240,
    )

    assert artifact["status"] == "refreshed"
    assert artifact["selected_scope_config"] == {
        "selected_strategy_group_id": "SOR-001",
        "max_symbols": 2,
        "stale_after_seconds": 240,
        "source": "cli_or_env",
    }
    assert calls[-2] == (
        "/api/trading-console/owner-console-source-readiness"
        "?selected_strategy_group_id=SOR-001&max_symbols=2&stale_after_seconds=240"
    )
    assert calls[-1] == (
        "/api/trading-console/strategygroup-runtime-pilot-status"
        "?selected_strategy_group_id=SOR-001&max_symbols=2&stale_after_seconds=240"
    )


def test_refresh_product_state_artifacts_refreshes_local_artifacts_without_goal_status_writer(tmp_path):
    events = []
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "strategy_group_live_facts_ready_for_armed_observation"},
        },
        "/api/trading-console/owner-console-source-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "ready"},
        },
        "/api/trading-console/strategygroup-runtime-pilot-status": {
            "freshness_status": "warning",
            "blockers": [],
            "warnings": [],
            "data": {"status": "waiting_for_market"},
        },
    }

    def opener(request, timeout):
        path = request.full_url.replace("http://unit", "")
        events.append(f"api:{path}")
        return _FakeResponse(payloads[path])

    def dry_run_builder(output_dir):
        events.append("dry_run")
        assert output_dir == tmp_path / "dry"
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def chain_closure_status_builder(**kwargs):
        events.append("chain_closure")
        assert kwargs["audit_artifact"]["scope"] == "runtime_dry_run_audit_chain"
        return {
            "scope": "runtime_execution_chain_closure_status",
            "status": "non_market_execution_chain_ready",
            "real_execution": {
                "real_order_allowed": False,
                "missing_live_proofs": [
                    "live_fresh_signal",
                    "same_run_action_time_finalgate_pass",
                ],
            },
        }

    def live_closure_evidence_refresher(**kwargs):
        events.append("live_closure")
        assert kwargs["report_dir"] == tmp_path
        assert kwargs["output_json"] == tmp_path / "runtime-live-closure-evidence.json"
        assert kwargs["verification_output_json"] == (
            tmp_path / "runtime-live-closure-evidence-verification.json"
        )
        assert kwargs["refresh_output_json"] == (
            tmp_path / "runtime-live-closure-evidence-refresh.json"
        )
        return {
            "scope": "runtime_live_closure_evidence_refresh",
            "status": "live_closure_refresh_not_started",
            "verification": {
                "status": "live_closure_not_started",
                "first_bounded_real_order_complete": False,
                "real_order_closure_proven": False,
                "reject_reasons": [],
            },
        }

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=tmp_path / "runtime-dry-run-audit-chain.json",
        dry_run_builder=dry_run_builder,
        refresh_chain_closure_status=True,
        chain_closure_output_json=tmp_path / "runtime-execution-chain-closure-status.json",
        chain_closure_status_builder=chain_closure_status_builder,
        refresh_live_closure_evidence=True,
        live_closure_evidence_refresher=live_closure_evidence_refresher,
    )

    assert artifact["status"] == "refreshed"
    assert events == [
        "dry_run",
        "chain_closure",
        "live_closure",
        "api:/api/trading-console/strategy-group-live-facts-readiness",
        "api:/api/trading-console/owner-console-source-readiness",
        "api:/api/trading-console/strategygroup-runtime-pilot-status",
    ]
    assert artifact["dry_run_audit_refresh"] == {
        "enabled": True,
        "status": "passed",
        "output_json": str(tmp_path / "runtime-dry-run-audit-chain.json"),
        "output_dir": str(tmp_path / "dry"),
        "goal_status_input_json": str(tmp_path / "runtime-dry-run-audit-chain.json"),
        "scenario_count": 14,
        "dangerous_effects_absent": True,
    }
    assert artifact["chain_closure_status_refresh"] == {
        "enabled": True,
        "status": "non_market_execution_chain_ready",
        "output_json": str(tmp_path / "runtime-execution-chain-closure-status.json"),
        "audit_json": str(tmp_path / "runtime-dry-run-audit-chain.json"),
        "real_order_allowed": False,
        "missing_live_proof_count": 2,
    }
    assert artifact["live_closure_evidence_refresh"] == {
        "enabled": True,
        "status": "live_closure_refresh_not_started",
        "output_json": str(tmp_path / "runtime-live-closure-evidence.json"),
        "verification_output_json": str(
            tmp_path / "runtime-live-closure-evidence-verification.json"
        ),
        "refresh_output_json": str(
            tmp_path / "runtime-live-closure-evidence-refresh.json"
        ),
        "report_dir": str(tmp_path),
        "verification_status": "live_closure_not_started",
        "first_bounded_real_order_complete": False,
        "real_order_closure_proven": False,
        "reject_reasons": [],
    }
    assert artifact["goal_status_refresh"] == {
        "enabled": False,
        "status": "retired_external_pg_projector_required",
        "reason": (
            "Goal Status current projection is owned by "
            "build_strategygroup_runtime_goal_status.py --require-database-url"
        ),
    }
    assert (tmp_path / "runtime-dry-run-audit-chain.json").exists()
    assert (tmp_path / "runtime-execution-chain-closure-status.json").exists()
    assert not (tmp_path / "strategygroup-runtime-goal-status.json").exists()
    assert artifact["safety_invariants"]["optional_dry_run_audit_chain_refresh"] is True
    assert artifact["safety_invariants"]["optional_chain_closure_status_refresh"] is True
    assert artifact["safety_invariants"]["optional_live_closure_evidence_refresh"] is True
    assert artifact["safety_invariants"]["optional_goal_status_refresh"] is False
    assert (
        artifact["safety_invariants"]["goal_status_external_pg_projector_required"]
        is True
    )
    assert artifact["safety_invariants"]["optional_source_readiness_unavailable_evidence"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_refresh_product_state_artifacts_retires_default_goal_status_writer(
    tmp_path,
    monkeypatch,
):
    output_dir = tmp_path / "reports"
    external_dry_run_json = tmp_path / "external" / "runtime-dry-run-audit-chain.json"
    external_goal_status_json = tmp_path / "external" / "strategygroup-runtime-goal-status.json"

    def missing_cookie():
        raise RuntimeError("operator auth missing")

    def dry_run_builder(output_dir):
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=output_dir,
        label="unit",
        timeout_seconds=7,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=external_dry_run_json,
        dry_run_builder=dry_run_builder,
    )

    mirrored_dry_run_json = output_dir / "runtime-dry-run-audit-chain.json"
    mirrored_goal_status_json = output_dir / "strategygroup-runtime-goal-status.json"
    assert external_dry_run_json.exists()
    assert mirrored_dry_run_json.exists()
    assert not external_goal_status_json.exists()
    assert not mirrored_goal_status_json.exists()
    assert artifact["dry_run_audit_refresh"]["output_json"] == str(external_dry_run_json)
    assert artifact["dry_run_audit_refresh"]["goal_status_input_json"] == str(
        mirrored_dry_run_json
    )
    assert artifact["goal_status_refresh"] == {
        "enabled": False,
        "status": "retired_external_pg_projector_required",
        "reason": (
            "Goal Status current projection is owned by "
            "build_strategygroup_runtime_goal_status.py --require-database-url"
        ),
    }
    assert "fallback_input_json" not in artifact["goal_status_refresh"]
    assert artifact["dry_run_audit_refresh"]["status"] == "passed"
    assert artifact["source_readiness_unavailable_evidence"]["goal_status_included"] is False
    assert artifact["safety_invariants"]["optional_goal_status_refresh"] is False
    assert (
        artifact["safety_invariants"]["goal_status_external_pg_projector_required"]
        is True
    )
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_refresh_product_state_artifacts_auth_missing_does_not_block_local_audit_refresh(
    tmp_path,
    monkeypatch,
):
    def missing_cookie():
        raise RuntimeError("operator auth missing")

    def dry_run_builder(output_dir):
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    (tmp_path / "strategygroup-runtime-goal-status.json").write_text(
        json.dumps(
            {
                "scope": "strategygroup_runtime_goal_status",
                "status": "missing_fact",
                "checks": {"runtime_dry_run_audit_passed": True},
                "owner_state": {
                    "non_authority_checkpoint": (
                        "refresh_or_repair_owner_console_source_readiness"
                    )
                },
                "real_order_boundary": {"ready_for_real_order_action": False},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)
    (tmp_path / "tokyo-readonly-probe-current.json").write_text(
        json.dumps(
            {
                "scope": "tokyo_runtime_governance_readonly_probe",
                "status": "blocked",
                "checks": {"blockers": ["tokyo_ssh_publickey_denied"]},
                "facts": {"probe_error": "Permission denied (publickey)."},
            }
        ),
        encoding="utf-8",
    )

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=tmp_path / "runtime-dry-run-audit-chain.json",
        dry_run_builder=dry_run_builder,
    )

    assert artifact["status"] == "refresh_blocked"
    assert artifact["dry_run_audit_refresh"]["status"] == "passed"
    assert artifact["goal_status_refresh"]["status"] == (
        "retired_external_pg_projector_required"
    )
    assert artifact["source_readiness_unavailable_evidence"] == {
        "enabled": True,
        "status": "source_unavailable",
        "output_json": str(tmp_path / "owner-console-source-readiness.json"),
        "reason": "operator_cookie_unavailable",
        "goal_status_included": True,
    }
    assert "source_readiness_fallback" not in artifact
    assert "operator_cookie_unavailable:RuntimeError" in artifact["blockers"]
    assert (
        "owner-console-source-readiness.json:refresh_skipped:"
        "operator_cookie_unavailable"
    ) in artifact["blockers"]
    assert (tmp_path / "runtime-dry-run-audit-chain.json").exists()
    assert (tmp_path / "strategygroup-runtime-goal-status.json").exists()
    source_readiness = json.loads(
        (tmp_path / "owner-console-source-readiness.json").read_text(
            encoding="utf-8"
        )
    )
    assert source_readiness["status"] == "source_unavailable"
    assert source_readiness["owner_state"]["status"] == "temporarily_unavailable"
    assert "next_safe_checkpoint" not in source_readiness["owner_state"]
    assert source_readiness["owner_state"]["non_authority_checkpoint"] == (
        "refresh_or_repair_owner_console_source_readiness"
    )
    assert source_readiness["source_health"]["runtime_source"]["status"] == "unavailable"
    assert source_readiness["source_health"]["watcher"]["status"] == "unavailable"
    assert source_readiness["source_health"]["runtime_dry_run_audit"]["status"] == "ready"
    assert source_readiness["source_health"]["deploy_channel"]["status"] == "degraded"
    assert source_readiness["source_health"]["deploy_channel"]["owner_label"] == (
        "部署通道暂不可用"
    )
    assert source_readiness["source_health"]["deploy_channel"]["summary"][
        "blockers"
    ] == ["tokyo_ssh_publickey_denied"]
    assert (
        source_readiness["raw_status_refs"]["strategygroup_runtime_goal_status"]
        == "missing_fact"
    )
    assert (
        source_readiness["raw_status_refs"]["source_unavailable_reason"]
        == "operator_cookie_unavailable"
    )
    assert "fallback_reason" not in source_readiness["raw_status_refs"]
    assert source_readiness["raw_status_refs"]["tokyo_deploy_channel_blockers"] == [
        "tokyo_ssh_publickey_denied"
    ]
    assert (
        source_readiness["safety_invariants"][
            "source_readiness_unavailable_evidence_only"
        ]
        is True
    )
    assert (
        "source_readiness_fallback_evidence_only"
        not in source_readiness["safety_invariants"]
    )
    assert "fallback_packet_only" not in source_readiness["safety_invariants"]
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["optional_source_readiness_unavailable_evidence"] is True
    assert "optional_source_readiness_fallback" not in artifact["safety_invariants"]


def test_refresh_product_state_artifacts_can_skip_api_readmodels_for_local_artifact_refresh(
    tmp_path,
    monkeypatch,
):
    def missing_cookie():
        raise AssertionError("operator cookie should not be requested")

    def dry_run_builder(output_dir):
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {"dangerous_effects_absent": True},
            "required_checks": {"all_scenarios_passed": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
                "disabled_smoke_is_real_execution_proof": False,
            },
        }

    def chain_closure_status_builder(**kwargs):
        return {
            "scope": "runtime_execution_chain_closure_status",
            "status": "non_market_execution_chain_ready",
            "real_execution": {
                "real_order_allowed": False,
                "missing_live_proofs": ["live_fresh_signal"],
            },
        }

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    artifact = refresh_product_state_artifacts(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        generated_at_ms=1,
        refresh_api_readmodels=False,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=tmp_path / "runtime-dry-run-audit-chain.json",
        dry_run_builder=dry_run_builder,
        refresh_chain_closure_status=True,
        chain_closure_output_json=tmp_path
        / "runtime-execution-chain-closure-status.json",
        chain_closure_status_builder=chain_closure_status_builder,
    )

    assert artifact["status"] == "refreshed"
    assert artifact["blockers"] == []
    assert artifact["artifacts"] == [
        {
            "endpoint": "api_readmodels",
            "output_json": None,
            "status": "skipped_by_request",
            "api_freshness_status": None,
            "api_blocker_count": 0,
            "api_warning_count": 0,
        }
    ]
    assert artifact["source_readiness_unavailable_evidence"] == {
        "enabled": False,
        "status": "skipped",
    }
    assert artifact["dry_run_audit_refresh"]["status"] == "passed"
    assert artifact["chain_closure_status_refresh"]["status"] == (
        "non_market_execution_chain_ready"
    )
    assert artifact["safety_invariants"]["optional_api_readmodel_refresh"] is False
    assert not (tmp_path / "owner-console-source-readiness.json").exists()


def test_deploy_channel_status_wins_over_docs_only_readonly_head_mismatch(tmp_path):
    (tmp_path / "tokyo-deploy-channel-status.json").write_text(
        json.dumps(
            {
                "scope": "tokyo_runtime_deploy_channel_status",
                "status": "postdeploy_accepted",
                "checks": {"blockers": []},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tokyo-readonly-probe-current.json").write_text(
        json.dumps(
            {
                "scope": "tokyo_runtime_governance_readonly_probe",
                "status": "blocked",
                "checks": {"blockers": ["remote_current_head_mismatch"]},
                "facts": {
                    "current_head": "6b615aac",
                    "current_status": "release_manifest_without_git_status",
                },
            }
        ),
        encoding="utf-8",
    )

    deploy_channel = refresh_script._deploy_channel_status_evidence(tmp_path)

    assert deploy_channel == {
        "status": "ready",
        "owner_label": "部署通道正常",
        "reason": "postdeploy_accepted",
        "summary": {
            "checked": True,
            "connectivity_ready": None,
            "blockers": [],
            "source_status": "postdeploy_accepted",
        },
    }


def test_cli_can_treat_degraded_local_refresh_as_continuable(
    tmp_path,
    monkeypatch,
    capsys,
):
    def missing_cookie():
        raise RuntimeError("operator auth missing")

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    output_json = tmp_path / "product-state-refresh-artifact.json"
    exit_code = refresh_script.main(
        [
            "--output-dir",
            str(tmp_path),
            "--output-json",
            str(output_json),
            "--refresh-dry-run-audit-chain",
            "--allow-degraded-local-refresh-success",
            "--selected-strategy-group-id",
            "MPG-001",
            "--max-symbols",
            "3",
            "--stale-after-seconds",
            "180",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["cli_exit_policy"] == artifact["cli_exit_policy"]
    assert artifact["status"] == "refresh_blocked"
    assert artifact["cli_exit_policy"] == {
        "status": "degraded_local_refresh_continuable",
        "exit_code": 0,
        "reason": "operator_cookie_unavailable_with_local_audit_refresh_complete",
    }
    assert artifact["dry_run_audit_refresh"]["status"] == "passed"
    assert artifact["dry_run_audit_refresh"]["scenario_count"] == 14
    assert artifact["goal_status_refresh"]["status"] == (
        "retired_external_pg_projector_required"
    )
    assert artifact["source_readiness_unavailable_evidence"]["reason"] == (
        "operator_cookie_unavailable"
    )
    assert "source_readiness_fallback" not in artifact
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert list(tmp_path.glob(".product-state-refresh-artifact.json.*.tmp")) == []
    assert list(tmp_path.glob(".runtime-dry-run-audit-chain.json.*.tmp")) == []
    assert list(tmp_path.glob(".strategygroup-runtime-goal-status.json.*.tmp")) == []


def test_cli_keeps_default_blocked_exit_for_degraded_refresh(
    tmp_path,
    monkeypatch,
    capsys,
):
    def missing_cookie():
        raise RuntimeError("operator auth missing")

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    exit_code = refresh_script.main(
        [
            "--output-dir",
            str(tmp_path),
            "--refresh-dry-run-audit-chain",
            "--selected-strategy-group-id",
            "MPG-001",
            "--max-symbols",
            "3",
            "--stale-after-seconds",
            "180",
        ]
    )

    assert exit_code == 2
    artifact = json.loads(capsys.readouterr().out)
    assert artifact["status"] == "refresh_blocked"
    assert "cli_exit_policy" not in artifact
    assert artifact["dry_run_audit_refresh"]["status"] == "passed"
    assert artifact["goal_status_refresh"]["status"] == (
        "retired_external_pg_projector_required"
    )
