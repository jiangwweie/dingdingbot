from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import runtime_signal_watcher_tick


def _args(tmp_path: Path, **overrides):
    defaults = {
        "output_dir": str(tmp_path / "watcher"),
        "state_json": None,
        "env_file": None,
        "api_base": "http://127.0.0.1:18080",
        "source": "sample",
        "strategy_source": "sample",
        "runtime_instance_id": [],
        "max_iterations": 1,
        "loop_interval_seconds": 0.0,
        "cycle_timeout_seconds": 0.0,
        "status_stale_after_seconds": 900.0,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "allow_prepare_records": False,
        "include_packets": False,
        "notify_no_signal": False,
        "notification_dry_run": False,
        "notification_timeout_seconds": 1.0,
        "feishu_webhook_url": None,
        "feishu_webhook_secret": None,
        "label": "unit-test",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _summary(status: str = "waiting_for_signal", *, ready: bool = False) -> dict:
    return {
        "iteration": 1,
        "cycle_dir": "cycle-1",
        "status": status,
        "active_runtime_count": 1,
        "monitored_runtime_count": 1,
        "prepare_records_created": ready,
        "shadow_candidate_created": ready,
        "runtime_execution_intent_draft_created": ready,
        "recorded_execution_intent_created": ready,
        "submit_authorization_created": ready,
        "protection_plan_created": ready,
        "executable_execution_intent_created": False,
        "ready_for_final_gate_preflight": status == "ready_for_final_gate_preflight",
        "creates_shadow_candidate": ready,
        "creates_execution_intent": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "blockers": [] if ready else ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": [],
        "prepared_authorization_id": "auth-ready-1" if ready else None,
        "runtime_signal_summaries": [
            {
                "runtime_instance_id": "runtime-1",
                "strategy_family_id": "CPM-001",
                "strategy_family_version_id": "CPM-001-v0",
                "symbol": "BNB/USDT:USDT",
                "side": "long",
                "status": status,
                "signal_summary": {
                    "evaluation_status": "ready" if ready else "observe_only",
                    "signal_type": "would_enter" if ready else "no_action",
                    "side": "long" if ready else None,
                    "confidence": "0.81" if ready else None,
                    "reason_codes": ["ready"] if ready else ["no_signal"],
                    "human_summary": "ready" if ready else "no signal",
                },
            }
        ],
    }


def _fake_supervisor(output_status: str, *, ready: bool = False):
    def builder(args):
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        latest = _summary(output_status, ready=ready)
        loop = {
            "scope": "runtime_active_observation_loop",
            "status": output_status,
            "stop_reason": (
                f"status_changed:{output_status}"
                if ready
                else "max_iterations_exhausted"
            ),
            "iterations_requested": 1,
            "iterations_completed": 1,
            "latest_summary": latest,
            "cycle_summaries": [latest],
            "blockers": latest["blockers"],
            "warnings": [],
            "operator_command_plan": {
                "not_executed": True,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "monitor_loop_only": True,
                "prepare_records_created": ready,
                "shadow_candidate_created": ready,
                "runtime_execution_intent_draft_created": ready,
                "recorded_execution_intent_created": ready,
                "submit_authorization_created": ready,
                "protection_plan_created": ready,
                "executable_execution_intent_created": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }
        (output_dir / "loop-packet.json").write_text(json.dumps(loop), encoding="utf-8")
        (output_dir / "latest-summary.json").write_text(
            json.dumps(latest), encoding="utf-8"
        )
        (output_dir / "latest-status.txt").write_text(output_status + "\n", encoding="utf-8")
        return {
            "scope": "runtime_active_observation_supervisor",
            "status": "supervisor_completed",
            "blockers": [],
            "warnings": [],
            "safety_invariants": {"forbidden_effects": []},
        }

    return builder


def test_watcher_tick_writes_packets_without_notifying_on_no_signal(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_packet_from_path",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_packet",
            "status": "observation_running_no_signal",
            "active_runtime_observation": {
                "active_runtime_count": 1,
                "latest_iteration": 1,
                "iterations_completed": 1,
                "iterations_remaining": 0,
                "stop_reason": "max_iterations_exhausted",
            },
            "signal_counts": {
                "runtime_ready_signal_count": 0,
                "strategy_group_would_enter_signal_count": 0,
                "strategy_group_no_action_signal_count": 1,
            },
            "runtime_prepare_context": {},
            "operator_command_plan": {
                "next_step": "continue_active_runtime_observation",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_packet_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("waiting_for_signal"),
        notifier=lambda *items: sent.append(items) or {"sent": True, "status_code": 200},
    )

    assert packet["status"] == "watching_no_signal"
    assert packet["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert packet["post_signal_auto_resume"]["blocked_reason"] == "no_fresh_strategy_signal"
    assert packet["operator_command_plan"]["next_step"] == "continue_watcher_observation"
    assert packet["operator_command_plan"]["can_continue_without_owner_chat"] is True
    assert packet["operator_command_plan"]["requires_action_time_final_gate"] is True
    assert packet["operator_command_plan"]["requires_official_operation_layer"] is True
    assert packet["notification"]["required"] is False
    assert packet["notification"]["reason"] == (
        "waiting_for_market_no_owner_attention_needed"
    )
    assert sent == []
    assert (tmp_path / "watcher" / "latest-status.json").exists()
    assert (tmp_path / "watcher" / "operator-packet.json").exists()
    assert (tmp_path / "watcher" / "wakeup-packet.json").exists()
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_watcher_tick_does_not_notify_when_operator_packet_needs_review_but_waiting_for_market(
    tmp_path,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_packet_from_path",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_packet",
            "status": "strategy_group_signal_review_available",
            "active_runtime_observation": {
                "active_runtime_count": 6,
                "monitored_runtime_count": 3,
                "latest_iteration": 1,
                "iterations_completed": 1,
                "iterations_remaining": 0,
                "stop_reason": "max_iterations_exhausted",
            },
            "signal_counts": {
                "runtime_ready_signal_count": 0,
                "strategy_group_would_enter_signal_count": 1,
                "strategy_group_no_action_signal_count": 7,
            },
            "runtime_prepare_context": {},
            "operator_command_plan": {
                "next_step": "review_strategy_group_would_enter_without_execution",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_packet_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("waiting_for_signal"),
        notifier=lambda *items: sent.append(items) or {"sent": True, "status_code": 200},
    )

    assert packet["wakeup_status"] == "operator_packet_needs_review"
    assert packet["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert packet["notification"]["required"] is False
    assert packet["notification"]["reason"] == (
        "waiting_for_market_no_owner_attention_needed"
    )
    assert sent == []


def test_watcher_tick_sends_feishu_on_ready_signal(tmp_path):
    calls = []

    def notifier(webhook_url, webhook_secret, body, timeout):
        calls.append((webhook_url, webhook_secret, body, timeout))
        return {"sent": True, "status_code": 200, "response_body_preview": "ok"}

    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(
            tmp_path,
            feishu_webhook_url="https://example.test/hook",
            feishu_webhook_secret="secret-value",
        ),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=notifier,
    )

    assert packet["status"] == "owner_notified"
    assert packet["wakeup_status"] == "prepared_shadow_evidence_ready_for_owner_review"
    assert packet["post_signal_auto_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert packet["post_signal_auto_resume"]["can_continue_without_owner_chat"] is True
    assert packet["post_signal_auto_resume"]["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["notification"]["sent"] is True
    assert calls[0][0] == "https://example.test/hook"
    assert calls[0][1] == "secret-value"
    assert "monitored runtimes: 1" in calls[0][2]["text"]
    assert "auth-ready-1" in calls[0][2]["text"]
    assert "secret-value" not in json.dumps(packet)


def test_watcher_tick_suppresses_duplicate_ready_event(tmp_path):
    first = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )
    assert first["notification"]["sent"] is True

    calls = []
    second = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: calls.append(items) or {"sent": True, "status_code": 200},
    )

    assert second["notification"]["duplicate_suppressed"] is True
    assert second["notification"]["skipped_reason"] == "event_already_notified"
    assert calls == []


def test_watcher_tick_reuses_feishu_webhook_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BRC_SIGNAL_WATCHER_FEISHU_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "\n".join(
            [
                "TRADING_ENV=live",
                "FEISHU_WEBHOOK_URL='https://example.test/from-env-file'",
                "FEISHU_WEBHOOK_SECRET='env-file-secret'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, env_file=str(env_file)),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: calls.append(items) or {"sent": True, "status_code": 200},
    )

    assert packet["status"] == "owner_notified"
    assert packet["notification"]["configured"] is True
    assert packet["notification"]["secret_configured"] is True
    assert calls[0][0] == "https://example.test/from-env-file"
    assert calls[0][1] == "env-file-secret"
    assert "env-file-secret" not in json.dumps(packet)


def test_watcher_tick_auto_resume_can_stop_at_non_executing_prepare_checkpoint(tmp_path):
    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=False),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert packet["post_signal_auto_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert packet["post_signal_auto_resume"]["blocked_reason"] == (
        "fresh_strategy_signal_ready"
    )
    assert packet["post_signal_auto_resume"]["automatic_recovery_action"] == (
        "rerun_watcher_tick_with_allow_prepare_records"
    )
    assert packet["operator_command_plan"]["can_continue_without_owner_chat"] is True
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_order_lifecycle"] is False


def test_watcher_tick_auto_resume_reaches_final_gate_checkpoint_after_prepare_records(tmp_path):
    packet = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(
            tmp_path,
            allow_prepare_records=True,
            feishu_webhook_url="https://example.test/hook",
        ),
        supervisor_builder=_fake_supervisor(
            "ready_for_final_gate_preflight",
            ready=True,
        ),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert packet["post_signal_auto_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert packet["post_signal_auto_resume"]["prepared_authorization_id"] == (
        "auth-ready-1"
    )
    assert packet["post_signal_auto_resume"]["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["operator_command_plan"]["next_step"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["operator_command_plan"]["creates_prepare_records"] is True
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is True
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_order_lifecycle"] is False
    assert packet["safety_invariants"]["post_signal_auto_resume_decision_only"] is False
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"][
        "runtime_execution_intent_draft_created"
    ] is True
    assert packet["safety_invariants"]["recorded_execution_intent_created"] is True
    assert packet["safety_invariants"]["submit_authorization_created"] is True
    assert packet["safety_invariants"]["protection_plan_created"] is True
    assert packet["safety_invariants"]["allowed_prepare_record_effects"] == [
        "prepare_records_created",
        "shadow_candidate_created",
        "runtime_execution_intent_draft_created",
        "recorded_execution_intent_created",
        "submit_authorization_created",
        "protection_plan_created",
    ]
    assert packet["safety_invariants"]["real_submit_requested"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_notification_dry_run_does_not_mark_event_as_notified(tmp_path):
    first = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(
            tmp_path,
            feishu_webhook_url="https://example.test/hook",
            notification_dry_run=True,
        ),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
    )
    assert first["notification"]["skipped_reason"] == "notification_dry_run"

    calls = []
    second = runtime_signal_watcher_tick.build_watcher_tick_packet(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: calls.append(items) or {"sent": True, "status_code": 200},
    )

    assert second["notification"]["duplicate_suppressed"] is False
    assert second["notification"]["sent"] is True
    assert calls


def test_feishu_text_body_supports_signed_custom_bot_payload():
    body = runtime_signal_watcher_tick._feishu_text_body("hello", secret="top-secret")

    assert body["msg_type"] == "text"
    assert body["content"] == {"text": "hello"}
    assert body["timestamp"]
    assert body["sign"]
    assert "top-secret" not in json.dumps(body)
