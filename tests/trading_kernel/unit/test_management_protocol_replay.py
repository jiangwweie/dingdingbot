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
