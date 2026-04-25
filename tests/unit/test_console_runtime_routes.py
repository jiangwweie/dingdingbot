"""Unit tests for Console Runtime routes (v1 readonly API - second batch).

Mock 契约与真实 repo 对齐:
- signals/attempts: {"total": int, "data": list[dict]}
- orders: get_orders_by_status(status, symbol=None), get_orders_by_symbol(symbol), get_open_orders()
- intents: list(status=...), list_unfinished() - 都不接受 limit
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.readmodels.runtime_attempts import RuntimeAttemptsReadModel
from src.application.readmodels.runtime_execution_intents import RuntimeExecutionIntentsReadModel
from src.application.readmodels.runtime_orders import RuntimeOrdersReadModel
from src.application.readmodels.runtime_positions import RuntimePositionsReadModel
from src.application.readmodels.runtime_signals import RuntimeSignalsReadModel
from src.domain.execution_intent import ExecutionIntentStatus
from src.domain.models import OrderStatus, PositionInfo


def _make_account_snapshot(
    total_balance: Decimal = Decimal("1000"),
    available_balance: Decimal = Decimal("800"),
    unrealized_pnl: Decimal = Decimal("50"),
    timestamp_ms: int | None = None,
    positions: list[PositionInfo] | None = None,
) -> MagicMock:
    snapshot = MagicMock()
    snapshot.total_balance = total_balance
    snapshot.available_balance = available_balance
    snapshot.unrealized_pnl = unrealized_pnl
    snapshot.timestamp = timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    snapshot.positions = positions or []
    return snapshot


def _make_position(
    symbol: str = "ETH/USDT:USDT",
    side: str = "long",
    size: Decimal = Decimal("0.5"),
    entry_price: Decimal = Decimal("3000"),
    current_price: Decimal = Decimal("3100"),
    unrealized_pnl: Decimal = Decimal("50"),
    leverage: int = 5,
) -> PositionInfo:
    return PositionInfo(
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
    )


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# ============================================================
# Positions Tests
# ============================================================


@pytest.mark.asyncio
async def test_positions_adapter_normal_projection():
    """Positions adapter should project account snapshot to console format."""
    read_model = RuntimePositionsReadModel()
    position = _make_position()
    snapshot = _make_account_snapshot(positions=[position])

    response = await read_model.build(account_snapshot=snapshot, position_repo=None)

    assert len(response.positions) == 1
    pos = response.positions[0]
    assert pos.symbol == "ETH/USDT:USDT"
    assert pos.direction == "LONG"
    assert pos.quantity == 0.5
    assert pos.entry_price == 3000.0
    assert pos.current_price == 3000.0  # PositionInfo 没有 current_price, fallback
    assert pos.unrealized_pnl == 50.0
    assert pos.leverage == 5
    assert abs(pos.margin - 300.0) < 0.01
    assert abs(pos.exposure - 1500.0) < 0.01


@pytest.mark.asyncio
async def test_positions_adapter_short_direction():
    read_model = RuntimePositionsReadModel()
    position = _make_position(side="short")
    snapshot = _make_account_snapshot(positions=[position])

    response = await read_model.build(account_snapshot=snapshot, position_repo=None)

    assert response.positions[0].direction == "SHORT"


@pytest.mark.asyncio
async def test_positions_adapter_no_snapshot():
    read_model = RuntimePositionsReadModel()

    response = await read_model.build(account_snapshot=None, position_repo=None)

    assert response.positions == []


# ============================================================
# Signals Tests (真实 repo 返回 {"total": ..., "data": [...]})
# ============================================================


@pytest.mark.asyncio
async def test_signals_adapter_with_envelope():
    """Signals adapter should correctly read {"total": ..., "data": [...]} envelope."""
    read_model = RuntimeSignalsReadModel()

    async def mock_get_signals(*args, **kwargs):
        return {
            "total": 1,
            "data": [
                {
                    "id": "signal_001",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "15m",
                    "direction": "LONG",
                    "strategy_name": "pinbar_ema",
                    "score": 0.85,
                    "created_at": _now_ms(),
                    "status": "PENDING",
                }
            ],
        }

    signal_repo = MagicMock()
    signal_repo.get_signals = mock_get_signals

    response = await read_model.build(signal_repo=signal_repo, symbol=None, limit=100)

    assert len(response.signals) == 1
    sig = response.signals[0]
    assert sig.signal_id == "signal_001"
    assert sig.symbol == "ETH/USDT:USDT"
    assert sig.direction == "LONG"
    assert sig.strategy_name == "pinbar_ema"
    assert sig.score == 0.85
    assert sig.status == "PENDING"


@pytest.mark.asyncio
async def test_signals_adapter_empty_envelope():
    """Signals adapter should handle empty {"total": 0, "data": []} correctly."""
    read_model = RuntimeSignalsReadModel()

    async def mock_get_signals(*args, **kwargs):
        return {"total": 0, "data": []}

    signal_repo = MagicMock()
    signal_repo.get_signals = mock_get_signals

    response = await read_model.build(signal_repo=signal_repo, symbol=None, limit=100)

    assert response.signals == []


@pytest.mark.asyncio
async def test_signals_adapter_no_repo():
    read_model = RuntimeSignalsReadModel()

    response = await read_model.build(signal_repo=None, symbol=None, limit=100)

    assert response.signals == []


# ============================================================
# Attempts Tests (真实 repo 返回 {"total": ..., "data": [...]})
# ============================================================


@pytest.mark.asyncio
async def test_attempts_adapter_with_envelope():
    """Attempts adapter should correctly read {"total": ..., "data": [...]} envelope."""
    read_model = RuntimeAttemptsReadModel()

    async def mock_get_attempts(*args, **kwargs):
        return {
            "total": 1,
            "data": [
                {
                    "id": "attempt_001",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "15m",
                    "final_result": "FILTERED",
                    "kline_timestamp": _now_ms(),
                }
            ],
        }

    signal_repo = MagicMock()
    signal_repo.get_attempts = mock_get_attempts

    response = await read_model.build(signal_repo=signal_repo, symbol=None, timeframe=None, limit=100)

    assert len(response.attempts) == 1
    att = response.attempts[0]
    assert att.attempt_id == "attempt_001"
    assert att.signal_id is None
    assert att.final_result == "FILTERED"
    assert att.filter_reason == "filter_rejected"
    assert att.reject_reason is None


@pytest.mark.asyncio
async def test_attempts_adapter_no_pattern_with_envelope():
    """Attempts adapter should map NO_PATTERN with envelope."""
    read_model = RuntimeAttemptsReadModel()

    async def mock_get_attempts(*args, **kwargs):
        return {
            "total": 1,
            "data": [
                {
                    "id": "attempt_002",
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "1h",
                    "final_result": "NO_PATTERN",
                    "kline_timestamp": _now_ms(),
                }
            ],
        }

    signal_repo = MagicMock()
    signal_repo.get_attempts = mock_get_attempts

    response = await read_model.build(signal_repo=signal_repo, symbol=None, timeframe=None, limit=100)

    assert len(response.attempts) == 1
    assert response.attempts[0].final_result == "NO_PATTERN"
    assert response.attempts[0].reject_reason == "no_pattern_detected"


# ============================================================
# Orders Tests (真实 repo 签名)
# ============================================================


@pytest.mark.asyncio
async def test_orders_adapter_by_symbol():
    """Orders adapter should use get_orders_by_symbol with real signature."""
    read_model = RuntimeOrdersReadModel()

    order = MagicMock()
    order.id = "order_001"
    order.symbol = "ETH/USDT:USDT"
    order.direction = "LONG"
    order.order_type = "LIMIT"
    order.status = "OPEN"
    order.requested_qty = Decimal("0.5")
    order.price = Decimal("3000")
    order.reduce_only = False
    order.created_at = _now_ms()
    order.updated_at = None

    async def mock_get_orders_by_symbol(symbol, limit=100):
        assert symbol == "ETH/USDT:USDT"
        return [order]

    order_repo = MagicMock()
    order_repo.get_orders_by_symbol = mock_get_orders_by_symbol

    response = await read_model.build(order_repo=order_repo, symbol="ETH/USDT:USDT", status=None, limit=100)

    assert len(response.orders) == 1
    ord = response.orders[0]
    assert ord.order_id == "order_001"
    assert ord.side == "BUY"
    assert ord.type == "LIMIT"
    assert ord.status == "OPEN"


@pytest.mark.asyncio
async def test_orders_adapter_by_status():
    """Orders adapter should convert status string to OrderStatus enum before calling repo."""
    read_model = RuntimeOrdersReadModel()

    order = MagicMock()
    order.id = "order_002"
    order.symbol = "ETH/USDT:USDT"
    order.direction = "SHORT"
    order.order_type = "MARKET"
    order.status = "OPEN"
    order.requested_qty = Decimal("0.3")
    order.price = None
    order.reduce_only = True
    order.created_at = _now_ms()
    order.updated_at = _now_ms()

    async def mock_get_orders_by_status(status, symbol=None):
        # 真实 repo 期望 OrderStatus 枚举，不是原始字符串
        assert isinstance(status, OrderStatus)
        assert status == OrderStatus.OPEN
        assert symbol is None
        return [order]

    order_repo = MagicMock()
    order_repo.get_orders_by_status = mock_get_orders_by_status

    response = await read_model.build(order_repo=order_repo, symbol=None, status="OPEN", limit=100)

    assert len(response.orders) == 1
    ord = response.orders[0]
    assert ord.side == "SELL"
    assert ord.reduce_only is True


@pytest.mark.asyncio
async def test_orders_adapter_invalid_status():
    """Orders adapter should return empty list for invalid status string, not call repo."""
    read_model = RuntimeOrdersReadModel()

    repo_called = False

    async def mock_get_orders_by_status(status, symbol=None):
        repo_called = True
        raise AssertionError("repo should not be called with invalid status")

    order_repo = MagicMock()
    order_repo.get_orders_by_status = mock_get_orders_by_status

    response = await read_model.build(order_repo=order_repo, symbol=None, status="INVALID_STATUS", limit=100)

    assert response.orders == []
    assert not repo_called


@pytest.mark.asyncio
async def test_orders_adapter_no_symbol_no_status():
    """Orders adapter should use get_open_orders when no symbol/status, not get_orders_by_symbol("")."""
    read_model = RuntimeOrdersReadModel()

    order = MagicMock()
    order.id = "order_003"
    order.symbol = "ETH/USDT:USDT"
    order.direction = "LONG"
    order.order_type = "LIMIT"
    order.status = "OPEN"
    order.requested_qty = Decimal("0.5")
    order.price = Decimal("3000")
    order.reduce_only = False
    order.created_at = _now_ms()
    order.updated_at = None

    async def mock_get_open_orders(symbol=None):
        return [order]

    async def mock_get_orders_by_symbol(symbol, limit=100):
        # Should NOT be called with empty string
        raise AssertionError(f"get_orders_by_symbol called with symbol='{symbol}', should not happen")

    order_repo = MagicMock()
    order_repo.get_open_orders = mock_get_open_orders
    order_repo.get_orders_by_symbol = mock_get_orders_by_symbol

    response = await read_model.build(order_repo=order_repo, symbol=None, status=None, limit=100)

    assert len(response.orders) == 1
    assert response.orders[0].order_id == "order_003"


@pytest.mark.asyncio
async def test_orders_adapter_no_repo():
    read_model = RuntimeOrdersReadModel()

    response = await read_model.build(order_repo=None, symbol=None, status=None, limit=100)

    assert response.orders == []


# ============================================================
# Execution Intents Tests (真实 repo 签名)
# ============================================================


@pytest.mark.asyncio
async def test_intents_adapter_list_unfinished():
    """Intents adapter should use list_unfinished() without limit."""
    read_model = RuntimeExecutionIntentsReadModel()

    intent = MagicMock()
    intent.id = "intent_001"
    intent.symbol = "ETH/USDT:USDT"
    intent.status = "pending"
    intent.signal_id = "signal_001"
    intent.created_at = _now_ms()
    intent.updated_at = None
    intent.signal_payload = {
        "direction": "LONG",
        "suggested_position_size": Decimal("0.5"),
    }

    async def mock_list_unfinished():
        # 真实签名: list_unfinished() - 不接受参数
        return [intent]

    intent_repo = MagicMock()
    intent_repo.list_unfinished = mock_list_unfinished

    response = await read_model.build(intent_repo=intent_repo, status=None, limit=100)

    assert len(response.intents) == 1
    inte = response.intents[0]
    assert inte.intent_id == "intent_001"
    assert inte.side == "BUY"
    assert inte.quantity == 0.5
    assert inte.related_signal_id == "signal_001"


@pytest.mark.asyncio
async def test_intents_adapter_list_with_status():
    """Intents adapter should convert status string to ExecutionIntentStatus enum before calling repo."""
    read_model = RuntimeExecutionIntentsReadModel()

    intent = MagicMock()
    intent.id = "intent_002"
    intent.symbol = "BTC/USDT:USDT"
    intent.status = "completed"
    intent.signal_id = "signal_002"
    intent.created_at = _now_ms()
    intent.updated_at = _now_ms()
    intent.signal_payload = {
        "direction": "SHORT",
        "suggested_position_size": Decimal("0.2"),
    }

    async def mock_list(status=None):
        # 真实 repo 期望 ExecutionIntentStatus 枚举，不是原始字符串
        assert isinstance(status, ExecutionIntentStatus)
        assert status == ExecutionIntentStatus.COMPLETED
        return [intent]

    intent_repo = MagicMock()
    intent_repo.list = mock_list

    response = await read_model.build(intent_repo=intent_repo, status="completed", limit=100)

    assert len(response.intents) == 1
    inte = response.intents[0]
    assert inte.intent_id == "intent_002"
    assert inte.side == "SELL"
    assert inte.quantity == 0.2


@pytest.mark.asyncio
async def test_intents_adapter_invalid_status():
    """Intents adapter should return empty list for invalid status string, not call repo."""
    read_model = RuntimeExecutionIntentsReadModel()

    repo_called = False

    async def mock_list(status=None):
        repo_called = True
        raise AssertionError("repo should not be called with invalid status")

    intent_repo = MagicMock()
    intent_repo.list = mock_list

    response = await read_model.build(intent_repo=intent_repo, status="invalid_status", limit=100)

    assert response.intents == []
    assert not repo_called


@pytest.mark.asyncio
async def test_intents_adapter_limit_slice():
    """Intents adapter should slice results at readmodel layer when limit is set."""
    read_model = RuntimeExecutionIntentsReadModel()

    intents = []
    for i in range(5):
        intent = MagicMock()
        intent.id = f"intent_{i:03d}"
        intent.symbol = "ETH/USDT:USDT"
        intent.status = "pending"
        intent.signal_id = f"signal_{i:03d}"
        intent.created_at = _now_ms()
        intent.updated_at = None
        intent.signal_payload = {
            "direction": "LONG",
            "suggested_position_size": Decimal("0.1"),
        }
        intents.append(intent)

    async def mock_list_unfinished():
        return intents  # 返回 5 个，但 limit=3

    intent_repo = MagicMock()
    intent_repo.list_unfinished = mock_list_unfinished

    response = await read_model.build(intent_repo=intent_repo, status=None, limit=3)

    # readmodel 层切片：只返回 3 个
    assert len(response.intents) == 3


@pytest.mark.asyncio
async def test_intents_adapter_empty_list():
    read_model = RuntimeExecutionIntentsReadModel()

    async def mock_list_unfinished():
        return []

    intent_repo = MagicMock()
    intent_repo.list_unfinished = mock_list_unfinished

    response = await read_model.build(intent_repo=intent_repo, status=None, limit=100)

    assert response.intents == []


@pytest.mark.asyncio
async def test_intents_adapter_no_repo():
    read_model = RuntimeExecutionIntentsReadModel()

    response = await read_model.build(intent_repo=None, status=None, limit=100)

    assert response.intents == []