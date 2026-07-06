from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from scripts import runtime_active_observation_monitor


class _FakeClient:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {"http_status": 200, "body": self.items}


def _args(**overrides):
    values = {
        "env_file": None,
        "api_base": "http://unit",
        "source": "live_market",
        "include_exchange": False,
        "allow_prepare_records": False,
        "runtime_instance_id": [],
        "strategy_family_id": [],
        "database_url": "sqlite://",
        "require_database_url": True,
        "allow_non_postgres_for_test": True,
        "max_runtimes": 100,
        "max_cycles_per_runtime": 1,
        "interval_seconds": 0.0,
        "continue_on_blocked": False,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "timeout_seconds": 10.0,
        "playbook_id": None,
        "include_runtime_artifacts": False,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-unit",
        "reason": "unit test",
    }
    values.update(overrides)
    return type("Args", (), values)()


@pytest.fixture(autouse=True)
def _default_pg_candidate_scope(monkeypatch):
    def fake_pg_candidate_universe(*, database_url, allow_non_postgres_for_test):
        assert database_url
        assert allow_non_postgres_for_test is True
        return {}, {
            "source": "pg_runtime_control_state:candidate_scope",
            "loaded": False,
            "strategy_group_count": 0,
            "side_scope": {},
            "source_mode": "db_backed",
            "projection_target": "production_current",
        }

    monkeypatch.setattr(
        runtime_active_observation_monitor,
        "_read_candidate_universe_from_pg",
        fake_pg_candidate_universe,
    )


def _patch_pg_candidate_scope(
    monkeypatch,
    *,
    universe: dict[str, list[str]],
    side_scope: dict[str, list[str]] | None = None,
) -> None:
    def fake_pg_candidate_universe(*, database_url, allow_non_postgres_for_test):
        assert database_url
        assert allow_non_postgres_for_test is True
        return universe, {
            "source": "pg_runtime_control_state:candidate_scope",
            "loaded": bool(universe),
            "strategy_group_count": len(universe),
            "side_scope": side_scope or {},
            "source_mode": "db_backed",
            "projection_target": "production_current",
        }

    monkeypatch.setattr(
        runtime_active_observation_monitor,
        "_read_candidate_universe_from_pg",
        fake_pg_candidate_universe,
    )


def _runtime(
    runtime_id,
    *,
    status="active",
    symbol="AVAX/USDT:USDT",
    side="short",
    strategy_family_id="BTPC-001",
    strategy_family_version_id="BTPC-001-v0",
    **extra,
):
    payload = {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": symbol,
        "side": side,
        "strategy_family_id": strategy_family_id,
        "strategy_family_version_id": strategy_family_version_id,
    }
    payload.update(extra)
    return payload


def test_active_monitor_runs_only_active_runtimes_without_side_effects(tmp_path):
    client = _FakeClient(
        [
            _runtime("runtime-active-1"),
            _runtime("runtime-revoked", status="revoked"),
            _runtime("runtime-active-2", symbol="BNB/USDT:USDT", side="long"),
        ]
    )
    seen = []

    def builder(args):
        seen.append(
            {
                "runtime_instance_id": args.runtime_instance_id,
                "symbol": args.symbol,
                "side": args.side,
                "allow_prepare_records": args.allow_prepare_records,
                "four_hour_limit": args.four_hour_limit,
            }
        )
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": {
                            "status": "observe_only",
                            "evaluator_id": "BTPC001PriceActionEvaluator",
                            "can_call_semantic_binding": False,
                            "semantics_binding_found": True,
                            "strategy_candidate_mode": (
                                "shadow_order_candidate_allowed"
                            ),
                            "output": {
                                "signal_type": "no_action",
                                "required_execution_mode": "observe_only",
                                "side": "none",
                                "reason_codes": [
                                    (
                                        "btpc_no_action_no_bear_pullback_"
                                        "continuation"
                                    )
                                ],
                                "human_summary": (
                                    "BTPC v0 did not confirm bear-trend "
                                    "pullback continuation."
                                ),
                                "confidence": "0.25",
                                "timestamp_ms": 1781197200000,
                                "data_quality": {"status": "ok"},
                                "signal_snapshot": {
                                    "context_tags": {
                                        "market_state": "TREND_DOWN",
                                        "entry_pattern": "none",
                                    }
                                },
                            },
                        }
                    }
                }
            },
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert [item["runtime_instance_id"] for item in seen] == [
        "runtime-active-1",
        "runtime-active-2",
    ]
    assert {item["four_hour_limit"] for item in seen} == {25}
    assert packet["status"] == "waiting_for_signal"
    assert packet["active_runtime_count"] == 2
    assert packet["monitored_runtime_count"] == 2
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert "operator_command_plan" not in packet
    assert packet["observation_monitor_plan"]["places_order"] is False
    assert {
        summary["runtime_instance_id"] for summary in packet["runtime_summaries"]
    } == {"runtime-active-1", "runtime-active-2"}
    signal_summary = packet["runtime_summaries"][0]["signal_summary"]
    assert signal_summary["evaluation_status"] == "observe_only"
    assert signal_summary["reason_codes"] == [
        "btpc_no_action_no_bear_pullback_continuation"
    ]
    assert signal_summary["human_summary"].startswith("BTPC v0")
    assert signal_summary["context_tags"]["market_state"] == "TREND_DOWN"


def test_active_monitor_can_filter_specific_active_runtimes(tmp_path):
    client = _FakeClient(
        [
            _runtime("runtime-ada", symbol="ADA/USDT:USDT", side="short"),
            _runtime("runtime-bnb", symbol="BNB/USDT:USDT", side="long"),
            _runtime("runtime-avax", symbol="AVAX/USDT:USDT", side="short"),
        ]
    )
    seen = []

    def builder(args):
        seen.append(args.runtime_instance_id)
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            runtime_instance_id=["runtime-ada", "runtime-avax"],
        ),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert seen == ["runtime-ada", "runtime-avax"]
    assert packet["active_runtime_count"] == 3
    assert packet["monitored_runtime_count"] == 2
    assert packet["requested_runtime_instance_ids"] == ["runtime-ada", "runtime-avax"]
    assert packet["selected_runtime_instance_ids"] == ["runtime-ada", "runtime-avax"]
    assert packet["status"] == "waiting_for_signal"
    assert packet["warnings"] == []


def test_active_monitor_can_filter_by_strategy_family(tmp_path):
    client = _FakeClient(
        [
            _runtime(
                "runtime-mpg",
                strategy_family_id="MPG-001",
                strategy_family_version_id="MPG-001-v0",
            ),
            _runtime(
                "runtime-teq",
                strategy_family_id="TEQ-001",
                strategy_family_version_id="TEQ-001-v0",
            ),
            _runtime(
                "runtime-legacy",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
            ),
        ]
    )
    seen = []

    def builder(args):
        seen.append((args.runtime_instance_id, args.strategy_family_id))
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(strategy_family_id=["MPG-001", "TEQ-001"]),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert seen == [("runtime-mpg", "MPG-001"), ("runtime-teq", "TEQ-001")]
    assert packet["active_runtime_count"] == 3
    assert packet["monitored_runtime_count"] == 2
    assert packet["requested_strategy_family_ids"] == ["MPG-001", "TEQ-001"]
    assert packet["selected_runtime_instance_ids"] == ["runtime-mpg", "runtime-teq"]


def test_active_monitor_candidate_universe_filters_legacy_strategy_symbols(
    tmp_path,
    monkeypatch,
):
    _patch_pg_candidate_scope(
        monkeypatch,
        universe={
            "MPG-001": ["OPUSDT", "SOLUSDT"],
            "SOR-001": ["ETHUSDT"],
        },
        side_scope={
            "MPG-001": ["long"],
            "SOR-001": ["long"],
        },
    )
    client = _FakeClient(
        [
            _runtime(
                "runtime-mpg-op",
                strategy_family_id="MPG-001",
                strategy_family_version_id="MPG-001-v0",
                symbol="OP/USDT:USDT",
                side="long",
            ),
            _runtime(
                "runtime-mpg-coin",
                strategy_family_id="MPG-001",
                strategy_family_version_id="MPG-001-v0",
                symbol="COIN/USDT:USDT",
                side="long",
            ),
            _runtime(
                "runtime-sor-eth",
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                symbol="ETH/USDT:USDT",
                side="long",
            ),
            _runtime(
                "runtime-sor-xag",
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                symbol="XAG/USDT:USDT",
                side="long",
            ),
        ]
    )
    seen = []

    def builder(args):
        seen.append(args.runtime_instance_id)
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            strategy_family_id=["MPG-001", "SOR-001"],
        ),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert seen == ["runtime-mpg-op", "runtime-sor-eth"]
    assert packet["active_runtime_count"] == 4
    assert packet["monitored_runtime_count"] == 2
    assert packet["selected_runtime_instance_ids"] == [
        "runtime-mpg-op",
        "runtime-sor-eth",
    ]
    assert packet["candidate_universe_excluded_runtime_instance_ids"] == [
        "runtime-mpg-coin",
        "runtime-sor-xag",
    ]
    assert (
        "runtime_excluded_by_candidate_universe:runtime-mpg-coin"
        in packet["warnings"]
    )
    assert packet["candidate_universe_coverage"]["active_matched_row_count"] == 2
    assert packet["candidate_universe_coverage"]["missing_row_count"] == 1


def test_active_monitor_reports_candidate_universe_runtime_scope_gaps(
    tmp_path,
    monkeypatch,
):
    _patch_pg_candidate_scope(
        monkeypatch,
        universe={
            "MPG-001": ["OPUSDT", "SOLUSDT"],
            "BRF2-001": ["BTCUSDT"],
            "SOR-001": ["ETHUSDT"],
        },
        side_scope={
            "MPG-001": ["long"],
            "BRF2-001": ["short"],
            "SOR-001": ["long"],
        },
    )
    client = _FakeClient(
        [
            _runtime(
                "runtime-mpg-sol",
                strategy_family_id="MPG-001",
                strategy_family_version_id="MPG-001-v0",
                symbol="SOL/USDT:USDT",
                side="long",
            ),
            _runtime(
                "runtime-sor-eth",
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                symbol="ETH/USDT:USDT",
                side="long",
            ),
        ]
    )

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            strategy_family_id=["MPG-001", "SOR-001"],
        ),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    coverage = packet["candidate_universe_coverage"]
    rows = {
        (row["strategy_group_id"], row["symbol"], row["side"]): row
        for row in coverage["rows"]
    }
    assert coverage["status"] == "incomplete"
    assert coverage["expected_row_count"] == 4
    assert coverage["active_matched_row_count"] == 2
    assert rows[("MPG-001", "SOLUSDT", "long")]["state"] == "active_watcher_scope"
    assert rows[("SOR-001", "ETHUSDT", "long")]["state"] == "active_watcher_scope"
    assert rows[("MPG-001", "OPUSDT", "long")]["blocker_class"] == (
        "runtime_profile_scope_missing"
    )
    assert (
        "candidate_universe_runtime_profile_scope_missing:MPG-001:OPUSDT"
        in packet["warnings"]
    )
    assert packet["observation_monitor_plan"][
        "candidate_universe_coverage_status"
    ] == "incomplete"
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_active_monitor_candidate_universe_from_pg_control_state_seed():
    control_state = {
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "candidate_scope": [
            {
                "strategy_group_id": strategy_group_id,
                "symbol": symbol,
                "side": side,
                "status": "active",
            }
            for strategy_group_id, symbols, sides in (
                (
                    "CPM-RO-001",
                    ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
                    ("long",),
                ),
                (
                    "MPG-001",
                    ("OPUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
                    ("long",),
                ),
                (
                    "MI-001",
                    ("AVAXUSDT", "ETHUSDT", "SOLUSDT"),
                    ("long",),
                ),
                (
                    "SOR-001",
                    ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
                    ("long", "short"),
                ),
                (
                    "BRF2-001",
                    ("BTCUSDT", "AVAXUSDT", "ETHUSDT"),
                    ("short",),
                ),
            )
            for symbol in symbols
            for side in sides
        ],
    }
    universe, source = (
        runtime_active_observation_monitor._candidate_universe_from_control_state(
            control_state
        )
    )

    assert source["source"] == "pg_runtime_control_state:candidate_scope"
    assert source["source_mode"] == "db_backed"
    assert universe["CPM-RO-001"] == ["AVAXUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT"]
    assert universe["SOR-001"] == ["AVAXUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert source["side_scope"]["CPM-RO-001"] == ["long"]
    assert source["side_scope"]["MPG-001"] == ["long"]
    assert source["side_scope"]["MI-001"] == ["long"]
    assert source["side_scope"]["SOR-001"] == ["long", "short"]
    assert source["side_scope"]["BRF2-001"] == ["short"]


def test_active_monitor_requires_pg_candidate_universe_when_requested():
    with pytest.raises(RuntimeError, match="PG_DATABASE_URL is required"):
        runtime_active_observation_monitor._candidate_universe_for_args(
            _args(database_url="", require_database_url=True)
        )


def test_active_monitor_cli_rejects_candidate_universe_json():
    with pytest.raises(SystemExit) as exc:
        runtime_active_observation_monitor._parse_args(
            [
                "--api-base",
                "http://unit",
                "--candidate-universe-json",
                "candidate-pool.json",
            ]
        )

    assert exc.value.code == 2


def test_active_monitor_records_side_specific_candidate_universe_coverage(
    tmp_path,
    monkeypatch,
):
    _patch_pg_candidate_scope(
        monkeypatch,
        universe={"SOR-001": ["ETHUSDT"]},
        side_scope={"SOR-001": ["long", "short"]},
    )
    client = _FakeClient(
        [
            _runtime(
                "runtime-sor-eth-short",
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                symbol="ETH/USDT:USDT",
                side="short",
            ),
        ]
    )

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            strategy_family_id=["SOR-001"],
        ),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    coverage = packet["candidate_universe_coverage"]
    row = coverage["rows"][0]
    assert packet["monitored_runtime_count"] == 1
    assert packet["candidate_universe_excluded_runtime_instance_ids"] == []
    assert coverage["status"] == "incomplete"
    assert coverage["active_matched_row_count"] == 1
    rows = {(item["symbol"], item["side"]): item for item in coverage["rows"]}
    long_row = rows[("ETHUSDT", "long")]
    short_row = rows[("ETHUSDT", "short")]
    assert long_row["state"] == "runtime_profile_scope_missing"
    assert long_row["matched_runtime_sides"] == ["short"]
    assert long_row["side_mismatch_runtime_instance_ids"] == [
        "runtime-sor-eth-short"
    ]
    assert long_row["next_action"] == "bind_or_repair_runtime_profile_scope_side"
    assert short_row["state"] == "active_watcher_scope"
    assert short_row["active_runtime_instance_ids"] == ["runtime-sor-eth-short"]


def test_active_monitor_writes_candidate_universe_coverage_to_pg(tmp_path):
    db_path = tmp_path / "runtime.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE brc_watcher_runtime_coverage (
              runtime_coverage_id TEXT PRIMARY KEY,
              strategy_group_id TEXT,
              symbol TEXT,
              side TEXT,
              detector_key TEXT,
              runtime_profile_id TEXT,
              coverage_state TEXT,
              liveness_state TEXT,
              last_tick_at_ms INTEGER,
              valid_until_ms INTEGER,
              is_current BOOLEAN,
              created_at_ms INTEGER
            )
            """
        )

    artifact = {
        "candidate_universe_coverage": {
            "rows": [
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "OPUSDT",
                    "side": "long",
                    "state": "active_watcher_scope",
                    "runtime_profile": {
                        "runtime_profile_id": "owner-runtime-console-v1"
                    },
                },
                {
                    "strategy_group_id": "BRF2-001",
                    "symbol": "BTCUSDT",
                    "side": "short",
                    "state": "runtime_profile_scope_missing",
                    "runtime_profile": {},
                },
            ]
        }
    }

    result = runtime_active_observation_monitor.write_candidate_universe_coverage_to_pg(
        artifact,
        database_url=f"sqlite:///{db_path}",
        allow_non_postgres_for_test=True,
        now_ms=1770000000000,
    )

    assert result["status"] == "pg_watcher_runtime_coverage_written"
    assert result["written_count"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT strategy_group_id, symbol, side, detector_key, runtime_profile_id,
                   coverage_state, liveness_state, last_tick_at_ms, is_current
            FROM brc_watcher_runtime_coverage
            ORDER BY strategy_group_id, symbol, side
            """
        ).fetchall()
    assert rows == [
        (
            "BRF2-001",
            "BTCUSDT",
            "short",
            "runtime_active_observation_monitor",
            None,
            "missing",
            "missing",
            1770000000000,
            1,
        ),
        (
            "MPG-001",
            "OPUSDT",
            "long",
            "runtime_active_observation_monitor",
            "owner-runtime-console-v1",
            "covered",
            "active",
            1770000000000,
            1,
        ),
    ]


def test_active_monitor_cli_rejects_strategy_handoff_dir():
    with pytest.raises(SystemExit) as exc:
        runtime_active_observation_monitor._parse_args(
            [
                "--api-base",
                "http://unit",
                "--strategy-handoff-dir",
                "docs/current/strategy-group-handoffs",
            ]
        )

    assert exc.value.code == 2


def test_active_monitor_cli_does_not_expose_handoff_file_authority():
    args = runtime_active_observation_monitor._parse_args(
        ["--api-base", "http://unit"]
    )

    assert not hasattr(args, "strategy_handoff_dir")
    assert not hasattr(args, "allow_local_file_diagnostic")


def test_active_monitor_projects_runtime_profile_boundary_for_runtime_scope(
    tmp_path,
    monkeypatch,
):
    _patch_pg_candidate_scope(
        monkeypatch,
        universe={"SOR-001": ["SOLUSDT"]},
        side_scope={"SOR-001": ["long"]},
    )
    client = _FakeClient(
        [
            _runtime(
                "runtime-sor-sol-long",
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                symbol="SOL/USDT:USDT",
                side="long",
                runtime_profile={
                    "runtime_profile_id": "profile:sor-sol-long",
                    "max_notional_per_action_usdt": "8",
                    "max_leverage": "1",
                },
            ),
        ]
    )

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            strategy_family_id=["SOR-001"],
        ),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    rows = {
        (item["symbol"], item["side"]): item
        for item in packet["candidate_universe_coverage"]["rows"]
    }
    profile = rows[("SOLUSDT", "long")]["runtime_profile"]
    assert rows[("SOLUSDT", "long")]["state"] == "active_watcher_scope"
    assert profile["max_notional"] == "8"
    assert profile["leverage"] == "1"
    assert profile["runtime_profile_id"] == "profile:sor-sol-long"
    assert profile["profile_source"] == "runtime"
    assert profile["authority_boundary"] == (
        "runtime_profile_projection_only; no_live_profile_or_sizing_change"
    )


def test_active_monitor_downgrades_non_actionable_historical_observation_blockers(
    tmp_path,
):
    client = _FakeClient(
        [
            _runtime("runtime-old-exhausted", strategy_family_id="MPG-001"),
            _runtime("runtime-waiting", strategy_family_id="TEQ-001"),
        ]
    )

    def builder(args):
        if args.runtime_instance_id == "runtime-old-exhausted":
            return {
                "status": "blocked",
                "ready_for_prepare": False,
                "ready_for_final_gate_preflight": False,
                "blockers": [
                    "runtime_attempts_exhausted",
                    "order_candidate_id_or_authorization_id_required",
                ],
                "warnings": [],
                "observation_cycle_plan": {"next_step": "resolve"},
                "safety_invariants": {
                    "prepare_records_created": False,
                    "exchange_write_called": False,
                    "order_created": False,
                    "order_lifecycle_called": False,
                    "attempt_counter_mutated": False,
                    "runtime_budget_mutated": False,
                },
            }
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["blockers"] == []
    old_summary = packet["runtime_summaries"][0]
    assert old_summary["status"] == "waiting_for_signal"
    assert old_summary["blockers"] == []
    assert (
        "non_actionable_observation_blocker:runtime_attempts_exhausted"
        in old_summary["warnings"]
    )
    assert "operator_command_plan" not in packet
    assert packet["observation_monitor_plan"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_active_monitor_downgrades_observe_only_stop_reference_gap(tmp_path):
    client = _FakeClient(
        [
            _runtime(
                "runtime-teq",
                strategy_family_id="TEQ-001",
                strategy_family_version_id="TEQ-001-v0",
                side="long",
                symbol="INTC/USDT:USDT",
            )
        ]
    )

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "blocked",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": [
                "strategy_stop_reference_unavailable",
                "order_candidate_id_or_authorization_id_required",
            ],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "resolve"},
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": {
                            "status": "ready_for_semantic_binding",
                            "evaluator_id": "TEQ001PilotReferenceEvaluator",
                            "can_call_semantic_binding": True,
                            "semantics_binding_found": True,
                            "strategy_candidate_mode": (
                                "shadow_order_candidate_allowed"
                            ),
                            "output": {
                                "signal_type": "would_enter",
                                "required_execution_mode": "observe_only",
                                "side": "long",
                                "reason_codes": ["teq_breakout_close_confirmed"],
                                "human_summary": "TEQ observe-only would-enter.",
                                "confidence": "0.62",
                                "timestamp_ms": 1781920800000,
                                "data_quality": {"status": "ok"},
                                "signal_snapshot": {
                                    "context_tags": {
                                        "market_state": "TREND_UP",
                                        "entry_pattern": (
                                            "equity_like_momentum_breakout"
                                        ),
                                    }
                                },
                            },
                        }
                    }
                }
            },
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
            },
        },
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["blockers"] == []
    summary = packet["runtime_summaries"][0]
    assert summary["status"] == "waiting_for_signal"
    assert summary["blockers"] == []
    assert (
        "non_actionable_observation_blocker:strategy_stop_reference_unavailable"
        in summary["warnings"]
    )
    assert (
        "non_actionable_observation_blocker:order_candidate_id_or_authorization_id_required"
        in summary["warnings"]
    )
    assert "operator_command_plan" not in packet
    assert packet["observation_monitor_plan"]["places_order"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_active_monitor_keeps_stop_reference_gap_hard_when_not_observe_only(tmp_path):
    client = _FakeClient(
        [
            _runtime(
                "runtime-live",
                strategy_family_id="MPG-001",
                strategy_family_version_id="MPG-001-v0",
                side="long",
            )
        ]
    )

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "blocked",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_stop_reference_unavailable"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "resolve"},
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": {
                            "status": "ready_for_semantic_binding",
                            "output": {
                                "signal_type": "would_enter",
                                "required_execution_mode": "live",
                                "side": "long",
                            },
                        }
                    }
                }
            },
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    assert packet["status"] == "blocked"
    assert packet["blockers"] == [
        "runtime-live:strategy_stop_reference_unavailable"
    ]


def test_active_monitor_keeps_non_actionable_blocker_hard_after_order_side_effect(
    tmp_path,
):
    client = _FakeClient([_runtime("runtime-prepared", strategy_family_id="MPG-001")])

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "blocked",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["order_candidate_id_or_authorization_id_required"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "resolve"},
            "safety_invariants": {
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "exchange_write_called": False,
                "order_created": True,
                "order_lifecycle_called": False,
            },
        },
    )

    assert packet["status"] == "blocked"
    assert packet["blockers"] == [
        "runtime-prepared:order_candidate_id_or_authorization_id_required"
    ]


def test_active_monitor_reports_missing_requested_runtime_as_warning(tmp_path):
    client = _FakeClient([_runtime("runtime-ada", symbol="ADA/USDT:USDT")])

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(
            runtime_instance_id=["runtime-ada", "runtime-missing"],
        ),
        client=client,
        runtime_artifact_builder=lambda args: {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": [],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["monitored_runtime_count"] == 1
    assert packet["selected_runtime_instance_ids"] == ["runtime-ada"]
    assert packet["warnings"] == [
        "requested_runtime_not_active_or_not_found:runtime-missing"
    ]


def test_active_monitor_allows_prepare_records_only_when_explicit():
    client = _FakeClient([_runtime("runtime-active-1")])

    def builder(args):
        assert args.allow_prepare_records is True
        return {
            "status": "ready_for_final_gate_preflight",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": True,
            "blockers": [],
            "warnings": [],
            "observation_cycle_plan": {
                "prepared_authorization_id": "auth-1",
                "signal_input_json": "/tmp/signal.json",
            },
            "safety_invariants": {
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "executable_execution_intent_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(allow_prepare_records=True),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert "operator_command_plan" not in packet
    assert packet["observation_monitor_plan"]["creates_shadow_candidate"] is True
    assert packet["observation_monitor_plan"]["creates_execution_intent"] is False
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"]["recorded_execution_intent_created"] is True
    assert packet["safety_invariants"]["executable_execution_intent_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    summary = packet["runtime_summaries"][0]
    assert summary["created_records"] == {
        "shadow_candidate_created": True,
        "runtime_execution_intent_draft_created": True,
        "recorded_execution_intent_created": True,
        "submit_authorization_created": True,
        "protection_plan_created": True,
        "executable_execution_intent_created": False,
    }
    assert summary["forbidden_effects"]["order_lifecycle_called"] is False


def test_active_monitor_preserves_signal_input_when_prepare_records_need_candidate_authorization(tmp_path):
    client = _FakeClient([_runtime("runtime-active-1")])
    signal_path = tmp_path / "signal-input.json"

    def builder(args):
        return {
            "status": "blocked",
            "blocked_stage": None,
            "signal_input_json": str(signal_path),
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["order_candidate_id_or_authorization_id_required"],
            "warnings": ["runtime_live_execution_enabled_operation_layer_handoff"],
            "api_prepare_plan": {
                "next_step": "resolve_prepare_blockers",
                "signal_input_json": str(signal_path),
                "not_executed": True,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "latest_artifact": {
                "observation_payload": {
                    "signal_artifact": {
                        "evaluation_result": {
                            "status": "ready_for_semantic_binding",
                            "can_call_semantic_binding": True,
                            "semantics_binding_found": True,
                            "strategy_candidate_mode": (
                                "shadow_order_candidate_allowed"
                            ),
                            "output": {
                                "signal_type": "would_enter",
                                "required_execution_mode": "observe_only",
                                "side": "long",
                                "reason_codes": ["mpg_breakout_close_confirmed"],
                                "human_summary": "MPG-001 v0 signal detected.",
                                "confidence": "0.61",
                                "data_quality": {"status": "ok"},
                            },
                        },
                    },
                },
            },
            "safety_invariants": {
                "prepare_records_created": False,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": False,
                "recorded_execution_intent_created": False,
                "submit_authorization_created": False,
                "protection_plan_created": False,
                "executable_execution_intent_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(allow_prepare_records=True),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert packet["status"] == "ready_for_prepare"
    assert packet["blockers"] == []
    assert packet["observation_monitor_plan"]["signal_input_json"] == str(signal_path)
    assert packet["observation_monitor_plan"]["creates_execution_intent"] is False
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    summary = packet["runtime_summaries"][0]
    assert summary["status"] == "ready_for_prepare"
    assert summary["signal_input_json"] == str(signal_path)
    assert summary["blockers"] == []
    assert summary["signal_summary"]["signal_type"] == "would_enter"


def test_active_monitor_clamps_timeout_to_observation_api_limit(tmp_path):
    client = _FakeClient([_runtime("runtime-active-1")])
    seen = []

    def builder(args):
        seen.append(args.timeout_seconds)
        return {
            "status": "waiting_for_signal",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
            "blockers": ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            "warnings": [],
            "observation_cycle_plan": {"next_step": "wait"},
            "safety_invariants": {
                "prepare_records_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        }

    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(timeout_seconds=120.0),
        client=client,
        runtime_artifact_builder=builder,
    )

    assert seen == [60.0]
    assert packet["requested_timeout_seconds"] == 120.0
    assert packet["effective_observation_timeout_seconds"] == 60.0
    assert packet["warnings"] == [
        "observation_timeout_seconds_clamped_to_api_max_60"
    ]


def test_active_monitor_handles_no_active_runtimes():
    packet = runtime_active_observation_monitor._build_monitor_artifact(
        _args(),
        client=_FakeClient([_runtime("runtime-revoked", status="revoked")]),
        runtime_artifact_builder=lambda args: {"status": "waiting_for_signal"},
    )

    assert packet["status"] == "no_active_runtimes"
    assert packet["active_runtime_count"] == 0
    assert packet["monitored_runtime_count"] == 0
    assert "operator_command_plan" not in packet
    assert packet["observation_monitor_plan"]["next_step"] == (
        "start_or_authorize_a_runtime_before_monitoring"
    )
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_active_monitor_cli_prints_stdout_only(monkeypatch, capsys):
    def fake_build_monitor_artifact(args):
        return {
            "status": "waiting_for_signal",
            "active_runtime_count": 1,
            "safety_invariants": {"exchange_write_called": False},
        }

    monkeypatch.setattr(
        runtime_active_observation_monitor,
        "_build_monitor_artifact",
        fake_build_monitor_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_active_observation_monitor.py",
        ],
    )

    assert runtime_active_observation_monitor.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload["status"] == "waiting_for_signal"
