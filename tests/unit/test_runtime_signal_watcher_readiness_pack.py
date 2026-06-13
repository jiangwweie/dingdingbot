from __future__ import annotations

import json
from pathlib import Path

from scripts.build_runtime_signal_watcher_readiness_pack import build_pack


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_runtime_signal_watcher_readiness_pack_ready_for_resume(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_notified",
            "wakeup_status": "prepared_shadow_evidence_ready_for_owner_review",
            "operator_status": "strategy_group_signal_review_available",
            "status_packet_status": "ok",
            "notification": {
                "configured": True,
                "attempted": True,
                "sent": True,
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(report_dir / "wakeup-packet.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-packet.json", {"status": "strategy_group_signal_review_available"})
    _write(report_dir / "status-packet.json", {"status": "ok", "blockers": [], "warnings": []})
    _write(report_dir / "notification-state.json", {"last_notified_event_key": "ready-event"})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    deployment = json.loads((output_dir / "deployment-readiness-packet.json").read_text())
    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["deployment_status"] == "ready"
    assert summary["resume_status"] == "ready_for_steps_5_8"
    assert summary["can_continue_steps_5_8"] is True
    assert deployment["notification"]["duplicate_suppression_observed"] is True
    assert deployment["safety_invariants"]["exchange_write_called"] is False
    assert resume["can_continue_steps_5_8"] is True
    assert "action-time FinalGate" in resume["required_before_real_submit"]


def test_build_runtime_signal_watcher_readiness_pack_blocks_unsafe_effect(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_notified",
            "wakeup_status": "prepared_shadow_evidence_ready_for_owner_review",
            "operator_status": "strategy_group_signal_review_available",
            "notification": {"configured": True},
            "safety_invariants": {
                "exchange_write_called": True,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(report_dir / "wakeup-packet.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-packet.json", {"status": "strategy_group_signal_review_available"})
    _write(report_dir / "status-packet.json", {"status": "ok"})
    _write(report_dir / "notification-state.json", {})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["deployment_status"] == "unsafe_watcher_effect_detected"
    assert summary["can_continue_steps_5_8"] is False
    assert resume["status"] == "blocked"
    assert "exchange_write_called" in resume["blockers"]
