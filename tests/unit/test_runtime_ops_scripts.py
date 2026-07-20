from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace

from scripts.ops import check_tokyo_runtime_ops_health_once
from scripts import create_runtime_closed_trade_review
from scripts import runtime_live_position_monitor, runtime_position_exit_plan


def test_runtime_monitor_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "PG_DATABASE_URL=postgresql+asyncpg://example",
                "EXCHANGE_API_KEY=key-from-file",
            ]
        )
    )
    monkeypatch.setenv("PG_DATABASE_URL", "")
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)

    runtime_live_position_monitor._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://example"
    assert os.environ["EXCHANGE_API_KEY"] == "key-from-file"


def test_tokyo_ops_health_pg_counts_do_not_expose_dsn_in_command_plan():
    payload = check_tokyo_runtime_ops_health_once.build_payload(execute_local=False)
    row = next(item for item in payload["results"] if item["name"] == "pg_runtime_row_counts")
    chain_row = next(
        item for item in payload["results"] if item["name"] == "pg_l2_l7_chain_health"
    )
    command_text = " ".join(row["command"])
    chain_command_text = " ".join(chain_row["command"])

    assert row["status"] == "planned"
    assert row["command"] == ["internal_sqlalchemy_readonly_row_counts"]
    assert chain_row["status"] == "planned"
    assert chain_row["command"] == ["internal_sqlalchemy_readonly_l2_l7_chain_health"]
    assert "psql" not in command_text
    assert "psql" not in chain_command_text
    assert "PG_DATABASE_URL" not in command_text
    assert "PG_DATABASE_URL" not in chain_command_text
    assert "DATABASE_URL" not in command_text
    assert "DATABASE_URL" not in chain_command_text


def test_tokyo_ops_health_low_priority_du_timeout_is_not_global_warn(monkeypatch):
    def fake_which(_name):
        return "/usr/bin/fake"

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=124 if "du" in command else 0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(check_tokyo_runtime_ops_health_once.shutil, "which", fake_which)
    monkeypatch.setattr(
        check_tokyo_runtime_ops_health_once.subprocess, "run", fake_run
    )
    monkeypatch.setattr(
        check_tokyo_runtime_ops_health_once,
        "_pg_runtime_row_counts_result",
        lambda *, execute_local: {
            "name": "pg_runtime_row_counts",
            "command": ["internal_sqlalchemy_readonly_row_counts"],
            "status": "ok",
        },
    )
    monkeypatch.setattr(
        check_tokyo_runtime_ops_health_once,
        "_pg_l2_l7_chain_health_result",
        lambda *, execute_local: {
            "name": "pg_l2_l7_chain_health",
            "command": ["internal_sqlalchemy_readonly_l2_l7_chain_health"],
            "status": "ok",
        },
    )

    payload = check_tokyo_runtime_ops_health_once.build_payload(execute_local=True)

    timeout_rows = [
        row for row in payload["results"] if row["status"] == "skipped_timeout"
    ]
    assert payload["status"] == "ok"
    assert {row["name"] for row in timeout_rows} == {
        "reports_du",
        "releases_du",
        "backups_du",
    }


def test_tokyo_ops_l2_l7_summary_accepts_completed_rehearsal_without_open_objects():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [
                {"strategy_group_id": "CPM-RO-001", "current_count": 4},
                {"strategy_group_id": "MPG-001", "current_count": 4},
                {"strategy_group_id": "MI-001", "current_count": 3},
                {"strategy_group_id": "SOR-001", "current_count": 8},
                {"strategy_group_id": "BRF2-001", "current_count": 3},
            ],
            "recent_counts": {
                "facts": 26,
                "signals": 0,
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
                "monitor": 1,
            },
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {
                "status": "protected_submit_rehearsal_completed",
                "fresh_signal_present": True,
                "ready_for_real_order_action": False,
                "owner_action_required": False,
                "blockers": [],
            },
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {
                    "calls_finalgate": False,
                    "calls_operation_layer": False,
                    "calls_exchange_write": False,
                    "order_created": False,
                    "live_profile_changed": False,
                    "order_sizing_changed": False,
                },
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
        }
    )

    assert summary["status"] == "ok"
    assert summary["issues"] == []
    assert summary["goal_status"] == "protected_submit_rehearsal_completed"
    assert summary["open_counts"]["lanes"] == 0


def test_tokyo_ops_l2_l7_summary_does_not_promote_historical_notify_blocker():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {
                "facts": 22,
                "signals": 0,
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
                "monitor": 1,
            },
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "waiting_for_signal", "blockers": []},
            "monitor": {
                "status": "notify",
                "blocker_classes": ["tp1_reference_missing"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "submitted_attempts_without_protection": [],
            "incomplete_protection_sets": [],
            "tp1_filled_without_runner_sl": [],
            "runner_protected_without_runner_sl": [],
            "lifecycle_closed_without_post_submit_closed": [],
            "post_submit_closed_without_lifecycle_closed": [],
        }
    )

    assert summary["status"] == "ok"
    assert "server_monitor_status_not_classified" not in summary["issues"]
    assert summary["server_monitor_status"] == "notify"
    assert summary["server_monitor_blocker_classes"] == []
    assert summary["server_monitor_raw_blocker_classes"] == ["tp1_reference_missing"]


def test_tokyo_ops_l2_l7_summary_flags_ready_pseudo_blocker():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {
                "status": "protected_submit_rehearsal_completed",
                "blockers": ["candidate_pool_blocker:action_time_preflight_ready:2"],
            },
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
        }
    )

    assert summary["status"] == "warn"
    assert "goal_status_ready_pseudo_blocker" in summary["issues"]


def test_tokyo_ops_l2_l7_summary_flags_terminal_status_with_open_objects():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 1,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {
                "status": "protected_submit_rehearsal_completed",
                "blockers": [],
            },
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
        }
    )

    assert summary["status"] == "warn"
    assert "terminal_goal_status_with_open_l2_l7_objects" in summary["issues"]


def test_tokyo_ops_l2_l7_summary_flags_tp1_fill_without_runner_sl():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "tp1_filled_without_runner_sl": [
                {
                    "exit_protection_set_id": "set-1",
                    "ticket_id": "ticket-1",
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "tp1_filled_without_runner_sl" in summary["issues"]
    assert summary["tp1_filled_without_runner_sl_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_runner_protected_without_runner_sl():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "runner_protected_without_runner_sl": [
                {
                    "exit_protection_set_id": "set-1",
                    "ticket_id": "ticket-1",
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "runner_protected_without_runner_sl" in summary["issues"]
    assert summary["runner_protected_without_runner_sl_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_exact_lifecycle_attention_state():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "submitted_attempts_without_protection": [],
            "incomplete_protection_sets": [],
            "tp1_filled_without_runner_sl": [],
            "runner_protected_without_runner_sl": [],
            "lifecycle_closed_without_post_submit_closed": [],
            "post_submit_closed_without_lifecycle_closed": [],
            "lifecycle_attention_rows": [
                {
                    "lifecycle_run_id": "lifecycle-1",
                    "ticket_id": "ticket-1",
                    "protected_submit_attempt_id": "attempt-1",
                    "strategy_group_id": "SOR-001",
                    "symbol": "AVAXUSDT",
                    "side": "short",
                    "status": "runner_mutation_pending",
                    "first_blocker": "runner_sl_exchange_order_id_required",
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "ticket_bound_lifecycle_attention_state" in summary["issues"]
    assert summary["lifecycle_attention_state_count"] == 1
    assert summary["lifecycle_attention_statuses"] == ["runner_mutation_pending"]
    assert summary["lifecycle_owner_feedback"] == {
        "status": "processing",
        "label": "处理中",
        "reason": "runner_sl_exchange_order_id_required",
        "ticket_id": "ticket-1",
        "strategy_group_id": "SOR-001",
        "symbol": "AVAXUSDT",
        "side": "short",
        "lifecycle_status": "runner_mutation_pending",
        "phase": "reducing",
        "protection_state": "pending",
        "reconciliation_state": "pending",
        "control_state": "automated",
        "next_action": "run_official_runner_mutation_command",
        "non_authority_checkpoint": "run_official_runner_mutation_command",
        "owner_action_required": False,
        "exchange_write_authorized": False,
    }


def test_tokyo_ops_l2_l7_summary_flags_runner_mutation_command_without_runner_proof():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "submitted_attempts_without_protection": [],
            "incomplete_protection_sets": [],
            "tp1_filled_without_runner_sl": [],
            "runner_protected_without_runner_sl": [],
            "lifecycle_closed_without_post_submit_closed": [],
            "post_submit_closed_without_lifecycle_closed": [],
            "runner_mutation_commands_without_runner_proof": [
                {
                    "runner_mutation_command_id": "runner-command-1",
                    "ticket_id": "ticket-1",
                    "status": "result_recorded",
                }
            ],
            "lifecycle_attention_rows": [],
        }
    )

    assert summary["status"] == "warn"
    assert "runner_mutation_command_without_runner_proof" in summary["issues"]
    assert summary["runner_mutation_command_without_runner_proof_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_invalid_submitted_order_semantics():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "submitted_attempts_with_invalid_order_semantics": [
                {
                    "protected_submit_attempt_id": "attempt-1",
                    "ticket_id": "ticket-1",
                    "semantic_issues": {
                        "SL": ["submit_result_sl_terminal_status"],
                        "TP1": ["submit_result_tp1_price_missing"],
                    },
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "submitted_attempt_invalid_order_semantics" in summary["issues"]
    assert summary["submitted_attempt_invalid_order_semantics_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_closed_protection_with_live_orders():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "closed_protection_sets_with_live_orders": [
                {
                    "exit_protection_set_id": "set-1",
                    "ticket_id": "ticket-1",
                    "live_order_count": 1,
                }
            ],
        }
    )

    assert summary["status"] == "critical"
    assert "closed_exit_protection_set_with_live_orders" in summary["issues"]
    assert summary["closed_protection_set_with_live_order_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_lifecycle_closure_projection_mismatch():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "lifecycle_closed_without_post_submit_closed": [
                {"lifecycle_run_id": "lifecycle-1", "ticket_id": "ticket-1"}
            ],
            "post_submit_closed_without_lifecycle_closed": [
                {
                    "post_submit_closure_id": "closure-1",
                    "ticket_id": "ticket-2",
                    "lifecycle_status": "runner_protected",
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "lifecycle_closed_without_post_submit_closed" in summary["issues"]
    assert "post_submit_closed_without_lifecycle_closed" in summary["issues"]
    assert summary["lifecycle_closed_without_post_submit_closed_count"] == 1
    assert summary["post_submit_closed_without_lifecycle_closed_count"] == 1


def test_tokyo_ops_l2_l7_summary_flags_closed_without_lifecycle_evidence_events():
    summary = check_tokyo_runtime_ops_health_once.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 1770000600000,
            "since_ms": 1770000000000,
            "missing_tables": [],
            "missing_coverage": [],
            "coverage_by_group": [],
            "recent_counts": {},
            "open_counts": {
                "promotions": 0,
                "lanes": 0,
                "tickets": 0,
                "attempts": 0,
            },
            "goal": {"status": "running", "blockers": []},
            "monitor": {
                "status": "quiet",
                "blocker_classes": ["none"],
                "forbidden_effects": {},
            },
            "unadvanced_fresh_signals": [],
            "recent_duplicate_lanes": [],
            "post_submit_closed_without_lifecycle_evidence_events": [
                {
                    "post_submit_closure_id": "closure-1",
                    "ticket_id": "ticket-1",
                    "protected_submit_attempt_id": "attempt-1",
                }
            ],
        }
    )

    assert summary["status"] == "warn"
    assert "post_submit_closed_without_lifecycle_evidence_events" in summary["issues"]
    assert summary["post_submit_closed_without_lifecycle_evidence_event_count"] == 1


def test_runtime_monitor_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_artifact(args):
        print("noisy exchange close log")
        return {
            "scope": "runtime_live_position_monitor",
            "status": "active_protection_warning",
            "artifact": {"runtime_instance_id": args.runtime_instance_id},
        }

    monkeypatch.setattr(runtime_live_position_monitor, "_build_artifact", fake_build_artifact)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_live_position_monitor.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_live_position_monitor.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy exchange close log" not in captured.out
    assert "noisy exchange close log" in captured.err


def test_runtime_exit_plan_env_loader_preserves_non_empty_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://from-file")
    monkeypatch.setenv("PG_DATABASE_URL", "postgresql+asyncpg://already-set")

    runtime_position_exit_plan._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://already-set"


def test_closed_trade_review_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://post-close")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    create_runtime_closed_trade_review._load_env_file(str(env_file))
    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://post-close"


def test_runtime_monitor_loads_env_before_infrastructure_imports(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://from-file")
    observed = {}

    class FakeRuntimeRepository:
        def __init__(self):
            observed["pg_at_repository_init"] = os.environ.get("PG_DATABASE_URL")

        async def initialize(self):
            return None

    class FakePositionRepository:
        async def initialize(self):
            return None

    class FakeOrderRepository:
        async def initialize(self):
            return None

    class FakeMonitorService:
        def __init__(self, **kwargs):
            pass

        async def build_monitor_artifact(self, *, runtime_instance_id):
            class Status:
                value = "ok"

            class Artifact:
                status = Status()

                def model_dump(self, mode="python"):
                    return {"runtime_instance_id": runtime_instance_id}

            return Artifact()

    async def fake_close_all_connections():
        return None

    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infrastructure.pg_strategy_runtime_repository",
        type(
            "Module",
            (),
            {"PgStrategyRuntimeRepository": FakeRuntimeRepository},
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infrastructure.pg_position_repository",
        type("Module", (), {"PgPositionRepository": FakePositionRepository}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infrastructure.pg_order_repository",
        type("Module", (), {"PgOrderRepository": FakeOrderRepository}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.application.runtime_live_position_monitor_service",
        type("Module", (), {"RuntimeLivePositionMonitorService": FakeMonitorService}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.application.reconciliation",
        type("Module", (), {"ReconciliationService": object}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infrastructure.exchange_gateway",
        type("Module", (), {"ExchangeGateway": object}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "src.infrastructure.connection_pool",
        type("Module", (), {"close_all_connections": fake_close_all_connections}),
    )

    import asyncio

    asyncio.run(
        runtime_live_position_monitor._build_artifact(
            Namespace(
                env_file=str(env_file),
                runtime_instance_id="runtime-1",
                skip_exchange=True,
                skip_reconciliation=True,
            )
        )
    )

    assert observed["pg_at_repository_init"] == "postgresql+asyncpg://from-file"
