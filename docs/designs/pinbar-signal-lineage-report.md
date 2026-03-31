# Pinbar 信号溯源分析报告

**分析时间**: 2026-03-31
**分析对象**:  signals-prod.db 中的信号 (ID 286-291)

---

## 📋 执行摘要

通过日志溯源和 K 线数据重建分析，发现 **6 个信号中有 5 个 (83.3%) 不符合标准 Pinbar 形态定义**。

| 信号 ID | 币种 | 时间 | 方向 | Pinbar 验证 | 状态 |
|--------|------|------|------|-----------|------|
| 291 | BNB | 21:15 | LONG | ❌ 下影线 0.44% | 信号覆盖 |
| 290 | ETH | 20:45 | LONG | ❌ 下影线 55.29% | 正常生成 |
| 289 | SOL | 19:45 | LONG | ❌ 下影线 24% | 正常生成 |
| 288 | BTC | 19:15 | LONG | ❌ 上影线 69.83% | 正常生成 |
| 287 | ETH | 18:15 | LONG | ❌ 上影线 81.75% | 正常生成 |
| 286 | BNB | 18:00 | LONG | ✅ 下影线 61.11% | 正常生成 |

---

## 🔍 日志溯源发现

### 信号 291 (BNB/USDT 15m LONG @ 21:15)

**关键日志**:
```
[2026-03-30 21:15:01] [INFO] Signal covering: new score (0.705) > old score (0.703) for BNB/USDT:USDT 15m [01pinbar-ema60]
[2026-03-30 21:15:01] [DEBUG] 止损计算：direction=long, entry=619.51
[2026-03-30 21:15:01] [INFO] Signal superseded: old_signal=f1b5c2f65d9aef3e -> new_signal=70dc438627f45d0c
```

**分析**:
- 这不是一个新生成的信号，而是**信号覆盖 (Signal Covering)** 场景
- 新信号 (score 0.705) 覆盖了旧信号 (score 0.703)
- K 线数据：O:619.51 H:621.21 L:618.96 C:618.97
- 实际形态：**上影线 K 线** (上影线 75.56%, 下影线 0.44%)
- 检测方向：SHORT → 实际信号：LONG ❌

### 信号 286 (BNB/USDT 15m LONG @ 18:00)

**关键日志**:
```
[2026-03-30 18:00:00] [DEBUG] K-line received: BNB/USDT:USDT 15m @ 1774864800000
[2026-03-30 18:00:00] [DEBUG] MTF trends for BNB/USDT:USDT:15m: {'1h': <TrendDirection.BULLISH: 'bullish'>}
[2026-03-30 18:00:00] [DEBUG] 止损计算：direction=long, entry=617.94
[2026-03-30 18:00:00] [INFO] 开始跟踪信号：f1b5c2f65d9aef3e (BNB/USDT:USDT 15m)
```

**分析**:
- 唯一符合 Pinbar 形态的信号
- K 线数据：O:617.94 H:618.15 L:617.61 C:617.97
- 形态：下影线 61.11%, 实体 5.56% ✅
- 但日志中**缺少 Pinbar 检测通过的明确记录**

---

## 🚨 核心问题

### 问题 1: 日志链路不完整

所有信号的日志都显示：
```
K-line received → MTF trends → 止损计算 → 信号跟踪
```

**缺失的日志**:
- Pinbar 形态检测通过/失败的记录
- PatternResult 的详细信息
- 过滤器链通过的记录

### 问题 2: 信号覆盖机制可能被滥用

信号 291 是一个典型的异常案例：
- 原始信号 (18:00 生成) 是符合 Pinbar 的
- 覆盖信号 (21:15 生成) 完全不符合 Pinbar
- 覆盖逻辑仅比较 score，未重新验证形态

### 问题 3: 配置阈值过于宽松

```yaml
# core.yaml
pinbar_defaults:
  min_wick_ratio: 0.5          # 50% (应≥60%)
  max_body_ratio: 0.35         # 35% (应≤30%)
  body_position_tolerance: 0.3 # 30% (应≤10%)
```

### 问题 4: MTF 过滤器失效

所有信号的 MTF 状态都是 `Confirmed`，但日志中未发现 MTF 数据Unavailable 的记录。

---

## 📊 K 线数据验证

### 信号 291 - BNB/USDT @ 21:15

```
O:619.51  H:621.21  L:618.96  C:618.97

Candle Range: 2.25
Body: 0.54 (24.00%)
Upper Wick: 1.70 (75.56%) ← 主导
Lower Wick: 0.01 (0.44%)  ← 太短，不符合看涨 Pinbar

判定：上影线 K 线，应生成 SHORT 信号或无信号
实际：LONG 信号 ❌
```

### 信号 288 - BTC/USDT @ 19:15

```
O:67559.0  H:67998.0  L:67508.1  C:67655.9

Candle Range: 489.9
Body: 96.9 (19.78%)
Upper Wick: 342.1 (69.83%) ← 主导
Lower Wick: 50.9 (10.39%)

判定：上影线 K 线，应生成 SHORT 信号或无信号
实际：LONG 信号 ❌
```

---

## 🔧 修复建议

### 1. 增强日志记录

在 `strategy_engine.py` 和 `signal_pipeline.py` 中添加：

```python
logger.info(f"[PINBAR_DETECTED] symbol={symbol} timeframe={timeframe} "
            f"direction={direction} wick_ratio={wick_ratio:.2%} "
            f"body_ratio={body_ratio:.2%} body_position={body_position:.2f}")
```

### 2. 修复信号覆盖逻辑

信号覆盖时应重新验证形态：

```python
# 在 check_cover 函数中
if should_cover:
    # 重新验证新信号的 Pinbar 形态
    new_pattern = pinbar_strategy.detect(new_kline)
    if new_pattern is None:
        # 新信号不符合 Pinbar，取消覆盖
        should_cover = False
```

### 3. 收紧配置阈值

```yaml
pinbar_defaults:
  min_wick_ratio: 0.6    # 60%
  max_body_ratio: 0.3    # 30%
  body_position_tolerance: 0.1  # 10%
```

### 4. 添加形态验证中间件

在信号入库前添加最终验证：

```python
def validate_pinbar_signal(signal, kline):
    """验证信号是否符合 Pinbar 形态"""
    metrics = calculate_pinbar_metrics(kline)
    if signal.direction == 'long':
        return metrics['lower_wick_ratio'] >= 0.6
    else:
        return metrics['upper_wick_ratio'] >= 0.6
```

---

## 📝 结论

1. **当前系统中 83.3% 的信号不符合 Pinbar 形态定义**
2. **日志记录不完整，无法完整追溯检测链路**
3. **信号覆盖机制存在被滥用的风险**
4. **配置阈值过于宽松是主要原因之一**

**建议优先级**:
1. 🔴 高：增强日志记录，添加形态验证
2. 🟡 中：修复信号覆盖逻辑
3. 🟢 低：调整配置阈值

---

**报告完成时间**: 2026-03-31 12:00
