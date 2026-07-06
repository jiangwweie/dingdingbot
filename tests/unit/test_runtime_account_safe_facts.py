from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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


def test_runtime_account_safe_facts_cli_writes_pg_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_json = tmp_path / "account-safe.json"
    db_path = tmp_path / "runtime.db"
    with sqlite3.connect(db_path) as conn:
        _create_pg_scope_tables(conn)
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

    def fake_request_json(**kwargs):
        path = kwargs["path"]
        if path.endswith("/exchangeInfo"):
            return {
                "payload": {
                    "symbols": [
                        {
                            "symbol": "ETHUSDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }
            }
        if path.endswith("/account"):
            return {
                "payload": {
                    "canTrade": True,
                    "availableBalance": "100",
                    "totalWalletBalance": "100",
                    "assets": [],
                }
            }
        if path.endswith("/positionRisk"):
            return {"payload": [{"symbol": "ETHUSDT", "positionAmt": "0"}]}
        if path.endswith("/openOrders"):
            return {"payload": []}
        raise AssertionError(path)

    monkeypatch.setattr(module, "_request_json", fake_request_json)

    exit_code = module.main(
        [
            "--database-url",
            f"sqlite:///{db_path}",
            "--allow-non-postgres-for-test",
        ]
    )

    assert exit_code == 0
    assert not output_json.exists()
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


def test_runtime_account_safe_facts_cli_rejects_live_facts_json(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        module.main(
            [
                "--live-facts-json",
                str(tmp_path / "live-facts.json"),
                "--database-url",
                "sqlite:///:memory:",
                "--allow-non-postgres-for-test",
            ]
        )

    assert exc.value.code == 2


def _create_pg_scope_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE brc_strategy_group_candidate_scope (
          candidate_scope_id TEXT PRIMARY KEY,
          strategy_group_id TEXT,
          symbol TEXT,
          scope_state TEXT,
          policy_current_id TEXT,
          status TEXT
        );
        CREATE TABLE brc_owner_policy_current (
          policy_current_id TEXT PRIMARY KEY,
          enabled_state TEXT,
          pretrade_candidate_allowed BOOLEAN,
          max_notional NUMERIC
        );
        CREATE TABLE brc_candidate_scope_event_bindings (
          binding_id TEXT PRIMARY KEY,
          candidate_scope_id TEXT,
          event_spec_id TEXT,
          status TEXT
        );
        CREATE TABLE brc_strategy_side_event_specs (
          event_spec_id TEXT,
          protection_ref_type TEXT,
          status TEXT
        );
        INSERT INTO brc_owner_policy_current (
          policy_current_id, enabled_state, pretrade_candidate_allowed, max_notional
        ) VALUES (
          'policy:CPM-RO-001:ETHUSDT:long', 'enabled', 1, 20
        );
        INSERT INTO brc_strategy_group_candidate_scope (
          candidate_scope_id, strategy_group_id, symbol, scope_state,
          policy_current_id, status
        ) VALUES (
          'scope:CPM-RO-001:ETHUSDT:long', 'CPM-RO-001', 'ETHUSDT',
          'live_submit_allowed', 'policy:CPM-RO-001:ETHUSDT:long', 'active'
        );
        INSERT INTO brc_candidate_scope_event_bindings (
          binding_id, candidate_scope_id, event_spec_id, status
        ) VALUES (
          'binding:scope:CPM-RO-001:ETHUSDT:long:CPM-LONG',
          'scope:CPM-RO-001:ETHUSDT:long', 'event:CPM-LONG', 'active'
        );
        INSERT INTO brc_strategy_side_event_specs (
          event_spec_id, protection_ref_type, status
        ) VALUES (
          'event:CPM-LONG', 'pullback_low_reference', 'current'
        );
        """
    )
