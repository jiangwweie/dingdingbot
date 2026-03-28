# Test-04: 快照回滚 + 信号状态连续性集成测试

**优先级**: P0 | **预估工时**: 3-4h | **负责窗口**: 窗口 1（Claude）

---

## 测试目标

验证配置快照回滚后，正在跟踪中的信号状态不中断、不丢失。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_snapshot_rollback_signal_continuity.py`

**步骤**:
1. 创建测试文件
2. 编写测试框架
3. 验证测试文件可导入

**代码模板**:

```python
"""
Test-04: Snapshot Rollback + Signal Continuity Integration Test

Verifies that signal status tracking remains intact after config snapshot rollback.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import List

from src.domain.models import (
    SignalStatus, SignalResult, StrategyDefinition, KlineData,
)
from src.application.config_manager import ConfigManager
from src.application.signal_pipeline import SignalPipeline
from src.application.signal_tracker import SignalStatusTracker
from src.infrastructure.signal_repository import SignalRepository
from src.interfaces.api import create_snapshot, activate_snapshot


@pytest.fixture
async def config_manager():
    """Create ConfigManager instance for testing."""
    # TODO: 实现 fixture


@pytest.fixture
async def signal_pipeline(config_manager):
    """Create SignalPipeline instance for testing."""
    # TODO: 实现 fixture


@pytest.fixture
async def signal_repository():
    """Create SignalRepository instance for testing."""
    # TODO: 实现 fixture


@pytest.fixture
async def status_tracker(signal_repository):
    """Create SignalStatusTracker instance for testing."""
    # TODO: 实现 fixture


class TestSnapshotRollbackSignalContinuity:
    """Test signal continuity after snapshot rollback."""

    async def test_signal_tracking_continues_after_rollback(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 策略 A 正在运行，生成信号 Signal-001（状态：GENERATED）
        2. 保存配置快照 V1
        3. 修改策略配置，生成信号 Signal-002（状态：GENERATED）
        4. 回滚到快照 V1（策略 A 恢复）
        5. 验证：Signal-001 和 Signal-002 的状态跟踪不中断
        6. 验证：更新信号状态时正确落盘
        """
        # TODO: 实现测试逻辑
        pass

    async def test_signal_status_update_works_after_rollback(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 回滚后，更新信号状态为 FILLED
        2. 验证状态正确保存
        """
        # TODO: 实现测试逻辑
        pass

    async def test_multiple_signals_tracked_independently_after_rollback(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 回滚前有多个信号在跟踪
        2. 回滚后所有信号独立跟踪，互不影响
        """
        # TODO: 实现测试逻辑
        pass
```

**验收**:
```bash
python -c "from tests.integration.test_snapshot_rollback_signal_continuity import *; print('OK')"
```

---

## 步骤 2: 实现 Test Fixtures

**目标**: 创建测试所需的 fixture

**代码**:

```python
@pytest.fixture
async def config_manager():
    """Create ConfigManager instance for testing."""
    from src.application.config_manager import load_all_configs
    config_manager = load_all_configs()
    yield config_manager


@pytest.fixture
async def signal_repository(tmp_path):
    """Create in-memory SignalRepository for testing."""
    # 使用 SQLite 内存模式加速测试
    from src.infrastructure.signal_repository import SignalRepository
    repository = SignalRepository(":memory:")
    await repository.initialize()
    yield repository
    await repository.close()


@pytest.fixture
async def status_tracker(signal_repository):
    """Create SignalStatusTracker instance."""
    from src.application.signal_tracker import SignalStatusTracker
    tracker = SignalStatusTracker(signal_repository)
    yield tracker


@pytest.fixture
async def signal_pipeline(config_manager, signal_repository, status_tracker):
    """Create SignalPipeline instance for testing."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_total_exposure=Decimal('0.8'),
    )

    notifier = NotificationService(
        enabled=False,  # 测试时禁用通知
        webhook_url=None,
    )

    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=notifier,
        signal_repository=signal_repository,
        cooldown_seconds=300,
    )

    yield pipeline

    # Cleanup
    await pipeline.close()
```

---

## 步骤 3: 实现核心测试逻辑

### 测试 1: 信号跟踪连续性

```python
async def test_signal_tracking_continues_after_rollback(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
):
    """验证回滚后信号跟踪不中断。"""

    # 1. 创建测试 K 线数据
    from src.domain.models import KlineData
    kline1 = KlineData(
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

    # 2. 处理 K 线，生成信号 1
    signal1 = await signal_pipeline.process_kline(kline1)
    assert signal1 is not None

    # 3. 验证：信号 1 状态为 GENERATED
    track1 = await status_tracker.get_signal_status(signal1.id)
    assert track1.status == SignalStatus.GENERATED

    # 4. 保存快照 V1
    from src.interfaces.api import create_snapshot
    snapshot_v1 = await create_snapshot(
        description="rollback-point",
        created_by="test",
    )
    assert snapshot_v1 is not None

    # 5. 修改策略配置（模拟用户操作）
    # 临时修改 user_config 中的策略
    original_strategies = config_manager.user_config.strategies.copy()
    modified_strategy = original_strategies[0].copy()
    modified_strategy.name = "Modified-策略"
    config_manager.user_config.strategies[0] = modified_strategy

    # 6. 处理 K 线 2，生成信号 2（使用修改后的配置）
    kline2 = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000 + 900000,  # 15 分钟后
        open=Decimal('50100'),
        high=Decimal('50200'),
        low=Decimal('50000'),
        close=Decimal('50150'),
        volume=Decimal('1000'),
        is_closed=True,
    )
    signal2 = await signal_pipeline.process_kline(kline2)
    assert signal2 is not None

    # 7. 回滚到快照 V1
    from src.interfaces.api import activate_snapshot
    await activate_snapshot(snapshot_v1.id)

    # 8. 验证：信号 1 仍在跟踪中
    track1_after = await status_tracker.get_signal_status(signal1.id)
    assert track1_after.status == SignalStatus.GENERATED

    # 9. 验证：信号 2 仍在跟踪中
    track2_after = await status_tracker.get_signal_status(signal2.id)
    assert track2_after.status == SignalStatus.GENERATED
```

### 测试 2: 状态更新正确性

```python
async def test_signal_status_update_works_after_rollback(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
):
    """验证回滚后状态更新正确。"""

    # ... 前置步骤同上 ...

    # 回滚后
    await activate_snapshot(snapshot_v1.id)

    # 更新信号 1 状态为 FILLED
    await status_tracker.update_status(
        signal1.id,
        SignalStatus.FILLED,
        filled_price=Decimal('51000'),
    )

    # 验证状态正确保存
    track1_filled = await status_tracker.get_signal_status(signal1.id)
    assert track1_filled.status == SignalStatus.FILLED
    assert track1_filled.filled_price == Decimal('51000')
    assert track1_filled.filled_at is not None
```

### 测试 3: 多信号独立跟踪

```python
async def test_multiple_signals_tracked_independently_after_rollback(
    self,
    config_manager,
    signal_pipeline,
    signal_repository,
    status_tracker,
):
    """验证回滚后多信号独立跟踪。"""

    # ... 前置步骤同上 ...

    # 回滚后
    await activate_snapshot(snapshot_v1.id)

    # 更新信号 1 状态为 FILLED
    await status_tracker.update_status(
        signal1.id,
        SignalStatus.FILLED,
        filled_price=Decimal('51000'),
    )

    # 更新信号 2 状态为 CANCELLED
    await status_tracker.update_status(
        signal2.id,
        SignalStatus.CANCELLED,
        cancel_reason="测试取消",
    )

    # 验证：信号 1 状态为 FILLED
    track1 = await status_tracker.get_signal_status(signal1.id)
    assert track1.status == SignalStatus.FILLED

    # 验证：信号 2 状态为 CANCELLED
    track2 = await status_tracker.get_signal_status(signal2.id)
    assert track2.status == SignalStatus.CANCELLED

    # 验证：两个信号状态互不影响
    assert track1.filled_price != track2.filled_price  # 只有 signal1 有成交价
```

---

## 步骤 4: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_snapshot_rollback_signal_continuity.py -v

# 运行特定测试类
pytest tests/integration/test_snapshot_rollback_signal_continuity.py::TestSnapshotRollbackSignalContinuity -v
```

**预期输出**:
```
tests/integration/test_snapshot_rollback_signal_continuity.py::TestSnapshotRollbackSignalContinuity::test_signal_tracking_continues_after_rollback PASSED
tests/integration/test_snapshot_rollback_signal_continuity.py::TestSnapshotRollbackSignalContinuity::test_signal_status_update_works_after_rollback PASSED
tests/integration/test_snapshot_rollback_signal_continuity.py::TestSnapshotRollbackSignalContinuity::test_multiple_signals_tracked_independently_after_rollback PASSED

============================== 3 passed in 2.5s ==============================
```

---

## 步骤 5: 提交代码

```bash
git add tests/integration/test_snapshot_rollback_signal_continuity.py
git commit -m "test(integration): 添加快照回滚 + 信号连续性集成测试 (#Test-04)"
```

---

## 完成后

1. 更新 `docs/tasks/S-integration-overview.md` 中的状态
2. 通知窗口 2 和窗口 3 Test-04 已完成
3. 继续执行 Test-03

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| Fixture 无法创建 | 检查 imports 是否正确 |
| 测试超时 | 增加 `@pytest.mark.asyncio(timeout=30)` |
| 信号 ID 重复 | 确保使用 UUID 生成器 |
| 回滚不生效 | 检查 `activate_snapshot()` 实现 |

---

*本文档为窗口 1 执行 Test-04 的详细指南*
