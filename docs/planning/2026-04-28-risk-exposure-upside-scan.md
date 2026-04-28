# R0: Risk / Exposure Upside Scan — 最佳可能性上限扫描

> **日期**: 2026-04-28
> **脚本**: `scripts/run_r0_risk_upside_scan.py`
> **数据**: `reports/research/risk_exposure_upside_scan_2026-04-28.json`
> **性质**: 激励性上限扫描，不作为上线建议，不作为参数冻结依据

---

## 0. 核心结论（先说结论）

**如果只看最佳可能性：**
- T1 单策略上限：**3yr +3,654**（risk=2.0%, MaxDD=39%, fragile）
- Pinbar + T1 组合上限：**未知**（Pinbar proxy 未校准，无法可靠计算组合）
- 系统总上限（假设 Pinbar 恢复 engine 口径 +9,067）：**3yr +12,000~15,000**（纯理论天花板）

**真实上线应该从哪里开始：**
- **T1: risk=1.0%, exposure=1.0~2.0** → 3yr +1,949, MaxDD=22.5%, Calmar=0.86
- 这是唯一经过完整审计验证的配置
- 不需要放大 risk/exposure，收益提升主要来自解决 fragile 问题

---

## 1. 扫描设计

### 1.1 Grid

| 维度 | 取值 |
|------|------|
| max_total_exposure | 1.0, 1.5, 2.0, 2.5, 3.0 |
| max_loss_percent | 0.5%, 1.0%, 1.5%, 2.0% |
| portfolio weight | 100/0, 80/20, 70/30, 60/40, 50/50 |
| years | 2023, 2024, 2025 |

总配置数：120（20 Pinbar + 20 T1 + 80 Portfolio）

### 1.2 口径说明

| 项目 | Pinbar Proxy | T1 Proxy |
|------|-------------|----------|
| 入场 | next 1h bar open + 0.01% slippage | next 4h bar open + 0.01% slippage |
| TP | TP1=1.0R (SL→BE), TP2=3.5R (full close) | ATR trailing, no fixed TP |
| SL | signal bar low | entry - 2×ATR(14) |
| Fee | entry + exit 各 0.0405% | entry + exit 各 0.0405% |
| EMA filter | 1h EMA50 (>0.5%) + 4h EMA60 bullish | 无 |
| Sizing | fixed INITIAL_BALANCE × max_loss_pct / R | dynamic equity × max_loss_pct / risk_dist |
| Exposure cap | min(risk_size, BALANCE×exp/price) | min(risk_size, equity×exp/price) |

### 1.3 ⚠️ Pinbar Proxy 质量警告

**Pinbar proxy 结果与 engine 参考值存在系统性偏差：**

| 年份 | Proxy | Engine | Δ |
|------|-------|--------|---|
| 2023 | -2,729 | -3,924 | +1,195 |
| 2024 | +1,950 | +8,501 | **-6,551** |
| 2025 | -1,041 | +4,490 | **-5,531** |
| **3yr** | **-1,820** | **+9,067** | **-10,887** |

**根因分析**：Pinbar engine 使用 Backtester 引擎撮合，proxy 使用独立模拟。两者在信号检测、TP 执行顺序、费用计算上存在差异。proxy 持续低于 engine 表明 proxy 少计了正收益来源。

**影响**：所有包含 Pinbar 的组合（Portfolio）结果不可靠，仅 T1 standalone 结果经过审计验证。

---

## 2. T1 上限扫描（✅ 已验证）

### 2.1 T1 全 Grid 结果

| Exposure | Risk | 3yr PnL | MaxDD | Calmar | Sharpe | Worst Year |
|----------|------|---------|-------|--------|--------|------------|
| 1.0 | 0.5% | **+1,004** | 12.2% | 0.83 | 0.86 | 2025 (+145) |
| 1.0 | 1.0% | **+1,949** | 22.5% | 0.86 | 0.90 | 2025 (+256) |
| 1.0 | 1.5% | **+2,853** | 31.6% | 0.90 | 0.93 | 2025 (+333) |
| 1.0 | 2.0% | **+3,526** | 38.5% | 0.92 | 0.94 | 2025 (+376) |
| 1.5 | 1.0% | **+1,949** | 22.5% | 0.86 | 0.90 | 2025 (+256) |
| 2.0 | 1.0% | **+1,949** | 22.5% | 0.86 | 0.90 | 2025 (+256) |
| 2.0 | 2.0% | **+3,654** | 39.1% | 0.93 | 0.94 | 2025 (+376) |

### 2.2 关键发现

**1. Exposure cap 对 T1 完全无影响。**

T1 的 Donchian 4h 通道宽度 4-8%，position size 远低于 exposure cap。所有 20 个 exposure-risk 组合的 exposure_rejected = 0。

→ **T1 不需要调整 exposure，只需控制 risk。**

**2. Risk 线性缩放，Calmar 几乎不变。**

| Risk | PnL | MaxDD | Calmar |
|------|-----|-------|--------|
| 0.5% | +1,004 | 12.2% | 0.83 |
| 1.0% | +1,949 | 22.5% | 0.86 |
| 1.5% | +2,853 | 31.6% | 0.90 |
| 2.0% | +3,654 | 39.1% | 0.93 |

收益与 MaxDD 几乎 1:1 线性增长（因为 T1 single-position，equity curve 线性缩放）。

→ **放大 risk 只是放大赌注，不改变策略质量。Calmar 0.83-0.93 恒定。**

**3. T1 始终 fragile。**

所有配置的 top1 winner 贡献 ~47% PnL，top3 贡献 ~112%（去掉 top3 则亏损）。

→ **这是趋势跟随的固有特征，不是参数问题。放大 risk 不解决 fragile。**

**4. 最差年份永远是 2025（不是 2023）。**

T1 在 2023 反而是最强年份（+1,358 at 1% risk），2025 最弱（+256）。

→ **T1 与 Pinbar 的互补性已确认：Pinbar 2023 亏最多，T1 2023 赚最多。**

### 2.3 T1 CAGR 与风险代价

| 配置 | CAGR | MaxDD | Sharpe | 性质 |
|------|------|-------|--------|------|
| risk=0.5% | 3.2% | 12.2% | 0.86 | 保守 |
| risk=1.0% | 6.2% | 22.5% | 0.90 | **当前 baseline** |
| risk=1.5% | 8.7% | 31.6% | 0.93 | 激进 |
| risk=2.0% | 10.9% | 39.1% | 0.94 | 天花板 |

CAGR 3.2% → 10.9%，代价是 MaxDD 12% → 39%。

---

## 3. 杠杆需求分析

### 3.1 R-multiple 分布（baseline 1% risk）

| 策略 | R p50 | R p90 | R max | Leverage p50 | Leverage p90 | >5x占比 |
|------|-------|-------|-------|-------------|-------------|---------|
| Pinbar | 15.7 | 39.0 | 132.6 | 1.3x | 0.5x | 4% |
| T1 | 86.1 | 162.1 | 261.1 | 0.2x | 0.1x | 0% |

**解读**：
- T1 的 ATR-based stop 很宽（R ~86-162 USDT），1% risk 下杠杆极低（0.1-0.2x）
- Pinbar 的 stop 较窄（R ~16-39 USDT），杠杆略高但仍低（0.5-1.3x）
- **两个策略在 1% risk 下都不需要高杠杆**（<5x 占比极低）
- risk=2.0% 时杠杆翻倍，但仍 <3x for T1

→ **杠杆不是瓶颈，不需要杠杆放大来实现收益目标。**

---

## 4. 三类最佳配置

### 4.1 Aggressive Best Case（激进最佳）

| 指标 | 值 |
|------|-----|
| 策略 | T1 standalone |
| Exposure | 1.5 |
| Risk | 2.0% |
| 3yr PnL | **+3,654** |
| CAGR | 10.9% |
| MaxDD | **39.1%** |
| Calmar | 0.93 |
| Sharpe | 0.94 |
| Fragile | ⚠️ YES (top1=46.8%) |
| Worst Year | 2025 (+376) |

**性质**: 激励性天花板。39% MaxDD 在实盘中不可接受。收益提升来自 risk 放大（1%→2%），不是策略改进。

### 4.2 Balanced Best Case（平衡最佳）

| 指标 | 值 |
|------|-----|
| 策略 | T1 standalone |
| Exposure | 1.0-2.0（无影响） |
| Risk | **1.0%** |
| 3yr PnL | **+1,949** |
| CAGR | 6.2% |
| MaxDD | **22.5%** |
| Calmar | 0.86 |
| Sharpe | 0.90 |
| Fragile | ⚠️ YES |

**性质**: 当前 T1-R baseline。收益/回撤比最优（Calmar 0.86）。已通过完整审计。

### 4.3 Conservative Best Case（保守最佳）

| 指标 | 值 |
|------|-----|
| 策略 | T1 standalone |
| Exposure | 1.0 |
| Risk | **0.5%** |
| 3yr PnL | **+1,004** |
| CAGR | 3.2% |
| MaxDD | **12.2%** |
| Calmar | 0.83 |
| Sharpe | 0.86 |
| Fragile | ⚠️ YES |

**性质**: 接近 Sim-1 观察盘思路。低回撤，低收益。适合验证阶段。

---

## 5. 收益来源分解

| 来源 | 贡献 | 说明 |
|------|------|------|
| **Risk 放大** (0.5%→2.0%) | PnL ×3.6 | 纯赌注放大，Calmar 不变 |
| **Exposure 放大** (1.0→3.0) | **≈0** | T1 exposure cap 从未触发 |
| **组合互补** | **未验证** | Pinbar proxy 不可靠 |
| **策略 alpha** | ~+1,949/yr | T1 本身的正期望（at 1% risk） |

**关键发现**：T1 的全部收益来自策略 alpha（趋势跟随正期望）。risk 放大只是倍数。exposure 放大对 T1 无效。组合互补因 Pinbar proxy 问题未验证。

---

## 6. Pinbar Proxy 问题记录

### 6.1 偏差详情

| 年份 | Proxy PnL | Engine PnL | Δ | Δ% |
|------|-----------|------------|---|-----|
| 2023 | -2,729 | -3,924 | +1,195 | 30% |
| 2024 | +1,950 | +8,501 | -6,551 | 77% |
| 2025 | -1,041 | +4,490 | -5,531 | 123% |
| 3yr | -1,820 | +9,067 | -10,887 | 120% |

### 6.2 已排除的原因

- ✅ Entry price: 已修复为 next bar open（非 signal bar close）
- ✅ TP logic: 已修复为 TP1→BE stop, TP2→full close（非 partial close）
- ✅ Position sizing: 已使用 fixed INITIAL_BALANCE（非 dynamic equity）
- ❌ 仍不匹配

### 6.3 可能的剩余原因

1. **信号集合差异**: proxy 与 engine 的 Pinbar 检测、EMA 过滤可能产生不同信号集
2. **TP_RATIOS**: engine 可能使用 partial close（50% at TP1），proxy 使用 full close at TP2
3. **Entry fee**: proxy 收取 entry fee，engine 可能不收
4. **Fill logic**: engine 可能有更复杂的 fill 模型

### 6.4 下一步

修复 Pinbar proxy 需要：
1. 读取 Backtester 源码确认 TP_RATIOS 执行逻辑
2. 对齐 entry/exit fee 计算
3. 逐笔比对 proxy vs engine 2024 年前 10 笔交易

预计耗时：2-3h。修复后重跑 R0 scan 可获得可靠的组合分析。

---

## 7. 对研究路线的影响

### 7.1 已确认

- ✅ T1 上限已知：risk=1% → +1,949/3yr, MaxDD=22.5%
- ✅ T1 不受 exposure cap 影响
- ✅ T1 杠杆需求极低（<0.3x at 1% risk）
- ✅ Risk 放大不改变策略质量（Calmar 恒定）
- ✅ T1 fragile 是结构性的，不是参数问题

### 7.2 未确认（因 Pinbar proxy 问题）

- ❌ Pinbar + T1 组合的收益上限
- ❌ 组合后的 MaxDD 改善程度
- ❌ 最优 portfolio weight

### 7.3 决策建议

| 优先级 | 任务 | 理由 |
|--------|------|------|
| **P0** | 修复 Pinbar proxy 对齐 engine | 组合分析的前提 |
| **P0** | 修复后重跑 R0 scan | 获得可靠组合上限 |
| P1 | 如果组合上限不理想 → 解决 T1 fragile | fragile 是组合收益的瓶颈 |
| P2 | M1c E4 Donchian filter | 增强 Pinbar 底座 |

### 7.4 一句话结论

> **T1 本身上限已知（+3,654/3yr at 2% risk），但收益质量不高（Calmar 0.93, fragile）。系统真正上限取决于 Pinbar 底座强弱 + 组合互补效果，而这两项因 Pinbar proxy 未对齐而未验证。下一步 P0 是修复 Pinbar proxy。**

---

*R0 scan 完成时间: 2026-04-28*
*性质: research-only，不改 src，不改 runtime，不提交 git*
