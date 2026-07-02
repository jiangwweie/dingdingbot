from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_tokyo_runtime_server_monitor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_tokyo_runtime_server_monitor",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "daily_table": tmp_path / "daily-table.json",
        "candidate_pool": tmp_path / "candidate-pool.json",
        "public_facts": tmp_path / "public-facts.json",
        "account_safe_facts": tmp_path / "account-safe-facts.json",
        "watcher_status": tmp_path / "watcher-status.json",
        "deploy_health": tmp_path / "deploy-health.json",
        "output": tmp_path / "monitor.json",
        "dedupe": tmp_path / "dedupe.json",
    }


def _write_healthy_sources(paths: dict[str, Path]) -> None:
    _write(
        paths["daily_table"],
        {
            "status": "daily_live_enablement_table_ready",
            "rows": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETHUSDT",
                    "first_blocker": "computed_not_satisfied",
                }
            ],
        },
    )
    _write(
        paths["candidate_pool"],
        {
            "status": "strategy_live_candidate_pool_ready",
            "action_time_lane_inputs": [],
            "candidate_rows": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "selected_symbol": "ETHUSDT",
                    "first_blocker": "computed_not_satisfied",
                    "action_time_readiness": {
                        "status": "waiting_for_market",
                        "action_time_path_ready": False,
                        "public_facts_ready": True,
                    },
                }
            ],
        },
    )
    _write(
        paths["public_facts"],
        {
            "status": "binance_usdm_public_facts_ready",
            "checks": {"public_facts_ready": True},
        },
    )
    _write(
        paths["account_safe_facts"],
        {
            "status": "account_safe_facts_ready",
            "checks": {"account_safe_facts_ready": True},
        },
    )
    _write(paths["watcher_status"], {"status": "ok", "latest_status": "waiting_for_signal"})
    _write(paths["deploy_health"], {"status": "deploy_health_ready", "checks": {"ready": True}})


def _args(module, paths: dict[str, Path]):
    return module._parse_args(
        [
            "--output-json",
            str(paths["output"]),
            "--dedupe-state-json",
            str(paths["dedupe"]),
            "--daily-table-json",
            str(paths["daily_table"]),
            "--candidate-pool-json",
            str(paths["candidate_pool"]),
            "--public-facts-json",
            str(paths["public_facts"]),
            "--account-safe-facts-json",
            str(paths["account_safe_facts"]),
            "--watcher-status-json",
            str(paths["watcher_status"]),
            "--deploy-health-json",
            str(paths["deploy_health"]),
            "--skip-systemd",
            "--feishu-webhook-url",
            "https://example.invalid/webhook",
        ]
    )


def test_healthy_waiting_is_quiet_without_feishu_notification(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    calls: list[dict] = []

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: calls.append({"args": args}) or {"sent": True},
    )

    assert artifact["status"] == "healthy_waiting_quiet"
    assert artifact["decision"]["decision"] == "quiet"
    assert artifact["notification"]["attempted"] is False
    assert artifact["notification"]["skipped_reason"] == "healthy_waiting_quiet"
    assert calls == []
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["withdrawal_or_transfer_created"] is False
    assert artifact["safety_invariants"]["credentials_or_secrets_mutated"] is False
    assert artifact["safety_invariants"]["live_profile_changed"] is False
    assert artifact["safety_invariants"]["order_sizing_changed"] is False


def test_fresh_signal_or_action_time_boundary_notifies_once_with_dedupe(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {"strategy_group_id": "MPG-001", "symbol": "SOLUSDT"}
    ]
    _write(paths["candidate_pool"], candidate_pool)
    calls: list[dict] = []

    def notifier(*args):
        calls.append({"args": args})
        return {"sent": True, "status_code": 200}

    first = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)
    second = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)

    assert first["decision"]["decision"] == "notify"
    assert first["decision"]["checkpoint"] == "fresh_signal_action_time_boundary"
    assert first["notification"]["attempted"] is True
    assert first["notification"]["sent"] is True
    assert second["notification"]["duplicate_suppressed"] is True
    assert second["notification"]["attempted"] is False
    assert len(calls) == 1
    dedupe_key = first["notification"]["dedupe_key"]
    assert dedupe_key["automation_id"] == "tokyo-runtime-server-monitor"
    assert dedupe_key["strategy_group_id"] == "MPG-001"
    assert dedupe_key["symbol"] == "SOLUSDT"
    assert dedupe_key["blocker_class"] == "action_time_boundary"
    assert dedupe_key["checkpoint"] == "fresh_signal_action_time_boundary"
    assert dedupe_key["first_seen_at"]
    assert dedupe_key["last_notified_at"]


def test_conditional_action_time_rehearsal_notifies_with_separate_checkpoint(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "scope_state": "conditional_action_time_rehearsal_allowed",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "BRF2-001"
    assert artifact["decision"]["symbol"] == "BTCUSDT"
    assert artifact["decision"]["blocker_class"] == "conditional_action_time_rehearsal"
    assert artifact["decision"]["checkpoint"] == "conditional_action_time_rehearsal"
    assert "conditional_action_time_rehearsal_only" in artifact["decision"]["reasons"]
    assert artifact["notification"]["dedupe_key"]["checkpoint"] == (
        "conditional_action_time_rehearsal"
    )
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_promotion_candidate_from_candidate_pool_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["promotion_candidates"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "promotion_state": "promotion_candidate",
            "signal_state": "fresh",
            "first_blocker": "scope_not_attached",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "MPG-001"
    assert artifact["decision"]["symbol"] == "OPUSDT"
    assert artifact["decision"]["blocker_class"] == "promotion_candidate"
    assert artifact["decision"]["checkpoint"] == "fresh_signal_promotion"
    assert "promotion_candidate_present" in artifact["decision"]["reasons"]
    assert artifact["notification"]["sent"] is True


def test_fresh_symbol_readiness_non_market_blocker_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["symbol_readiness_rows"] = [
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "signal_state": "fresh",
            "first_blocker": "watcher_tick_missing",
        }
    ]
    _write(paths["candidate_pool"], candidate_pool)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["strategy_group_id"] == "SOR-001"
    assert artifact["decision"]["symbol"] == "ETHUSDT"
    assert artifact["decision"]["blocker_class"] == "watcher_tick_missing"
    assert artifact["decision"]["checkpoint"] == "fresh_signal_promotion"
    assert (
        "fresh_signal_blocked_by_non_market_blocker:watcher_tick_missing"
        in artifact["decision"]["reasons"]
    )
    assert artifact["notification"]["sent"] is True


def test_non_market_blocker_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    daily_table = json.loads(paths["daily_table"].read_text(encoding="utf-8"))
    daily_table["rows"][0]["first_blocker"] = "scope_not_attached"
    _write(paths["daily_table"], daily_table)

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "scope_not_attached"
    assert artifact["notification"]["sent"] is True


def test_watcher_or_systemd_failure_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)

    args = _args(module, paths)
    args.skip_systemd = False
    args.systemd_unit = ["brc-runtime-signal-watcher.service"]

    def runner(unit: str):
        assert unit == "brc-runtime-signal-watcher.service"
        return module.CommandResult(stdout="failed", stderr="", returncode=3)

    artifact = module.build_server_monitor_artifact(
        args,
        systemd_runner=runner,
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "watcher_or_service_failure"
    assert artifact["decision"]["checkpoint"] == "systemd"
    assert artifact["systemd"]["ready"] is False
    assert artifact["notification"]["sent"] is True


def test_watcher_status_failure_notifies(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    _write(paths["watcher_status"], {"status": "stale", "latest_status": "stale"})

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "watcher_or_service_failure"
    assert artifact["decision"]["checkpoint"] == "watcher_status"
    assert artifact["notification"]["sent"] is True


def test_feishu_failure_records_retry_without_trading_state_change(tmp_path: Path) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    candidate_pool = json.loads(paths["candidate_pool"].read_text(encoding="utf-8"))
    candidate_pool["action_time_lane_inputs"] = [
        {"strategy_group_id": "SOR-001", "symbol": "ETHUSDT"}
    ]
    _write(paths["candidate_pool"], candidate_pool)
    calls: list[str] = []

    def notifier(*args):
        calls.append("called")
        if len(calls) == 1:
            return {"sent": False, "status_code": 500, "error": "boom"}
        return {"sent": True, "status_code": 200}

    first = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)
    second = module.build_server_monitor_artifact(_args(module, paths), notifier=notifier)

    assert first["notification"]["attempted"] is True
    assert first["notification"]["sent"] is False
    assert first["notification"]["retry_pending"] is False
    assert second["notification"]["attempted"] is True
    assert second["notification"]["sent"] is True
    assert second["safety_invariants"]["notification_state_is_trading_authority"] is False
    assert second["safety_invariants"]["places_order"] is False
    assert second["safety_invariants"]["live_profile_changed"] is False
    assert len(calls) == 2


def test_public_or_account_safe_facts_failure_is_runtime_data_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()
    paths = _base_paths(tmp_path)
    _write_healthy_sources(paths)
    _write(paths["public_facts"], {"status": "binance_usdm_public_facts_unavailable"})

    artifact = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert artifact["decision"]["decision"] == "notify"
    assert artifact["decision"]["blocker_class"] == "runtime_data_gap"
    assert "runtime_data_gap:public_facts" in artifact["decision"]["reasons"]

    _write_healthy_sources(paths)
    _write(paths["account_safe_facts"], {"status": "account_safe_facts_unavailable"})
    second = module.build_server_monitor_artifact(
        _args(module, paths),
        notifier=lambda *args: {"sent": True, "status_code": 200},
    )

    assert second["decision"]["decision"] == "notify"
    assert second["decision"]["blocker_class"] == "runtime_data_gap"
    assert "runtime_data_gap:account_safe_facts" in second["decision"]["reasons"]
