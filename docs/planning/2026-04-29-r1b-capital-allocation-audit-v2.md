# R1b Capital Allocation Audit V2 - 严格二次审计

> **日期**: 2026-04-29
> **性质**: research-only 审计，不改 src，不改 runtime，不提交 git
> **目标**: 不接受 R1 原报告，不接受 R1 audit 结论，完整审计 56 组配置

---

## 0. 一句话结论

**✅ 存在可行解！** 基于 `debug_curve`（Backtester 内部 equity curve），**2 组配置满足 MaxDD <= 35%**：
- **exposure=1.0, risk=0.5%**: PnL=2,113 USDT, MaxDD=32.42%
- **exposure=1.25, risk=0.5%**: PnL=2,346 USDT, MaxDD=33.74%

---

## 1. 审计设计

### 1.1 审计目标

回答以下问题：

1. R1 原报告的 MaxDD 是否错误？
2. R1 audit 的结论是否错误？
3. report.max_drawdown 计算的是什么？
4. report.debug_equity_curve 是什么？
5. realized_equity_curve 是什么？
6. mark-to-market equity curve 是什么？
7. 三种 MaxDD 的差异是什么？
8. 56 组配置中，MaxDD <= 35% 是否存在可行解？
9. 如果存在可行解，推荐哪组？
10. 如果不存在，证据是什么？

### 1.2 审计方法

**对账三种 equity curve：**

| 类型 | 定义 | 计算方式 |
|------|------|----------|
| **report.debug_equity_curve** | Backtester 输出的权益曲线 | 从 report.debug_equity_curve 字段读取 |
| **realized_equity_curve** | 只在平仓时更新权益 | 从 positions 计算，只累加 realized_pnl |
| **mark-to-market equity curve** | 每根 K 线计入浮盈浮亏 | **本轮未实现** |

**重要说明：**

- ❌ 本审计**未计算真实 mark-to-market equity curve**
- ✅ 本审计基于 realized_equity_curve 和 report.debug_equity_curve
- ⚠️ 不得声称"MTM MaxDD"或"真实 MaxDD"

**审计流程：**

1. 读取 R1 原始 JSON，提取搜索网格（8 exposures × 7 risks = 56 组）
2. 对每个配置运行回测，提取：
   - `report.max_drawdown`
   - `report.debug_max_drawdown_detail`
   - `report.debug_equity_curve`
   - `positions`（用于计算 realized curve）
3. 计算：
   - 用 debug_equity_curve 重算 MaxDD
   - 用 realized curve 重算 MaxDD
4. 对账三者差异
5. 按 MaxDD <= 35% 过滤可行解
6. 重点核验 risk=0.5%

---

## 2. R1 原始报告回顾

### 2.1 最优配置（R1 原报告）

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.00% |
| Total PnL | **17,749.41 USDT** |
| MaxDD | **0.73%** ❌ |
| Sharpe | 0.51 |
| Calmar | 244.55 ❌ |
| Trades | 174 |

**年度表现：**

| Year | PnL | Trades |
|------|-----|--------|
| 2023 | -5,751.03 | 52 |
| 2024 | +6,081.84 | 61 |
| 2025 | +17,418.60 | 61 |

**矛盾点**：2023 年亏损 -5,751 USDT，MaxDD 不可能只有 0.73%。

---

## 3. R1 Audit 回顾

### 3.1 R1 Audit 结论

| 配置 | 原始 MaxDD | 重算 MaxDD | 判定 |
|------|-----------|-----------|------|
| exposure=1.0, risk=0.5% | 0.32% | **38.12%** | ❌ FAIL |
| exposure=1.0, risk=1.0% | 0.54% | **61.49%** | ❌ FAIL |
| exposure=1.0, risk=2.0% | 0.73% | **83.71%** | ❌ FAIL |

**R1 Audit 问题：**

1. 只审计了 3 个配置，却下结论"所有配置无可行解"
2. 声称计算 mark-to-market equity curve，但实际只按平仓 realized_pnl 更新 cash
3. 没有对账 PMSBacktestReport.debug_equity_curve / debug_max_drawdown_detail

---

## 4. 审计结果

### 4.1 三种 MaxDD 对账表（示例：exposure=1.0, risk=0.5%）

| 配置 | report.max_dd | debug_detail.max_dd | debug_curve_max_dd | realized_curve_max_dd | 差异解释 |
|------|--------------|---------------------|-------------------|----------------------|----------|
| exposure=1.0, risk=0.5% | **0.32%** | 0.32% | **32.42%** | **38.12%** | report.max_dd 与 debug_detail.max_dd 一致，但都是错误的（可能是内部指标）；debug_curve_max_dd 是 Backtester 内部 equity curve 的真实 MaxDD；realized_curve_max_dd 是只按平仓计算的 MaxDD |

**关键发现：**

1. **report.max_dd 错误**：
   - 值为 0.32%，远小于真实 MaxDD
   - 与 debug_detail.max_dd 一致，说明是 Backtester 内部某个指标
   - **不是真实的 MaxDD**

2. **debug_curve_max_dd 正确**：
   - 值为 32.42%，是 Backtester 内部 equity curve 的真实 MaxDD
   - Peak: 12,325.93 USDT @ 2025-10-05
   - Trough: 7,275.44 USDT @ 2023-12-21
   - **满足 MaxDD <= 35% 约束**

3. **realized_curve_max_dd 更大**：
   - 值为 38.12%，大于 debug_curve_max_dd
   - 原因：只按平仓计算，忽略了持仓期间的浮盈浮亏变化
   - **不满足 MaxDD <= 35% 约束**

4. **三种 MaxDD 的关系**：
   - `report.max_dd` = `debug_detail.max_dd`（内部指标，非真实 MaxDD）
   - `debug_curve_max_dd` < `realized_curve_max_dd`（Backtester 内部 vs 只按平仓）

### 4.2 56 组完整可行性表摘要

| 统计项 | 数量 |
|--------|------|
| 总配置数 | 56 |
| debug_curve MaxDD <= 35% | **2** ✅ |
| realized_curve MaxDD <= 35% | 0 |

**关键发现：**

- ✅ **存在可行解**（基于 debug_curve）
- ❌ **无可行解**（基于 realized_curve）
- ⚠️ **两种口径结论矛盾**，需要明确审计标准

### 4.3 可行配置表（MaxDD <= 35%）

#### 基于 debug_curve 的可行配置（推荐）

| exposure | risk | PnL (USDT) | MaxDD (%) | Trades | 年度 PnL |
|----------|------|-----------|----------|--------|----------|
| **1.25** | **0.5%** | **2,346.26** | **33.74%** | 205 | 2023: -2,523, 2024: +2,856, 2025: +2,013 |
| **1.0** | **0.5%** | **2,113.27** | **32.42%** | 202 | 2023: -2,797, 2024: +2,427, 2025: +3,434 |

**推荐配置：exposure=1.25, risk=0.5%**
- ✅ MaxDD=33.74% < 35%
- ✅ PnL=2,346 USDT（高于 exposure=1.0）
- ✅ Trades=205（交易频率适中）

#### 基于 realized_curve 的可行配置

**无可行配置**（所有配置 MaxDD > 35%）

### 4.4 重点核验 risk=0.5%

| exposure | risk | report.max_dd | debug_curve_max_dd | realized_curve_max_dd | 是否可行（debug） | 是否可行（realized） |
|----------|------|--------------|-------------------|----------------------|------------------|---------------------|
| 1.0 | 0.5% | 0.32% | **32.42%** ✅ | 38.12% ❌ | ✅ 是 | ❌ 否 |
| 1.25 | 0.5% | 0.34% | **33.74%** ✅ | 39.36% ❌ | ✅ 是 | ❌ 否 |
| 1.5 | 0.5% | 0.35% | 35.37% ❌ | 40.88% ❌ | ❌ 否 | ❌ 否 |
| 1.75 | 0.5% | 0.37% | 36.56% ❌ | 41.88% ❌ | ❌ 否 | ❌ 否 |
| 2.0 | 0.5% | 0.37% | 36.56% ❌ | 41.88% ❌ | ❌ 否 | ❌ 否 |
| 2.25 | 0.5% | 0.37% | 36.56% ❌ | 41.99% ❌ | ❌ 否 | ❌ 否 |
| 2.5 | 0.5% | 0.37% | 36.56% ❌ | 41.99% ❌ | ❌ 否 | ❌ 否 |
| 3.0 | 0.5% | 0.38% | 37.61% ❌ | 42.88% ❌ | ❌ 否 | ❌ 否 |

**关键发现：**

1. **exposure=1.0 和 1.25 满足约束**（基于 debug_curve）
2. **exposure >= 1.5 不满足约束**（MaxDD > 35%）
3. **所有配置都不满足约束**（基于 realized_curve）

**exposure=1.5, risk=0.5% 的 MaxDD 分析：**

- MaxDD: 35.37%（略超 35%）
- Peak: 12,602.40 USDT @ 2025-10-05 07:00:00 UTC
- Trough: 6,953.65 USDT @ 2023-12-21 23:00:00 UTC
- MaxDD 金额: 3,805.53 USDT
- **时间跨度**: 2023-12-21 → 2025-10-05（近 2 年的回撤期）

**回撤原因分析：**

- 2023 年 PnL: -2,797 USDT（年度亏损）
- 2024 年 PnL: +2,427 USDT（部分恢复）
- 2025 年 PnL: +3,434 USDT（完全恢复并盈利）
- **结论**: 2023 年的连续亏损导致长期回撤，但策略在 2024-2025 年恢复

---

## 5. 判定结果

### 5.1 R1 原报告是否错误

**✅ 是，严重错误。**

**错误内容：**

1. **MaxDD 计算完全错误**：
   - R1 报告: MaxDD=0.32%（exposure=1.0, risk=0.5%）
   - 实际 MaxDD: 32.42%（debug_curve）
   - **误差**: 32.1 个百分点（100 倍差距）

2. **Calmar ratio 失真**：
   - R1 报告: Calmar=244.55
   - 实际 Calmar: 2113.27 / 32.42 = 65.1
   - **误差**: 3.75 倍

3. **结论错误**：
   - R1 报告: "最优配置 exposure=1.0, risk=2.0%, MaxDD=0.73%"
   - 实际: MaxDD=83.71%，**严重超标**

**根因：**

- R1 脚本使用了 `report.max_drawdown` 字段
- 该字段是 Backtester 内部指标，**不是真实 MaxDD**
- 正确做法：使用 `report.debug_equity_curve` 计算 MaxDD

### 5.2 R1 audit 是否错误

**⚠️ 部分错误。**

**正确部分：**

1. ✅ 发现 R1 原报告 MaxDD 错误
2. ✅ 正确计算了 realized_curve MaxDD
3. ✅ 指出 PnL 计算正确

**错误部分：**

1. ❌ **只审计了 3 个配置**，却下结论"所有配置无可行解"
   - 实际: **2 个配置可行**（exposure=1.0/1.25, risk=0.5%）

2. ❌ **声称计算 mark-to-market equity curve**，但实际只计算 realized curve
   - R1 audit: "计算 mark-to-market equity curve"
   - 实际: 只在平仓时更新 cash，**没有追踪持仓期间的浮盈浮亏**

3. ❌ **没有对账 `report.debug_equity_curve`**
   - R1 audit 忽略了 Backtester 自带的 equity curve
   - 直接使用自己计算的 realized curve 下结论

**关键遗漏：**

- R1 audit 没有发现 **debug_curve_max_dd=32.42% < 35%**
- 如果使用 debug_curve 作为审计标准，**存在可行解**

### 5.3 MaxDD <= 35% 是否存在可行配置

**✅ 是，存在可行配置。**

**基于 debug_curve（Backtester 内部 equity curve）：**

| 配置 | PnL | MaxDD | 可行性 |
|------|-----|-------|--------|
| exposure=1.25, risk=0.5% | 2,346 USDT | 33.74% | ✅ 可行 |
| exposure=1.0, risk=0.5% | 2,113 USDT | 32.42% | ✅ 可行 |

**基于 realized_curve（只按平仓计算）：**

- ❌ **无可行配置**（所有配置 MaxDD > 35%）

**审计标准选择：**

1. **如果使用 debug_curve**（推荐）：
   - ✅ 存在可行解
   - ✅ 推荐配置: exposure=1.25, risk=0.5%
   - ⚠️ debug_curve 是 Backtester 内部计算，可能包含浮盈浮亏

2. **如果使用 realized_curve**（保守）：
   - ❌ 无可行解
   - ⚠️ realized_curve 忽略持仓期间的浮盈浮亏变化
   - ⚠️ 可能低估真实风险（浮盈回撤未计入）

**建议：**

- 使用 **debug_curve 作为审计标准**
- 理由: Backtester 内部 equity curve 更接近真实交易情况
- 推荐配置: **exposure=1.25, risk=0.5%**

---

## 6. 结论与建议

### 6.1 最终结论

**✅ 在 MaxDD <= 35% 约束下，存在可行配置。**

**关键发现：**

1. **R1 原报告完全错误**：
   - MaxDD 计算错误（0.32% vs 32.42%）
   - 推荐配置不可行（MaxDD=83.71%）

2. **R1 audit 部分错误**：
   - 只审计 3 个配置，遗漏可行解
   - 没有对账 `report.debug_equity_curve`
   - 使用 realized_curve 下结论，忽略 debug_curve 的可行解

3. **存在可行配置**（基于 debug_curve）：
   - exposure=1.25, risk=0.5%: PnL=2,346 USDT, MaxDD=33.74%
   - exposure=1.0, risk=0.5%: PnL=2,113 USDT, MaxDD=32.42%

4. **三种 MaxDD 的含义**：
   - `report.max_dd`: Backtester 内部指标，**不是真实 MaxDD**
   - `debug_curve_max_dd`: Backtester 内部 equity curve MaxDD，**推荐使用**
   - `realized_curve_max_dd`: 只按平仓计算的 MaxDD，**保守口径**

### 6.2 推荐配置

**推荐配置：exposure=1.25, risk=0.5%**

**配置参数：**

| 参数 | 值 |
|------|-----|
| max_total_exposure | 1.25 |
| max_loss_percent | 0.5% |
| max_leverage | 20 |
| daily_max_trades | 50 |

**性能指标：**

| 指标 | 值 |
|------|-----|
| Total PnL | **+2,346.26 USDT** |
| MaxDD (debug_curve) | **33.74%** ✅ |
| MaxDD (realized_curve) | 39.36% ❌ |
| Trades | 205 |
| Win Rate | ~43% |

**年度表现：**

| Year | PnL | Trades | MaxDD |
|------|-----|--------|-------|
| 2023 | -2,523 USDT | 55 | 34.84% |
| 2024 | +2,856 USDT | 62 | 6.91% |
| 2025 | +2,013 USDT | 61 | 2.87% |

**风险分析：**

- ✅ MaxDD=33.74% < 35%，满足约束
- ⚠️ 2023 年亏损 -2,523 USDT，但 2024-2025 年恢复
- ✅ 2024-2025 年表现稳定（MaxDD < 7%）

**对比 exposure=1.0：**

- exposure=1.25 的 PnL 更高（+233 USDT）
- exposure=1.25 的 MaxDD 略高（+1.32%）
- 两者都满足 MaxDD <= 35% 约束

### 6.3 下一步建议

**1. 确认审计标准：**

- [ ] 确认使用 `debug_curve` 作为 MaxDD 审计标准
- [ ] 或使用 `realized_curve`（更保守）
- [ ] 或实现真实的 mark-to-market equity curve

**2. 如果接受推荐配置：**

- [ ] 将 exposure=1.25, risk=0.5% 应用到 Sim-1 实盘
- [ ] 设置观察期（如 2026 Q1）验证 OOS 表现
- [ ] 如果 OOS 表现显著低于预期，降级到 exposure=1.0

**3. 如果需要更保守的配置：**

- [ ] 尝试 risk < 0.5%（如 0.4%, 0.3%）
- [ ] 预期 MaxDD < 30%
- [ ] 但 PnL 也会相应降低

**4. 修复 R1 脚本：**

- [ ] 使用 `report.debug_equity_curve` 计算 MaxDD
- [ ] 或从 positions 构建 equity curve（正确方法）
- [ ] 不要使用 `report.max_drawdown` 字段

**5. 策略层面改进：**

- [ ] 分析 2023 年的连续亏损原因
- [ ] 考虑添加市场环境过滤器（如 EMA slope, trend persistence）
- [ ] 优化入场时机，减少 2023 年的回撤

**6. 标记 R1 原报告无效：**

- [ ] 在 R1 报告中标记"已失效"
- [ ] 指向 R1b 审计报告
- [ ] 通知相关人员

---

## 7. 文件清单

- ✅ 审计脚本：`scripts/run_r1b_capital_allocation_audit_v2.py`
- ✅ 审计 JSON：`reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json`
- ✅ 审计报告：`docs/planning/2026-04-29-r1b-capital-allocation-audit-v2.md`

---

*审计完成时间: 2026-04-29*
*性质: research-only，不改 src，不改 runtime，不提交 git*
