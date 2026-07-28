from __future__ import annotations

import pytest

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
    to_ccxt_symbol,
)


def test_binance_usdm_codec_parses_canonical_perpetual_and_converts_to_ccxt() -> None:
    identity = parse_binance_usdm_instrument_id(
        "binance-usdm:BTCUSDT:perpetual"
    )

    assert identity.venue_id == "binance-usdm"
    assert identity.symbol == "BTCUSDT"
    assert identity.base_asset == "BTC"
    assert identity.quote_asset == "USDT"
    assert to_ccxt_symbol(identity) == "BTC/USDT:USDT"


@pytest.mark.parametrize(
    "exchange_instrument_id",
    (
        " binance-usdm:BTCUSDT:perpetual",
        "binance-usdm:btcusdt:perpetual",
        "binance-usdm:BTCUSD:perpetual",
        "binance-usdm:BTCUSDT:spot",
        "unknown:BTCUSDT:perpetual",
        "binance-usdm:USDT:perpetual",
    ),
)
def test_binance_usdm_codec_rejects_noncanonical_or_unsupported_ids(
    exchange_instrument_id: str,
) -> None:
    with pytest.raises(ValueError):
        parse_binance_usdm_instrument_id(exchange_instrument_id)
