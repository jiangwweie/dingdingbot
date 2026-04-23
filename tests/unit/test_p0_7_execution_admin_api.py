"""
P0-7: Execution Admin API 测试

测试目标：
1. 查询 pending_recovery 返回列表
2. 查询 circuit_breaker 返回 symbol 列表
3. clear pending_recovery 生效
4. clear circuit_breaker 生效
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.interfaces.api import app, set_v3_dependencies
from src.application.execution_orchestrator import ExecutionOrchestrator


@pytest.fixture
def mock_orchestrator():
    """创建 mock ExecutionOrchestrator"""
    orchestrator = MagicMock(spec=ExecutionOrchestrator)
    return orchestrator


@pytest.fixture
def client(mock_orchestrator):
    """创建 TestClient 并注入 mock orchestrator"""
    # 注入 mock orchestrator
    set_v3_dependencies(
        capital_protection=None,
        account_service=None,
        execution_orchestrator=mock_orchestrator,
    )
    return TestClient(app)


def test_get_pending_recovery_success(client, mock_orchestrator):
    """
    测试查询 pending_recovery 成功

    场景：
    1. orchestrator 已初始化
    2. 有 2 条 pending_recovery 记录
    断言：
    - 返回 200
    - count = 2
    - records 包含正确字段
    """
    # 准备：mock list_pending_recovery
    mock_orchestrator.list_pending_recovery.return_value = [
        {
            "order_id": "order_001",
            "exchange_order_id": "ex_order_001",
            "symbol": "BTC/USDT:USDT",
            "error": "交易所撤销订单失败",
        },
        {
            "order_id": "order_002",
            "exchange_order_id": "ex_order_002",
            "symbol": "ETH/USDT:USDT",
            "error": "交易所撤销订单失败",
        },
    ]

    # 执行：GET /api/execution/recovery/pending
    response = client.get("/api/execution/recovery/pending")

    # 验证
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["count"] == 2
    assert len(data["records"]) == 2
    assert data["records"][0]["order_id"] == "order_001"
    assert data["records"][1]["order_id"] == "order_002"


def test_get_circuit_breaker_success(client, mock_orchestrator):
    """
    测试查询 circuit_breaker 成功

    场景：
    1. orchestrator 已初始化
    2. 有 2 个 symbol 被熔断
    断言：
    - 返回 200
    - count = 2
    - symbols 包含正确的 symbol
    """
    # 准备：mock list_circuit_breaker_symbols
    mock_orchestrator.list_circuit_breaker_symbols.return_value = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
    ]

    # 执行：GET /api/execution/circuit-breaker
    response = client.get("/api/execution/circuit-breaker")

    # 验证
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["count"] == 2
    assert len(data["symbols"]) == 2
    assert "BTC/USDT:USDT" in data["symbols"]
    assert "ETH/USDT:USDT" in data["symbols"]


def test_clear_pending_recovery_success(client, mock_orchestrator):
    """
    测试清除 pending_recovery 成功

    场景：
    1. orchestrator 已初始化
    2. pending_recovery 存在
    断言：
    - 返回 200
    - clear_pending_recovery 被调用
    """
    # 准备：mock get_pending_recovery 和 clear_pending_recovery
    mock_orchestrator.get_pending_recovery.return_value = {
        "order_id": "order_001",
        "exchange_order_id": "ex_order_001",
        "symbol": "BTC/USDT:USDT",
        "error": "交易所撤销订单失败",
    }
    mock_orchestrator.clear_pending_recovery.return_value = None

    # 执行：POST /api/execution/recovery/pending/order_001/clear
    response = client.post("/api/execution/recovery/pending/order_001/clear")

    # 验证
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "order_001" in data["message"]

    # 验证：clear_pending_recovery 被调用
    mock_orchestrator.clear_pending_recovery.assert_called_once_with("order_001")


def test_clear_pending_recovery_not_found(client, mock_orchestrator):
    """
    测试清除不存在的 pending_recovery

    场景：
    1. orchestrator 已初始化
    2. pending_recovery 不存在
    断言：
    - 返回 404
    """
    # 准备：mock get_pending_recovery 返回 None
    mock_orchestrator.get_pending_recovery.return_value = None

    # 执行：POST /api/execution/recovery/pending/order_999/clear
    response = client.post("/api/execution/recovery/pending/order_999/clear")

    # 验证
    assert response.status_code == 404


def test_clear_circuit_breaker_success(client, mock_orchestrator):
    """
    测试清除 circuit_breaker 成功

    场景：
    1. orchestrator 已初始化
    2. symbol 处于熔断状态
    断言：
    - 返回 200
    - clear_circuit_breaker 被调用
    """
    # 准备：mock is_symbol_blocked 和 clear_circuit_breaker
    mock_orchestrator.is_symbol_blocked.return_value = True
    mock_orchestrator.clear_circuit_breaker.return_value = None

    # 执行：POST /api/execution/circuit-breaker/clear?symbol=BTC/USDT:USDT
    response = client.post(
        "/api/execution/circuit-breaker/clear",
        params={"symbol": "BTC/USDT:USDT"}
    )

    # 验证
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "BTC/USDT:USDT" in data["message"]

    # 验证：clear_circuit_breaker 被调用
    mock_orchestrator.clear_circuit_breaker.assert_called_once_with("BTC/USDT:USDT")


def test_clear_circuit_breaker_not_found(client, mock_orchestrator):
    """
    测试清除不存在的 circuit_breaker

    场景：
    1. orchestrator 已初始化
    2. symbol 未处于熔断状态
    断言：
    - 返回 404
    """
    # 准备：mock is_symbol_blocked 返回 False
    mock_orchestrator.is_symbol_blocked.return_value = False

    # 执行：POST /api/execution/circuit-breaker/clear?symbol=BTC/USDT:USDT
    response = client.post(
        "/api/execution/circuit-breaker/clear",
        params={"symbol": "BTC/USDT:USDT"}
    )

    # 验证
    assert response.status_code == 404


if __name__ == "__main__":
    # 可直接运行：python tests/unit/test_p0_7_execution_admin_api.py
    import sys
    pytest.main([__file__, "-v"] + sys.argv[1:])
