# 测试架构重构设计文档 (方案 C)

> **文档状态**: 待审核  
> **创建日期**: 2026-04-06  
> **负责人**: QA Tester + Architect  
> **审核人**: [待填写]

---

## 一、背景与目标

### 1.1 问题陈述

当前订单核心领域测试覆盖率不足：

| 模块 | 当前覆盖率 | 目标覆盖率 | 差距 |
|------|-----------|-----------|------|
| OrderManager | 75% | 95% | -20% |
| OrderRepository | 31% | 85% | -54% |

**主要原因**:
1. 测试代码重复度高，缺乏工厂模式
2. 缺少参数化测试，LONG/SHORT 方向只测了一边
3. 异常处理路径未覆盖
4. 依赖注入路径未测试
5. 目录结构扁平，缺乏分层组织

### 1.2 重构目标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| OrderManager 覆盖率 | 75% | 95% | +20% |
| OrderRepository 覆盖率 | 31% | 85% | +54% |
| 测试用例数量 | 19 | 35+ | +84% |
| SHORT 方向覆盖 | 0% | 100% | ✅ |
| 异常处理覆盖 | 部分 | 完整 | ✅ |
| 测试代码复用率 | 低 | 高 | ✅ |

---

## 二、已确认的架构决策

| 决策点 | 选择方案 | 理由 |
|--------|----------|------|
| 目录结构 | **选项 B** - 按领域重组 | 结构清晰，易于导航和维护 |
| Factory 模式 | 自定义工厂 | 无额外依赖，完全可控 |
| 数据库策略 | 每测试一个临时数据库 | 测试隔离，可检测事务相关 Bug |
| Mock 库 | 添加 `pytest-mock` | 语法简洁，自动清理 |

---

## 三、测试分层架构设计

### 3.1 目录结构

```
tests/
├── unit/                           # 单元测试层 (Mock 外部依赖)
│   ├── conftest.py                 # 全局 fixtures + factories
│   ├── domain/                     # 领域层测试
│   │   ├── test_order_state_machine.py
│   │   ├── test_order_manager.py
│   │   ├── test_order_strategy.py
│   │   └── test_models.py
│   ├── application/                # 应用层测试
│   │   ├── test_order_lifecycle_service.py
│   │   └── test_config_manager.py
│   ├── infrastructure/             # 基础设施层测试
│   │   ├── test_order_repository_unit.py
│   │   └── test_exchange_gateway.py
│   └── fixtures/                   # 可复用测试夹具
│       ├── order_factory.py
│       ├── position_factory.py
│       └── strategy_factory.py
│
├── integration/                    # 集成测试层 (真实数据库 + Mock 交易所)
│   ├── conftest.py                 # 集成测试 fixtures
│   └── order/
│       ├── test_order_repository_integration.py
│       ├── test_order_lifecycle_integration.py
│       └── test_order_audit_integration.py
│
└── e2e/                            # 端到端测试 (远端规划)
    └── order/
        └── test_order_full_chain.py
```

### 3.2 分层测试策略

| 层级 | 测试对象 | 依赖处理 | 执行速度 | 覆盖率目标 |
|------|----------|----------|----------|-----------|
| Unit | 单个类/函数 | Mock 所有外部依赖 | 快 (<1ms/测试) | 代码路径 95%+ |
| Integration | 模块间交互 | 真实数据库 + Mock 交易所 | 中 (<100ms/测试) | 集成点 100% |
| E2E | 完整业务流程 | 全链路 (可 Mock 交易所) | 慢 (<1s/测试) | 核心场景 100% |

---

## 四、工厂模式设计

### 4.1 OrderFactory

**文件**: `tests/unit/fixtures/order_factory.py`

```python
"""订单工厂 - 快速创建测试订单"""
from decimal import Decimal
import uuid
import itertools
from datetime import datetime, timezone

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction
)


class OrderFactory:
    """订单工厂
    
    注意：使用 itertools.count() 确保测试并发执行时计数器安全
    """
    
    _counter = itertools.count(1)  # 线程安全的递增计数器
    
    @classmethod
    def create(
        cls,
        role: OrderRole = OrderRole.ENTRY,
        status: OrderStatus = OrderStatus.OPEN,
        symbol: str = "BTC/USDT:USDT",
        direction: Direction = Direction.LONG,
        qty: Decimal = Decimal('1.0'),
        price: Decimal = Decimal('65000'),
        filled_qty: Decimal = Decimal('0'),
        **overrides
    ) -> Order:
        """
        创建订单，支持覆盖默认值
        
        Args:
            role: 订单角色
            status: 订单状态
            symbol: 交易对
            direction: 方向
            qty: 数量
            price: 价格
            filled_qty: 已成交数量
            **overrides: 其他覆盖字段
        
        Returns:
            Order 对象
        """
        counter_val = next(cls._counter)  # 线程安全获取下一个计数值
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        return Order(
            id=f"ord_test_{counter_val}_{uuid.uuid4().hex[:8]}",
            signal_id=f"sig_test_{counter_val}",
            symbol=symbol,
            direction=direction,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
            order_role=role,
            price=price,
            requested_qty=qty,
            filled_qty=filled_qty,
            status=status,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.SL],
            **overrides
        )
    
    @classmethod
    def entry_order(cls, **kwargs) -> Order:
        """快速创建 ENTRY 订单"""
        return cls.create(role=OrderRole.ENTRY, status=OrderStatus.CREATED, **kwargs)
    
    @classmethod
    def tp_order(cls, level: int = 1, **kwargs) -> Order:
        """快速创建 TP 订单"""
        role_map = {1: OrderRole.TP1, 2: OrderRole.TP2, 3: OrderRole.TP3}
        return cls.create(role=role_map.get(level, OrderRole.TP1), **kwargs)
    
    @classmethod
    def sl_order(cls, **kwargs) -> Order:
        """快速创建 SL 订单"""
        return cls.create(role=OrderRole.SL, **kwargs)
```

### 4.2 PositionFactory

**文件**: `tests/unit/fixtures/position_factory.py`

```python
"""仓位工厂"""
from decimal import Decimal
import uuid

from src.domain.models import Position, Direction


class PositionFactory:
    """仓位工厂"""
    
    @classmethod
    def create(
        cls,
        direction: Direction = Direction.LONG,
        entry_price: Decimal = Decimal('65000'),
        current_qty: Decimal = Decimal('1.0'),
        signal_id: str = None,
        **overrides
    ) -> Position:
        """创建仓位"""
        return Position(
            id=f"pos_test_{uuid.uuid4().hex[:8]}",
            signal_id=signal_id or f"sig_test_{uuid.uuid4().hex[:8]}",
            symbol="BTC/USDT:USDT",
            direction=direction,
            entry_price=entry_price,
            current_qty=current_qty,
            unrealized_pnl=Decimal('0'),
            **overrides
        )
    
    @classmethod
    def long_position(cls, **kwargs) -> Position:
        """快速创建 LONG 仓位"""
        return cls.create(direction=Direction.LONG, **kwargs)
    
    @classmethod
    def short_position(cls, **kwargs) -> Position:
        """快速创建 SHORT 仓位"""
        return cls.create(direction=Direction.SHORT, **kwargs)
```

### 4.3 SignalFactory

**文件**: `tests/unit/fixtures/signal_factory.py`

```python
"""信号工厂"""
from decimal import Decimal
import uuid

from src.domain.models import Signal, Direction


class SignalFactory:
    """信号工厂"""
    
    @classmethod
    def create(
        cls,
        signal_id: str = "sig-001",
        strategy_id: str = "pinbar",
        symbol: str = "BTC/USDT:USDT",
        direction: Direction = Direction.LONG,
        timestamp: int = 1711785600000,
        expected_entry: Decimal = Decimal('65000'),
        expected_sl: Decimal = Decimal('64000'),
        pattern_score: float = 0.85,
        **overrides
    ) -> Signal:
        """创建测试信号"""
        return Signal(
            id=signal_id,
            strategy_id=strategy_id,
            symbol=symbol,
            direction=direction,
            timestamp=timestamp,
            expected_entry=expected_entry,
            expected_sl=expected_sl,
            pattern_score=pattern_score,
            **overrides
        )
    
    @classmethod
    def long_signal(cls, **kwargs) -> Signal:
        """快速创建 LONG 信号"""
        return cls.create(direction=Direction.LONG, **kwargs)
    
    @classmethod
    def short_signal(cls, **kwargs) -> Signal:
        """快速创建 SHORT 信号"""
        return cls.create(direction=Direction.SHORT, **kwargs)
```

### 4.4 StrategyFactory

**文件**: `tests/unit/fixtures/strategy_factory.py`

```python
"""策略工厂"""
from decimal import Decimal
from typing import List, Optional

from src.domain.models import OrderStrategy


class StrategyFactory:
    """策略工厂"""
    
    @classmethod
    def single_tp(
        cls,
        strategy_id: str = "std-single-tp",
        name: str = "标准单 TP",
        tp_ratio: Decimal = Decimal('1.0'),
        tp_target: Decimal = Decimal('1.5'),
        sl_rr: Decimal = Decimal('-1.0'),
        **overrides
    ) -> OrderStrategy:
        """创建单 TP 策略"""
        return OrderStrategy(
            id=strategy_id,
            name=name,
            tp_levels=1,
            tp_ratios=[tp_ratio],
            tp_targets=[tp_target],
            initial_stop_loss_rr=sl_rr,
            trailing_stop_enabled=True,
            oco_enabled=True,
            **overrides
        )
    
    @classmethod
    def multi_tp(
        cls,
        strategy_id: str = "std-multi-tp",
        name: str = "多级别止盈",
        tp_levels: int = 3,
        tp_ratios: Optional[List[Decimal]] = None,
        tp_targets: Optional[List[Decimal]] = None,
        sl_rr: Decimal = Decimal('-1.0'),
        **overrides
    ) -> OrderStrategy:
        """创建多 TP 策略"""
        if tp_ratios is None:
            tp_ratios = [Decimal('0.5'), Decimal('0.3'), Decimal('0.2')]
        if tp_targets is None:
            tp_targets = [Decimal('1.5'), Decimal('2.0'), Decimal('3.0')]
        
        return OrderStrategy(
            id=strategy_id,
            name=name,
            tp_levels=tp_levels,
            tp_ratios=tp_ratios,
            tp_targets=tp_targets,
            initial_stop_loss_rr=sl_rr,
            trailing_stop_enabled=True,
            oco_enabled=True,
            **overrides
        )
```

### 4.5 使用示例

```python
# 旧方式 (重复代码多)
order = Order(
    id="ord_123",
    signal_id="sig_123",
    symbol="BTC/USDT:USDT",
    direction=Direction.LONG,
    ...  # 20+ 字段
)

# 新方式 (简洁，可读性强)
from tests.unit.fixtures.order_factory import OrderFactory

order = OrderFactory.entry_order(qty=Decimal('0.5'))
tp1 = OrderFactory.tp_order(level=1, price=Decimal('70000'))
sl = OrderFactory.sl_order(trigger_price=Decimal('63000'))

# 带覆盖
custom_order = OrderFactory.create(
    role=OrderRole.TP1,
    direction=Direction.SHORT,
    qty=Decimal('2.0'),
    price=Decimal('3500')
)
```

---

## 五、参数化测试设计

### 5.1 LONG/SHORT 方向覆盖

**计算公式说明**:
```
# 止损价格计算 (RR=-1.0 表示 1% 止损距离)
LONG:  sl_price = entry × (1 - 0.01)
SHORT: sl_price = entry × (1 + 0.01)

# 止盈价格计算 (RR=1.5 表示 1.5R 止盈)
LONG:  tp_price = entry + 1.5 × (entry - sl)
SHORT: tp_price = entry - 1.5 × (sl - entry)

# 本测试参数：entry_price=65000, sl_rr=-1.0 (1% 止损), tp_rr=1.5
# LONG:  sl = 65000 × 0.99 = 64350, tp = 65000 + 1.5 × (65000-64350) = 65975
# SHORT: sl = 65000 × 1.01 = 65650, tp = 65000 - 1.5 × (65650-65000) = 64025
```

```python
import pytest
from decimal import Decimal
from src.domain.models import Direction


@pytest.mark.parametrize("direction,expected_sl_price,expected_tp_price", [
    # entry=65000, sl_rr=-1.0 (1% 止损), tp_rr=1.5
    (Direction.LONG, Decimal('64350'), Decimal('65975')),    # LONG: SL 在下，TP 在上
    (Direction.SHORT, Decimal('65650'), Decimal('64025')),   # SHORT: SL 在上，TP 在下
])
def test_calculate_stop_loss_price(direction, expected_sl_price, expected_tp_price):
    """测试止损/止盈价格计算 - 覆盖 LONG 和 SHORT 方向"""
    manager = OrderManager()
    entry_price = Decimal('65000')
    
    sl_price = manager._calculate_stop_loss_price(entry_price, direction, Decimal('-1.0'))
    assert sl_price == expected_sl_price
```

### 5.2 多 TP 级别覆盖

```python
@pytest.mark.parametrize("tp_levels,tp_ratios,expected_qty", [
    (1, [Decimal('1.0')], [Decimal('1.0')]),           # 单 TP
    (2, [Decimal('0.5'), Decimal('0.5')], [Decimal('0.5'), Decimal('0.5')]),  # 双 TP
    (3, [Decimal('0.5'), Decimal('0.3'), Decimal('0.2')], [Decimal('0.5'), Decimal('0.3'), Decimal('0.2')]),  # 三 TP
])
def test_multi_tp_level_generation(tp_levels, tp_ratios, expected_qty):
    """测试多 TP 级别订单生成"""
    strategy = OrderStrategy(
        id="test_multi_tp",
        tp_levels=tp_levels,
        tp_ratios=tp_ratios,
    )
    # ... 测试逻辑
```

### 5.3 订单状态组合覆盖

```python
@pytest.mark.parametrize("entry_status,tp_status,sl_status,expected_action", [
    ("FILLED", "OPEN", "OPEN", "wait_for_tp_or_sl"),
    ("FILLED", "FILLED", "OPEN", "update_sl_qty"),
    ("FILLED", "OPEN", "FILLED", "cancel_remaining_tp"),
    ("FILLED", "CANCELED", "FILLED", "position_closed"),
])
def test_order_chain_status_combinations(entry_status, tp_status, sl_status, expected_action):
    """测试订单状态组合"""
    # ... 测试逻辑
```

---

## 六、Mock 策略设计

### 6.1 依赖注入模式

```python
# OrderManager 依赖注入
class OrderManager:
    def __init__(
        self,
        order_repository: Optional[Any] = None,
        order_lifecycle_service: Optional[Any] = None,
    ):
        self._order_repository = order_repository
        self._order_lifecycle_service = order_lifecycle_service
```

### 6.2 pytest-mock 使用

**安装**: 在 `requirements.txt` 中添加 `pytest-mock>=2.0.0`

```python
import pytest
from unittest.mock import AsyncMock

async def test_order_manager_with_mock_services(mocker):
    """使用 pytest-mock 测试 OrderManager"""
    # Mock 依赖
    mock_repository = mocker.AsyncMock(spec=OrderRepository)
    mock_lifecycle_service = mocker.AsyncMock(spec=OrderLifecycleService)
    
    # 创建 OrderManager
    manager = OrderManager(
        order_repository=mock_repository,
        order_lifecycle_service=mock_lifecycle_service
    )
    
    # 设置返回值
    mock_repository.save.return_value = None
    
    # 执行测试
    await manager.save_order_chain([order])
    
    # 验证调用
    mock_repository.save.assert_called_once_with(order)
```

### 6.3 Mock 对象规范

| 依赖 | Mock 方式 | Mock 方法 |
|------|----------|----------|
| ExchangeGateway | `mocker.AsyncMock()` | `cancel_order()`, `get_order_status()`, `submit_order()`, `fetch_balance()` |
| OrderAuditLogger | `mocker.AsyncMock()` | `log_event()`, `log_status_change()` |
| OrderLifecycleService | `mocker.AsyncMock()` | `cancel_order()`, `submit_order()`, `create_order()`, `confirm_order()` |
| OrderRepository | `mocker.AsyncMock()` (Unit) / 真实数据库 (Integration) | `save()`, `update_status()`, `get_order()`, `delete()`, `get_orders_by_signal()` |

**Mock 方法详细说明**:

| 模块 | 必须 Mock 的方法 | 可选 Mock 的方法 |
|------|----------------|----------------|
| OrderRepository | `save()`, `get_order()`, `update_status()`, `get_orders_by_signal()` | `delete()`, `get_by_symbol()`, `get_open_orders()` |
| ExchangeGateway | `cancel_order()`, `submit_order()` | `get_order_status()`, `fetch_balance()`, `start_asset_polling()` |
| OrderAuditLogger | `log_event()`, `log_status_change()` | 无 |
| OrderLifecycleService | `cancel_order()`, `submit_order()`, `create_order()` | `confirm_order()`, `update_order_filled()` |

---

## 七、数据库策略设计

### 7.1 临时数据库 Fixture

**文件**: `tests/integration/conftest.py`

```python
import pytest
import tempfile
import os

from src.infrastructure.order_repository import OrderRepository


@pytest.fixture
def temp_db_path():
    """创建临时数据库文件路径"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # 清理
    if os.path.exists(path):
        os.remove(path)
    # 清理 WAL 和 SHM 文件
    for ext in ['-wal', '-shm']:
        wal_path = path + ext
        if os.path.exists(wal_path):
            os.remove(wal_path)


@pytest_asyncio.fixture
async def order_repository(temp_db_path):
    """创建 OrderRepository 实例"""
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()
```

### 7.2 每测试一个临时数据库

```python
@pytest.mark.asyncio
async def test_save_order(order_repository):
    """测试保存订单 - 每个测试都有独立的数据库"""
    # order_repository 是每个测试的新实例
    # 数据库是临时创建的，测试后自动清理
    await order_repository.save(order)
    saved = await order_repository.get_order(order.id)
    assert saved is not None
```

**优点**:
- 测试完全隔离，无副作用
- 可检测事务相关 Bug
- 测试失败不影响其他测试

**缺点**:
- I/O 开销增加约 20-30%
- 测试时间稍长

---

## 八、实施路线图

### 8.1 任务分解与依赖关系

```
第 1 周
├── 阶段 1: 基础设施搭建 (1h)
│   ├── 1.1 添加 pytest-mock 依赖 ✓
│   ├── 1.2 创建 tests/unit/conftest.py ✓
│   ├── 1.3 创建 tests/unit/fixtures/ 目录 ✓
│   └── 1.4 创建工厂类 (OrderFactory, PositionFactory) ✓
│
├── 阶段 2: OrderManager 测试重构 (2-3h)
│   ├── 2.1 参数化测试覆盖 SHORT 方向
│   ├── 2.2 新增 6 个测试用例
│   └── 2.3 覆盖率目标：75% → 95%
│
├── 阶段 3: OrderRepository 测试重构 (3-4h)
│   ├── 3.1 创建单元测试文件
│   ├── 3.2 创建集成测试文件
│   ├── 3.3 新增 CRUD 操作测试
│   └── 3.4 覆盖率目标：31% → 85%
│
└── 阶段 4: 目录结构重组 (1h)
    ├── 4.1 创建按领域组织的子目录
    ├── 4.2 移动测试文件
    └── 4.3 更新导入路径

第 2 周
└── 阶段 5: 文档和收尾 (0.5h)
    ├── 5.1 更新 pytest_report.txt
    ├── 5.2 更新 progress.md
    └── 5.3 Git 提交并推送
```

### 8.2 并行执行簇

```
并行簇 1 (可同时进行):
├── 阶段 1: 基础设施搭建 (必须先完成)
│
├── 阶段 2: OrderManager 测试 ← 依赖阶段 1
│
├── 阶段 3: OrderRepository 测试 ← 依赖阶段 1

并行簇 2 (阶段 2 和 3 完成后可同时进行):
├── 阶段 4: 目录结构重组
└── 阶段 5: 文档收尾
```

### 8.3 详细任务清单

| 任务 ID | 任务名称 | 预计工时 | 依赖 | 负责人 |
|--------|----------|----------|------|--------|
| INFRA-1 | 添加 pytest-mock 到 requirements.txt | 0.25h | - | QA |
| INFRA-2 | 创建 tests/unit/conftest.py | 0.5h | - | QA |
| INFRA-3 | 创建 OrderFactory | 0.5h | INFRA-2 | QA |
| INFRA-4 | 创建 PositionFactory | 0.25h | INFRA-2 | QA |
| OM-1 | 参数化测试覆盖 SHORT 方向 | 0.5h | INFRA-4 | QA |
| OM-2 | 依赖注入 setter 测试 | 0.25h | INFRA-3 | QA |
| OM-3 | 异常处理路径测试 (3 个) | 0.75h | INFRA-3 | QA |
| OM-4 | TP ratios 归一化测试 | 0.25h | INFRA-3 | QA |
| OM-5 | OCO 完整路径测试 | 0.5h | INFRA-4 | QA |
| OM-6 | 覆盖率验证 (目标 95%) | 0.25h | OM-1~5 | QA |
| OR-1 | 创建 test_order_repository_unit.py | 0.25h | INFRA-2 | QA |
| OR-2 | 创建 test_order_repository_integration.py | 0.25h | INFRA-2 | QA |
| OR-3 | CRUD 操作测试 (save/update/delete) | 1h | OR-1 | QA |
| OR-4 | 依赖注入测试 | 0.5h | OR-1 | QA |
| OR-5 | 批量删除测试 | 0.5h | OR-2 | QA |
| OR-6 | 覆盖率验证 (目标 85%) | 0.5h | OR-3~5 | QA |
| REORG-1 | 创建 domain/ 子目录 | 0.25h | OM-6, OR-6 | QA |
| REORG-2 | 创建 application/ 子目录 | 0.25h | OM-6, OR-6 | QA |
| REORG-3 | 创建 infrastructure/ 子目录 | 0.25h | OM-6, OR-6 | QA |
| REORG-4 | 移动文件并更新导入 | 0.5h | REORG-1~3 | QA |
| DOC-1 | 更新 pytest_report.txt | 0.25h | REORG-4 | QA |
| DOC-2 | 更新 progress.md | 0.25h | DOC-1 | QA |

**预计总工时**: 18-22h（2-3 个工作日）

**工时评估说明**:
- OrderManager 从 75%→95%：需补充约 10-12 个测试用例，每个 0.5h，共 5-6h
- OrderRepository 从 31%→85%：需补充约 20-25 个测试用例，每个 0.5h，共 10-12h
- 目录重组：移动文件 + 更新导入路径，约需 1-2h（使用 IDE 重构功能）
- 回归测试和文档：约 2-3h

---

## 九、验收标准

### 9.1 覆盖率指标

| 模块 | 覆盖率目标 | 验证方式 |
|------|-----------|----------|
| OrderManager | ≥95% | `pytest --cov=src.domain.order_manager` |
| OrderRepository | ≥85% | `pytest --cov=src.infrastructure.order_repository` |
| OrderLifecycleService | 保持≥95% | 回归测试验证 |

### 9.2 测试用例数量

| 测试文件 | 当前用例数 | 目标用例数 | 新增 |
|----------|-----------|-----------|------|
| test_order_manager.py | 15 | 25+ | +10 |
| test_order_repository_unit.py | 0 | 15+ | +15 |
| test_order_repository_integration.py | 4 | 10+ | +6 |

### 9.3 代码质量要求

- [ ] 所有测试通过 `pytest tests/ -v` 验证
- [ ] 无 `any` 类型滥用 (TypeScript 前端测试)
- [ ] Mock 对象使用 `spec=` 参数确保接口一致性
- [ ] 测试代码 DRY (Don't Repeat Yourself)
- [ ] 测试名称清晰描述测试意图
- [ ] 每个测试文件有文档字符串说明测试范围

### 9.4 文档要求

- [ ] 更新 `docs/planning/progress.md`
- [ ] 更新 `docs/planning/task_plan.md`
- [ ] Git 提交信息清晰描述变更内容

---

## 十、回归测试策略

### 10.1 现有测试保护

在重构过程中，必须确保现有测试不受影响：

1. **重构前**: 运行完整测试套件，记录通过率基线
2. **重构中**: 每完成一个阶段，运行相关回归测试
3. **重构后**: 完整测试套件通过率必须 ≥ 100%

### 10.2 回归测试命令

```bash
# 阶段 1 完成后回归测试（基础设施）
pytest tests/unit/conftest.py --collect-only  # 验证 fixtures 可加载

# 阶段 2 完成后回归测试（OrderManager）
pytest tests/unit/domain/test_order_manager.py -v --tb=short

# 阶段 3 完成后回归测试（OrderRepository）
pytest tests/unit/infrastructure/test_order_repository_unit.py -v --tb=short
pytest tests/integration/order/test_order_repository_integration.py -v --tb=short

# 全部完成后回归测试（完整套件）
pytest tests/unit/ tests/integration/ -v --tb=short

# 覆盖率验证
pytest --cov=src/domain --cov=src/application --cov=src/infrastructure \
       --cov-report=term-missing --cov-fail-under=85
```

### 10.3 回归测试检查清单

```markdown
## 阶段 2 完成后（OrderManager）
- [ ] test_order_manager.py 所有测试通过
- [ ] OrderManager 覆盖率 ≥ 90%
- [ ] 无破坏性变更

## 阶段 3 完成后（OrderRepository）
- [ ] test_order_repository_unit.py 所有测试通过
- [ ] test_order_repository_integration.py 所有测试通过
- [ ] OrderRepository 覆盖率 ≥ 80%
- [ ] 无破坏性变更

## 阶段 4 完成后（目录重组）
- [ ] 所有测试文件导入正确
- [ ] pytest tests/ -v 全部通过
- [ ] 覆盖率报告生成成功

## 最终验收
- [ ] OrderManager 覆盖率 ≥ 95%
- [ ] OrderRepository 覆盖率 ≥ 85%
- [ ] 测试执行时间 < 60 秒
- [ ] Git 提交并推送
```

---

## 十一、风险与缓解

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| pytest-mock 与现有测试冲突 | 中 | 低 | 逐步迁移，保留旧测试兼容性 |
| 工厂模式过度抽象 | 低 | 中 | 保持简单，按需扩展 |
| 数据库 I/O 导致测试变慢 | 低 | 中 | 接受 20-30%  slowdown，保证测试隔离性 |
| 目录重组导致导入错误 | 中 | 中 | 使用 IDE 重构功能，批量更新导入 |

---

## 十二、审核记录

| 日期 | 审核人 | 审核结果 | 备注 |
|------|--------|----------|------|
| [待填写] | [用户] | ☐ 通过 ☐ 需修改 ☐ 拒绝 | |

---

*文档结束*
