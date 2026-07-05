from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import build_runtime_account_safe_facts as module


def _live_facts() -> dict:
    return {
        "status": "ready",
        "account": {
            "available_balance_present": True,
            "available_balance_positive": True,
            "exchange_account_trade_permission": True,
        },
        "active_position": {"status": "no_active_position"},
        "open_orders": {"status": "no_open_orders"},
        "budget": {"status": "available_for_candidate_specific_reservation"},
        "exchange_rules": {"status": "ready"},
        "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        "protection": {"status": "ready_for_candidate_specific_plan"},
        "safety_invariants": {
            "signed_get_only": True,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def test_runtime_account_safe_facts_ready_from_live_facts():
    artifact = module.build_runtime_account_safe_facts(
        live_facts=_live_facts(),
        generated_at_utc="2026-07-03T00:00:00+00:00",
    )

    assert artifact["status"] == "runtime_account_safe_facts_ready"
    assert artifact["checks"]["account_safe_facts_ready"] is True
    assert artifact["checks"]["private_action_time_facts_ready"] is True
    assert artifact["checks"]["active_position_or_open_order_clear"] is True
    assert artifact["checks"]["action_time_available_balance"] is True
    assert artifact["blockers"] == []
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_runtime_account_safe_facts_blocks_open_position():
    live_facts = _live_facts()
    live_facts["active_position"] = {"status": "active_position_present"}

    artifact = module.build_runtime_account_safe_facts(
        live_facts=live_facts,
        generated_at_utc="2026-07-03T00:00:00+00:00",
    )

    assert artifact["status"] == "runtime_account_safe_facts_blocked"
    assert artifact["checks"]["account_safe_facts_ready"] is False
    assert "active_position_clear" in artifact["blockers"]


def test_runtime_account_safe_facts_cli_writes_pg_snapshots(tmp_path: Path):
    live_facts = tmp_path / "live-facts.json"
    output_json = tmp_path / "account-safe.json"
    db_path = tmp_path / "runtime.db"
    live_facts.write_text(json.dumps(_live_facts()), encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
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

    exit_code = module.main(
        [
            "--live-facts-json",
            str(live_facts),
            "--database-url",
            f"sqlite:///{db_path}",
            "--allow-non-postgres-for-test",
            "--output-json",
            str(output_json),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["source_mode"] == "db_backed"
    assert len(artifact["pg_fact_snapshot_ids"]) == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT fact_surface, strategy_group_id, symbol, side, satisfied,
                   freshness_state
            FROM brc_runtime_fact_snapshots
            ORDER BY fact_surface
            """
        ).fetchall()
    assert {row[0] for row in rows} == {"account_safe", "account_mode"}
    assert all(row[1] is None and row[2] is None and row[3] is None for row in rows)
    assert all(row[4] == 1 for row in rows)
    assert all(row[5] == "fresh" for row in rows)
