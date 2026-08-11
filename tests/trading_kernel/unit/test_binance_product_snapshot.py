from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.infrastructure.binance_product_snapshot import (
    parse_binance_product_snapshots,
)

OBSERVED_MS = 1_800_000_000_000
INSTRUMENT_ID = "binance-usdm:AAPLUSDT:perpetual"


def _exchange_info() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "AAPLUSDT",
                "contractType": "TRADIFI_PERPETUAL",
                "underlyingType": "EQUITY",
                "marginAsset": "USDT",
                "status": "TRADING",
            }
        ]
    }


def test_recorded_binance_product_payload_builds_regular_session_snapshot() -> None:
    snapshots = parse_binance_product_snapshots(
        exchange_instrument_ids=(INSTRUMENT_ID,),
        exchange_info=_exchange_info(),
        trading_schedule={
            "data": [
                {
                    "symbol": "AAPLUSDT",
                    "tradingSessions": [
                        {
                            "session": "REGULAR",
                            "startTime": OBSERVED_MS - 3_600_000,
                            "endTime": OBSERVED_MS + 18_000_000,
                        }
                    ],
                }
            ]
        },
        premium_index=[
            {
                "symbol": "AAPLUSDT",
                "markPrice": "228.12",
                "indexPrice": "228.08",
                "lastFundingRate": "0.0001",
            }
        ],
        depth_by_symbol={
            "AAPLUSDT": {
                "bids": [["228.10", "12"]],
                "asks": [["228.14", "9"]],
            }
        },
        observed_at_ms=OBSERVED_MS,
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.product_status == "active"
    assert snapshot.session_state == "regular"
    assert snapshot.regular_session_open_ms == OBSERVED_MS - 3_600_000
    assert snapshot.regular_session_close_ms == OBSERVED_MS + 18_000_000
    assert snapshot.mark_price == Decimal("228.12")
    assert snapshot.index_price == Decimal("228.08")
    assert snapshot.best_bid == Decimal("228.10")
    assert snapshot.best_ask == Decimal("228.14")
    assert snapshot.best_bid_quantity == Decimal(12)
    assert snapshot.best_ask_quantity == Decimal(9)


def test_missing_schedule_fails_closed_without_discarding_product_status() -> None:
    snapshot = parse_binance_product_snapshots(
        exchange_instrument_ids=(INSTRUMENT_ID,),
        exchange_info=_exchange_info(),
        trading_schedule={"data": []},
        premium_index=[],
        depth_by_symbol={},
        observed_at_ms=OBSERVED_MS,
    )[0]

    assert snapshot.product_status == "active"
    assert snapshot.session_state == "unavailable"
    assert snapshot.regular_session_open_ms is None
    assert snapshot.regular_session_close_ms is None
    assert snapshot.mark_price is None
    assert snapshot.valid_until_ms == OBSERVED_MS + 900_000
