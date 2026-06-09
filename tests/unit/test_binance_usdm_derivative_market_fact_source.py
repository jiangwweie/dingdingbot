from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from src.infrastructure.binance_usdm_derivative_market_fact_source import (
    BinanceUsdmDerivativeMarketFactSource,
)


NOW_MS = 1_781_000_000_000


@pytest.mark.asyncio
async def test_binance_derivative_market_fact_source_reads_public_facts():
    requested: list[str] = []

    def transport(url: str, timeout: float):
        requested.append(url)
        assert timeout == 10.0
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        assert query["symbol"] == ["BNBUSDT"]
        if parsed.path == "/fapi/v1/premiumIndex":
            return {
                "symbol": "BNBUSDT",
                "markPrice": "650.50",
                "lastFundingRate": "0.000123",
                "nextFundingTime": str(NOW_MS + 28_800_000),
                "time": str(NOW_MS),
            }
        if parsed.path == "/fapi/v1/openInterest":
            return {
                "symbol": "BNBUSDT",
                "openInterest": "12345.67",
                "time": str(NOW_MS),
            }
        if parsed.path == "/futures/data/globalLongShortAccountRatio":
            assert query["period"] == ["5m"]
            assert query["limit"] == ["1"]
            return [
                {
                    "symbol": "BNBUSDT",
                    "longShortRatio": "1.8",
                    "longAccount": "0.6429",
                    "shortAccount": "0.3571",
                    "timestamp": str(NOW_MS),
                }
            ]
        raise AssertionError(f"unexpected url {url}")

    source = BinanceUsdmDerivativeMarketFactSource(
        now_ms=lambda: NOW_MS,
        transport=transport,
    )

    facts = await source.read_strategy_market_facts(
        symbol="BNB/USDT:USDT",
        generated_at_ms=NOW_MS,
    )

    assert len(requested) == 3
    assert facts.source_id == "binance_usdm_derivative_market_facts_read_only"
    assert facts.freshness == "fresh"
    assert facts.funding_rate == Decimal("0.000123")
    assert facts.next_funding_time_ms == NOW_MS + 28_800_000
    assert facts.open_interest == Decimal("12345.67")
    assert facts.open_interest_notional == Decimal("8030858.3350")
    assert facts.crowding_proxy == {
        "status": "defined",
        "proxy_type": "global_long_short_account_ratio",
        "definition": "Binance USD-M public global long/short account ratio; account-count crowding proxy, not execution authority.",
        "period": "5m",
        "long_short_ratio": "1.8",
        "long_account": "0.6429",
        "short_account": "0.3571",
        "timestamp_ms": NOW_MS,
        "source_id": "binance_usdm_derivative_market_facts_read_only",
    }
    assert facts.missing_fields == []
    assert facts.stale_fields == []
    assert facts.read_only_guarantee is True
    assert facts.external_call_type == "binance_usdm_public_http_read_only"
    assert facts.metadata["api_key_used"] is False
    assert facts.metadata["exchange_gateway_used"] is False
    assert facts.not_order is True
    assert facts.not_execution_intent is True
    assert facts.not_execution_authority is True


@pytest.mark.asyncio
async def test_binance_derivative_market_fact_source_marks_missing_and_stale_facts():
    old_ms = NOW_MS - 20 * 60 * 1000

    def transport(url: str, _timeout: float):
        parsed = urlparse(url)
        if parsed.path == "/fapi/v1/premiumIndex":
            return {
                "symbol": "ETHUSDT",
                "lastFundingRate": "0.0002",
                "nextFundingTime": str(NOW_MS + 28_800_000),
                "time": str(old_ms),
            }
        if parsed.path == "/fapi/v1/openInterest":
            return {"symbol": "ETHUSDT", "time": str(NOW_MS)}
        if parsed.path == "/futures/data/globalLongShortAccountRatio":
            return [
                {
                    "symbol": "ETHUSDT",
                    "longShortRatio": "1.4",
                    "longAccount": "0.5833",
                    "shortAccount": "0.4167",
                    "timestamp": str(old_ms),
                }
            ]
        raise AssertionError(f"unexpected url {url}")

    source = BinanceUsdmDerivativeMarketFactSource(
        now_ms=lambda: NOW_MS,
        transport=transport,
    )

    facts = await source.read_strategy_market_facts(
        symbol="ETH/USDT:USDT",
        generated_at_ms=NOW_MS,
    )

    assert facts.freshness == "stale"
    assert facts.funding_rate == Decimal("0.0002")
    assert facts.open_interest is None
    assert facts.crowding_proxy is not None
    assert facts.missing_fields == ["open_interest"]
    assert set(facts.stale_fields) == {"funding_rate", "crowding_proxy"}


@pytest.mark.asyncio
async def test_binance_derivative_market_fact_source_keeps_partial_failures_non_executing():
    def transport(url: str, _timeout: float):
        parsed = urlparse(url)
        if parsed.path == "/fapi/v1/premiumIndex":
            raise RuntimeError("premium endpoint unavailable")
        if parsed.path == "/fapi/v1/openInterest":
            return {"symbol": "SOLUSDT", "openInterest": "456.78", "time": str(NOW_MS)}
        if parsed.path == "/futures/data/globalLongShortAccountRatio":
            return []
        raise AssertionError(f"unexpected url {url}")

    source = BinanceUsdmDerivativeMarketFactSource(
        now_ms=lambda: NOW_MS,
        transport=transport,
    )

    facts = await source.read_strategy_market_facts(
        symbol="SOL/USDT:USDT",
        generated_at_ms=NOW_MS,
    )

    assert facts.freshness == "partial"
    assert facts.funding_rate is None
    assert facts.open_interest == Decimal("456.78")
    assert facts.crowding_proxy is None
    assert facts.missing_fields == ["funding_rate", "crowding_proxy"]
    assert facts.warnings == ["premium_index_read_failed:RuntimeError"]
    assert facts.metadata["endpoint_status"]["premium_index"]["status"] == "read_failed"
    assert facts.metadata["endpoint_status"]["open_interest"]["status"] == "available"
    assert facts.read_only_guarantee is True
    assert facts.metadata["api_key_used"] is False
    assert facts.metadata["exchange_gateway_used"] is False
    assert facts.not_order is True
    assert facts.not_execution_intent is True
    assert facts.not_execution_authority is True
