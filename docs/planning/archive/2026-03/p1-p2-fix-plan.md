# P1/P2 问题修复执行计划

> **创建日期**: 2026-04-01
> **负责人**: @backend
> **优先级**: P1 (必须修复) / P2 (优化改进)
> **预计工时**: 6-8 小时

---

## 执行策略

| 级别 | 说明 | 本迭代完成 |
|------|------|------------|
| **P1** | 中等严重性问题，存在潜在风险 | ✅ 必须完成 |
| **P2** | 代码质量优化，可维护性改进 | ⏳ 视时间完成 |

---

## 问题详细分析

### P1 级问题 (必须修复)

#### P1-1: trigger_price 零值风险

**文件**: `src/domain/risk_manager.py`  
**行号**: 174  
**问题描述**: 
```python
current_trigger = sl_order.trigger_price or position.entry_price
```
当 `trigger_price` 为 `Decimal("0")` 时，会被判定为 falsy，错误地使用 `entry_price` 作为止损触发价，导致 Trailing Stop 计算错误。

**修复方案**:
```python
# 修复前
current_trigger = sl_order.trigger_price or position.entry_price

# 修复后
current_trigger = sl_order.trigger_price if sl_order.trigger_price is not None else position.entry_price
```

**风险等级**: 中 - 可能导致止损计算错误

---

#### P1-2: STOP_LIMIT 订单缺少价格偏差检查

**文件**: `src/application/capital_protection.py`  
**行号**: 184-202  
**问题描述**: 
`pre_order_check()` 方法仅对 `LIMIT` 订单检查价格偏差，但 `STOP_LIMIT` 订单同样需要检查限价单价格合理性。

**修复方案**:
在 `_check_price_reasonability()` 调用处添加对 `OrderType.STOP_LIMIT` 的检查：
```python
# 限价单 (LIMIT 或 STOP_LIMIT) 需要检查价格偏差
if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and price is not None:
    price_check, ticker_price, deviation = await self._check_price_reasonability(
        symbol=symbol,
        order_price=price,
    )
```

**风险等级**: 中 - 可能允许异常价格的 STOP_LIMIT 订单

---

#### P1-3: trigger_price 字段应从 CCXT 响应提取

**文件**: `src/infrastructure/exchange_gateway.py`  
**行号**: 1369  
**问题描述**: 
```python
trigger_price=None,  # CCXT 不直接返回 trigger_price
```
CCXT 实际上在 `order['info']['triggerPrice']` 或 `order['stopPrice']` 中返回触发价，当前代码硬编码为 `None` 导致信息丢失。

**修复方案**:
```python
# 尝试从多个可能的字段提取 trigger_price
trigger_price_raw = (
    raw_order.get('info', {}).get('triggerPrice')
    or raw_order.get('info', {}).get('stopPrice')
    or raw_order.get('stopPrice')
    or raw_order.get('triggerPrice')
)
trigger_price = Decimal(str(trigger_price_raw)) if trigger_price_raw else None
```

**风险等级**: 中 - 触发价信息丢失，影响前端展示和对账

---

### P2 级问题 (优化改进)

#### P2-1: 魔法数字配置化

**文件**: `src/domain/risk_manager.py`  
**行号**: 30-43  
**问题描述**: 
```python
trailing_percent: Decimal = Decimal('0.02')     # 2%
step_threshold: Decimal = Decimal('0.005')      # 0.5%
```
硬编码魔法数字，不利于配置管理和回测调优。

**修复方案**:
1. 创建 `RiskManagerConfig` Pydantic 类
2. 从配置文件加载参数
3. 支持策略级覆写

```python
class RiskManagerConfig(BaseModel):
    trailing_percent: Decimal = Decimal("0.02")
    step_threshold: Decimal = Decimal("0.005")
    breakeven_threshold: Decimal = Decimal("0.01")  # Breakeven 触发阈值 1%
```

**收益**: 可维护性提升，支持动态调参

---

#### P2-2: 类常量移到配置文件

**文件**: `src/application/capital_protection.py`  
**行号**: 65-67  
**问题描述**: 
```python
MIN_NOTIONAL = Decimal("5")  # 最小名义价值 5 USDT
PRICE_DEVIATION_THRESHOLD = Decimal("0.10")  # 10%
EXTREME_PRICE_DEVIATION_THRESHOLD = Decimal("0.20")  # 20%
```
交易所特定常量应配置化，支持不同交易所适配。

**修复方案**:
1. 移到 `config/core.yaml` 的 `capital_protection` 段
2. 支持按交易所配置（Binance/Bybit/OKX 最小名义价值不同）
3. 极端行情阈值支持动态调整

```yaml
# config/core.yaml
capital_protection:
  min_notional:
    binance: 5      # Binance 5 USDT
    bybit: 2        # Bybit 2 USDT
    okx: 5          # OKX 5 USDT
  price_deviation_threshold: "0.10"
  extreme_price_deviation_threshold: "0.20"
```

**收益**: 多交易所适配性提升

---

#### P2-3: 重复代码重构

**文件**: `src/infrastructure/exchange_gateway.py`  
**行号**: 多处  
**问题描述**: 
- 订单状态解析逻辑重复
- Decimal 转换逻辑重复
- 时间戳解析逻辑重复

**修复方案**:
1. 提取 `_parse_decimal()` 工具方法
2. 提取 `_parse_timestamp()` 工具方法
3. 提取 `_parse_order_status()` 为独立方法（已存在，但可优化）

```python
def _parse_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """安全解析 Decimal 值"""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        logger.warning(f"无法解析 Decimal 值：{value}")
        return default
```

**收益**: 代码复用率提升，可维护性增强

---

## 任务分解

| 任务 ID | 任务描述 | 负责人 | 预计工时 | 依赖 |
|---------|----------|--------|----------|------|
| Task 1 | P1-1 修复 - trigger_price 零值风险 | @backend | 0.5h | - |
| Task 2 | P1-2 修复 - STOP_LIMIT 价格偏差检查 | @backend | 1h | - |
| Task 3 | P1-3 修复 - trigger_price 字段提取 | @backend | 1h | - |
| Task 4 | P2-1 修复 - 魔法数字配置化 | @backend | 1.5h | Task 1-3 |
| Task 5 | P2-2 修复 - 类常量配置化 | @backend | 1.5h | Task 1-3 |
| Task 6 | P2-3 修复 - 重复代码重构 | @backend | 1.5h | Task 1-3 |
| Task 7 | 测试验证 - 编写修复验证测试 | @qa | 1.5h | Task 1-6 |
| Task 8 | 代码审查 - P1/P2 修复质量把关 | @reviewer | 1h | Task 7 |

---

## 时间安排

| 时间 | 任务 | 负责人 |
|------|------|--------|
| **Day 1 上午** | Task 1-3 (P1 问题修复) | @backend |
| **Day 1 下午** | Task 4-6 (P2 问题修复) | @backend |
| **Day 2 上午** | Task 7 (测试验证) | @qa |
| **Day 2 下午** | Task 8 (代码审查) + 回归测试 | @reviewer |

**预计完成时间**: 2026-04-02 下班前

---

## 测试策略

### 单元测试

| 修复项 | 测试用例 | 验证方式 |
|--------|----------|----------|
| P1-1 | `test_trailing_stop_zero_trigger` | 模拟 trigger_price=0 场景 |
| P1-2 | `test_stop_limit_price_deviation_check` | 验证 STOP_LIMIT 订单价格检查 |
| P1-3 | `test_trigger_price_extraction` | 验证 CCXT 响应中 trigger_price 提取 |
| P2-1 | `test_risk_manager_config_loading` | 验证配置加载 |
| P2-2 | `test_capital_protection_config_override` | 验证配置覆写 |
| P2-3 | `test_decimal_parsing_edge_cases` | 验证 Decimal 解析边界情况 |

### 集成测试

- 现有 E2E 测试回归（103 个测试用例）
- Phase 5 实盘测试回归（Window 1-4）

### 验收标准

- 所有新增测试用例 100% 通过
- 现有测试回归 100% 通过
- 代码覆盖率不下降

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| P1-3 CCXT 字段名变更 | 低 | 中 | 多字段回退解析，记录日志 |
| P2-1/2 配置不兼容 | 低 | 低 | 保留默认值，向后兼容 |
| P2-3 重构引入回归 | 中 | 中 | 完整回归测试覆盖 |
| 时间不足 P2 延期 | 中 | 低 | P2 可延至下一迭代 |

---

## 回滚方案

如修复引入严重问题：

1. **代码回滚**: `git revert <commit-hash>`
2. **配置回滚**: 恢复 `config/core.yaml` 到修复前版本
3. **热修复**: 如仅配置问题，直接修改配置无需代码回滚

---

## 交付清单

### 代码修改

- [ ] `src/domain/risk_manager.py` - P1-1, P2-1
- [ ] `src/application/capital_protection.py` - P1-2, P2-2
- [ ] `src/infrastructure/exchange_gateway.py` - P1-3, P2-3
- [ ] `config/core.yaml` - P2-1, P2-2 配置段
- [ ] `src/domain/risk_manager.py` - 新增 `RiskManagerConfig` 类

### 测试文件

- [ ] `tests/unit/test_risk_manager.py` - 新增 P1-1 测试
- [ ] `tests/unit/test_capital_protection.py` - 新增 P1-2 测试
- [ ] `tests/unit/test_exchange_gateway.py` - 新增 P1-3 测试

### 文档更新

- [ ] `docs/planning/p1-p2-fix-plan.md` (本文档) - 执行计划
- [ ] `docs/planning/progress.md` - 进度日志
- [ ] `docs/planning/findings.md` - 技术发现记录

---

## 验收标准

### P1 修复验收

- [ ] P1-1: Trailing Stop 在 trigger_price=0 时不崩溃
- [ ] P1-2: STOP_LIMIT 订单价格偏差>10% 时被拒绝
- [ ] P1-3: CCXT 响应含 triggerPrice 时正确解析

### P2 修复验收（可选）

- [ ] P2-1: RiskManagerConfig 可从配置加载
- [ ] P2-2: 最小名义价值可从配置覆写
- [ ] P2-3: _parse_decimal 工具方法被复用

### 测试验收

- [ ] 新增测试用例≥6 个
- [ ] 回归测试 100% 通过
- [ ] 代码覆盖率不下降

---

*最后更新：2026-04-01*
