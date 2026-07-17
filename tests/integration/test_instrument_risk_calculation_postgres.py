"""PostgreSQL certification for migration 136's atomic V1-to-V2 rule switch."""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import os
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]


def test_postgres_migration_136_keeps_v1_opaque_and_switches_one_current_v2() -> None:
    dsn = os.environ["BRC_LOCAL_TEST_POSTGRES_DSN"]
    schema = os.environ["BRC_LOCAL_TEST_POSTGRES_SCHEMA"]
    engine = sa.create_engine(dsn, connect_args={"options": f"-c search_path={schema}"})
    _create_schema(engine)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("""
                INSERT INTO brc_exchange_instruments VALUES
                ('binance_usdm:SOLUSDT', 'binance_usdm', 'crypto', 'perpetual',
                 'USDT', 'USDT', 'active')
            """))
            conn.execute(sa.text("""
                INSERT INTO brc_instrument_rule_snapshots VALUES
                ('rule-v1', 'binance_usdm:SOLUSDT', 'v1', .01, .001, .001, 5,
                 10, 20, 'rule-fact-v1', 2000000000000, :v1_hash, 'current', 1)
            """), {"v1_hash": "a" * 64})
            conn.execute(sa.text("""
                INSERT INTO brc_budget_reservations VALUES
                ('reservation-v1', 'rule-v1', 'active', 'v1')
            """))
            migration = _migration()
            previous_op = migration.op
            migration.op = Operations(MigrationContext.configure(conn))
            try:
                migration.upgrade()
                rows = conn.execute(sa.text("""
                SELECT instrument_rule_snapshot_id, rule_schema_version,
                       risk_calculation_kind, supersedes_instrument_rule_snapshot_id,
                       semantic_hash, status, contract_multiplier
                FROM brc_instrument_rule_snapshots
                ORDER BY instrument_rule_snapshot_id
                """)).mappings().all()
                assert rows == [
                {
                    "instrument_rule_snapshot_id": "rule-v1",
                    "rule_schema_version": "v1",
                    "risk_calculation_kind": None,
                    "supersedes_instrument_rule_snapshot_id": None,
                    "semantic_hash": "a" * 64,
                    "status": "superseded",
                    "contract_multiplier": Decimal("10"),
                },
                {
                    "instrument_rule_snapshot_id": "rule-v1:v2",
                    "rule_schema_version": "v2",
                    "risk_calculation_kind": "linear_quote_settled",
                    "supersedes_instrument_rule_snapshot_id": "rule-v1",
                    "semantic_hash": rows[1]["semantic_hash"],
                    "status": "current",
                    "contract_multiplier": Decimal("10"),
                },
                ]
                assert len(rows[1]["semantic_hash"]) == 64
                migration.downgrade()
                restored = conn.execute(sa.text("""
                SELECT instrument_rule_snapshot_id, rule_schema_version, semantic_hash, status
                FROM brc_instrument_rule_snapshots
                """)).mappings().all()
                assert restored == [{
                "instrument_rule_snapshot_id": "rule-v1",
                "rule_schema_version": "v1", "semantic_hash": "a" * 64,
                "status": "current",
                }]
            finally:
                migration.op = previous_op
    finally:
        engine.dispose()


def _create_schema(engine: sa.Engine) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "brc_exchange_instruments", metadata,
        sa.Column("exchange_instrument_id", sa.String(192), primary_key=True),
        sa.Column("exchange_id", sa.String(96), nullable=False),
        sa.Column("asset_class", sa.String(64), nullable=False),
        sa.Column("instrument_type", sa.String(64), nullable=False),
        sa.Column("settlement_asset", sa.String(64), nullable=False),
        sa.Column("margin_asset", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    sa.Table(
        "brc_instrument_rule_snapshots", metadata,
        sa.Column("instrument_rule_snapshot_id", sa.String(192), primary_key=True),
        sa.Column("exchange_instrument_id", sa.String(192), nullable=False),
        sa.Column("rule_schema_version", sa.String(32), nullable=False),
        sa.Column("price_tick", sa.Numeric(36, 18), nullable=False),
        sa.Column("quantity_step", sa.Numeric(36, 18), nullable=False),
        sa.Column("min_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("min_notional", sa.Numeric(36, 18), nullable=False),
        sa.Column("contract_multiplier", sa.Numeric(36, 18), nullable=False),
        sa.Column("exchange_max_leverage_for_claim_notional", sa.Integer(), nullable=False),
        sa.Column("source_fact_snapshot_id", sa.String(192), nullable=False),
        sa.Column("valid_until_ms", sa.BIGINT(), nullable=False),
        sa.Column("semantic_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
    )
    sa.Table(
        "brc_budget_reservations", metadata,
        sa.Column("budget_reservation_id", sa.String(192), primary_key=True),
        sa.Column("instrument_rule_snapshot_id", sa.String(192), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("capacity_claim_schema_version", sa.String(32), nullable=True),
    )
    sa.Table(
        "brc_account_exposure_current", metadata,
        sa.Column("account_exposure_current_id", sa.String(192), primary_key=True),
        sa.Column("exchange_instrument_id", sa.String(192), nullable=True),
        sa.Column("exposure_state", sa.String(32), nullable=False),
    )
    metadata.create_all(engine)


def _migration():
    path = ROOT / "migrations/versions/2026-07-17-136_add_instrument_risk_calculation_kind.py"
    spec = importlib.util.spec_from_file_location("instrument_risk_migration_136", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

