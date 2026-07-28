"""Strict canonical identity for Binance USD-M USDT perpetual instruments."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict


_CANONICAL_INSTRUMENT_ID = re.compile(
    r"^binance-usdm:([A-Z0-9]+)USDT:perpetual$"
)
_CCXT_BINANCE_USDM_SYMBOL = re.compile(r"^([A-Z0-9]+)/USDT:USDT$")


class BinanceUsdmInstrumentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    symbol: str
    base_asset: str
    quote_asset: str
    product_type: str


def parse_binance_usdm_instrument_id(
    exchange_instrument_id: str,
) -> BinanceUsdmInstrumentIdentity:
    """Parse one already-canonical Binance USD-M USDT perpetual identity."""

    match = _CANONICAL_INSTRUMENT_ID.fullmatch(exchange_instrument_id)
    if match is None:
        raise ValueError("instrument id must be canonical Binance USD-M USDT perpetual")
    base_asset = match.group(1)
    if not base_asset:
        raise ValueError("instrument id requires a non-blank base asset")
    return BinanceUsdmInstrumentIdentity(
        venue_id="binance-usdm",
        symbol=f"{base_asset}USDT",
        base_asset=base_asset,
        quote_asset="USDT",
        product_type="perpetual",
    )


def to_ccxt_symbol(identity: BinanceUsdmInstrumentIdentity) -> str:
    """Convert a validated canonical identity without Registry or database lookup."""

    return f"{identity.base_asset}/{identity.quote_asset}:{identity.quote_asset}"


def parse_binance_usdm_ccxt_symbol(
    symbol: str,
) -> BinanceUsdmInstrumentIdentity:
    """Parse one strict CCXT Binance USD-M USDT perpetual symbol."""

    match = _CCXT_BINANCE_USDM_SYMBOL.fullmatch(symbol)
    if match is None:
        raise ValueError("CCXT symbol must be Binance USD-M BASE/USDT:USDT")
    return parse_binance_usdm_instrument_id(
        f"binance-usdm:{match.group(1)}USDT:perpetual"
    )


def to_exchange_instrument_id(identity: BinanceUsdmInstrumentIdentity) -> str:
    """Render one validated Binance USD-M identity in canonical kernel form."""

    return f"{identity.venue_id}:{identity.symbol}:{identity.product_type}"
