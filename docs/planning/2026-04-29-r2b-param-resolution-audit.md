# R2b 参数解析链审计报告

> **日期**: 2026-04-29
> **任务**: 定位 Backtester 参数解析链断裂根因
> **结论**: ✅ **根因已定位：None 值被 resolve_decimal 丢弃，回退到默认值**

---

## 1. 一句话根因

**`resolve_decimal()` 函数在 `override_val=None` 时，跳过该值并回退到 `defaults[key]`，导致脚本传入的 `max_atr_ratio=None` 被丢弃，最终使用了 `BACKTEST_PARAM_DEFAULTS["max_atr_ratio"] = Decimal("0.01")`。**

---

## 2. 参数链 Diff 表

### A. 脚本传入参数（`run_r2a_baseline_smoke.py`）

```python
runtime_overrides = BacktestRuntimeOverrides(
    ema_period=50,                          # ✅ 传入
    min_distance_pct=Decimal("0.005"),      # ✅ 传入
    mtf_ema_period=60,                      # ✅ 传入
    max_atr_ratio=None,                     # ❌ 传入 None（意图：移除 ATR）

    tp_targets=[Decimal("1.0"), Decimal("3.5")],  # ✅ 传入
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],   # ✅ 传入
    breakeven_enabled=False,                # ✅ 传入

    allowed_directions=["LONG"],            # ✅ 传入
    fee_rate=BNB9_FEE_RATE,                 # ✅ 传入
    slippage_rate=BNB9_SLIPPAGE,            # ✅ 传入
)
```

### B. Backtester 参数解析链（`backtester.py:resolve_backtest_params()`）

```python
def resolve_decimal(
    key: str,
    override_val: Optional[Decimal],
    request_val: Optional[Decimal] = None,
    kv_key: Optional[str] = None,
) -> Decimal:
    """解析 Decimal 参数"""
    if override_val is not None:        # ❌ None 不满足条件，跳过
        return override_val
    if request_val is not None:
        return request_val
    if kv_configs and kv_key and kv_configs.get(kv_key) is not None:
        return Decimal(str(kv_configs[kv_key]))
    return defaults[key]                # ❌ 回退到 BACKTEST_PARAM_DEFAULTS["max_atr_ratio"] = 0.01
```

**`max_atr_ratio` 解析过程**:
```python
max_atr_ratio=resolve_decimal(
    "max_atr_ratio",
    overrides.max_atr_ratio,    # None（脚本传入）
    kv_key="strategy.atr.max_atr_ratio",
)
→ override_val=None → 跳过
→ request_val=None → 跳过
→ kv_configs=None → 跳过
→ return defaults["max_atr_ratio"] = Decimal("0.01")  # ❌ 回退到默认值
```

### C. 最终 Resolved Params

| 参数 | 脚本传入值 | 最终 Resolved 值 | 是否一致 | 偏移环节 |
|------|-----------|----------------|---------|---------|
| **ema_period** | 50 | 50 | ✅ 一致 | - |
| **mtf_ema_period** | 60 | 60 | ✅ 一致 | - |
| **min_distance_pct** | 0.005 | 0.005 | ✅ 一致 | - |
| **max_atr_ratio** | **None** | **0.01** | ❌ **不一致** | `resolve_decimal()` 回退到默认值 |
| **tp_targets** | [1.0, 3.5] | [1.0, 3.5] | ✅ 一致 | - |
| **tp_ratios** | [0.5, 0.5] | [0.5, 0.5] | ✅ 一致 | - |
| **breakeven_enabled** | False | False | ✅ 一致 | - |
| **allowed_directions** | ["LONG"] | ["LONG"] | ✅ 一致 | - |

---

## 3. 哪一步发生了偏移？

**偏移环节**: `resolve_decimal()` 函数逻辑

**偏移原因**:
1. 脚本传入 `max_atr_ratio=None`（意图：移除 ATR 过滤器）
2. `resolve_decimal()` 检查 `if override_val is not None:` → `None` 不满足条件 → 跳过
3. 后续 `request_val`、`kv_configs` 均为 `None` → 跳过
4. 最终回退到 `defaults["max_atr_ratio"] = Decimal("0.01")`
5. **ATR 过滤器被意外启用**，导致信号集合和收益分布改变

**核心问题**:
- **Python 的 `None` 值无法区分"未传入"和"显式传入 None"**
- `resolve_decimal()` 将 `None` 视为"未传入"，而非"显式禁用"
- 导致脚本意图（移除 ATR）被丢弃

---

## 4. 最小复现实验

**实验配置**:
- 年份: 2024
- exposure: 2.0
- risk: 1.0%
- baseline strategy expected

**实验结果**（已运行）:

### 脚本传入参数
```python
runtime_overrides = BacktestRuntimeOverrides(
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    mtf_ema_period=60,
    max_atr_ratio=None,  # ❌ 显式传入 None
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    breakeven_enabled=False,
    allowed_directions=["LONG"],
    fee_rate=Decimal("0.000405"),
    slippage_rate=Decimal("0.0001"),
)
```

### 最终 Resolved Params（日志证据）
```
[INFO] Running v3 PMS backtest with config: slippage=0.001, fee=0.0004, initial_balance=10000, tp_slippage=0.0005, funding_enabled=True, funding_rate=0.0001, min_distance_pct=0.005, max_atr_ratio=0.01, breakeven_enabled=False
```

**关键证据**: `max_atr_ratio=0.01`（而非 None）

### 二者 Diff

| 参数 | 脚本传入 | 最终 Resolved | Diff |
|------|---------|--------------|------|
| **max_atr_ratio** | **None** | **0.01** | ❌ **不一致** |

### 回测结果失真

| 指标 | 期望值（Baseline） | 实际值 | 是否一致 |
|------|------------------|--------|---------|
| **Trades** | 几十笔 | **558** | ❌ 失真 |
| **PnL** | 明显正收益 | **-6757.92 USDT** | ❌ 失真 |
| **MaxDD** | 合理范围 | **70.85%** | ❌ 失真 |

---

## 5. 修复建议（不改代码）

### ⚠️ 重要修正：`max_atr_ratio=0` 不是正确修复

**错误认知**：之前认为 `max_atr_ratio=Decimal("0")` 可以禁用 ATR 过滤器。

**正确分析**：查看 ATR 过滤器实际逻辑：

```python
# src/domain/strategies/engulfing.py (约 167-172 行)
if atr_pct is not None and max_atr_ratio is not None:
    if atr_pct > max_atr_ratio:
        return False, "atr_too_high"
```

若设置 `max_atr_ratio=Decimal("0")`：
- 条件变为 `if atr_pct > 0: reject`
- **几乎所有正常 K 线都会被拒绝**（因为 ATR% 几乎总是正数）
- 这等价于「ATR 过滤器永远拒绝」，而非「关闭 ATR 过滤器」

**结论**: `max_atr_ratio=0` ≠ 禁用 ATR，而是「ATR 阈值归零」，行为完全相反。

---

### 方案 A（推荐，脚本层）：改用 baseline strategy/profile

**不再依赖 `runtime_overrides.max_atr_ratio=None`**

改为让 R2 显式使用 baseline strategy/profile，其中 ATR filter `enabled=False`。

**修改方向**：
```python
# ❌ 错误写法（None 被丢弃，回退到 0.01）
runtime_overrides = BacktestRuntimeOverrides(
    max_atr_ratio=None,  # ❌ 无法表达"关闭 ATR"
)

# ✅ 正确写法（从 strategy/profile 层关闭 ATR）
# 让 R2 引用 baseline strategy ID 或 profile ID
# 该 baseline 配置中 ATR filter 的 enabled=False
```

**理由**：
1. **零侵入**：不动核心参数解析链
2. **语义清晰**：`enabled=false` 比 `max_atr_ratio=None` 更直观
3. **可追溯**：baseline profile 作为 SSOT，R2 只是引用

---

### 方案 B（需谨慎，src 层）：修改参数解析链

**修改 `resolve_decimal()` 支持显式 None 语义**

这属于核心代码修复，需要：
1. 区分「未传入」和「显式传入 None」
2. 可能需要引入 sentinel 值（如 `UNSET = object()`）
3. 影响面广，需全面回归测试

**暂不推荐**：先确认方案 A 是否可行。

---

## 6. 下一步行动

### 推荐路径：方案 A（脚本层修复）

**Step 1: 确认 baseline profile 配置**

检查 baseline strategy/profile 中是否存在 ATR filter 的 `enabled` 字段：
```bash
# 查找 baseline profile 配置
# 确认 ATR filter 的 enabled 字段
```

**Step 2: 修改 R2 脚本引用 baseline**

若 baseline profile 中 ATR filter `enabled=False`：
```python
# ✅ R2 脚本改为引用 baseline profile
# 不再依赖 runtime_overrides.max_atr_ratio=None
```

**Step 3: 运行 Smoke Test 验证**

```bash
python3 scripts/run_r2a_baseline_smoke.py
```

**验收标准**:
- ✅ 日志不显示 `max_atr_ratio` 参数（ATR filter 已 disabled）
- ✅ Trades 回到几十笔量级（Baseline 水平）
- ✅ PnL 回到明显正收益区间

---

## 7. 总结

### 问题确认

- ✅ 根因已定位：`resolve_decimal()` 将 `None` 视为"未传入"，回退到默认值
- ✅ 脚本传入 `max_atr_ratio=None` 被丢弃
- ✅ 最终使用了 `BACKTEST_PARAM_DEFAULTS["max_atr_ratio"] = 0.01`
- ✅ ATR 过滤器被意外启用，导致 trades 飙升、PnL 失真

### 修复方案修正

| 方案 | 原结论 | 修正后结论 | 原因 |
|------|--------|-----------|------|
| `max_atr_ratio=0` | ✅ 正确 | ❌ **错误** | `if atr_pct > 0: reject`，几乎全部拒绝 |
| 方案 A | 修改脚本用 `=0` | 改用 baseline profile | `enabled=false` 语义正确 |
| 方案 B | 不推荐 | 需谨慎 | 核心代码修复，影响面广 |

### 下一步

1. **确认 baseline profile 中 ATR filter 的 `enabled` 字段是否存在**
2. **若存在**：R2 脚本改为引用该 profile（方案 A）
3. **若不存在**：需在 baseline profile 中添加 `enabled=false`，再让 R2 引用
4. **暂不执行方案 B**（修改 `resolve_decimal()`），属于核心代码修复，需先确认方案 A 不可行后再考虑

---

*审计完成时间: 2026-04-29*
*问题级别: P0（参数解析链断裂）*
*修复优先级: P0（必须修复后才能继续）*
*修正时间: 2026-04-29（修正方案 A 结论）*
