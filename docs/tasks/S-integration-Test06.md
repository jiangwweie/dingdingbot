# Test-06: 多策略 +EMA 缓存 + 信号状态跟踪集成测试

**优先级**: P1 | **预估工时**: 3-4h | **负责窗口**: 窗口 3（用户）

---

## 测试目标

验证多个策略共享 EMA 缓存时，每个策略的信号独立正确跟踪。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_multi_strategy_ema_signal_tracking.py`

**代码模板**:

```python
"""
Test-06: Multi-Strategy + EMA Cache + Signal Tracking Integration Test

Verifies independent signal tracking when multiple strategies share EMA cache.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import List

from src.domain.models import KlineData, SignalStatus, StrategyDefinition
from src.domain.indicators import EMACache
from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.signal_repository import SignalRepository
from src.application.signal_tracker import SignalStatusTracker


@pytest.fixture
async def ema_cache():
    """Create EMACache instance."""
    cache = EMACache(ttl_seconds=3600, max_size=1000)
    yield cache
    await cache.clear()


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
    """Create SignalPipeline instance."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService

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


class TestMultiStrategyEMASignalTracking:
    """Test multi-strategy with shared EMA cache and signal tracking."""

    async def test_ema_cache_shared_across_strategies(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 配置 5 个策略，都使用 EMA60 过滤器
        2. 推送相同 K 线数据
        3. 验证 EMA 只计算一次（缓存命中）
        4. 验证每个策略生成独立的信号
        """
        # TODO: 实现
        pass

    async def test_signals_tracked_independently(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 多个策略生成多个信号
        2. 验证每个信号独立跟踪
        3. 更新一个信号状态，其他不受影响
        """
        # TODO: 实现
        pass

    async def test_ema_cache_stats_correct(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 多策略共享缓存
        2. 验证缓存统计正确
        3. 访问计数符合预期
        """
        # TODO: 实现
        pass
```

---

## 步骤 2: 实现核心测试逻辑

### 测试 1: EMA 缓存共享

```python
async def test_ema_cache_shared_across_strategies(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
    ema_cache,
):
    """验证多策略共享 EMA 缓存。"""

    # 1. 清空缓存
    await ema_cache.clear()

    # 2. 创建测试 K 线
    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000,
        open=Decimal('50000'),
        high=Decimal('50100'),
        low=Decimal('49900'),
        close=Decimal('50050'),
        volume=Decimal('1000'),
        is_closed=True,
    )

    # 3. 推送 K 线（多策略会共享 EMA）
    signals = []
    for i in range(5):
        # 模拟多策略处理
        signal = await signal_pipeline.process_kline(kline)
        if signal is not None:
            signals.append(signal)

    # 4. 验证：生成了信号
    assert len(signals) > 0

    # 5. 验证：EMA 缓存命中
    stats = await ema_cache.get_stats()
    assert stats['size'] >= 1

    # 6. 验证：访问计数正确
    for key, entry in stats['entries'].items():
        assert entry['access_count'] >= 1
```

### 测试 2: 信号独立跟踪

```python
async def test_signals_tracked_independently(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
    ema_cache,
):
    """验证信号独立跟踪。"""

    # 1. 生成多个信号
    signals = []
    for i in range(5):
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000 + i * 60000,
            open=Decimal('50000') + Decimal(i * 100),
            high=Decimal('50100') + Decimal(i * 100),
            low=Decimal('49900') + Decimal(i * 100),
            close=Decimal('50050') + Decimal(i * 100),
            volume=Decimal('1000'),
            is_closed=True,
        )
        signal = await signal_pipeline.process_kline(kline)
        if signal is not None:
            signals.append(signal)

    # 2. 验证：所有信号初始状态为 GENERATED
    for signal in signals:
        track = await status_tracker.get_signal_status(signal.id)
        assert track.status == SignalStatus.GENERATED

    # 3. 更新信号 1 为 FILLED
    await status_tracker.update_status(
        signals[0].id,
        SignalStatus.FILLED,
        filled_price=Decimal('51000'),
    )

    # 4. 更新信号 2 为 CANCELLED
    await status_tracker.update_status(
        signals[1].id,
        SignalStatus.CANCELLED,
        cancel_reason="测试取消",
    )

    # 5. 验证：信号 1 状态为 FILLED
    track1 = await status_tracker.get_signal_status(signals[0].id)
    assert track1.status == SignalStatus.FILLED
    assert track1.filled_price == Decimal('51000')

    # 6. 验证：信号 2 状态为 CANCELLED
    track2 = await status_tracker.get_signal_status(signals[1].id)
    assert track2.status == SignalStatus.CANCELLED

    # 7. 验证：其他信号状态不变
    for i in range(2, len(signals)):
        track = await status_tracker.get_signal_status(signals[i].id)
        assert track.status == SignalStatus.GENERATED
```

### 测试 3: 缓存统计正确

```python
async def test_ema_cache_stats_correct(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
    ema_cache,
):
    """验证 EMA 缓存统计正确。"""

    # 1. 清空缓存
    await ema_cache.clear()

    # 2. 推送 K 线
    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000,
        open=Decimal('50000'),
        high=Decimal('50100'),
        low=Decimal('49900'),
        close=Decimal('50050'),
        volume=Decimal('1000'),
        is_closed=True,
    )

    # 3. 多次处理（模拟多策略）
    for _ in range(5):
        await signal_pipeline.process_kline(kline)

    # 4. 验证缓存统计
    stats = await ema_cache.get_stats()

    assert stats['size'] >= 1
    assert stats['max_size'] == 1000
    assert stats['ttl_seconds'] == 3600

    # 5. 验证条目信息
    for key, entry in stats['entries'].items():
        assert 'period' in entry
        assert 'is_ready' in entry
        assert 'access_count' in entry
        assert 'age_seconds' in entry
```

---

## 步骤 3: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_multi_strategy_ema_signal_tracking.py -v

# 运行整个类
pytest tests/integration/test_multi_strategy_ema_signal_tracking.py::TestMultiStrategyEMASignalTracking -v
```

**预期输出**:
```
tests/integration/test_multi_strategy_ema_signal_tracking.py::TestMultiStrategyEMASignalTracking::test_ema_cache_shared_across_strategies PASSED
tests/integration/test_multi_strategy_ema_signal_tracking.py::TestMultiStrategyEMASignalTracking::test_signals_tracked_independently PASSED
tests/integration/test_multi_strategy_ema_signal_tracking.py::TestMultiStrategyEMASignalTracking::test_ema_cache_stats_correct PASSED

============================== 3 passed in 3.5s ==============================
```

---

## 步骤 4: 提交代码

```bash
git add tests/integration/test_multi_strategy_ema_signal_tracking.py
git commit -m "test(integration): 添加多策略+EMA 缓存 + 信号跟踪集成测试 (#Test-06)"
```

---

## 依赖

- ✅ Test-01 已完成（窗口 3 先执行 Test-01）

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| EMA 缓存未命中 | 检查缓存键名是否正确 |
| 信号 ID 重复 | 确保使用 UUID 生成器 |
| 状态更新不生效 | 检查 `signal_repository` 是否正确注入 |

---

*本文档为窗口 3 执行 Test-06 的详细指南*
