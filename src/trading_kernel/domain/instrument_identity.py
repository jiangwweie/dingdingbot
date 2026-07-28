"""Strict canonical identity for Binance USD-M USDT perpetual instruments."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict


_CANONICAL_INSTRUMENT_ID = re.compile(
    r"^binance-usdm:([A-Z0-9]+)USDT:perpetual$"
)


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
