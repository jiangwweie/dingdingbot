"""Real PostgreSQL serialization certification for effective policy adoption."""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
from threading import Event, Thread

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa

from src.application.action_time.ticket_exit_policy_adoption_service import (
    apply_ticket_exit_policy_adoption,
    evaluate_ticket_exit_policy_adoption_eligibility,
    revoke_ticket_exit_policy_adoption,
)
from src.application.action_time.ticket_exit_policy_binding import (
    resolve_effective_ticket_exit_policy_binding,
)
from src.domain.ticket_exit_policy import TicketExitPolicySnapshot


ROOT = Path(__file__).resolve().parents[2]
TICKET_ID = "ticket:postgres-adoption"
NOW_MS = 3_000


def test_postgres_two_connections_serialize_accept_revoke_accept() -> None:
    dsn = os.environ["BRC_LOCAL_TEST_POSTGRES_DSN"]
    schema = os.environ["BRC_LOCAL_TEST_POSTGRES_SCHEMA"]
    engine = sa.create_engine(dsn, connect_args={"options": f"-c search_path={schema}"})
    _create_schema(engine)
    try:
        with engine.begin() as conn:
            _apply_migration(conn, "2026-07-16-125_add_active_ticket_exit_policy_adoption.py")
            _apply_migration(
                conn,
                "2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py",
            )
            _seed(conn)
            eligibility = evaluate_ticket_exit_policy_adoption_eligibility(
                conn,
                ticket_id=TICKET_ID,
                exchange_snapshot=_snapshot(),
                owner_authorization_ref="owner:approved",
                runtime_head="c" * 40,
                now_ms=NOW_MS,
            )
            assert eligibility.status == "eligible", eligibility.blockers

        second_started = Event()
        second_done = Event()
        second_result: dict[str, object] = {}

        def second_accept() -> None:
            with engine.begin() as conn:
                second_started.set()
                second_result["result"] = apply_ticket_exit_policy_adoption(
                    conn,
                    eligibility=eligibility,
                    expected_eligibility_hash=eligibility.eligibility_hash,
                    now_ms=NOW_MS + 1,
                )
            second_done.set()

        with engine.begin() as conn:
            first = apply_ticket_exit_policy_adoption(
                conn,
                eligibility=eligibility,
                expected_eligibility_hash=eligibility.eligibility_hash,
                now_ms=NOW_MS + 1,
            )
            worker = Thread(target=second_accept, daemon=True)
            worker.start()
            assert second_started.wait(timeout=2)
            assert second_done.wait(timeout=0.2) is False
        assert second_done.wait(timeout=5)
        worker.join(timeout=1)
        second = second_result["result"]
        assert {first["status"], second["status"]} == {
            "adoption_applied",
            "adoption_idempotent",
        }

        with engine.begin() as conn:
            revoked = revoke_ticket_exit_policy_adoption(
                conn,
                ticket_id=TICKET_ID,
                adoption_event_id=first["adoption_event_id"],
                expected_adoption_projection_version=1,
                now_ms=NOW_MS + 2,
            )
            revoked_binding = resolve_effective_ticket_exit_policy_binding(
                conn,
                ticket_id=TICKET_ID,
                now_ms=NOW_MS + 2,
            )
            assert revoked_binding.mutation_allowed is False
            eligibility_b = evaluate_ticket_exit_policy_adoption_eligibility(
                conn,
                ticket_id=TICKET_ID,
                exchange_snapshot=_snapshot(),
                owner_authorization_ref="owner:approved",
                runtime_head="c" * 40,
                now_ms=NOW_MS + 3,
            )
            accepted_b = apply_ticket_exit_policy_adoption(
                conn,
                eligibility=eligibility_b,
                expected_eligibility_hash=eligibility_b.eligibility_hash,
                now_ms=NOW_MS + 4,
            )
            current = conn.execute(
                sa.text("SELECT * FROM brc_ticket_exit_policy_current")
            ).mappings().one()
            assert revoked["status"] == "adoption_revoked"
            assert current["adoption_event_id"] == accepted_b["adoption_event_id"]
            assert current["adoption_state"] == "accepted"
            assert current["mutation_allowed"] is True
            assert current["adoption_projection_version"] == 3
            assert conn.execute(
                sa.text(
                    "SELECT count(*) FROM brc_ticket_exit_policy_adoption_events "
                    "WHERE decision = 'accepted'"
                )
            ).scalar_one() == 2
    finally:
        engine.dispose()


def _create_schema(engine: sa.Engine) -> None:
    metadata = sa.MetaData()
    sa.Table("brc_action_time_tickets", metadata, sa.Column("ticket_id", sa.String(192), primary_key=True), sa.Column("created_at_ms", sa.BIGINT(), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("strategy_group_id", sa.String(128), nullable=False), sa.Column("strategy_group_version_id", sa.String(160), nullable=False), sa.Column("event_spec_id", sa.String(160), nullable=False), sa.Column("event_spec_version_id", sa.String(200), nullable=False), sa.Column("side", sa.String(32), nullable=False), sa.Column("exchange_instrument_id", sa.String(192), nullable=False), sa.Column("exit_policy_id", sa.String(192), nullable=False), sa.Column("exit_policy_version", sa.String(96), nullable=False), sa.Column("exit_policy_snapshot", sa.JSON(), nullable=False), sa.Column("exit_policy_hash", sa.String(64), nullable=False))
    sa.Table("brc_strategy_exit_policies", metadata, sa.Column("exit_policy_id", sa.String(192), primary_key=True), sa.Column("exit_policy_version", sa.String(96), primary_key=True), sa.Column("strategy_group_id", sa.String(128), nullable=False), sa.Column("strategy_version", sa.String(160), nullable=False), sa.Column("event_spec_id", sa.String(160), nullable=False), sa.Column("event_spec_version", sa.String(160), nullable=False), sa.Column("side", sa.String(32), nullable=False), sa.Column("policy_family", sa.String(64), nullable=False), sa.Column("policy_payload", sa.JSON(), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("approved_by", sa.String(128), nullable=False), sa.Column("approved_at_ms", sa.BIGINT(), nullable=False), sa.Column("created_at_ms", sa.BIGINT(), nullable=False))
    sa.Table("brc_ticket_bound_order_lifecycle_runs", metadata, sa.Column("lifecycle_run_id", sa.String(192), primary_key=True), sa.Column("ticket_id", sa.String(192), nullable=False), sa.Column("status", sa.String(96), nullable=False), sa.Column("entry_filled_qty", sa.Numeric(36, 18), nullable=False), sa.Column("entry_avg_price", sa.Numeric(36, 18), nullable=False), sa.Column("exit_protection_set_id", sa.String(192), nullable=False))
    sa.Table("brc_ticket_bound_exit_protection_sets", metadata, sa.Column("exit_protection_set_id", sa.String(192), primary_key=True), sa.Column("ticket_id", sa.String(192), nullable=False), sa.Column("entry_exchange_order_id", sa.String(192), nullable=False), sa.Column("entry_filled_qty", sa.Numeric(36, 18), nullable=False), sa.Column("entry_avg_price", sa.Numeric(36, 18), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("sl_order_id", sa.String(192), nullable=False), sa.Column("tp1_order_id", sa.String(192), nullable=False), sa.Column("protection_complete", sa.Boolean(), nullable=False), sa.Column("reconciled_with_exchange", sa.Boolean(), nullable=False))
    sa.Table("brc_ticket_bound_exit_protection_orders", metadata, sa.Column("exit_protection_order_id", sa.String(192), primary_key=True), sa.Column("exit_protection_set_id", sa.String(192), nullable=False), sa.Column("ticket_id", sa.String(192), nullable=False), sa.Column("role", sa.String(64), nullable=False), sa.Column("exchange_order_id", sa.String(192), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("order_type", sa.String(64), nullable=False), sa.Column("side", sa.String(32), nullable=False), sa.Column("qty", sa.Numeric(36, 18), nullable=False), sa.Column("price", sa.Numeric(36, 18), nullable=True), sa.Column("trigger_price", sa.Numeric(36, 18), nullable=True), sa.Column("reduce_only", sa.Boolean(), nullable=False), sa.Column("generation", sa.Integer(), nullable=False))
    sa.Table("brc_ticket_bound_exchange_commands", metadata, sa.Column("exchange_command_id", sa.String(192), primary_key=True), sa.Column("ticket_id", sa.String(192), nullable=False), sa.Column("command_state", sa.String(64), nullable=False))
    sa.Table("brc_exchange_instruments", metadata, sa.Column("exchange_instrument_id", sa.String(192), primary_key=True), sa.Column("exchange_id", sa.String(64), nullable=False), sa.Column("exchange_symbol", sa.String(128), nullable=False), sa.Column("price_tick", sa.Numeric(36, 18), nullable=True), sa.Column("quantity_step", sa.Numeric(36, 18), nullable=True))
    sa.Table("brc_ticket_exit_policy_current", metadata, sa.Column("ticket_id", sa.String(192), primary_key=True), sa.Column("exit_protection_set_id", sa.String(192), nullable=True), sa.Column("exit_policy_id", sa.String(192), nullable=False), sa.Column("exit_policy_version", sa.String(96), nullable=False), sa.Column("exit_policy_hash", sa.String(64), nullable=False), sa.Column("exit_execution_snapshot", sa.JSON(), nullable=True), sa.Column("exit_execution_hash", sa.String(64), nullable=True), sa.Column("actual_r_per_unit", sa.Numeric(36, 18), nullable=True), sa.Column("resolved_tp1_price", sa.Numeric(36, 18), nullable=True), sa.Column("resolved_tp1_target_qty", sa.Numeric(36, 18), nullable=True), sa.Column("tp1_cumulative_filled_qty", sa.Numeric(36, 18), nullable=False, server_default="0"), sa.Column("tp1_completion_state", sa.String(32), nullable=False, server_default="unfilled"), sa.Column("remaining_position_qty", sa.Numeric(36, 18), nullable=True), sa.Column("state", sa.String(64), nullable=False, server_default="bound"), sa.Column("first_blocker", sa.String(256), nullable=True), sa.Column("updated_at_ms", sa.BIGINT(), nullable=False))
    metadata.create_all(engine)


def _apply_migration(conn: sa.Connection, filename: str) -> None:
    path = ROOT / "migrations/versions" / filename
    spec = importlib.util.spec_from_file_location(f"postgres_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    previous_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = previous_op


def _seed(conn: sa.Connection) -> None:
    payload = {
        "exit_policy_id": "exit-policy:SOR-001:SOR-LONG:right-tail-v1", "exit_policy_version": "2026-07-15-v1", "strategy_group_id": "SOR-001", "strategy_version": "sgv:SOR-001:v2", "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2", "event_spec_version": "v2", "side": "long", "policy_family": "right_tail_runner", "reward_basis": "actual_entry_r", "take_profit_legs": [{"role": "TP1", "reward_multiple": "1", "quantity_fraction": "0.5", "execution_style": "limit_gtc", "market_fallback_allowed": False}], "tp_completion_tolerance_qty_steps": 1, "post_tp1_floor_rule": {"kind": "runner_leg_cost_adjusted_break_even", "trigger": "tp1_target_quantity_complete", "exit_fee_basis": "conservative_taker", "slippage_buffer_ticks": 2, "minimum_improvement_ticks": 2}, "invalidation_rules": [{"kind": "reference_price_cross", "rule_id": "SOR-LONG:native-invalidation-v1", "trigger": "close_below_or_equal", "reference_key": "opening_range_high"}], "time_stop_rule": {"kind": "max_holding_bars", "max_holding_bars": 96}, "runner_rule": {"kind": "structural_atr", "timeframe": "15m", "structure_rule": "confirmed_higher_low", "structure_window_bars": 4, "atr_period": 14, "atr_buffer_multiple": "0.5", "minimum_improvement_ticks": 2},
    }
    policy = TicketExitPolicySnapshot.with_canonical_hash(payload)
    legacy = {"binding_kind": "legacy_unbound", "historical_semantics_not_synthesized": True}
    legacy_hash = __import__("hashlib").sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    conn.execute(sa.text("INSERT INTO brc_action_time_tickets VALUES (:id,2000,'submitted','SOR-001','sgv:SOR-001:v2','event_spec:SOR-001:SOR-LONG:v2','event_spec:SOR-001:SOR-LONG:v2:v2','long','binance_usdm:AVAX/USDT:USDT','legacy_unbound','legacy_unbound',:legacy,:legacy_hash)"), {"id": TICKET_ID, "legacy": json.dumps(legacy), "legacy_hash": legacy_hash})
    conn.execute(sa.text("INSERT INTO brc_strategy_exit_policies VALUES (:id,:version,'SOR-001','sgv:SOR-001:v2','event_spec:SOR-001:SOR-LONG:v2','v2','long','right_tail_runner',:payload,:hash,'current','owner',1000,1000)"), {"id": policy.exit_policy_id, "version": policy.exit_policy_version, "payload": json.dumps(policy.model_dump(mode="json")), "hash": policy.payload_hash})
    conn.execute(sa.text("INSERT INTO brc_ticket_bound_order_lifecycle_runs VALUES ('lifecycle:postgres',:ticket,'position_protected',65,6.658784615384615385,'protection:postgres')"), {"ticket": TICKET_ID})
    conn.execute(sa.text("INSERT INTO brc_ticket_bound_exit_protection_sets VALUES ('protection:postgres',:ticket,'entry:postgres',65,6.658784615384615385,'reconciled','sl-local','tp1-local',true,true)"), {"ticket": TICKET_ID})
    conn.execute(sa.text("INSERT INTO brc_ticket_bound_exit_protection_orders VALUES ('sl-local','protection:postgres',:ticket,'SL','4000001769200556','open','STOP_MARKET','sell',65,NULL,6.449,true,1), ('tp1-local','protection:postgres',:ticket,'TP1','39583407650','open','LIMIT','sell',32,6.875,NULL,true,1)"), {"ticket": TICKET_ID})
    conn.execute(sa.text("INSERT INTO brc_exchange_instruments VALUES ('binance_usdm:AVAX/USDT:USDT','binance_usdm','AVAX/USDT:USDT',NULL,NULL)"))


def _snapshot() -> dict[str, object]:
    return {"account_id": "owner-subaccount-runtime-v0", "exchange_id": "binance_usdm", "exchange_instrument_id": "binance_usdm:AVAX/USDT:USDT", "exchange_symbol": "AVAX/USDT:USDT", "position_mode": "one_way", "position_side": None, "market_rule": {"exchange_instrument_id": "binance_usdm:AVAX/USDT:USDT", "exchange_id": "binance_usdm", "exchange_market_id": "AVAXUSDT", "price_tick": "0.001", "quantity_step": "1", "min_notional": "5", "source": "binance_usdm_public_exchange_info"}, "position": {"qty": "65", "entry_price": "6.658784615384615385", "position_flat": False, "truth_state": "active"}, "open_orders": [{"exchange_order_id": "4000001769200556", "side": "sell", "position_side": "BOTH", "reduce_only": True, "qty": "65", "price": "", "trigger_price": "6.449", "status": "open"}, {"exchange_order_id": "39583407650", "side": "sell", "position_side": "BOTH", "reduce_only": True, "qty": "32", "price": "6.875", "trigger_price": "", "status": "open"}], "recent_fills": [{"exchange_order_id": "entry:postgres", "qty": "65", "price": "6.658784615384615385", "fee": {"cost": "0.216", "currency": "USDT"}}], "commission_rate": {"symbol": "AVAXUSDT", "maker_commission_rate": "0.0002", "taker_commission_rate": "0.0005"}}
