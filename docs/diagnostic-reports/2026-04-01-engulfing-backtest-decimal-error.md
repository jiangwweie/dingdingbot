# 诊断报告：回测沙箱吞没形态策略 Decimal 错误

**报告日期**: 2026-04-01  
**诊断分析师**: Diagnostic Analyst  
**错误**: `'decimal.Decimal' object has no attribute 'open'`  
**触发场景**: 回测沙箱执行吞没形态策略配合过滤器组合

---

## 一、问题澄清与定界

### 错误信息
```json
{"error": "'decimal.Decimal' object has no attribute 'open'"}
```

### 请求参数
```json
{
  "symbol": "SOL/USDT:USDT",
  "timeframe": "1h",
  "start_time": 1772380800000,
  "end_time": 1775048110856,
  "strategies": [{
    "id": "1775048002807-e0a1vzi2x",
    "name": "02 吞没 ema60",
    "logic_tree": {
      "gate": "AND",
      "children": [
        {"type": "trigger", "id": "...", "config": {"type": "engulfing", ...}},
        {"type": "filter", "id": "...", "config": {"type": "mtf", ...}},
        {"type": "filter", "id": "...", "config": {"type": "ema", ...}},
        {"type": "filter", "id": "...", "config": {"type": "atr", ...}}
      ]
    }
  }]
}
```

### 问题定界
- **错误类型**: 类型错误 - 期望 `KlineData` 对象但收到 `Decimal` 对象
- **错误位置**: 某处代码调用 `kline.open` 但 `kline` 变量是 `Decimal` 对象
- **影响范围**: 吞没形态策略在回测沙箱中无法执行（实盘正常）
- **触发条件**: 使用 logic_tree + engulfing trigger + 回测模式

---

## 二、初步假设（按可能性排序）

| 可能性 | 假设 | 验证结果 |
|--------|------|----------|
| 60% | `backtester.py` 未传递 `kline_history` 导致吞没策略接收到错误数据 | ✅ **确认根因** |
| 25% | `recursive_engine.py` 中 `_evaluate_trigger_leaf` 传递错误的 kline | ❌ 排除 |
| 10% | `DynamicStrategyRunner` 中 ATR 值获取逻辑错误 | ❌ 排除 |
| 5% | FilterContext 中 kline 字段被覆盖 | ❌ 排除 |

---

## 三、根因确认（5 Why 分析）

### Why 1: 为什么会报错 `'decimal.Decimal' object has no attribute 'open'`？

**答**: 因为某处代码期望接收 `KlineData` 对象并访问 `.open` 属性，但实际收到的是 `Decimal` 对象。

### Why 2: 为什么会收到 Decimal 对象而不是 KlineData？

**答**: 检查 `EngulfingStrategy.detect()` 方法签名：
```python
def detect(self, kline: KlineData, prev_kline: Optional[KlineData] = None, atr_value: Optional[Decimal] = None)
```

当 `prev_kline=None` 时，方法返回 `None`（第 56-57 行）：
```python
if prev_kline is None:
    return None
```

### Why 3: 为什么 prev_kline 会是 None？

**答**: 检查 `DynamicStrategyRunner.run_all()` 在 `strategy_engine.py:702-709`:
```python
if hasattr(strat.strategy, 'detect_with_history') and kline_history:
    pattern = strat.strategy.detect_with_history(kline, kline_history, atr_value)
elif hasattr(strat.strategy, 'detect'):
    pattern = strat.strategy.detect(kline, atr_value)  # ← 这里！没有传 prev_kline
```

当 `kline_history` 为 `None` 时，会调用 `detect(kline, atr_value)`，但 `EngulfingStrategy.detect()` 的第二个参数是 `prev_kline`，不是 `atr_value`！

### Why 4: 为什么 kline_history 会是 None？

**答**: 检查 `backtester.py:387`:
```python
# Run all strategies with their filter chains
strat_attempts = runner.run_all(kline, higher_tf_trends)
#                                                    ↑ 没有传递 kline_history！
```

对比正确调用应该在第 3 个参数传递 `kline_history`。

### Why 5: 为什么回测器没有传递 kline_history？

**答**: **根因确认** - `_run_strategy_loop` 函数设计时未考虑需要历史 K 线的策略（如吞没形态）。

---

## 四、详细技术分析

### 问题代码位置

**文件**: `src/application/backtester.py`  
**函数**: `_run_strategy_loop`  
**行号**: 387

```python
# 当前代码（错误）
strat_attempts = runner.run_all(kline, higher_tf_trends)
```

### 参数签名不匹配问题

**文件**: `src/domain/strategy_engine.py`  
**函数**: `DynamicStrategyRunner.run_all`  
**行号**: 702-717

```python
# 当 kline_history 为 None 时执行此分支
elif hasattr(strat.strategy, 'detect'):
    import inspect
    sig = inspect.signature(strat.strategy.detect)
    if 'atr_value' in sig.parameters:
        pattern = strat.strategy.detect(kline, atr_value)  # ← 问题在这里！
```

对于 `EngulfingStrategy.detect()`:
```python
def detect(self, kline: KlineData, prev_kline: Optional[KlineData] = None, atr_value: Optional[Decimal] = None)
```

参数顺序是：`kline`, `prev_kline`, `atr_value`

但调用时传入的是：`kline`, `atr_value`

导致 `atr_value` (Decimal) 被传给 `prev_kline` 参数，然后在方法内部：
```python
if prev_kline is None:  # ← 实际上 prev_kline 是 Decimal，不是 None
    return None
```

但后续代码尝试访问 `prev_kline.open` 时就会报错！

### 实际错误链路

```
Backtester._run_strategy_loop(kline, higher_tf_trends)  # 未传 kline_history
    ↓
DynamicStrategyRunner.run_all(kline, higher_tf_trends)  # kline_history=None
    ↓
elif branch: detect(kline, atr_value)  # atr_value (Decimal) 被传给 prev_kline
    ↓
EngulfingStrategy.detect(kline, prev_kline=Decimal, ...)
    ↓
# prev_kline 不是 None，所以继续执行
prev_open = prev_kline.open  # ← 报错！Decimal 没有 .open 属性
```

---

## 五、修复方案

### 方案 A: 修复 backtester.py 传递 kline_history（推荐）

**修改文件**: `src/application/backtester.py`  
**修改位置**: `_run_strategy_loop` 函数

```python
# 修改前（第 387 行）
strat_attempts = runner.run_all(kline, higher_tf_trends)

# 修改后
# 构建 kline_history（截至当前 kline 的历史）
kline_history = klines[:klines.index(kline)]  # 或使用累积方式
strat_attempts = runner.run_all(kline, higher_tf_trends, kline_history=kline_history)
```

**更高效的实现**:
```python
# 在 _run_strategy_loop 函数中累积历史
kline_history = []
for kline in klines:
    runner.update_state(kline)
    higher_tf_trends = self._get_closest_higher_tf_trends(kline.timestamp, higher_tf_data)
    
    # 传递截至当前的历史（不包括当前 kline）
    strat_attempts = runner.run_all(
        kline, 
        higher_tf_trends, 
        kline_history=kline_history.copy()  # 或使用 deque 优化
    )
    
    # 更新历史
    kline_history.append(kline)
```

**优点**:
- 直接修复根因
- 吞没形态策略可以正常工作
- 支持所有需要历史 K 线的策略

**缺点**:
- 需要额外的内存存储历史
- 可能影响性能（可以使用 `collections.deque` 限制最大长度）

---

### 方案 B: 修复 parameter 绑定逻辑（防御性修复）

**修改文件**: `src/domain/strategy_engine.py`  
**修改位置**: `DynamicStrategyRunner.run_all`

```python
# 修改前（第 714-715 行）
if 'atr_value' in sig.parameters:
    pattern = strat.strategy.detect(kline, atr_value)

# 修改后：使用关键字参数避免位置参数混淆
if 'atr_value' in sig.parameters:
    pattern = strat.strategy.detect(kline, atr_value=atr_value)
```

**优点**:
- 防御性编程，避免参数顺序问题
- 不影响其他调用方

**缺点**:
- 不解决 `kline_history=None` 的根本问题
- 吞没形态策略仍然无法在回测中工作（因为 `prev_kline=None` 会直接返回 `None`）

---

### 方案 C: 组合修复（最佳实践）

同时实施方案 A + 方案 B：
1. 修复 `backtester.py` 传递 `kline_history`
2. 修复 `strategy_engine.py` 使用关键字参数

**修改清单**:

| 文件 | 行号 | 修改内容 |
|------|------|----------|
| `backtester.py` | 376-388 | 累积 kline_history 并传递给 `runner.run_all()` |
| `strategy_engine.py` | 707, 715 | 使用关键字参数调用 `detect()` 和 `detect_with_history()` |

---

## 六、优先级建议

| 优先级 | 方案 | 理由 |
|--------|------|------|
| 🔴 **P0** | 方案 C（组合修复） | 彻底解决问题 + 防御性编程 |
| 🟠 P1 | 方案 A | 仅修复根因，快速上线 |
| 🟡 P2 | 方案 B | 仅防御性修复，不能解决回测问题 |

---

## 七、验证步骤

修复后执行以下验证：

```bash
# 1. 运行吞没形态策略单元测试
pytest tests/unit/test_engulfing_strategy.py -v

# 2. 运行回测集成测试
pytest tests/integration/test_engulfing_e2e.py -v

# 3. 手动测试回测 API
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SOL/USDT:USDT",
    "timeframe": "1h",
    "strategies": [{
      "name": "吞没 ema60",
      "triggers": [{"type": "engulfing"}],
      "filters": [{"type": "ema"}, {"type": "mtf"}, {"type": "atr"}]
    }]
  }'
```

**预期结果**: 
- 不再出现 `'decimal.Decimal' object has no attribute 'open'` 错误
- 回测报告包含吞没形态策略信号

---

## 八、相关文件

- `src/application/backtester.py` - 回测器主文件
- `src/domain/strategy_engine.py` - 策略引擎（参数绑定逻辑）
- `src/domain/strategies/engulfing_strategy.py` - 吞没形态策略实现
- `src/domain/recursive_engine.py` - 递归评估引擎（与问题无关）

---

*诊断完成。建议立即实施方案 C 修复。*
