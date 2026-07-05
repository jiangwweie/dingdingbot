from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_runtime_control_state")
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
    with engine.connect() as conn:
        yield conn
    engine.dispose()


@pytest.fixture()
def seed_module():
    return _load_module(SEED_PATH, "seed_runtime_control_state_foundation")


def _count(conn, table_name: str) -> int:
    return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def test_seed_dry_run_reports_current_active_scope(seed_module):
    report = seed_module.dry_run_report()

    assert report["status"] == "dry_run"
    assert report["strategy_group_count"] == 5
    assert report["event_spec_count"] == 6
    assert report["candidate_scope_count"] == 22
    assert report["unique_symbol_count"] == 6
    assert report["strategy_scope_counts"] == {
        "BRF2-001": 3,
        "CPM-RO-001": 4,
        "MI-001": 3,
        "MPG-001": 4,
        "SOR-001": 8,
    }
    assert all(value is False for value in report["forbidden_effects"].values())


def test_seed_applies_current_strategy_event_scope_without_runtime_events(
    connection,
    seed_module,
):
    with connection.begin():
        report = seed_module.seed_runtime_control_state_foundation(connection)

    assert report["status"] == "applied"
    assert _count(connection, "brc_strategy_groups") == 5
    assert _count(connection, "brc_strategy_side_event_specs") == 6
    assert _count(connection, "brc_strategy_group_candidate_scope") == 22
    assert _count(connection, "brc_runtime_scope_bindings") == 22
    assert _count(connection, "brc_execution_policies") == 6
    assert _count(connection, "brc_current_projection_ownership") == 6

    assert _count(connection, "brc_live_signal_events") == 0
    assert _count(connection, "brc_promotion_candidates") == 0
    assert _count(connection, "brc_action_time_lane_inputs") == 0
    assert _count(connection, "brc_action_time_tickets") == 0
    assert _count(connection, "brc_budget_reservations") == 0


def test_seed_is_idempotent(connection, seed_module):
    with connection.begin():
        seed_module.seed_runtime_control_state_foundation(connection)
        seed_module.seed_runtime_control_state_foundation(connection)

    assert _count(connection, "brc_strategy_group_candidate_scope") == 22
    assert _count(connection, "brc_owner_policy_current") == 22
    assert _count(connection, "brc_candidate_scope_event_bindings") == 22
    assert _count(connection, "brc_runtime_scope_bindings") == 22


def test_seed_cli_normalizes_asyncpg_dsn_for_sync_engine(
    seed_module,
    monkeypatch,
    capsys,
):
    seen_urls: list[str] = []

    class FakeBegin:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    def fake_create_engine(database_url: str):
        seen_urls.append(database_url)
        return FakeEngine()

    monkeypatch.setattr(seed_module.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        seed_module,
        "seed_runtime_control_state_foundation",
        lambda *_args, **_kwargs: {
            "status": "applied",
            "forbidden_effects": {
                "exchange_write": False,
                "order_created": False,
            },
        },
    )

    assert (
        seed_module.main(
            [
                "--apply",
                "--json",
                "--database-url",
                "postgresql+asyncpg://user:pass@localhost:5432/brc",
            ]
        )
        == 0
    )

    assert seen_urls == ["postgresql+psycopg://user:pass@localhost:5432/brc"]
    assert '"status": "applied"' in capsys.readouterr().out


def test_seed_preserves_strategy_specific_side_support(connection, seed_module):
    with connection.begin():
        seed_module.seed_runtime_control_state_foundation(connection)

    unsupported = connection.execute(
        text(
            """
            SELECT strategy_group_id, symbol, side
            FROM brc_strategy_group_candidate_scope
            WHERE (strategy_group_id = 'CPM-RO-001' AND side = 'short')
               OR (strategy_group_id = 'MPG-001' AND side = 'short')
               OR (strategy_group_id = 'MI-001' AND side = 'short')
               OR (strategy_group_id = 'BRF2-001' AND side = 'long')
            """
        )
    ).all()
    assert unsupported == []

    sor_sides = {
        row[0]
        for row in connection.execute(
            text(
                """
                SELECT DISTINCT side
                FROM brc_strategy_group_candidate_scope
                WHERE strategy_group_id = 'SOR-001'
                """
            )
        )
    }
    assert sor_sides == {"long", "short"}


def test_seed_records_mi_relative_strength_as_hard_required_fact(
    connection,
    seed_module,
):
    with connection.begin():
        seed_module.seed_runtime_control_state_foundation(connection)

    row = connection.execute(
        text(
            """
            SELECT required_for_promotion, required_for_ticket, required_for_finalgate
            FROM brc_strategy_event_required_facts
            WHERE event_spec_id = 'event_spec:MI-001:MI-LONG:v1'
              AND fact_key = 'relative_strength_confirmed'
            """
        )
    ).one()
    assert tuple(row) == (True, True, True)


def test_seed_records_brf2_conditional_hard_gates(connection, seed_module):
    with connection.begin():
        seed_module.seed_runtime_control_state_foundation(connection)

    row = connection.execute(
        text(
            """
            SELECT conditional_hard_gates
            FROM brc_runtime_scope_bindings
            WHERE strategy_group_id = 'BRF2-001'
              AND symbol = 'BTCUSDT'
              AND side = 'short'
            """
        )
    ).one()
    gates = row[0]
    if isinstance(gates, str):
        gates = json.loads(gates)
    assert gates == [
        "short_side_disable_clear",
        "squeeze_clear",
        "liquidity_clear",
    ]


def test_seed_validator_rejects_mirrored_unsupported_side(seed_module):
    rows = seed_module.build_seed_rows()
    rows["brc_strategy_group_candidate_scope"].append(
        {
            "candidate_scope_id": "candidate_scope:CPM-RO-001:ETHUSDT:short:CPM-SHORT",
            "strategy_group_id": "CPM-RO-001",
            "symbol": "ETHUSDT",
            "exchange_symbol": "ETH/USDT:USDT",
            "asset_class": "crypto_usdm_perp",
            "side": "short",
            "timeframe": "1h",
            "candidate_role": "candidate",
            "observation_scope": "active_wip",
            "scope_state": "live_submit_allowed",
            "priority_rank": 99,
            "policy_current_id": "policy_current:bad",
            "status": "active",
            "valid_from_ms": 1770000000000,
            "valid_until_ms": None,
            "created_at_ms": 1770000000000,
            "updated_at_ms": 1770000000000,
            "metadata": {"event_id": "CPM-SHORT"},
        }
    )

    with pytest.raises(ValueError, match="unsupported candidate scope seed"):
        seed_module.validate_seed_rows(rows)
