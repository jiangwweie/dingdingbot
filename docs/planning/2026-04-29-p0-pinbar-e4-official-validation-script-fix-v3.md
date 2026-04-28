# P0 Pinbar(E4 donchian_distance) Official Backtester Validation — 脚本第三次修正说明

**日期**: 2026-04-29
**状态**: 脚本已三次修正，待运行 2023 smoke test
**类型**: Research script preparation (no src/ modifications)

---

## 关键修正项（第三次修正）

### 1. ✅ 补充 LONG-only runtime_overrides

**问题**: 脚本打印 LONG-only，但没有真正传 `allowed_directions`。

**修正**:
```python
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES

# CRITICAL: Set LONG-only via runtime_overrides
overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
overrides.allowed_directions = ["LONG"]

# 运行回测
report = await backtester.run_backtest(
    request,
    runtime_overrides=overrides,
)
```

**目的**:
- 确认 P0 是 ETH 1h LONG-only baseline + E4
- 不允许 SHORT 混入结果

---

### 2. ✅ Summary 保留 PMS 报告归因/过滤证据

**修正**:
```python
if isinstance(report, PMSBacktestReport):
    summary = {
        ...
        # CRITICAL: Preserve attribution/filter evidence from PMS report
        "signal_attributions": report.signal_attributions or [],
        "aggregate_attribution": report.aggregate_attribution or {},
        "analysis_dimensions": report.analysis_dimensions or {},
        "debug_max_drawdown_detail": report.debug_max_drawdown_detail,
        "debug_equity_curve_len": len(report.debug_equity_curve or []),
    }
```

**目的**: 即使 PMSBacktestReport 没有 `reject_reasons`，也保留 attribution 字段用于验证。

---

### 3. ✅ Smoke 条件更严格

**修正前**: 允许"trades 少了就谨慎继续"

**修正后**: **必须找到 donchian_distance 证据**

**验证项**:
1. E0 total_trades > 0
2. E1 total_trades > 0
3. E1 total_trades <= E0 total_trades
4. **必须找到 `donchian_distance` 或 `too_close_to_donchian_high` 证据**

**检查字段**:
- `signal_attributions` (list)
- `analysis_dimensions` (dict)
- `aggregate_attribution` (dict)

**失败条件**: 如果找不到第 4 点，**必须停止**，不允许继续。

**代码**:
```python
if not donchian_evidence_found:
    print(f"\n✗ Cannot prove donchian_distance is working - smoke test FAILED")
    smoke_pass = False
```

---

### 4. ✅ 改正文案

**修正前**: "进入 _run_dynamic_strategy_loop"

**修正后**: 正确表述 v3_pms dynamic path:

```
mode=v3_pms
v3_pms 内部 use_dynamic=True
_run_v3_pms_backtest() 使用 _build_dynamic_runner()
循环中 runner.update_state() + runner.run_all()
```

**代码路径**:
```python
# src/application/backtester.py:_run_v3_pms_backtest()
use_dynamic = request.strategies is not None and len(request.strategies) > 0
if use_dynamic:
    runner = self._build_dynamic_runner(...)
    # 循环中:
    runner.update_state(kline)
    runner.run_all(...)
```

---

## 实验配置（最终版）

### E0: Pinbar Baseline

```
Strategy: pinbar_baseline_e0
Trigger: Pinbar (min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1)
Filters:
  - EMA50 trend filter
  - MTF EMA60 validation
Mode: v3_pms (position-level backtesting)
Order Strategy: TP1@1R (50%), TP2@3.5R (50%)
Direction: LONG-only (via runtime_overrides.allowed_directions=["LONG"])
```

### E1: Pinbar + E4 Donchian Distance

```
Strategy: pinbar_e4_e1
Trigger: Pinbar (same as E0)
Filters:
  - EMA50 trend filter
  - MTF EMA60 validation
  - donchian_distance (lookback=20, max_distance_to_high_pct=-0.016809)
Mode: v3_pms (position-level backtesting)
Order Strategy: TP1@1R (50%), TP2@3.5R (50%)
Direction: LONG-only (via runtime_overrides.allowed_directions=["LONG"])
```

### E4 Threshold

```
lookback: 20
max_distance_to_high_pct: -0.016809 (M1c 验证阈值)
```

### Cost Model (BNB9)

```
Entry Slippage: 0.01%
TP Slippage: 0%
Fee: 0.0405%
```

### Risk Config

```
Max Loss: 1%
Max Exposure: 2.0x (research profile)
```

---

## 未修改文件

✅ **严格遵守约束**:
- ✅ 未修改 src/ 核心代码
- ✅ 未修改 sim1_eth_runtime
- ✅ 未修改 runtime profile
- ✅ 未修改 PinbarStrategy
- ✅ 未修改 risk_calculator
- ✅ 未修改现有 baseline 脚本

**仅修改**: `scripts/run_p0_pinbar_e4_official.py`

---

## Diff 摘要

### 新增导入

```python
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import BacktestRuntimeOverrides
```

### 新增 LONG-only 配置

```python
overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
overrides.allowed_directions = ["LONG"]
report = await backtester.run_backtest(request, runtime_overrides=overrides)
```

### 新增归因字段保留

```python
summary["signal_attributions"] = report.signal_attributions or []
summary["aggregate_attribution"] = report.aggregate_attribution or {}
summary["analysis_dimensions"] = report.analysis_dimensions or {}
summary["debug_max_drawdown_detail"] = report.debug_max_drawdown_detail
summary["debug_equity_curve_len"] = len(report.debug_equity_curve or [])
```

### 更严格 smoke 验证

```python
if not donchian_evidence_found:
    print(f"\n✗ Cannot prove donchian_distance is working - smoke test FAILED")
    smoke_pass = False  # 必须停止，不允许继续
```

---

## 2023 Smoke Test 准备状态

✅ **已准备好运行 2023 smoke test**:

1. ✅ Mode: v3_pms (position-level backtesting)
2. ✅ Dynamic strategy path: strategies 非空
3. ✅ Order strategy: TP1@1R (50%), TP2@3.5R (50%)
4. ✅ LONG-only: runtime_overrides.allowed_directions=["LONG"]
5. ✅ BNB9 cost model: 0.01% / 0% / 0.0405%
6. ✅ E4 threshold: lookback=20, max_distance_to_high_pct=-0.016809
7. ✅ Attribution fields preserved: signal_attributions, analysis_dimensions, aggregate_attribution
8. ✅ Strict smoke validation: 必须找到 donchian_distance 证据

**执行命令**:
```bash
python3 scripts/run_p0_pinbar_e4_official.py
```

**预期输出**:
```
✓ v3_pms dynamic strategy path confirmed: mode=v3_pms, strategies=1, order_strategy=p0_pinbar_e4
✓ Runtime overrides: allowed_directions=['LONG']
✓ E1 strategy contains donchian_distance filter

[2023 smoke test]
✓ E0 has {trades} trades
✓ E1 has {trades} trades
✓ E1 filtered {filtered} trades
✓ E1 has signal_attributions ({count} entries)
✓ Found donchian_distance evidence in signal_attributions
✓ E1 has donchian_distance rejection evidence - filter is working

✅ 2023 SMOKE TEST PASSED - Proceeding to full backtest
```

**如果失败**:
```
✗ Cannot prove donchian_distance is working - smoke test FAILED
❌ 2023 SMOKE TEST FAILED - Stopping execution
```

---

## 下一步

**等待用户确认后运行 2023 smoke test**。

**如果 smoke 通过**: 继续运行完整 2023-2025 backtest
**如果 smoke 失败**: 停止并调查原因（检查 PMSBacktestReport attribution 字段）
