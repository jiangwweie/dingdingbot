from src.infrastructure.exchange_gateway import ExchangeGateway


def test_recent_order_updates_are_symbol_scoped_before_legacy_fallback():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    eth = {
        "id": "same-exchange-id",
        "clientOrderId": "same-client-id",
        "symbol": "ETH/USDT:USDT",
    }
    btc = {
        "id": "same-exchange-id",
        "clientOrderId": "same-client-id",
        "symbol": "BTC/USDT:USDT",
    }

    gateway._remember_recent_order_update(eth)
    gateway._remember_recent_order_update(btc)

    eth_candidates = gateway._recent_order_update_candidates(
        "same-exchange-id",
        "same-client-id",
        expected_symbol="ETH/USDT:USDT",
    )
    btc_candidates = gateway._recent_order_update_candidates(
        "same-exchange-id",
        "same-client-id",
        expected_symbol="BTC/USDT:USDT",
    )

    assert eth_candidates[0]["symbol"] == "ETH/USDT:USDT"
    assert btc_candidates[0]["symbol"] == "BTC/USDT:USDT"


def test_order_watch_running_state_has_symbol_scope():
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)

    gateway._order_ws_running = True
    gateway._order_ws_running_symbols["ETH/USDT:USDT"] = True
    gateway._order_ws_running_symbols["BTC/USDT:USDT"] = False

    assert gateway._order_ws_running is True
    assert gateway._order_ws_running_symbols["ETH/USDT:USDT"] is True
    assert gateway._order_ws_running_symbols["BTC/USDT:USDT"] is False
