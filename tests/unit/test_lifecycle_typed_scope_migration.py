from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
)


def test_migration_113_creates_account_mode_current_and_source_domain_holds(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "typed-scope.db"
    config = Config()
    config.set_main_option("script_location", str(Path("migrations").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "106")
    from scripts.seed_runtime_control_state_foundation import (
        seed_runtime_control_state_foundation,
    )

    bootstrap_engine = create_engine(f"sqlite:///{db_path}")
    with bootstrap_engine.begin() as conn:
        seed_runtime_control_state_foundation(
            conn,
            migration_baseline_revision="106",
        )
    bootstrap_engine.dispose()
    command.upgrade(config, "113")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        assert inspector.has_table("brc_runtime_capabilities_current")
        mode_columns = {
            item["name"]
            for item in inspector.get_columns("brc_exchange_account_modes_current")
        }
        hold_columns = {
            item["name"]
            for item in inspector.get_columns("brc_ticket_bound_scope_freezes")
        }
        assert {
            "account_id",
            "exchange_id",
            "position_mode",
            "dual_side_position",
            "position_mode_safe",
            "fact_snapshot_id",
            "valid_until_ms",
        } <= mode_columns
        assert {
            "account_id",
            "exchange_id",
            "exchange_instrument_id",
            "position_mode",
            "position_bucket",
            "netting_domain_key",
            "source_ticket_id",
        } <= hold_columns
        unique_names = {
            item.get("name")
            for item in inspector.get_unique_constraints(
                "brc_ticket_bound_scope_freezes"
            )
        }
        index_names = {
            item.get("name")
            for item in inspector.get_indexes("brc_ticket_bound_scope_freezes")
        }
        assert "uq_brc_scope_freeze_current" not in unique_names
        assert "uq_brc_domain_hold_active_source" in index_names

        with engine.begin() as conn:
            capability = conn.execute(
                text(
                    "SELECT status, certification_ref "
                    "FROM brc_runtime_capabilities_current "
                    "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
                )
            ).mappings().one()
            assert capability["status"] == "disabled"
            assert capability["certification_ref"] == (
                "migration-113:phase-one-fail-closed"
            )
            ids = write_account_safe_fact_snapshots(
                conn,
                artifact={
                    "generated_at_utc": "2026-07-11T09:00:00+00:00",
                    "checks": {
                        "account_safe_facts_ready": True,
                        "account_safe": True,
                        "account_trade_permission": True,
                        "open_orders_clear": True,
                        "active_position_or_open_order_clear": True,
                        "action_time_available_balance": True,
                        "source_signed_get_only": True,
                        "source_exchange_write_called": False,
                        "source_order_created": False,
                    },
                    "facts": {},
                    "account_mode": {
                        "status": "fresh",
                        "account_id": "account-1",
                        "exchange_id": "binance_usdm",
                        "runtime_profile_id": "profile-1",
                        "account_mode": "hedge",
                        "dual_side_position": True,
                        "position_mode_safe": True,
                        "observed_at": "2026-07-11T09:00:00+00:00",
                        "source": (
                            "binance_usdm_signed_get:"
                            "/fapi/v1/positionSide/dual"
                        ),
                    },
                    "blockers": [],
                },
                source_ref="unit:account-mode",
            )
            assert len(ids) == 3
            assert any(":account_capacity_base:" in fact_id for fact_id in ids)
            mode = conn.execute(
                text(
                    "SELECT * FROM brc_exchange_account_modes_current "
                    "WHERE account_id = 'account-1'"
                )
            ).mappings().one()
            assert mode["position_mode"] == "hedge"
            assert mode["dual_side_position"] in {True, 1}
            assert mode["position_mode_safe"] in {True, 1}
            assert mode["fact_snapshot_id"] in ids
            assert mode["valid_until_ms"] - mode["observed_at_ms"] == 300_000

            values = {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "status": "active",
                "first_blocker": "unit_risk",
                "blockers": '["unit_risk"]',
                "freeze_scope": "{}",
                "next_action": "reconcile",
                "authority_boundary": "unit",
                "created_at_ms": 1,
                "updated_at_ms": 1,
                "account_id": "account-1",
                "runtime_profile_id": "profile-1",
                "exchange_id": "binance_usdm",
                "exchange_instrument_id": "instrument-1",
                "position_mode": "one_way",
                "position_bucket": "BOTH",
                "netting_domain_key": "account-1|instrument-1|one_way|BOTH",
                "source_ticket_id": "ticket-1",
            }
            for suffix in ("a", "b"):
                conn.execute(
                    text(
                        """
                        INSERT INTO brc_ticket_bound_scope_freezes (
                          scope_freeze_id, strategy_group_id, symbol, side,
                          status, source_kind, source_id, first_blocker,
                          blockers, freeze_scope, next_action,
                          authority_boundary, created_at_ms, updated_at_ms,
                          account_id, runtime_profile_id, exchange_id,
                          exchange_instrument_id, position_mode,
                          position_bucket, netting_domain_key, source_ticket_id
                        ) VALUES (
                          :scope_freeze_id, :strategy_group_id, :symbol, :side,
                          :status, 'unit', :source_id, :first_blocker,
                          :blockers, :freeze_scope, :next_action,
                          :authority_boundary, :created_at_ms, :updated_at_ms,
                          :account_id, :runtime_profile_id, :exchange_id,
                          :exchange_instrument_id, :position_mode,
                          :position_bucket, :netting_domain_key, :source_ticket_id
                        )
                        """
                    ),
                    {
                        **values,
                        "scope_freeze_id": f"hold-{suffix}",
                        "source_id": f"source-{suffix}",
                    },
                )
            assert conn.execute(
                text(
                    "SELECT count(*) FROM brc_ticket_bound_scope_freezes "
                    "WHERE status = 'active'"
                )
            ).scalar_one() == 2
    finally:
        engine.dispose()
