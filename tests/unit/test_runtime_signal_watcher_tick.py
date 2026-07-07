from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts import runtime_signal_watcher_tick


def _args(tmp_path: Path, **overrides):
    defaults = {
        "output_dir": str(tmp_path / "watcher"),
        "env_file": None,
        "api_base": "http://127.0.0.1:18080",
        "source": "sample",
        "strategy_source": "sample",
        "runtime_instance_id": [],
        "strategy_family_id": [],
        "database_url": "",
        "require_database_url": False,
        "allow_non_postgres_for_test": False,
        "max_iterations": 1,
        "loop_interval_seconds": 0.0,
        "cycle_timeout_seconds": 0.0,
        "status_stale_after_seconds": 900.0,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "allow_prepare_records": False,
        "allow_arm_preview": False,
        "allow_attempt_policy_prepare": False,
        "allow_disabled_smoke": False,
        "skip_disabled_smoke_prerequisite_probe": True,
        "include_artifacts": False,
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
        "pg_live_signal_events": (
            {
                "status": "pg_live_signal_events_written",
                "written_count": 1,
                "signal_event_ids": ["signal-unit-ready"],
            }
            if ready
            else {
                "status": "pg_live_signal_events_noop",
                "written_count": 0,
                "reason": "would_enter_signal_summary_missing",
            }
        ),
    }


def _fake_supervisor(output_status: str, *, ready: bool = False):
    def builder(args):
        output_dir = Path(args.output_dir)
        latest = _summary(output_status, ready=ready)
        loop = {
            "scope": "runtime_signal_watcher_in_memory_observation",
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
            "operator_review_plan": {
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
        artifact = {
            "scope": "runtime_signal_watcher_in_memory_supervisor",
            "status": "supervisor_completed",
            "blockers": [],
            "warnings": [],
            "loop_artifact": loop,
            "latest_summary": latest,
            "safety_invariants": {"forbidden_effects": []},
        }
        artifact["status_artifact"] = runtime_signal_watcher_tick._status_from_loop_artifact(
            output_dir=output_dir,
            supervisor_artifact=artifact,
            loop_artifact=loop,
            latest_summary=latest,
            stale_after_seconds=float(args.status_stale_after_seconds),
        )
        return artifact

    return builder


def _fake_supervisor_from_latest(latest: dict):
    def builder(args):
        output_dir = Path(args.output_dir)
        output_status = str(latest.get("status") or "waiting_for_signal")
        loop = {
            "scope": "runtime_signal_watcher_in_memory_observation",
            "status": output_status,
            "stop_reason": f"status_changed:{output_status}",
            "iterations_requested": 1,
            "iterations_completed": 1,
            "latest_summary": latest,
            "cycle_summaries": [latest],
            "blockers": latest.get("blockers") or [],
            "warnings": [],
            "operator_review_plan": {
                "not_executed": True,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "monitor_loop_only": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        }
        artifact = {
            "scope": "runtime_signal_watcher_in_memory_supervisor",
            "status": "supervisor_completed",
            "blockers": [],
            "warnings": [],
            "loop_artifact": loop,
            "latest_summary": latest,
            "safety_invariants": {"forbidden_effects": []},
        }
        artifact["status_artifact"] = runtime_signal_watcher_tick._status_from_loop_artifact(
            output_dir=output_dir,
            supervisor_artifact=artifact,
            loop_artifact=loop,
            latest_summary=latest,
            stale_after_seconds=float(args.status_stale_after_seconds),
        )
        return artifact

    return builder


def test_watcher_tick_uses_memory_refs_without_notifying_on_no_signal(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_evidence",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_evidence",
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
            "operator_review_plan": {
                "next_step": "continue_active_runtime_observation",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_evidence_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("waiting_for_signal"),
        notifier=lambda *items: sent.append(items) or {"sent": True, "status_code": 200},
    )

    assert artifact["status"] == "watching_no_signal"
    assert artifact["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert artifact["watcher_status_evidence_status"] == (
        "observation_window_complete_no_signal"
    )
    assert "status_packet_status" not in artifact
    assert artifact["post_signal_auto_resume"]["blocked_reason"] == "no_fresh_strategy_signal"
    assert "operator_command_plan" not in artifact
    assert "next_step" not in artifact["watcher_tick_plan"]
    assert artifact["watcher_tick_plan"]["non_authority_checkpoint"] == (
        "continue_watcher_observation"
    )
    assert artifact["watcher_tick_plan"]["not_execution_authority"] is True
    assert artifact["watcher_tick_plan"]["can_continue_without_owner_chat"] is True
    assert artifact["watcher_tick_plan"]["requires_action_time_final_gate"] is True
    assert artifact["watcher_tick_plan"]["requires_official_operation_layer"] is True
    assert artifact["notification"]["required"] is False
    assert artifact["notification"]["reason"] == (
        "waiting_for_market_no_owner_attention_needed"
    )
    assert sent == []
    assert not (tmp_path / "watcher" / "latest-status.json").exists()
    assert not (tmp_path / "watcher" / "notification-state.json").exists()
    assert not (tmp_path / "watcher" / "operator-evidence.json").exists()
    assert not (tmp_path / "watcher" / "wakeup-evidence.json").exists()
    assert artifact["paths"] == {
        "status_artifact_ref": "memory:runtime_signal_watcher_in_memory_status",
        "operator_evidence_ref": "memory:runtime_observation_operator_evidence",
        "wakeup_evidence_ref": "memory:runtime_observation_wakeup_evidence",
        "watcher_tick_ref": "stdout:runtime_signal_watcher_tick",
    }
    assert not (tmp_path / "watcher" / "supervisor-packet.json").exists()
    assert not (tmp_path / "watcher" / "operator-packet.json").exists()
    assert not (tmp_path / "watcher" / "wakeup-packet.json").exists()
    assert "legacy_operator_packet_json" not in artifact["paths"]
    assert "legacy_wakeup_packet_json" not in artifact["paths"]
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_lifecycle_called"] is False


def test_watcher_tick_passes_operation_layer_flags_to_supervisor(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_evidence",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_evidence",
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
            "operator_review_plan": {
                "next_step": "continue_active_runtime_observation",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_evidence_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    def supervisor_builder(args):
        captured["allow_arm_preview"] = args.allow_arm_preview
        captured["allow_attempt_policy_prepare"] = args.allow_attempt_policy_prepare
        captured["allow_disabled_smoke"] = args.allow_disabled_smoke
        captured["skip_disabled_smoke_prerequisite_probe"] = (
            args.skip_disabled_smoke_prerequisite_probe
        )
        return _fake_supervisor("waiting_for_signal")(args)

    runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(
            tmp_path,
            allow_arm_preview=True,
            allow_attempt_policy_prepare=True,
            allow_disabled_smoke=True,
            skip_disabled_smoke_prerequisite_probe=False,
        ),
        supervisor_builder=supervisor_builder,
    )

    assert captured == {
        "allow_arm_preview": True,
        "allow_attempt_policy_prepare": True,
        "allow_disabled_smoke": True,
        "skip_disabled_smoke_prerequisite_probe": False,
    }


def test_watcher_tick_cli_rejects_candidate_universe_json(tmp_path):
    with pytest.raises(SystemExit) as exc:
        runtime_signal_watcher_tick._parse_args(
            [
                "--output-dir",
                str(tmp_path / "watcher"),
                "--candidate-universe-json",
                "/srv/current/latest-strategy-live-candidate-pool.json",
            ]
        )

    assert exc.value.code == 2


def test_watcher_tick_cli_rejects_local_file_diagnostic_flag(tmp_path):
    with pytest.raises(SystemExit) as exc:
        runtime_signal_watcher_tick._parse_args(
            [
                "--output-dir",
                str(tmp_path / "watcher"),
                "--allow-local-file-diagnostic",
            ]
        )

    assert exc.value.code == 2


def test_watcher_tick_passes_pg_candidate_scope_flags_to_supervisor(
    tmp_path,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_evidence",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_evidence",
            "status": "observation_running_no_signal",
            "active_runtime_observation": {},
            "signal_counts": {},
            "runtime_prepare_context": {},
            "operator_review_plan": {
                "next_step": "continue_active_runtime_observation",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_evidence_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    def supervisor_builder(args):
        captured["database_url"] = args.database_url
        captured["require_database_url"] = args.require_database_url
        captured["has_candidate_universe_json"] = hasattr(args, "candidate_universe_json")
        captured["has_allow_local_file_diagnostic"] = hasattr(
            args,
            "allow_local_file_diagnostic",
        )
        return _fake_supervisor("waiting_for_signal")(args)

    runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(
            tmp_path,
            database_url="postgresql://unit/runtime",
            require_database_url=True,
        ),
        supervisor_builder=supervisor_builder,
    )

    assert captured == {
        "database_url": "postgresql+psycopg://unit/runtime",
        "require_database_url": True,
        "has_candidate_universe_json": False,
        "has_allow_local_file_diagnostic": False,
    }


def test_watcher_tick_stale_status_recovers_on_fresh_observation_artifacts(
    tmp_path,
):
    def supervisor_builder(args):
        artifact = _fake_supervisor("waiting_for_signal")(args)
        artifact["status_artifact"]["status"] = "stale"
        artifact["status_artifact"]["blockers"] = [
            "active_observation_status_stale"
        ]
        return artifact

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path),
        supervisor_builder=supervisor_builder,
    )

    assert artifact["post_signal_auto_resume"]["status"] == (
        "blocked_observation_evidence"
    )
    assert artifact["post_signal_auto_resume"]["next_recover_condition"] == (
        "fresh_non_forbidden_observation_artifacts_exist"
    )
    assert "fresh_non_forbidden_observation_packets_exist" not in json.dumps(artifact)


def test_watcher_tick_does_not_notify_when_operator_evidence_needs_review_but_waiting_for_market(
    tmp_path,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_evidence",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_evidence",
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
            "operator_review_plan": {
                "next_step": "review_strategy_group_would_enter_without_execution",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_evidence_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("waiting_for_signal"),
        notifier=lambda *items: sent.append(items) or {"sent": True, "status_code": 200},
    )

    assert artifact["wakeup_status"] == "operator_evidence_needs_review"
    assert artifact["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert artifact["notification"]["required"] is False
    assert artifact["notification"]["reason"] == (
        "waiting_for_market_no_owner_attention_needed"
    )
    assert sent == []


def test_watcher_tick_sends_feishu_on_ready_signal(tmp_path):
    calls = []

    def notifier(webhook_url, webhook_secret, body, timeout):
        calls.append((webhook_url, webhook_secret, body, timeout))
        return {"sent": True, "status_code": 200, "response_body_preview": "ok"}

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(
            tmp_path,
            feishu_webhook_url="https://example.test/hook",
            feishu_webhook_secret="secret-value",
        ),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=notifier,
    )

    assert artifact["status"] == "owner_notified"
    assert artifact["wakeup_status"] == "prepared_shadow_evidence_ready_for_owner_review"
    assert artifact["post_signal_auto_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert artifact["post_signal_auto_resume"]["can_continue_without_owner_chat"] is True
    assert "automatic_recovery_action" not in artifact["post_signal_auto_resume"]
    assert artifact["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "rerun_watcher_tick_with_allow_prepare_records"
    )
    assert artifact["notification"]["sent"] is True
    assert calls[0][0] == "https://example.test/hook"
    assert calls[0][1] == "secret-value"
    assert "monitored runtimes: 1" in calls[0][2]["text"]
    assert "auth-ready-1" in calls[0][2]["text"]
    assert "secret-value" not in json.dumps(artifact)


def test_watcher_tick_suppresses_duplicate_ready_event(tmp_path):
    first = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )
    assert first["notification"]["sent"] is True

    calls = []
    second = runtime_signal_watcher_tick.build_watcher_tick_artifact(
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

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, env_file=str(env_file)),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
        notifier=lambda *items: calls.append(items) or {"sent": True, "status_code": 200},
    )

    assert artifact["status"] == "owner_notified"
    assert artifact["notification"]["configured"] is True
    assert artifact["notification"]["secret_configured"] is True
    assert calls[0][0] == "https://example.test/from-env-file"
    assert calls[0][1] == "env-file-secret"
    assert "env-file-secret" not in json.dumps(artifact)


def test_watcher_tick_auto_resume_can_stop_at_non_executing_prepare_checkpoint(tmp_path):
    latest = _summary("ready_for_prepare", ready=False)
    latest.update(
        {
            "signal_input_json": "pg://runtime-control-state/live-signal-events/signal-unit-ready",
            "pg_live_signal_events": {
                "status": "pg_live_signal_events_written",
                "written_count": 1,
                "signal_event_ids": ["signal-unit-ready"],
            },
        }
    )

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor_from_latest(latest),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert artifact["post_signal_auto_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert artifact["post_signal_auto_resume"]["blocked_reason"] == (
        "pg_fresh_strategy_signal_ready"
    )
    assert "automatic_recovery_action" not in artifact["post_signal_auto_resume"]
    assert artifact["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "rerun_watcher_tick_with_allow_prepare_records"
    )
    assert "operator_command_plan" not in artifact
    assert artifact["watcher_tick_plan"]["can_continue_without_owner_chat"] is True
    assert artifact["watcher_tick_plan"]["places_order"] is False
    assert artifact["watcher_tick_plan"]["calls_order_lifecycle"] is False


def test_watcher_tick_blocks_legacy_ready_without_pg_live_signal_event(tmp_path):
    latest = _summary("ready_for_prepare", ready=True)
    latest["prepared_authorization_id"] = None
    latest["shadow_candidate_id"] = None
    latest["pg_live_signal_events"] = {
        "status": "pg_live_signal_events_blocked",
        "written_count": 0,
        "skipped": [{"blocker": "fresh_public_fact_snapshot_missing"}],
    }

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor_from_latest(latest),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert artifact["post_signal_auto_resume"]["status"] == (
        "blocked_observation_evidence"
    )
    assert artifact["post_signal_auto_resume"]["blocked_at"] == "pg_live_signal_event"
    assert artifact["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "materialize_pg_live_signal_event"
    )
    assert artifact["watcher_tick_plan"]["can_continue_without_owner_chat"] is False


def test_watcher_tick_treats_only_expired_pg_signals_as_market_wait(tmp_path):
    latest = _summary("ready_for_prepare", ready=False)
    latest["pg_live_signal_events"] = {
        "status": "pg_live_signal_events_blocked",
        "written_count": 0,
        "skipped": [
            {"blocker": "signal_event_expired", "strategy_group_id": "MPG-001"},
            {"blocker": "signal_event_expired", "strategy_group_id": "CPM-RO-001"},
        ],
    }

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(tmp_path, feishu_webhook_url="https://example.test/hook"),
        supervisor_builder=_fake_supervisor_from_latest(latest),
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert artifact["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert artifact["post_signal_auto_resume"]["blocked_reason"] == (
        "detected_strategy_signals_expired"
    )
    assert artifact["notification"]["required"] is False
    assert artifact["notification"]["sent"] is False
    assert artifact["status"] == "watching_no_signal"
    assert artifact["watcher_tick_plan"]["can_continue_without_owner_chat"] is True


def test_watcher_tick_keeps_fresh_signal_prepare_when_status_has_chain_blockers(
    tmp_path,
    monkeypatch,
):
    def supervisor_builder(args):
        output_dir = Path(args.output_dir)
        latest = _summary("ready_for_final_gate_preflight", ready=False)
        latest.update(
            {
                "signal_input_json": "pg://runtime-control-state/live-signal-events/signal-sor-btc",
                "pg_live_signal_events": {
                    "status": "pg_live_signal_events_written",
                    "written_count": 1,
                    "signal_event_ids": ["signal-sor-btc"],
                },
                "blockers": [
                    "runtime-old:{'id': 'NEXT-ATTEMPT-POSITION-ORDER-CONFLICT', 'evidence': 'pg_open_order_count=1'}"
                ],
            }
        )
        loop = {
            "scope": "runtime_signal_watcher_in_memory_observation",
            "status": "ready_for_final_gate_preflight",
            "stop_reason": "status_changed:ready_for_final_gate_preflight",
            "iterations_requested": 1,
            "iterations_completed": 1,
            "latest_summary": latest,
            "cycle_summaries": [latest],
            "blockers": latest["blockers"],
            "warnings": [],
            "operator_review_plan": {
                "not_executed": True,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "monitor_loop_only": True,
                "prepare_records_created": False,
                "shadow_candidate_created": False,
                "runtime_execution_intent_draft_created": False,
                "recorded_execution_intent_created": False,
                "submit_authorization_created": False,
                "protection_plan_created": False,
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
        artifact = {
            "scope": "runtime_signal_watcher_in_memory_supervisor",
            "status": "supervisor_completed",
            "blockers": [],
            "warnings": [],
            "loop_artifact": loop,
            "latest_summary": latest,
            "safety_invariants": {"forbidden_effects": []},
        }
        artifact["status_artifact"] = runtime_signal_watcher_tick._status_from_loop_artifact(
            output_dir=output_dir,
            supervisor_artifact=artifact,
            loop_artifact=loop,
            latest_summary=latest,
            stale_after_seconds=float(args.status_stale_after_seconds),
        )
        return artifact

    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_operator_evidence",
        lambda **kwargs: {
            "scope": "runtime_observation_operator_evidence",
            "status": "strategy_group_signal_review_available",
            "signal_counts": {"runtime_ready_signal_count": 1},
            "operator_review_plan": {
                "next_step": "prepare_candidate_grant_authorization_evidence",
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": {
                "operator_evidence_only": True,
                "execution_intent_created": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effects": [],
            },
        },
    )
    monkeypatch.setattr(
        runtime_signal_watcher_tick,
        "build_wakeup_evidence",
        lambda operator: {
            "status": "runtime_signal_ready_for_non_executing_prepare",
            "summary": {"runtime_ready_signal_count": 1},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(
            tmp_path,
            allow_prepare_records=True,
            feishu_webhook_url="https://example.test/hook",
        ),
        supervisor_builder=supervisor_builder,
        notifier=lambda *items: {"sent": True, "status_code": 200},
    )

    assert artifact["post_signal_auto_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert artifact["post_signal_auto_resume"]["signal_input_json"] == (
        "pg://runtime-control-state/live-signal-events/signal-sor-btc"
    )
    assert artifact["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "wait_for_prepare_records_then_rebuild_final_gate_status"
    )
    assert artifact["watcher_tick_plan"]["places_order"] is False
    assert artifact["watcher_tick_plan"]["calls_order_lifecycle"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_watcher_tick_auto_resume_keeps_prepare_records_pg_ticket_only(tmp_path):
    artifact = runtime_signal_watcher_tick.build_watcher_tick_artifact(
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

    assert artifact["post_signal_auto_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert artifact["post_signal_auto_resume"]["prepared_authorization_id"] == (
        "auth-ready-1"
    )
    assert "automatic_recovery_action" not in artifact["post_signal_auto_resume"]
    assert artifact["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "wait_for_prepare_records_then_rebuild_final_gate_status"
    )
    assert "operator_command_plan" not in artifact
    assert "next_step" not in artifact["watcher_tick_plan"]
    assert artifact["watcher_tick_plan"]["non_authority_checkpoint"] == (
        "wait_for_prepare_records_then_rebuild_final_gate_status"
    )
    assert artifact["watcher_tick_plan"]["not_execution_authority"] is True
    assert artifact["watcher_tick_plan"]["creates_prepare_records"] is True
    assert artifact["watcher_tick_plan"]["creates_shadow_candidate"] is True
    assert artifact["watcher_tick_plan"]["places_order"] is False
    assert artifact["watcher_tick_plan"]["calls_order_lifecycle"] is False
    assert artifact["safety_invariants"]["post_signal_auto_resume_decision_only"] is False
    assert artifact["safety_invariants"]["prepare_records_created"] is True
    assert artifact["safety_invariants"]["shadow_candidate_created"] is True
    assert artifact["safety_invariants"][
        "runtime_execution_intent_draft_created"
    ] is True
    assert artifact["safety_invariants"]["recorded_execution_intent_created"] is True
    assert artifact["safety_invariants"]["submit_authorization_created"] is True
    assert artifact["safety_invariants"]["protection_plan_created"] is True
    assert artifact["safety_invariants"]["allowed_prepare_record_effects"] == [
        "prepare_records_created",
        "shadow_candidate_created",
        "runtime_execution_intent_draft_created",
        "recorded_execution_intent_created",
        "submit_authorization_created",
        "protection_plan_created",
    ]
    assert artifact["safety_invariants"]["real_submit_requested"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_notification_dry_run_does_not_mark_event_as_notified(tmp_path):
    first = runtime_signal_watcher_tick.build_watcher_tick_artifact(
        _args(
            tmp_path,
            feishu_webhook_url="https://example.test/hook",
            notification_dry_run=True,
        ),
        supervisor_builder=_fake_supervisor("ready_for_prepare", ready=True),
    )
    assert first["notification"]["skipped_reason"] == "notification_dry_run"

    calls = []
    second = runtime_signal_watcher_tick.build_watcher_tick_artifact(
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
