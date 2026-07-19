from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from scripts import seed_runtime_control_state_foundation as seed
from src.domain.instrument_risk_identity import build_canonical_exchange_instrument_id


ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
EXPAND = ROOT / "migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py"
CUTOVER = ROOT / "migrations/versions/2026-07-19-138_cutover_canonical_instrument_identity.py"


def test_migration_138_replaces_legacy_current_generation_without_rewriting_history() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade(conn, FOUNDATION, "migration_086_canonical_cutover")
        _upgrade(conn, EXPAND, "migration_131_canonical_cutover")
        seed.seed_runtime_control_state_foundation(conn)
        legacy_ids = _convert_seed_to_legacy_generation(conn)

        _upgrade(conn, CUTOVER, "migration_138_canonical_cutover")

        active_instruments = conn.execute(
            sa.text(
                """SELECT exchange_instrument_id, exchange_symbol, asset_class,
                          instrument_type, settlement_asset, margin_asset,
                          instrument_identity_schema_version
                FROM brc_exchange_instruments
                WHERE status = 'active'
                ORDER BY exchange_symbol"""
            )
        ).mappings().all()
        instrument_statuses = conn.execute(
            sa.text(
                """SELECT status, count(*) FROM brc_exchange_instruments
                GROUP BY status ORDER BY status"""
            )
        ).all()
        candidate_statuses = conn.execute(
            sa.text(
                """SELECT status, count(*) FROM brc_strategy_group_candidate_scope
                GROUP BY status ORDER BY status"""
            )
        ).all()
        binding_statuses = conn.execute(
            sa.text(
                """SELECT status, count(*) FROM brc_candidate_scope_event_bindings
                GROUP BY status ORDER BY status"""
            )
        ).all()
        runtime_statuses = conn.execute(
            sa.text(
                """SELECT status, count(*) FROM brc_runtime_scope_bindings
                GROUP BY status ORDER BY status"""
            )
        ).all()
        active_candidate_ids = conn.execute(
            sa.text(
                """SELECT candidate_scope_id
                FROM brc_strategy_group_candidate_scope
                WHERE status = 'active'"""
            )
        ).scalars().all()

    assert len(active_instruments) == 6
    assert all(
        row["exchange_instrument_id"]
        == build_canonical_exchange_instrument_id(
            exchange_id="binance_usdm",
            exchange_symbol=row["exchange_symbol"],
            asset_class="crypto",
            instrument_type="perpetual",
            settlement_asset="USDT",
            margin_asset="USDT",
        )
        and row["asset_class"] == "crypto"
        and row["instrument_type"] == "perpetual"
        and row["settlement_asset"] == "USDT"
        and row["margin_asset"] == "USDT"
        and row["instrument_identity_schema_version"] == "v2"
        for row in active_instruments
    )
    assert instrument_statuses == [("active", 6), ("retired", 6)]
    assert candidate_statuses == [("active", 22), ("revoked", 22)]
    assert binding_statuses == [("active", 22), ("revoked", 22)]
    assert runtime_statuses == [("active", 22), ("revoked", 22)]
    assert all(value.endswith(":identity-v2") for value in active_candidate_ids)
    with engine.connect() as conn:
        retired_ids = set(
            conn.execute(
                sa.text(
                    """SELECT exchange_instrument_id
                    FROM brc_exchange_instruments WHERE status = 'retired'"""
                )
            ).scalars()
        )
    assert set(legacy_ids) == retired_ids


def test_migration_138_rejects_unexpected_legacy_identity_before_cutover() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _upgrade(conn, FOUNDATION, "migration_086_canonical_cutover_negative")
        _upgrade(conn, EXPAND, "migration_131_canonical_cutover_negative")
        seed.seed_runtime_control_state_foundation(conn)
        _convert_seed_to_legacy_generation(conn)
        conn.execute(
            sa.text(
                """UPDATE brc_exchange_instruments
                SET instrument_type = 'perpetual'
                WHERE exchange_symbol = 'BTC/USDT:USDT'"""
            )
        )

        with pytest.raises(
            RuntimeError,
            match="canonical_instrument_cutover_legacy_registry_shape_invalid",
        ):
            _upgrade(conn, CUTOVER, "migration_138_canonical_cutover_negative")

        assert conn.execute(
            sa.text(
                """SELECT count(*) FROM brc_strategy_group_candidate_scope
                WHERE status = 'active'"""
            )
        ).scalar_one() == 22
        assert conn.execute(
            sa.text(
                """SELECT count(*) FROM brc_exchange_instruments
                WHERE status = 'retired'"""
            )
        ).scalar_one() == 0


def test_migration_138_is_forward_only() -> None:
    module = _load(CUTOVER, "migration_138_forward_only")
    with pytest.raises(
        RuntimeError,
        match="canonical_instrument_identity_cutover_is_forward_only",
    ):
        module.downgrade()


def _convert_seed_to_legacy_generation(conn: sa.Connection) -> tuple[str, ...]:
    instruments = conn.execute(
        sa.text(
            """SELECT exchange_instrument_id, exchange_symbol
            FROM brc_exchange_instruments ORDER BY exchange_symbol"""
        )
    ).mappings().all()
    legacy_ids: list[str] = []
    for row in instruments:
        canonical_id = str(row["exchange_instrument_id"])
        legacy_id = f"binance_usdm:{row['exchange_symbol']}"
        legacy_ids.append(legacy_id)
        conn.execute(
            sa.text(
                """UPDATE brc_strategy_group_candidate_scope
                SET exchange_instrument_id = :legacy_id,
                    asset_class = 'crypto_usdm_perp'
                WHERE exchange_instrument_id = :canonical_id"""
            ),
            {"legacy_id": legacy_id, "canonical_id": canonical_id},
        )
        conn.execute(
            sa.text(
                """UPDATE brc_symbol_instrument_mappings
                SET exchange_instrument_id = :legacy_id
                WHERE exchange_instrument_id = :canonical_id"""
            ),
            {"legacy_id": legacy_id, "canonical_id": canonical_id},
        )
        conn.execute(
            sa.text(
                """UPDATE brc_exchange_instruments
                SET exchange_instrument_id = :legacy_id,
                    asset_class = 'crypto_usdm_perp',
                    instrument_type = NULL,
                    settlement_asset = NULL,
                    margin_asset = NULL,
                    instrument_identity_schema_version = NULL
                WHERE exchange_instrument_id = :canonical_id"""
            ),
            {"legacy_id": legacy_id, "canonical_id": canonical_id},
        )
    conn.execute(
        sa.text(
            """UPDATE brc_symbols SET asset_class = 'crypto_usdm_perp'
            WHERE status = 'active'"""
        )
    )
    return tuple(legacy_ids)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _upgrade(conn: sa.Connection, path: Path, name: str) -> None:
    module = _load(path, name)
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old_op
