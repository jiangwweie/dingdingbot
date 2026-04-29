# Test-05: 队列拥堵 + 信号状态完整性集成测试

**优先级**: P0 | **预估工时**: 4-6h | **负责窗口**: 窗口 2（用户）

---

## 测试目标

验证队列拥堵时，信号状态不丢失、不重复、顺序正确。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_queue_congestion_signal_integrity.py`

**代码模板**:

```python
"""
Test-05: Queue Congestion + Signal Integrity Integration Test

Verifies signal state integrity during queue congestion.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import List
from unittest.mock import patch, AsyncMock

from src.domain.models import KlineData, SignalStatus
from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.signal_repository import SignalRepository
from src.application.signal_tracker import SignalStatusTracker


@pytest.fixture
async def config_manager():
    """Create ConfigManager instance."""
    from src.application.config_manager import load_all_configs
    return load_all_configs()


@pytest.fixture
async def signal_repository():
    """Create in-memory SignalRepository."""
    repository = SignalRepository(":memory:")
    await repository.initialize()
    yield repository
    await repository.close()


@pytest.fixture
async def status_tracker(signal_repository):
    """Create SignalStatusTracker."""
    return SignalStatusTracker(signal_repository)


@pytest.fixture
async def signal_pipeline(config_manager, signal_repository, status_tracker):
    """Create SignalPipeline with small queue for testing."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService

    # 配置小队列参数
    config_manager.core_config.signal_pipeline.queue.batch_size = 10
    config_manager.core_config.signal_pipeline.queue.max_queue_size = 100

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_total_exposure=Decimal('0.8'),
    )

    notifier = NotificationService(enabled=False, webhook_url=None)

    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=notifier,
        signal_repository=signal_repository,
        cooldown_seconds=300,
    )

    yield pipeline

    await pipeline.close()


class TestQueueCongestionSignalIntegrity:
    """Test signal integrity during queue congestion."""

    async def test_no_signal_loss_during_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 配置小队列（max_size=100）
        2. 快速推送 500 个信号
        3. 验证背压告警触发
        4. 等待队列处理完成
        5. 验证所有信号落盘，无丢失
        """
        # TODO: 实现
        pass

    async def test_no_duplicate_signals_during_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 队列拥堵场景
        2. 验证无重复信号
        """
        # TODO: 实现
        pass

    async def test_all_signal_statuses_correct_after_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 队列拥堵后
        2. 验证所有信号状态正确
        """
        # TODO: 实现
        pass
```

---

## 步骤 2: 实现核心测试逻辑

### 测试 1: 无信号丢失

```python
async def test_no_signal_loss_during_congestion(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
):
    """验证队列拥堵时无信号丢失。"""

    # 1. 准备 500 个 K 线数据
    klines = []
    for i in range(500):
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
        klines.append(kline)

    # 2. 并发推送所有 K 线
    tasks = [signal_pipeline.process_kline(kline) for kline in klines]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 3. 过滤出成功的信号
    signals = [r for r in results if isinstance(r, type(signal_pipeline.process_kline(klines[0])))]
    signal_ids = [s.id for s in signals if s is not None]

    # 4. 验证：生成了信号
    assert len(signal_ids) > 0

    # 5. 等待队列完全处理
    max_wait = 60  # 最多等 60 秒
    waited = 0
    while waited < max_wait:
        queue_size = signal_pipeline.get_queue_size()
        if queue_size == 0:
            break
        await asyncio.sleep(1)
        waited += 1

    # 6. 验证：队列已清空
    assert signal_pipeline.get_queue_size() == 0

    # 7. 验证：所有信号已落盘
    all_signals = await signal_repository.get_all_signals()
    all_ids = [s['id'] if isinstance(s, dict) else s.id for s in all_signals]

    # 8. 验证：无丢失
    assert len(all_ids) == len(signal_ids), f"Expected {len(signal_ids)} signals, got {len(all_ids)}"
```

### 测试 2: 无重复信号

```python
async def test_no_duplicate_signals_during_congestion(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
):
    """验证队列拥堵时无重复信号。"""

    # ... 前置步骤同上 ...

    # 验证：无重复
    unique_ids = set(signal_ids)
    assert len(unique_ids) == len(signal_ids), "Duplicate signal IDs detected"
```

### 测试 3: 背压告警

```python
async def test_backpressure_alert_triggered(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
    caplog,
):
    """验证背压告警正确触发。"""

    import logging

    # 1. 设置日志捕获
    caplog.set_level(logging.WARNING)

    # 2. 推送大量信号
    # ... 同上 ...

    # 3. 验证：背压告警日志
    assert "BACKPRESSURE ALERT" in caplog.text
```

---

## 步骤 3: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_queue_congestion_signal_integrity.py -v

# 运行特定测试
pytest tests/integration/test_queue_congestion_signal_integrity.py::TestQueueCongestionSignalIntegrity::test_no_signal_loss_during_congestion -v
```

**预期输出**:
```
tests/integration/test_queue_congestion_signal_integrity.py::TestQueueCongestionSignalIntegrity::test_no_signal_loss_during_congestion PASSED
tests/integration/test_queue_congestion_signal_integrity.py::TestQueueCongestionSignalIntegrity::test_no_duplicate_signals_during_congestion PASSED
tests/integration/test_queue_congestion_signal_integrity.py::TestQueueCongestionSignalIntegrity::test_backpressure_alert_triggered PASSED

============================== 3 passed in 8.5s ==============================
```

---

## 步骤 4: 提交代码

```bash
git add tests/integration/test_queue_congestion_signal_integrity.py
git commit -m "test(integration): 添加队列拥堵 + 信号完整性集成测试 (#Test-05)"
```

---

## 依赖

无

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| 测试时间过长 | 缩小队列参数，减少信号数量 |
| 队列 size 方法不存在 | 添加 `get_queue_size()` 方法到 SignalPipeline |
| 非确定性行为 | 多次运行验证，增加重试 |
| 数据库连接耗尽 | 使用 SQLite 内存模式 |

---

*本文档为窗口 2 执行 Test-05 的详细指南*
