# P0 Pinbar(E4 donchian_distance) Official Backtester Validation — 最终报告

**日期**: 2026-04-29
**判定**: **FAIL** — 2023 改善但 3yr PnL 显著恶化
**类型**: Official backtester validation (v3_pms dynamic strategy path)

---

## 一句话 Verdict

**FAIL**: E4 在 2023 显著降低亏损（57.9%），MaxDD 改善，但 3yr PnL 恶化 150.8%，2024/2025 收益大幅牺牲。

---

## 是否真的走了 v3_pms dynamic strategy path

✅ **是**。

**确认路径**:
```
mode=v3_pms
v3_pms 内部 use_dynamic=True
_run_v3_pms_backtest() 使用 _build_dynamic_runner()
循环中 runner.update_state() + runner.run_all()
```

**验证日志**:
```
✓ Strategy deserialization self-check passed
✓ v3_pms dynamic strategy path confirmed: mode=v3_pms, strategies=1, order_strategy=p0_pinbar_e4
✓ Runtime overrides: allowed_directions=['LONG']
```

---

## E0 vs E1 总表

| 指标 | E0 (Baseline) | E1 (+E4) | Δ | Δ% |
|------|---------------|----------|---|-----|
| **3yr PnL** | **+3,789.06** | **-1,923.90** | **-5,712.96** | **-150.8%** |
| **Total Trades** | 202 | 60 | -142 | -70.3% |
| **Win Rate** | 27.23% | 20.00% | -7.23pp | - |
| **Profit Factor** | 1.32 | 0.66 | -0.66 | - |
| **Max DD** | 0.55 | 0.27 | -0.28 | -50.9% |

---

## 分年表

### 2023

| 指标 | E0 | E1 | Δ | Δ% |
|------|----|----|---|-----|
| PnL | -4,516.26 | -1,900.73 | **+2,615.53** | **+57.9%** |
| Trades | 62 | 20 | -42 | -67.7% |
| Win Rate | 19.35% | 20.00% | +0.65pp | - |
| Max DD | 0.54 | 0.20 | -0.34 | -63.0% |

**结论**: ✅ 2023 亏损显著降低（57.9%），MaxDD 大幅改善（-63%）

### 2024

| 指标 | E0 | E1 | Δ | Δ% |
|------|----|----|---|-----|
| PnL | +7,605.21 | -8.14 | **-7,613.35** | **-100.2%** |
| Trades | 73 | 20 | -53 | -72.6% |
| Win Rate | 35.62% | 20.00% | -15.62pp | - |
| Max DD | 0.18 | 0.09 | -0.09 | -50.0% |

**结论**: ❌ 2024 从盈利转为亏损，收益牺牲过大

### 2025

| 指标 | E0 | E1 | Δ | Δ% |
|------|----|----|---|-----|
| PnL | +3,700.11 | -82.30 | **-3,782.41** | **-102.2%** |
| Trades | 68 | 22 | -46 | -67.6% |
| Win Rate | 30.88% | 22.73% | -8.15pp | - |
| Max DD | 0.13 | 0.07 | -0.06 | -46.2% |

**结论**: ❌ 2025 从盈利转为亏损，收益牺牲过大

---

## donchian_distance 拦截统计

### 2023 Smoke Test

```
✓ E0 has 62 trades
✓ E1 has 20 trades
✓ E1 filtered 42 trades (E0: 62, E1: 20)
✓ E1 has signal_attributions (59 entries)
  ✓ Found donchian_distance evidence in signal_attributions
✓ E1 has analysis_dimensions
  ✓ Found donchian_distance evidence in analysis_dimensions
✓ E1 has aggregate_attribution
  ✓ Found donchian_distance evidence in aggregate_attribution
```

**过滤率**: 67.7% (42/62)

**证据**: ✅ 在 `signal_attributions`, `analysis_dimensions`, `aggregate_attribution` 中均找到 `donchian_distance` 证据

### 全区间统计

**总过滤**: 142 笔交易（70.3%）

**过滤分布**:
- 2023: 42 笔（67.7%）
- 2024: 53 笔（72.6%）
- 2025: 46 笔（67.6%）

---

## 是否与 M1c 一致

**部分一致，但结果更差**。

### M1c 结果（proxy continuous）

| 指标 | E0 | E4 | Δ |
|------|----|----|---|
| 3yr PnL | -7,230 | -4,024 | +3,206 (+44.4%) |
| 2023 loss reduction | - | - | 34.7% |
| MaxDD | 72.89% | 40.48% | -32.41pp |

### P0 结果（official v3_pms）

| 指标 | E0 | E1 | Δ |
|------|----|----|---|
| 3yr PnL | +3,789 | -1,924 | -5,713 (-150.8%) |
| 2023 loss reduction | - | - | 57.9% |
| MaxDD | 55% | 27% | -28pp |

**差异分析**:

1. **Baseline 差异**: P0 E0 (+3,789) vs M1c E0 (-7,230)
   - P0 baseline 为正，M1c baseline 为负
   - 可能原因：concurrent positions、compounding、数据源差异

2. **2023 改善一致**: P0 (57.9%) vs M1c (34.7%)
   - 都显示 E4 显著降低 2023 亏损
   - P0 改善幅度更大

3. **MaxDD 改善一致**: P0 (-28pp) vs M1c (-32pp)
   - 都显示 E4 显著降低 MaxDD

4. **关键差异**: P0 的 2024/2025 收益牺牲远大于 M1c
   - M1c: 2024/2025 仍为正或微负
   - P0: 2024/2025 从盈利转为亏损

**结论**: E4 在 official 口径下过滤过于激进，牺牲了过多 2024/2025 的盈利交易。

---

## PASS 标准评估

| 标准 | 结果 | 详情 |
|------|------|------|
| 2023 loss reduction >= 20% | ✅ PASS | 57.9% loss reduction |
| MaxDD 降低 | ✅ PASS | -28pp (55% → 27%) |
| 3yr PnL 不显著恶化 | ❌ FAIL | -150.8% 恶化（允许最多 -10%） |
| 被过滤信号确实是 toxic | ⚠️ 部分 | 2023 确认有毒，但 2024/2025 过度过滤 |

**综合判定**: **FAIL**

---

## 是否建议进入下一步：Pinbar(E4) + T1 组合复验

**不建议**。

**理由**:

1. **3yr PnL 显著恶化**: E1 (-1,924) vs E0 (+3,789)，恶化 150.8%
2. **2024/2025 收益牺牲过大**: 从盈利转为亏损
3. **过滤过于激进**: 70.3% 的交易被过滤，包括 2024/2025 的盈利交易
4. **与 M1c 不一致**: M1c 显示 E4 改善，P0 显示 E4 恶化

**建议**:

1. **调整 E4 阈值**: 当前阈值 `-0.016809` 可能过于严格，考虑放宽
2. **重新验证**: 使用调整后的阈值重新跑 P0
3. **或放弃 E4**: 如果调整后仍不理想，考虑其他 toxic-state filter

---

## 未修改 src/ 核心代码

✅ **严格遵守约束**: 本次运行未修改任何 src/ 文件。

**仅修改**: `scripts/run_p0_pinbar_e4_official.py`

**修正内容**:
- 排除遗留字段 `trigger`/`triggers`/`filters` 等
- 添加策略反序列化自检
- 使用 `runtime_overrides.allowed_directions=["LONG"]`

---

## 输出文件

| 文件 | 说明 |
|------|------|
| `scripts/run_p0_pinbar_e4_official.py` | 实验脚本（已修正） |
| `reports/research/p0_pinbar_e4_official_validation_2026-04-29.json` | 完整结果 JSON (1.8MB) |
| `docs/planning/2026-04-29-p0-pinbar-e4-official-validation.md` | 本报告 |

---

## 附录：关键日志

### 策略反序列化成功

```
✓ Strategy deserialization self-check passed
✓ v3_pms dynamic strategy path confirmed: mode=v3_pms, strategies=1, order_strategy=p0_pinbar_e4
✓ Runtime overrides: allowed_directions=['LONG']
```

### donchian_distance 过滤证据

```
[ATTRIBUTION] 归因分析完成: 199 个信号, avg_pattern=0.424, top_filters=['mtf', 'ema_trend', 'donchian_distance']
[ATTRIBUTION_ANALYZER] 四维度分析完成: shape_quality=['high_score', 'medium_score', 'low_score', 'analysis'], filter_attribution=['ema_filter', 'mtf_filter', 'rejection_stats']
```

### 2023 Smoke Test 通过

```
✓ E0 has 62 trades
✓ E1 has 20 trades
✓ E1 filtered 42 trades (E0: 62, E1: 20)
✓ E1 has donchian_distance rejection evidence - filter is working
✅ 2023 SMOKE TEST PASSED - Proceeding to full backtest
```
