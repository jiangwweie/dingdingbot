from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "fetch_binance_usdm_public_facts.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_binance_usdm_public_facts",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _exchange_symbol() -> dict:
    return {
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.001"},
            {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ],
    }


def test_mark_price_fresh_requires_recent_exchange_timestamp():
    module = _load_module()
    observed_at = datetime(2026, 6, 30, 0, 10, 0, tzinfo=timezone.utc)
    stale_premium = {
        "markPrice": "100.0",
        "lastFundingRate": "0.0001",
        "time": int(
            datetime(2026, 6, 30, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
        ),
    }
    book = {"bidPrice": "99.99", "askPrice": "100.01"}

    row = module._symbol_row_from_payload(
        "BTCUSDT",
        _exchange_symbol(),
        stale_premium,
        book,
        observed_at,
    )

    assert row["mark_price_fresh"] is False
    assert row["public_facts_ready"] is False
    assert row["mark_price_age_seconds"] == 600
