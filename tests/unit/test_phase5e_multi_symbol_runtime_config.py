from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.seed_phase5e_profile import PHASE5E_PROFILE
from src.application.runtime_config import MarketRuntimeConfig


def test_market_runtime_config_defaults_to_primary_symbol_for_legacy_profiles():
    config = MarketRuntimeConfig.model_validate(
        {
            "primary_symbol": "ETH/USDT:USDT",
            "primary_timeframe": "1h",
            "mtf_timeframe": "4h",
        }
    )

    assert config.symbols == ["ETH/USDT:USDT"]
    assert config.subscribed_pairs == [
        ("ETH/USDT:USDT", "1h"),
        ("ETH/USDT:USDT", "4h"),
    ]


def test_market_runtime_config_accepts_phase5e_two_symbol_scope():
    config = MarketRuntimeConfig.model_validate(PHASE5E_PROFILE["market"])

    assert config.primary_symbol == "ETH/USDT:USDT"
    assert config.symbols == ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    assert config.subscribed_pairs == [
        ("ETH/USDT:USDT", "1h"),
        ("ETH/USDT:USDT", "4h"),
        ("BTC/USDT:USDT", "1h"),
        ("BTC/USDT:USDT", "4h"),
    ]
    assert config.model_dump(mode="json", by_alias=True, exclude_none=True)["symbols"] == [
        "ETH/USDT:USDT",
        "BTC/USDT:USDT",
    ]


def test_market_runtime_config_rejects_scope_without_primary_symbol():
    with pytest.raises(ValidationError, match="primary_symbol must be included"):
        MarketRuntimeConfig.model_validate(
            {
                "primary_symbol": "ETH/USDT:USDT",
                "symbols": ["BTC/USDT:USDT"],
                "primary_timeframe": "1h",
                "mtf_timeframe": "4h",
            }
        )


def test_market_runtime_config_rejects_duplicate_symbols():
    with pytest.raises(ValidationError, match="symbols must be unique"):
        MarketRuntimeConfig.model_validate(
            {
                "primary_symbol": "ETH/USDT:USDT",
                "symbols": ["ETH/USDT:USDT", "ETH/USDT:USDT"],
                "primary_timeframe": "1h",
                "mtf_timeframe": "4h",
            }
        )
