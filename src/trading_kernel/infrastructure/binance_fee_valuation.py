"""Bounded read-only BNB commission valuation from one Binance USD-M snapshot."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from decimal import Decimal

from src.trading_kernel.domain.fee_valuation import FeeValuationEvidence


async def read_bnbusdt_fee_valuation_evidence(
    *,
    exchange: object,
    review_observed_at_ms: int,
) -> FeeValuationEvidence:
    """Read one BNBUSDT index snapshot for a final Review only."""

    if review_observed_at_ms <= 0:
        raise ValueError("review observation time must be positive")
    fetch = getattr(exchange, "fapiPublicGetPremiumIndex", None)
    if not callable(fetch):
        raise TypeError("Binance venue lacks BNBUSDT index snapshot lookup")
    response = fetch({"symbol": "BNBUSDT"})
    if inspect.isawaitable(response):
        response = await response
    if not isinstance(response, Mapping):
        raise TypeError("Binance BNBUSDT index snapshot is not a mapping")
    if str(response.get("symbol") or "").strip().upper() != "BNBUSDT":
        raise RuntimeError("Binance BNBUSDT index snapshot symbol is invalid")
    index_price = Decimal(str(response.get("indexPrice") or "0"))
    if not index_price.is_finite() or index_price <= 0:
        raise RuntimeError("Binance BNBUSDT index snapshot price is non-positive")
    observed_at_ms = int(response.get("time") or review_observed_at_ms)
    if observed_at_ms <= 0:
        raise RuntimeError("Binance BNBUSDT index snapshot time is invalid")
    return FeeValuationEvidence(
        method="binance_usdm_bnbusdt_review_index_snapshot",
        rate_usdt_per_asset=index_price,
        price_pair="BNBUSDT",
        observed_at_ms=observed_at_ms,
        valued_at_ms=review_observed_at_ms,
    )
