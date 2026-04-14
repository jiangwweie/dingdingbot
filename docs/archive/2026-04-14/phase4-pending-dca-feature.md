# Phase 4 待办事项 - 分批建仓功能

**创建日期**: 2026-03-30
**状态**: ⏳ 延期至 Phase 5
**优先级**: P2 (重要不紧急)

---

## 功能描述

**分批建仓 (Scale-In / DCA)** 允许策略分多个批次入场，每批有不同的入场条件和价格。

### 原始设计 (已移除)

```python
OrderStrategy(
    entry_batches=2,
    entry_ratios=[Decimal('0.6'), Decimal('0.4')],  # 60% / 40%
)
```

### 未解决的问题

| 问题 | 说明 | 复杂度 |
|------|------|--------|
| **入场条件定义** | 第二批 40% 何时入场？是固定价格挂单还是触发条件 (如跌破 X%) 补仓？ | 高 |
| **成本计算** | 多批次入场后，如何计算平均开仓价 (entry_price)？ | 中 |
| **止损计算基准** | SL 是基于第一批成本、平均成本、还是最后一批成本？ | 中 |
| **状态机复杂性** | 需要独立的批次状态追踪 (BatchState) | 高 |
| **与 TP 联动** | 多批次入场后，TP 如何计算？基于平均成本还是分批计算？ | 高 |

---

## 延期原因

1. **复杂度爆炸**: 分批建仓引入独立的成本计算状态机，会显著增加 Phase 4 的实现和测试复杂度

2. **核心功能聚焦**: Phase 4 应聚焦于多级别止盈 (Multi-TP) 和 OCO 逻辑的稳定性

3. **实盘关联性强**: 分批建仓策略与实盘网关的订单类型 (限价单、条件单) 强相关，更适合在 Phase 5 实盘集成时统一设计

---

## Phase 5 实现建议

### 建议方案：DCAStrategy 独立模块

```python
class DCAStrategy(BaseModel):
    """分批建仓策略 (Phase 5 实现)"""

    # 批次配置
    batches: List[DCAEntryBatch]

    # 触发条件类型
    trigger_type: Literal["price_level", "percentage_drop", "indicator_signal"]

    # 成本计算模式
    cost_basis_mode: Literal["average", "last_batch"]


class DCAEntryBatch(BaseModel):
    """单个建仓批次"""
    batch_index: int                    # 批次序号 (1-based)
    ratio: Decimal                      # 该批次比例 (0.0-1.0)
    trigger_price: Optional[Decimal]    # 触发价格 (限价单)
    trigger_drop_percent: Optional[Decimal]  # 相对首批的跌幅百分比
    order_type: OrderType               # MARKET / LIMIT
```

### 配置示例

```python
# 马丁格尔 DCA 策略
DCAStrategy(
    batches=[
        DCAEntryBatch(batch_index=1, ratio=Decimal('0.5'), order_type=OrderType.MARKET),
        DCAEntryBatch(batch_index=2, ratio=Decimal('0.3'), trigger_drop_percent=Decimal('-2.0')),
        DCAEntryBatch(batch_index=3, ratio=Decimal('0.2'), trigger_drop_percent=Decimal('-4.0')),
    ],
    trigger_type="percentage_drop",
    cost_basis_mode="average",
)
```

---

## 依赖关系

| 依赖模块 | 说明 |
|---------|------|
| **OrderManager (Phase 4)** | 订单编排基础框架 |
| **Position 成本计算** | 需要扩展 Position 模型支持多批次成本追踪 |
| **实盘网关 (Phase 5)** | 支持限价单、条件单的类型 |

---

## 验收标准 (Phase 5)

- [ ] 支持 2-5 个建仓批次
- [ ] 支持限价单和市价单混合
- [ ] 平均成本计算正确
- [ ] SL 基于平均成本计算
- [ ] TP 基于平均成本计算
- [ ] 单元测试覆盖率 ≥ 95%
- [ ] 集成测试覆盖所有批次组合

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `docs/designs/phase4-order-orchestration-contract.md` | Phase 4 契约表 (已移除 entry_batches) |
| `src/domain/models.py` | Position 模型 (需扩展成本计算) |

---

## 变更记录

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-03-30 | 从 Phase 4 移除，延期至 Phase 5 | - |

---

*此文档追踪因复杂度原因延期实现的功能，确保后续迭代不会遗漏。*
