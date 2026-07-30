"""Committed Owner-approved manifest for the initial StrategyUniverse batch."""

from __future__ import annotations

APPROVED_UNIVERSE_EVENT_ORDER = (
    "CPM-LONG",
    "MPG-LONG",
    "MI-LONG",
    "SOR-LONG",
    "SOR-SHORT",
    "BRF2-SHORT",
)

APPROVED_FIRST_BATCH_INSTRUMENT_IDS = tuple(
    sorted(
        f"binance-usdm:{symbol}USDT:perpetual"
        for symbol in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA")
    )
)
