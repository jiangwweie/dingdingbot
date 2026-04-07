# ADR-003: 订单管理模块代码审查问题修复设计

> **架构决策记录 (Architecture Decision Record)**
> **文档级别**: P8 架构师评审级
> **创建日期**: 2026-04-07
> **状态**: 待评审 (Pending Review)
> **影响范围**: OrderRepository, OrderManager, OrderAuditLogger, OrderLifecycleService
> **关联任务**: 订单管理模块全面代码审查

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

## 2. 修复方案设计

### 2.1 方案 A：最小改动（快速修复）

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

**文档状态**: 待评审 (Pending Review)

**下一步**:
1. 架构师评审本设计文档
2. 开发团队确认实施方案
3. QA 团队确认测试方案
4. 进入实施阶段

---

*文档创建时间：2026-04-07*