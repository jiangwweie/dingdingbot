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
                    f"{strategy_group_id}/{symbol} first_blocker={first_blocker} "
                    "watcher_tick_present=True"
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
                "required_facts_readiness": _action_time_private_facts_ready(),
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


def _mi_trial_admission() -> dict:
    return {
        "schema": "brc.mi_trial_admission_decision.v1",
        "status": "mi_trial_admission_decision_ready",
        "strategy_group_id": "MI-001",
        "trial_admission_decision": "park",
        "symbol_evidence": [
            {
                "symbol": "AVAXUSDT",
                "replay_supported": False,
                "public_facts_ready": True,
                "liquidity": {
                    "spread_ok": True,
                    "min_notional_ok": True,
                    "qty_step_ok": True,
                },
                "funding_not_extreme": True,
                "strategy_fit": "not_supported_by_current_replay",
            },
            {
                "symbol": "SOLUSDT",
                "replay_supported": True,
                "public_facts_ready": False,
                "liquidity": {
                    "spread_ok": False,
                    "min_notional_ok": True,
                    "qty_step_ok": True,
                },
                "funding_not_extreme": True,
                "strategy_fit": "formal_replay_review_opened",
            },
        ],
    }


def _brf2_missing_runtime_signal_facts() -> dict:
    return {
        "schema": "brc.brf2_runtime_signal_facts.v1",
        "status": "brf2_runtime_signal_facts_missing_watcher_input",
        "strategy_group_id": "BRF2-001",
        "fact_input_present": False,
        "watcher_tick_present": False,
        "first_blocker": {
            "class": "brf2_watcher_fact_input_missing",
            "owner": "engineering",
            "repair_checkpoint": "attach_brf2_watcher_fact_input_producer",
        },
    }


def _brf2_ready_runtime_signal_facts() -> dict:
    return {
        "schema": "brc.brf2_runtime_signal_facts.v1",
        "status": "brf2_runtime_signal_facts_ready",
        "strategy_group_id": "BRF2-001",
        "fact_input_present": True,
        "watcher_tick_present": True,
        "signal_context": {"symbol": "BTC/USDT:USDT"},
        "facts": {
            "closed_1h_ohlcv": {"status": "ready"},
            "closed_5m_ohlcv": {"status": "ready"},
            "rally_context": {"status": "not_satisfied"},
            "rally_failure_trigger_state": {"status": "not_confirmed"},
            "short_squeeze_risk_state": {"status": "bounded"},
            "strong_reclaim_disable_state": {"status": "false"},
            "liquidity_downshift_state": {"status": "false"},
            "spread_liquidity_state": {"status": "acceptable"},
        },
    }


def _brf2_per_symbol_runtime_signal_facts() -> dict:
    base = _brf2_ready_runtime_signal_facts()
    base["per_symbol_facts"] = [
        {
            "symbol": symbol,
            "watcher_tick_present": True,
            "fact_input_present": True,
            "fresh_signal_present": False,
            "facts": {
                "closed_1h_ohlcv": {"status": "ready"},
                "closed_5m_ohlcv": {"status": "ready"},
                "rally_context": {"status": "not_satisfied"},
                "rally_failure_trigger_state": {"status": "not_confirmed"},
                "short_squeeze_risk_state": {"status": "bounded"},
                "strong_reclaim_disable_state": {"status": "false"},
                "liquidity_downshift_state": {"status": "false"},
                "spread_liquidity_state": {"status": "acceptable"},
            },
        }
        for symbol in ("BTCUSDT", "AVAXUSDT", "ETHUSDT")
    ]
    return base


def _action_time_private_facts_ready() -> dict:
    return {
        "public_facts_ready": True,
        "private_action_time_facts_ready": True,
        "active_position_or_open_order_clear": True,
        "action_time_available_balance": True,
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
    assert artifact["summary"]["symbol_readiness_count"] == 18
    assert artifact["summary"]["deploy_ready"] is False
    assert "rank_1_lane" not in artifact["summary"]
    assert "rank_1_task_id" not in artifact["summary"]
    assert "daily_table_single_lane_consistent" not in artifact["checks"]
    rows = {row["strategy_group_id"]: row for row in artifact["candidate_rows"]}
    assert rows["MPG-001"]["candidate_status"] == "candidate_runtime_input_blocked"
    assert rows["CPM-RO-001"]["candidate_status"] == "candidate_market_condition_wait"
    assert rows["BRF2-001"]["candidate_status"] == "candidate_conditional_observation"
    assert rows["MI-001"]["candidate_status"] == "candidate_scope_decision_pending"
    assert rows["MPG-001"]["action_time_readiness"]["status"] == "blocked_public_facts"
    readiness = artifact["symbol_readiness_rows"]
    assert {
        row["strategy_group_id"]: artifact["pretrade_runtime"][
            "candidate_symbols_per_strategy_group"
        ][row["strategy_group_id"]]
        for row in artifact["candidate_rows"]
    } == {
        "CPM-RO-001": 4,
        "MPG-001": 4,
        "MI-001": 3,
        "SOR-001": 4,
        "BRF2-001": 3,
    }
    assert "brf2_research_supported_symbols_only" not in {
        row["symbol"] for row in readiness
    }
    assert all(
        row["server_runtime_coverage"]["state"] == "runtime_profile_scope_missing"
        for row in readiness
    )
    cpm_symbols = {
        row["symbol"]
        for row in readiness
        if row["strategy_group_id"] == "CPM-RO-001"
    }
    assert {"ETHUSDT", "SOLUSDT", "AVAXUSDT"}.issubset(cpm_symbols)
    assert artifact["pretrade_runtime"]["candidate_symbols_per_strategy_group"][
        "MPG-001"
    ] >= 2
    assert artifact["checks"]["each_strategy_has_multiple_candidate_symbols"] is True
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
    assert "daily_table_single_lane_consistency" not in review
    assert review["mpg_watcher_closure"]["status"] == "open"
    assert review["sor_watcher_closure"]["status"] == "open"
    assert review["cpm_computed_refresh"]["status"] == "cleared"
    assert review["brf2_conditionalization"]["status"] == "cleared"
    assert review["output_whitelist_gate"]["status"] == "cleared"
    assert review["review_report"]["status"] == "cleared"
    assert review["postdeploy_validation_script"]["status"] == "cleared"


def test_candidate_pool_treats_cpm_action_time_reclassification_as_computed_refresh_closed():
    daily_table = json.loads(json.dumps(_daily_table()))
    cpm_daily = next(
        row
        for row in daily_table["rows"]
        if row["strategy_group_id"] == "CPM-RO-001"
    )
    cpm_daily["symbol"] = "AVAXUSDT"
    cpm_daily["first_blocker"] = "action_time_boundary_not_reproduced"
    cpm_daily["next_engineering_action"] = "prepare_cpm_candidate_authorization_evidence"
    cpm_daily["first_blocker_evidence"] = (
        "output/runtime-monitor/latest-replay-live-parity-audit.json:"
        "CPM-RO-001/AVAXUSDT first_blocker=action_time_boundary_not_reproduced "
        "watcher_tick_present=True"
    )
    cpm_daily["closest_to_live_rank"] = 1
    action_time = _action_time()
    action_time["strategy_rows"].extend(
        [
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "ETHUSDT",
                "action_time_path_ready": False,
                "first_blocker": "fresh_cpm_long_signal_absent",
                "next_action": "wait_for_fresh_signal_then_refresh_private_action_time_facts",
                "required_facts_readiness": _action_time_private_facts_ready(),
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "AVAXUSDT",
                "action_time_path_ready": True,
                "first_blocker": "private_action_time_facts_required",
                "next_action": "refresh_private_action_time_facts_before_finalgate",
                "required_facts_readiness": _action_time_private_facts_ready(),
            },
        ]
    )
    single_lane = _single_lane()
    single_lane["active_lane"] = {
        "strategy_group_id": "CPM-RO-001",
        "symbol": "AVAXUSDT",
        "side": "long",
        "stage": "armed",
    }
    single_lane["first_blocker"] = "action_time_boundary_not_reproduced"

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=daily_table,
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=action_time,
        single_lane_task_packet=single_lane,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = {row["strategy_group_id"]: row for row in artifact["candidate_rows"]}
    review = {row["item"]: row for row in artifact["p0_p1_review"]}
    assert rows["CPM-RO-001"]["selected_symbol"] == "AVAXUSDT"
    assert rows["CPM-RO-001"]["action_time_readiness"]["status"] == (
        "ready_for_finalgate_preflight"
    )
    assert rows["CPM-RO-001"]["action_time_readiness"]["first_blocker"] == (
        "private_action_time_facts_required"
    )
    assert review["cpm_computed_refresh"]["status"] == "cleared"


def test_candidate_pool_consumes_server_runtime_candidate_universe_coverage():
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "incomplete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "runtime_profile_scope_missing",
                    "blocker_class": "runtime_profile_scope_missing",
                    "active_runtime_instance_ids": [],
                    "selected_runtime_instance_ids": [],
                    "next_action": (
                        "bind_or_start_pretrade_runtime_for_candidate_symbol"
                    ),
                },
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "SOLUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-sol"],
                    "selected_runtime_instance_ids": ["runtime-mpg-sol"],
                    "next_action": "continue_pretrade_observation",
                },
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = {
        (row["strategy_group_id"], row["symbol"]): row
        for row in artifact["symbol_readiness_rows"]
    }
    op = rows[("MPG-001", "OPUSDT")]
    sol = rows[("MPG-001", "SOLUSDT")]
    assert op["first_blocker"] == "detector_not_attached"
    assert op["evidence_ref"] == "default_candidate_universe:MPG-001/OPUSDT"
    assert op["server_runtime_coverage"]["state"] == "runtime_profile_scope_missing"
    assert sol["observation_scope"] == "active_observation"
    assert sol["watcher_state"] == "fresh"
    assert artifact["server_runtime_coverage"]["status"] == "incomplete"
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_does_not_treat_server_scope_as_watcher_tick():
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "blocker_class": "watcher_tick_missing",
            "detector_attached": True,
            "watcher_tick_present": False,
            "computed": False,
            "failed_facts": [],
            "mismatch_count": 4,
            "next_action": "refresh_or_repair_watcher_public_fact_input",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-sor-eth"],
                    "selected_runtime_instance_ids": ["runtime-sor-eth"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "SOR-001" and item["symbol"] == "ETHUSDT"
    )
    assert row["server_runtime_coverage"]["state"] == "active_watcher_scope"
    assert row["watcher_state"] == "missing"
    assert row["first_blocker"] == "watcher_tick_missing"
    assert "first_blocker=watcher_tick_missing" in row["evidence_ref"]
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_prefers_computed_failed_facts_over_missing_watcher_tick():
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "scope_not_attached",
            "detector_attached": True,
            "watcher_tick_present": False,
            "computed": True,
            "failed_facts": ["spread_ok"],
            "mismatch_count": 10,
            "next_action": "produce_scoped_live_observation_or_scope_proposal",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": ["runtime-mpg-op"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    assert row["watcher_state"] == "missing"
    assert row["public_facts_state"]["state"] == "computed_not_satisfied"
    assert row["first_blocker"] == "computed_not_satisfied"
    assert row["next_action"] == "continue_observation_with_failed_fact_matrix"
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_consumes_sor_detector_facts_for_authorized_symbols():
    sor_detector = {
        "status": "sor_session_detector_facts_ready",
        "symbol_detector_rows": [
            {
                "symbol": "ETHUSDT",
                "public_facts_ready": True,
                "latest_candle_close_time_utc": "2026-07-02T00:15:00+00:00",
                "fresh_session_range_signal": False,
                "missing_required_trigger_facts": ["follow_through_confirmed"],
            }
        ],
    }
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-sor-eth"],
                    "selected_runtime_instance_ids": ["runtime-sor-eth"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        sor_detector=sor_detector,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "SOR-001" and item["symbol"] == "ETHUSDT"
    )
    assert row["watcher_state"] == "fresh"
    assert row["public_facts_state"]["state"] == "computed_not_satisfied"
    assert row["first_blocker"] == "computed_not_satisfied"
    assert row["next_action"] == "continue_observation_with_failed_fact_matrix"
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_consumes_mi_trial_admission_symbol_evidence():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        mi_trial_admission=_mi_trial_admission(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MI-001" and item["symbol"] == "AVAXUSDT"
    )
    assert row["detector_state"] == "ready"
    assert row["watcher_state"] == "fresh"
    assert row["public_facts_state"]["state"] == "computed_not_satisfied"
    assert row["public_facts_state"]["computed_not_satisfied"] == [
        "replay_supported",
        "strategy_fit",
    ]
    assert row["first_blocker"] == "computed_not_satisfied"
    assert row["next_action"] == "continue_observation_with_failed_fact_matrix"
    assert "mi_trial_admission_decision:symbol_evidence" in row["evidence_ref"]
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_reclassifies_brf2_runtime_facts_gap_as_watcher_input():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        brf2_runtime_signal_facts=_brf2_missing_runtime_signal_facts(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "BRF2-001" and item["symbol"] == "BTCUSDT"
    )
    assert row["detector_state"] == "ready"
    assert row["watcher_state"] == "missing"
    assert row["public_facts_state"]["state"] == "missing"
    assert row["first_blocker"] == "watcher_tick_missing"
    assert row["next_action"] == "refresh_readonly_watcher_for_candidate_symbol"
    assert "brf2_runtime_signal_facts:missing_watcher_input" in row["evidence_ref"]
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_marks_brf2_uncovered_symbols_as_watcher_input_gap():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        brf2_runtime_signal_facts=_brf2_ready_runtime_signal_facts(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = {
        item["symbol"]: item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "BRF2-001"
    }
    assert rows["BTCUSDT"]["detector_state"] == "ready"
    assert rows["BTCUSDT"]["first_blocker"] == "computed_not_satisfied"
    assert rows["BTCUSDT"]["public_facts_state"]["computed_not_satisfied"] == [
        "rally_context",
        "rally_failure_trigger_state",
        "short_squeeze_risk_state",
    ]
    assert rows["ETHUSDT"]["detector_state"] == "ready"
    assert rows["ETHUSDT"]["first_blocker"] == "watcher_tick_missing"
    assert (
        "brf2_runtime_signal_facts:missing_symbol_fact_input"
        in rows["ETHUSDT"]["evidence_ref"]
    )
    assert rows["AVAXUSDT"]["first_blocker"] == "watcher_tick_missing"
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_consumes_brf2_per_symbol_public_proxy_facts():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        brf2_runtime_signal_facts=_brf2_per_symbol_runtime_signal_facts(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = {
        item["symbol"]: item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "BRF2-001"
    }
    assert set(rows) == {"BTCUSDT", "AVAXUSDT", "ETHUSDT"}
    for row in rows.values():
        assert row["detector_state"] == "ready"
        assert row["watcher_state"] == "fresh"
        assert row["first_blocker"] == "computed_not_satisfied"
        assert row["public_facts_state"]["state"] == "computed_not_satisfied"
        assert "rally_context" in row["public_facts_state"]["computed_not_satisfied"]
        assert "brf2_runtime_signal_facts:per_symbol_facts" in row["evidence_ref"]
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_fails_closed_when_brf2_ready_fact_symbol_is_unknown():
    brf2_facts = _brf2_ready_runtime_signal_facts()
    brf2_facts["signal_context"] = {"symbol": ""}

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        brf2_runtime_signal_facts=brf2_facts,
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    rows = [
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "BRF2-001"
    ]
    assert {row["first_blocker"] for row in rows} == {"watcher_tick_missing"}
    assert all(row["detector_state"] == "ready" for row in rows)
    assert all(
        "brf2_runtime_signal_facts:missing_symbol_fact_input" in row["evidence_ref"]
        for row in rows
    )
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_blocks_fresh_signal_when_action_time_boundary_not_reproduced():
    sor_detector = {
        "status": "sor_session_detector_facts_ready",
        "symbol_detector_rows": [
            {
                "symbol": "ETHUSDT",
                "public_facts_ready": True,
                "latest_candle_close_time_utc": "2026-07-02T00:15:00+00:00",
                "fresh_session_range_signal": True,
                "missing_required_trigger_facts": [],
            }
        ],
    }
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-sor-eth"],
                    "selected_runtime_instance_ids": ["runtime-sor-eth"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        sor_detector=sor_detector,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "SOR-001" and item["symbol"] == "ETHUSDT"
    )
    assert row["signal_state"] == "fresh"
    assert row["public_facts_state"]["state"] == "satisfied"
    assert row["scope_state"] == "live_submit_allowed"
    assert row["first_blocker"] == "action_time_boundary_not_reproduced"
    assert row["promotion_state"] == "idle"
    assert artifact["promotion_candidates"] == []
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_maps_missing_private_action_time_facts_to_contract_blocker():
    sor_detector = {
        "status": "sor_session_detector_facts_ready",
        "symbol_detector_rows": [
            {
                "symbol": "ETHUSDT",
                "public_facts_ready": True,
                "latest_candle_close_time_utc": "2026-07-02T00:15:00+00:00",
                "fresh_session_range_signal": True,
                "missing_required_trigger_facts": [],
            }
        ],
    }
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "action_time_path_ready": True,
            "first_blocker": "private_action_time_facts_required",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": {
                "public_facts_ready": True,
                "private_action_time_facts_ready": False,
            },
        }
    )
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-sor-eth"],
                    "selected_runtime_instance_ids": ["runtime-sor-eth"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=action_time,
        sor_detector=sor_detector,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "SOR-001" and item["symbol"] == "ETHUSDT"
    )
    assert row["signal_state"] == "fresh"
    assert row["public_facts_state"]["state"] == "satisfied"
    assert row["first_blocker"] == "action_time_boundary_not_reproduced"
    assert row["next_action"] == "refresh_private_action_time_facts_before_finalgate"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_blocks_authorized_fresh_signal_without_server_runtime_scope():
    daily_table = json.loads(json.dumps(_daily_table()))
    mpg_daily = next(
        row for row in daily_table["rows"] if row["strategy_group_id"] == "MPG-001"
    )
    mpg_daily["selected_symbol"] = "SOLUSDT"
    mpg_daily["first_blocker"] = "scope_not_attached"
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity.setdefault("per_symbol_mismatch_table", [])
    parity["per_symbol_mismatch_table"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "scope_not_attached",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "produce_scoped_live_observation_or_scope_proposal",
        }
    )

    single_lane = _single_lane()
    single_lane["first_blocker"] = "scope_not_attached"
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=daily_table,
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=single_lane,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        row
        for row in artifact["symbol_readiness_rows"]
        if row["strategy_group_id"] == "MPG-001" and row["symbol"] == "OPUSDT"
    )
    assert row["signal_state"] == "fresh"
    assert row["scope_state"] == "live_submit_allowed"
    assert row["first_blocker"] == "runtime_profile_scope_missing"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert artifact["checks"]["readonly_signal_cannot_order"] is True
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_uses_owner_authorization_for_live_submit_scope():
    tradeability = _tradeability()
    mpg = next(
        row
        for row in tradeability["decision_rows"]
        if row["strategy_group_id"] == "MPG-001"
    )
    mpg["policy_scope"] = {"symbol_scope": ["OPUSDT"]}
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "scope_not_attached",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "produce_scoped_live_observation_or_scope_proposal",
        }
    ]

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        row
        for row in artifact["symbol_readiness_rows"]
        if row["strategy_group_id"] == "MPG-001" and row["symbol"] == "OPUSDT"
    )
    assert row["scope_state"] == "live_submit_allowed"
    assert row["owner_authorization"]["live_submit_allowed"] == "scoped"
    assert row["first_blocker"] == "runtime_profile_scope_missing"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_selects_one_action_time_input_and_defers_the_rest():
    tradeability = _tradeability()
    for strategy_group_id, symbols in {
        "CPM-RO-001": ["SOLUSDT"],
        "MPG-001": ["OPUSDT"],
    }.items():
        row = next(
            item
            for item in tradeability["decision_rows"]
            if item["strategy_group_id"] == strategy_group_id
        )
        row["policy_scope"] = {"live_submit_symbols": symbols}
    action_time = _action_time()
    action_time["strategy_rows"].extend(
        [
            {
                "strategy_group_id": "CPM-RO-001",
                "symbol": "SOLUSDT",
                "action_time_path_ready": True,
                "first_blocker": "private_action_time_facts_required",
                "next_action": "refresh_private_action_time_facts_before_finalgate",
                "required_facts_readiness": _action_time_private_facts_ready(),
            },
            {
                "strategy_group_id": "MPG-001",
                "symbol": "OPUSDT",
                "action_time_path_ready": True,
                "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
                "next_action": "refresh_private_action_time_facts_before_finalgate",
                "required_facts_readiness": _action_time_private_facts_ready(),
            },
        ]
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "SOLUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 13,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "expected_row_count": 2,
            "active_matched_row_count": 2,
            "missing_row_count": 0,
            "rows": [
                {
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "SOLUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-cpm-sol"],
                    "selected_runtime_instance_ids": ["runtime-cpm-sol"],
                    "next_action": "continue_pretrade_observation",
                },
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": ["runtime-mpg-op"],
                    "next_action": "continue_pretrade_observation",
                },
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    assert len(artifact["action_time_lane_inputs"]) == 1
    assert artifact["action_time_lane_inputs"][0]["strategy_group_id"] == "CPM-RO-001"
    assert artifact["action_time_lane_inputs"][0]["symbol"] == "SOLUSDT"
    assert artifact["action_time_lane_inputs"][0]["active_runtime_instance_ids"] == [
        "runtime-cpm-sol"
    ]
    assert artifact["action_time_lane_inputs"][0]["server_runtime_coverage"][
        "state"
    ] == "active_watcher_scope"
    assert artifact["action_time_lane_inputs"][0]["next_action"] == (
        "prepare_non_executing_finalgate_preflight_input"
    )
    assert artifact["action_time_lane_inputs"][0]["action_time"]["status"] == (
        "ready_for_finalgate_preflight"
    )
    assert artifact["action_time_lane_inputs"][0]["public_facts_state"]["state"] == (
        "satisfied"
    )
    selected_rows = [
        row
        for row in artifact["symbol_readiness_rows"]
        if (row["strategy_group_id"], row["symbol"])
        in {("CPM-RO-001", "SOLUSDT"), ("MPG-001", "OPUSDT")}
    ]
    assert {row["first_blocker"] for row in selected_rows} == {
        "market_wait_validated"
    }
    assert artifact["arbitration"]["eligible_action_time_candidate_count"] == 2
    assert artifact["arbitration"]["single_real_submit_candidate"] is True
    assert artifact["arbitration"]["deferred_action_time_candidates"] == [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "side": "long",
            "reason": "deferred_by_single_action_time_candidate_rule",
        }
    ]
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_allows_brf2_conditional_action_time_rehearsal_only():
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "action_time_path_ready": True,
            "first_blocker": "private_action_time_facts_required",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 3,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "symbol": "BTCUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-brf2-btc"],
                    "selected_runtime_instance_ids": ["runtime-brf2-btc"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "BRF2-001" and item["symbol"] == "BTCUSDT"
    )
    assert row["scope_state"] == "conditional_action_time_rehearsal_allowed"
    assert row["owner_authorization"]["live_submit_allowed"] == "conditional_hard_gated"
    assert {"short_side_disable_clear", "squeeze_clear", "liquidity_clear"}.issubset(
        set(row["owner_authorization"]["real_submit_required_gates"])
    )
    assert row["promotion_state"] == "action_time_lane"
    assert artifact["action_time_lane_inputs"][0]["strategy_group_id"] == "BRF2-001"
    assert (
        artifact["action_time_lane_inputs"][0]["scope_state"]
        == "conditional_action_time_rehearsal_allowed"
    )
    assert artifact["checks"]["calls_exchange_write"] is False
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_validator_rejects_brf2_scoped_live_submit_spoof():
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "action_time_path_ready": True,
            "first_blocker": "private_action_time_facts_required",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "BRF2-001",
            "symbol": "BTCUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 3,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "symbol": "BTCUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-brf2-btc"],
                    "selected_runtime_instance_ids": ["runtime-brf2-btc"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = artifact["action_time_lane_inputs"][0]
    row["scope_state"] = "live_submit_allowed"
    row["owner_authorization"]["live_submit_allowed"] = "scoped"

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any(
        "owner_authorization.live_submit_allowed must be conditional_hard_gated"
        in error
        for error in errors
    )
    assert any(
        "scope_state must be conditional_action_time_rehearsal_allowed" in error
        for error in errors
    )


def test_candidate_pool_validator_rejects_action_time_input_with_unresolved_blocker():
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": ["runtime-mpg-op"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    row["first_blocker"] = "action_time_boundary_not_reproduced"
    artifact["action_time_lane_inputs"][0][
        "first_blocker"
    ] = "action_time_boundary_not_reproduced"

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("action_time_lane has unresolved blocker" in error for error in errors)
    assert any(
        "action_time_lane_inputs[0] has unresolved blocker" in error
        for error in errors
    )

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    row["first_blocker"] = "active_position_resolution"
    artifact["action_time_lane_inputs"][0]["first_blocker"] = (
        "active_position_resolution"
    )

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("action_time_lane has unresolved blocker" in error for error in errors)
    assert any(
        "action_time_lane_inputs[0] has unresolved blocker" in error
        for error in errors
    )


def test_candidate_pool_blocks_action_time_when_active_position_resolution_needed():
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "resolve_active_position_or_open_order_before_submit",
            "required_facts_readiness": {
                "public_facts_ready": True,
                "private_action_time_facts_ready": True,
            },
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        }
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": ["runtime-mpg-op"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    assert row["signal_state"] == "fresh"
    assert row["scope_state"] == "live_submit_allowed"
    assert row["public_facts_state"]["state"] == "satisfied"
    assert row["first_blocker"] == "active_position_resolution"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_blocks_action_time_when_server_runtime_scope_missing():
    tradeability = _tradeability()
    row = next(
        item
        for item in tradeability["decision_rows"]
        if item["strategy_group_id"] == "MPG-001"
    )
    row["policy_scope"] = {"live_submit_symbols": ["OPUSDT"]}
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "incomplete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "runtime_profile_scope_missing",
                    "blocker_class": "runtime_profile_scope_missing",
                    "active_runtime_instance_ids": [],
                    "selected_runtime_instance_ids": [],
                    "next_action": (
                        "bind_or_start_pretrade_runtime_for_candidate_symbol"
                    ),
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    assert row["first_blocker"] == "runtime_profile_scope_missing"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_blocks_action_time_when_server_runtime_coverage_absent():
    tradeability = _tradeability()
    row = next(
        item
        for item in tradeability["decision_rows"]
        if item["strategy_group_id"] == "MPG-001"
    )
    row["policy_scope"] = {"live_submit_symbols": ["OPUSDT"]}
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
    ]

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor={"candidate_universe_coverage": {"rows": []}},
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    assert row["first_blocker"] == "runtime_profile_scope_missing"
    assert row["promotion_state"] == "idle"
    assert row["evidence_ref"].endswith(
        "MPG-001/OPUSDT first_blocker=runtime_profile_scope_missing"
    )
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_blocks_action_time_when_runtime_not_selected():
    tradeability = _tradeability()
    row = next(
        item
        for item in tradeability["decision_rows"]
        if item["strategy_group_id"] == "MPG-001"
    )
    row["policy_scope"] = {"live_submit_symbols": ["OPUSDT"]}
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "incomplete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": [],
                    "next_action": "select_pretrade_runtime_for_action_time_symbol",
                }
            ],
        }
    }

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    assert row["first_blocker"] == "runtime_profile_scope_missing"
    assert row["promotion_state"] == "idle"
    assert artifact["action_time_lane_inputs"] == []
    assert _validator().validate_strategy_live_candidate_pool(artifact) == []


def test_candidate_pool_validator_rejects_action_time_without_server_runtime_scope():
    tradeability = _tradeability()
    for item in tradeability["decision_rows"]:
        if item["strategy_group_id"] == "MPG-001":
            item["policy_scope"] = {"live_submit_symbols": ["OPUSDT"]}
    action_time = _action_time()
    action_time["strategy_rows"].append(
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "action_time_path_ready": True,
            "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
            "next_action": "refresh_private_action_time_facts_before_finalgate",
            "required_facts_readiness": _action_time_private_facts_ready(),
        }
    )
    parity = _parity()
    parity["per_symbol_mismatch_table"] = [
        {
            "strategy_group_id": "MPG-001",
            "symbol": "OPUSDT",
            "blocker_class": "market_wait_validated",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": [],
            "mismatch_count": 10,
            "next_action": "wait_for_fresh_signal_or_refresh_action_time_facts",
        },
    ]
    runtime_active_monitor = {
        "candidate_universe_coverage": {
            "status": "complete",
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "state": "active_watcher_scope",
                    "blocker_class": "none",
                    "active_runtime_instance_ids": ["runtime-mpg-op"],
                    "selected_runtime_instance_ids": ["runtime-mpg-op"],
                    "next_action": "continue_pretrade_observation",
                }
            ],
        }
    }
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    row["server_runtime_coverage"] = {}
    artifact["action_time_lane_inputs"][0]["server_runtime_coverage"] = {}
    artifact["action_time_lane_inputs"][0]["active_runtime_instance_ids"] = []
    artifact["action_time_lane_inputs"][0]["selected_runtime_instance_ids"] = []

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("action_time_lane requires active server runtime coverage" in error for error in errors)
    assert any("action_time_lane_inputs[0] requires active server runtime coverage" in error for error in errors)

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    row["server_runtime_coverage"]["symbol"] = "SOLUSDT"
    artifact["action_time_lane_inputs"][0]["server_runtime_coverage"][
        "strategy_group_id"
    ] = "SOR-001"

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any(
        "server_runtime_coverage.symbol must match row symbol" in error
        for error in errors
    )
    assert any(
        "server_runtime_coverage.strategy_group_id must match row strategy_group_id"
        in error
        for error in errors
    )

    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=tradeability,
        replay_live_parity=parity,
        action_time_boundary=action_time,
        single_lane_task_packet=_single_lane(),
        runtime_active_monitor=runtime_active_monitor,
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    row = next(
        item
        for item in artifact["symbol_readiness_rows"]
        if item["strategy_group_id"] == "MPG-001" and item["symbol"] == "OPUSDT"
    )
    row["server_runtime_coverage"]["selected_runtime_instance_ids"] = []
    artifact["action_time_lane_inputs"][0]["server_runtime_coverage"][
        "selected_runtime_instance_ids"
    ] = []
    artifact["action_time_lane_inputs"][0]["selected_runtime_instance_ids"] = []

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("action_time_lane requires active server runtime coverage" in error for error in errors)
    assert any("action_time_lane_inputs[0] requires active server runtime coverage" in error for error in errors)


def test_candidate_pool_no_stale_facts_waives_blocked_public_facts_with_reason():
    daily_table = json.loads(json.dumps(_daily_table()))
    for row in daily_table["rows"]:
        row["first_blocker"] = "computed_not_satisfied"
        row["next_engineering_action"] = "continue_observation_with_failed_fact_matrix"
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=daily_table,
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )

    review = {row["item"]: row for row in artifact["p0_p1_review"]}
    assert review["no_stale_facts"]["status"] == "waived_with_reason"
    assert "action-time public facts are not cleared" in review["no_stale_facts"]["evidence"]
    assert artifact["summary"]["p1_cleared_or_waived"] is True


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


def test_action_time_readiness_requires_public_facts_for_finalgate_preflight():
    readiness = _builder()._action_time_readiness(
        {
            "action_time_path_ready": True,
            "required_facts_readiness": {
                "public_facts_ready": False,
                "private_action_time_facts_ready": True,
                "active_position_or_open_order_clear": True,
                "action_time_available_balance": True,
            },
        }
    )

    assert readiness["status"] == "blocked_public_facts"
    assert readiness["public_facts_ready"] is False
    assert readiness["private_action_time_facts_ready"] is True


def test_candidate_pool_validator_rejects_preflight_ready_without_public_facts():
    artifact = _builder().build_strategy_live_candidate_pool(
        daily_table=_daily_table(),
        tradeability=_tradeability(),
        replay_live_parity=_parity(),
        action_time_boundary=_action_time(),
        single_lane_task_packet=_single_lane(),
        generated_at_utc="2026-07-01T00:00:00+00:00",
    )
    artifact["candidate_rows"][0]["action_time_readiness"] = {
        "status": "ready_for_finalgate_preflight",
        "action_time_path_ready": True,
        "public_facts_ready": False,
        "private_action_time_facts_ready": True,
    }

    errors = _validator().validate_strategy_live_candidate_pool(artifact)

    assert any("public_facts_ready" in error for error in errors)


def test_candidate_pool_cli_and_validator_cli_round_trip(tmp_path: Path):
    daily = tmp_path / "daily.json"
    tradeability = tmp_path / "tradeability.json"
    parity = tmp_path / "parity.json"
    action_time = tmp_path / "action_time.json"
    mi_trial = tmp_path / "mi_trial.json"
    brf2_facts = tmp_path / "brf2_facts.json"
    single_lane = tmp_path / "single_lane.json"
    output_json = tmp_path / "candidate_pool.json"
    output_md = tmp_path / "candidate_pool.md"
    daily.write_text(json.dumps(_daily_table()), encoding="utf-8")
    tradeability.write_text(json.dumps(_tradeability()), encoding="utf-8")
    parity.write_text(json.dumps(_parity()), encoding="utf-8")
    action_time.write_text(json.dumps(_action_time()), encoding="utf-8")
    mi_trial.write_text(json.dumps({}), encoding="utf-8")
    brf2_facts.write_text(json.dumps({}), encoding="utf-8")
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
            "--mi-trial-admission-json",
            str(mi_trial),
            "--brf2-runtime-signal-facts-json",
            str(brf2_facts),
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
