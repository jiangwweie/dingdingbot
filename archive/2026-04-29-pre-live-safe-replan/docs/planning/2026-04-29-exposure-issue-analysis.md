# Exposure 无效问题深度分析

> **日期**: 2026-04-29
> **问题**: 为什么敞口（exposure）几乎没什么用？

---

## 1. 问题现象

### 1.1 数据对比

**相同 risk 不同 exposure 的 PnL 对比：**

| risk | exposure=1.0 | exposure=3.0 | 差异 |
|------|-------------|-------------|------|
| 0.50% | 2,113.27 USDT | 2,089.18 USDT | -1.1% |
| 1.00% | 3,280.54 USDT | 4,302.57 USDT | +31.2% |
| 1.50% | 9,519.31 USDT | 4,793.32 USDT | -49.7% |
| 2.00% | 14,490.19 USDT | 5,616.41 USDT | -61.2% |

**关键发现：**
- ❌ exposure 从 1.0 → 3.0，PnL **没有显著提升**
- ❌ 某些情况下，exposure=3.0 的 PnL **反而更低**
- ❌ exposure 参数似乎**没有发挥作用**

---

## 2. 根因分析

### 2.1 position_size=0 统计

**从日志中统计：**

```
position_size=0 出现次数: 2580 次
```

**原因分析：**

```
position_size=0 的原因统计：
  risk_amount <= 0: 2580 次
```

**结论：** 所有 position_size=0 都是因为 `risk_amount <= 0`

---

### 2.2 risk_calculator.py 逻辑分析

**关键代码（第 156-166 行）：**

```python
# Step 4: Calculate base risk amount using available balance
base_risk_amount = account.available_balance * max_loss_percent

# Step 5: Apply exposure limit - reduce risk if approaching limit
exposure_limited_risk = account.available_balance * available_exposure
risk_amount = min(base_risk_amount, exposure_limited_risk)

# If no risk budget available, return zero position
if risk_amount <= Decimal(0):
    logger.warning(f"[RISK_CALC] position_size=0: risk_amount <= 0 (base={base_risk_amount}, exposure_limited={exposure_limited_risk}, available_exposure={available_exposure})")
    return Decimal(0), 1
```

**问题所在：**

1. **base_risk_amount** = `available_balance * max_loss_percent`
   - 例如：10,000 * 0.005 = 50 USDT

2. **exposure_limited_risk** = `available_balance * available_exposure`
   - 例如：10,000 * 0.5 = 5,000 USDT（如果 available_exposure=0.5）

3. **risk_amount** = min(50, 5000) = 50 USDT

4. **问题：** exposure_limited_risk 几乎总是大于 base_risk_amount
   - 因为 available_exposure 通常 > max_loss_percent
   - 例如：available_exposure=0.5 vs max_loss_percent=0.005
   - 0.5 >> 0.005，所以 exposure 限制几乎不生效

---

### 2.3 核心问题

**exposure 限制的设计缺陷：**

```python
# 当前逻辑（错误）：
exposure_limited_risk = available_balance * available_exposure
risk_amount = min(base_risk_amount, exposure_limited_risk)

# 问题：
# - base_risk_amount = 10,000 * 0.005 = 50 USDT
# - exposure_limited_risk = 10,000 * 0.5 = 5,000 USDT
# - min(50, 5000) = 50 USDT
# - exposure 限制永远不生效！
```

**正确的逻辑应该是：**

```python
# 正确逻辑：
# exposure 限制应该限制的是 position_value，而不是 risk_amount
# position_value = position_size * entry_price
# position_size = risk_amount / stop_distance

# 方法 1：限制 position_value
max_position_value = available_balance * available_exposure
position_size = risk_amount / stop_distance
position_value = position_size * entry_price

if position_value > max_position_value:
    position_size = max_position_value / entry_price
```

---

## 3. 为什么 exposure=3.0 反而表现更差？

### 3.1 原因分析

**关键发现：**

1. **exposure 不影响 position_size 计算**
   - 因为 exposure_limited_risk >> base_risk_amount
   - exposure 限制几乎不生效

2. **exposure 影响的是 available_exposure**
   - available_exposure = max_total_exposure - current_exposure_ratio
   - 如果 current_exposure_ratio > max_total_exposure，available_exposure = 0
   - 导致 position_size=0

3. **exposure=3.0 允许更多并发持仓**
   - 但更多并发持仓 = 更高风险
   - 在 2023 年的恶劣市场环境下，更多持仓 = 更多亏损

### 3.2 数据验证

**exposure=1.0 vs exposure=3.0（risk=0.5%）：**

| Year | exposure=1.0 | exposure=3.0 | 差异 |
|------|-------------|-------------|------|
| 2023 | -2,797.01 | -3,307.71 | -18.3% |
| 2024 | +2,426.61 | +3,090.23 | +27.3% |
| 2025 | +3,434.33 | +3,350.09 | -2.5% |

**发现：**
- 2023 年：exposure=3.0 **亏损更多**（-18.3%）
- 2024 年：exposure=3.0 **盈利更多**（+27.3%）
- 2025 年：exposure=3.0 **盈利略少**（-2.5%）

**结论：**
- exposure=3.0 在**牛市**表现更好（2024）
- exposure=3.0 在**熊市**表现更差（2023）
- 但整体差异不大，因为 exposure 限制**根本没有生效**

---

## 4. 正确的 exposure 限制实现

### 4.1 当前实现的问题

**当前逻辑：**

```python
# Step 5: Apply exposure limit - reduce risk if approaching limit
exposure_limited_risk = account.available_balance * available_exposure
risk_amount = min(base_risk_amount, exposure_limited_risk)
```

**问题：**
- ❌ 混淆了 "风险金额" 和 "敞口金额"
- ❌ exposure 应该限制的是 position_value，而不是 risk_amount
- ❌ 导致 exposure 限制几乎不生效

### 4.2 正确实现

**方法 1：限制 position_value**

```python
# Step 1: Calculate base position size
base_risk_amount = account.available_balance * max_loss_percent
base_position_size = base_risk_amount / stop_distance

# Step 2: Calculate max position value based on exposure
max_position_value = account.total_balance * available_exposure

# Step 3: Calculate position size from max_position_value
max_position_size = max_position_value / entry_price

# Step 4: Take the minimum
position_size = min(base_position_size, max_position_size)
```

**方法 2：限制并发持仓数量**

```python
# Step 1: Calculate base position size
position_size = base_risk_amount / stop_distance

# Step 2: Check if adding this position would exceed exposure limit
new_total_value = current_total_position_value + (position_size * entry_price)
new_exposure_ratio = new_total_value / account.total_balance

if new_exposure_ratio > max_total_exposure:
    # Reduce position size to fit within exposure limit
    allowed_value = account.total_balance * max_total_exposure - current_total_position_value
    position_size = allowed_value / entry_price
```

---

## 5. 结论

### 5.1 为什么 exposure 几乎无效？

**根本原因：**

1. **设计缺陷：** exposure 限制的是 risk_amount，而不是 position_value
2. **数值差异：** available_exposure >> max_loss_percent，导致 exposure 限制永远不生效
3. **实际效果：** exposure 参数只影响 available_exposure 的计算，但不影响最终的 position_size

### 5.2 为什么 exposure=3.0 反而表现更差？

**原因：**

1. **exposure 不影响 position_size 计算**
2. **exposure 影响的是并发持仓数量**
3. **更多并发持仓 = 更高风险**
4. **在熊市（2023），更多持仓 = 更多亏损**

### 5.3 如何修复？

**建议：**

1. **修改 risk_calculator.py 的 exposure 限制逻辑**
   - 限制 position_value，而不是 risk_amount
   - 确保 exposure 限制真正生效

2. **重新运行 R1 搜索**
   - 使用修复后的逻辑
   - 预期 exposure 参数会有显著影响

3. **验证修复效果**
   - 对比 exposure=1.0 vs exposure=3.0 的 position_size 分布
   - 确认 exposure=3.0 的 position_size 确实更大

---

## 6. 影响评估

### 6.1 对 R1 搜索结果的影响

**当前结果：**
- ❌ exposure 参数几乎无效
- ❌ 最优配置的 exposure=1.0（因为 exposure 更大反而表现更差）

**修复后预期：**
- ✅ exposure 参数会有显著影响
- ✅ exposure=3.0 的 PnL 会显著高于 exposure=1.0
- ✅ 需要重新搜索最优配置

### 6.2 对策略的影响

**当前策略：**
- ❌ exposure 限制形同虚设
- ❌ 无法有效控制总敞口风险

**修复后：**
- ✅ exposure 限制真正生效
- ✅ 可以有效控制总敞口风险
- ✅ 策略风险更加可控

---

*分析完成时间: 2026-04-29*
*性质: research-only，不改 src，不改 runtime，不提交 git*
