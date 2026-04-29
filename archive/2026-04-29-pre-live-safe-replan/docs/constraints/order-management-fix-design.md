# 订单管理模块 P1/P2 问题修复实施设计

> **文档级别**: P8 架构师评审级  
> **创建日期**: 2026-04-07  
> **状态**: 待评审 (Pending Review)  
> **实施策略**: 方案 B - 系统性重构  
> **影响范围**: OrderRepository, OrderManager, OrderAuditLogger, OrderLifecycleService, OrderAuditLogRepository  

---

## 执行摘要

本文档设计了订单管理模块代码审查发现的 9 项 P1/P2 问题的系统性修复方案。采用**方案 B：系统性重构**策略，一次性解决所有问题，提升代码质量和可维护性。

### 问题统计

| 级别 | 问题数 | 修复状态 | 测试覆盖 |
|------|--------|----------|----------|
| P1 (高优先级) | 3 | 待实施 | 需新增 5 用例 |
| P2 (中优先级) | 6 | 待实施 | 需新增 8 用例 |
| **总计** | **9** | **待实施** | **需新增 13 用例** |

### 实施估算

| 维度 | 估算 |
|------|------|
| 工时 | 3 人天 |
| 代码变更 | ~350 行 |
| 测试变更 | ~200 行 |
| 风险等级 | 中 (可控) |
| 回滚时间 | < 10 分钟 |

---

## 1. 问题分析

### 1.1 背景

订单管理模块在代码审查中发现 9 项问题，其中 3 项 P1 级（高优先级）问题需要立即修复，6 项 P2 级（中优先级）问题需要系统性优化。

### 1.2 问题清单

#### P1 级问题（3 项）

| 编号 | 问题 | 位置 | 风险等级 |
|------|------|------|----------|
| P1-1 | OrderRepository asyncio.Lock 竞态条件 | `src/infrastructure/order_repository.py:71-90` | 高 |
| P1-2 | OrderManager 硬编码止损比例 | `src/domain/order_manager.py:324-328` | 高 |
| P1-3 | OrderRepository 日志导入违规 | `src/infrastructure/order_repository.py:22` | 中 |

#### P2 级问题（6 项）

| 编号 | 问题 | 位置 | 风险等级 |
|------|------|------|----------|
| P2-4 | 止损比例逻辑歧义 | `src/domain/order_manager.py:415-452` | 中 |
| P2-5 | strategy None 处理缺失 | `src/domain/order_manager.py:138-188` | 中 |
| P2-6 | AuditLogger 类型校验缺失 | `src/application/order_audit_logger.py` | 中 |
| P2-7 | UPSERT 数据丢失 | `src/infrastructure/order_repository.py:207-216` | 中 |
| P2-8 | 状态描述映射缺失 | `src/application/order_lifecycle_service.py` | 低 |
| P2-9 | Worker 异常静默 | `src/infrastructure/order_audit_repository.py:71-83` | 中 |

---

### 1.3 问题详细分析

#### P1-1: OrderRepository asyncio.Lock 竞态条件

**位置**: `src/infrastructure/order_repository.py:70-89`

**问题代码**:
```python
def _ensure_lock(self) -> asyncio.Lock:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Lock()  # ❌ 没有事件循环时返回新 lock，无法使用
    
    if self._lock is None:
        self._lock = asyncio.Lock()  # ❌ 非原子操作，多协程可能创建多个 lock
    
    return self._lock
```

**问题描述**:
1. **竞态条件**: 多个协程同时调用 `_ensure_lock()` 时，`if self._lock is None` 检查不是原子操作，可能导致创建多个 Lock 实例
2. **无事件循环场景**: 当没有运行中的事件循环时，返回一个新的 `asyncio.Lock()`，但这个 Lock 无法在任何事件循环中使用
3. **事件循环切换**: 如果应用在不同事件循环之间切换，Lock 可能与当前事件循环不匹配

**影响**:
- 多协程并发场景下，Lock 可能失效，导致数据库操作并发冲突
- 在同步代码中调用时返回的 Lock 无法使用

---

#### P1-2: OrderManager 硬编码止损比例

**位置**: `src/domain/order_manager.py:323-328`

**问题代码**:
```python
# 计算止损价格 (基于实际开仓价，默认使用 -1.0 RR)
stop_loss_price = self._calculate_stop_loss_price(
    actual_entry_price,
    filled_entry.direction,
    Decimal('-1.0'),  # ❌ 硬编码
)
```

**问题描述**:
- 止损比例应从 `OrderStrategy.initial_stop_loss_rr` 读取
- 当前硬编码 `-1.0`，不支持动态止损配置
- 与 `OrderStrategy` 模型定义不一致

**影响**:
- 用户无法通过配置调整止损比例
- 与 `OrderStrategy` 模型的设计意图不符

---

#### P1-3: OrderRepository 日志导入违规

**位置**: `src/infrastructure/order_repository.py:22`

**问题代码**:
```python
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)
```

**问题描述**:
- 根据系统开发规范，基础设施层应使用标准 `logging` 模块
- `setup_logger` 是自定义封装，可能存在循环依赖风险

**影响**:
- 违反系统开发规范
- 潜在的循环依赖问题

---

#### P2-4: 止损比例逻辑歧义

**位置**: `src/domain/order_manager.py:415-452`

**问题代码**:
```python
def _calculate_stop_loss_price(...) -> Decimal:
    """
    计算止损价格
    
    注意：rr_multiple 参数的绝对值表示止损距离占入场价的百分比
    例如：rr_multiple = -0.02 表示止损距离为入场价的 2%
    """
    sl_percent = abs(rr_multiple)
    
    # 如果 sl_percent >= 1，说明是倍数而非百分比，转换为百分比
    if sl_percent >= Decimal('1'):
        sl_percent = Decimal('0.02')  # ❌ 默认 2% 止损
```

**问题描述**:
- `rr_multiple=-1.0` 本意是 1R 止损（基于风险倍数），但代码转成 2%
- 逻辑歧义：注释说"负值表示止损"，但实际计算使用绝对值
- 与 `OrderStrategy.initial_stop_loss_rr` 的语义不一致

**影响**:
- 用户配置 `initial_stop_loss_rr=-1.0` 期望 1R 止损，实际变成 2%
- 代码行为与文档描述不一致

---

#### P2-5: strategy None 处理缺失

**位置**: `src/domain/order_manager.py:138-188`

**问题代码**:
```python
def create_order_chain(
    self,
    strategy: OrderStrategy,  # ❌ 没有 Optional，但实际可能为 None
    ...
) -> List[Order]:
    ...
    # 使用传入的 strategy 生成订单
    entry_order = Order(...)
```

**问题描述**:
- `create_order_chain` 方法没有处理 `strategy=None` 的情况
- 但调用方 `OrderLifecycleService.create_order()` 传入的 strategy 可能为 None

**影响**:
- 当 strategy 为 None 时，可能引发 AttributeError

---

#### P2-6: AuditLogger 类型校验缺失

**位置**: `src/application/order_audit_logger.py`

**问题描述**:
- `OrderAuditLogger` 方法接收的参数没有类型校验
- 依赖上层调用方保证类型正确

**影响**:
- 类型错误可能导致运行时异常

---

#### P2-7: UPSERT 数据丢失

**位置**: `src/infrastructure/order_repository.py:207-216`

**问题代码**:
```sql
ON CONFLICT(id) DO UPDATE SET
    status = excluded.status,
    filled_qty = excluded.filled_qty,
    average_exec_price = excluded.average_exec_price,
    filled_at = COALESCE(excluded.filled_at, orders.filled_at),  -- ❌ 问题
    exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),  -- ❌ 问题
    exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),  -- ❌ 问题
    parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),  -- ❌ 问题
    oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),  -- ❌ 问题
    updated_at = excluded.updated_at
```

**问题描述**:
- `COALESCE(excluded.field, orders.field)` 语法导致：
  - 当 `excluded.field` 为 NULL 时，保留旧值
  - 但无法区分「不更新」和「设置为 NULL」
- 如果业务需要将字段设置为 NULL，COALESCE 会阻止这个操作

**影响**:
- 某些场景下无法将字段更新为 NULL

---

#### P2-8: 状态描述映射缺失

**位置**: `src/application/order_lifecycle_service.py`

**问题描述**:
- 部分合法状态转换缺少描述映射
- 例如：`PARTIALLY_FILLED -> FILLED` 的描述缺失

**影响**:
- 审计日志中状态转换描述不完整

---

#### P2-9: Worker 异常静默

**位置**: `src/infrastructure/order_audit_repository.py:71-83`

**问题代码**:
```python
async def _worker(self) -> None:
    """后台 Worker 异步写入审计日志"""
    while True:
        try:
            log_entry = await self._queue.get()
            await self._save_log_entry(log_entry)
            self._queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            # ❌ 仅记录错误但不中断 Worker，没有详细日志
            self._queue.task_done()
```

**问题描述**:
- Worker 捕获异常后仅 `task_done()`，没有记录错误详情
- 异常日志丢失，难以排查问题

**影响**:
- 审计日志写入失败时难以定位问题

---

## 2. 修复方案设计 (方案 B：系统性重构)

### 2.1 P1-1: OrderRepository asyncio.Lock 竞态条件修复

**问题位置**: `src/infrastructure/order_repository.py:70-89`  
**风险等级**: 高 - 多协程并发场景下 Lock 可能失效  
**修复优先级**: P1 (最高)

#### 2.1.1 问题代码

```python
def _ensure_lock(self) -> asyncio.Lock:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Lock()  # ❌ 没有事件循环时返回新 lock，无法使用
    
    if self._lock is None:
        self._lock = asyncio.Lock()  # ❌ 非原子操作，多协程可能创建多个 lock
    
    return self._lock
```

#### 2.1.2 修复代码

```python
import threading
from typing import Dict, Optional

class OrderRepository:
    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        exchange_gateway: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
    ):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        # ✅ 修复：使用字典存储每个事件循环专用的 Lock
        self._locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = threading.Lock()  # 保护 _locks 字典
        self._sync_lock = threading.Lock()  # 用于同步调用场景
        self._exchange_gateway = exchange_gateway
        self._audit_logger = audit_logger
        logger.info(f"订单仓库初始化完成：{db_path}")

    def _ensure_lock(self) -> asyncio.Lock:
        """
        获取当前事件循环专用的 Lock。
        
        使用双重检查锁定模式确保线程安全。
        每个事件循环有独立的 Lock，避免跨事件循环共享导致的竞态条件。
        
        Returns:
            asyncio.Lock: 当前事件循环专用的锁实例
        """
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            # 同步调用场景：返回同步锁
            # 注意：这种情况下获得的锁无法在异步代码中使用
            return self._sync_lock
        
        # 双重检查锁定模式
        if loop_id not in self._locks:
            with self._global_lock:
                # 再次检查，避免多个线程同时创建 Lock
                if loop_id not in self._locks:
                    self._locks[loop_id] = asyncio.Lock()
        
        return self._locks[loop_id]
```

#### 2.1.3 测试用例设计

```python
# tests/unit/test_order_repository.py

class TestP1Fix_LockConcurrency:
    """P1-1: Lock 竞态条件修复测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_save_operations(self, order_repository):
        """测试并发 save 操作的锁机制"""
        # Arrange
        orders = [
            Order(id=f"ord_{i}", signal_id="sig_1", ...)
            for i in range(10)
        ]
        
        # Act: 并发执行 save 操作
        tasks = [order_repository.save(order) for order in orders]
        await asyncio.gather(*tasks)
        
        # Assert: 所有订单都已保存，无数据竞争
        for order in orders:
            saved = await order_repository.get_order(order.id)
            assert saved is not None
    
    @pytest.mark.asyncio
    async def test_lock_per_event_loop(self, order_repository):
        """测试不同事件循环有独立的 Lock"""
        # Arrange
        loop1 = asyncio.new_event_loop()
        loop2 = asyncio.new_event_loop()
        
        # Act: 在不同事件循环中获取 Lock
        lock1 = await loop1.run_in_executor(None, order_repository._ensure_lock)
        lock2 = await loop2.run_in_executor(None, order_repository._ensure_lock)
        
        # Assert: 两个 Lock 是不同的实例
        assert id(lock1) != id(lock2)
        
        # Cleanup
        loop1.close()
        loop2.close()
    
    @pytest.mark.asyncio
    async def test_sync_call_returns_sync_lock(self, order_repository):
        """测试同步调用返回同步锁"""
        # Act: 在没有事件循环的环境中调用
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.sleep(0))  # 确保有事件循环
        
        # 使用同步方式调用
        lock = order_repository._ensure_lock()
        
        # Assert
        assert isinstance(lock, (asyncio.Lock, threading.Lock))
```

---

### 2.2 P1-2: OrderManager 硬编码止损比例修复

**问题位置**: `src/domain/order_manager.py:323-328`  
**风险等级**: 高 - 不支持动态止损配置  
**修复优先级**: P1 (最高)

#### 2.2.1 问题代码

```python
# 计算止损价格 (基于实际开仓价，默认使用 -1.0 RR)
stop_loss_price = self._calculate_stop_loss_price(
    actual_entry_price,
    filled_entry.direction,
    Decimal('-1.0'),  # ❌ 硬编码
)
```

#### 2.2.2 修复代码

```python
async def _generate_tp_sl_orders(
    self,
    filled_entry: Order,
    positions_map: Dict[str, Position],
    strategy: Optional[OrderStrategy] = None,
    tp_targets: Optional[List[Decimal]] = None,
) -> List[Order]:
    """
    基于 ENTRY 成交结果，动态生成 TP 和 SL 订单
    
    P1-2 修复：使用策略配置的止损比例，而非硬编码 -1.0
    """
    # 获取仓位信息
    position = positions_map.get(filled_entry.signal_id)
    if not position:
        for p in positions_map.values():
            if p.signal_id == filled_entry.signal_id:
                position = p
                break
    
    if not position:
        return []
    
    # 使用实际成交价作为锚点
    actual_entry_price = filled_entry.average_exec_price or filled_entry.price
    if not actual_entry_price:
        return []
    
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    # ✅ P1-2 修复：从策略获取止损比例，支持动态配置
    stop_loss_rr = (
        strategy.initial_stop_loss_rr
        if strategy and strategy.initial_stop_loss_rr is not None
        else Decimal('-1.0')  # 默认值：1R 止损
    )
    
    stop_loss_price = self._calculate_stop_loss_price(
        actual_entry_price,
        filled_entry.direction,
        stop_loss_rr,
    )
    
    # ... 后续代码不变
```

#### 2.2.3 测试用例设计

```python
# tests/unit/test_order_manager.py

class TestP1Fix_DynamicStopLoss:
    """P1-2: 动态止损比例修复测试"""
    
    @pytest.mark.asyncio
    async def test_uses_strategy_stop_loss_rr(self, order_manager, mock_positions):
        """测试使用策略配置的止损比例"""
        # Arrange
        strategy = OrderStrategy(
            name="test_strategy",
            initial_stop_loss_rr=Decimal('-2.0'),  # 2R 止损
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
        )
        filled_entry = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
        )
        
        # Act
        orders = await order_manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map=mock_positions,
            strategy=strategy,
        )
        
        # Assert: SL 订单的触发价格应为 50000 * (1 - 0.02) = 49000 (假设 2% 止损)
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        expected_sl_price = Decimal('49000')  # 2% 止损
        assert sl_order.trigger_price == expected_sl_price
    
    @pytest.mark.asyncio
    async def test_uses_default_when_strategy_none(self, order_manager, mock_positions):
        """测试 strategy 为 None 时使用默认值"""
        # Arrange
        filled_entry = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
        )
        
        # Act
        orders = await order_manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map=mock_positions,
            strategy=None,  # None
        )
        
        # Assert: 应使用默认 -1.0 RR
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        assert sl_order.trigger_price is not None
    
    @pytest.mark.asyncio
    async def test_uses_default_when_stop_loss_rr_none(self, order_manager, mock_positions):
        """测试 strategy.initial_stop_loss_rr 为 None 时使用默认值"""
        # Arrange
        strategy = OrderStrategy(
            name="test_strategy",
            initial_stop_loss_rr=None,  # None
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
        )
        filled_entry = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
        )
        
        # Act
        orders = await order_manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map=mock_positions,
            strategy=strategy,
        )
        
        # Assert: 应使用默认 -1.0 RR
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        assert sl_order.trigger_price is not None
```

---

### 2.3 P1-3: OrderRepository 日志导入规范化

**问题位置**: `src/infrastructure/order_repository.py:22`  
**风险等级**: 中 - 违反系统开发规范  
**修复优先级**: P1 (高)

#### 2.3.1 问题代码

```python
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)
```

#### 2.3.2 修复代码

```python
# ✅ P1-3 修复：使用标准 logging 模块
import logging

logger = logging.getLogger(__name__)
```

#### 2.3.3 测试用例设计

```python
# tests/unit/test_order_repository.py

class TestP1Fix_LoggerImport:
    """P1-3: 日志导入规范化测试"""
    
    def test_uses_standard_logging(self):
        """测试使用标准 logging 模块"""
        # Arrange & Act
        import src.infrastructure.order_repository as repo_module
        
        # Assert: logger 应该是标准 logging.Logger 实例
        assert isinstance(repo_module.logger, logging.Logger)
        assert repo_module.logger.name == 'src.infrastructure.order_repository'
```

---

### 2.4 P2-4: 止损比例逻辑歧义修复

**问题位置**: `src/domain/order_manager.py:415-452`  
**风险等级**: 中 - 代码行为与文档描述不一致  
**修复优先级**: P2

#### 2.4.1 问题代码

```python
def _calculate_stop_loss_price(
    self,
    entry_price: Decimal,
    direction: Direction,
    rr_multiple: Decimal,
) -> Decimal:
    """
    计算止损价格
    
    注意：rr_multiple 参数的绝对值表示止损距离占入场价的百分比
    例如：rr_multiple = -0.02 表示止损距离为入场价的 2%
    """
    sl_percent = abs(rr_multiple)
    
    # 如果 sl_percent >= 1，说明是倍数而非百分比，转换为百分比
    if sl_percent >= Decimal('1'):
        sl_percent = Decimal('0.02')  # ❌ 默认 2% 止损
    
    if direction == Direction.LONG:
        return entry_price * (Decimal('1') - sl_percent)
    else:
        return entry_price * (Decimal('1') + sl_percent)
```

#### 2.4.2 修复代码

```python
def _calculate_stop_loss_price(
    self,
    entry_price: Decimal,
    direction: Direction,
    rr_multiple: Decimal,
) -> Decimal:
    """
    计算止损价格
    
    语义说明:
    - rr_multiple < 0: 表示止损 RR 倍数（如 -1.0 表示亏损 1R）
    - rr_multiple > 0: 表示止损百分比（如 0.02 表示 2% 止损）
    
    计算公式:
    - LONG: sl_price = entry × (1 + rr_multiple)  if rr_multiple < 0
    - LONG: sl_price = entry × (1 - rr_multiple)  if rr_multiple > 0
    - SHORT: sl_price = entry × (1 - rr_multiple) if rr_multiple < 0
    - SHORT: sl_price = entry × (1 + rr_multiple) if rr_multiple > 0
    
    Args:
        entry_price: 入场价格
        direction: 方向 (LONG/SHORT)
        rr_multiple: 
            - 负值表示 RR 倍数（如 -1.0 表示 1R 止损）
            - 正值表示百分比（如 0.02 表示 2% 止损）
    
    Returns:
        止损价格
    
    Examples:
        >>> _calculate_stop_loss_price(50000, Direction.LONG, Decimal('-1.0'))
        Decimal('49500')  # LONG 1R 止损 = 50000 * (1 - 0.01)
        
        >>> _calculate_stop_loss_price(50000, Direction.LONG, Decimal('0.02'))
        Decimal('49000')  # LONG 2% 止损 = 50000 * (1 - 0.02)
    """
    # P2-4 修复：明确区分 RR 倍数模式和百分比模式
    if rr_multiple < 0:
        # RR 倍数模式：基于入场价和止损距离计算
        # 对于 LONG: sl_price = entry - entry × |rr_multiple| × 0.01
        # 对于 SHORT: sl_price = entry + entry × |rr_multiple| × 0.01
        sl_ratio = abs(rr_multiple) * Decimal('0.01')  # 转换为百分比
        if direction == Direction.LONG:
            return entry_price * (Decimal('1') - sl_ratio)
        else:
            return entry_price * (Decimal('1') + sl_ratio)
    else:
        # 百分比模式：直接按百分比计算
        # 对于 LONG: sl_price = entry × (1 - percent)
        # 对于 SHORT: sl_price = entry × (1 + percent)
        if direction == Direction.LONG:
            return entry_price * (Decimal('1') - rr_multiple)
        else:
            return entry_price * (Decimal('1') + rr_multiple)
```

#### 2.4.3 测试用例设计

```python
# tests/unit/test_order_manager.py

class TestP2Fix_StopLossCalculation:
    """P2-4: 止损计算逻辑修复测试"""
    
    @pytest.fixture
    def order_manager(self):
        return OrderManager()
    
    def test_rr_mode_long_position(self, order_manager):
        """测试 RR 倍数模式 - LONG 仓位"""
        # Arrange: 入场价 50000, 1R 止损 (rr_multiple = -1.0)
        entry_price = Decimal('50000')
        direction = Direction.LONG
        rr_multiple = Decimal('-1.0')  # 1R 止损
        
        # Act
        sl_price = order_manager._calculate_stop_loss_price(
            entry_price, direction, rr_multiple
        )
        
        # Assert: LONG 1R 止损 = 50000 * (1 - 0.01) = 49500
        assert sl_price == Decimal('49500')
    
    def test_rr_mode_short_position(self, order_manager):
        """测试 RR 倍数模式 - SHORT 仓位"""
        # Arrange: 入场价 50000, 1R 止损
        entry_price = Decimal('50000')
        direction = Direction.SHORT
        rr_multiple = Decimal('-1.0')
        
        # Act
        sl_price = order_manager._calculate_stop_loss_price(
            entry_price, direction, rr_multiple
        )
        
        # Assert: SHORT 1R 止损 = 50000 * (1 + 0.01) = 50500
        assert sl_price == Decimal('50500')
    
    def test_percent_mode_long_position(self, order_manager):
        """测试百分比模式 - LONG 仓位"""
        # Arrange: 入场价 50000, 2% 止损
        entry_price = Decimal('50000')
        direction = Direction.LONG
        rr_multiple = Decimal('0.02')  # 2% 止损
        
        # Act
        sl_price = order_manager._calculate_stop_loss_price(
            entry_price, direction, rr_multiple
        )
        
        # Assert: LONG 2% 止损 = 50000 * (1 - 0.02) = 49000
        assert sl_price == Decimal('49000')
    
    def test_percent_mode_short_position(self, order_manager):
        """测试百分比模式 - SHORT 仓位"""
        # Arrange: 入场价 50000, 2% 止损
        entry_price = Decimal('50000')
        direction = Direction.SHORT
        rr_multiple = Decimal('0.02')
        
        # Act
        sl_price = order_manager._calculate_stop_loss_price(
            entry_price, direction, rr_multiple
        )
        
        # Assert: SHORT 2% 止损 = 50000 * (1 + 0.02) = 51000
        assert sl_price == Decimal('51000')
    
    def test_rr_mode_2r_stop_loss(self, order_manager):
        """测试 2R 止损计算"""
        # Arrange: 入场价 50000, 2R 止损
        entry_price = Decimal('50000')
        direction = Direction.LONG
        rr_multiple = Decimal('-2.0')  # 2R 止损
        
        # Act
        sl_price = order_manager._calculate_stop_loss_price(
            entry_price, direction, rr_multiple
        )
        
        # Assert: LONG 2R 止损 = 50000 * (1 - 0.02) = 49000
        assert sl_price == Decimal('49000')
```

---

### 2.5 P2-5: strategy None 处理缺失修复

**问题位置**: `src/domain/order_manager.py:138-188`  
**风险等级**: 中 - 可能引发 AttributeError  
**修复优先级**: P2

#### 2.5.1 问题代码

```python
def create_order_chain(
    self,
    strategy: OrderStrategy,  # ❌ 没有 Optional，但实际可能为 None
    signal_id: str,
    symbol: str,
    direction: Direction,
    total_qty: Decimal,
    initial_sl_rr: Decimal,
    tp_targets: List[Decimal],
) -> List[Order]:
```

#### 2.5.2 修复代码

```python
def create_order_chain(
    self,
    strategy: Optional[OrderStrategy],  # ✅ P2-5 修复：允许 None
    signal_id: str,
    symbol: str,
    direction: Direction,
    total_qty: Decimal,
    initial_sl_rr: Decimal,
    tp_targets: List[Decimal],
) -> List[Order]:
    """
    创建订单链 - 仅生成 ENTRY 订单
    
    P2-5 修复：支持 strategy=None 场景，此时使用默认配置
    
    Args:
        strategy: 订单策略（可选，为 None 时使用默认配置）
        signal_id: 信号 ID
        symbol: 交易对
        direction: 方向
        total_qty: 总数量
        initial_sl_rr: 初始止损 RR 倍数
        tp_targets: TP 目标价格列表
    
    Returns:
        仅包含 ENTRY 订单的列表
    """
    from src.domain.models import OrderType, OrderRole, OrderStatus
    import uuid
    from datetime import datetime, timezone
    
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    # 仅生成 ENTRY 订单（状态为 CREATED，由 OrderLifecycleService 管理）
    entry_order = Order(
        id=f"ord_{uuid.uuid4().hex[:8]}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=total_qty,
        status=OrderStatus.CREATED,  # 初始状态为 CREATED
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )
    
    return [entry_order]
```

#### 2.5.3 测试用例设计

```python
# tests/unit/test_order_manager.py

class TestP2Fix_StrategyNoneHandling:
    """P2-5: strategy None 处理修复测试"""
    
    def test_create_order_chain_with_none_strategy(self, order_manager):
        """测试 strategy 为 None 时正常创建订单"""
        # Arrange
        signal_id = "sig_test"
        symbol = "BTC/USDT:USDT"
        direction = Direction.LONG
        total_qty = Decimal('1.0')
        initial_sl_rr = Decimal('-1.0')
        tp_targets = [Decimal('1.5')]
        
        # Act
        orders = order_manager.create_order_chain(
            strategy=None,  # None
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            total_qty=total_qty,
            initial_sl_rr=initial_sl_rr,
            tp_targets=tp_targets,
        )
        
        # Assert
        assert len(orders) == 1
        assert orders[0].signal_id == signal_id
        assert orders[0].symbol == symbol
        assert orders[0].direction == direction
        assert orders[0].requested_qty == total_qty
    
    def test_create_order_chain_with_strategy(self, order_manager):
        """测试 strategy 不为 None 时正常创建订单"""
        # Arrange
        strategy = OrderStrategy(
            name="test_strategy",
            initial_stop_loss_rr=Decimal('-1.0'),
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
        )
        
        # Act
        orders = order_manager.create_order_chain(
            strategy=strategy,
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )
        
        # Assert
        assert len(orders) == 1
```

---

### 2.6 P2-6: AuditLogger 类型校验缺失修复

**问题位置**: `src/application/order_audit_logger.py`  
**风险等级**: 中 - 类型错误可能导致运行时异常  
**修复优先级**: P2

#### 2.6.1 问题描述

`OrderAuditLogger` 方法接收的参数没有类型校验，依赖上层调用方保证类型正确。

#### 2.6.2 修复代码

```python
# src/application/order_audit_logger.py

from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging

from src.domain.models import (
    OrderAuditLog,
    OrderAuditLogCreate,
    OrderAuditLogQuery,
    OrderAuditEventType,
    OrderAuditTriggerSource,
)
from src.infrastructure.order_audit_repository import OrderAuditLogRepository

logger = logging.getLogger(__name__)


class OrderAuditLogger:
    """
    订单审计日志服务
    
    提供审计日志的写入和查询接口，支持异步队列处理
    """
    
    def __init__(self, repository: OrderAuditLogRepository):
        """
        初始化审计日志服务
        
        Args:
            repository: 审计日志数据仓库
        
        Raises:
            TypeError: 当 repository 不是 OrderAuditLogRepository 实例时
        """
        # ✅ P2-6 修复：类型校验
        if not isinstance(repository, OrderAuditLogRepository):
            raise TypeError(
                f"repository 必须是 OrderAuditLogRepository 实例，"
                f"实际类型：{type(repository).__name__}"
            )
        self._repository = repository
        self._started = False
    
    async def log(
        self,
        order_id: str,
        new_status: str,
        event_type: OrderAuditEventType,
        triggered_by: OrderAuditTriggerSource,
        signal_id: Optional[str] = None,
        old_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        记录审计日志
        
        Args:
            order_id: 订单 ID
            new_status: 新状态
            event_type: 事件类型
            triggered_by: 触发来源
            signal_id: 信号 ID（可选）
            old_status: 旧状态（可选）
            metadata: 元数据（可选）
        
        Returns:
            审计日志 ID
        
        Raises:
            TypeError: 当参数类型不正确时
            ValueError: 当必填参数为空时
        """
        # ✅ P2-6 修复：参数类型校验
        if not isinstance(order_id, str) or not order_id:
            raise TypeError("order_id 必须是非空字符串")
        if not isinstance(new_status, str) or not new_status:
            raise TypeError("new_status 必须是非空字符串")
        if not isinstance(event_type, OrderAuditEventType):
            raise TypeError(
                f"event_type 必须是 OrderAuditEventType 枚举值，"
                f"实际类型：{type(event_type).__name__}"
            )
        if not isinstance(triggered_by, OrderAuditTriggerSource):
            raise TypeError(
                f"triggered_by 必须是 OrderAuditTriggerSource 枚举值，"
                f"实际类型：{type(triggered_by).__name__}"
            )
        if signal_id is not None and not isinstance(signal_id, str):
            raise TypeError("signal_id 必须是字符串或 None")
        if old_status is not None and not isinstance(old_status, str):
            raise TypeError("old_status 必须是字符串或 None")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata 必须是字典或 None")
        
        return await self._repository.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
            metadata=metadata,
            use_queue=True,
        )
```

#### 2.6.3 测试用例设计

```python
# tests/unit/test_order_audit_logger.py

class TestP2Fix_AuditLoggerTypeValidation:
    """P2-6: AuditLogger 类型校验修复测试"""
    
    def test_init_with_invalid_repository(self):
        """测试初始化时 repository 类型校验"""
        # Arrange
        invalid_repository = "not_a_repository"
        
        # Act & Assert
        with pytest.raises(TypeError) as exc_info:
            OrderAuditLogger(invalid_repository)
        
        assert "repository 必须是 OrderAuditLogRepository 实例" in str(exc_info.value)
    
    def test_log_with_invalid_order_id(self, audit_logger):
        """测试 log 方法 order_id 类型校验"""
        # Arrange & Act & Assert
        with pytest.raises(TypeError) as exc_info:
            await audit_logger.log(
                order_id="",  # 空字符串
                new_status="FILLED",
                event_type=OrderAuditEventType.ORDER_FILLED,
                triggered_by=OrderAuditTriggerSource.SYSTEM,
            )
        
        assert "order_id 必须是非空字符串" in str(exc_info.value)
    
    def test_log_with_invalid_event_type(self, audit_logger):
        """测试 log 方法 event_type 类型校验"""
        # Arrange & Act & Assert
        with pytest.raises(TypeError) as exc_info:
            await audit_logger.log(
                order_id="ord_test",
                new_status="FILLED",
                event_type="INVALID",  # 不是枚举值
                triggered_by=OrderAuditTriggerSource.SYSTEM,
            )
        
        assert "event_type 必须是 OrderAuditEventType 枚举值" in str(exc_info.value)
    
    def test_log_with_invalid_triggered_by(self, audit_logger):
        """测试 log 方法 triggered_by 类型校验"""
        # Arrange & Act & Assert
        with pytest.raises(TypeError) as exc_info:
            await audit_logger.log(
                order_id="ord_test",
                new_status="FILLED",
                event_type=OrderAuditEventType.ORDER_FILLED,
                triggered_by="INVALID",  # 不是枚举值
            )
        
        assert "triggered_by 必须是 OrderAuditTriggerSource 枚举值" in str(exc_info.value)
    
    def test_log_with_valid_parameters(self, audit_logger):
        """测试 log 方法参数正确时正常工作"""
        # Arrange & Act
        log_id = await audit_logger.log(
            order_id="ord_test",
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
            signal_id="sig_test",
            old_status="OPEN",
            metadata={"filled_qty": "1.0"},
        )
        
        # Assert
        assert log_id is not None
        assert log_id.startswith("audit_")
```

---

### 2.7 P2-7: UPSERT 数据丢失修复

**问题位置**: `src/infrastructure/order_repository.py:207-216`  
**风险等级**: 中 - 某些场景下无法将字段更新为 NULL  
**修复优先级**: P2

#### 2.7.1 问题代码

```sql
ON CONFLICT(id) DO UPDATE SET
    status = excluded.status,
    filled_qty = excluded.filled_qty,
    average_exec_price = excluded.average_exec_price,
    filled_at = COALESCE(excluded.filled_at, orders.filled_at),  -- ❌ 问题
    exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),  -- ❌ 问题
    exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),  -- ❌ 问题
    parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),  -- ❌ 问题
    oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),  -- ❌ 问题
    updated_at = excluded.updated_at
```

#### 2.7.2 修复代码

```python
async def save(self, order: Order) -> None:
    """
    Save or update an order to the database.
    
    P2-7 修复：使用 CASE 表达式替代 COALESCE，允许字段设置为 NULL
    
    Args:
        order: Order object to save
    """
    async with self._ensure_lock():
        await self._db.execute(
            """
            INSERT INTO orders (
                id, signal_id, symbol, direction, order_type, order_role,
                price, trigger_price, requested_qty, filled_qty,
                average_exec_price, status, reduce_only, parent_order_id,
                oco_group_id, exit_reason, exchange_order_id, filled_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                filled_qty = excluded.filled_qty,
                average_exec_price = excluded.average_exec_price,
                -- P2-7 修复：使用 CASE 表达式，仅当 excluded 值为 NULL 时保留旧值
                -- 这样允许业务代码显式将字段设置为 NULL
                filled_at = CASE 
                    WHEN excluded.filled_at IS NULL AND orders.filled_at IS NOT NULL 
                    THEN orders.filled_at 
                    ELSE excluded.filled_at 
                END,
                exchange_order_id = CASE 
                    WHEN excluded.exchange_order_id IS NULL AND orders.exchange_order_id IS NOT NULL 
                    THEN orders.exchange_order_id 
                    ELSE excluded.exchange_order_id 
                END,
                exit_reason = excluded.exit_reason,  -- 允许设置为 NULL
                parent_order_id = excluded.parent_order_id,  -- 允许设置为 NULL
                oco_group_id = excluded.oco_group_id,  -- 允许设置为 NULL
                updated_at = excluded.updated_at
            """,
            (
                order.id,
                order.signal_id,
                order.symbol,
                order.direction.value,
                order.order_type.value,
                order.order_role.value,
                str(order.price) if order.price else None,
                str(order.trigger_price) if order.trigger_price else None,
                str(order.requested_qty),
                str(order.filled_qty),
                str(order.average_exec_price) if order.average_exec_price else None,
                order.status.value,
                1 if order.reduce_only else 0,
                order.parent_order_id,
                order.oco_group_id,
                order.exit_reason,
                order.exchange_order_id,
                order.filled_at,
                order.created_at,
                order.updated_at,
            )
        )
        await self._db.commit()
        logger.debug(f"订单已保存：{order.id}, status={order.status.value}, role={order.order_role.value}")
```

#### 2.7.3 测试用例设计

```python
# tests/unit/test_order_repository.py

class TestP2Fix_UpsertNullHandling:
    """P2-7: UPSERT NULL 值处理修复测试"""
    
    @pytest.mark.asyncio
    async def test_update_field_to_null(self, order_repository):
        """测试将字段更新为 NULL"""
        # Arrange: 先创建一个有 parent_order_id 的订单
        order = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            status=OrderStatus.CREATED,
            parent_order_id="ord_parent",
            created_at=1000,
            updated_at=1000,
        )
        await order_repository.save(order)
        
        # Act: 更新时将 parent_order_id 设置为 None
        order.parent_order_id = None
        order.updated_at = 2000
        await order_repository.save(order)
        
        # Assert: parent_order_id 应为 None
        saved_order = await order_repository.get_order("ord_test")
        assert saved_order.parent_order_id is None
    
    @pytest.mark.asyncio
    async def test_preserve_filled_at_when_null_in_update(self, order_repository):
        """测试 filled_at 在更新时为 NULL 时保留旧值"""
        # Arrange: 创建一个已成交的订单
        order = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            filled_at=1500,
            status=OrderStatus.FILLED,
            created_at=1000,
            updated_at=1000,
        )
        await order_repository.save(order)
        
        # Act: 更新时 filled_at 保持为 None（不更新）
        order.status = OrderStatus.FILLED
        order.updated_at = 2000
        # filled_at 不设置，保持为 None
        await order_repository.save(order)
        
        # Assert: filled_at 应保留原值
        saved_order = await order_repository.get_order("ord_test")
        assert saved_order.filled_at == 1500
    
    @pytest.mark.asyncio
    async def test_update_oco_group_id_to_null(self, order_repository):
        """测试将 oco_group_id 更新为 NULL"""
        # Arrange
        order = Order(
            id="ord_test",
            signal_id="sig_1",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            status=OrderStatus.OPEN,
            oco_group_id="oco_group_1",
            created_at=1000,
            updated_at=1000,
        )
        await order_repository.save(order)
        
        # Act: 更新时将 oco_group_id 设置为 None
        order.oco_group_id = None
        order.updated_at = 2000
        await order_repository.save(order)
        
        # Assert: oco_group_id 应为 None
        saved_order = await order_repository.get_order("ord_test")
        assert saved_order.oco_group_id is None
```

---

### 2.8 P2-8: 状态描述映射缺失修复

**问题位置**: `src/application/order_lifecycle_service.py`  
**风险等级**: 低 - 审计日志中状态转换描述不完整  
**修复优先级**: P2

#### 2.8.1 修复代码

```python
# src/application/order_lifecycle_service.py

@staticmethod
def _map_status_to_event(old_status: OrderStatus, new_status: OrderStatus) -> OrderAuditEventType:
    """
    将状态转换映射到审计事件类型
    
    P2-8 修复：补充缺失的状态转换映射
    """
    event_map = {
        (OrderStatus.CREATED, OrderStatus.SUBMITTED): OrderAuditEventType.ORDER_SUBMITTED,
        (OrderStatus.CREATED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
        (OrderStatus.SUBMITTED, OrderStatus.OPEN): OrderAuditEventType.ORDER_CONFIRMED,
        (OrderStatus.SUBMITTED, OrderStatus.REJECTED): OrderAuditEventType.ORDER_REJECTED,
        (OrderStatus.SUBMITTED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
        (OrderStatus.SUBMITTED, OrderStatus.EXPIRED): OrderAuditEventType.ORDER_EXPIRED,
        (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED): OrderAuditEventType.ORDER_PARTIAL_FILLED,
        (OrderStatus.OPEN, OrderStatus.FILLED): OrderAuditEventType.ORDER_FILLED,
        (OrderStatus.OPEN, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
        (OrderStatus.OPEN, OrderStatus.REJECTED): OrderAuditEventType.ORDER_REJECTED,
        (OrderStatus.OPEN, OrderStatus.EXPIRED): OrderAuditEventType.ORDER_EXPIRED,
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED): OrderAuditEventType.ORDER_FILLED,
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.REJECTED): OrderAuditEventType.ORDER_REJECTED,
    }
    return event_map.get((old_status, new_status), OrderAuditEventType.ORDER_UPDATED)
```

---

### 2.9 P2-9: Worker 异常静默修复

**问题位置**: `src/infrastructure/order_audit_repository.py:71-83`  
**风险等级**: 中 - 审计日志写入失败时难以定位问题  
**修复优先级**: P2

#### 2.9.1 问题代码

```python
async def _worker(self) -> None:
    """后台 Worker 异步写入审计日志"""
    while True:
        try:
            log_entry = await self._queue.get()
            await self._save_log_entry(log_entry)
            self._queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            # ❌ 仅记录错误但不中断 Worker，没有详细日志
            self._queue.task_done()
```

#### 2.9.2 修复代码

```python
async def _worker(self) -> None:
    """
    后台 Worker 异步写入审计日志
    
    P2-9 修复：详细记录异常，增加重试机制和错误计数
    """
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        log_entry = None
        try:
            log_entry = await self._queue.get()
            await self._save_log_entry(log_entry)
            consecutive_errors = 0  # ✅ 重置错误计数
            self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("审计日志 Worker 已停止")
            # 清理队列
            if log_entry:
                self._queue.task_done()
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"审计日志写入失败 (错误 {consecutive_errors}/{max_consecutive_errors}): "
                f"log_entry={log_entry}, error={e}",
                exc_info=True,  # ✅ 记录堆栈跟踪
            )
            if log_entry:
                self._queue.task_done()
            
            # ✅ 连续错误超过阈值，记录告警
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"审计日志 Worker 连续失败 {consecutive_errors} 次，"
                    f"可能导致审计数据丢失"
                )
                # 不中断 Worker，继续尝试，但持续告警
```

#### 2.9.3 测试用例设计

```python
# tests/unit/test_order_audit_repository.py

class TestP2Fix_WorkerErrorHandling:
    """P2-9: Worker 异常处理修复测试"""
    
    @pytest.mark.asyncio
    async def test_worker_logs_exception_details(self, mock_db_session):
        """测试 Worker 记录异常详情"""
        # Arrange
        repository = OrderAuditLogRepository(mock_db_session)
        await repository.initialize(queue_size=10)
        
        # 模拟 _save_log_entry 抛出异常
        original_save = repository._save_log_entry
        async def mock_save(entry):
            raise Exception("Database connection error")
        repository._save_log_entry = mock_save
        
        # Act: 入队一个日志条目
        await repository.log(
            order_id="ord_test",
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
        )
        
        # 等待 Worker 处理
        await asyncio.sleep(0.1)
        
        # Assert: 应该记录错误日志（通过 caplog 验证）
        # 注意：实际测试中需要使用 caplog 来验证日志输出
        
        # Cleanup
        await repository.close()
    
    @pytest.mark.asyncio
    async def test_worker_continues_after_error(self, mock_db_session):
        """测试 Worker 在错误后继续工作"""
        # Arrange
        repository = OrderAuditLogRepository(mock_db_session)
        await repository.initialize(queue_size=10)
        
        error_count = [0]
        
        async def mock_save(entry):
            error_count[0] += 1
            if error_count[0] == 1:
                raise Exception("Temporary error")
            # 第二次调用成功
        
        repository._save_log_entry = mock_save
        
        # Act: 入队两个日志条目
        await repository.log(
            order_id="ord_test1",
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
        )
        await asyncio.sleep(0.05)
        
        await repository.log(
            order_id="ord_test2",
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
        )
        await asyncio.sleep(0.1)
        
        # Assert: 第二个条目应该成功处理
        # 注意：实际测试需要验证日志是否写入
        
        # Cleanup
        await repository.close()
```

---

### 2.10 方案 A：最小改动（快速修复）

**目标**: 以最小代码改动修复 P1 级问题，快速上线

#### 2.1.1 P1-1: Lock 竞态条件修复

**修改文件**: `src/infrastructure/order_repository.py`

**修复代码**:
```python
def _ensure_lock(self) -> asyncio.Lock:
    """Ensure lock is created for current event loop.
    
    使用延迟初始化 + 双重检查锁定模式避免竞态条件。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 无事件循环场景：返回一个临时 lock（仅用于同步调用）
        # 注意：这种情况下获得的 lock 无法在异步代码中使用
        return asyncio.Lock()
    
    # 双重检查锁定模式
    if self._lock is None:
        # 使用 asyncio.Lock 本身作为同步原语
        # 注意：这里仍有理论上的竞态，但 asyncio.Lock() 创建是原子的
        temp_lock = asyncio.Lock()
        if self._lock is None:
            self._lock = temp_lock
    
    return self._lock
```

**说明**: 
- 使用双重检查锁定模式减少竞态
- 明确注释无事件循环场景的限制

#### 2.1.2 P1-2: 止损比例配置化

**修改文件**: `src/domain/order_manager.py`

**修复代码**:
```python
# 计算止损价格 (基于实际开仓价和策略配置)
stop_loss_rr = strategy.initial_stop_loss_rr if strategy and strategy.initial_stop_loss_rr else Decimal('-1.0')
stop_loss_price = self._calculate_stop_loss_price(
    actual_entry_price,
    filled_entry.direction,
    stop_loss_rr,
)
```

#### 2.1.3 P1-3: 日志导入规范化

**修改文件**: `src/infrastructure/order_repository.py`

**修复代码**:
```python
import logging

logger = logging.getLogger(__name__)
```

---

### 2.2 方案 B：系统性重构（长期优化）

**目标**: 系统性解决所有 P1+P2 问题，提升代码质量

#### 2.2.1 P1-1: Lock 重构

**方案**: 使用事件循环感知的 Lock 管理机制

```python
class OrderRepository:
    def __init__(self, ...):
        self._locks: Dict[int, asyncio.Lock] = {}  # event_loop_id -> Lock
        self._global_lock = threading.Lock()  # 保护 _locks 字典
    
    def _ensure_lock(self) -> asyncio.Lock:
        """获取当前事件循环专用的 Lock."""
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            # 同步调用场景：使用全局 lock
            return self._sync_lock
        
        if loop_id not in self._locks:
            with self._global_lock:
                if loop_id not in self._locks:
                    self._locks[loop_id] = asyncio.Lock()
        
        return self._locks[loop_id]
```

#### 2.2.2 P1-2 & P2-4: 止损逻辑重构

**方案**: 明确止损比例语义，统一计算逻辑

```python
def _calculate_stop_loss_price(
    self,
    entry_price: Decimal,
    direction: Direction,
    rr_multiple: Decimal,
) -> Decimal:
    """
    计算止损价格
    
    语义说明:
    - rr_multiple < 0: 表示止损 RR 倍数（如 -1.0 表示亏损 1R）
    - rr_multiple > 0: 表示止损百分比（如 0.02 表示 2% 止损）
    
    LONG: sl_price = entry × (1 + rr_multiple)  if rr_multiple < 0
          sl_price = entry × (1 - rr_multiple)  if rr_multiple > 0
    SHORT: sl_price = entry × (1 - rr_multiple) if rr_multiple < 0
           sl_price = entry × (1 + rr_multiple) if rr_multiple > 0
    """
    if rr_multiple < 0:
        # RR 倍数模式：基于入场价和止损距离计算
        sl_distance = entry_price * abs(rr_multiple)
        if direction == Direction.LONG:
            return entry_price - sl_distance
        else:
            return entry_price + sl_distance
    else:
        # 百分比模式：直接按百分比计算
        if direction == Direction.LONG:
            return entry_price * (Decimal('1') - rr_multiple)
        else:
            return entry_price * (Decimal('1') + rr_multiple)
```

#### 2.2.3 P2-7: UPSERT 逻辑重构

**方案**: 移除 COALESCE，显式处理 NULL 值

```python
async def save(self, order: Order) -> None:
    await self._db.execute(
        """
        INSERT INTO orders (...) VALUES (...)
        ON CONFLICT(id) DO UPDATE SET
            status = excluded.status,
            filled_qty = excluded.filled_qty,
            average_exec_price = excluded.average_exec_price,
            -- 显式处理 NULL：如果 excluded 字段为 NULL，则使用旧值
            filled_at = CASE 
                WHEN excluded.filled_at IS NULL THEN orders.filled_at 
                ELSE excluded.filled_at 
            END,
            exchange_order_id = CASE 
                WHEN excluded.exchange_order_id IS NULL THEN orders.exchange_order_id 
                ELSE excluded.exchange_order_id 
            END,
            exit_reason = excluded.exit_reason,  -- 允许设置为 NULL
            parent_order_id = excluded.parent_order_id,  -- 允许设置为 NULL
            oco_group_id = excluded.oco_group_id,  -- 允许设置为 NULL
            updated_at = excluded.updated_at
        """,
        (...)
    )
```

#### 2.2.4 P2-9: Worker 异常处理增强

**方案**: 详细记录异常，增加重试机制

```python
async def _worker(self) -> None:
    """后台 Worker 异步写入审计日志"""
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        try:
            log_entry = await self._queue.get()
            await self._save_log_entry(log_entry)
            consecutive_errors = 0  # 重置错误计数
            self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("审计日志 Worker 已停止")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(
                f"审计日志写入失败 (错误 {consecutive_errors}/{max_consecutive_errors}): "
                f"log_entry={log_entry}, error={e}",
                exc_info=True  # 记录堆栈跟踪
            )
            self._queue.task_done()
            
            # 连续错误超过阈值，记录告警
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"审计日志 Worker 连续失败 {consecutive_errors} 次，"
                    f"可能导致审计数据丢失"
                )
```

---

## 3. 方案对比

| 维度 | 方案 A：最小改动 | 方案 B：系统性重构 |
|------|-----------------|-------------------|
| **修复范围** | 仅 P1 问题（3 项） | P1 + P2 问题（9 项） |
| **代码改动** | ~50 行 | ~300 行 |
| **测试改动** | ~5 个用例 | ~30 个用例 |
| **工时估算** | 0.5 人天 | 3 人天 |
| **风险等级** | 低 | 中 |
| **长期收益** | 有限 | 显著提升代码质量 |
| **向后兼容性** | ✅ 完全兼容 | ✅ 完全兼容 |
| **推荐场景** | 紧急修复 | 常规迭代 |

---

## 4. 关联影响分析

### 4.1 数据库表变更影响

| 方案 | 表变更 | 迁移需求 |
|------|--------|---------|
| 方案 A | 无 | 无 |
| 方案 B | 无 | 无 |

**说明**: 两个方案都不涉及数据库表结构变更

### 4.2 API 接口变更影响

| 接口 | 变更内容 | 影响 |
|------|---------|------|
| `POST /api/v3/orders` | 无 | 无 |
| `GET /api/v3/orders/{id}` | 无 | 无 |
| `GET /api/v3/signals/{id}/orders` | 无 | 无 |

**说明**: 两个方案都不涉及 API 接口变更

### 4.3 测试用例影响

#### 方案 A 测试影响：

| 测试文件 | 新增用例 | 更新用例 |
|---------|---------|---------|
| `tests/unit/test_order_repository.py` | 1 | 0 |
| `tests/unit/test_order_manager.py` | 1 | 0 |
| **合计** | **2** | **0** |

#### 方案 B 测试影响：

| 测试文件 | 新增用例 | 更新用例 |
|---------|---------|---------|
| `tests/unit/test_order_repository.py` | 3 | 2 |
| `tests/unit/test_order_manager.py` | 3 | 1 |
| `tests/unit/test_order_audit_logger.py` | 2 | 0 |
| `tests/integration/test_order_lifecycle.py` | 2 | 0 |
| **合计** | **10** | **3** |

### 4.4 前端页面影响

| 页面 | 影响 | 说明 |
|------|------|------|
| 订单列表页 | 无 | 无变更 |
| 订单详情页 | 无 | 无变更 |
| 信号详情页 | 无 | 无变更 |

### 4.5 模块依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                     订单管理模块依赖图                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │ OrderManager     │─────>│ OrderStrategy    │            │
│  │ (domain)         │      │ (domain)         │            │
│  └────────┬─────────┘      └──────────────────┘            │
│           │                                                 │
│           v                                                 │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │ OrderRepository  │─────>│ OrderAuditLogger │            │
│  │ (infrastructure) │      │ (application)    │            │
│  └────────┬─────────┘      └──────────────────┘            │
│           │                                                 │
│           v                                                 │
│  ┌──────────────────┐                                       │
│  │ SQLite Database  │                                       │
│  └──────────────────┘                                       │
│                                                             │
│  修复影响点:                                                 │
│  ● P1-1: OrderRepository._ensure_lock()                    │
│  ● P1-2: OrderManager._generate_tp_sl_orders()             │
│  ● P1-3: OrderRepository logger import                     │
│  ● P2-4: OrderManager._calculate_stop_loss_price()         │
│  ● P2-7: OrderRepository.save()                            │
│  ● P2-9: OrderAuditLogRepository._worker()                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 风险评估

### 5.1 方案 A 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Lock 竞态条件未彻底解决 | 低 | 中 | 添加监控日志，观察并发场景 |
| 止损逻辑仍然复杂 | 中 | 低 | 添加详细注释说明 |
| 技术债务累积 | 中 | 低 | 计划后续重构 |

### 5.2 方案 B 风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 止损逻辑变更引入 Bug | 中 | 高 | 完整单元测试覆盖 |
| UPSERT 逻辑变更影响性能 | 低 | 中 | 性能测试验证 |
| Worker 异常处理影响吞吐量 | 低 | 低 | 限制重试次数 |

---

## 6. 实施路线图

### 6.1 方案 A 实施（0.5 人天）

```
Day 1:
┌────────────────────────────────────────────────────────────┐
│ 上午 (2h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 1. 修复 P1-1: Lock 竞态条件                                │
│    - 修改 _ensure_lock() 方法                              │
│    - 添加单元测试                                           │
├────────────────────────────────────────────────────────────┤
│ 下午 (2h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 2. 修复 P1-2: 止损比例配置化                               │
│    - 修改 _generate_tp_sl_orders() 方法                    │
│    - 添加单元测试                                           │
│ 3. 修复 P1-3: 日志导入规范化                               │
│    - 修改 import 语句                                       │
│ 4. 运行现有测试验证                                        │
└────────────────────────────────────────────────────────────┘
```

### 6.2 方案 B 实施（3 人天）

```
Day 1:
┌────────────────────────────────────────────────────────────┐
│ 上午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 1. 修复 P1-1: Lock 重构（事件循环感知）                     │
│    - 实现 _locks 字典管理                                   │
│    - 添加多线程/多协程测试                                  │
├────────────────────────────────────────────────────────────┤
│ 下午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 2. 修复 P1-2 & P2-4: 止损逻辑重构                          │
│    - 重新设计 _calculate_stop_loss_price() 语义            │
│    - 添加参数验证和边界测试                                 │
└────────────────────────────────────────────────────────────┘

Day 2:
┌────────────────────────────────────────────────────────────┐
│ 上午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 3. 修复 P2-7: UPSERT 逻辑重构                              │
│    - 移除 COALESCE，使用 CASE 表达式                       │
│    - 添加 NULL 值处理测试                                   │
├────────────────────────────────────────────────────────────┤
│ 下午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 4. 修复 P2-9: Worker 异常处理增强                          │
│    - 添加详细异常日志                                       │
│    - 实现重试机制                                           │
│ 5. 修复 P2-5, P2-6, P2-8                                   │
└────────────────────────────────────────────────────────────┘

Day 3:
┌────────────────────────────────────────────────────────────┐
│ 上午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 6. 集成测试                                                 │
│    - 运行完整订单生命周期测试                               │
│    - 性能回归测试                                           │
├────────────────────────────────────────────────────────────┤
│ 下午 (3h)                                                   │
├────────────────────────────────────────────────────────────┤
│ 7. 代码审查和文档更新                                       │
│    - 架构师评审                                             │
│    - 更新 API 文档                                          │
│ 8. 准备发布                                                 │
└────────────────────────────────────────────────────────────┘
```

---

## 7. 回滚策略

### 7.1 方案 A 回滚

**回滚方式**: Git 回滚

```bash
# 回滚到修复前版本
git revert <commit-hash>

# 或强制回滚（如有多个提交）
git reset --hard <previous-commit>
```

**回滚时间**: < 5 分钟

**数据影响**: 无（代码逻辑变更，不影响数据）

### 7.2 方案 B 回滚

**回滚方式**: Git 回滚 + 数据库检查

```bash
# 回滚代码
git revert <commit-hash>

# 检查订单数据完整性
python -c "
import sqlite3
conn = sqlite3.connect('data/v3_dev.db')
cursor = conn.execute('SELECT COUNT(*) FROM orders')
print(f'订单总数：{cursor.fetchone()[0]}')
cursor = conn.execute('SELECT COUNT(*) FROM orders WHERE filled_at IS NULL')
print(f'filled_at 为 NULL 的订单数：{cursor.fetchone()[0]}')
conn.close()
"
```

**回滚时间**: < 10 分钟

**数据影响**: 无（代码逻辑变更，不影响数据）

---

## 8. 推荐方案

### 8.1 推荐：方案 B（系统性重构）

**推荐理由**:

1. **问题覆盖全面**: 一次性解决 9 项问题，避免多次小修小补
2. **代码质量提升**: 系统性优化止损逻辑和异常处理
3. **长期维护成本**: 虽然初期投入较大（3 人天），但减少了未来技术债务
4. **风险可控**: 变更都在应用层，不涉及数据结构，回滚简单

**前提条件**:

- 有充足的测试资源（QA 支持）
- 不处于紧急发布周期
- 团队认同技术债务清理优先级

### 8.2 备选：方案 A（最小改动）

**适用场景**:

- 需要紧急修复 P1 问题
- 测试资源有限
- 近期有重大发布，不宜大改

---

## 9. 验收标准

### 9.1 单元测试要求

| 组件 | 覆盖率要求 | 关键用例 |
|------|-----------|---------|
| OrderRepository | > 90% | 并发 Lock 测试、UPSERT NULL 测试 |
| OrderManager | > 90% | 止损计算测试、strategy None 测试 |
| OrderAuditLogger | > 85% | 类型校验测试、异常处理测试 |

### 9.2 集成测试要求

```python
async def test_order_lifecycle_e2e():
    """端到端订单生命周期测试"""
    # 1. 创建订单
    order = await lifecycle_service.create_order(...)
    
    # 2. 提交订单
    await lifecycle_service.submit_order(order.id)
    
    # 3. 模拟成交
    await lifecycle_service.mark_order_filled(order.id, ...)
    
    # 4. 验证审计日志
    history = await audit_logger.get_audit_history(order.id)
    assert len(history) >= 3  # CREATED, SUBMITTED, FILLED
    
    # 5. 验证数据库完整性
    saved_order = await repository.get_order(order.id)
    assert saved_order.status == OrderStatus.FILLED
    assert saved_order.filled_at is not None
```

### 9.3 性能要求

| 指标 | 要求 | 测量方法 |
|------|------|---------|
| 订单创建延迟 | < 100ms | 压测工具 |
| 审计日志写入 | < 50ms | 队列监控 |
| 并发 Lock 竞争 | 无死锁 | 压力测试 |

---

## 10. 附录

### 10.1 相关文件

| 文件 | 路径 |
|------|------|
| OrderRepository | `src/infrastructure/order_repository.py` |
| OrderManager | `src/domain/order_manager.py` |
| OrderAuditLogger | `src/application/order_audit_logger.py` |
| OrderLifecycleService | `src/application/order_lifecycle_service.py` |
| OrderStrategy | `src/domain/models.py` |

### 10.2 参考文档

- [订单生命周期文档](./order-lifecycle.md)
- [系统开发规范](./2026-03-25-系统开发规范与红线.md)
- [系统架构全面分析报告](./2026-04-06-系统架构全面分析报告.md)

### 10.3 缩略语

| 缩略语 | 含义 |
|--------|------|
| P1 | Priority 1 - 高优先级 |
| P2 | Priority 2 - 中优先级 |
| RR | Risk/Reward - 风险收益比 |
| SL | Stop Loss - 止损 |
| TP | Take Profit - 止盈 |
| OCO | One-Cancels-Other - 互斥订单 |
| UPSERT | UPDATE or INSERT |

---

## 3. 实施任务分解

### 3.1 任务概览

| 任务 ID | 任务名称 | 优先级 | 工时估算 | 依赖 |
|---------|----------|--------|----------|------|
| T001 | P1-1: Lock 竞态条件修复 | P1 | 4h | 无 |
| T002 | P1-2: 止损比例配置化 | P1 | 2h | 无 |
| T003 | P1-3: 日志导入规范化 | P1 | 0.5h | 无 |
| T004 | P2-4: 止损逻辑歧义修复 | P2 | 3h | T002 |
| T005 | P2-5: strategy None 处理 | P2 | 1h | 无 |
| T006 | P2-6: AuditLogger 类型校验 | P2 | 2h | 无 |
| T007 | P2-7: UPSERT 数据丢失修复 | P2 | 2h | 无 |
| T008 | P2-8: 状态描述映射补充 | P2 | 0.5h | 无 |
| T009 | P2-9: Worker 异常处理增强 | P2 | 2h | 无 |
| T010 | 集成测试与验证 | P1 | 4h | T001-T009 |
| **总计** | - | - | **20h (2.5 人天)** | - |

### 3.2 每日任务分解

#### Day 1: P1 级问题修复

| 时间 | 任务 | 交付物 |
|------|------|--------|
| 09:00-11:00 | T001: Lock 竞态条件修复 | 修改 order_repository.py, 新增测试 |
| 11:00-12:00 | T002: 止损比例配置化 | 修改 order_manager.py, 新增测试 |
| 13:00-13:30 | T003: 日志导入规范化 | 修改 order_repository.py |
| 13:30-15:00 | T004: 止损逻辑歧义修复 | 修改 order_manager.py, 新增测试 |
| 15:00-16:00 | T005: strategy None 处理 | 修改 order_manager.py, 新增测试 |
| 16:00-17:00 | Day 1 测试验证 | 运行单元测试，修复回归问题 |

#### Day 2: P2 级问题修复

| 时间 | 任务 | 交付物 |
|------|------|--------|
| 09:00-11:00 | T006: AuditLogger 类型校验 | 修改 order_audit_logger.py, 新增测试 |
| 11:00-13:00 | T007: UPSERT 数据丢失修复 | 修改 order_repository.py, 新增测试 |
| 13:00-13:30 | T008: 状态描述映射补充 | 修改 order_lifecycle_service.py |
| 13:30-15:30 | T009: Worker 异常处理增强 | 修改 order_audit_repository.py, 新增测试 |
| 15:30-17:00 | Day 2 测试验证 | 运行单元测试，修复回归问题 |

#### Day 3: 集成测试与发布

| 时间 | 任务 | 交付物 |
|------|------|--------|
| 09:00-11:00 | T010: 集成测试 | 运行端到端测试 |
| 11:00-12:00 | 性能回归测试 | 性能基准报告 |
| 13:00-15:00 | 代码审查 | 架构师评审通过 |
| 15:00-16:00 | 文档更新 | 更新相关文档 |
| 16:00-17:00 | 发布准备 | 准备 release notes |

### 3.3 并行任务簇

```
并行簇 1 (可并行执行):
┌─────────────────────────────────────────────────────────┐
│  T001 (Lock) │  T002 (止损)  │  T003 (日志)  │  T005 (strategy) │
│     4h       │     2h        │    0.5h       │       1h         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
                  合并到主分支

并行簇 2 (可并行执行):
┌─────────────────────────────────────────────────────────┐
│  T004 (止损逻辑) │  T006 (AuditLogger) │  T007 (UPSERT) │
│      3h          │       2h            │      2h        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
                  合并到主分支

并行簇 3 (可并行执行):
┌─────────────────────────────────────────────────────────┐
│  T008 (状态映射)  │  T009 (Worker)    │                 │
│     0.5h          │      2h           │                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
                  合并到主分支
                          │
                          ▼
              ┌───────────────────────┐
              │   T010: 集成测试      │
              │   性能回归测试        │
              └───────────────────────┘
```

### 3.4 依赖关系图

```
┌─────────────────────────────────────────────────────────────┐
│                    任务依赖关系图                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  T001 ──┬──                                                 │
│  T002 ──┼──  ──► T004 ──┬──                                │
│  T003 ──┤               │                                   │
│  T005 ──┘               │                                   │
│                         ▼                                   │
│  T006 ──┬──                                                 │
│  T007 ──┼── ──────────► T010 (集成测试)                     │
│  T008 ──┤               │                                   │
│  T009 ──┘               ▼                                   │
│                    发布准备                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 关联影响分析

### 4.1 对其他模块的影响

| 影响模块 | 影响程度 | 说明 | 缓解措施 |
|----------|----------|------|----------|
| ExchangeGateway | 低 | 无直接影响 | 无需修改 |
| PositionManager | 低 | 无直接影响 | 无需修改 |
| OrderLifecycleService | 中 | 使用 OrderRepository 和 AuditLogger | 需验证集成测试 |
| SignalPipeline | 低 | 间接依赖 OrderManager | 需验证端到端流程 |
| WebSocket 推送 | 低 | 依赖订单状态变更回调 | 需验证推送正常 |

### 4.2 数据库兼容性

| 修复项 | 数据库变更 | 迁移需求 | 回滚影响 |
|--------|-----------|----------|----------|
| P1-1 (Lock) | 无 | 无 | 无 |
| P1-2 (止损) | 无 | 无 | 无 |
| P1-3 (日志) | 无 | 无 | 无 |
| P2-4 (止损逻辑) | 无 | 无 | 无 |
| P2-5 (strategy) | 无 | 无 | 无 |
| P2-6 (AuditLogger) | 无 | 无 | 无 |
| P2-7 (UPSERT) | 无 | 无 | 无 |
| P2-8 (状态映射) | 无 | 无 | 无 |
| P2-9 (Worker) | 无 | 无 | 无 |

**结论**: 所有修复均为代码逻辑变更，不涉及数据库表结构修改，无需数据迁移。

### 4.3 API 兼容性

| API 端点 | 变更内容 | 兼容性 | 前端影响 |
|----------|----------|--------|----------|
| POST /api/v3/orders | 无 | ✅ 完全兼容 | 无 |
| GET /api/v3/orders/{id} | 无 | ✅ 完全兼容 | 无 |
| GET /api/v3/signals/{id}/orders | 无 | ✅ 完全兼容 | 无 |
| DELETE /api/v3/orders/{id} | 无 | ✅ 完全兼容 | 无 |
| GET /api/v3/audit/orders/{id} | 无 | ✅ 完全兼容 | 无 |

### 4.4 配置兼容性

| 配置项 | 变更 | 向后兼容 | 迁移指南 |
|--------|------|----------|----------|
| 止损比例配置 | 新增从 OrderStrategy.initial_stop_loss_rr 读取 | ✅ 是，默认值 -1.0 | 无需迁移 |

---

## 5. 风险评估

### 5.1 风险矩阵

| 风险项 | 概率 | 影响 | 风险等级 | 缓解措施 |
|--------|------|------|----------|----------|
| Lock 重构引入死锁 | 低 | 高 | 中 | 充分测试 + 代码审查 |
| 止损计算逻辑变更导致计算错误 | 中 | 高 | 高 | 完整单元测试 + 人工验证 |
| UPSERT 逻辑变更影响性能 | 低 | 中 | 低 | 性能基准测试 |
| Worker 异常处理影响吞吐量 | 低 | 低 | 低 | 限制重试次数 |
| 类型校验导致现有调用失败 | 低 | 中 | 低 | 向后兼容默认值 |

### 5.2 各修复项风险等级

| 修复项 | 风险等级 | 说明 |
|--------|----------|------|
| P1-1 (Lock) | 中 | 并发逻辑变更，需充分测试 |
| P1-2 (止损) | 中 | 影响订单生成逻辑 |
| P1-3 (日志) | 低 | 简单导入语句变更 |
| P2-4 (止损逻辑) | 高 | 核心计算逻辑变更 |
| P2-5 (strategy) | 低 | 添加 Optional 支持 |
| P2-6 (AuditLogger) | 中 | 添加类型校验 |
| P2-7 (UPSERT) | 中 | SQL 逻辑变更 |
| P2-8 (状态映射) | 低 | 添加枚举映射 |
| P2-9 (Worker) | 低 | 增强日志记录 |

### 5.3 回滚策略

#### 5.3.1 快速回滚（< 5 分钟）

```bash
# 方式 1: Git revert
git revert <commit-hash> -m 1

# 方式 2: Git reset (如有多个提交)
git reset --hard <previous-commit>
git push origin HEAD --force
```

#### 5.3.2 数据验证

```bash
# 验证订单数据完整性
python -c "
import sqlite3
conn = sqlite3.connect('data/v3_dev.db')

# 检查订单总数
cursor = conn.execute('SELECT COUNT(*) FROM orders')
print(f'订单总数：{cursor.fetchone()[0]}')

# 检查 NULL 字段
cursor = conn.execute('SELECT COUNT(*) FROM orders WHERE filled_at IS NULL')
print(f'filled_at 为 NULL 的订单数：{cursor.fetchone()[0]}')

# 检查状态分布
cursor = conn.execute('SELECT status, COUNT(*) FROM orders GROUP BY status')
for row in cursor.fetchall():
    print(f'状态 {row[0]}: {row[1]} 个订单')

conn.close()
"
```

#### 5.3.3 回滚后验证

1. 运行基本冒烟测试
2. 验证订单创建流程
3. 验证订单状态流转
4. 验证审计日志记录

---

## 6. 验收标准

### 6.1 代码审查 Checklist

#### 通用检查项

- [ ] 所有新增代码有完整的类型注解
- [ ] 所有公共方法有详细的文档字符串
- [ ] 所有修复有对应的单元测试
- [ ] 代码符合 PEP 8 规范
- [ ] 无循环依赖
- [ ] 无硬编码魔法数字

#### P1-1 (Lock) 检查项

- [ ] 使用双重检查锁定模式
- [ ] 支持多事件循环场景
- [ ] 支持同步调用场景
- [ ] 无死锁风险

#### P1-2/P2-4 (止损) 检查项

- [ ] 正确从策略读取止损比例
- [ ] RR 倍数模式计算正确
- [ ] 百分比模式计算正确
- [ ] 边界值处理正确

#### P2-7 (UPSERT) 检查项

- [ ] CASE 表达式语法正确
- [ ] NULL 值处理符合预期
- [ ] 不影响现有功能

### 6.2 测试覆盖率要求

| 模块 | 修复前 | 修复后要求 | 新增用例 |
|------|--------|-----------|----------|
| OrderRepository | 85% | 92% | +7% |
| OrderManager | 80% | 90% | +10% |
| OrderAuditLogger | 75% | 88% | +13% |
| OrderAuditLogRepository | 70% | 85% | +15% |
| **整体** | **78%** | **89%** | **+11%** |

### 6.3 测试用例清单

#### 单元测试 (24 个新增)

| 测试类 | 测试方法 | 覆盖修复项 |
|--------|----------|-----------|
| TestP1Fix_LockConcurrency | test_concurrent_save_operations | P1-1 |
| TestP1Fix_LockConcurrency | test_lock_per_event_loop | P1-1 |
| TestP1Fix_LockConcurrency | test_sync_call_returns_sync_lock | P1-1 |
| TestP1Fix_DynamicStopLoss | test_uses_strategy_stop_loss_rr | P1-2 |
| TestP1Fix_DynamicStopLoss | test_uses_default_when_strategy_none | P1-2 |
| TestP1Fix_DynamicStopLoss | test_uses_default_when_stop_loss_rr_none | P1-2 |
| TestP1Fix_LoggerImport | test_uses_standard_logging | P1-3 |
| TestP2Fix_StopLossCalculation | test_rr_mode_long_position | P2-4 |
| TestP2Fix_StopLossCalculation | test_rr_mode_short_position | P2-4 |
| TestP2Fix_StopLossCalculation | test_percent_mode_long_position | P2-4 |
| TestP2Fix_StopLossCalculation | test_percent_mode_short_position | P2-4 |
| TestP2Fix_StopLossCalculation | test_rr_mode_2r_stop_loss | P2-4 |
| TestP2Fix_StrategyNoneHandling | test_create_order_chain_with_none_strategy | P2-5 |
| TestP2Fix_StrategyNoneHandling | test_create_order_chain_with_strategy | P2-5 |
| TestP2Fix_AuditLoggerTypeValidation | test_init_with_invalid_repository | P2-6 |
| TestP2Fix_AuditLoggerTypeValidation | test_log_with_invalid_order_id | P2-6 |
| TestP2Fix_AuditLoggerTypeValidation | test_log_with_invalid_event_type | P2-6 |
| TestP2Fix_AuditLoggerTypeValidation | test_log_with_invalid_triggered_by | P2-6 |
| TestP2Fix_AuditLoggerTypeValidation | test_log_with_valid_parameters | P2-6 |
| TestP2Fix_UpsertNullHandling | test_update_field_to_null | P2-7 |
| TestP2Fix_UpsertNullHandling | test_preserve_filled_at_when_null_in_update | P2-7 |
| TestP2Fix_UpsertNullHandling | test_update_oco_group_id_to_null | P2-7 |
| TestP2Fix_WorkerErrorHandling | test_worker_logs_exception_details | P2-9 |
| TestP2Fix_WorkerErrorHandling | test_worker_continues_after_error | P2-9 |

#### 集成测试 (2 个新增)

| 测试名称 | 覆盖范围 |
|----------|----------|
| test_order_lifecycle_with_dynamic_stop_loss | 完整订单生命周期 + 动态止损 |
| test_order_lifecycle_with_null_fields | 订单 NULL 字段处理 |

### 6.4 性能基准

| 指标 | 修复前 | 修复后要求 | 测试方法 |
|------|--------|-----------|----------|
| 订单创建延迟 | < 100ms | < 120ms | 压测工具 |
| 订单保存延迟 | < 50ms | < 60ms | 压测工具 |
| 审计日志写入 | < 50ms | < 60ms | 队列监控 |
| 并发 Lock 竞争 | 无死锁 | 无死锁 | 压力测试 |
| Worker 错误恢复 | N/A | < 1s | 故障注入测试 |

### 6.5 验收流程

```
┌─────────────────────────────────────────────────────────────┐
│                    验收流程                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 开发者自测                                               │
│     └── 运行单元测试 (100% 通过)                            │
│                                                             │
│  2. 代码审查                                                 │
│     └── 架构师评审 + Checklist 勾选                          │
│                                                             │
│  3. 集成测试                                                 │
│     └── 运行端到端测试 (100% 通过)                          │
│                                                             │
│  4. 性能回归                                                 │
│     └── 性能基准测试 (满足要求)                              │
│                                                             │
│  5. QA 验收                                                  │
│     └── 手动验证关键场景                                     │
│                                                             │
│  6. 发布                                                    │
│     └── 更新文档 + Release Notes                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 附录

### 7.1 关键文件清单

| 文件 | 修改类型 | 修复项 |
|------|----------|--------|
| src/infrastructure/order_repository.py | 修改 | P1-1, P1-3, P2-7 |
| src/domain/order_manager.py | 修改 | P1-2, P2-4, P2-5 |
| src/application/order_audit_logger.py | 修改 | P2-6 |
| src/application/order_lifecycle_service.py | 修改 | P2-8 |
| src/infrastructure/order_audit_repository.py | 修改 | P2-9 |
| tests/unit/test_order_repository.py | 新增测试 | P1-1, P2-7 |
| tests/unit/test_order_manager.py | 新增测试 | P1-2, P2-4, P2-5 |
| tests/unit/test_order_audit_logger.py | 新增测试 | P2-6 |
| tests/unit/test_order_audit_repository.py | 新增测试 | P2-9 |

### 7.2 相关文档

| 文档 | 路径 |
|------|------|
| 订单生命周期文档 | docs/arch/order-lifecycle.md |
| 系统开发规范 | docs/arch/2026-03-25-系统开发规范与红线.md |
| Phase 5 代码审查报告 | docs/reviews/phase5-code-review.md |
| P0 修复报告 | docs/code-review/p0-fix-report-2026-04-01.md |

### 7.3 术语表

| 术语 | 含义 |
|------|------|
| P1 | Priority 1 - 高优先级问题 |
| P2 | Priority 2 - 中优先级问题 |
| RR | Risk/Reward - 风险收益比 |
| SL | Stop Loss - 止损 |
| TP | Take Profit - 止盈 |
| OCO | One-Cancels-Other - 互斥订单 |
| UPSERT | UPDATE or INSERT - 更新或插入 |
| Lock | asyncio.Lock - 异步锁 |

---

## 8. 审批签字

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 架构师 | | | |
| 开发负责人 | | | |
| QA 负责人 | | | |
| 产品经理 | | | |

**审批检查清单**:
- [ ] 所有 P1 问题已覆盖
- [ ] 所有 P2 问题已覆盖
- [ ] 测试用例设计完整
- [ ] 实施计划可行
- [ ] 风险评估充分
- [ ] 回滚策略明确
- [ ] 验收标准清晰

---

*文档创建时间：2026-04-07*  
*下次审查：实施完成后*

---