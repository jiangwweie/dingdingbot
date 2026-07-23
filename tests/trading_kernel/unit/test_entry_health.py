from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.account_entry_health import (
    AccountEntryHealthStatus,
    classify_account_entry_health,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    AdmissionOrder,
    AdmissionOwnership,
    AdmissionPosition,
    EntryAdmissionSnapshot,
)
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.instrument_entry_health import (
    InstrumentEntryHealthStatus,
    classify_instrument_entry_health,
)


def test_unowned_order_anywhere_blocks_cross_account_with_shared_digest() -> None:
    snapshot = _snapshot(
        open_orders=(
            AdmissionOrder(
                exchange_order_id="manual:btc:1",
                venue_client_order_id=None,
                exchange_instrument_id="BTCUSDT",
                position_side="long",
                reduce_only=False,
            ),
        )
    )
    ownership = AdmissionOwnership()

    account = classify_account_entry_health(snapshot, ownership)
    instrument = classify_instrument_entry_health(
        snapshot,
        ownership,
        exchange_instrument_id="SOLUSDT",
        requested_position_side="short",
    )

    assert account.status is AccountEntryHealthStatus.UNOWNED_ORDER
    assert account.entry_block_scope is EntryBlockScope.ACCOUNT_CAPACITY
    assert account.entry_admission_snapshot_digest == snapshot.digest()
    assert instrument.entry_admission_snapshot_digest == snapshot.digest()


def test_owned_opposite_side_position_allows_shared_leverage_without_mutation() -> None:
    snapshot = _snapshot(
        positions=(
            AdmissionPosition(
                exchange_instrument_id="SOLUSDT",
                position_side="long",
                quantity=Decimal("0.25"),
                average_entry_price=Decimal("100"),
            ),
        ),
        open_orders=(
            AdmissionOrder(
                exchange_order_id="stop:1",
                venue_client_order_id="brc-stop-1",
                exchange_instrument_id="SOLUSDT",
                position_side="long",
                reduce_only=True,
            ),
        ),
    )
    ownership = AdmissionOwnership(
        owned_position_domain_keys=(
            "binance-usdm:subaccount-main:SOLUSDT:long",
        ),
        owned_exchange_order_ids=("stop:1",),
    )

    health = classify_instrument_entry_health(
        snapshot,
        ownership,
        exchange_instrument_id="SOLUSDT",
        requested_position_side="short",
    )

    assert health.status is InstrumentEntryHealthStatus.HEALTHY_OPPOSITE_SIDE
    assert health.configured_leverage == 3
    assert health.leverage_change_allowed is False
    assert health.entry_block_scope is EntryBlockScope.NONE


def test_owned_residual_order_after_flatness_blocks_only_leverage_domain() -> None:
    snapshot = _snapshot(
        open_orders=(
            AdmissionOrder(
                exchange_order_id="residue:1",
                venue_client_order_id="brc-residue-1",
                exchange_instrument_id="SOLUSDT",
                position_side="long",
                reduce_only=True,
            ),
        ),
    )
    ownership = AdmissionOwnership(owned_exchange_order_ids=("residue:1",))

    health = classify_instrument_entry_health(
        snapshot,
        ownership,
        exchange_instrument_id="SOLUSDT",
        requested_position_side="short",
    )

    assert health.status is InstrumentEntryHealthStatus.OWNED_RESIDUAL_ORDER
    assert health.entry_block_scope is EntryBlockScope.LEVERAGE_DOMAIN
    assert health.entry_block_key == "binance-usdm:subaccount-main:SOLUSDT"


def _snapshot(
    *,
    positions: tuple[AdmissionPosition, ...] = (),
    open_orders: tuple[AdmissionOrder, ...] = (),
) -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        venue_id="binance-usdm",
        account_id="subaccount-main",
        position_mode="independent_sides",
        margin_mode="cross",
        total_wallet_balance=Decimal("100"),
        total_margin_balance=Decimal("100"),
        total_initial_margin=Decimal("10"),
        total_maintenance_margin=Decimal("1"),
        available_margin=Decimal("90"),
        best_bid_price=Decimal("100"),
        best_ask_price=Decimal("101"),
        instrument_facts=(
            AdmissionInstrumentFacts(
                exchange_instrument_id="SOLUSDT",
                mark_price=Decimal("100.5"),
                configured_leverage=3,
            ),
        ),
        positions=positions,
        open_orders=open_orders,
        observed_at_ms=1_800_000_000_000,
        valid_until_ms=1_800_000_005_000,
    )
