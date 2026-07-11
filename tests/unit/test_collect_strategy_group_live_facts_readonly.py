from __future__ import annotations

import json
from pathlib import Path

from scripts.collect_strategy_group_live_facts_readonly import collect_live_facts


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_collect_strategy_group_live_facts_readonly_uses_get_and_masks_values(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "EXCHANGE_API_KEY=test-key\nEXCHANGE_API_SECRET=test-secret\n",
        encoding="utf-8",
    )
    requests = []

    def fake_urlopen(request, *, timeout):
        requests.append((request.full_url, request.get_method(), dict(request.header_items())))
        if request.full_url.endswith("/fapi/v1/exchangeInfo"):
            return _Response(
                {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "ETHUSDT",
                            "status": "TRADING",
                            "filters": [],
                        },
                    ]
                }
            )
        if "/fapi/v2/account" in request.full_url:
            return _Response(
                {
                    "canTrade": True,
                    "feeTier": 0,
                    "totalWalletBalance": "123.45",
                    "availableBalance": "100.00",
                    "assets": [{"asset": "USDT"}],
                }
            )
        if "/fapi/v2/positionRisk" in request.full_url:
            return _Response(
                [
                    {"symbol": "BTCUSDT", "positionAmt": "0"},
                    {"symbol": "ETHUSDT", "positionAmt": "0.2"},
                ]
            )
        if "/fapi/v1/openOrders" in request.full_url:
            return _Response([{"symbol": "BTCUSDT", "orderId": 1}])
        if "/fapi/v1/positionSide/dual" in request.full_url:
            return _Response({"dualSidePosition": False})
        raise AssertionError(request.full_url)

    packet = collect_live_facts(
        symbols=["BTCUSDT", "ETHUSDT"],
        max_notional_requirement_usdt="8",
        has_candidate_specific_protection_template=True,
        strategy_group_count=1,
        account_id="owner-subaccount-runtime-v0",
        exchange_id="binance_usdm",
        env_file=env_file,
        base_url="https://unit.test",
        urlopen=fake_urlopen,
    )

    assert packet["status"] == "ready"
    assert {method for _url, method, _headers in requests} == {"GET"}
    assert all(
        "x-mbx-apikey" in {key.lower(): value for key, value in headers.items()}
        or "/exchangeInfo" in url
        for url, _method, headers in requests
    )
    assert packet["exchange_rules"]["symbols"]["BTCUSDT"]["status"] == "TRADING"
    assert packet["account"]["status"] == "fresh"
    assert packet["account"]["exchange_account_trade_permission"] is True
    assert "can_trade" not in packet["account"]
    assert packet["account"]["available_balance_present"] is True
    assert "100.00" not in json.dumps(packet)
    assert packet["active_position"]["status"] == "active_position_present"
    assert packet["active_position"]["active_symbols"] == ["ETHUSDT"]
    assert packet["open_orders"]["status"] == "open_orders_present"
    assert packet["open_orders"]["open_order_symbols"] == ["BTCUSDT"]
    assert packet["budget"]["status"] == "available_for_candidate_specific_reservation"
    assert packet["budget"]["max_notional_requirement_usdt"] == "8"
    assert packet["protection"]["status"] == "ready_for_candidate_specific_plan"
    assert packet["next_attempt_gate"]["status"] == "blocked"
    assert packet["next_attempt_gate"]["reason"] == "active_position_present"
    assert packet["account_mode"]["account_id"] == "owner-subaccount-runtime-v0"
    assert packet["account_mode"]["exchange_id"] == "binance_usdm"
    assert packet["account_mode"]["dual_side_position"] is False
    assert packet["account_mode"]["account_mode"] == "one_way"
    assert packet["account_mode"]["position_mode_safe"] is True
    assert packet["account_mode"]["observed_at"]
    assert packet["account_mode"]["source"].endswith(
        "/fapi/v1/positionSide/dual"
    )
    assert packet["safety_invariants"]["post_delete_put_used"] is False
    assert packet["safety_invariants"]["secrets_printed"] is False


def test_collect_strategy_group_live_facts_derives_candidate_prerequisites_when_flat(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "EXCHANGE_API_KEY=test-key\nEXCHANGE_API_SECRET=test-secret\n",
        encoding="utf-8",
    )

    def fake_urlopen(request, *, timeout):
        if request.full_url.endswith("/fapi/v1/exchangeInfo"):
            return _Response(
                {
                    "symbols": [
                        {"symbol": "BTCUSDT", "status": "TRADING", "filters": []},
                        {"symbol": "ETHUSDT", "status": "TRADING", "filters": []},
                    ]
                }
            )
        if "/fapi/v2/account" in request.full_url:
            return _Response(
                {
                    "canTrade": True,
                    "feeTier": 0,
                    "totalWalletBalance": "123.45",
                    "availableBalance": "9.00",
                    "assets": [{"asset": "USDT"}],
                }
            )
        if "/fapi/v2/positionRisk" in request.full_url:
            return _Response(
                [
                    {"symbol": "BTCUSDT", "positionAmt": "0"},
                    {"symbol": "ETHUSDT", "positionAmt": "0"},
                ]
            )
        if "/fapi/v1/openOrders" in request.full_url:
            return _Response([])
        if "/fapi/v1/positionSide/dual" in request.full_url:
            return _Response({"dualSidePosition": False})
        raise AssertionError(request.full_url)

    packet = collect_live_facts(
        symbols=["BTCUSDT", "ETHUSDT"],
        max_notional_requirement_usdt="8",
        has_candidate_specific_protection_template=True,
        strategy_group_count=1,
        account_id="owner-subaccount-runtime-v0",
        exchange_id="binance_usdm",
        env_file=env_file,
        base_url="https://unit.test",
        urlopen=fake_urlopen,
    )

    assert packet["active_position"]["status"] == "no_active_position"
    assert packet["open_orders"]["status"] == "no_open_orders"
    assert packet["budget"]["status"] == "available_for_candidate_specific_reservation"
    assert packet["protection"]["status"] == "ready_for_candidate_specific_plan"
    assert packet["next_attempt_gate"]["status"] == "ready_for_strategy_signal"
    assert "9.00" not in json.dumps(packet)


def test_collect_strategy_group_live_facts_rejects_non_boolean_position_mode(
    tmp_path,
):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "EXCHANGE_API_KEY=test-key\nEXCHANGE_API_SECRET=test-secret\n",
        encoding="utf-8",
    )

    def fake_urlopen(request, *, timeout):
        if request.full_url.endswith("/fapi/v1/exchangeInfo"):
            return _Response(
                {
                    "symbols": [
                        {"symbol": "BTCUSDT", "status": "TRADING", "filters": []}
                    ]
                }
            )
        if "/fapi/v2/account" in request.full_url:
            return _Response(
                {
                    "canTrade": True,
                    "availableBalance": "9.00",
                    "totalWalletBalance": "9.00",
                    "assets": [],
                }
            )
        if "/fapi/v2/positionRisk" in request.full_url:
            return _Response([{"symbol": "BTCUSDT", "positionAmt": "0"}])
        if "/fapi/v1/openOrders" in request.full_url:
            return _Response([])
        if "/fapi/v1/positionSide/dual" in request.full_url:
            return _Response({"dualSidePosition": "false"})
        raise AssertionError(request.full_url)

    packet = collect_live_facts(
        symbols=["BTCUSDT"],
        max_notional_requirement_usdt="8",
        has_candidate_specific_protection_template=True,
        strategy_group_count=1,
        account_id="owner-subaccount-runtime-v0",
        exchange_id="binance_usdm",
        env_file=env_file,
        base_url="https://unit.test",
        urlopen=fake_urlopen,
    )

    assert packet["status"] == "partial"
    assert packet["account_mode"]["status"] == "malformed"
    assert packet["account_mode"]["dual_side_position"] is None
    assert packet["account_mode"]["account_mode"] is None
    assert packet["account_mode"]["position_mode_safe"] is False
