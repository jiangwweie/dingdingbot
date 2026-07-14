import pytest
import ccxt
from pathlib import Path
from decimal import Decimal
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import OrderType
from src.domain.exceptions import InvalidOrderError

SYMBOL = "ETH/USDT:USDT"
REPO_ROOT = Path(__file__).resolve().parents[2]

class MockRestExchange:
    def __init__(self):
        self.create_order_calls = []
        self.fetch_order_calls = []
        self.fetch_open_orders_calls = []
        
        self.fetch_order_exception = None
        self.fetch_open_orders_exception = None
        
        self.mocked_fetch_order_response = None
        self.mocked_fetch_open_orders_response = []
        self.set_leverage_calls = []
        self.configured_leverage = 2

    async def fetch_positions(self):
        return [
            {
                "symbol": SYMBOL,
                "side": "long",
                "contracts": "0",
                "leverage": self.configured_leverage,
                "info": {
                    "positionSide": "BOTH",
                    "leverage": self.configured_leverage,
                },
            }
        ]

    async def set_leverage(self, leverage, symbol, params=None):
        self.set_leverage_calls.append(
            {"leverage": leverage, "symbol": symbol, "params": params or {}}
        )
        self.configured_leverage = leverage
        return {"leverage": leverage, "symbol": symbol}

    async def create_order(self, symbol, type, side, amount, price=None, params=None):
        self.create_order_calls.append({
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": params or {}
        })
        return {
            "id": "mock-exchange-id",
            "status": "open",
            "filled": "0",
            "average": "0"
        }

    async def fetch_order(self, id, symbol):
        self.fetch_order_calls.append({"id": id, "symbol": symbol})
        if self.fetch_order_exception:
            raise self.fetch_order_exception
        if self.mocked_fetch_order_response is not None:
            return self.mocked_fetch_order_response
        return {"id": id, "symbol": symbol, "status": "open", "info": {}}

    async def fetch_open_orders(self, symbol, params=None):
        self.fetch_open_orders_calls.append({"symbol": symbol, "params": params or {}})
        if self.fetch_open_orders_exception:
            raise self.fetch_open_orders_exception
        return self.mocked_fetch_open_orders_response

@pytest.fixture
def mock_exchange():
    return MockRestExchange()

@pytest.fixture
def gateway(mock_exchange):
    gw = ExchangeGateway("binance", "key", "secret", testnet=True)
    gw.rest_exchange = mock_exchange
    gw._order_confirmation_retry_delays = ()
    return gw

@pytest.mark.asyncio
async def test_place_order_stop_market_parameters(gateway, mock_exchange):
    """
    CCXT type = STOP_MARKET；
    params 包含 reduceOnly=true；
    params 包含 stopPrice；
    params 包含 triggerPrice；
    不传 fake limit price；
    side 正确；
    quantity 正确；
    """
    result = await gateway.place_order(
        symbol=SYMBOL,
        order_type="stop_market",
        side="sell",
        amount=Decimal("0.5"),
        price=None,
        trigger_price=Decimal("2000.5"),
        reduce_only=True,
        client_order_id="sl-123"
    )
    
    assert len(mock_exchange.create_order_calls) == 1
    call = mock_exchange.create_order_calls[0]
    
    assert call["type"] == "STOP_MARKET"
    assert call["side"] == "sell"
    assert call["amount"] == "0.5"
    assert call["price"] is None
    
    params = call["params"]
    assert params.get("reduceOnly") is True
    assert params.get("stopPrice") == "2000.5"
    assert params.get("triggerPrice") == "2000.5"
    assert params.get("clientOrderId") == "sl-123"
    assert result.reduce_only is True
    assert result.exchange_reduce_only_param_sent is True
    assert result.exchange_reduce_only_omit_reason is None


@pytest.mark.asyncio
async def test_place_order_binance_hedge_mode_omits_reduce_only_param(gateway, mock_exchange):
    result = await gateway.place_order(
        symbol="BNB/USDT:USDT",
        order_type="stop_market",
        side="sell",
        amount=Decimal("0.01"),
        trigger_price=Decimal("637.10"),
        reduce_only=True,
        position_side="LONG",
        client_order_id="sl-bnb-hedge",
    )

    call = mock_exchange.create_order_calls[-1]
    params = call["params"]
    assert call["type"] == "STOP_MARKET"
    assert call["side"] == "sell"
    assert params.get("positionSide") == "LONG"
    assert params.get("stopPrice") == "637.10"
    assert params.get("triggerPrice") == "637.10"
    assert params.get("clientOrderId") == "sl-bnb-hedge"
    assert "reduceOnly" not in params
    assert result.reduce_only is True
    assert result.exchange_reduce_only_param_sent is False
    assert result.exchange_reduce_only_omit_reason == "binance_hedge_mode_position_side"


@pytest.mark.asyncio
async def test_place_order_binance_hedge_mode_tp_limit_omits_reduce_only_param(
    gateway,
    mock_exchange,
):
    result = await gateway.place_order(
        symbol="BNB/USDT:USDT",
        order_type="limit",
        side="sell",
        amount=Decimal("0.01"),
        price=Decimal("649.90"),
        reduce_only=True,
        position_side="LONG",
        client_order_id="tp-bnb-hedge",
    )

    call = mock_exchange.create_order_calls[-1]
    params = call["params"]
    assert call["type"] == "limit"
    assert call["side"] == "sell"
    assert call["amount"] == "0.01"
    assert call["price"] == "649.90"
    assert params.get("positionSide") == "LONG"
    assert params.get("clientOrderId") == "tp-bnb-hedge"
    assert "reduceOnly" not in params
    assert "stopPrice" not in params
    assert "triggerPrice" not in params
    assert result.reduce_only is True
    assert result.exchange_reduce_only_param_sent is False
    assert result.exchange_reduce_only_omit_reason == "binance_hedge_mode_position_side"


@pytest.mark.asyncio
async def test_place_order_does_not_affect_limit_or_market(gateway, mock_exchange):
    await gateway.place_order(
        symbol=SYMBOL,
        order_type="limit",
        side="buy",
        amount=Decimal("1.0"),
        price=Decimal("1900.0"),
        reduce_only=False
    )
    call = mock_exchange.create_order_calls[-1]
    assert call["type"] == "limit"
    assert call["price"] == "1900.0"
    assert "stopPrice" not in call["params"]
    assert "reduceOnly" not in call["params"]

    await gateway.place_order(
        symbol=SYMBOL,
        order_type="market",
        side="sell",
        amount=Decimal("1.0"),
        reduce_only=True
    )
    call2 = mock_exchange.create_order_calls[-1]
    assert call2["type"] == "market"
    assert call2["price"] is None
    assert call2["params"].get("reduceOnly") is True


@pytest.mark.asyncio
async def test_place_order_omits_reduce_only_when_false(gateway, mock_exchange):
    result = await gateway.place_order(
        symbol=SYMBOL,
        order_type="market",
        side="buy",
        amount=Decimal("0.01"),
        reduce_only=False,
        position_side="LONG",
        client_order_id="entry-123",
    )

    call = mock_exchange.create_order_calls[-1]
    assert call["type"] == "market"
    assert call["side"] == "buy"
    assert call["params"].get("positionSide") == "LONG"
    assert call["params"].get("clientOrderId") == "entry-123"
    assert "reduceOnly" not in call["params"]
    assert result.exchange_reduce_only_param_sent is False
    assert result.exchange_reduce_only_omit_reason is None


@pytest.mark.asyncio
async def test_entry_place_order_ensures_desired_leverage_before_order_write(
    gateway,
    mock_exchange,
):
    await gateway.place_order(
        symbol=SYMBOL,
        order_type="market",
        side="buy",
        amount=Decimal("0.01"),
        reduce_only=False,
        desired_leverage=7,
        client_order_id="entry-dynamic-leverage",
    )

    assert mock_exchange.set_leverage_calls == [
        {"leverage": 7, "symbol": SYMBOL, "params": {}}
    ]
    assert len(mock_exchange.create_order_calls) == 1


@pytest.mark.asyncio
async def test_protection_order_rejects_desired_leverage_before_exchange_write(
    gateway,
    mock_exchange,
):
    with pytest.raises(InvalidOrderError):
        await gateway.place_order(
            symbol=SYMBOL,
            order_type="stop_market",
            side="sell",
            amount=Decimal("0.01"),
            trigger_price=Decimal("1900"),
            reduce_only=True,
            desired_leverage=7,
            client_order_id="sl-invalid-leverage-mutation",
        )

    assert mock_exchange.set_leverage_calls == []
    assert mock_exchange.create_order_calls == []


@pytest.mark.asyncio
async def test_place_order_rejects_hedge_position_side_for_non_binance_before_write(
    gateway,
    mock_exchange,
):
    gateway.exchange_name = "okx"

    with pytest.raises(InvalidOrderError) as exc_info:
        await gateway.place_order(
            symbol=SYMBOL,
            order_type="market",
            side="buy",
            amount=Decimal("0.01"),
            reduce_only=False,
            position_side="LONG",
            client_order_id="entry-non-binance",
        )

    assert "only supported by the Binance hedge-mode ccxt adapter" in str(exc_info.value)
    assert mock_exchange.create_order_calls == []


@pytest.mark.asyncio
async def test_place_order_rejects_invalid_position_side_before_write(gateway, mock_exchange):
    with pytest.raises(InvalidOrderError) as exc_info:
        await gateway.place_order(
            symbol="BNB/USDT:USDT",
            order_type="market",
            side="buy",
            amount=Decimal("0.01"),
            reduce_only=False,
            position_side="BOTH",
            client_order_id="entry-invalid-position-side",
        )

    assert "Unsupported hedge position side" in str(exc_info.value)
    assert mock_exchange.create_order_calls == []


def test_business_code_does_not_bypass_exchange_gateway_for_exchange_order_writes():
    roots = [
        REPO_ROOT / "src" / "application",
        REPO_ROOT / "src" / "domain",
        REPO_ROOT / "src" / "interfaces",
    ]
    forbidden_markers = (
        "rest_exchange.create_order",
        "privatePost",
        "private_post",
        "fapiPrivate",
        "/fapi/v1/order",
    )
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text()
            if any(marker in text for marker in forbidden_markers):
                offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


@pytest.mark.asyncio
async def test_confirm_order_exists_metadata_validation(gateway, mock_exchange):
    # 1. id matching but symbol mismatch => False
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": "BTC/USDT:USDT",
        "status": "open",
        "info": {}
    }
    res1 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000"),
        expected_type="STOP_MARKET"
    )
    assert res1 is False

    # 2. id matching but side mismatch => False
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "buy",
        "status": "open"
    }
    res2 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000"),
        expected_type="STOP_MARKET"
    )
    assert res2 is False

    # 3. id matching but reduceOnly mismatch => False
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "sell",
        "status": "open",
        "info": {"reduceOnly": False}
    }
    res3 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000"),
        expected_type="STOP_MARKET"
    )
    assert res3 is False

    # 4. id matching but type not STOP_MARKET => False
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "sell",
        "type": "limit",
        "status": "open",
        "info": {"reduceOnly": True}
    }
    res4 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000"),
        expected_type="STOP_MARKET"
    )
    assert res4 is False

    # 5. id matching but stopPrice significantly different => False
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "sell",
        "type": "stop_market",
        "status": "open",
        "info": {"reduceOnly": True, "stopPrice": "2050.0"}
    }
    res5 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000.0"),
        expected_type="STOP_MARKET"
    )
    assert res5 is False

    # 6. Exact match => True
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "sell",
        "type": "stop_market",
        "status": "open",
        "info": {"reduceOnly": True, "stopPrice": "2000.0000000"}
    }
    res6 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000.0"),
        expected_type="STOP_MARKET"
    )
    assert res6 is True

    # 7. Tick-size truncation match => True (exchange truncates to 0.01)
    mock_exchange.mocked_fetch_order_response = {
        "id": "exchange-id",
        "symbol": SYMBOL,
        "side": "sell",
        "type": "stop_market",
        "status": "open",
        "info": {"reduceOnly": True, "stopPrice": "2116.78"}
    }
    res7 = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2116.778400000000000000000"),
        expected_type="STOP_MARKET"
    )
    assert res7 is True

@pytest.mark.asyncio
async def test_confirm_order_exists_network_error_fail_closed(gateway, mock_exchange):
    # If network error occurs during fetch_order and fetch_open_orders, returns False
    mock_exchange.fetch_order_exception = ccxt.NetworkError("Network down")
    mock_exchange.fetch_open_orders_exception = ccxt.NetworkError("Network down")
    
    res = await gateway.confirm_order_exists(
        exchange_order_id="exchange-id",
        symbol=SYMBOL,
        side="sell",
        reduce_only=True,
        stop_price=Decimal("2000.0"),
        expected_type="STOP_MARKET"
    )
    assert res is False
