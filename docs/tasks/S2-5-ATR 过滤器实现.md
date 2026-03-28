# S2-5: ATR 过滤器核心逻辑实现

## 任务概述

**优先级**: 🔴 最高优先级

**目标**: 完成 ATR 过滤器的核心检查逻辑，解决 Pinbar 止损过近问题

**预计工作量**: 4-6 小时

---

## 问题背景

### 当前症状

历史信号数据显示止损距离异常小：

| 信号 | 入场价 | 止损价 | 差价 | 止损比例 | 问题 |
|------|--------|--------|------|----------|------|
| BNB/USDT 15m SHORT | 644.94 | 644.95 | 0.01 | **0.0016%** | ⚠️ 太近 |
| BNB/USDT 1h SHORT | 644.94 | 644.95 | 0.01 | **0.0016%** | ⚠️ 太近 |
| BNB/USDT 15m LONG | 645.39 | 645.38 | 0.01 | **0.0015%** | ⚠️ 太近 |
| SOL/USDT 15m LONG | 92.020 | 92.010 | 0.01 | **0.0109%** | ⚠️ 太近 |
| BTC/USDT 15m LONG | 70833.10 | 70833.00 | 0.10 | **0.0001%** | ⚠️ 太近 |

**正常交易**的止损距离通常在 **1%~3%** 以上，而当前系统仅为 **0.0001%~0.01%**。

### 根本原因

1. **Pinbar 检测只看比例，不看绝对波幅**
   - `wick_ratio >= 0.6` 且 `body_ratio <= 0.3` 即可通过
   - 十字星（body_ratio ≈ 0）也能通过检测

2. **ATR 过滤器是占位符实现**
   - `AtrFilterDynamic.check()` 始终返回 `passed=True`
   - 没有实际的 ATR 阈值检查

3. **止损计算没有缓冲空间**
   - LONG: `stop_loss = kline.low`
   - SHORT: `stop_loss = kline.high`
   - 没有添加 ATR 或固定百分比缓冲

---

## 技术方案

### 方案 A：完善 ATR 过滤器（推荐）

在 `AtrFilterDynamic.check()` 中实现真正的波幅检查：

```python
def check(self, pattern: PatternResult, context: FilterContext) -> TraceEvent:
    if not self._enabled:
        return TraceEvent(node_name=self.name, passed=True, reason="filter_disabled")

    kline = context.kline
    atr = self._get_atr(kline.symbol, kline.timeframe)

    if atr is None:
        return TraceEvent(node_name=self.name, passed=False, reason="atr_data_not_ready")

    # 计算 K 线波幅与 ATR 的比率
    candle_range = kline.high - kline.low
    min_range = atr * self._min_atr_ratio

    if candle_range < min_range:
        return TraceEvent(
            node_name=self.name,
            passed=False,
            reason="insufficient_volatility",
            metadata={
                "candle_range": float(candle_range),
                "atr": float(atr),
                "min_required": float(min_range),
                "ratio": float(candle_range / atr),
            }
        )

    return TraceEvent(
        node_name=self.name,
        passed=True,
        reason="volatility_sufficient",
        metadata={
            "candle_range": float(candle_range),
            "atr": float(atr),
            "ratio": float(candle_range / atr),
        }
    )
```

### 方案 B：止损计算添加 ATR 缓冲（可选增强）

在 `RiskCalculator.calculate_stop_loss()` 中添加缓冲：

```python
def calculate_stop_loss(self, kline: KlineData, direction: Direction, atr: Decimal = None) -> Decimal:
    if direction == Direction.LONG:
        stop_loss = kline.low
        if atr:
            stop_loss = stop_loss - (atr * Decimal("0.5"))  # 0.5 倍 ATR 缓冲
    else:
        stop_loss = kline.high
        if atr:
            stop_loss = stop_loss + (atr * Decimal("0.5"))

    return self._quantize_price(stop_loss, kline.close)
```

### 方案 C：最小止损距离限制（辅助方案）

```python
MIN_STOP_LOSS_PERCENT = Decimal("0.005")  # 最小 0.5% 止损

if direction == Direction.LONG:
    stop_loss = kline.low
    min_stop = entry_price * (Decimal(1) - MIN_STOP_LOSS_PERCENT)
    stop_loss = min(stop_loss, min_stop)
```

---

## 实施步骤

### Step 1: 实现 ATR 过滤器核心逻辑

**文件**: `src/domain/filter_factory.py`

修改 `AtrFilterDynamic.check()` 方法（第 387-401 行）

**测试**:
```python
def test_atr_filter_rejects_low_volatility():
    # 创建小波幅 K 线
    kline = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000,
        open=Decimal("100"),
        high=Decimal("100.01"),  # 波幅仅 0.01
        low=Decimal("99.99"),
        close=Decimal("100"),
        volume=Decimal("1000"),
    )

    # ATR 假设为 1.0，min_atr_ratio=0.5，则最小波幅要求=0.5
    # 实际波幅 0.02 < 0.5，应该被拒绝
    filter = AtrFilterDynamic(period=14, min_atr_ratio=Decimal("0.5"), enabled=True)
    # 预先设置 ATR 值
    filter._atr_values["BTC/USDT:USDT"] = [Decimal("1.0")] * 14

    context = FilterContext(kline=kline, ...)
    result = filter.check(pattern, context)

    assert result.passed == False
    assert result.reason == "insufficient_volatility"
```

### Step 2: 确保 update_state() 正确更新 ATR 数据

**文件**: `src/domain/filter_factory.py`

验证 `AtrFilterDynamic.update_state()` 方法（第 349-371 行）正确计算 True Range 和 ATR。

### Step 3: 添加单元测试

**文件**: `tests/unit/test_filter_factory.py`

新增测试类 `TestAtrFilterDynamic`：
- `test_atr_filter_disabled_always_passes`
- `test_atr_filter_rejects_low_volatility`
- `test_atr_filter_accepts_normal_volatility`
- `test_atr_filter_returns_metadata`
- `test_atr_filter_edge_case_candle_range_equals_min`

### Step 4: 集成测试

**文件**: `tests/integration/test_atr_filter_e2e.py`

创建端到端测试：
- 使用真实 K 线数据
- 验证十字星形态被 ATR 过滤器正确拒绝
- 验证正常 Pinbar 能通过过滤器

### Step 5: 可选 - 止损计算添加 ATR 缓冲

**文件**: `src/domain/risk_calculator.py`

如果 Step 1-4 后止损距离仍不够，考虑在 `calculate_stop_loss()` 中添加 ATR 缓冲。

### Step 6: 配置文档更新

**文件**: `config/core.yaml`

添加 ATR 过滤器默认配置：
```yaml
atr_filter:
  enabled: true
  period: 14
  min_atr_ratio: 0.5  # K 线波幅至少是 ATR 的 50%
```

---

## 验收标准

- [ ] ATR 过滤器能正确拒绝波幅 < min_atr_ratio × ATR 的 K 线
- [ ] 十字星/一字线形态不再产生信号
- [ ] 止损距离从 0.001% 提升到 0.5%~1% 级别
- [ ] 单元测试新增 5+ 个，覆盖率 100%
- [ ] 集成测试验证端到端流程
- [ ] 所有现有测试仍通过（回归测试）

---

## 相关文件

- `src/domain/filter_factory.py` - AtrFilterDynamic 实现
- `src/domain/risk_calculator.py` - 止损计算逻辑
- `src/domain/logic_tree.py` - FilterConfig 定义
- `tests/unit/test_filter_factory.py` - 过滤器测试
- `config/core.yaml` - 过滤器配置

---

## 技术笔记

### ATR 计算逻辑

```python
# True Range 计算
true_range = max(
    kline.high - kline.low,
    abs(kline.high - prev_close),
    abs(kline.low - prev_close)
)

# Simple ATR（当前实现）
atr = sum(recent_true_ranges[-period:]) / period

# 可选：Wilder's Smoothing（更平滑）
atr = ((prev_atr * (period - 1)) + current_tr) / period
```

### 推荐参数配置

| 周期 | min_atr_ratio 建议值 | 说明 |
|------|---------------------|------|
| 15m | 0.3 ~ 0.5 | 短周期波动大，阈值可低 |
| 1h | 0.5 ~ 0.7 | 中等周期 |
| 4h+ | 0.7 ~ 1.0 | 长周期波动稳定，阈值可高 |

---

## 决策记录

### 2026-03-28: 任务创建

**决策**: 将 ATR 过滤器实现列为最高优先级

**原因**:
1. 直接影响信号质量和用户信任
2. 当前止损距离（0.001%）完全失去风险管理意义
3. 任何价格波动都会触发止损，用户体验极差

**参与者**: 用户（分析师）、AI 助手

---

## 附录：Pinbar 策略参数优化建议

### 问题背景

用户发现某些有效的 Pinbar 形态被系统过滤掉，特征是：
- 下影线占总长度的约 50%（当前要求≥60%）
- 实体位置居中（当前要求实体在顶部/底部 10% 区域内）

### 当前参数 vs 建议参数

| 参数 | 当前值 | 建议值 | 说明 |
|------|-------|-------|------|
| `min_wick_ratio` | 0.6 (60%) | 0.5 (50%) | 覆盖"下影线占一半"的形态 |
| `max_body_ratio` | 0.3 (30%) | 0.35 (35%) | 稍微放宽实体大小限制 |
| `body_position_tolerance` | 0.1 (10%) | 0.3 (30%) | 允许实体在中点偏上区域（≥55% 位置） |

### 实体位置计算验证

```python
# tolerance = 0.3 时的实体位置要求（看涨 Pinbar）
body_position >= (1 - tolerance - body_ratio / 2)
body_position >= (1 - 0.3 - 0.175)  # body_ratio=0.35
body_position >= 0.525
```

**效果**：实体中心在 52.5% 以上即可（中点偏上），而不是当前的 75% 以上。

### 实施建议

1. **先调整参数验证效果**：修改 `config/core.yaml` 中的 `pinbar_defaults`
2. **观察历史信号变化**：使用预览功能验证是否覆盖想要的形态
3. **根据实际效果微调**：如果信号过多则适当收紧，过少则适当放宽

### 相关文件

- `config/core.yaml` - Pinbar 默认配置
- `src/domain/strategy_engine.py:27-58` - `PinbarConfig` 类定义
- `src/domain/strategy_engine.py:144-229` - Pinbar 检测逻辑

---

*最后更新*: 2026-03-28（添加 Pinbar 参数优化建议）
