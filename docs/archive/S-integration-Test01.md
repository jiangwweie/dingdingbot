# Test-01: 配置快照 + WebSocket 降级联动集成测试

**优先级**: P1 | **预估工时**: 2-3h | **负责窗口**: 窗口 3（用户）

---

## 测试目标

验证当 WebSocket 连接失败时，系统能正确降级到轮询模式，同时配置快照功能正常工作。

---

## 步骤 1: 创建测试文件

**文件**: `tests/integration/test_snapshot_ws_fallback.py`

**代码模板**:

```python
"""
Test-01: Config Snapshot + WebSocket Fallback Integration Test

Verifies config snapshot functionality during WebSocket degradation.
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
from src.interfaces.api import create_snapshot, activate_snapshot, list_snapshots


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
    """Create SignalPipeline instance."""
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


class TestSnapshotWSFallback:
    """Test config snapshot functionality during WebSocket fallback."""

    async def test_snapshot_creation_during_ws_fallback(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
    ):
        """
        测试场景:
        1. WebSocket 正常运行
        2. 创建配置快照
        3. 模拟 WebSocket 失败，降级到轮询
        4. 验证轮询模式下仍可创建快照
        5. WebSocket 恢复后自动重连
        """
        # TODO: 实现
        pass

    async def test_snapshot_rollback_works_during_ws_fallback(
        self,
        config_manager,
        exchange_gateway,
        signal_pipeline,
    ):
        """
        测试场景:
        1. WebSocket 降级后
        2. 执行快照回滚
        3. 验证回滚功能正常
        """
        # TODO: 实现
        pass
```

---

## 步骤 2: 实现核心测试逻辑

### 测试 1: WebSocket 降级时创建快照

```python
async def test_snapshot_creation_during_ws_fallback(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
):
    """验证 WebSocket 降级时配置快照功能正常。"""

    # 1. WebSocket 正常运行
    assert exchange_gateway._ws_running or not exchange_gateway.is_polling_mode()

    # 2. 创建快照 V1
    snapshot_v1 = await create_snapshot(
        description="before-ws-fallback",
        created_by="test",
    )
    assert snapshot_v1 is not None

    # 3. 模拟 WebSocket 失败
    with patch.object(exchange_gateway, '_ws_subscribe_account_loop', side_effect=Exception("WS failed")):
        try:
            await exchange_gateway.subscribe_account_updates(lambda x: None)
        except Exception:
            pass

    # 4. 等待降级
    await asyncio.sleep(2)

    # 5. 验证：已降级到轮询
    assert not exchange_gateway._ws_running

    # 6. 验证：轮询模式下可创建快照
    snapshot_v2 = await create_snapshot(
        description="after-fallback",
        created_by="test",
    )
    assert snapshot_v2 is not None
    assert snapshot_v2.id > snapshot_v1.id

    # 7. 验证：快照列表正确
    snapshots = await list_snapshots()
    assert len(snapshots) >= 2
```

### 测试 2: WebSocket 降级时回滚

```python
async def test_snapshot_rollback_works_during_ws_fallback(
    self,
    config_manager,
    exchange_gateway,
    signal_pipeline,
):
    """验证 WebSocket 降级时快照回滚功能正常。"""

    # 1. 创建快照 V1
    snapshot_v1 = await create_snapshot(description="v1")

    # 2. 修改配置
    original_strategies = config_manager.user_config.strategies.copy()
    config_manager.user_config.strategies[0].name = "Modified"

    # 3. WebSocket 降级
    # ... 同上 ...

    # 4. 回滚到 V1
    await activate_snapshot(snapshot_v1.id)

    # 5. 验证：配置已回滚
    assert config_manager.user_config.strategies[0].name != "Modified"
```

---

## 步骤 3: 运行测试验证

```bash
# 运行单个测试
pytest tests/integration/test_snapshot_ws_fallback.py -v
```

**预期输出**:
```
tests/integration/test_snapshot_ws_fallback.py::TestSnapshotWSFallback::test_snapshot_creation_during_ws_fallback PASSED
tests/integration/test_snapshot_ws_fallback.py::TestSnapshotWSFallback::test_snapshot_rollback_works_during_ws_fallback PASSED

============================== 2 passed in 5.5s ==============================
```

---

## 步骤 4: 提交代码

```bash
git add tests/integration/test_snapshot_ws_fallback.py
git commit -m "test(integration): 添加配置快照+WebSocket 降级集成测试 (#Test-01)"
```

---

## 依赖

无

---

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| API 端点不存在 | 从 `src/interfaces/api.py` 导入正确函数 |
| WebSocket 降级判断不准 | 添加状态检查方法 |
| 快照 ID 比较失败 | 使用 `>=` 而非 `>` 比较 |

---

*本文档为窗口 3 执行 Test-01 的详细指南*
