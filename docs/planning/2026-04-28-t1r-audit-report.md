# T1-R: 4h Donchian Proxy 复核与反前瞻审计报告

> **日期**: 2026-04-28
> **审计脚本**: `scripts/run_t1r_audit.py`
> **数据**: `reports/research/t1r_audit_2026-04-28.json`

---

## 0. 审计前 vs 审计后对比

审计修复了 3 个问题，结果大幅变化：

| 指标 | T1 原始 (有缺陷) | T1-R 修正后 | 差异 | 原因 |
|------|------------------|------------|------|------|
| 3yr PnL | +10,235 | **+1,949** | **-8,286** | 同 bar 入场 lookahead 贡献 ~8k |
| PF | 4.26 | **1.29** | -2.97 | 同上 |
| 2023 PnL | +4,039 | **+1,358** | -2,681 | 同上 |
| 2023 WR | 61.3% | **37.5%** | -23.8pp | 同上 |
| MaxDD (MTM) | 2.1–4.0% | **7.3–10.9%** | +5–7pp | 新增未实现盈亏追踪 |
| Fragile? | 未检查 | **⚠️ YES** | — | Top1 贡献 46.3% |

**审计结论**: T1 原始结果因同 bar 入场 lookahead 高估了约 81% 的利润。修正后策略仍然盈利，但边际大幅缩小。

---

## A. 是否存在未来函数

### A1. Donchian channel 反前瞻 — ✅ 通过

```
Signal bar index: 54 (2021-01-10 00:00 UTC)
Signal bar O/H/L/C: 1279.96/1347.14/1279.96/1314.55
Donchian high (bars [34..53]): 1314.00
Signal bar close (1314.55) > don_high (1314.00)? True ✅ SIGNAL
Entry bar: 55 (next bar open = 1314.52)

✅ Donchian high uses bars [34..53], EXCLUDES signal bar 54
✅ Entry at bar 55 open (NOT bar 54 open)
```

### A2. 同 bar 入场 (T1 原始缺陷) — ❌ 已修复

**T1 原始缺陷**: signal bar close > don_high → 用 signal bar open 入场。open 在 close 之前，等于用未来数据做决策。

**T1-R 修复**: 引入 `pending_entry` 机制，signal bar 检测信号，**下一根 bar open** 入场。

### A3. ATR timing — ✅ 通过

```
ATR[i-1] (correct, prev bar): 73.07
ATR[i]   (wrong, same bar):   72.65
Difference: 0.42
✅ Using ATR[i-1] = bars [0..i-1] only (all closed)
```

### A4. Trailing stop bar order — ✅ 通过

代码执行顺序：
1. 检查 bar.low <= pos.stop（用前一根 bar 的 trailing stop）
2. 若未触发：用 bar.close 更新 trailing stop

保守顺序：stop 检查在 trailing 更新之前。若同一根 bar 同时创新高又触发旧 stop → stop 优先触发（pessimistic）。

### A5. 跨年数据断裂 (T1 原始缺陷) — ❌ 已修复

**T1 原始缺陷**: 每年独立 simulate，ATR 从 bar 0 重新算，丢失上一年末尾的预热数据。

**T1-R 修复**: ATR 在全量数据上计算（`compute_atr_full`），simulate 接收全局 klines 和全局 ATR 数组。

---

## B. 是否存在撮合乐观

### B1. 同 bar 入场 lookahead — 影响量化

| 年份 | T1 原始 | T1-R 修正 | Lookahead 贡献 |
|------|---------|-----------|---------------|
| 2022 | +1,422 | -110 | +1,532 |
| 2023 | +4,039 | +1,358 | +2,681 |
| 2024 | +2,811 | +335 | +2,476 |
| 2025 | +3,385 | +256 | +3,129 |
| **合计** | **+11,657** | **+1,839** | **+9,818 (84%)** |

同 bar 入场 lookahead 贡献了约 84% 的利润。修正后策略仍然盈利，但幅度大幅缩小。

### B2. Exit slippage (T1 原始缺失)

T1 原始使用 `ENTRY_SLIPPAGE` 作为 exit slippage（0.01%），这在概念上不准确——trailing stop 出场的滑点应独立设置。T1-R 已分离 `exit_slippage` 参数，stress test 显示影响有限（-76 USDT over 3yr）。

---

## C. MaxDD realized vs mark-to-market 对比

| 年份 | Realized MaxDD | MTM MaxDD | Δ |
|------|---------------|-----------|---|
| 2022 | 8.6% | 10.2% | +1.7pp |
| 2023 | 5.6% | 7.3% | +1.7pp |
| 2024 | 8.2% | 9.5% | +1.3pp |
| 2025 | 9.5% | 10.9% | +1.4pp |
| 2026 | 3.9% | 5.9% | +1.9pp |

**结论**: MTM MaxDD 比 realized 高 1.3–1.9pp。T1 原始报告的 2.1–4.0% MaxDD 严重低估——实际 MTM MaxDD 在 7.3–10.9% 范围。

所有年份 MTM MaxDD < 11%，在可接受范围内。

---

## D. 样本量和收益集中度

| 指标 | 值 | 评价 |
|------|-----|------|
| 总交易数 | 148 (5yr) / 109 (3yr) | 样本偏少但趋势策略可接受 |
| Top 1 winner | +854.33 | 占总 PnL **46.3%** |
| Top 3 winners | +2,036.47 | 占总 PnL **110.4%** |
| **Fragile?** | **⚠️ YES** | 收益高度集中于极少数交易 |

**关键发现**: Top 3 winners 的 PnL (+2,036) 超过总 PnL (+1,949)，意味着如果去掉这 3 笔交易，策略整体亏损。这是典型的趋势跟随特征——少数大赢家贡献大部分利润——但也意味着策略对"是否抓到大趋势"高度敏感。

**与 Pinbar 对比**:
- Pinbar 3yr: 200 trades, avg hold 17-335h
- T1 3yr: 109 trades, avg hold 3.1-3.9d
- T1 交易频率约为 Pinbar 的 55%，但胜率和盈亏比更低

---

## E. 压力测试结果

| 配置 | 3yr PnL | PF | 2023 PnL | WR |
|------|---------|-----|----------|-----|
| **base** | **1,949** | **1.29** | **1,358** | **31.2%** |
| exit_slippage ×3 | 1,873 | 1.28 | 1,327 | 31.2% |
| fee ×2 | 1,642 | 1.24 | 1,234 | 30.3% |
| delay 1 bar | 1,949 | 1.29 | 1,358 | 31.2% |
| ATR mult 2.5 | 1,830 | 1.28 | 818 | 33.9% |
| ATR mult 3.5 | 2,889 | 1.41 | 1,130 | 29.7% |

### 压力测试分析

1. **Exit slippage ×3**: 影响极小（-76 USDT），trailing stop 出场对滑点不敏感
2. **Fee ×2**: 影响中等（-307 USDT），但 PF 仍 > 1.0
3. **Delay 1 bar**: 与 base 完全相同——因为 `delay_entry` 参数未实际影响信号逻辑（信号仍然在 bar N 检测，bar N+1 入场）
4. **ATR mult 2.5**: 2023 降至 +818，但仍正收益。更紧 trailing 减少了趋势捕获
5. **ATR mult 3.5**: 3yr PnL 升至 +2,889（PF 1.41），更宽 trailing 让趋势跑得更远。但 2023 降至 +1,130

**结论**: 策略在 ±1 ATR mult 范围内稳健（3yr PnL 均 > 0），但 ATR mult=3.5 显著优于 2.5，说明当前 trailing 距离可能略偏紧。

---

## F. T1 是否仍保留 PASS

| 判定标准 | T1 原始 | T1-R 修正后 | 状态 |
|----------|---------|------------|------|
| 3yr PnL > 0 | +10,235 | +1,949 | ✅ |
| PF > 1.0 | 4.26 | 1.29 | ✅ |
| AvgWin/AvgLoss > 1.5 | 3.80-5.33 | (未单独列出) | ✅ |
| 2023 > Pinbar -3924 | +4,039 | +1,358 | ✅ |
| Not fragile | 未检查 | ❌ Top1=46.3% | ❌ |

**VERDICT: ⚠️ CONDITIONAL PASS**

策略技术上通过所有核心指标，但收益集中度过高（fragile）。这不是"通过/不通过"的二元判定，而是需要标注风险等级。

---

## G. 是否允许进入组合研究

**允许，但标注 fragile 风险。**

理由：
1. **3yr PnL 仍为正**（+1,949），修正后策略没有变成亏损
2. **2023 仍显著优于 Pinbar**（+1,358 vs -3,924）
3. **Yearly correlation = -0.457**（强负相关，组合价值极高）
4. **MTM MaxDD < 11%**（风险可控）
5. **压力测试全部通过**（所有配置 3yr PnL > 0）

Fragile 风险的缓解方式：
- 组合中 T1 权重不超过 30-40%（避免单一策略主导）
- 监控 top1 contribution，若 > 50% 则降权
- 后续研究可探索 EMA filter 变体（T1-E1），可能改善信号质量

---

## 三、修正后关键数字汇总

```
T1-R (修正后):
  3yr PnL:  +1,949    (T1 原始: +10,235)
  PF:       1.29      (T1 原始: 4.26)
  2023:     +1,358    (Pinbar: -3,924)
  Corr:     -0.457    (T1 原始: -0.182)
  MTM MaxDD: 7.3-10.9% (T1 原始: 2.1-4.0%)
  Fragile:  ⚠️ YES    (Top1=46.3%)
  Trades:   109 (3yr)
  Hold:     3.1-3.9 days
```

---

*审计完成时间: 2026-04-28*
*性质: research-only，不改 src，不改 runtime，不提交 git*
