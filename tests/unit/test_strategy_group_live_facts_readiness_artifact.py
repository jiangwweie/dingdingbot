from __future__ import annotations

import json
import sqlite3

import sqlalchemy as sa

import scripts.build_strategy_group_live_facts_readiness_artifact as readiness_script
import src.application.readmodels.strategy_group_live_facts_readiness as readiness_readmodel
from src.application.readmodels.strategy_group_live_facts_readiness import (
    build_readiness_artifact,
    build_readiness_artifact_from_pg,
)


def _intake() -> dict:
    return {
        "source_anchor": {
            "repo": "/strategy-repo",
            "branch": "codex/strategy-research-20260613-goal",
            "commit": "05f616b0",
        },
        "strategy_picker": [
            {
                "strategy_group_id": "MPG-001",
                "supported_symbols": ["BTCUSDT", "ETHUSDT"],
                "supported_symbol_count": 2,
                "picker": {"default_mode": "armed_observation"},
                "warnings": [],
            },
            {
                "strategy_group_id": "PMR-001",
                "supported_symbols": ["XAUUSDT"],
                "supported_symbol_count": 1,
                "picker": {"default_mode": "observe_only"},
                "warnings": ["observe_only_until_role_session_mark_readiness"],
            },
        ],
    }


def _exchange_rules() -> dict:
    return {
        "symbols": {
            "BTCUSDT": {"status": "TRADING"},
            "ETHUSDT": {"status": "TRADING"},
            "XAUUSDT": {"status": "TRADING"},
        }
    }


def test_live_facts_readiness_allows_observation_when_candidate_facts_missing():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={"exchange_rules": _exchange_rules()},
        generated_at_ms=1,
    )

    assert artifact["status"] == (
        "strategy_group_observe_ready_candidate_prerequisites_pending"
    )
    assert artifact["counts"]["observe_ready"] == 2
    assert artifact["counts"]["armed_candidate_prepare_ready"] == 0
    assert artifact["operator_path"]["can_continue_observation"] is True
    assert artifact["operator_path"]["can_prepare_fresh_candidate"] is False
    assert artifact["operator_path"]["next_gate"] == (
        "continue_observation_and_prepare_candidate_prerequisites"
    )
    assert artifact["operator_path"]["requires_action_time_final_gate_before_submit"] is True
    assert artifact["owner_state"]["status"] == (
        "observe_ready_candidate_prerequisites_missing"
    )
    assert artifact["owner_state"]["blocked_at"] == "candidate_prepare_facts"
    assert artifact["owner_state"]["authority_mode"] == (
        "observe_only_until_candidate_prerequisites_ready"
    )
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "continue_observation_and_prepare_candidate_prerequisite_facts"
    )
    assert artifact["owner_state"]["checkpoint_source"] == "owner_state"
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["blockers"] == []
    assert "MPG-001:account:missing" in artifact["candidate_prepare_blockers"]
    mpg = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "MPG-001"
    )
    assert mpg["observe_ready"] is True
    assert "account:missing" in mpg["blockers"]


def test_live_facts_readiness_marks_armed_ready_when_required_live_facts_pass():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={
            "exchange_rules": _exchange_rules(),
            "account": {"status": "fresh"},
            "active_position": {"status": "no_active_position"},
            "open_orders": {"status": "no_open_orders"},
            "protection": {"status": "ready_for_candidate_specific_plan"},
            "budget": {"status": "available_for_candidate_specific_reservation"},
            "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        },
        generated_at_ms=1,
    )

    assert artifact["status"] == "strategy_group_live_facts_ready_for_armed_observation"
    assert artifact["counts"]["observe_ready"] == 2
    assert artifact["counts"]["armed_candidate_prepare_ready"] == 1
    assert artifact["operator_path"]["can_prepare_fresh_candidate"] is True
    assert artifact["operator_path"]["next_gate"] == (
        "review_ready_groups_before_fresh_candidate_prepare"
    )
    assert artifact["owner_state"]["status"] == "armed_observation_ready"
    assert artifact["owner_state"]["blocked_at"] == "none"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "continue_watcher_observation"
    )
    assert artifact["blockers"] == []
    assert artifact["candidate_prepare_blockers"] == []


def test_live_facts_readiness_blocks_observation_when_exchange_rules_missing():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={},
        generated_at_ms=1,
    )

    assert artifact["status"] == "strategy_group_live_facts_blocked"
    assert artifact["counts"]["observe_ready"] == 0
    assert artifact["operator_path"]["can_continue_observation"] is False
    assert artifact["owner_state"]["blocked_at"] == "live_fact_readiness"
    assert artifact["owner_state"]["authority_mode"] == "not_observing"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "refresh_strategy_group_live_facts_readonly"
    )
    assert (
        "MPG-001:exchange_rules_not_ready_for_any_supported_symbol"
        in artifact["blockers"]
    )


def test_live_facts_readiness_allows_partial_supported_symbol_availability():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={
            "exchange_rules": {
                "symbols": {
                    "BTCUSDT": {"status": "TRADING"},
                    "ETHUSDT": {"status": "missing"},
                    "XAUUSDT": {"status": "missing"},
                }
            },
            "account": {"status": "fresh"},
            "active_position": {"status": "no_active_position"},
            "open_orders": {"status": "no_open_orders"},
            "protection": {"status": "ready_for_candidate_specific_plan"},
            "budget": {"status": "available_for_candidate_specific_reservation"},
            "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        },
        generated_at_ms=1,
    )

    mpg = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "MPG-001"
    )
    pmr = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "PMR-001"
    )

    assert mpg["observe_ready"] is True
    assert mpg["armed_candidate_prepare_ready"] is True
    assert mpg["exchange_rules"]["ready_symbols"] == ["BTCUSDT"]
    assert mpg["exchange_rules"]["blocked_symbols"] == ["ETHUSDT"]
    assert "exchange_rules_not_ready_for_some_supported_symbols" in mpg["warnings"]
    assert (
        "MPG-001:exchange_rules_not_ready_for_any_supported_symbol"
        not in artifact["blockers"]
    )
    assert pmr["observe_ready"] is False
    assert (
        "PMR-001:exchange_rules_not_ready_for_any_supported_symbol"
        in artifact["blockers"]
    )


def test_live_facts_readiness_does_not_expose_legacy_packet_builder():
    assert not hasattr(readiness_script, "build_packet")
    assert not hasattr(readiness_script, "build_readiness_artifact")
    assert not hasattr(readiness_script, "build_readiness_artifact_from_pg")


def test_live_facts_readiness_cli_rejects_live_facts_json(tmp_path):
    try:
        readiness_readmodel._parse_args(
            [
                "--live-facts-json",
                str(tmp_path / "live-facts.json"),
                "--output-json",
                str(tmp_path / "out.json"),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("retired live-facts JSON input must be rejected")


def test_live_facts_readiness_script_is_thin_cli_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(readiness_readmodel, "main", lambda argv=None: 7)

    assert readiness_script.main(["--ignored-by-fake-main"]) == 7


def test_live_facts_readiness_builds_from_pg_fact_snapshots(tmp_path):
    db_path = tmp_path / "runtime.db"
    with sqlite3.connect(db_path) as conn:
        _create_runtime_fact_snapshots(conn)
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            artifact = build_readiness_artifact_from_pg(
                conn=conn,
                intake_artifact=_intake(),
                generated_at_ms=1,
            )
    finally:
        engine.dispose()

    assert artifact["status"] == "strategy_group_live_facts_ready_for_armed_observation"
    assert artifact["live_facts_source"]["mode"] == "pg_runtime_fact_snapshots"
    assert artifact["live_facts"]["source_mode"] == "db_backed"
    assert artifact["counts"]["observe_ready"] == 2
    assert artifact["counts"]["armed_candidate_prepare_ready"] == 1
    assert artifact["candidate_prepare_blockers"] == []


def _create_runtime_fact_snapshots(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE brc_runtime_fact_snapshots (
          fact_snapshot_id TEXT PRIMARY KEY,
          strategy_group_id TEXT,
          symbol TEXT,
          side TEXT,
          runtime_profile_id TEXT,
          fact_surface TEXT,
          source_kind TEXT,
          source_ref TEXT,
          computed BOOLEAN,
          satisfied BOOLEAN,
          freshness_state TEXT,
          failed_facts TEXT,
          fact_values TEXT,
          blocker_class TEXT,
          observed_at_ms INTEGER,
          valid_until_ms INTEGER,
          created_at_ms INTEGER
        )
        """
    )
    for symbol in ("BTCUSDT", "ETHUSDT", "XAUUSDT"):
        conn.execute(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id,
              fact_surface, source_kind, source_ref, computed, satisfied,
              freshness_state, failed_facts, fact_values, blocker_class,
              observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              ?, 'MPG-001', ?, 'long', 'runtime:MPG-001', 'pretrade_public',
              'live_market', 'unit', 1, 1, 'fresh', '[]', ?, NULL,
              1780000000000, 1780000300000, 1780000000000
            )
            """,
            (
                f"fact:MPG-001:{symbol}:long:pretrade_public:1780000000000",
                symbol,
                json.dumps(
                    {
                        "symbol": symbol,
                        "public_facts_ready": True,
                        "public_symbol_row": {
                            "symbol": symbol,
                            "public_facts_ready": True,
                        },
                    }
                ),
            ),
        )
    checks = {
        "source_signed_get_only": True,
        "source_exchange_write_called": False,
        "source_order_created": False,
        "account_trade_permission": True,
        "active_position_clear": True,
        "open_orders_clear": True,
        "budget_available": True,
        "protection_template_ready": True,
        "next_attempt_gate_ready": True,
        "account_safe": True,
        "account_safe_facts_ready": True,
        "private_action_time_facts_ready": True,
        "active_position_or_open_order_clear": True,
        "action_time_available_balance": True,
    }
    for surface in ("account_safe", "account_mode"):
        conn.execute(
            """
            INSERT INTO brc_runtime_fact_snapshots (
              fact_snapshot_id, strategy_group_id, symbol, side, runtime_profile_id,
              fact_surface, source_kind, source_ref, computed, satisfied,
              freshness_state, failed_facts, fact_values, blocker_class,
              observed_at_ms, valid_until_ms, created_at_ms
            ) VALUES (
              ?, NULL, NULL, NULL, NULL, ?, 'live_account_readonly', 'unit',
              1, 1, 'fresh', '[]', ?, NULL, 1780000000000, 1780000060000,
              1780000000000
            )
            """,
            (f"fact:global:{surface}:1780000000000", surface, json.dumps(checks)),
        )
