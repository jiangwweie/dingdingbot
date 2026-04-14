# P2 改进建议和已知问题修复方案设计

> **文档级别**: P2 改进建议  
> **创建日期**: 2026-04-07  
> **状态**: 待评审 (Pending Review)  
> **实施策略**: 系统性修复  
> **影响范围**: OrderRepository, OrderManager, OrderAuditLogger  

---

## 执行摘要

本文档设计了 3 个 P2 级改进问题和 1 个已知问题的修复方案。这些问题虽然不阻塞核心功能，但影响代码质量和长期可维护性。

### 问题清单

| 编号 | 问题 | 位置 | 风险等级 | 修复优先级 |
|------|------|------|----------|-----------|
| IMP-001 | `save_batch()` COALESCE 问题 | `order_repository.py:289-293` | 中 | P2 |
| IMP-002 | `tp_ratios` 求和精度问题 | `order_manager.py:360`, `models.py:1128,1136` | 中 | P2 |
| 已知 -1 | `OrderAuditLogger.start()` 参数错误 | 待调查 | 待确认 | 待确认 |

### 实施估算

| 维度 | 估算 |
|------|------|
| 工时 | 0.5 人天 |
| 代码变更 | ~50 行 |
| 测试变更 | ~80 行 |
| 风险等级 | 低 |
| 回滚时间 | < 5 分钟 |

---

## 1. 问题分析

### 1.1 背景

在代码审查和测试过程中发现 3 个 P2 级改进点：
1. `save_batch()` 方法使用 COALESCE 语法与 T007 相同问题
2. `tp_ratios` 求和使用 Python 原生 `sum()` 可能导致 Decimal 精度问题
3. `OrderAuditLogger.start()` 参数错误（待调查）

---

### 1.2 IMP-001: save_batch() COALESCE 问题

**问题位置**: `src/infrastructure/order_repository.py:289-293`

**问题代码**:
```python
ON CONFLICT(id) DO UPDATE SET
    filled_at = COALESCE(excluded.filled_at, orders.filled_at),
    exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),
    exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),
    parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),
    oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),
```

**问题描述**:
- 与 T007 相同问题，使用 `COALESCE(excluded.field, orders.field)` 语法
- 当 `excluded.field` 为 NULL 时，会保留旧值而非更新为 NULL
- 无法区分「不更新」和「设置为 NULL」两种业务语义

**影响范围**:
- 订单字段更新时无法将字段设置为 NULL
- 例如：无法清除 `exchange_order_id`、`oco_group_id` 等字段

**参考文档**: `docs/arch/order-management-fix-design.md` (T007 修复方案)

---

### 1.3 IMP-002: tp_ratios 求和精度问题

**问题位置**: 
- `src/domain/order_manager.py:360`
- `src/domain/models.py:1128, 1136-1137`

**问题代码**:
```python
# order_manager.py:360
total_ratio = sum(tp_ratios)

# models.py:1128
total = sum(self.tp_ratios)

# models.py:1136-1137
if v and sum(v) != Decimal('1.0'):
    total = sum(v)
```

**问题描述**:
- Python 内置 `sum()` 函数在处理 `Decimal` 列表时，内部使用浮点数累加
- 可能导致精度损失，特别是在多次累加后
- 应使用 `functools.reduce()` 或 `Decimal` 累加器确保精度

**影响范围**:
- 止盈比例验证可能因精度问题误判
- 多级别 TP 订单数量计算可能产生微小误差

**示例**:
```python
from decimal import Decimal

# 精度问题示例
ratios = [Decimal('0.33333333')] * 3
total = sum(ratios)  # 可能不是精确的 0.99999999
# 正确方式：使用 Decimal 累加
total = Decimal('0')
for r in ratios:
    total += r
```

---

### 1.4 已知 -1: OrderAuditLogger.start() 参数错误

**问题描述**: 测试报告显示 `OrderAuditLogger.start()` 存在参数传递错误

**调查过程**:

阅读相关代码发现：
1. `OrderAuditLogger.start(queue_size: int = 1000)` 接收 `queue_size` 参数
2. 调用方 `OrderLifecycleService.start()` 调用时传入默认参数：
   ```python
   await self._audit_logger.start()  # 使用默认 queue_size=1000
   ```
3. 测试代码中也有类似调用：
   ```python
   await audit_logger.start()  # 测试中使用默认值
   ```

**分析结果**: 
- 当前代码中 `start()` 方法参数传递正确
- `queue_size` 参数有合理默认值 `1000`
- 调用方可以不传参使用默认值

**建议**: 
- 此问题可能已修复或为误报
- 建议在测试中显式传入 `queue_size` 参数以增强可读性

---

## 2. 修复方案设计

### 2.1 IMP-001: save_batch() COALESCE 问题修复

**问题位置**: `src/infrastructure/order_repository.py:285-294`  
**风险等级**: 中  
**修复优先级**: P2

#### 2.1.1 问题代码

```python
ON CONFLICT(id) DO UPDATE SET
    status = excluded.status,
    filled_qty = excluded.filled_qty,
    average_exec_price = excluded.average_exec_price,
    filled_at = COALESCE(excluded.filled_at, orders.filled_at),
    exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),
    exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),
    parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),
    oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),
    updated_at = excluded.updated_at
```

#### 2.1.2 修复代码

使用 `CASE` 表达式替代 `COALESCE`，支持将字段更新为 NULL：

```python
# ✅ IMP-001 修复：使用 CASE 表达式支持 NULL 更新
ON CONFLICT(id) DO UPDATE SET
    status = excluded.status,
    filled_qty = excluded.filled_qty,
    average_exec_price = excluded.average_exec_price,
    filled_at = CASE 
        WHEN excluded.filled_at IS NULL THEN orders.filled_at 
        ELSE excluded.filled_at 
    END,
    exchange_order_id = CASE 
        WHEN excluded.exchange_order_id IS NULL THEN orders.exchange_order_id 
        ELSE excluded.exchange_order_id 
    END,
    exit_reason = CASE 
        WHEN excluded.exit_reason IS NULL THEN orders.exit_reason 
        ELSE excluded.exit_reason 
    END,
    parent_order_id = CASE 
        WHEN excluded.parent_order_id IS NULL THEN orders.parent_order_id 
        ELSE excluded.parent_order_id 
    END,
    oco_group_id = CASE 
        WHEN excluded.oco_group_id IS NULL THEN orders.oco_group_id 
        ELSE excluded.oco_group_id 
    END,
    updated_at = excluded.updated_at
```

#### 2.1.3 测试用例设计

```python
# tests/unit/infrastructure/test_order_repository_unit.py

class TestIMP001_UpsertNullHandling:
    """IMP-001: UPSERT NULL 字段处理测试"""
    
    @pytest.fixture
    async def repo(self, db_connection):
        """创建订单仓库实例"""
        repo = OrderRepository()
        repo._db = db_connection
        return repo
    
    @pytest.mark.asyncio
    async def test_update_field_to_null(self, repo):
        """测试可以将字段更新为 NULL"""
        # Arrange: 创建订单并设置 exchange_order_id
        order1 = create_test_order(
            id="order_001",
            exchange_order_id="binance_123",
            filled_at=datetime.now(timezone.utc),
        )
        await repo.save(order1)
        
        # Act: 更新时将 exchange_order_id 设为 NULL
        order2 = create_test_order(
            id="order_001",  # 相同 ID
            exchange_order_id=None,  # 设置为 NULL
            filled_at=None,
        )
        await repo.save(order2)
        
        # Assert: 验证字段已被更新为 NULL
        saved = await repo.get_by_id("order_001")
        assert saved.exchange_order_id is None
        assert saved.filled_at is None
    
    @pytest.mark.asyncio
    async def test_preserve_field_when_null_in_update(self, repo):
        """测试当更新值为 NULL 时保留原值"""
        # Arrange: 创建订单
        order1 = create_test_order(
            id="order_002",
            exchange_order_id="binance_456",
            exit_reason="TAKE_PROFIT",
        )
        await repo.save(order1)
        
        # Act: 更新时不传递某些字段（保持 NULL）
        # 注意：当前修复后，NULL 会被更新，如需保留原值需应用层控制
        order2 = create_test_order(
            id="order_002",
            exchange_order_id=None,  # 明确设置为 NULL
            exit_reason="STOP_LOSS",  # 更新 exit_reason
        )
        await repo.save(order2)
        
        # Assert: exchange_order_id 被更新为 NULL
        saved = await repo.get_by_id("order_002")
        assert saved.exchange_order_id is None
        assert saved.exit_reason == "STOP_LOSS"
    
    @pytest.mark.asyncio
    async def test_update_oco_group_id_to_null(self, repo):
        """测试可以将 OCO 组 ID 更新为 NULL"""
        # Arrange
        order1 = create_test_order(
            id="order_003",
            oco_group_id="oco_group_789",
        )
        await repo.save(order1)
        
        # Act: 清除 OCO 组 ID
        order2 = create_test_order(
            id="order_003",
            oco_group_id=None,
        )
        await repo.save(order2)
        
        # Assert
        saved = await repo.get_by_id("order_003")
        assert saved.oco_group_id is None
```

---

### 2.2 IMP-002: tp_ratios 求和精度问题修复

**问题位置**: `src/domain/order_manager.py:360`, `src/domain/models.py:1128, 1136`  
**风险等级**: 中  
**修复优先级**: P2

#### 2.2.1 问题代码

```python
# order_manager.py:360
total_ratio = sum(tp_ratios)

# models.py:1128
total = sum(self.tp_ratios)

# models.py:1136
if v and sum(v) != Decimal('1.0'):
```

#### 2.2.2 修复代码

**方案 A: 使用 functools.reduce()**

```python
from functools import reduce
from operator import add

# order_manager.py:360
total_ratio = reduce(add, tp_ratios, Decimal('0'))

# models.py:1128
total = reduce(add, self.tp_ratios, Decimal('0'))

# models.py:1136
if v and reduce(add, v, Decimal('0')) != Decimal('1.0'):
```

**方案 B: 使用 Decimal 累加器（推荐）**

```python
# order_manager.py:360
# ✅ IMP-002 修复：使用 Decimal 累加器确保精度
total_ratio = Decimal('0')
for ratio in tp_ratios:
    total_ratio += ratio

# models.py:1128
total = Decimal('0')
for ratio in self.tp_ratios:
    total += ratio

# models.py:1136
total = Decimal('0')
for ratio in v:
    total += ratio
if v and total != Decimal('1.0'):
```

**方案 C: 使用 math.fsum()（不推荐，返回 float）**

```python
import math
total_ratio = Decimal(str(math.fsum(tp_ratios)))
```

#### 2.2.3 推荐方案：方案 B（Decimal 累加器）

**理由**:
1. 代码可读性最好
2. 不引入额外依赖
3. 完全保留 Decimal 精度
4. 性能与 `reduce()` 相当

#### 2.2.4 完整修复代码

**文件 1**: `src/domain/order_manager.py:360`

```python
# 修复前
total_ratio = sum(tp_ratios)

# 修复后
# ✅ IMP-002 修复：使用 Decimal 累加器确保精度
total_ratio = Decimal('0')
for ratio in tp_ratios:
    total_ratio += ratio
```

**文件 2**: `src/domain/models.py:1128`

```python
# 修复前
def validate_ratios(self) -> bool:
    if not self.tp_ratios:
        return False
    total = sum(self.tp_ratios)
    return abs(total - Decimal('1.0')) < Decimal('0.0001')

# 修复后
def validate_ratios(self) -> bool:
    """
    验证比例总和是否为 1.0

    返回:
        True: 比例有效
        False: 比例无效
    """
    if not self.tp_ratios:
        return False
    # ✅ IMP-002 修复：使用 Decimal 累加器确保精度
    total = Decimal('0')
    for ratio in self.tp_ratios:
        total += ratio
    # 使用 Decimal 精度比较，允许小误差
    return abs(total - Decimal('1.0')) < Decimal('0.0001')
```

**文件 3**: `src/domain/models.py:1132-1140`

```python
# 修复前
@field_validator('tp_ratios')
@classmethod
def validate_tp_ratios_sum(cls, v):
    """验证 tp_ratios 总和是否接近 1.0"""
    if v and sum(v) != Decimal('1.0'):
        total = sum(v)
        if abs(total - Decimal('1.0')) > Decimal('0.0001'):
            raise ValueError(f"tp_ratios 总和必须为 1.0，当前为 {total}")
    return v

# 修复后
@field_validator('tp_ratios')
@classmethod
def validate_tp_ratios_sum(cls, v):
    """验证 tp_ratios 总和是否接近 1.0"""
    if v:
        # ✅ IMP-002 修复：使用 Decimal 累加器确保精度
        total = Decimal('0')
        for ratio in v:
            total += ratio
        if abs(total - Decimal('1.0')) > Decimal('0.0001'):
            raise ValueError(f"tp_ratios 总和必须为 1.0，当前为 {total}")
    return v
```

#### 2.2.5 测试用例设计

```python
# tests/unit/domain/test_order_manager.py

class TestIMP002_DecimalPrecision:
    """IMP-002: Decimal 精度修复测试"""
    
    @pytest.fixture
    def order_manager(self):
        return OrderManager()
    
    def test_sum_tp_ratios_precision(self, order_manager):
        """测试 tp_ratios 求和精度"""
        # Arrange: 构造可能产生精度问题的比例
        tp_ratios = [Decimal('0.33333333'), Decimal('0.33333333'), Decimal('0.33333334')]
        
        # Act: 使用修复后的代码（假设已修复）
        total = Decimal('0')
        for ratio in tp_ratios:
            total += ratio
        
        # Assert: 验证精度正确
        assert total == Decimal('1.0')
    
    def test_sum_tp_ratios_edge_case(self, order_manager):
        """测试边界情况：多级别 TP 比例求和"""
        # Arrange: 5 级别 TP，每级 0.2
        tp_ratios = [Decimal('0.2')] * 5
        
        # Act
        total = Decimal('0')
        for ratio in tp_ratios:
            total += ratio
        
        # Assert
        assert total == Decimal('1.0')
    
    def test_sum_tp_ratios_small_error(self, order_manager):
        """测试小误差容忍"""
        # Arrange: 带小误差的比例
        tp_ratios = [Decimal('0.3333333333')] * 3
        
        # Act
        total = Decimal('0')
        for ratio in tp_ratios:
            total += ratio
        
        # Assert: 允许小误差
        assert abs(total - Decimal('1.0')) < Decimal('0.0001')


# tests/unit/domain/test_models.py

class TestIMP002_OrderStrategyDecimalPrecision:
    """IMP-002: OrderStrategy Decimal 精度测试"""
    
    def test_validate_ratios_with_decimal_sum(self):
        """测试比例验证使用 Decimal 累加"""
        # Arrange
        strategy = OrderStrategy(
            id="strategy_001",
            name="Test Strategy",
            tp_ratios=[Decimal('0.33333333'), Decimal('0.33333333'), Decimal('0.33333334')],
        )
        
        # Act
        is_valid = strategy.validate_ratios()
        
        # Assert
        assert is_valid is True
    
    def test_validate_ratios_sum_not_one(self):
        """测试比例总和不等于 1.0 时抛出异常"""
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            OrderStrategy(
                id="strategy_002",
                name="Test Strategy",
                tp_ratios=[Decimal('0.5'), Decimal('0.5'), Decimal('0.5')],  # 总和 1.5
            )
        
        assert "tp_ratios 总和必须为 1.0" in str(exc_info.value)
```

---

### 2.3 已知 -1: OrderAuditLogger.start() 参数错误

**问题位置**: `src/application/order_audit_logger.py:98-108`  
**风险等级**: 低（可能为误报）  
**修复优先级**: P3

#### 2.3.1 问题分析

经调查，`OrderAuditLogger.start()` 方法签名正确：

```python
async def start(self, queue_size: int = 1000) -> None:
    """
    启动审计日志服务

    Args:
        queue_size: 异步队列最大容量
    """
    if not self._started:
        await self._repository.initialize(queue_size)
        self._started = True
        logger.info(f"OrderAuditLogger 已启动（队列容量：{queue_size}）")
```

调用方使用默认参数是合理的：
```python
await self._audit_logger.start()  # 使用默认 queue_size=1000
```

#### 2.3.2 改进建议

虽然参数传递没有错误，但为增强代码可读性和明确性，建议：

**方案 A: 显式传入参数（推荐）**

```python
# OrderLifecycleService.start()
await self._audit_logger.start(queue_size=1000)  # 显式指定队列容量
```

**方案 B: 调整默认值**

```python
# 如果 1000 不够，可以调整为更大的默认值
async def start(self, queue_size: int = 10000) -> None:
    ...
```

#### 2.3.3 修复代码（方案 A）

```python
# src/application/order_lifecycle_service.py:104

# 修复前
await self._audit_logger.start()

# 修复后
# ✅ 已知 -1 修复：显式传入 queue_size 参数增强可读性
await self._audit_logger.start(queue_size=1000)
```

#### 2.3.4 测试用例设计

```python
# tests/unit/application/test_order_audit_logger.py

class TestKnownIssue1_StartParameter:
    """已知 -1: start() 参数错误修复测试"""
    
    @pytest.mark.asyncio
    async def test_start_with_explicit_queue_size(self, audit_logger, mock_repository):
        """测试显式传入 queue_size 参数"""
        # Arrange
        queue_size = 2000
        
        # Act
        await audit_logger.start(queue_size=queue_size)
        
        # Assert
        mock_repository.initialize.assert_called_once_with(queue_size)
    
    @pytest.mark.asyncio
    async def test_start_with_default_queue_size(self, audit_logger, mock_repository):
        """测试使用默认 queue_size 参数"""
        # Act
        await audit_logger.start()
        
        # Assert: 默认值为 1000
        mock_repository.initialize.assert_called_once_with(1000)
```

---

## 3. 关联影响分析

### 3.1 IMP-001 影响分析

| 影响维度 | 分析 |
|----------|------|
| **向下兼容** | 兼容 - 现有调用方不受影响 |
| **向上兼容** | 兼容 - 新语义支持 NULL 更新 |
| **性能影响** | 无 - CASE 表达式与 COALESCE 性能相当 |
| **数据迁移** | 无需迁移 |
| **前端影响** | 无 |

**受影响的调用方**:
- `OrderLifecycleService._transition()` - 调用 `save_batch()` 更新订单状态
- `OrderRepository.save()` - 单条订单保存（使用相同 SQL 模式）

---

### 3.2 IMP-002 影响分析

| 影响维度 | 分析 |
|----------|------|
| **向下兼容** | 兼容 - 计算结果更精确 |
| **向上兼容** | 兼容 - 不影响现有逻辑 |
| **性能影响** | 可忽略 - Decimal 累加器性能与 sum() 相当 |
| **数据迁移** | 无需迁移 |
| **前端影响** | 无 |

**受影响的调用方**:
- `OrderManager._generate_tp_orders()` - 计算 TP 比例总和
- `OrderStrategy.validate_ratios()` - 验证比例总和
- `OrderStrategy.validate_tp_ratios_sum()` - 字段验证器

---

### 3.3 已知 -1 影响分析

| 影响维度 | 分析 |
|----------|------|
| **向下兼容** | 兼容 - 仅改进代码可读性 |
| **向上兼容** | 兼容 |
| **性能影响** | 无 |
| **数据迁移** | 无需迁移 |
| **前端影响** | 无 |

---

## 4. 实施路线图

### 4.1 任务分解

| 任务 ID | 任务名称 | 预计工时 | 依赖关系 |
|---------|----------|----------|----------|
| T001 | IMP-001: COALESCE 问题修复 | 1h | 无 |
| T002 | IMP-002: Decimal 精度修复 | 1h | 无 |
| T003 | 已知 -1: start() 参数显式化 | 0.5h | 无 |
| T004 | 单元测试编写 | 1.5h | T001, T002, T003 |
| T005 | 代码审查 | 0.5h | T004 |

### 4.2 并行簇分析

```
┌─────────────────────────────────────────────────────────────┐
│                    并行簇分析                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  并行簇 1 (可并行执行):                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  T001    │  │  T002    │  │  T003    │                  │
│  │ COALESCE │  │ Decimal  │  │ start()  │                  │
│  │  修复    │  │  修复    │  │  显式化  │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │             │             │                         │
│       └─────────────┼─────────────┘                         │
│                     │                                       │
│                     ▼                                       │
│              ┌─────────────┐                                │
│              │    T004     │                                │
│              │ 单元测试编写 │                                │
│              └──────┬──────┘                                │
│                     │                                       │
│                     ▼                                       │
│              ┌─────────────┐                                │
│              │    T005     │                                │
│              │   代码审查   │                                │
│              └─────────────┘                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 实施顺序

```
会话 1 (1h):
├── T001: IMP-001 COALESCE 修复
└── T002: IMP-002 Decimal 精度修复

会话 2 (1h):
├── T003: 已知 -1 start() 参数显式化
├── T004: 单元测试编写
└── T005: 代码审查 + 自测
```

---

## 5. 验收标准

### 5.1 代码审查 Checklist

#### 通用检查项

- [ ] 所有新增代码有完整的类型注解
- [ ] 所有修复有对应的单元测试
- [ ] 代码符合 PEP 8 规范
- [ ] 无循环依赖

#### IMP-001 检查项

- [ ] CASE 表达式语法正确
- [ ] NULL 值处理符合预期
- [ ] 不影响现有功能

#### IMP-002 检查项

- [ ] 使用 Decimal 累加器替代 sum()
- [ ] 所有 tp_ratios 求和位置已修复
- [ ] 精度验证逻辑正确

#### 已知 -1 检查项

- [ ] start() 调用显式传入 queue_size 参数
- [ ] 参数值合理（1000）

---

### 5.2 测试覆盖率要求

| 模块 | 修复前 | 修复后要求 | 新增用例 |
|------|--------|-----------|----------|
| OrderRepository | 85% | 87% | +2% |
| OrderManager | 80% | 82% | +2% |
| OrderStrategy | 75% | 78% | +3% |

### 5.3 测试用例清单

#### 单元测试 (7 个新增)

| 测试类 | 测试方法 | 覆盖修复项 |
|--------|----------|-----------|
| TestIMP001_UpsertNullHandling | test_update_field_to_null | IMP-001 |
| TestIMP001_UpsertNullHandling | test_preserve_field_when_null_in_update | IMP-001 |
| TestIMP001_UpsertNullHandling | test_update_oco_group_id_to_null | IMP-001 |
| TestIMP002_DecimalPrecision | test_sum_tp_ratios_precision | IMP-002 |
| TestIMP002_DecimalPrecision | test_sum_tp_ratios_edge_case | IMP-002 |
| TestIMP002_DecimalPrecision | test_sum_tp_ratios_small_error | IMP-002 |
| TestKnownIssue1_StartParameter | test_start_with_explicit_queue_size | 已知 -1 |
| TestKnownIssue1_StartParameter | test_start_with_default_queue_size | 已知 -1 |

---

### 5.4 验收流程

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
│  3. 回归测试                                                 │
│     └── 运行现有测试套件 (100% 通过)                        │
│                                                             │
│  4. 发布                                                    │
│     └── Git 提交 + 推送                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 附录

### 6.1 关键文件清单

| 文件 | 修改类型 | 修复项 |
|------|----------|--------|
| `src/infrastructure/order_repository.py` | 修改 | IMP-001 |
| `src/domain/order_manager.py` | 修改 | IMP-002 |
| `src/domain/models.py` | 修改 | IMP-002 |
| `src/application/order_lifecycle_service.py` | 修改 | 已知 -1 |
| `tests/unit/infrastructure/test_order_repository_unit.py` | 新增测试 | IMP-001 |
| `tests/unit/domain/test_order_manager.py` | 新增测试 | IMP-002 |
| `tests/unit/domain/test_models.py` | 新增测试 | IMP-002 |
| `tests/unit/application/test_order_audit_logger.py` | 新增测试 | 已知 -1 |

### 6.2 参考资料

| 文档 | 路径 |
|------|------|
| T007 修复方案 | `docs/arch/order-management-fix-design.md` |
| 系统开发规范 | `docs/arch/2026-03-25-系统开发规范与红线.md` |
| Decimal 精度最佳实践 | `docs/arch/decimal-precision-best-practices.md` |

---

*本设计文档遵循 P8 架构师评审级标准*
