from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / "scripts" / "runtime_pg_fact_snapshots.py"
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts" / "seed_runtime_control_state_foundation.py"


def _load_file_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_engine():
    migration = _load_file_module(MIGRATION_PATH, "migration_086_pg_fact_helper")
    seed = _load_file_module(SEED_PATH, "seed_runtime_control_state_pg_fact_helper")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    return engine


def _public_artifact() -> dict:
    return {
        "generated_at_utc": "2026-07-05T00:00:00+00:00",
        "symbols": [
            {
                "symbol": "ETHUSDT",
                "public_facts_ready": True,
                "exchange_contract_exists": True,
                "mark_price_fresh": True,
                "mark_price_observed_at_utc": "2026-07-05T00:00:00+00:00",
                "funding_not_extreme": True,
                "spread_ok": True,
                "min_notional_ok": True,
                "qty_step_ok": True,
                "leverage_available": True,
                "facts": {"spread_bps": 0.5, "last_funding_rate": "0.0001"},
            },
            {
                "symbol": "SOLUSDT",
                "public_facts_ready": False,
                "exchange_contract_exists": True,
                "mark_price_fresh": True,
                "mark_price_observed_at_utc": "2026-07-05T00:00:00+00:00",
                "funding_not_extreme": True,
                "spread_ok": False,
                "min_notional_ok": True,
                "qty_step_ok": True,
                "leverage_available": True,
                "facts": {"spread_bps": 15.0, "last_funding_rate": "0.0001"},
            },
        ],
    }


def test_public_fact_snapshots_are_lane_scoped_and_exportable_from_pg():
    helper = _load_file_module(HELPER_PATH, "runtime_pg_fact_snapshots_test")
    engine = _seed_engine()
    try:
        with engine.begin() as conn:
            ids = helper.write_pretrade_public_fact_snapshots(
                conn,
                artifact=_public_artifact(),
                source_ref="unit:public-fetch",
                source_kind="unit_test",
            )
            rows = conn.execute(
                text(
                    """
                    SELECT strategy_group_id, symbol, side, fact_surface, satisfied,
                           blocker_class
                    FROM brc_runtime_fact_snapshots
                    WHERE fact_surface = 'pretrade_public'
                    ORDER BY strategy_group_id, symbol, side
                    """
                )
            ).mappings().all()
            export = helper.read_pretrade_public_facts_artifact(
                conn,
                symbols=["ETHUSDT", "SOLUSDT"],
            )
    finally:
        engine.dispose()

    assert ids
    assert all(row["strategy_group_id"] for row in rows)
    assert all(row["side"] in {"long", "short"} for row in rows)
    eth_rows = [row for row in rows if row["symbol"] == "ETHUSDT"]
    sol_rows = [row for row in rows if row["symbol"] == "SOLUSDT"]
    assert eth_rows
    assert sol_rows
    assert all(row["satisfied"] in {True, 1} for row in eth_rows)
    assert all(row["blocker_class"] == "computed_not_satisfied" for row in sol_rows)
    assert export["source_mode"] == "db_backed"
    assert {
        row["symbol"]: row["public_facts_ready"]
        for row in export["symbols"]
    } == {"ETHUSDT": True, "SOLUSDT": False}


def test_account_safe_fact_snapshots_are_global_and_exportable_from_pg():
    helper = _load_file_module(HELPER_PATH, "runtime_pg_account_fact_helper_test")
    engine = _seed_engine()
    artifact = {
        "generated_at_utc": "2026-07-05T00:00:00+00:00",
        "status": "runtime_account_safe_facts_ready",
        "source_status": "ready",
        "checks": {
            "account_safe_facts_ready": True,
            "account_safe": True,
            "private_action_time_facts_ready": True,
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
            "open_orders_clear": True,
            "account_trade_permission": True,
            "source_signed_get_only": True,
            "source_exchange_write_called": False,
            "source_order_created": False,
        },
        "facts": {
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
            "total_wallet_balance": "123.45",
            "available_balance": "100.00",
        },
        "account_mode": {
            "status": "fresh",
            "account_id": "owner-subaccount-runtime-v0",
            "exchange_id": "binance_usdm",
            "runtime_profile_id": "owner-runtime-console-v1",
            "account_mode": "hedge",
            "dual_side_position": True,
            "position_mode_safe": True,
            "observed_at": "2026-07-05T00:00:00+00:00",
            "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
        },
        "blockers": [],
    }
    try:
        with engine.begin() as conn:
            ids = helper.write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="unit:live-facts",
                source_kind="unit_test",
            )
            rows = conn.execute(
                text(
                    """
                    SELECT fact_snapshot_id, strategy_group_id, symbol, side,
                           runtime_profile_id, fact_surface, satisfied,
                           freshness_state, fact_values, observed_at_ms,
                           valid_until_ms
                    FROM brc_runtime_fact_snapshots
                    WHERE fact_surface IN
                      ('account_safe', 'account_capacity_base', 'account_mode')
                    ORDER BY fact_surface
                    """
                )
            ).mappings().all()
            export = helper.read_latest_account_safe_facts_artifact(conn)
    finally:
        engine.dispose()

    assert len(ids) == 3
    assert {row["fact_surface"] for row in rows} == {
        "account_safe", "account_capacity_base", "account_mode"
    }
    assert all(row["strategy_group_id"] is None for row in rows)
    assert all(row["symbol"] is None for row in rows)
    assert all(row["side"] is None for row in rows)
    assert all(row["runtime_profile_id"] == "owner-runtime-console-v1" for row in rows)
    assert all(
        row["satisfied"] in {True, 1}
        for row in rows
        if row["fact_surface"] != "account_capacity_base"
    )
    assert all(
        row["freshness_state"] == "fresh"
        for row in rows
        if row["fact_surface"] != "account_capacity_base"
    )
    ttl_by_surface = {
        row["fact_surface"]: row["valid_until_ms"] - row["observed_at_ms"]
        for row in rows
    }
    assert ttl_by_surface == {
        "account_capacity_base": 60_000,
        "account_mode": 300_000,
        "account_safe": 60_000,
    }
    assert export["source_mode"] == "db_backed"
    assert export["checks"]["account_safe_facts_ready"] is True
    assert export["checks"]["account_mode_snapshot_ready"] is True
    assert export["checks"]["open_orders_clear"] is True
    mode_values = next(
        row["fact_values"]
        for row in rows
        if row["fact_surface"] == "account_mode"
    )
    if isinstance(mode_values, str):
        mode_values = json.loads(mode_values)
    assert mode_values["account_id"] == "owner-subaccount-runtime-v0"
    assert mode_values["exchange_id"] == "binance_usdm"
    assert mode_values["account_mode"] == "hedge"
    assert mode_values["dual_side_position"] is True
    assert mode_values["position_mode_safe"] is True
    account_values = next(
        row["fact_values"]
        for row in rows
        if row["fact_surface"] == "account_safe"
    )
    if isinstance(account_values, str):
        account_values = json.loads(account_values)
    assert account_values["total_wallet_balance"] == "123.45"
    assert account_values["available_balance"] == "100.00"


def test_stale_account_mode_cannot_leave_account_safe_snapshot_satisfied():
    helper = _load_file_module(HELPER_PATH, "runtime_pg_stale_account_mode_test")
    engine = _seed_engine()
    artifact = {
        "generated_at_utc": "2026-07-05T00:06:00+00:00",
        "status": "runtime_account_safe_facts_ready",
        "source_status": "ready",
        "checks": {
            "account_safe_facts_ready": True,
            "account_safe": True,
            "private_action_time_facts_ready": True,
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
            "open_orders_clear": True,
            "account_trade_permission": True,
            "source_signed_get_only": True,
            "source_exchange_write_called": False,
            "source_order_created": False,
        },
        "facts": {
            "active_position_or_open_order_clear": True,
            "action_time_available_balance": True,
        },
        "account_mode": {
            "status": "fresh",
            "account_id": "owner-subaccount-runtime-v0",
            "exchange_id": "binance_usdm",
            "runtime_profile_id": "owner-runtime-console-v1",
            "account_mode": "one_way",
            "dual_side_position": False,
            "position_mode_safe": True,
            "observed_at": "2026-07-05T00:00:00+00:00",
            "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
        },
        "blockers": [],
    }
    try:
        with engine.begin() as conn:
            helper.write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="unit:stale-live-facts",
                source_kind="unit_test",
            )
            rows = {
                row["fact_surface"]: dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT fact_surface, satisfied, freshness_state, fact_values
                        FROM brc_runtime_fact_snapshots
                        WHERE fact_surface IN ('account_safe', 'account_mode')
                        """
                    )
                ).mappings()
            }
    finally:
        engine.dispose()

    mode_values = rows["account_mode"]["fact_values"]
    if isinstance(mode_values, str):
        mode_values = json.loads(mode_values)
    assert rows["account_safe"]["satisfied"] in {False, 0}
    assert rows["account_mode"]["satisfied"] in {False, 0}
    assert rows["account_mode"]["freshness_state"] == "stale"
    assert mode_values["account_mode"] is None
    assert mode_values["dual_side_position"] is None
    assert mode_values["position_mode_safe"] is False


def test_capacity_base_fact_is_independent_from_legacy_flat_account_safe_fact():
    helper = _load_file_module(HELPER_PATH, "runtime_pg_capacity_base_fact_test")
    engine = _seed_engine()
    artifact = {
        "generated_at_utc": "2026-07-17T00:00:00+00:00",
        "status": "runtime_account_safe_facts_blocked",
        "source_status": "ready",
        "checks": {
            "account_safe_facts_ready": False,
            "account_safe": False,
            "account_capacity_base_ready": True,
            "account_capacity_base_safe": True,
            "account_trade_permission": True,
            "source_signed_get_only": True,
            "source_exchange_write_called": False,
            "source_order_created": False,
        },
        "facts": {
            "total_wallet_balance": "600",
            "available_balance": "500",
            "exchange_max_leverage_by_symbol": {"ETHUSDT": 100},
            "account_capacity_source_snapshot_id": "account-risk-snapshot-1",
            "account_capacity_base": {
                "observed_at_ms": 1784246400000,
                "valid_until_ms": 1784246460000,
            },
        },
        "account_mode": {
            "status": "fresh",
            "account_id": "owner-subaccount-runtime-v0",
            "exchange_id": "binance_usdm",
            "runtime_profile_id": "owner-runtime-console-v1",
            "account_mode": "hedge",
            "dual_side_position": True,
            "position_mode_safe": True,
            "observed_at": "2026-07-17T00:00:00+00:00",
            "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
        },
        "blockers": ["active_position_clear"],
    }
    try:
        with engine.begin() as conn:
            helper.write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="unit:capacity-base",
                source_kind="unit_test",
            )
            rows = {
                row["fact_surface"]: row
                for row in conn.execute(
                    text(
                        """
                        SELECT fact_surface, satisfied, fact_values, observed_at_ms,
                               valid_until_ms
                        FROM brc_runtime_fact_snapshots
                        WHERE fact_surface IN
                          ('account_safe', 'account_capacity_base', 'account_mode')
                        """
                    )
                ).mappings()
            }
    finally:
        engine.dispose()

    assert rows["account_safe"]["satisfied"] in {False, 0}
    assert rows["account_capacity_base"]["satisfied"] in {True, 1}
    capacity_values = rows["account_capacity_base"]["fact_values"]
    safe_values = rows["account_safe"]["fact_values"]
    if isinstance(capacity_values, str):
        capacity_values = json.loads(capacity_values)
    if isinstance(safe_values, str):
        safe_values = json.loads(safe_values)
    assert capacity_values["schema_version"] == "account_capacity_base.v1"
    assert capacity_values["account_capacity_source_snapshot_id"] == "account-risk-snapshot-1"
    assert capacity_values["exchange_max_leverage_by_symbol"] == {"ETHUSDT": 100}
    assert capacity_values["account_capacity_base_safe"] is True
    assert safe_values["account_capacity_source_snapshot_id"] == "account-risk-snapshot-1"
    assert rows["account_capacity_base"]["observed_at_ms"] == 1784246400000
    assert rows["account_capacity_base"]["valid_until_ms"] == 1784246460000
    assert rows["account_safe"]["observed_at_ms"] == 1784246400000
    assert rows["account_safe"]["valid_until_ms"] == 1784246460000
