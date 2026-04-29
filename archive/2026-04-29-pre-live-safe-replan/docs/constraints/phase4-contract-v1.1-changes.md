# Phase 4 契约表 v1.1 修订报告

**创建日期**: 2026-03-30
**修订版本**: v1.1
**修订性质**: 重大修订 (修复 4 个架构问题)

---

## 修订摘要

本次修订源于用户 @jiangwei 对 v1.0 契约表的深度评审，发现了 4 个跨模块边界冲突和实盘参数定义缺失问题。修订后契约表与 Phase 2/Phase 3 无缝衔接，消除了架构竞态和实盘盲区。

---

## 问题与修复对照表

### 🔴 高优先级问题

| 问题 | 原设计缺陷 | 修复方案 | 影响范围 |
|------|----------|---------|---------|
| **SL 订单数量维护竞态** | Phase 3 DynamicRiskManager 和 Phase 4 OrderManager 都在修改 SL 的 `requested_qty`，产生竞态条件 | 职责重划：OrderManager 负责 SL 数量同步，DynamicRiskManager 仅负责 SL 价格调整 (Breakeven/Trailing) | 1.3 节职责边界声明、4.3 节 OCO 逻辑 |
| **TP/SL 价格锚点错误** | 在 ENTRY 成交前按预期 `entry_price` 计算 TP/SL 价格，实盘因滑点会导致 RR 计算错误 | 修改订单链生成时序：`create_order_chain()` 仅生成 ENTRY 订单，`handle_order_filled()` 在 ENTRY 成交后基于 `actual_exec_price` 动态生成 TP/SL | 3.3 节方法签名、附录 B 示例 |

### 🟡 中优先级问题

| 问题 | 原设计缺陷 | 修复方案 | 影响范围 |
|------|----------|---------|---------|
| **分批建仓配置缺失** | `entry_batches` 和 `entry_ratios` 字段缺少后续批次入场条件定义，复杂度高 | 移除分批建仓配置，延期至 Phase 5 实现；创建 `phase4-pending-dca-feature.md` 追踪待办 | 2.2 节 OrderStrategy 字段、6.3 节示例、测试用例 |
| **OCO 逻辑不完整** | OCO 判定条件仅检查"是否最后一个 TP"，未基于仓位数量统一判定 | 明确 OCO 基于 `position.current_qty` 判定：==0 时撤销所有挂单，>0 时更新 SL 数量 | 4.3 节 OCO 逻辑、测试用例 |

---

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `docs/designs/phase4-pending-dca-feature.md` | 分批建仓功能待办记录 (延期至 Phase 5) |

### 修改文件

| 文件 | 变更说明 |
|------|---------|
| `docs/designs/phase4-order-orchestration-contract.md` | v1.0 → v1.1 (4 个重大修订) |

---

## 核心变更详解

### 1. 职责边界声明 (新增 1.3 节)

**修订前**: 无明确职责划分

**修订后**:
```markdown
### 1.3 职责边界声明

**OrderManager (Phase 4) vs DynamicRiskManager (Phase 3)**:

| 模块 | 负责领域 | 具体职责 |
|------|---------|---------|
| **OrderManager** | **量 (Quantity)** | - 任何 TP 成交后，立即更新 SL 的 `requested_qty`<br>- OCO 逻辑：仓位归零时撤销所有挂单<br>- ENTRY 成交后动态生成 TP/SL 订单 |
| **DynamicRiskManager** | **价 (Price)** | - 监听 TP1 首次成交事件<br>- 执行 Breakeven (SL 价格上移至 entry_price)<br>- 执行 Trailing Stop (追踪水位线)<br>- **不修改** `requested_qty` |

**声明**: OrderManager 接管 SL 订单的数量同步职责。DynamicRiskManager 仅负责 SL 订单的价格调整 (Breakeven/Trailing)，不再修改 `requested_qty`。
```

---

### 2. 订单链生成时序修订 (3.3 节)

**修订前**:
```python
def create_order_chain(...) -> List[Order]:
    """创建订单链"""
    # 直接生成 ENTRY + TP + SL
```

**修订后**:
```python
def create_order_chain(...) -> List[Order]:
    """
    创建订单链 - 仅生成 ENTRY 订单

    注意：TP/SL 订单将在 ENTRY 成交后，由 handle_order_filled() 动态生成
    理由：实盘场景中，ENTRY 订单由于滑点会导致实际开仓价 (average_exec_price) 偏离预期
         必须在 ENTRY 成交后，以实际开仓价为锚点计算 TP/SL 价格
    """
    # 只返回 ENTRY 订单
```

---

### 3. OCO 逻辑完善 (4.3 节)

**修订前**:
```python
if position.current_qty <= Decimal('0'):
    # 撤销所有剩余挂单
```

**修订后**:
```python
# 核心判定：基于仓位剩余数量
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

**职责边界声明**:
- **OrderManager**: 负责 SL 订单的 `requested_qty` 更新 (数量同步)
- **DynamicRiskManager**: 负责 SL 订单的 `trigger_price` 调整 (Breakeven/Trailing)

---

### 4. OrderStrategy 字段调整 (2.2 节 / 5.2 节)

**删除字段**:
- `entry_batches: int` - 延期至 Phase 5
- `entry_ratios: List[Decimal]` - 延期至 Phase 5
- `initial_stop_loss: Optional[Decimal]` - 替换为 `initial_stop_loss_rr`

**新增字段**:
- `initial_stop_loss_rr: Optional[Decimal]` - 初始止损 RR 倍数 (如 -1.0 表示亏损 1R)

**注释说明**:
```python
# 注意：entry_batches 和 entry_ratios 已移除，延期至 Phase 5 实现
# 参考：docs/designs/phase4-pending-dca-feature.md
```

---

### 5. 测试用例调整 (9.1 节 / 9.2 节)

**删除测试**:
- UT-003: OrderStrategy 分批建仓配置
- UT-005: generate_order_chain 单 TP (旧)
- UT-006: generate_order_chain 多 TP (旧)
- IT-003: 分批建仓完整流程

**新增测试**:
- UT-004: create_order_chain 仅生成 ENTRY
- UT-005: handle_order_filled ENTRY 成交 (基于 actual_exec_price)
- UT-008: handle_order_filled TP1 成交 (更新 SL 数量)
- UT-010: apply_oco_logic 完全平仓 (current_qty==0)
- UT-011: apply_oco_logic 部分平仓 (更新 SL 数量)
- UT-014: 职责边界验证
- IT-006: 职责边界验证

---

## 附录 B 示例更新

**修订前** (错误示范):
```
生成订单:
1. ENTRY: 1.0 BTC @ 65000
2. TP1: 0.5 BTC @ 66000 (RR=1.0)
...
```

**修订后** (正确示范):
```
执行流程:

1. OrderManager.create_order_chain() 仅生成 ENTRY 订单:
   ENTRY: 1.0 BTC @ 市价

2. 撮合引擎执行 ENTRY 订单:
   实际成交价 = 65065 (滑点 0.1%)
   average_exec_price = 65065

3. ENTRY 成交后，OrderManager.handle_order_filled() 动态生成:
   - TP1: 0.5 BTC @ 66065 (RR=1.0: 65065 + 1.0 × (65065 - 64000))
   - TP2: 0.3 BTC @ 67065 (RR=2.0)
   - TP3: 0.2 BTC @ 68065 (RR=3.0)
   - SL: 1.0 BTC @ 64000 (基于 actual_entry 计算)

**关键点**: TP/SL 价格基于实际开仓价 (65065) 计算，而非信号预期价 (65000)，确保 RR 计算准确。
```

---

## 影响评估

### 对 Phase 4 开发的影响

| 影响领域 | 说明 |
|---------|------|
| **实现复杂度** | 降低 (移除了分批建仓) |
| **代码行数** | 减少约 15% (分批建仓逻辑移除) |
| **测试用例** | 从 15 单元 +6 集成 调整为 14 单元 +6 集成 |
| **开发周期** | 缩短约 0.5-1 天 |

### 对 Phase 2/3 的影响

| 模块 | 影响 |
|------|------|
| **Phase 2 (撮合引擎)** | 无影响 |
| **Phase 3 (风控状态机)** | 需修改 DynamicRiskManager，移除 SL 数量更新逻辑 |

### 对 Backtester 集成的影响

Backtester 集成流程需调整：
```python
# 修订前
order_chain = order_manager.create_order_chain(...)  # 返回 ENTRY+TP+SL
active_orders.extend(order_chain)

# 修订后
entry_orders = order_manager.create_order_chain(...)  # 仅返回 ENTRY
active_orders.extend(entry_orders)
# TP/SL 将由 handle_order_filled() 在 ENTRY 成交后动态生成
```

---

## 待办追踪

### Phase 5 待实现功能

| 功能 | 说明 | 优先级 |
|------|------|--------|
| **分批建仓 (DCA)** | 多批次入场策略，需要独立成本计算状态机 | P2 |

**追踪文件**: `docs/designs/phase4-pending-dca-feature.md`

---

## 评审结论

✅ **修订通过**，可以进入 Phase 4 开发阶段。

**下一步行动**:
1. 确认契约表 v1.1
2. 启动 Phase 4 任务分解
3. 并行开发 (Backend + QA)
4. 代码审查
5. 测试执行
6. Git 提交

---

*报告生成时间：2026-03-30*
