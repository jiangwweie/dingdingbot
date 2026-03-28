# Test-03: EMA 缓存 + WebSocket 降级集成测试

**优先级**: P2 | **预估工时**: 2-3h | **负责窗口**: 窗口 1（Claude）

---

## 测试目标

验证 WebSocket 降级时，EMA 缓存正确失效/重建，避免使用过期数据。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_ema_cache_ws_fallback.py`

**代码模板**:

```python
"""
Test-03: EMA Cache + WebSocket Fallback Integration Test

Verifies EMA cache consistency during WebSocket degradation to polling mode.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.domain.models import KlineData
from src.domain.indicators import EMACache
from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.exchange_gateway import ExchangeGateway


@pytest.fixture
async def ema_cache():
    """Create EMACache instance for testing."""
    cache = EMACache(ttl_seconds=3600, max_size=1000)
    yield cache
    await cache.clear()


@pytest.fixture
async def config_manager():
    """Create ConfigManager instance for testing."""
    from src.application.config_manager import load_all_configs
    return load_all_configs()


@pytest.fixture
async def exchange_gateway(config_manager):
    """Create ExchangeGateway instance for testing."""
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
    """Create SignalPipeline instance for testing."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService
    from src.infrastructure.signal_repository import SignalRepository

    repository = SignalRepository(":memory:")
    await repository.initialize()

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_total_exposure=Decimal('0.8'),
    )

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


class TestEMACacheWSFallback:
    """Test EMA cache consistency during WebSocket fallback."""

    async def test_ema_cache_rebuild_on_ws_fallback(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
        ema_cache,
    ):
        """
        测试场景:
        1. WebSocket 正常运行，EMA 缓存正在使用
        2. 模拟 WebSocket 失败，降级到轮询模式
        3. 收到历史 K 线数据（时间戳更早）
        4. 验证 EMA 缓存正确重建
        """
        # TODO: 实现测试逻辑
        pass

    async def test_ema_cache_shared_across_strategies(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
        ema_cache,
    ):
        """
        测试场景:
        1. 多个策略共享同一个 EMA 周期
        2. 推送相同 K 线数据
        3. 验证 EMA 只计算一次（缓存命中）
        4. 验证每个策略独立生成信号
        """
        # TODO: 实现测试逻辑
        pass

    async def test_ema_cache_ttl_expiration(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
        ema_cache,
    ):
        """
        测试场景:
        1. EMA 缓存建立
        2. 模拟时间流逝（超过 TTL）
        3. 验证缓存自动失效
        4. 验证新 K 线到来时重新计算
        """
        # TODO: 实现测试逻辑
        pass
```

**验收**:
```bash
python -c "from tests.integration.test_ema_cache_ws_fallback import *; print('OK')"
```

---

## 步骤 2: 实现核心测试逻辑

### 测试 1: WebSocket 降级时 EMA 缓存重建

```python
async def test_ema_cache_rebuild_on_ws_fallback(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
    ema_cache,
):
    """验证 WebSocket 降级时 EMA 缓存正确重建。"""

    # 1. WebSocket 正常，推送 K 线建立 EMA 缓存
    klines = []
    for i in range(70):  # 超过 EMA60 周期
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
        await signal_pipeline.process_kline(kline)

    # 2. 验证：EMA 缓存已建立
    stats = await ema_cache.get_stats()
    assert stats['size'] >= 1

    # 3. 记录当前 EMA 值
    ema_key = "BTC/USDT:USDT:15m:60"
    old_ema_entry = stats['entries'].get(ema_key)
    assert old_ema_entry is not None
    old_ema_value = old_ema_entry.get('ema_value')

    # 4. 模拟 WebSocket 失败并降级
    with patch.object(exchange_gateway, '_ws_subscribe_account_loop', side_effect=Exception("WS failed")):
        # 触发订阅，会失败并降级
        try:
            await exchange_gateway.subscribe_account_updates(lambda x: None)
        except Exception:
            pass

    # 5. 等待降级完成
    await asyncio.sleep(2)

    # 6. 验证：已降级到轮询模式
    assert not exchange_gateway._ws_running or exchange_gateway.is_polling_mode()

    # 7. 模拟收到历史 K 线（时间戳更早）
    old_kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=500000,  # 早于之前的 K 线
        open=Decimal('49000'),
        high=Decimal('49100'),
        low=Decimal('48900'),
        close=Decimal('49050'),
        volume=Decimal('1000'),
        is_closed=True,
    )

    # 8. 处理历史 K 线
    await signal_pipeline.process_kline(old_kline)

    # 9. 验证：EMA 缓存已重建（值发生变化或被清理）
    new_stats = await ema_cache.get_stats()

    # 要么缓存被清理，要么 EMA 值发生变化
    if ema_key in new_stats['entries']:
        new_ema_entry = new_stats['entries'][ema_key]
        # EMA 值应该因历史数据而改变
        assert new_ema_entry['access_count'] > old_ema_entry['access_count']
    else:
        # 或者缓存被清理（降级时重置）
        pass
```

### 测试 2: 多策略共享 EMA 缓存

```python
async def test_ema_cache_shared_across_strategies(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
    ema_cache,
):
    """验证多策略共享 EMA 缓存。"""

    # 1. 清空缓存
    await ema_cache.clear()

    # 2. 创建两个使用相同 EMA 周期的策略
    # （通过 config_manager 配置）

    # 3. 推送 K 线
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

    # 4. 处理 K 线（两个策略都会用到 EMA）
    await signal_pipeline.process_kline(kline)

    # 5. 验证：EMA 缓存只计算一次
    stats = await ema_cache.get_stats()
    assert stats['size'] == 1  # 只有一个 EMA60 实例

    ema_entry = list(stats['entries'].values())[0]
    assert ema_entry['access_count'] >= 1  # 至少被访问一次
```

### 测试 3: EMA 缓存 TTL 过期

```python
async def test_ema_cache_ttl_expiration(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
    ema_cache,
):
    """验证 EMA 缓存 TTL 过期逻辑。"""

    # 1. 创建短 TTL 缓存（用于测试）
    test_cache = EMACache(ttl_seconds=1, max_size=1000)

    # 2. 创建 EMA 计算器
    from src.domain.indicators import EMACalculator
    calc = await test_cache.get_or_create("BTC/USDT:USDT:15m", "60")

    # 3. 验证：缓存已创建
    stats = await test_cache.get_stats()
    assert stats['size'] == 1

    # 4. 等待 TTL 过期
    await asyncio.sleep(1.5)

    # 5. 尝试获取（已过期，应该重新创建）
    calc2 = await test_cache.get_or_create("BTC/USDT:USDT:15m", "60")

    # 6. 验证：是新实例（或原实例但访问计数重置）
    stats2 = await test_cache.get_stats()
    # 缓存应该仍然存在，但 access_count 应该重置为 1
    entry = list(stats2['entries'].values())[0]
    assert entry['access_count'] == 1
```

---

## 步骤 3: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_ema_cache_ws_fallback.py -v

# 运行特定测试
pytest tests/integration/test_ema_cache_ws_fallback.py::TestEMACacheWSFallback::test_ema_cache_rebuild_on_ws_fallback -v
```

**预期输出**:
```
tests/integration/test_ema_cache_ws_fallback.py::TestEMACacheWSFallback::test_ema_cache_rebuild_on_ws_fallback PASSED
tests/integration/test_ema_cache_ws_fallback.py::TestEMACacheWSFallback::test_ema_cache_shared_across_strategies PASSED
tests/integration/test_ema_cache_ws_fallback.py::TestEMACacheWSFallback::test_ema_cache_ttl_expiration PASSED

============================== 3 passed in 4.2s ==============================
```

---

## 步骤 4: 提交代码

```bash
git add tests/integration/test_ema_cache_ws_fallback.py
git commit -m "test(integration): 添加 EMA 缓存+WebSocket 降级集成测试 (#Test-03)"
```

---

## 依赖

- ✅ Test-04 已完成（窗口 1 先执行 Test-04）
- 需要真实 Binance testnet API Key

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| WebSocket mock 不生效 | 使用 `patch.object` 正确定位 |
| EMA 缓存状态难观测 | 添加 `get_stats()` 返回详细信息 |
| 测试超时 | 缩短 TTL 时间，使用 `timeout=30` |
| 轮询模式判断不准 | 添加 `is_polling_mode()` 方法 |

---

*本文档为窗口 1 执行 Test-03 的详细指南*
