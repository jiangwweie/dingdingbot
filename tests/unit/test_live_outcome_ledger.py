from __future__ import annotations

from decimal import Decimal

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
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
    _submitted_orders,
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


def test_live_outcome_blocks_mismatched_exposure_episode_lineage(
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
    exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 5500,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET exposure_episode_id = 'exposure_episode:wrong' "
            "WHERE ticket_id = :ticket_id AND order_role = 'TP1'"
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 6000,
    )

    assert payload["status"] == "blocked_invalid_exposure_episode_lineage"
    assert payload["blockers"] == ["live_outcome_exposure_episode_mismatch"]
    assert pg_control_connection.execute(
        text("SELECT count(*) FROM brc_live_outcome_ledger")
    ).scalar_one() == 0


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
