from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa

from src.application.action_time.account_exchange_ownership import (
    AccountExchangeTruthClassification,
    AccountOrderClassification,
    AccountPositionClassification,
)
from src.application.action_time.account_exposure_current import (
    project_account_exposure_current,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    ExchangeOpenOrderRow,
    ExchangePositionRow,
    FullAccountRiskSnapshot,
)


NOW_MS = 1_752_480_000_000


def test_owned_position_with_confirmed_stop_projects_directional_risk_once() -> None:
    conn = _connection()
    snapshot = _snapshot(
        positions=(
            ExchangePositionRow(
                exchange_symbol="ETHUSDT",
                position_qty=Decimal("0.1"),
                entry_price=Decimal("2000"),
            ),
        ),
        orders=(
            ExchangeOpenOrderRow(
                exchange_symbol="ETHUSDT",
                exchange_order_id="stop-1",
                quantity=Decimal("0.1"),
                trigger_price=Decimal("1900"),
            ),
        ),
    )
    classification = _classification(
        position=AccountPositionClassification(
            exchange_symbol="ETHUSDT",
            exchange_instrument_id="binance_usdm:ETHUSDT",
            ownership_state="owned_by_ticket",
            owner_ticket_id="ticket-1",
        ),
        order=AccountOrderClassification(
            exchange_symbol="ETHUSDT",
            exchange_order_id="stop-1",
            algo_id="",
            client_order_id="",
            ownership_state="owned_by_ticket",
            purpose="initial_stop",
            owner_ticket_id="ticket-1",
        ),
    )

    first = project_account_exposure_current(
        conn,
        snapshot=snapshot,
        classification=classification,
        now_ms=NOW_MS,
    )
    second = project_account_exposure_current(
        conn,
        snapshot=snapshot,
        classification=classification,
        now_ms=NOW_MS + 1,
    )

    assert first.global_blockers == ()
    assert first.rows[0].exposure_state == "open_protected"
    assert first.rows[0].held_risk == Decimal("10")
    assert first.rows[0].position_slot_claimed is True
    assert second.semantic_event_count == 0
    assert conn.execute(sa.text("SELECT COUNT(*) FROM brc_account_risk_projection_events")).scalar_one() == 1


def test_owned_position_without_confirmed_stop_is_global_fail_closed() -> None:
    conn = _connection()
    result = project_account_exposure_current(
        conn,
        snapshot=_snapshot(
            positions=(
                ExchangePositionRow(
                    exchange_symbol="ETHUSDT",
                    position_qty=Decimal("0.1"),
                    entry_price=Decimal("2000"),
                ),
            )
        ),
        classification=_classification(
            position=AccountPositionClassification(
                exchange_symbol="ETHUSDT",
                exchange_instrument_id="binance_usdm:ETHUSDT",
                ownership_state="owned_by_ticket",
                owner_ticket_id="ticket-1",
            )
        ),
        now_ms=NOW_MS,
    )

    assert result.rows[0].exposure_state == "open_unprotected"
    assert result.rows[0].first_blocker == "account_exposure_protection_missing"
    assert result.global_blockers == ("account_exposure_protection_missing",)


def test_active_reservation_without_position_projects_reserved_slot() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
                budget_reservation_id, ticket_id, account_id, symbol, side, status,
                risk_at_stop, reserved_margin
            ) VALUES (
                'budget-1', 'ticket-1', 'account-1', 'ETHUSDT', 'long', 'active',
                '15', '30'
            )
            """
        )
    )

    result = project_account_exposure_current(
        conn,
        snapshot=_snapshot(),
        classification=AccountExchangeTruthClassification(
            orders=(), positions=(), new_entry_allowed=True, blockers=()
        ),
        now_ms=NOW_MS,
    )

    assert result.rows[0].exposure_state == "reserved"
    assert result.rows[0].held_risk == Decimal("15")
    assert result.rows[0].position_slot_claimed is True


def test_partial_fill_with_remaining_entry_holds_the_larger_planned_risk() -> None:
    conn = _connection()
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_budget_reservations (
                budget_reservation_id, ticket_id, account_id, symbol, side, status,
                risk_at_stop, reserved_margin
            ) VALUES ('budget-1', 'ticket-1', 'account-1', 'ETHUSDT', 'long',
                      'consumed', '15', '30')
            """
        )
    )
    snapshot = _snapshot(
        positions=(
            ExchangePositionRow(
                exchange_symbol="ETHUSDT",
                position_qty=Decimal("0.05"),
                entry_price=Decimal("2000"),
            ),
        ),
        orders=(
            ExchangeOpenOrderRow(
                exchange_symbol="ETHUSDT", exchange_order_id="stop-1",
                quantity=Decimal("0.1"), trigger_price=Decimal("1900"),
            ),
            ExchangeOpenOrderRow(
                exchange_symbol="ETHUSDT", exchange_order_id="entry-1",
                quantity=Decimal("0.05"), price=Decimal("2000"),
            ),
        ),
    )
    classification = AccountExchangeTruthClassification(
        positions=(
            AccountPositionClassification(
                exchange_symbol="ETHUSDT", exchange_instrument_id="binance_usdm:ETHUSDT",
                ownership_state="owned_by_ticket", owner_ticket_id="ticket-1",
            ),
        ),
        orders=(
            AccountOrderClassification(
                exchange_symbol="ETHUSDT", exchange_order_id="stop-1", algo_id="",
                client_order_id="", ownership_state="owned_by_ticket",
                purpose="initial_stop", owner_ticket_id="ticket-1",
            ),
            AccountOrderClassification(
                exchange_symbol="ETHUSDT", exchange_order_id="entry-1", algo_id="",
                client_order_id="", ownership_state="owned_by_ticket",
                purpose="working_entry", owner_ticket_id="ticket-1",
            ),
        ),
        new_entry_allowed=True,
        blockers=(),
    )

    result = project_account_exposure_current(
        conn, snapshot=snapshot, classification=classification, now_ms=NOW_MS
    )

    assert result.rows[0].exposure_state == "working_entry"
    assert result.rows[0].actual_directional_risk == Decimal("5")
    assert result.rows[0].working_entry_qty == Decimal("0.05")
    assert result.rows[0].held_risk == Decimal("15")


def test_unowned_position_projects_unknown_and_blocks_new_entry() -> None:
    conn = _connection()
    result = project_account_exposure_current(
        conn,
        snapshot=_snapshot(
            positions=(
                ExchangePositionRow(
                    exchange_symbol="SOLUSDT", position_qty=Decimal("1"),
                    entry_price=Decimal("150"),
                ),
            )
        ),
        classification=_classification(
            position=AccountPositionClassification(
                exchange_symbol="SOLUSDT", exchange_instrument_id="binance_usdm:SOLUSDT",
                ownership_state="external_unowned",
                blocker="account_exchange_position_unknown_global_fail_closed",
            )
        ),
        now_ms=NOW_MS,
    )

    assert result.rows[0].exposure_state == "unknown"
    assert result.global_blockers == ("account_exchange_position_unknown_global_fail_closed",)


def test_flat_matched_snapshot_releases_previously_projected_slot() -> None:
    conn = _connection()
    position = ExchangePositionRow(
        exchange_symbol="ETHUSDT", position_qty=Decimal("0.1"),
        entry_price=Decimal("2000"),
    )
    classification = _classification(
        position=AccountPositionClassification(
            exchange_symbol="ETHUSDT", exchange_instrument_id="binance_usdm:ETHUSDT",
            ownership_state="owned_by_ticket", owner_ticket_id="ticket-1",
        ),
        order=AccountOrderClassification(
            exchange_symbol="ETHUSDT", exchange_order_id="stop-1", algo_id="",
            client_order_id="", ownership_state="owned_by_ticket",
            purpose="initial_stop", owner_ticket_id="ticket-1",
        ),
    )
    project_account_exposure_current(
        conn,
        snapshot=_snapshot(
            positions=(position,),
            orders=(
                ExchangeOpenOrderRow(
                    exchange_symbol="ETHUSDT", exchange_order_id="stop-1",
                    quantity=Decimal("0.1"), trigger_price=Decimal("1900"),
                ),
            ),
        ),
        classification=classification,
        now_ms=NOW_MS,
    )

    result = project_account_exposure_current(
        conn,
        snapshot=_snapshot(),
        classification=AccountExchangeTruthClassification(
            orders=(), positions=(), new_entry_allowed=True, blockers=()
        ),
        now_ms=NOW_MS + 1,
    )

    assert result.rows[0].exposure_state == "flat"
    assert result.rows[0].held_risk == Decimal("0")
    assert result.rows[0].position_slot_claimed is False


def _snapshot(
    *,
    positions: tuple[ExchangePositionRow, ...] = (),
    orders: tuple[ExchangeOpenOrderRow, ...] = (),
) -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        positions=positions,
        regular_open_orders=orders,
        source_snapshot_id="snapshot-1",
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 60_000,
    )


def _classification(
    *,
    position: AccountPositionClassification,
    order: AccountOrderClassification | None = None,
) -> AccountExchangeTruthClassification:
    return AccountExchangeTruthClassification(
        orders=(order,) if order else (),
        positions=(position,),
        new_entry_allowed=True,
        blockers=(),
    )


def _connection() -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_exposure_current (
                account_exposure_current_id TEXT PRIMARY KEY,
                account_id TEXT, exchange_id TEXT, exchange_instrument_id TEXT,
                exchange_symbol TEXT, position_mode TEXT, position_bucket TEXT,
                netting_domain_key TEXT, owner_ticket_id TEXT, ownership_state TEXT,
                position_slot_claimed BOOLEAN, exposure_state TEXT, position_qty NUMERIC,
                entry_price NUMERIC, confirmed_stop_price NUMERIC, working_entry_qty NUMERIC,
                planned_reserved_risk NUMERIC, actual_directional_risk NUMERIC,
                held_risk NUMERIC, exchange_initial_margin NUMERIC,
                unreflected_pending_margin NUMERIC, protection_state TEXT,
                stop_covered_qty NUMERIC, tp1_open_qty NUMERIC, runner_stop_open_qty NUMERIC,
                reconciliation_state TEXT, first_blocker TEXT, source_snapshot_id TEXT,
                observed_at_ms BIGINT, valid_until_ms BIGINT, projection_version BIGINT,
                semantic_fingerprint TEXT, updated_at_ms BIGINT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_account_risk_projection_events (
                account_risk_projection_event_id TEXT PRIMARY KEY,
                account_exposure_current_id TEXT, semantic_fingerprint TEXT,
                event_payload TEXT, created_at_ms BIGINT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_budget_reservations (
                budget_reservation_id TEXT PRIMARY KEY, ticket_id TEXT, account_id TEXT,
                symbol TEXT, side TEXT, status TEXT, risk_at_stop NUMERIC,
                reserved_margin NUMERIC
            )
            """
        )
    )
    return conn
