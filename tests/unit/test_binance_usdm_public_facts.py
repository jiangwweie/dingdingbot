from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


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


def test_partial_public_facts_do_not_fail_global_watcher_tick():
    module = _load_module()

    assert (
        module._artifact_status(ready_count=5, symbol_count=6, errors=[])
        == "binance_usdm_public_facts_partial"
    )
    assert module._exit_code_for_status("binance_usdm_public_facts_partial") == 0


def test_endpoint_errors_still_fail_public_facts_fetch():
    module = _load_module()

    assert (
        module._artifact_status(
            ready_count=5,
            symbol_count=6,
            errors=["/fapi/v1/exchangeInfo:URLError:timeout"],
        )
        == "binance_usdm_public_facts_unavailable"
    )
    assert module._exit_code_for_status("binance_usdm_public_facts_unavailable") == 2


def test_comparative_candle_fetch_reads_each_unique_symbol_once():
    module = _load_module()

    class FakeSource:
        def __init__(self):
            self.calls = []

        def latest_closed_candles(self, *, symbol, timeframe, limit):
            self.calls.append((symbol, timeframe, limit))
            return [
                SimpleNamespace(
                    open_time_ms=index * 3_600_000,
                    close_time_ms=(index + 1) * 3_600_000,
                    close="100",
                )
                for index in range(limit)
            ]

    source = FakeSource()

    result = module._fetch_comparative_candles(
        source,
        ("SOLUSDT", "OPUSDT", "SOLUSDT", "ETHUSDT"),
    )

    assert list(result) == ["ETHUSDT", "OPUSDT", "SOLUSDT"]
    assert source.calls == [
        ("ETHUSDT", "1h", 13),
        ("OPUSDT", "1h", 13),
        ("SOLUSDT", "1h", 13),
    ]
