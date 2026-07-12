from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts import build_runtime_account_safe_facts as module


def _live_facts() -> dict:
    return {
        "status": "ready",
        "account": {
            "total_wallet_balance": "123.45",
            "available_balance": "100.00",
            "available_balance_present": True,
            "available_balance_positive": True,
            "exchange_account_trade_permission": True,
        },
        "leverage_brackets": {
            "status": "ready",
            "max_leverage_by_symbol": {"TESTUSDT": 100},
        },
        "active_position": {"status": "no_active_position"},
        "open_orders": {"status": "no_open_orders"},
        "budget": {"status": "available_for_candidate_specific_reservation"},
        "exchange_rules": {"status": "ready"},
        "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        "protection": {"status": "ready_for_candidate_specific_plan"},
        "account_mode": {
            "status": "fresh",
            "account_id": "owner-subaccount-runtime-v0",
            "exchange_id": "binance_usdm",
            "runtime_profile_id": "owner-runtime-console-v1",
            "dual_side_position": False,
            "account_mode": "one_way",
            "position_mode_safe": True,
            "observed_at": "2026-07-03T00:00:00+00:00",
            "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
        },
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
    assert artifact["facts"]["total_wallet_balance"] == "123.45"
    assert artifact["facts"]["available_balance"] == "100.00"
    assert artifact["blockers"] == []
    assert artifact["account_mode"]["account_mode"] == "one_way"
    assert artifact["account_mode"]["dual_side_position"] is False
    assert artifact["account_mode"]["position_mode_safe"] is True
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


@pytest.mark.parametrize(
    ("account_mode", "expected_status"),
    [
        ({}, "missing"),
        (
            {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": "owner-runtime-console-v1",
                "dual_side_position": "false",
                "account_mode": "one_way",
                "position_mode_safe": True,
                "observed_at": "2026-07-03T00:00:00+00:00",
                "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
            },
            "malformed",
        ),
        (
            {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": "owner-runtime-console-v1",
                "dual_side_position": False,
                "account_mode": "one_way",
                "position_mode_safe": True,
                "observed_at": "2026-07-02T23:58:00+00:00",
                "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
            },
            "stale",
        ),
    ],
    ids=("missing", "malformed", "stale"),
)
def test_runtime_account_safe_facts_never_defaults_unsafe_mode_to_one_way(
    account_mode: dict,
    expected_status: str,
):
    live_facts = _live_facts()
    live_facts["account_mode"] = account_mode

    artifact = module.build_runtime_account_safe_facts(
        live_facts=live_facts,
        generated_at_utc="2026-07-03T00:00:00+00:00",
    )

    assert artifact["status"] == "runtime_account_safe_facts_blocked"
    assert "account_mode_ready" in artifact["blockers"]
    assert artifact["account_mode"]["status"] == expected_status
    assert artifact["account_mode"]["account_mode"] is None
    assert artifact["account_mode"]["dual_side_position"] is None
    assert artifact["account_mode"]["position_mode_safe"] is False


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
        if path.endswith("/leverageBracket"):
            return {
                "payload": [
                    {"symbol": "ETHUSDT", "brackets": [{"initialLeverage": 100}]}
                ]
            }
        if path.endswith("/positionSide/dual"):
            return {"payload": {"dualSidePosition": False}}
        raise AssertionError(path)

    monkeypatch.setattr(module._impl, "_request_json", fake_request_json)

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
            SELECT fact_surface, strategy_group_id, symbol, side,
                   runtime_profile_id, satisfied, freshness_state, fact_values
            FROM brc_runtime_fact_snapshots
            ORDER BY fact_surface
            """
        ).fetchall()
    assert {row[0] for row in rows} == {"account_safe", "account_mode"}
    assert all(row[1] is None and row[2] is None and row[3] is None for row in rows)
    assert all(row[4] == "owner-runtime-console-v1" for row in rows)
    assert all(row[5] == 1 for row in rows)
    assert all(row[6] == "fresh" for row in rows)
    account_mode_row = next(row for row in rows if row[0] == "account_mode")
    account_mode_values = json.loads(account_mode_row[7])
    account_safe_row = next(row for row in rows if row[0] == "account_safe")
    account_safe_values = json.loads(account_safe_row[7])
    assert account_safe_values["exchange_max_leverage_by_symbol"] == {
        "ETHUSDT": 100
    }
    assert account_mode_values["account_id"] == "owner-subaccount-runtime-v0"
    assert account_mode_values["exchange_id"] == "binance_usdm"
    assert account_mode_values["account_mode"] == "one_way"
    assert account_mode_values["dual_side_position"] is False
    assert account_mode_values["position_mode_safe"] is True
    assert account_mode_values["observed_at"]
    assert account_mode_values["source"].endswith("/fapi/v1/positionSide/dual")


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


def test_runtime_account_safe_facts_projection_cadence_can_continue_when_blocked(
    monkeypatch: pytest.MonkeyPatch,
):
    blocked = {
        "status": "runtime_account_safe_facts_blocked",
        "checks": {"account_safe_facts_ready": False},
    }
    monkeypatch.setattr(
        module._impl,
        "collect_account_safe_live_facts_from_pg_scope",
        lambda *args, **kwargs: {"status": "partial"},
    )
    monkeypatch.setattr(
        module._impl,
        "build_runtime_account_safe_facts",
        lambda **kwargs: dict(blocked),
    )
    monkeypatch.setattr(
        module._impl,
        "write_account_safe_fact_snapshots",
        lambda *args, **kwargs: ["fact:account-mode"],
    )

    exit_code = module.main(
        [
            "--database-url",
            "sqlite:///:memory:",
            "--allow-non-postgres-for-test",
            "--allow-blocked-current-projection",
        ]
    )

    assert exit_code == 0


def test_runtime_account_safe_facts_normalizes_asyncpg_dsn_for_sync_projector(
    monkeypatch: pytest.MonkeyPatch,
):
    seen: dict[str, str] = {}
    sqlite_engine = module.sa.create_engine("sqlite:///:memory:")

    def fake_create_engine(database_url: str):
        seen["database_url"] = database_url
        return sqlite_engine

    monkeypatch.setattr(module._impl.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        module._impl,
        "collect_account_safe_live_facts_from_pg_scope",
        lambda *args, **kwargs: {"status": "ready"},
    )
    monkeypatch.setattr(
        module._impl,
        "build_runtime_account_safe_facts",
        lambda **kwargs: {
            "status": "runtime_account_safe_facts_ready",
            "checks": {"account_safe_facts_ready": True},
        },
    )
    monkeypatch.setattr(
        module._impl,
        "write_account_safe_fact_snapshots",
        lambda *args, **kwargs: ["fact:account-mode"],
    )

    exit_code = module.main(
        [
            "--database-url",
            "postgresql+asyncpg://user:pass@localhost/brc",
            "--require-database-url",
        ]
    )

    assert exit_code == 0
    assert seen["database_url"] == "postgresql+psycopg://user:pass@localhost/brc"


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
        CREATE TABLE brc_strategy_groups (
          strategy_group_id TEXT PRIMARY KEY,
          current_version_id TEXT
        );
        CREATE TABLE brc_strategy_group_versions (
          strategy_group_version_id TEXT PRIMARY KEY,
          risk_envelope TEXT
        );
        CREATE TABLE brc_runtime_scope_bindings (
          runtime_scope_binding_id TEXT PRIMARY KEY,
          candidate_scope_id TEXT,
          runtime_profile_id TEXT,
          status TEXT
        );
        CREATE TABLE brc_symbol_instrument_mappings (
          mapping_id TEXT PRIMARY KEY,
          symbol TEXT,
          exchange_instrument_id TEXT,
          status TEXT,
          valid_from_ms INTEGER,
          valid_until_ms INTEGER
        );
        CREATE TABLE brc_exchange_instruments (
          exchange_instrument_id TEXT PRIMARY KEY,
          exchange_id TEXT,
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
        INSERT INTO brc_strategy_groups (
          strategy_group_id, current_version_id
        ) VALUES (
          'CPM-RO-001', 'version:CPM-RO-001:v2'
        );
        INSERT INTO brc_strategy_group_versions (
          strategy_group_version_id, risk_envelope
        ) VALUES (
          'version:CPM-RO-001:v2',
          '{"account_id":"owner-subaccount-runtime-v0"}'
        );
        INSERT INTO brc_strategy_group_candidate_scope (
          candidate_scope_id, strategy_group_id, symbol, scope_state,
          policy_current_id, status
        ) VALUES (
          'scope:CPM-RO-001:ETHUSDT:long', 'CPM-RO-001', 'ETHUSDT',
          'live_submit_allowed', 'policy:CPM-RO-001:ETHUSDT:long', 'active'
        );
        INSERT INTO brc_runtime_scope_bindings (
          runtime_scope_binding_id, candidate_scope_id, runtime_profile_id, status
        ) VALUES (
          'runtime:scope:CPM-RO-001:ETHUSDT:long',
          'scope:CPM-RO-001:ETHUSDT:long', 'owner-runtime-console-v1', 'active'
        );
        INSERT INTO brc_symbol_instrument_mappings (
          mapping_id, symbol, exchange_instrument_id, status,
          valid_from_ms, valid_until_ms
        ) VALUES (
          'mapping:ETHUSDT:binance_usdm', 'ETHUSDT',
          'binance_usdm:ETH/USDT:USDT', 'active', 0, NULL
        );
        INSERT INTO brc_exchange_instruments (
          exchange_instrument_id, exchange_id, status
        ) VALUES (
          'binance_usdm:ETH/USDT:USDT', 'binance_usdm', 'active'
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
