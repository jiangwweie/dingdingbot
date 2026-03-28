# Test-02: 队列背压 + WebSocket 降级集成测试

**优先级**: P2 | **预估工时**: 2-3h | **负责窗口**: 窗口 2（用户）

---

## 测试目标

验证 WebSocket 降级到轮询时，高并发信号队列仍能正常工作，背压告警正确触发。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_queue_backpressure_ws.py`

**代码模板**:

```python
"""
Test-02: Queue Backpressure + WebSocket Fallback Integration Test

Verifies queue functionality during WebSocket degradation.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from src.domain.models import KlineData
from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.signal_repository import SignalRepository


@pytest.fixture
async def config_manager():
    """Create ConfigManager instance."""
    from src.application.config_manager import load_all_configs
    return load_all_configs()


@pytest.fixture
async def exchange_gateway(config_manager):
    """Create ExchangeGateway instance."""
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=config_manager.user_config.api_key,
        api_secret=config_manager.user_config.api_secret,
        testnet=config_manager.user_config.testnet,
    )
    await gateway.initialize()
    yield gateway
    await gateway.close()


@pytest.fixture
async def signal_pipeline(config_manager, exchange_gateway):
    """Create SignalPipeline with small queue."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService
    from src.infrastructure.signal_repository import SignalRepository

    # 配置小队列入量
    config_manager.core_config.signal_pipeline.queue.batch_size = 5
    config_manager.core_config.signal_pipeline.queue.flush_interval = 1.0
    config_manager.core_config.signal_pipeline.queue.max_queue_size = 50

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_total_exposure=Decimal('0.8'),
    )

    repository = SignalRepository(":memory:")
    await repository.initialize()

    notifier = NotificationService(enabled=False, webhook_url=None)

    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=notifier,
        signal_repository=repository,
        cooldown_seconds=300,
    )

    yield pipeline

    await pipeline.close()
    await repository.close()


class TestQueueBackpressureWSFallback:
    """Test queue backpressure during WebSocket fallback."""

    async def test_queue_works_during_ws_fallback(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
        caplog,
    ):
        """
        测试场景:
        1. WebSocket 正常运行
        2. 模拟 WebSocket 失败，降级到轮询
        3. 轮询间隔内大量 K 线涌入
        4. 验证队列背压告警触发
        5. 验证批量落盘正常
        """
        # TODO: 实现
        pass

    async def test_worker_auto_recovery_during_ws_fallback(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
    ):
        """
        测试场景:
        1. WebSocket 降级后
        2. 模拟 Worker 异常
        3. 验证自动恢复机制
        """
        # TODO: 实现
        pass
```

---

## 步骤 2: 实现核心测试逻辑

### 测试 1: 队列背压告警

```python
async def test_queue_works_during_ws_fallback(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
    caplog,
):
    """验证 WebSocket 降级时队列背压告警正确触发。"""
    import logging

    caplog.set_level(logging.WARNING)

    # 1. 初始 WebSocket 正常
    assert exchange_gateway._ws_running or not exchange_gateway.is_polling_mode()

    # 2. 模拟 WebSocket 失败
    with patch.object(exchange_gateway, '_ws_subscribe_account_loop', side_effect=Exception("WS failed")):
        try:
            await exchange_gateway.subscribe_account_updates(lambda x: None)
        except Exception:
            pass

    # 3. 等待降级
    await asyncio.sleep(2)

    # 4. 验证：已降级到轮询
    assert not exchange_gateway._ws_running

    # 5. 快速推送 100 个 K 线（模拟轮询间隔内积压）
    tasks = []
    for i in range(100):
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000 + i * 60000,
            open=Decimal('50000') + Decimal(i),
            high=Decimal('50100') + Decimal(i),
            low=Decimal('49900') + Decimal(i),
            close=Decimal('50050') + Decimal(i),
            volume=Decimal('1000'),
            is_closed=True,
        )
        tasks.append(signal_pipeline.process_kline(kline))

    await asyncio.gather(*tasks, return_exceptions=True)

    # 6. 验证：背压告警
    assert "BACKPRESSURE ALERT" in caplog.text

    # 7. 等待队列处理
    await asyncio.sleep(5)

    # 8. 验证：队列清空
    assert signal_pipeline.get_queue_size() == 0
```

### 测试 2: Worker 自动恢复

```python
async def test_worker_auto_recovery_during_ws_fallback(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
):
    """验证 Worker 异常时自动恢复。"""

    # 1. WebSocket 降级
    # ... 同上 ...

    # 2. 模拟 Worker 异常
    original_worker = signal_pipeline._flush_worker
    signal_pipeline._flush_worker = AsyncMock(side_effect=Exception("Worker failed"))

    # 3. 触发 Worker
    try:
        await signal_pipeline._flush_worker()
    except Exception:
        pass

    # 4. 验证：Worker 重启（有新 task 创建）
    # 这需要添加计数器来追踪重启次数
```

---

## 步骤 3: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_queue_backpressure_ws.py -v
```

**预期输出**:
```
tests/integration/test_queue_backpressure_ws.py::TestQueueBackpressureWSFallback::test_queue_works_during_ws_fallback PASSED
tests/integration/test_queue_backpressure_ws.py::TestQueueBackpressureWSFallback::test_worker_auto_recovery_during_ws_fallback PASSED

============================== 2 passed in 6.5s ==============================
```

---

## 步骤 4: 提交代码

```bash
git add tests/integration/test_queue_backpressure_ws.py
git commit -m "test(integration): 添加队列背压+WebSocket 降级集成测试 (#Test-02)"
```

---

## 依赖

- ✅ Test-05 已完成（窗口 2 先执行 Test-05）

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| WebSocket 降级判断不准 | 添加 `is_polling_mode()` 方法 |
| 背压日志未输出 | 检查 `caplog` 配置 |
| Worker 恢复难验证 | 添加 `_worker_restart_count` 计数器 |

---

*本文档为窗口 2 执行 Test-02 的详细指南*
