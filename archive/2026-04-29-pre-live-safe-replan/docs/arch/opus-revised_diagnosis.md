# 🔄 修正诊断：数据推翻了之前所有建议

> [!CAUTION]
> 你的分析师跑出的数据证明：**我之前的 P0 建议（score ≥ 0.7 过滤）会让情况更糟**。
> 高分信号胜率 28.4%，中分信号胜率 45.4%。分数越高越亏。

---

## 📊 三个颠覆性发现

### 发现 1：分数是**反向指标**

| 分数区间 | 信号数 | 胜率 | 平均盈亏比 |
|----------|--------|------|-----------|
| 0.7-1.0 (高分) | 252 | **28.4%** ❌ | -0.43 |
| 0.5-0.7 (中分) | 46 | **45.4%** ✅ | -0.09 |

**高分信号反而更差**。如果按我之前的建议过滤 score < 0.7，你会**只保留最差的信号**。

### 发现 2：实际胜率只有 38.6%，不是 64%

| 指标 | 分析师说的 | 实际数据 |
|------|-----------|---------|
| 胜率 | 64% | **38.6%** (95 TP1 / 246 总) |
| TP2 触发 | 未提及 | **0 次** |
| 4h 信号 | 回测了 | **只有 5 个**（0 TP, 4 SL） |

### 发现 3：提高 TP 让情况更差

| TP 设置 | 预估触发率 | 预估 EV/笔 |
|---------|-----------|-----------|
| 1.5R（当前）| 38.6% | **-42.07U** |
| 2.2R（分析师建议）| 26.3% | **-48.13U** ❌ |

TP 目标越高，触发率下降更快，净效果为负。

---

## 🔍 根因定位：3 个代码级问题

### 根因 1：评分公式奖励「陷阱形态」

看 [strategy_engine.py:291-301](file:///Users/jiangwei/Documents/dingdingbot/src/domain/strategy_engine.py#L291-L301)：

```python
pattern_ratio = wick_ratio  # Pinbar 使用影线占比作为形态质量

if atr_value and atr_value > 0:
    atr_ratio = candle_range / atr_value
    score = self.calculate_score(pattern_ratio, atr_ratio)  
    # score = wick_ratio × 0.7 + min(candle_range/ATR, 2.0) × 0.3
```

**问题分解**：

1. **`wick_ratio` 越高 → 分数越高**。但极端 wick_ratio（>0.8）通常是**清算瀑布**（cascading liquidations）造成的，不是真正的反转信号。市场经常在清算后继续原方向运动。

2. **`candle_range / ATR` 越高 → 加分越多**。波幅大的 K 线获得高分，但这种大波幅 Pinbar 往往出现在**剧烈波动期**，后续走势极不稳定。

3. **分数公式没有考虑收盘位置**。一根 Pinbar 即使影线很长，如果收盘价**没有回到开盘价附近**，说明反转力度不足。但当前公式不关心这个。

**核心洞察**：你的公式把"长影线+大波幅"等同于"高质量"，但在加密市场里，这恰恰是**止猎/清算陷阱**的特征。真正的反转信号通常是"中等影线+适度波幅+强势收盘"。

### 根因 2：EMA 过滤器逻辑过于简单

看 [strategy_engine.py:347-365](file:///Users/jiangwei/Documents/dingdingbot/src/domain/strategy_engine.py#L347-L365)：

```python
def check(self, pattern, context):
    if pattern.direction == Direction.LONG:
        if current_trend == TrendDirection.BULLISH:
            return FilterResult(passed=True, reason="trend_match")
        else:
            return FilterResult(passed=False, reason="bearish_trend_blocks_long")
```

**问题**：只看"价格在 EMA 上方还是下方"，不看**距离多远**。

- 价格在 EMA 上方 0.01% → bullish ✅（但没有意义，本质上是横盘）
- 价格在 EMA 上方 5% → bullish ✅（真正的趋势确认）

两者在过滤器眼里没有区别。分析师的数据"EMA 通过后胜率仍仅 47%"就是这个原因 — **几乎所有信号都通过了 EMA**，因为阈值太低。

### 根因 3：TP/SL 结构在 38.6% 胜率下数学上不可能盈利

```
EV = 0.386 × 1.5R − 0.614 × 1.0R = 0.579R − 0.614R = −0.035R
```

**每笔交易在成本之前就已经是负期望值**。再加上滑点 + 手续费，每笔亏得更多。

---

## 💡 修正后的建议（按 ROI 排序）

### ⭐ 优先级 1：修复评分公式（核心问题）

当前公式奖励错误特征。需要重新设计：

```python
# 当前（有害）
score = wick_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3

# 修正方案：惩罚极端值，奖励"甜蜜区间"
def calculate_score_v2(self, wick_ratio, body_ratio, body_position, atr_ratio=None):
    """
    新评分逻辑：
    1. 影线占比：0.6-0.75 是最佳区间，超过 0.85 反而减分
    2. 实体位置：收盘越接近极端位置，加分越多
    3. 波幅：适度波幅加分，超大波幅减分
    """
    # 影线质量：bell curve centered at 0.7
    wick_score = Decimal('1.0') - abs(wick_ratio - Decimal('0.7')) * Decimal('3')
    wick_score = max(Decimal('0'), min(wick_score, Decimal('1.0')))
    
    # 实体位置质量（body_position 0=bottom, 1=top）
    # LONG: body_position 越接近 1.0 越好
    # SHORT: body_position 越接近 0.0 越好
    position_score = body_position  # 对 LONG；SHORT 需要 1-body_position
    
    # 波幅质量：0.5-1.5 ATR 是最佳区间
    if atr_ratio and atr_ratio > 0:
        if atr_ratio < Decimal('0.5'):
            vol_score = atr_ratio / Decimal('0.5')       # 波幅太小
        elif atr_ratio <= Decimal('1.5'):
            vol_score = Decimal('1.0')                    # 甜蜜区间
        else:
            vol_score = Decimal('1.5') / atr_ratio        # 波幅太大，打折
    else:
        vol_score = Decimal('0.5')
    
    # 综合评分
    score = (wick_score * Decimal('0.4') 
             + position_score * Decimal('0.3') 
             + vol_score * Decimal('0.3'))
    
    return min(score, Decimal('1.0'))
```

**关键改变**：
- **影线占比**：从"越长越好"改为"0.7 附近最好"（钟形曲线）
- **极端波幅**：从"加分"改为"减分"（超过 1.5x ATR 开始打折）
- **新增维度**：实体位置（body_position）反映收盘力度

### ⭐ 优先级 2：EMA 过滤器加入距离阈值

```python
def check(self, pattern, context):
    if not self._enabled:
        return FilterResult(passed=True, reason="disabled")
    
    # 计算价格与 EMA 的距离百分比
    ema_value = self._get_ema(kline.symbol, kline.timeframe)
    distance_pct = abs(kline.close - ema_value) / ema_value
    
    # 距离太近（<0.5%）= 横盘，不确认趋势
    MIN_DISTANCE = Decimal('0.005')
    if distance_pct < MIN_DISTANCE:
        return FilterResult(
            passed=False, 
            reason=f"ema_distance_too_small ({distance_pct:.2%})",
            metadata={"distance_pct": float(distance_pct)}
        )
    
    # 方向匹配检查（现有逻辑）
    ...
```

**预期效果**：过滤掉横盘中的假信号，只在趋势明确时交易。

### ⭐ 优先级 3：降低 TP 目标 + 考虑部分平仓

不是提高 TP，而是**降低**：

```python
# 方案 A：单 TP 降到 1.2R（提高触发率）
OrderStrategy(
    tp_levels=1,
    tp_targets=[Decimal('1.2')],  # 从 1.5R 降到 1.2R
)

# 方案 B：部分止盈 + Trailing（利用已有的 DynamicRiskManager）
OrderStrategy(
    tp_levels=2,
    tp_ratios=[Decimal('0.6'), Decimal('0.4')],   # 60% 先走
    tp_targets=[Decimal('1.0'), Decimal('2.5')],   # TP1=1R, TP2=2.5R
    trailing_stop_enabled=True,                     # TP1 后启动 trailing
)
```

**为什么降低 TP？**

假设 TP 从 1.5R 降到 1.2R，触发率从 38.6% 提高到 ~48%（保守估计）：
```
EV = 0.48 × 1.2R − 0.52 × 1.0R = 0.576R − 0.52R = +0.056R ✅
```

从负变正！虽然每笔赚得少，但胜率提升补偿了单笔收益下降。

---

## 🚫 不要做的事

| 建议 | 为什么不做 |
|------|-----------|
| score ≥ 0.7 过滤 | ❌ 数据证明高分更差，这会加速亏损 |
| 提高 TP 到 2R/2.2R | ❌ 触发率下降太快，EV 更差 |
| 历史相似度预测 | ❌ 基础评分都不对，ML 建在错误特征上没用 |
| 动态仓位（基于当前分数）| ⚠️ 先修好评分再做，否则"高分加仓"=加速亏损 |

---

## 📋 建议行动计划

```
Step 1: 验证评分公式 v2（纯分析，不改代码）
  → 用现有回测数据，用 Python 脚本模拟新评分
  → 检查新分数与胜率的相关性
  → 确认新评分确实是正相关

Step 2: 降低 TP 到 1.2R（改 1 个参数）
  → 跑一次回测对比
  → 这是最快能验证的改动

Step 3: 如果 Step 1 验证通过，替换评分公式
  → 改 strategy_engine.py 的 calculate_score()
  → 重新跑全量回测

Step 4: EMA 距离阈值（在 Step 3 之后）
  → 加入最小距离过滤
  → 再跑回测对比
```

---

## ❓ 需要你决定

1. **你想先做 Step 1（验证新评分）还是 Step 2（降 TP）？**
   - Step 1 是诊断，不改代码，风险为零
   - Step 2 是最快能看到效果的改动

2. **你的回测是用默认 `OrderStrategy`（单 TP 1.5R）还是自定义过？**
   - 如果是默认的，TP2/TP3 从未触发是正常的（因为 `tp_levels=1`）
   - 如果你配置过双 TP 但仍未触发，说明 TP2 设置得太远

3. **15m 时间框架是否值得保留？**
   - 15m 的信噪比最差，交易成本占比最高
   - 可以考虑先放弃 15m，专注 1h
