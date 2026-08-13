"""Committed Owner-approved manifests for deployable StrategyUniverse batches."""

from __future__ import annotations

APPROVED_UNIVERSE_EVENT_SPECS = (
    ("CPM-LONG", "event_spec:CPM-RO-001:CPM-LONG:v3"),
    ("MPG-LONG", "event_spec:MPG-001:MPG-LONG:v3"),
    ("MI-LONG", "event_spec:MI-001:MI-LONG:v3"),
    ("SOR-LONG", "event_spec:SOR-001:SOR-LONG:v4"),
    ("SOR-SHORT", "event_spec:SOR-001:SOR-SHORT:v4"),
    ("BRF2-SHORT", "event_spec:BRF2-001:BRF2-SHORT:v3"),
)

APPROVED_UNIVERSE_EVENT_ORDER = tuple(
    event_id for event_id, _event_spec_id in APPROVED_UNIVERSE_EVENT_SPECS
)

APPROVED_FIRST_BATCH_INSTRUMENT_IDS = tuple(
    sorted(
        f"binance-usdm:{symbol}USDT:perpetual"
        for symbol in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA")
    )
)

APPROVED_TRADFI_UNIVERSE_EVENT_SPECS = (
    (
        "SOR-US-LONG-15M",
        "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
    ),
    (
        "SOR-US-SHORT-15M",
        "event_spec:SOR-US-EQ-PERP-001:SOR-US-SHORT-15M:v1",
    ),
)

APPROVED_TRADFI_UNIVERSE_EVENT_ORDER = tuple(
    event_id for event_id, _event_spec_id in APPROVED_TRADFI_UNIVERSE_EVENT_SPECS
)

APPROVED_TRADFI_FIRST_BATCH_INSTRUMENT_IDS = tuple(
    sorted(
        f"binance-usdm:{symbol}USDT:perpetual"
        for symbol in (
            "AAPL",
            "GOOGL",
            "MSFT",
            "NVDA",
            "META",
            "AMZN",
            "TSLA",
            "SNDK",
        )
    )
)

APPROVED_UNIVERSE_BATCHES = {
    "tiny-live-v1": (
        APPROVED_UNIVERSE_EVENT_SPECS,
        APPROVED_FIRST_BATCH_INSTRUMENT_IDS,
    ),
    "tradfi-equity-usdm-v1": (
        APPROVED_TRADFI_UNIVERSE_EVENT_SPECS,
        APPROVED_TRADFI_FIRST_BATCH_INSTRUMENT_IDS,
    ),
}
