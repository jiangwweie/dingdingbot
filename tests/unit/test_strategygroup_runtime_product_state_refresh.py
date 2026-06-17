from __future__ import annotations

import json

from scripts.refresh_strategygroup_runtime_product_state_packets import refresh_packets
from scripts import refresh_strategygroup_runtime_product_state_packets as refresh_script


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_refresh_packets_writes_readmodel_packets_without_side_effects(tmp_path):
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

    packet = refresh_packets(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
    )

    assert packet["status"] == "refreshed"
    assert [item["status"] for item in packet["packets"]] == [
        "strategy_group_observe_ready_candidate_prerequisites_pending",
        "ready",
        "waiting_for_market",
    ]
    assert (tmp_path / "strategy-group-live-facts-readiness.json").exists()
    assert (tmp_path / "owner-console-source-readiness.json").exists()
    assert (tmp_path / "strategygroup-runtime-pilot-status.json").exists()
    assert all(call[1] == 7 for call in calls)
    assert all(call[2] == "session=test" for call in calls)
    assert packet["safety_invariants"] == {
        "readmodel_refresh_only": True,
        "optional_signed_get_live_facts_precollect": False,
        "optional_dry_run_audit_chain_refresh": False,
        "optional_goal_status_refresh": False,
        "optional_source_readiness_fallback": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "places_order": False,
        "mutates_pg": False,
    }


def test_refresh_packets_can_precollect_live_facts_before_readmodel_refresh(tmp_path):
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

    packet = refresh_packets(
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
    assert packet["status"] == "refreshed"
    assert packet["live_facts_precollect"] == {
        "enabled": True,
        "status": "ready",
        "output_json": str(live_facts_path),
        "collector_error_count": 0,
        "signed_get_only": True,
    }
    assert packet["safety_invariants"]["optional_signed_get_live_facts_precollect"] is True
    assert packet["safety_invariants"]["optional_dry_run_audit_chain_refresh"] is False
    assert packet["safety_invariants"]["optional_goal_status_refresh"] is False
    assert packet["safety_invariants"]["optional_source_readiness_fallback"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_refresh_packets_passes_selected_strategygroup_scope_to_pilot_status(tmp_path):
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

    packet = refresh_packets(
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

    assert packet["status"] == "refreshed"
    assert packet["selected_scope_config"] == {
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


def test_refresh_packets_can_refresh_dry_run_and_goal_status(tmp_path):
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
        return _FakeResponse(payloads[path])

    def dry_run_builder(output_dir):
        assert output_dir == tmp_path / "dry"
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 12,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def goal_status_builder(**kwargs):
        assert kwargs["report_dir"] == tmp_path
        assert kwargs["release_manifest"] == tmp_path / "manifest.json"
        assert kwargs["expected_head"] == "abc123"
        return {
            "scope": "strategygroup_runtime_goal_status",
            "status": "waiting_for_signal",
            "ready_for_real_order_action": False,
            "next_safe_checkpoint": "continue_watcher_observation",
            "checks": {
                "runtime_dry_run_audit_passed": True,
                "ready_for_real_order_action": True,
            },
            "owner_state": {"next_safe_checkpoint": "continue_watcher_observation"},
            "real_order_boundary": {"ready_for_real_order_action": True},
        }

    packet = refresh_packets(
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
        refresh_goal_status=True,
        goal_status_output_json=tmp_path / "strategygroup-runtime-goal-status.json",
        release_manifest=tmp_path / "manifest.json",
        expected_head="abc123",
        goal_status_builder=goal_status_builder,
    )

    assert packet["status"] == "refreshed"
    assert packet["dry_run_audit_refresh"] == {
        "enabled": True,
        "status": "passed",
        "output_json": str(tmp_path / "runtime-dry-run-audit-chain.json"),
        "output_dir": str(tmp_path / "dry"),
        "goal_status_input_json": str(tmp_path / "runtime-dry-run-audit-chain.json"),
        "scenario_count": 12,
        "dangerous_effects_absent": True,
    }
    assert packet["goal_status_refresh"] == {
        "enabled": True,
        "status": "waiting_for_signal",
        "output_json": str(tmp_path / "strategygroup-runtime-goal-status.json"),
        "fallback_input_json": str(tmp_path / "strategygroup-runtime-goal-status.json"),
        "next_safe_checkpoint": "continue_watcher_observation",
        "runtime_dry_run_audit_passed": True,
        "ready_for_real_order_action": False,
    }
    assert (tmp_path / "runtime-dry-run-audit-chain.json").exists()
    assert (tmp_path / "strategygroup-runtime-goal-status.json").exists()
    assert packet["safety_invariants"]["optional_dry_run_audit_chain_refresh"] is True
    assert packet["safety_invariants"]["optional_goal_status_refresh"] is True
    assert packet["safety_invariants"]["optional_source_readiness_fallback"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_refresh_packets_mirrors_external_dry_run_packet_for_goal_status(
    tmp_path,
    monkeypatch,
):
    from scripts.build_strategygroup_runtime_goal_status import (
        REQUIRED_DRY_RUN_CHECKS,
    )

    output_dir = tmp_path / "reports"
    external_dry_run_json = tmp_path / "external" / "runtime-dry-run-audit-chain.json"
    external_goal_status_json = (
        tmp_path / "external" / "strategygroup-runtime-goal-status.json"
    )

    def missing_cookie():
        raise RuntimeError("operator auth missing")

    def dry_run_builder(output_dir):
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 12,
            "checks": {name: True for name in REQUIRED_DRY_RUN_CHECKS},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    packet = refresh_packets(
        api_base="http://unit",
        output_dir=output_dir,
        label="unit",
        timeout_seconds=7,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=external_dry_run_json,
        dry_run_builder=dry_run_builder,
        refresh_goal_status=True,
        goal_status_output_json=external_goal_status_json,
    )

    mirrored_dry_run_json = output_dir / "runtime-dry-run-audit-chain.json"
    mirrored_goal_status_json = output_dir / "strategygroup-runtime-goal-status.json"
    assert external_dry_run_json.exists()
    assert mirrored_dry_run_json.exists()
    assert external_goal_status_json.exists()
    assert mirrored_goal_status_json.exists()
    assert packet["dry_run_audit_refresh"]["output_json"] == str(external_dry_run_json)
    assert packet["dry_run_audit_refresh"]["goal_status_input_json"] == str(
        mirrored_dry_run_json
    )
    assert packet["goal_status_refresh"]["output_json"] == str(external_goal_status_json)
    assert packet["goal_status_refresh"]["fallback_input_json"] == str(
        mirrored_goal_status_json
    )
    assert packet["dry_run_audit_refresh"]["status"] == "passed"
    assert packet["goal_status_refresh"]["runtime_dry_run_audit_passed"] is True
    assert packet["source_readiness_fallback"]["goal_status_included"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_refresh_packets_auth_missing_does_not_block_local_audit_refresh(
    tmp_path,
    monkeypatch,
):
    def missing_cookie():
        raise RuntimeError("operator auth missing")

    def dry_run_builder(output_dir):
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 12,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def goal_status_builder(**kwargs):
        return {
            "scope": "strategygroup_runtime_goal_status",
            "status": "missing_fact",
            "checks": {"runtime_dry_run_audit_passed": True},
            "owner_state": {
                "next_safe_checkpoint": "refresh_or_repair_owner_console_source_readiness"
            },
            "real_order_boundary": {"ready_for_real_order_action": False},
        }

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

    packet = refresh_packets(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=tmp_path / "dry",
        dry_run_output_json=tmp_path / "runtime-dry-run-audit-chain.json",
        dry_run_builder=dry_run_builder,
        refresh_goal_status=True,
        goal_status_output_json=tmp_path / "strategygroup-runtime-goal-status.json",
        goal_status_builder=goal_status_builder,
    )

    assert packet["status"] == "refresh_blocked"
    assert packet["dry_run_audit_refresh"]["status"] == "passed"
    assert packet["goal_status_refresh"]["runtime_dry_run_audit_passed"] is True
    assert packet["source_readiness_fallback"] == {
        "enabled": True,
        "status": "source_unavailable",
        "output_json": str(tmp_path / "owner-console-source-readiness.json"),
        "reason": "operator_cookie_unavailable",
        "goal_status_included": True,
    }
    assert "operator_cookie_unavailable:RuntimeError" in packet["blockers"]
    assert (
        "owner-console-source-readiness.json:refresh_skipped:"
        "operator_cookie_unavailable"
    ) in packet["blockers"]
    assert (tmp_path / "runtime-dry-run-audit-chain.json").exists()
    assert (tmp_path / "strategygroup-runtime-goal-status.json").exists()
    source_readiness = json.loads(
        (tmp_path / "owner-console-source-readiness.json").read_text(
            encoding="utf-8"
        )
    )
    assert source_readiness["status"] == "source_unavailable"
    assert source_readiness["owner_state"]["status"] == "temporarily_unavailable"
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
    assert source_readiness["raw_status_refs"]["tokyo_deploy_channel_blockers"] == [
        "tokyo_ssh_publickey_denied"
    ]
    assert source_readiness["safety_invariants"]["fallback_packet_only"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["optional_source_readiness_fallback"] is True


def test_cli_can_treat_degraded_local_refresh_as_continuable(
    tmp_path,
    monkeypatch,
    capsys,
):
    def missing_cookie():
        raise RuntimeError("operator auth missing")

    monkeypatch.setattr(refresh_script, "_operator_cookie", missing_cookie)

    output_json = tmp_path / "product-state-refresh-packet.json"
    exit_code = refresh_script.main(
        [
            "--output-dir",
            str(tmp_path),
            "--output-json",
            str(output_json),
            "--refresh-dry-run-audit-chain",
            "--refresh-goal-status",
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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["cli_exit_policy"] == packet["cli_exit_policy"]
    assert packet["status"] == "refresh_blocked"
    assert packet["cli_exit_policy"] == {
        "status": "degraded_local_refresh_continuable",
        "exit_code": 0,
        "reason": "operator_cookie_unavailable_with_local_audit_refresh_complete",
    }
    assert packet["dry_run_audit_refresh"]["status"] == "passed"
    assert packet["dry_run_audit_refresh"]["scenario_count"] == 13
    assert packet["goal_status_refresh"]["runtime_dry_run_audit_passed"] is True
    assert packet["source_readiness_fallback"]["reason"] == (
        "operator_cookie_unavailable"
    )
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["places_order"] is False


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
            "--refresh-goal-status",
            "--selected-strategy-group-id",
            "MPG-001",
            "--max-symbols",
            "3",
            "--stale-after-seconds",
            "180",
        ]
    )

    assert exit_code == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["status"] == "refresh_blocked"
    assert "cli_exit_policy" not in packet
    assert packet["dry_run_audit_refresh"]["status"] == "passed"
    assert packet["goal_status_refresh"]["runtime_dry_run_audit_passed"] is True
