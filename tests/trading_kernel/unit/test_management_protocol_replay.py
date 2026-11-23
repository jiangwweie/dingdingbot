"""Recorded BNB endpoint evidence through the pinned CCXT JSON boundary."""

import json
from pathlib import Path

import ccxt
import pytest

from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_rest_order,
)

CORPUS = Path(__file__).parents[1] / "fixtures" / "management_protocol_v2"


@pytest.mark.parametrize(
    "filename,conditional",
    [
        ("bnb_entry.json", False),
        ("bnb_tp1_expired.json", False),
        ("bnb_app_exit.json", False),
        ("bnb_stop_cancelled.json", True),
    ],
)
def test_recorded_bnb_rest_evidence_survives_actual_ccxt_decode(filename, conditional):
    raw = json.loads((CORPUS / filename).read_text())
    x = ccxt.binanceusdm()
    decoded = x.on_json_response(json.dumps(raw))
    evidence = parse_rest_order(
        decoded,
        account_id="replay-account",
        conditional=conditional,
        received_at_ms=1794279000000,
        coverage_complete=True,
    )
    assert evidence.terms.exchange_instrument_id == "binance-usdm:BNBUSDT:perpetual"
    assert evidence.terms.self_trade_prevention_mode == "EXPIRE_MAKER"
    assert evidence.executed_quantity >= 0


def test_fixed_algo_new_uses_pinned_ccxt_protocol_without_trailing_activation_field():
    from src.trading_kernel.infrastructure.binance_management_observation import (
        parse_order_update,
    )

    raw = {
        "e": "ALGO_UPDATE",
        "E": 2001,
        "T": 2000,
        "o": {
            "caid": "brc-exact",
            "aid": 201,
            "at": "CONDITIONAL",
            "o": "STOP_MARKET",
            "s": "BNBUSDT",
            "S": "BUY",
            "ps": "SHORT",
            "f": "GTC",
            "q": "2.82",
            "X": "NEW",
            "ai": "",
            "ap": "0",
            "aq": "0",
            "act": "",
            "tp": "692.26",
            "p": "0",
            "V": "EXPIRE_MAKER",
            "wt": "CONTRACT_PRICE",
            "pm": "NONE",
            "cp": False,
            "pP": False,
            "R": True,
            "tt": 0,
            "gtd": 0,
        },
    }
    x = ccxt.binanceusdm()
    evidence = parse_order_update(
        x.on_json_response(json.dumps(raw)),
        account_id="replay-account",
        received_at_ms=2002,
        coverage_complete=True,
    )
    assert evidence.action.value == "new" and evidence.terms.exchange_order_id == "201"


@pytest.mark.parametrize("status", ["NEW", "CANCELED"])
def test_binance_close_all_algo_reduce_only_echo_is_canonical(status):
    from src.trading_kernel.infrastructure.binance_management_observation import (
        parse_order_update,
    )

    raw = {
        "e": "ALGO_UPDATE", "E": 2001, "T": 2000,
        "o": {
            "R": True, "S": "BUY", "V": "EXPIRE_MAKER", "X": status,
            "f": "GTE_GTC", "o": "STOP_MARKET", "p": "0", "q": "0",
            "s": "XRPUSDT", "cp": True, "ia": False, "pP": False,
            "pm": "NONE", "ps": "SHORT", "tp": "0.9229",
            "wt": "CONTRACT_PRICE", "aid": 201, "gtd": 0, "caid": "app-exact",
        },
    }
    evidence = parse_order_update(
        raw, account_id="replay-account", received_at_ms=2019, coverage_complete=True,
    )
    assert evidence.terms.close_position and evidence.terms.reduces_position
    assert evidence.terms.quantity is None and not evidence.terms.reduce_only
    # The same echo with a fixed quantity remains a protocol violation.
    raw["o"]["q"] = "1"
    with pytest.raises(ValueError, match="fixed quantity"):
        parse_order_update(raw, account_id="replay-account", received_at_ms=2019, coverage_complete=True)
