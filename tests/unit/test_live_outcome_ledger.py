from __future__ import annotations

from decimal import Decimal
import json

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.live_outcome_ledger import (
    _compatible_fee_total,
    _exit_slippage,
    _realized_pnl,
    _ticket_bound_funding_total,
    materialize_live_outcome_ledger,
)
from src.application.action_time.ticket_bound_fill_projector import (
    project_ticket_bound_exchange_fills,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_first_reconciliation_tick,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_post_submit_reconciliation_tick import (
    _attempt_snapshot,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_live_outcome_rejects_bare_closed_status_without_closure_lineage(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    result = submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )
    assert result["status"] == "submitted"
    proof = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert proof["status"] == "position_protected"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_order_lifecycle_runs
            SET status = 'lifecycle_closed',
                updated_at_ms = :updated_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"], "updated_at_ms": NOW_MS + 7000},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "blocked_invalid_lifecycle_lineage"
    assert payload["first_blocker"] == (
        "live_outcome_closed_post_submit_closure_missing"
    )
    assert pg_control_connection.execute(
        text("SELECT count(*) FROM brc_live_outcome_ledger")
    ).scalar_one() == 0


def test_live_outcome_ledger_ignores_disabled_smoke(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    assert prepared["status"] == "disabled_smoke_passed"

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 5000,
    )

    assert payload["status"] == "not_applicable_no_real_submit"
    assert (
        pg_control_connection.execute(
            text("SELECT count(*) FROM brc_live_outcome_ledger")
        ).scalar_one()
        == 0
    )


def test_live_outcome_projects_actual_exit_fill_fees_pnl_and_r_multiple(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    orders = _submitted_orders(prepared)
    entry = next(row for row in orders if row["order_role"] == "ENTRY")
    entry["fee"] = {"cost": "0.01", "currency": "USDT"}
    entry["fill_time_ms"] = NOW_MS + 4_900
    submit.record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": orders,
        },
        now_ms=NOW_MS + 5_000,
    )
    exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6_000,
    )
    sl = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id, qty, trigger_price "
            "FROM brc_ticket_bound_exit_protection_orders WHERE role = 'SL'"
        )
    ).mappings().one()
    project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": sl["exchange_order_id"],
                    "qty": str(sl["qty"]),
                    "price": "1990",
                    "fee": {"cost": "0.02", "currency": "USDT"},
                    "timestamp_ms": NOW_MS + 7_000,
                }
            ],
            "funding_income": [
                {
                    "income_id": "funding-1",
                    "symbol": "ETHUSDT",
                    "income_type": "FUNDING_FEE",
                    "amount": "-0.05",
                    "asset": "USDT",
                    "timestamp_ms": NOW_MS + 6_500,
                    "attribution_basis": "single_active_position_exact_symbol_time_window",
                },
                {
                    "income_id": "funding-other-symbol",
                    "symbol": "BTCUSDT",
                    "income_type": "FUNDING_FEE",
                    "amount": "10",
                    "asset": "USDT",
                    "timestamp_ms": NOW_MS + 6_500,
                    "attribution_basis": "single_active_position_exact_symbol_time_window",
                },
            ],
        },
        now_ms=NOW_MS + 7_000,
    )
    # Financial projection is also valid for a recovered lifecycle before
    # terminal closure; closed outcomes require the full finalizer lineage.
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_order_lifecycle_runs "
            "SET status = 'reconciliation_matched', updated_at_ms = :now_ms "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"], "now_ms": NOW_MS + 8_000},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 9_000,
    )

    outcome = payload["outcome"]
    expected_gross = (Decimal("1990") - Decimal("2000")) * Decimal(
        str(entry["filled_qty"])
    )
    assert outcome["final_exit_price"] == Decimal("1990")
    assert outcome["final_exit_time_ms"] == NOW_MS + 7_000
    assert outcome["fees"] == Decimal("0.03")
    assert outcome["entry_slippage"] == Decimal("0")
    expected_exit_slippage = (Decimal(str(sl["trigger_price"])) - Decimal("1990")) * Decimal(
        str(sl["qty"])
    )
    assert outcome["exit_slippage"] == expected_exit_slippage
    assert outcome["realized_pnl"] == expected_gross
    assert outcome["funding"] == Decimal("-0.05")
    assert outcome["net_pnl"] == expected_gross - Decimal("0.03") - Decimal("0.05")
    assert outcome["r_multiple"] == (
        expected_gross - Decimal("0.03") - Decimal("0.05")
    ) / Decimal(str(outcome["risk_at_stop"]))
    stored = pg_control_connection.execute(
        text(
            "SELECT funding, exit_slippage, net_pnl "
            "FROM brc_live_outcome_ledger WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).mappings().one()
    assert Decimal(str(stored["funding"])) == Decimal("-0.05")
    assert Decimal(str(stored["exit_slippage"])) == expected_exit_slippage
    assert Decimal(str(stored["net_pnl"])) == outcome["net_pnl"]


def test_tp1_gtc_taker_fill_records_economic_truth_without_lifecycle_defect(
    pg_control_connection,
):
    ids, _, tp1 = _submitted_attempt_with_protection(pg_control_connection)

    projected = project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": tp1["exchange_order_id"],
                    "qty": str(tp1["qty"]),
                    "price": str(tp1["price"]),
                    "fee": {"cost": "0.21", "currency": "USDT"},
                    "liquidity_role": "taker",
                    "timestamp_ms": NOW_MS + 7_000,
                }
            ]
        },
        now_ms=NOW_MS + 7_000,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_order_lifecycle_runs "
            "SET status = 'reconciliation_matched', first_blocker = NULL, "
            "blockers = '[]', updated_at_ms = :now_ms "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"], "now_ms": NOW_MS + 8_000},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 9_000,
    )

    assert projected["status"] == "fills_projected"
    assert payload["status"] == "recorded"
    outcome = payload["outcome"]
    assert outcome["tp1_liquidity_role"] == "taker"
    assert outcome["tp1_fee"] == Decimal("0.21")
    assert outcome["tp1_fee_asset"] == "USDT"
    assert outcome["source_refs"]["tp1_order_type"] == "limit"
    assert outcome["source_refs"]["tp1_time_in_force"] == "GTC"
    assert "tp1_gtx_taker_contradiction" not in outcome["lifecycle_defects"]


def test_tp1_gtx_taker_fill_hard_stops_as_contradictory_truth(
    pg_control_connection,
):
    ids, _, tp1 = _submitted_attempt_with_protection(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET execution_style = 'passive_limit_gtx', time_in_force = 'GTX', "
            "post_only = true WHERE order_role = 'TP1'"
        )
    )

    projected = project_ticket_bound_exchange_fills(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        exchange_snapshot={
            "recent_fills": [
                {
                    "exchange_order_id": tp1["exchange_order_id"],
                    "qty": str(tp1["qty"]),
                    "price": str(tp1["price"]),
                    "fee": {"cost": "0.05", "currency": "USDT"},
                    "liquidity_role": "taker",
                    "timestamp_ms": NOW_MS + 7_000,
                }
            ]
        },
        now_ms=NOW_MS + 7_000,
    )

    lifecycle = pg_control_connection.execute(
        text(
            "SELECT status, first_blocker FROM "
            "brc_ticket_bound_order_lifecycle_runs WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).mappings().one()
    assert projected["status"] == "blocked"
    assert projected["first_blocker"] == "tp1_gtx_taker_contradiction"
    assert lifecycle["status"] == "blocked"
    assert lifecycle["first_blocker"] == "tp1_gtx_taker_contradiction"


def test_live_outcome_keeps_selected_configured_and_effective_leverage_separate(
    pg_control_connection,
):
    ids, prepared, _ = _submitted_attempt_with_protection(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET exchange_result = :exchange_result "
            "WHERE order_role = 'ENTRY'"
        ),
        {
            "exchange_result": json.dumps(
                {
                    "selected_leverage": 2,
                    "exchange_configured_initial_leverage": 2,
                    "leverage_verified_at_ms": NOW_MS + 5_500,
                }
            )
        },
    )
    snapshot = _attempt_snapshot(prepared)
    snapshot["account_exposure"] = {
        "status": "ready",
        "account_id": "owner-subaccount-runtime-v0",
        "exchange_id": "binance_usdm",
        "account_margin_balance": "100",
        "gross_open_position_notional": "250",
        "effective_account_exposure_leverage": "2.5",
        "observed_at_ms": NOW_MS + 6_400,
        "blockers": [],
    }
    tick = materialize_ticket_bound_first_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_snapshot=snapshot,
        now_ms=NOW_MS + 6_500,
    )
    assert tick["status"] == "matched"
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_order_lifecycle_runs "
            "SET status = 'reconciliation_matched', first_blocker = NULL, "
            "blockers = '[]', updated_at_ms = :now_ms "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"], "now_ms": NOW_MS + 8_000},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 9_000,
    )

    outcome = payload["outcome"]
    assert outcome["leverage"] == Decimal("2")
    assert outcome["exchange_configured_initial_leverage"] == Decimal("2")
    assert outcome["effective_account_exposure_leverage"] == Decimal("2.5")
    assert outcome["source_refs"]["effective_leverage_status"] == "ready"


def test_funding_attribution_rejects_conflicting_duplicate_and_excludes_unrelated_rows():
    rows = [
        {
            "income_id": "funding-1",
            "ticket_id": "ticket-1",
            "symbol": "ETHUSDT",
            "income_type": "FUNDING_FEE",
            "amount": "-0.10",
            "asset": "USDT",
            "timestamp_ms": 1500,
            "attribution_basis": "single_active_position_exact_symbol_time_window",
        },
        {
            "income_id": "funding-1",
            "ticket_id": "ticket-1",
            "symbol": "ETHUSDT",
            "income_type": "FUNDING_FEE",
            "amount": "-0.20",
            "asset": "USDT",
            "timestamp_ms": 1500,
            "attribution_basis": "single_active_position_exact_symbol_time_window",
        },
    ]
    assert _ticket_bound_funding_total(
        rows,
        ticket_id="ticket-1",
        symbol="ETHUSDT",
        entry_time_ms=1000,
        final_exit_time_ms=2000,
    ) is None

    assert _ticket_bound_funding_total(
        [
            rows[0],
            {**rows[0], "income_id": "other", "symbol": "BTCUSDT", "amount": "5"},
        ],
        ticket_id="ticket-1",
        symbol="ETHUSDT",
        entry_time_ms=1000,
        final_exit_time_ms=2000,
    ) == Decimal("-0.10")


def test_first_real_sol_trade_exact_fee_and_net_pnl_regression():
    gross = _realized_pnl(
        side="short",
        entry_price=Decimal("75.47"),
        entry_qty=Decimal("0.8"),
        exits=[
            (Decimal("74.29"), Decimal("0.4")),
            (Decimal("74.75"), Decimal("0.4")),
        ],
    )
    fees = _compatible_fee_total(
        {"cost": "0.030188", "currency": "USDT"},
        {"cost": "0.0059432", "currency": "USDT"},
        {"cost": "0.01495", "currency": "USDT"},
    )

    assert gross == Decimal("0.760")
    assert fees == Decimal("0.0510812")
    assert gross - fees == Decimal("0.7089188")


def test_closed_outcome_fee_total_requires_every_known_fill_fee():
    assert _compatible_fee_total(
        {"cost": "0.030188", "currency": "USDT"},
        None,
        {"cost": "0.01495", "currency": "USDT"},
        require_all=True,
    ) is None


def test_funding_is_exact_zero_only_when_exchange_read_was_available():
    assert _ticket_bound_funding_total(
        [],
        ticket_id="ticket-1",
        symbol="SOLUSDT",
        entry_time_ms=1000,
        final_exit_time_ms=2000,
        funding_available=True,
    ) == Decimal("0")
    assert _ticket_bound_funding_total(
        [],
        ticket_id="ticket-1",
        symbol="SOLUSDT",
        entry_time_ms=1000,
        final_exit_time_ms=2000,
        funding_available=False,
    ) is None


def test_exit_slippage_is_signed_adverse_cost_for_long_and_short():
    assert _exit_slippage(
        side="long",
        reference_price=Decimal("100"),
        fill_price=Decimal("99"),
        fill_qty=Decimal("2"),
    ) == Decimal("2")
    assert _exit_slippage(
        side="short",
        reference_price=Decimal("100"),
        fill_price=Decimal("101"),
        fill_qty=Decimal("2"),
    ) == Decimal("2")


def _submitted_attempt_with_protection(conn):
    ids = _create_ready_protected_submit(conn)
    prepared = _prepare_real_submit(conn, ids)
    submitted_orders = _submitted_orders(prepared)
    result = submit.record_ticket_bound_protected_submit_result(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": submitted_orders,
        },
        now_ms=NOW_MS + 5_000,
    )
    assert result["status"] == "submitted"
    exit_protection.materialize_ticket_bound_exit_protection_set(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6_000,
    )
    tp1 = conn.execute(
        text(
            "SELECT * FROM brc_ticket_bound_exit_protection_orders "
            "WHERE role = 'TP1'"
        )
    ).mappings().one()
    return ids, prepared, dict(tp1)
