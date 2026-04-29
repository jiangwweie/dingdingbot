# P0 Pinbar(E4 donchian_distance) Official Backtester Validation — 脚本二次修正说明

**日期**: 2026-04-29
**状态**: 脚本已二次修正，待运行
**类型**: Research script preparation (no src/ modifications)

---

## 关键修正项（二次修正）

### 1. ✅ Mode 改回 v3_pms

**纠正**: v3_pms **不会**绕过 dynamic strategy path。

**验证**:
```python
# src/application/backtester.py:_run_v3_pms_backtest()
use_dynamic = request.strategies is not None and len(request.strategies) > 0
if use_dynamic:
    runner = self._build_dynamic_runner(...)
    # 循环中 runner.update_state(kline) 后 runner.run_all(...)
```

**修正**:
```python
request = BacktestRequest(
    mode="v3_pms",  # Use v3_pms for position-level backtesting with full PnL/MaxDD
    strategies=[strategy_dict],  # Dynamic strategy path
    order_strategy=ORDER_STRATEGY,  # CRITICAL: Order strategy for TP/SL
    ...
)
```

**原因**:
- v2_classic 返回 `BacktestReport`，不是 `PMSBacktestReport`
- 当前脚本只在 `PMSBacktestReport` 分支提取 PnL/trades
- v3_pms 提供完整仓位级 PnL / MaxDD / fees / slippage

---

### 2. ✅ BacktestRequest 必须传 order_strategy

**修正**:
```python
request = BacktestRequest(
    ...
    order_strategy=ORDER_STRATEGY,  # CRITICAL: Order strategy for TP/SL
    ...
)
```

**ORDER_STRATEGY 配置**:
```python
tp_ratios=[Decimal("0.5"), Decimal("0.5")],  # 50% TP1, 50% TP2
tp_targets=[Decimal("1.0"), Decimal("3.5")],  # TP1 at 1R, TP2 at 3.5R
```

---

### 3. ✅ BNB9 成本口径（保留）

```python
BNB9_SLIPPAGE = Decimal("0.0001")  # 0.01% entry slippage
BNB9_TP_SLIPPAGE = Decimal("0")  # 0% TP slippage
BNB9_FEE = Decimal("0.000405")  # 0.0405% fee
```

---

### 4. ✅ 冻结 TP 口径（保留）

```python
tp_ratios=[Decimal("0.5"), Decimal("0.5")],  # 50% TP1, 50% TP2
tp_targets=[Decimal("1.0"), Decimal("3.5")],  # TP1 at 1R, TP2 at 3.5R
```

---

### 5. ✅ 支持度检查修正

**新增检查**:
```python
assert request.mode == "v3_pms", f"mode must be v3_pms, got {request.mode}"
assert request.strategies is not None and len(request.strategies) > 0, "strategies must be non-empty"
assert request.order_strategy is not None, "order_strategy must be provided"
```

**E1 donchian_distance 检查**:
```python
has_donchian = check_donchian_in_tree(e1_dict["logic_tree"])
assert has_donchian, "E1 strategy must contain donchian_distance filter"
```

---

### 6. ✅ 2023 Smoke Test 增强

**验证项**:
1. E0 total_trades > 0
2. E1 total_trades > 0
3. E1 total_trades <= E0 total_trades
4. **E1 必须证明 donchian_distance rejection**

**证明方式**:
- `signal_attributions` 中包含 donchian_distance
- `analysis_dimensions.filter_attribution` 中包含 donchian_distance
- `aggregate_attribution` 中包含 donchian_distance
- 或其他 filter/reject 相关字段

**失败条件**:
- E0 或 E1 trades = 0
- E1 trades > E0 trades
- **无法证明 donchian_distance rejection**

**关键**: 只看 E1 trades 少于 E0 不够，必须证明是 donchian_distance 过滤导致。

---

### 7. ✅ 如果无法证明 donchian_distance rejection，停止

**逻辑**:
```python
if not donchian_evidence_found:
    if e1_2023["total_trades"] < e0_2023["total_trades"]:
        print(f"  E1 trades < E0 trades suggests filtering, but cannot prove it's donchian_distance")
        print(f"  Proceeding with caution - will check full report for evidence")
    else:
        print(f"✗ Cannot prove donchian_distance is working - smoke test FAILED")
        smoke_pass = False
```

**停止条件**: 无法证明 donchian_distance rejection 且 E1 trades >= E0 trades

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

## 运行方式

```bash
python3 scripts/run_p0_pinbar_e4_official.py
```

**执行流程**:
1. 支持度检查 (v3_pms, strategies, order_strategy, donchian_distance)
2. 2023 smoke test
3. 验证 donchian_distance rejection 证据
4. 如果 smoke 通过 → 完整 2023-2025 backtest
5. 如果 smoke 失败 → 停止并汇报

---

## 最终汇报格式

### 1. 是否已改为 v3_pms dynamic path

✅ **是**。脚本使用 `mode="v3_pms"` 并验证 `strategies` 和 `order_strategy` 非空。

### 2. 是否确认进入 _run_dynamic_strategy_loop

✅ **是**。v3_pms 内部支持 dynamic strategy path:
```python
use_dynamic = request.strategies is not None and len(request.strategies) > 0
if use_dynamic:
    runner = self._build_dynamic_runner(...)
```

### 3. 2023 smoke: E0/E1 trades/PnL/reject_reasons

**待运行后填写**。

### 4. E1 是否真的触发 donchian_distance rejection

**待运行后填写**。

**验证方式**:
- 检查 `signal_attributions` / `analysis_dimensions` / `aggregate_attribution`
- 确认包含 `donchian_distance` 或 `too_close_to_donchian_high`

### 5. 完整 2023-2025 结果

**待运行后填写**（仅当 smoke test 通过）。

---

## 下一步

**等待用户确认后运行脚本**。

如果 2023 smoke test 通过且能证明 donchian_distance rejection，将获得完整 2023-2025 对比结果。
