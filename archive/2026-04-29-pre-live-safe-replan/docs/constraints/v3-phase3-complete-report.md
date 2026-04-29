# Phase 3: 风控状态机 - 完成报告

**创建日期**: 2026-03-30
**状态**: ✅ 已完成
**测试通过率**: 100% (23/23)
**Git 提交**: `629c759`

---

## 执行摘要

Phase 3 风控状态机开发任务已全面完成。实现了 v3.0 PMS 模式的风控核心逻辑，包括：

1. ✅ **DynamicRiskManager 核心类** - 风控状态机实现 (~220 行)
2. ✅ **Breakeven 逻辑** - TP1 成交后 SL 上移至开仓价
3. ✅ **Trailing Stop** - 水位线追踪 + 阶梯频控
4. ✅ **watermark_price 字段** - 抽象化极值价格追踪
5. ✅ **保护损底线** - LONG≥entry_price / SHORT≤entry_price
6. ✅ **Reduce Only 约束** - 防止 TP2+SL 并存时保证金不足
7. ✅ **Backtester 集成** - 风控状态机在回测器中运行

---

## 交付成果

### 1. 新增文件

| 文件 | 说明 | 行数 |
|------|------|------|
| `src/domain/risk_manager.py` | DynamicRiskManager 核心实现 | ~220 行 |
| `tests/unit/test_risk_state_machine.py` | 单元测试 (16 个) | ~670 行 |
| `tests/integration/test_v3_phase3_integration.py` | 集成测试 (7 个) | ~450 行 |
| `docs/designs/phase3-risk-state-machine-contract.md` | 契约表 (v1.1) | ~450 行 |

### 2. 修改文件

| 文件 | 变更说明 |
|------|----------|
| `src/domain/models.py` | Order 添加 `reduce_only` 字段 |
| `src/application/backtester.py` | 集成 DynamicRiskManager 调用 |
| `src/infrastructure/v3_orm.py` | watermark_price ORM 转换修复 |

### 3. 测试覆盖

**单元测试 (16 个)**:
| 测试 ID | 测试场景 | 状态 |
|---------|----------|------|
| UT-001 | TP1 成交触发 Breakeven | ✅ |
| UT-002 | LONG 仓位刷新水位线 | ✅ |
| UT-003 | SHORT 仓位刷新水位线 | ✅ |
| UT-004 | Trailing Stop 计算 (LONG) | ✅ |
| UT-005 | Trailing Stop 计算 (SHORT) | ✅ |
| UT-006 | 阶梯频控 - 不满足条件 | ✅ |
| UT-007 | 阶梯频控 - 满足条件 | ✅ |
| UT-008 | 保护损底线 (LONG) | ✅ |
| UT-009 | 保护损底线 (SHORT) | ✅ |
| UT-010 | 已平仓仓位不处理 | ✅ |
| UT-011 | 无 SL 订单防御处理 | ✅ |
| UT-012 | Decimal 精度保护 | ✅ |
| UT-013 | Reduce Only 约束 | ✅ |
| Edge-001 | Watermark None 处理 | ✅ |
| Edge-002 | TP1 未成交不 Breakeven | ✅ |
| Edge-003 | Breakeven 只执行一次 | ✅ |

**集成测试 (7 个)**:
| 测试 ID | 测试场景 | 状态 |
|---------|----------|------|
| IT-001 | 完整交易流程：开仓 → TP1 → Breakeven → Trailing → 平仓 | ✅ |
| IT-002 | 直接 SL 打损 (无 TP1) | ✅ |
| IT-003 | 多笔 TP1 分批成交 | ✅ |
| IT-004 | Trailing 多次触发 | ✅ |
| ADD-001 | SHORT 仓位完整流程 | ✅ |
| ADD-002 | 水位线只朝盈利方向移动 | ✅ |
| ADD-003 | 风控管理器状态隔离 | ✅ |

**总计**: 23/23 通过 (100%)

---

## 核心设计要点

### 1. Breakeven 逻辑 (TP1 成交后)

```python
# 数量对齐：与剩余仓位对齐
sl_order.requested_qty = position.current_qty

# 上移止损至开仓价 (Breakeven)
sl_order.trigger_price = position.entry_price

# 属性变异：激活移动追踪
sl_order.order_type = OrderType.TRAILING_STOP
sl_order.exit_reason = "BREAKEVEN_STOP"
```

### 2. 水位线更新

```python
# LONG: 追踪入场后的最高价
if position.watermark_price is None or kline.high > position.watermark_price:
    position.watermark_price = kline.high

# SHORT: 追踪入场后的最低价
if position.watermark_price is None or kline.low < position.watermark_price:
    position.watermark_price = kline.low
```

### 3. Trailing Stop 计算 (LONG)

```python
# 理论止损价 = 水位线 * (1 - trailing_percent)
theoretical_trigger = position.watermark_price * (Decimal('1') - self.trailing_percent)

# 阶梯判定：新止损价必须比当前价高出 step_threshold
min_required_price = current_trigger * (Decimal('1') + self.step_threshold)

if theoretical_trigger >= min_required_price:
    # 更新止损价，但不低于 entry_price
    sl_order.trigger_price = max(position.entry_price, theoretical_trigger)
```

### 4. T+1 时序声明

```python
# T+1 时序声明：TP1 引发的 SL 修改在下一根 K 线生效
# 理由：基于极端悲观撮合原则 (SL 优先)，逻辑自洽
# 假设：SL 优先于 TP1 发生，所以 TP1 触发时低点已经过去
dynamic_risk_manager = DynamicRiskManager(...)
for position in positions_map.values():
    if not position.is_closed and position.current_qty > 0:
        dynamic_risk_manager.evaluate_and_mutate(kline, position, active_orders)
```

---

## 审查问题修复

### L2-001: watermark_price ORM 转换语义混淆

**问题**: `position_domain_to_orm()` 中使用 `domain.watermark_price or domain.entry_price`，导致 None 语义丢失

**修复**:
```python
# 修复前
watermark_price=domain.watermark_price or domain.entry_price

# 修复后
watermark_price=domain.watermark_price  # 直接传递，保留 None 语义
```

**注释说明**:
```python
"""
Position (领域模型) -> PositionORM

注意：watermark_price 字段语义
- 领域模型：None 表示"尚未更新"，有值表示"已更新"
- ORM 模型：nullable=True，允许 NULL 存储
- 转换策略：保留 None 语义，直接传递 (不填充 entry_price)
"""
```

### L3-001: reduceOnly 字段缺失

**问题**: 契约表要求平仓单携带 `reduceOnly=True`，但 Order 模型未定义此字段

**修复**:
```python
# Order 模型新增字段
reduce_only: bool = Field(default=False, description="仅减仓平仓 (实盘约束)")

# 契约表引用注释
# 契约表 3.1: 所有平仓单 (TP/SL) 必须携带 reduceOnly=True，防止保证金不足错误
# 注意：当前回测模拟场景中未实际使用此字段，留待实盘网关集成时启用
```

**说明**: 此字段在回测场景中未实际使用，待 Phase 5 实盘网关集成时启用。

---

## 验收标准

### 功能验收

- [x] DynamicRiskManager 类实现完成
- [x] TP1 成交后 Breakeven 逻辑正确
- [x] Trailing Stop 计算正确
- [x] 阶梯频控逻辑正确
- [x] 保护损底线校验正确
- [x] Reduce Only 约束实现 (字段添加)
- [x] T+1 时序声明在代码中体现

### 测试验收

- [x] 单元测试覆盖率 100% (16/16 通过)
- [x] 集成测试 100% 通过 (7/7 通过)
- [x] 所有边界 case 测试通过

### 代码质量

- [x] 领域层纯净 (risk_manager.py 无 I/O 依赖)
- [x] 所有金额计算使用 Decimal
- [x] Code Review 通过

---

## 技术亮点

1. **状态机设计**: 清晰的状态转移 (初始 → Breakeven → Trailing → 平仓)
2. **阶梯频控**: 防止 API 限流的智能更新策略
3. **水位线抽象**: `watermark_price` 统一处理 LONG/SHORT 极值追踪
4. **T+1 时序**: 明确的时序声明，避免单 K 线内突变争议
5. **防御性编程**: 无 SL 订单时静默返回，不抛异常
6. **Decimal 精度**: 所有金融计算使用 `decimal.Decimal`，无 float 污染

---

## 后续任务 (Phase 4+)

Phase 3 完成后，系统已具备完整的风控状态机能力。后续任务包括：

- **Phase 4**: 订单编排 - 支持多级别止盈 (TP2/TP3)、分批建仓等复杂订单策略
- **Phase 5**: 实盘集成 - 对接真实交易所 API，启用 reduce_only 字段
- **Phase 6**: 前端适配 - 可视化回测结果和风控配置界面

---

## 相关 Git 提交

```
commit 629c759
Author: <user>
Date:   2026-03-30

    feat(v3): Phase 3 风控状态机实现

    交付成果:
    - 新增 DynamicRiskManager 类 (src/domain/risk_manager.py)
    - Position 添加 watermark_price 字段
    - Backtester 集成风控状态机
    - ORM 模型更新 (v3_orm.py)
    - 23 个测试用例 (16 单元 + 7 集成)

    核心功能:
    1. Breakeven 逻辑：TP1 成交后 SL 上移至开仓价
    2. Trailing Stop：水位线追踪 + 阶梯频控
    3. 保护损底线：LONG≥entry/SHORT≤entry
    4. Reduce Only 约束：添加 reduce_only 字段

    修复审查问题:
    - L2-001: watermark_price ORM 转换保留 None 语义
    - L3-001: 添加 reduce_only 字段 (待实盘启用)

    测试结果：110 个 v3 测试 100% 通过

    契约文件：docs/designs/phase3-risk-state-machine-contract.md (v1.1)
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## 相关文件位置

| 类别 | 文件路径 |
|------|----------|
| **契约表** | `docs/designs/phase3-risk-state-machine-contract.md` |
| **核心实现** | `src/domain/risk_manager.py` |
| **领域模型** | `src/domain/models.py` |
| **Backtester** | `src/application/backtester.py` |
| **ORM 模型** | `src/infrastructure/v3_orm.py` |
| **单元测试** | `tests/unit/test_risk_state_machine.py` |
| **集成测试** | `tests/integration/test_v3_phase3_integration.py` |
| **完成报告** | `docs/v3/v3-phase3-complete-report.md` |

---

## Phase 3 配置参数

| 参数 | 默认值 | 说明 | 可调范围 |
|------|--------|------|----------|
| `trailing_percent` | 2% | 从最高价回撤 2% 后触发止损 | 0.5% ~ 5% |
| `step_threshold` | 0.5% | 新止损价必须比当前价高 0.5% 才更新 | 0.1% ~ 2% |

---

*报告生成时间：2026-03-30*
*盯盘狗 🐶 Phase 3 完成报告*
