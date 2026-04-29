# Phase 4: 订单编排 - 完成报告

**创建日期**: 2026-03-30
**状态**: ✅ 已完成
**测试通过率**: 100% (25/25)
**Git 提交**: `c2b22f3`

---

## 执行摘要

Phase 4 订单编排开发任务已全面完成。实现了 v3.0 PMS 模式的订单编排核心逻辑，包括：

1. ✅ **OrderManager 核心类** - 订单编排管理器 (~400 行)
2. ✅ **OrderStrategy 类** - 订单策略配置 (支持 1-5 级 TP)
3. ✅ **订单生成时序** - create_order_chain() 仅生成 ENTRY 订单
4. ✅ **动态 TP/SL 生成** - ENTRY 成交后基于 actual_exec_price 生成
5. ✅ **OCO 逻辑** - 基于仓位数量判定撤销/更新
6. ✅ **TP 价格计算** - 基于实际开仓价和 RR 倍数
7. ✅ **Backtester 集成** - OrderManager 完整集成到回测器

---

## 交付成果

### 1. 新增文件

| 文件 | 说明 | 行数 |
|------|------|------|
| `src/domain/order_manager.py` | OrderManager 核心实现 | ~400 行 |
| `tests/unit/test_v3_order_manager.py` | 单元测试 (19 个) | ~650 行 |
| `tests/integration/test_v3_phase4_integration.py` | 集成测试 (6 个) | ~350 行 |

### 2. 修改文件

| 文件 | 变更说明 |
|------|----------|
| `src/domain/models.py` | OrderStrategy 添加 tp_targets 字段，Order 添加 parent_order_id/oco_group_id |
| `src/application/backtester.py` | 集成 OrderManager，修复硬编码问题 |

### 3. 契约文档

| 文件 | 说明 |
|------|------|
| `docs/designs/phase4-order-orchestration-contract.md` | Phase 4 契约表 (v1.1) |
| `docs/designs/phase4-pending-dca-feature.md` | 分批建仓待办记录 (延期至 Phase 5) |
| `docs/designs/phase4-contract-v1.1-changes.md` | v1.1 修订报告 |

### 4. 测试覆盖

**单元测试 (19 个)**:
| 测试 ID | 测试场景 | 状态 |
|---------|----------|------|
| UT-001 | OrderStrategy 单 TP 配置 | ✅ |
| UT-002 | OrderStrategy 多 TP 配置 | ✅ |
| UT-003 | OrderStrategy 比例验证失败 | ✅ |
| UT-004 | create_order_chain 仅生成 ENTRY | ✅ |
| UT-005 | handle_order_filled ENTRY 成交生成 TP+SL | ✅ |
| UT-006 | TP 目标价格计算 (LONG) | ✅ |
| UT-007 | TP 目标价格计算 (SHORT) | ✅ |
| UT-008 | handle_order_filled TP1 成交更新 SL 数量 | ✅ |
| UT-009 | handle_order_filled SL 成交撤销所有 TP 订单 | ✅ |
| UT-010 | apply_oco_logic 完全平仓撤销所有挂单 | ✅ |
| UT-011 | apply_oco_logic 部分平仓更新 SL 数量 | ✅ |
| UT-012 | get_order_chain_status 返回正确状态字典 | ✅ |
| UT-013 | Decimal 精度保护 | ✅ |
| UT-014 | 职责边界验证 | ✅ |

**集成测试 (6 个)**:
| 测试 ID | 测试场景 | 状态 |
|---------|----------|------|
| IT-001 | 完整订单链流程 | ✅ |
| IT-002 | 多 TP 策略完整流程 | ✅ |
| IT-003 | OCO 逻辑验证 | ✅ |
| IT-004 | 部分止盈后打损 | ✅ |
| IT-005 | 与风控状态机集成 | ✅ |
| IT-006 | 职责边界验证 | ✅ |

**总计**: 25/25 通过 (100%)

---

## 核心设计要点

### 1. 订单生成时序

**修订前 (v1.0)**:
```python
create_order_chain() → ENTRY + TP + SL  # 错误：TP/SL 价格基于预期 entry_price
```

**修订后 (v1.1)**:
```python
create_order_chain() → ENTRY only
handle_order_filled() → TP + SL  # 正确：基于 actual_exec_price
```

### 2. 职责边界声明

| 模块 | 负责领域 | 具体职责 |
|------|---------|---------|
| **OrderManager** | **量 (Quantity)** | - SL 数量同步<br>- OCO 逻辑<br>- ENTRY 成交后动态生成 TP/SL |
| **DynamicRiskManager** | **价 (Price)** | - Breakeven (SL 价格上移)<br>- Trailing Stop (水位线追踪)<br>- **不修改** `requested_qty` |

### 3. TP 价格计算

**LONG 仓位**:
```python
tp_price = actual_entry + RR × (actual_entry - sl)
```

**SHORT 仓位**:
```python
tp_price = actual_entry - RR × (sl - actual_entry)
```

**关键点**: 基于实际开仓价 (`actual_exec_price`) 计算，而非信号预期价。

### 4. OCO 逻辑

```python
# 基于仓位剩余数量判定
if position.current_qty <= Decimal('0'):
    # 完全平仓：撤销所有剩余挂单
    for order in active_orders:
        if order.signal_id == signal_id and order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELED
else:
    # 部分平仓：更新 SL 数量与剩余仓位对齐
    sl_order = self._find_order_by_role(active_orders, OrderRole.SL)
    if sl_order:
        sl_order.requested_qty = position.current_qty
```

---

## 审查问题修复

### L2-03: Backtester 硬编码问题

**问题**: `tp_targets` 硬编码为 `[Decimal('1.5')]`，未使用 `strategy.tp_targets`

**修复**:
```python
# 修复前
tp_targets=[Decimal('1.5')]

# 修复后
tp_targets=strategy.tp_targets
```

**OrderStrategy 扩展**:
```python
tp_targets: List[Decimal] = Field(
    default_factory=lambda: [Decimal('1.5')],
    description="各级 TP 目标 RR 倍数 (如 [1.5, 2.0, 3.0])"
)
```

---

## 验收标准

### 功能验收

- [x] OrderStrategy 类实现完成
- [x] OrderManager 类实现完成
- [x] 多级别止盈支持 (1-5 级)
- [x] OCO 逻辑实现正确
- [x] TP 目标价格计算正确 (基于实际开仓价)
- [x] 订单链状态追踪正确
- [x] Backtester 集成完成
- [x] 与 DynamicRiskManager 职责边界清晰

### 测试验收

- [x] 单元测试覆盖率 100% (19/19 通过)
- [x] 集成测试 100% 通过 (6/6 通过)
- [x] 所有边界 case 测试通过

### 代码质量

- [x] 领域层纯净 (order_manager.py 无 I/O 依赖)
- [x] 所有金额计算使用 Decimal
- [x] Code Review 通过

---

## 技术亮点

1. **订单生成时序**: ENTRY 成交后才生成 TP/SL，确保 RR 计算基于实际开仓价
2. **职责边界清晰**: OrderManager 管量，DynamicRiskManager 管价，无竞态条件
3. **多 TP 支持**: TP1-TP5 级别，各级别比例和 RR 目标可配置
4. **OCO 原子性**: 基于仓位数量统一判定，防止中间状态泄露
5. **Decimal 精度**: 所有金融计算使用 `decimal.Decimal`，无 float 污染

---

## 待办事项 (延期至 Phase 5)

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **分批建仓 (DCA)** | 多批次入场策略，需要独立成本计算状态机 | P2 |

**追踪文件**: `docs/designs/phase4-pending-dca-feature.md`

---

## 后续任务 (Phase 5+)

Phase 4 完成后，系统已具备完整的订单编排能力。后续任务包括：

- **Phase 5**: 实盘集成 - 对接真实交易所 API，启用 reduce_only 字段，实现分批建仓
- **Phase 6**: 前端适配 - 可视化回测结果和订单策略配置界面

---

## 相关 Git 提交

```
commit c2b22f3
Author: <user>
Date:   2026-03-30

    feat(v3): Phase 4 订单编排实现

    交付成果:
    - 新增 OrderManager 类 (src/domain/order_manager.py)
    - OrderStrategy 类支持多级别止盈 (1-5 级)
    - Order 模型添加 parent_order_id 和 oco_group_id 字段
    - Backtester 集成 OrderManager
    - 25 个测试用例 (19 单元 + 6 集成)

    核心功能:
    1. 订单链生成：create_order_chain() 仅生成 ENTRY 订单
    2. 动态 TP/SL：ENTRY 成交后基于 actual_exec_price 生成
    3. OCO 逻辑：current_qty==0 时撤销所有挂单
    4. 多 TP 支持：TP1-TP5 级别，各级别比例可配置
    5. TP 价格计算：基于实际开仓价和 RR 倍数

    修复审查问题 (L2-03):
    - Backtester 硬编码 tp_targets，改为使用 strategy.tp_targets
    - OrderStrategy 添加 tp_targets 字段

    测试结果：128 个 v3 测试 100% 通过

    契约文件：docs/designs/phase4-order-orchestration-contract.md (v1.1)
    待办记录：docs/designs/phase4-pending-dca-feature.md (分批建仓延期至 Phase 5)
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## 相关文件位置

| 类别 | 文件路径 |
|------|----------|
| **契约表** | `docs/designs/phase4-order-orchestration-contract.md` |
| **核心实现** | `src/domain/order_manager.py` |
| **领域模型** | `src/domain/models.py` |
| **Backtester** | `src/application/backtester.py` |
| **单元测试** | `tests/unit/test_v3_order_manager.py` |
| **集成测试** | `tests/integration/test_v3_phase4_integration.py` |
| **完成报告** | `docs/v3/v3-phase4-complete-report.md` |

---

## Phase 4 配置示例

### 标准单 TP 策略

```python
OrderStrategy(
    id="std_single_tp",
    name="标准单 TP",
    tp_levels=1,
    tp_ratios=[Decimal('1.0')],
    tp_targets=[Decimal('1.5')],  # 1.5R 止盈
    initial_stop_loss_rr=Decimal('-1.0'),
    trailing_stop_enabled=True,
    oco_enabled=True,
)
```

### 多级别止盈策略

```python
OrderStrategy(
    id="multi_tp",
    name="多级别止盈",
    tp_levels=3,
    tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
    tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
    initial_stop_loss_rr=Decimal('-1.0'),
    trailing_stop_enabled=True,
    oco_enabled=True,
)
```

---

*报告生成时间：2026-03-30*
*盯盘狗 🐶 Phase 4 完成报告*
