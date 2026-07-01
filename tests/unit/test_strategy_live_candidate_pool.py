from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "scripts" / "build_strategy_live_candidate_pool.py"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_strategy_live_candidate_pool.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _builder():
    return _load_module(BUILDER_PATH, "build_strategy_live_candidate_pool")


def _validator():
    return _load_module(VALIDATOR_PATH, "validate_strategy_live_candidate_pool")


def _daily_table() -> dict:
    rows = [
        ("CPM-RO-001", "ETHUSDT", "long", "armed", "computed_not_satisfied", 4),
        ("MPG-001", "SOLUSDT", "long", "armed", "watcher_tick_missing", 1),
        ("MI-001", "AVAXUSDT", "long", "admission", "scope_not_attached", 3),
        ("SOR-001", "ETHUSDT", "long", "armed", "watcher_tick_missing", 2),
        (
            "BRF2-001",
            "brf2_research_supported_symbols_only",
            "short",
            "armed",
            "computed_not_satisfied",
            5,
        ),
    ]
    return {
        "schema": "brc.daily_live_enablement_table.v1",
        "status": "daily_live_enablement_table_ready",
        "source_validation": {"valid": True},
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "rows": [
            {
                "strategy_group_id": strategy_group_id,
                "symbol": symbol,
                "side": side,
                "stage": stage,
                "chain_position": "replay_live_parity",
                "first_blocker": first_blocker,
                "first_blocker_evidence": (
                    "output/runtime-monitor/latest-replay-live-parity-audit.json:"
                    f"{strategy_group_id}/{symbol} blocker_class={first_blocker}"
                ),
                "owner_action_required": "no",
                "next_engineering_action": "next_action_for_" + first_blocker,
                "stop_condition": "stop when blocker moves",
                "closest_to_live_rank": rank,
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
            }
            for strategy_group_id, symbol, side, stage, first_blocker, rank in rows
        ],
    }


def _tradeability() -> dict:
    owners = {
        "CPM-RO-001": "market",
        "MPG-001": "runtime",
        "MI-001": "engineering",
        "SOR-001": "runtime",
        "BRF2-001": "market",
    }
    return {
        "schema": "brc.strategygroup_tradeability_decision.v1",
        "status": "tradeability_decision_ready",
        "decision_rows": [
            {
                "strategy_group_id": strategy_group_id,
                "blocker_owner": owner,
            }
            for strategy_group_id, owner in owners.items()
        ],
    }


def _parity() -> dict:
    return {
        "schema": "brc.replay_live_parity_audit.v1",
        "status": "replay_live_parity_audit_ready",
    }


def _action_time() -> dict:
    return {
        "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
        "status": "strategy_fresh_signal_action_time_boundary_ready",
        "strategy_rows": [
            {
                "strategy_group_id": "MPG-001",
                "action_time_path_ready": False,
                "first_blocker": "watcher_tick_missing",
                "next_action": "refresh_or_repair_watcher_public_fact_input",
                "required_facts_readiness": {
                    "public_facts_ready": False,
                    "private_action_time_facts_ready": False,
                },
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "action_time_path_ready": True,
                "first_blocker": "fresh_cpm_long_signal_absent",
                "next_action": "wait_for_fresh_signal_then_refresh_private_action_time_facts",
                "required_facts_readiness": {
                    "public_facts_ready": True,
                    "private_action_time_facts_ready": False,
                },
            },
        ],
    }


def _single_lane() -> dict:
    return {
        "schema": "brc.single_lane_task_packet.v1",
        "status": "single_lane_task_packet_ready",
        "task_id": "P0-MPG-001-WATCHER-TICK-MISSING-CLOSURE",
        "active_lane": {
            "strategy_group_id": "MPG-001",
            "symbol": "SOLUSDT",
            "side": "long",
            "stage": "armed",
        },
        "first_blocker": "watcher_tick_missing",
    }


def test_candidate_pool_builds_five_wip_candidate_rows():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert artifact["schema"] == "brc.strategy_live_candidate_pool.v1"
    assert artifact["status"] == "strategy_live_candidate_pool_ready"
    assert artifact["summary"]["candidate_count"] == 5
    assert artifact["summary"]["deploy_ready"] is False
    assert artifact["summary"]["rank_1_lane"] == "MPG-001:SOLUSDT"
    rows = {row["strategy_group_id"]: row for row in artifact["candidate_rows"]}
    assert rows["MPG-001"]["candidate_status"] == "candidate_runtime_input_blocked"
    assert rows["CPM-RO-001"]["candidate_status"] == "candidate_market_condition_wait"
    assert rows["BRF2-001"]["candidate_status"] == "candidate_conditional_observation"
    assert rows["MI-001"]["candidate_status"] == "candidate_scope_decision_pending"
    assert rows["MPG-001"]["action_time_readiness"]["status"] == "blocked_public_facts"
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_review_keeps_open_p0_items_visible():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    review = {row["item"]: row for row in artifact["p0_p1_review"]}
    assert review["five_strategy_candidate_pool_control_surface"]["status"] == "cleared"
    assert review["daily_table_single_lane_consistency"]["status"] == "cleared"
    assert review["mpg_watcher_closure"]["status"] == "open"
    assert review["sor_watcher_closure"]["status"] == "open"
    assert review["brf2_conditionalization"]["status"] == "cleared"


def test_candidate_pool_validator_rejects_missing_required_candidate_field():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    artifact["candidate_rows"][0]["trigger_condition"] = ""

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("trigger_condition" in error for error in errors)


def test_candidate_pool_validator_rejects_authority_leakage():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    artifact["safety_invariants"]["calls_exchange_write"] = True

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("calls_exchange_write" in error for error in errors)


def test_candidate_pool_cli_and_validator_cli_round_trip(tmp_path: Path):
    daily = tmp_path / "daily.json"
    tradeability = tmp_path / "tradeability.json"
    parity = tmp_path / "parity.json"
    action_time = tmp_path / "action_time.json"
    single_lane = tmp_path / "single_lane.json"
    output_json = tmp_path / "candidate_pool.json"
    output_md = tmp_path / "candidate_pool.md"
    daily.write_text(json.dumps(_daily_table()), encoding="utf-8")
    tradeability.write_text(json.dumps(_tradeability()), encoding="utf-8")
    parity.write_text(json.dumps(_parity()), encoding="utf-8")
    action_time.write_text(json.dumps(_action_time()), encoding="utf-8")
    single_lane.write_text(json.dumps(_single_lane()), encoding="utf-8")

    build = subprocess.run(
        [
            sys.executable,
            str(BUILDER_PATH),
            "--daily-table-json",
            str(daily),
            "--tradeability-json",
            str(tradeability),
            "--replay-live-parity-json",
            str(parity),
            "--action-time-boundary-json",
            str(action_time),
            "--single-lane-task-packet-json",
            str(single_lane),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    validate = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(output_json)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
