from __future__ import annotations

import os
import sys
from argparse import Namespace

from scripts.ops import check_tokyo_runtime_ops_health_once
from scripts import create_runtime_closed_trade_review, recover_runtime_exchange_close_projection
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


def test_post_close_script_env_loaders_fill_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://post-close")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    recover_runtime_exchange_close_projection._load_env_file(str(env_file))
    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://post-close"

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
