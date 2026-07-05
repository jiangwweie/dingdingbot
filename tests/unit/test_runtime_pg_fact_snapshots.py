from __future__ import annotations

import importlib.util
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
