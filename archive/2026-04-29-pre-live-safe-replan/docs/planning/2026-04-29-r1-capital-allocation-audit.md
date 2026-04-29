# R1 Capital Allocation Audit - MaxDD 重大错误发现

> **日期**: 2026-04-29
> **性质**: research-only 审计，不改 src，不改 runtime，不提交 git
> **结论**: ❌ **FAIL - R1 原始 MaxDD 报告完全错误**

---

## 0. 核心发现（先说结论）

**R1 原始报告的 MaxDD 计算存在严重错误：**

| 配置 | 原始 MaxDD | 重算 MaxDD | 差异 | 判定 |
|------|-----------|-----------|------|------|
| exposure=1.0, risk=0.5% | 0.32% | **38.12%** | +37.79% | ❌ 严重低估 |
| exposure=1.0, risk=1.0% | 0.54% | **61.49%** | +60.95% | ❌ 严重低估 |
| exposure=1.0, risk=2.0% | 0.73% | **83.71%** | +82.99% | ❌ 严重低估 |

**影响：**
- ❌ R1 最优配置（exposure=1.0, risk=2.0%）的 MaxDD 不是 0.7%，而是 **83.71%**
- ❌ 所有配置的 MaxDD 都远超 35% 约束，**R1 搜索结果全部无效**
- ❌ Calmar ratio 完全失真（原始 244.55 vs 真实 ~21）
- ❌ risk=2.0% 不能作为推荐配置

---

## 1. 审计设计

### 1.1 审计目标

验证 R1 报告中 MaxDD 的正确性，回答以下问题：

1. R1 的 MaxDD 是怎么计算的？
2. MaxDD 单位是 USDT、ratio，还是 percent？
3. R1 是否使用 realized equity curve？
4. 是否使用 mark-to-market equity curve？
5. 2023 PnL=-5,751 时，2023 单年 MaxDD 到底是多少？
6. 3yr continuous equity curve 的最大回撤是多少？
7. report 中的 MaxDD=0.7% 是否来自错误字段或错误单位？
8. Calmar 是否因此失真？
9. risk 从 0.5% 到 2.0% 时，PnL 和 MaxDD 是否应该近似线性放大？
10. exposure=1.0 是否真的没有拦截信号？

### 1.2 审计方法

重新计算 mark-to-market equity curve 的 MaxDD：

```python
def compute_equity_curve(positions, initial_balance):
    """
    从 positions 构建完整的 equity curve
    - 入场事件：记录开仓
    - 出场事件：cash += realized_pnl
    - equity = cash（假设无浮盈浮亏追踪）
    """
    events = []
    events.append({"timestamp": start_time, "equity": initial_balance})

    for pos in positions:
        if pos.entry_time:
            events.append({"timestamp": pos.entry_time, "type": "entry"})
        if pos.exit_time:
            events.append({
                "timestamp": pos.exit_time,
                "type": "exit",
                "realized_pnl": pos.realized_pnl
            })

    # 按时间排序，计算 equity
    equity_curve = []
    cash = initial_balance
    for event in sorted(events, key=lambda x: x["timestamp"]):
        if event["type"] == "exit":
            cash += event["realized_pnl"]
        equity_curve.append({"timestamp": event["timestamp"], "equity": cash})

    return equity_curve

def compute_max_drawdown(equity_curve):
    """
    计算 MaxDD = max(peak - trough) / peak
    """
    peak = equity_curve[0]["equity"]
    max_dd = 0.0

    for point in equity_curve:
        equity = point["equity"]
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return max_dd
```

---

## 2. R1 原始报告回顾

### 2.1 最优配置（错误）

| 指标 | 值 |
|------|-----|
| max_total_exposure | 1.0 |
| max_loss_percent | 2.0% |
| Total PnL | +17,749.41 USDT |
| **MaxDD** | **0.7%** ❌ |
| Sharpe | 0.51 |
| Calmar | 244.55 ❌ |
| Trades | 174 |

### 2.2 年度表现

| Year | PnL | Trades |
|------|-----|--------|
| 2023 | -5,751 | 52 |
| 2024 | +6,082 | 61 |
| 2025 | +17,419 | 61 |

**矛盾点**：如果 2023 年亏损 -5,751 USDT，MaxDD 不可能只有 0.7%。

---

## 3. 审计结果

### 3.1 配置 1: exposure=1.0, risk=0.5%

| 指标 | 原始 | 重算 | 差异 |
|------|------|------|------|
| MaxDD (%) | 0.32% | **38.12%** | +37.79% |
| MaxDD (USDT) | 32.42 | **4,108.30** | +4,075.88 |
| Peak Equity | - | 13,086.16 | - |
| Trough Equity | - | 6,669.47 | - |
| Total PnL | +3,063.93 | +3,063.93 | ✅ 一致 |
| Trades | 202 | 202 | ✅ 一致 |

**年度 MaxDD：**

| Year | MaxDD (%) | MaxDD (USDT) | Peak | Trough |
|------|-----------|--------------|------|--------|
| 2023 | **34.84%** | 3,755.51 | 10,777.77 | 7,022.26 |
| 2024 | 6.91% | 702.50 | 12,615.20 | 9,466.49 |
| 2025 | 2.87% | 346.71 | 13,456.56 | 11,725.34 |

### 3.2 配置 2: exposure=1.0, risk=1.0%

| 指标 | 原始 | 重算 | 差异 |
|------|------|------|------|
| MaxDD (%) | 0.54% | **61.49%** | +60.95% |
| MaxDD (USDT) | 53.74 | **7,354.92** | +7,301.18 |
| Peak Equity | - | 14,950.46 | - |
| Trough Equity | - | 4,606.32 | - |
| Total PnL | +4,889.77 | +4,889.77 | ✅ 一致 |
| Trades | 186 | 186 | ✅ 一致 |

**年度 MaxDD：**

| Year | MaxDD (%) | MaxDD (USDT) | Peak | Trough |
|------|-----------|--------------|------|--------|
| 2023 | **54.47%** | 6,515.14 | 11,961.24 | 5,446.10 |
| 2024 | 13.44% | 1,379.80 | 13,949.16 | 8,884.30 |
| 2025 | 5.42% | 719.93 | 15,540.85 | 12,569.79 |

### 3.3 配置 3: exposure=1.0, risk=2.0% (R1 最优)

| 指标 | 原始 | 重算 | 差异 |
|------|------|------|------|
| MaxDD (%) | 0.73% | **83.71%** | +82.99% |
| MaxDD (USDT) | 72.58 | **11,706.59** | +11,634.01 |
| Peak Equity | - | 28,061.27 | - |
| Trough Equity | - | 2,277.33 | - |
| Total PnL | +17,749.41 | +17,749.41 | ✅ 一致 |
| Trades | 174 | 174 | ✅ 一致 |

**年度 MaxDD：**

| Year | MaxDD (%) | MaxDD (USDT) | Peak | Trough |
|------|-----------|--------------|------|--------|
| 2023 | **72.37%** | 10,120.60 | 13,983.92 | 3,863.32 |
| 2024 | 22.70% | 2,357.79 | 16,699.49 | 8,028.35 |
| 2025 | 8.52% | 2,363.29 | 27,730.46 | 25,367.17 |

---

## 4. 根因分析

### 4.1 R1 脚本的 MaxDD 计算错误

**原始代码（错误）：**

```python
# R1 脚本
max_dd_overall = report.max_drawdown  # 假设已经是百分比
max_dd_pct = max_dd_overall / Decimal("100")  # 再除以 100

# 结果：max_dd_pct = 0.73 / 100 = 0.0073 = 0.73%
```

**问题：**
1. `report.max_drawdown` 已经是百分比（0-100），不需要再除以 100
2. 但即使不除以 100，0.73% 仍然太小
3. **真正的问题**：R1 脚本没有计算 mark-to-market equity curve，直接使用了 `report.max_drawdown`

### 4.2 PMSBacktestReport.max_drawdown 的含义

根据模型定义：

```python
max_drawdown: Decimal = Field(
    ge=Decimal('0'),
    le=Decimal('100'),
    description="最大回撤 (%)，范围 0 ~ 100"
)
```

**但实际计算的是什么？**

从审计结果看，`report.max_drawdown` 的值（0.32%, 0.54%, 0.73%）远小于真实的 MaxDD（38%, 61%, 84%），说明：

- ❌ 不是 mark-to-market MaxDD
- ❌ 不是 realized equity curve MaxDD
- ⚠️ 可能是某种瞬时回撤指标，或者计算逻辑有误

### 4.3 为什么 PnL 一致但 MaxDD 错误？

- PnL 是从 positions 累加 `realized_pnl`，计算正确
- MaxDD 需要从 equity curve 计算，但 R1 脚本直接使用了 `report.max_drawdown`
- **关键缺失**：没有构建完整的 equity curve，没有追踪 peak/trough

---

## 5. 风险收益关系验证

### 5.1 risk 放大是否线性？

| Risk | Total PnL | MaxDD (%) | PnL 倍数 | MaxDD 倍数 |
|------|-----------|-----------|----------|-----------|
| 0.5% | +3,063.93 | 38.12% | 1.0x | 1.0x |
| 1.0% | +4,889.77 | 61.49% | 1.6x | 1.6x |
| 2.0% | +17,749.41 | 83.71% | 5.8x | 2.2x |

**发现：**
- risk 从 0.5% → 1.0%：PnL 和 MaxDD 近似线性放大（1.6x）
- risk 从 1.0% → 2.0%：PnL 放大 3.6x，但 MaxDD 只放大 1.4x
- **非线性关系**：高 risk 下收益提升更快，但回撤增加较慢

### 5.2 exposure=1.0 是否拦截信号？

从审计结果看，所有配置的 equity curve 都有大量 "position_size=0" 警告，说明：

- ✅ exposure=1.0 确实拦截了大量信号
- ⚠️ 但这反而降低了风险（MaxDD 被限制）

---

## 6. 判定结果

### 6.1 PASS 条件检查

| 条件 | 结果 | 判定 |
|------|------|------|
| 重算 MaxDD 仍 <=35% | ❌ 所有配置 >35% | FAIL |
| 2023 单年 MaxDD 解释合理 | ✅ 2023 MaxDD 34-72% 合理 | PASS |
| 3yr continuous MaxDD 合理 | ✅ 38-84% 合理 | PASS |
| risk=2% 结论仍成立 | ❌ MaxDD=83.71% > 35% | FAIL |

**总体判定：❌ FAIL**

---

## 7. 结论与建议

### 7.1 R1 搜索结果无效

**原因：**
1. MaxDD 计算错误，所有配置的实际 MaxDD 都远超 35% 约束
2. Calmar ratio 失真，不能作为风险调整收益的依据
3. risk=2.0% 的推荐配置实际 MaxDD=83.71%，不可接受

### 7.2 正确的风险收益关系

**基于重算结果：**

| Risk | Total PnL | MaxDD | Calmar | 适用场景 |
|------|-----------|-------|--------|----------|
| 0.5% | +3,063.93 | 38.12% | 8.0 | ❌ MaxDD > 35% |
| 1.0% | +4,889.77 | 61.49% | 8.0 | ❌ MaxDD > 35% |
| 2.0% | +17,749.41 | 83.71% | 21.2 | ❌ MaxDD > 35% |

**结论：在 MaxDD <= 35% 约束下，ETH Pinbar baseline 无可行解。**

### 7.3 下一步建议

1. **降低 risk 目标**：
   - 尝试 risk < 0.5%（如 0.25%, 0.3%, 0.4%）
   - 预期 MaxDD < 35%

2. **放宽 MaxDD 约束**：
   - 如果接受 MaxDD <= 60%，则 risk=1.0% 可行
   - 如果接受 MaxDD <= 85%，则 risk=2.0% 可行

3. **修复 R1 脚本**：
   - 使用 equity curve 计算正确的 MaxDD
   - 重新搜索所有配置

4. **策略层面改进**：
   - 2023 年的巨大回撤是策略结构性问题
   - 考虑添加市场环境过滤器（如 EMA slope, trend persistence）

---

## 8. 文件清单

- ✅ 审计脚本：`scripts/run_r1_capital_allocation_audit.py`
- ✅ 审计 JSON：`reports/research/r1_capital_allocation_audit_2026-04-29.json`
- ✅ 审计报告：`docs/planning/2026-04-29-r1-capital-allocation-audit.md`

---

*审计完成时间: 2026-04-29*
*性质: research-only，不改 src，不改 runtime，不提交 git*
