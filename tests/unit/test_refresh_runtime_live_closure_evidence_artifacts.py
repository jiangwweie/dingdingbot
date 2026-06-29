from __future__ import annotations

import json

from scripts import refresh_runtime_live_closure_evidence_artifacts as refresher


BOUNDARY_FIELDS = {
    "strategy_group_id": "MPG-001",
    "runtime_profile_id": "owner-runtime-console-v1",
    "subaccount_id": "tokyo-runtime-subaccount",
    "symbol": "MSTR/USDT:USDT",
    "side": "long",
    "notional": "100",
    "leverage": "1",
}


def _official_complete_sources() -> list[dict]:
    return [
        {
            "scope": "runtime_signal_watcher_live_signal",
            "status": "fresh_signal_ready",
            "signal_packet_id": "live-signal-packet-1",
            **BOUNDARY_FIELDS,
        },
        {
            "scope": "strategy_group_live_facts_readiness",
            "status": "ready",
            "signal_packet_id": "live-signal-packet-1",
            "required_facts_readiness_artifact_id": "facts-ready-1",
            **BOUNDARY_FIELDS,
        },
        {
            "scope": "official_entry_chain",
            "status": "official_operation_layer_submit_ready",
            "ids": {
                "signal_packet_id": "live-signal-packet-1",
                "order_candidate_id": "candidate-1",
                "runtime_grant_id": "runtime-grant-1",
                "fresh_submit_authorization_id": "fresh-auth-1",
                "action_time_finalgate_packet_id": "finalgate-1",
                "operation_layer_submit_authorization_id": "op-auth-1",
                "exchange_submit_execution_result_id": "exchange-result-1",
                "exchange_native_hard_stop_order_id": "hard-stop-1",
            },
            **BOUNDARY_FIELDS,
            "safety_invariants": {
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_submit_accepted": True,
                "exchange_native_protection": True,
                "hard_stop_accepted": True,
                "reduce_only": True,
            },
            "exchange_order_id": "entry-order-1",
        },
        {
            "scope": "official_post_submit_close_loop",
            "status": "settled",
            "ids": {
                "exchange_submit_execution_result_id": "exchange-result-1",
                "post_submit_finalize_payload_id": "finalize-1",
                "post_submit_reconciliation_evidence_id": "reconcile-1",
                "post_submit_budget_settlement_id": "settlement-1",
                "submit_outcome_review_id": "review-1",
            },
            **BOUNDARY_FIELDS,
            "post_submit_finalize_complete": True,
            "post_submit_reconciliation_matched": True,
            "post_submit_budget_settled": True,
            "submit_outcome_review_recorded": True,
        },
    ]


def _write_json(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_refresh_live_closure_evidence_artifacts_writes_complete_outputs(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    for index, source in enumerate(_official_complete_sources(), start=1):
        _write_json(report_dir / f"source-{index}.json", source)
    _write_json(
        report_dir / "runtime-dry-run-audit-chain.json",
        {
            "scope": "runtime_dry_run_audit_chain",
            "status": "dry_run_passed",
            "exchange_submit_execution_result_id": "dry-result-1",
        },
    )

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    evidence = json.loads(
        (report_dir / refresher.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    verification = json.loads(
        (report_dir / refresher.VERIFICATION_FILENAME).read_text(encoding="utf-8")
    )
    persisted_refresh = json.loads(
        (report_dir / refresher.REFRESH_FILENAME).read_text(encoding="utf-8")
    )
    assert refresh["status"] == "live_closure_refresh_complete"
    assert persisted_refresh["status"] == "live_closure_refresh_complete"
    assert refresh["source_counts"] == {
        "discovered_json": 5,
        "included_json": 4,
        "skipped_json": 1,
        "read_errors": 0,
    }
    assert evidence["official_live_closure_evidence"] is True
    assert evidence["missing_evidence_keys"] == []
    assert evidence["reject_reasons"] == []
    assert verification["status"] == "live_closure_complete"
    assert verification["completion"]["first_bounded_real_order_complete"] is True
    assert refresh["safety_invariants"]["exchange_write_called"] is False


def test_refresh_keeps_partial_live_closure_evidence_in_progress(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    for index, source in enumerate(_official_complete_sources()[:2], start=1):
        _write_json(report_dir / f"source-{index}.json", source)

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    verification = json.loads(
        (report_dir / refresher.VERIFICATION_FILENAME).read_text(encoding="utf-8")
    )
    assert refresh["status"] == "live_closure_refresh_in_progress"
    assert verification["status"] == "live_closure_in_progress"
    assert verification["first_incomplete_stage"] == "candidate_authorization_bound"


def test_refresh_writes_not_started_when_only_non_live_sources_exist(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    _write_json(
        report_dir / "runtime-dry-run-audit-chain.json",
        {
            "scope": "runtime_dry_run_audit_chain",
            "status": "dry_run_passed",
            "signal_packet_id": "mock-signal-1",
        },
    )

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    verification = json.loads(
        (report_dir / refresher.VERIFICATION_FILENAME).read_text(encoding="utf-8")
    )
    assert refresh["status"] == "live_closure_refresh_not_started"
    assert refresh["source_counts"]["included_json"] == 0
    assert refresh["source_counts"]["skipped_json"] == 1
    assert verification["status"] == "live_closure_not_started"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_refresh_skips_passive_runtime_reports_with_sample_or_stale_ids(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    _write_json(
        report_dir / "main-control-handoff.json",
        {
            "scope": "strategy_group_intake_main_control_projection",
            "status": "ready_for_main_control_intake",
            "strategy_group_id": "MI-001",
            "candidate_id": "MI-001-SOL-LONG",
            "symbol": "SOL/USDT:USDT",
            "side": "long",
        },
    )
    _write_json(
        report_dir / "post-signal-resume-pack.json",
        {
            "scope": "runtime_signal_watcher_post_signal_resume_pack",
            "status": "waiting_for_market",
            "signal_packet_id": "runtime-signal-input:old",
            "authorization_id": "runtime-submit-authorization-intent_old",
        },
    )
    _write_json(
        report_dir / "strategygroup-runtime-goal-status.json",
        {
            "scope": "strategygroup_runtime_goal_status",
            "status": "fresh_signal_processing",
            "checks": {"fresh_signal_present": True},
            "ready_for_real_order_action": False,
        },
    )

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    evidence = json.loads(
        (report_dir / refresher.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    verification = json.loads(
        (report_dir / refresher.VERIFICATION_FILENAME).read_text(encoding="utf-8")
    )
    assert refresh["status"] == "live_closure_refresh_not_started"
    assert refresh["source_counts"] == {
        "discovered_json": 3,
        "included_json": 0,
        "skipped_json": 3,
        "read_errors": 0,
    }
    assert evidence["present_evidence_keys"] == []
    assert evidence["reject_reasons"] == []
    assert verification["status"] == "live_closure_not_started"


def test_refresh_tolerates_malformed_legacy_json_by_default(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "reconciliation-refresh-old.json").write_text(
        "INFO not json",
        encoding="utf-8",
    )

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    assert refresh["status"] == "live_closure_refresh_not_started"
    assert refresh["source_counts"] == {
        "discovered_json": 1,
        "included_json": 0,
        "skipped_json": 0,
        "read_errors": 1,
    }
    assert refresh["read_errors"][0]["path"].endswith(
        "reconciliation-refresh-old.json"
    )


def test_refresh_can_strictly_block_on_malformed_json(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "reconciliation-refresh-old.json").write_text(
        "INFO not json",
        encoding="utf-8",
    )

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        strict_read_errors=True,
        generated_at_ms=1781755000000,
    )

    assert refresh["status"] == "live_closure_refresh_read_error"
    assert refresh["strict_read_errors"] is True


def test_refresh_rejects_exchange_result_without_live_submit_markers(tmp_path):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    sources = _official_complete_sources()
    sources[2]["safety_invariants"] = {}
    for index, source in enumerate(sources, start=1):
        _write_json(report_dir / f"source-{index}.json", source)

    refresh = refresher.build_refresh_report(
        report_dir=report_dir,
        generated_at_ms=1781755000000,
    )

    verification = json.loads(
        (report_dir / refresher.VERIFICATION_FILENAME).read_text(encoding="utf-8")
    )
    assert refresh["status"] == "live_closure_refresh_rejected"
    assert "live_exchange_not_called" in refresh["verification"]["reject_reasons"]
    assert "real_order_not_placed" in refresh["verification"]["reject_reasons"]
    assert verification["status"] == "blocked_live_closure_rejected"


def test_refresh_cli_writes_refresh_report(tmp_path, capsys):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    for index, source in enumerate(_official_complete_sources(), start=1):
        _write_json(report_dir / f"source-{index}.json", source)

    assert refresher.main(["--report-dir", str(report_dir)]) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    artifact = json.loads(
        (report_dir / refresher.REFRESH_FILENAME).read_text(encoding="utf-8")
    )
    assert artifact["status"] == "live_closure_refresh_complete"
