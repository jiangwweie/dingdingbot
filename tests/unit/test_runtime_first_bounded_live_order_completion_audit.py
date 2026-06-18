from __future__ import annotations

import json

from scripts import runtime_first_bounded_live_order_completion_audit as script


def _daily_check(**overrides):
    base = {
        "schema": 12,
        "status": "waiting_for_market",
        "current_read_interaction": {
            "level": "L0_local_cache_read",
            "remote_interaction_count": 0,
        },
        "checks": {"fresh_signal_notification_policy_checked": True},
        "notification": {"decision": "DONT_NOTIFY"},
    }
    base.update(overrides)
    return base


def _goal_progress(**overrides):
    base = {
        "schema": "brc.strategygroup_runtime_goal_progress_audit.v1",
        "status": "waiting_for_market",
        "interaction": {"remote_interaction_count": 0},
        "completion_boundary": {
            "goal_complete": False,
            "first_bounded_real_order_complete": False,
            "real_order_closure_proven": False,
        },
        "live_closure_evidence_boundary": {"status": "not_generated"},
    }
    base.update(overrides)
    return base


def _dry_run_audit(**overrides):
    checks = {
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": True,
        "disabled_smoke_not_real_execution_proof": True,
        "expanded_watcher_scope_execution_guard_checked": True,
        "fresh_signal_fast_auto_chain_checked": True,
        "non_executing_prepare_auto_bridge_checked": True,
        "only_mpg_tiny_real_order_eligible_checked": True,
        "allocated_subaccount_profile_boundary_checked": True,
        "operation_layer_authorization_chain_guard_checked": True,
        "operation_layer_blocker_review_policy_checked": True,
        "operation_layer_evidence_relay_checked": True,
        "operation_layer_hard_safety_blocker_matrix_checked": True,
        "post_submit_closed_loop_evidence_guard_checked": True,
        "post_submit_exit_outcome_matrix_checked": True,
        "post_submit_finalize_result_identity_guard_checked": True,
        "reduce_only_recovery_standing_authorization_checked": True,
        "required_facts_readiness_checked": True,
        "scoped_pipeline_operation_layer_handoff_checked": True,
        "selected_strategygroup_dispatch_guard_checked": True,
        "strategygroup_adapter_boundary_checked": True,
    }
    base = {
        "schema": "brc.runtime_dry_run_audit_chain.v1",
        "status": "passed",
        "checks": checks,
        "summary": dict(checks),
    }
    base.update(overrides)
    return base


def _live_cutover(**overrides):
    base = {
        "schema": "brc.runtime_live_cutover_readiness.v1",
        "status": "live_cutover_waiting_for_fresh_signal",
        "selected_strategy_group_id": "MPG-001",
        "first_live_lane": "selected_strategygroup_allocated_subaccount",
        "next_fresh_signal_cutover_ready": True,
        "current_real_submit_allowed": False,
        "current_real_submit_blocker": "no_live_fresh_signal_in_this_local_packet",
        "sections": [
            {"name": "strategy_scope", "status": "ready"},
            {"name": "entry_fast_chain", "status": "ready"},
            {"name": "operation_layer_relay", "status": "ready"},
            {"name": "hard_blocker_policy", "status": "ready"},
            {"name": "exit_protection_recovery", "status": "ready"},
            {"name": "post_submit_close_loop", "status": "ready"},
            {"name": "dry_run_safety", "status": "ready"},
        ],
        "live_closure_cutover_contract": {
            "required_evidence_keys": [
                "operation_layer_submit_authorization_id",
                "exchange_native_hard_stop_order_id",
            ],
            "checks": {
                "live_closure_contract_rejects_synthetic_signal": True,
                "live_closure_contract_rejects_disabled_smoke": True,
                "live_closure_contract_requires_exchange_acceptance": True,
                "live_closure_contract_requires_live_submit_truth": True,
                "live_closure_contract_requires_exchange_native_protection": True,
            },
        },
    }
    base.update(overrides)
    return base


def _input_sources(**overrides):
    base = {
        "daily_check": {
            "exists": True,
            "path": "/tmp/latest-daily-check.json",
            "schema": 12,
            "status": "waiting_for_market",
        },
        "goal_progress": {
            "exists": True,
            "path": "/tmp/latest-goal-progress.json",
            "schema": "brc.strategygroup_runtime_goal_progress_audit.v1",
            "status": "waiting_for_market",
        },
        "dry_run_audit": {
            "exists": True,
            "path": "/tmp/latest-runtime-dry-run-audit-chain.json",
            "schema": "brc.runtime_dry_run_audit_chain.v1",
            "status": "passed",
        },
        "live_cutover": {
            "exists": True,
            "path": "/tmp/latest-live-cutover-readiness.json",
            "schema": "brc.runtime_live_cutover_readiness.v1",
            "status": "live_cutover_waiting_for_fresh_signal",
        },
    }
    base.update(overrides)
    return base


def test_completion_audit_waits_for_market_with_no_non_market_gaps():
    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "not_complete_waiting_for_market"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == []
    assert report["input_source_gaps"] == []
    assert report["market_dependent_remaining"] == [
        "fresh signal -> RequiredFacts -> candidate/auth fast chain",
        "candidate/auth -> action-time FinalGate -> official Operation Layer evidence relay",
        "real submit must happen only through official Operation Layer",
        "entry accepted -> exchange-native hard stop/protection/recovery",
        "post-submit finalize / reconciliation / budget settlement / review closure",
    ]
    assert report["interaction"]["level"] == "L0_local_completion_audit"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["max_remote_interactions"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["interaction"]["calls_finalgate"] is False
    assert report["interaction"]["calls_operation_layer"] is False
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["interaction"]["places_order"] is False
    assert report["safety_invariants"] == {
        "approaches_real_order": False,
        "calls_exchange_write": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "places_order": False,
        "server_files_mutated": False,
        "withdrawal_or_transfer_created": False,
    }
    assert all(
        not item["missing_or_false_non_market_evidence"]
        for item in report["items"]
        if item["status"].startswith("ready")
    )


def test_completion_audit_default_daily_check_uses_current_schema_packet():
    assert script.DEFAULT_DAILY_CHECK_JSON.name == "latest-daily-check.json"
    assert "cache-only" not in str(script.DEFAULT_DAILY_CHECK_JSON)


def test_completion_audit_reports_non_market_gap():
    dry_run = _dry_run_audit()
    dry_run["checks"]["operation_layer_evidence_relay_checked"] = False
    dry_run["summary"]["operation_layer_evidence_relay_checked"] = False

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=dry_run,
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == [
        {
            "requirement": (
                "candidate/auth -> action-time FinalGate -> official Operation "
                "Layer evidence relay"
            ),
            "missing_or_false": ["operation_layer_evidence_relay_checked"],
        }
    ]


def test_completion_audit_reports_missing_input_source_schema_gap():
    input_sources = _input_sources(
        goal_progress={
            "exists": True,
            "path": "/tmp/latest-goal-progress.json",
            "status": "waiting_for_market",
        }
    )

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        input_sources=input_sources,
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["input_source_gaps"] == ["goal_progress:schema"]
    assert report["non_market_gaps"] == [
        {
            "requirement": "P0 completion audit input sources are traceable",
            "missing_or_false": ["goal_progress:schema"],
        }
    ]


def test_completion_audit_reports_missing_input_source_gap():
    input_sources = _input_sources()
    input_sources.pop("live_cutover")

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        input_sources=input_sources,
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["input_source_gaps"] == ["live_cutover:missing_source"]
    assert report["non_market_gaps"] == [
        {
            "requirement": "P0 completion audit input sources are traceable",
            "missing_or_false": ["live_cutover:missing_source"],
        }
    ]


def test_completion_audit_rejects_goal_progress_older_than_daily_check():
    input_sources = _input_sources(
        daily_check={
            "exists": True,
            "generated_at_utc": "2026-06-18T09:10:00+00:00",
            "path": "/tmp/latest-daily-check.json",
            "schema": 12,
            "status": "waiting_for_market",
        },
        goal_progress={
            "exists": True,
            "generated_at_utc": "2026-06-18T09:09:59+00:00",
            "path": "/tmp/latest-goal-progress.json",
            "schema": "brc.strategygroup_runtime_goal_progress_audit.v1",
            "status": "waiting_for_market",
        },
    )

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        input_sources=input_sources,
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["input_source_gaps"] == [
        "goal_progress:generated_before_daily_check"
    ]
    assert report["non_market_gaps"] == [
        {
            "requirement": "P0 completion audit input sources are traceable",
            "missing_or_false": [
                "goal_progress:generated_before_daily_check"
            ],
        }
    ]


def test_completion_audit_requires_live_submit_truth_contract_check():
    live_cutover = _live_cutover()
    live_cutover["live_closure_cutover_contract"]["checks"].pop(
        "live_closure_contract_requires_live_submit_truth"
    )

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=live_cutover,
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["non_market_gaps"] == [
        {
            "requirement": "live closure complete requires explicit live submit proof",
            "missing_or_false": [
                "live_closure_contract_requires_live_submit_truth"
            ],
        }
    ]


def test_completion_audit_requires_allocated_subaccount_boundary():
    dry_run = _dry_run_audit()
    dry_run["checks"]["allocated_subaccount_profile_boundary_checked"] = False
    dry_run["summary"]["allocated_subaccount_profile_boundary_checked"] = False

    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(),
        dry_run_audit=dry_run,
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["non_market_gaps"] == [
        {
            "requirement": "selected StrategyGroup and allocated subaccount boundary",
            "missing_or_false": ["allocated_subaccount_profile_boundary_checked"],
        }
    ]


def test_completion_audit_requires_fresh_signal_notification_policy_check():
    daily_check = _daily_check(checks={})

    report = script.build_completion_audit_report(
        daily_check=daily_check,
        goal_progress=_goal_progress(),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["non_market_gaps"] == [
        {
            "requirement": (
                "low-noise monitor stays quiet when healthy waiting and wakes on "
                "fresh signal"
            ),
            "missing_or_false": ["fresh_signal_notification_policy_checked"],
        }
    ]


def test_completion_audit_can_mark_live_closure_complete():
    live_closure = {
        "status": "complete",
        "first_bounded_real_order_complete": True,
        "real_order_closure_proven": True,
        "completed_stage_count": 9,
        "stage_count": 9,
        "missing_evidence_keys": [],
        "reject_reasons": [],
    }
    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(
            completion_boundary={
                "goal_complete": True,
                "first_bounded_real_order_complete": True,
                "real_order_closure_proven": True,
            },
            live_closure_evidence_boundary=live_closure,
        ),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "complete"
    assert report["goal_complete"] is True
    assert report["non_market_gaps"] == []
    assert report["market_dependent_remaining"] == []


def test_completion_audit_rejects_weak_complete_live_closure_boundary():
    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(
            completion_boundary={
                "goal_complete": True,
                "first_bounded_real_order_complete": True,
                "real_order_closure_proven": True,
            },
            live_closure_evidence_boundary={"status": "complete"},
        ),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == [
        {
            "requirement": "official live closure evidence boundary proves completion",
            "missing_or_false": ["live_closure_evidence_boundary_complete"],
        }
    ]


def test_completion_audit_rejects_completion_flags_without_live_closure_boundary():
    report = script.build_completion_audit_report(
        daily_check=_daily_check(),
        goal_progress=_goal_progress(
            completion_boundary={
                "goal_complete": True,
                "first_bounded_real_order_complete": True,
                "real_order_closure_proven": True,
            },
            live_closure_evidence_boundary={"status": "not_generated"},
        ),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == [
        {
            "requirement": "official live closure evidence boundary proves completion",
            "missing_or_false": ["live_closure_evidence_boundary_complete"],
        }
    ]


def test_completion_audit_marks_live_closure_in_progress_as_runtime_processing():
    report = script.build_completion_audit_report(
        daily_check=_daily_check(status="ready"),
        goal_progress=_goal_progress(
            live_closure_evidence_boundary={"status": "in_progress"},
        ),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "not_complete_runtime_processing"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == []
    assert report["market_dependent_remaining"]


def test_completion_audit_rejects_rejected_live_closure_evidence_boundary():
    report = script.build_completion_audit_report(
        daily_check=_daily_check(status="ready"),
        goal_progress=_goal_progress(
            live_closure_evidence_boundary={"status": "rejected"},
        ),
        dry_run_audit=_dry_run_audit(),
        live_cutover=_live_cutover(),
        generated_at_utc="2026-06-18T00:00:00+00:00",
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["goal_complete"] is False
    assert report["non_market_gaps"] == [
        {
            "requirement": "official live closure evidence boundary is usable",
            "missing_or_false": ["live_closure_evidence_boundary_rejected"],
        }
    ]


def test_completion_audit_cli_writes_outputs(tmp_path):
    daily = tmp_path / "daily.json"
    goal = tmp_path / "goal.json"
    dry = tmp_path / "dry.json"
    cutover = tmp_path / "cutover.json"
    output = tmp_path / "audit.json"
    owner = tmp_path / "audit.md"
    daily.write_text(
        json.dumps(
            _daily_check(
                schema=12,
                generated_at_utc="2026-06-18T08:00:00+00:00",
            )
        ),
        encoding="utf-8",
    )
    goal.write_text(json.dumps(_goal_progress()), encoding="utf-8")
    dry.write_text(json.dumps(_dry_run_audit()), encoding="utf-8")
    cutover.write_text(json.dumps(_live_cutover()), encoding="utf-8")

    exit_code = script.main(
        [
            "--daily-check-json",
            str(daily),
            "--goal-progress-json",
            str(goal),
            "--dry-run-audit-json",
            str(dry),
            "--live-cutover-json",
            str(cutover),
            "--output-json",
            str(output),
            "--output-owner-progress",
            str(owner),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output.read_text(encoding="utf-8"))
    owner_text = owner.read_text(encoding="utf-8")
    assert packet["status"] == "not_complete_waiting_for_market"
    assert packet["input_source_gaps"] == []
    assert packet["input_sources"]["daily_check"] == {
        "exists": True,
        "generated_at_ms": None,
        "generated_at_utc": "2026-06-18T08:00:00+00:00",
        "path": str(daily),
        "schema": 12,
        "scope": None,
        "source_expected_runtime_head": None,
        "source_runtime_head": None,
        "status": "waiting_for_market",
    }
    assert "- 非市场缺口: 无" in owner_text
    assert "- 交互等级: L0_local_completion_audit" in owner_text
    assert "- 远端交互次数: 0" in owner_text
    assert "- Exchange write: 否" in owner_text
    assert "- daily_check: status=waiting_for_market, schema=12" in owner_text
    assert "## Input Source Gaps" in owner_text


def test_completion_audit_cli_treats_runtime_processing_as_success(tmp_path):
    daily = tmp_path / "daily.json"
    goal = tmp_path / "goal.json"
    dry = tmp_path / "dry.json"
    cutover = tmp_path / "cutover.json"
    output = tmp_path / "audit.json"
    owner = tmp_path / "audit.md"
    daily.write_text(json.dumps(_daily_check(status="processing")), encoding="utf-8")
    goal.write_text(
        json.dumps(
            _goal_progress(
                live_closure_evidence_boundary={"status": "in_progress"},
            )
        ),
        encoding="utf-8",
    )
    dry.write_text(json.dumps(_dry_run_audit()), encoding="utf-8")
    cutover.write_text(json.dumps(_live_cutover()), encoding="utf-8")

    exit_code = script.main(
        [
            "--daily-check-json",
            str(daily),
            "--goal-progress-json",
            str(goal),
            "--dry-run-audit-json",
            str(dry),
            "--live-cutover-json",
            str(cutover),
            "--output-json",
            str(output),
            "--output-owner-progress",
            str(owner),
        ]
    )

    assert exit_code == 0
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert packet["status"] == "not_complete_runtime_processing"
