# T1: True Trend Follower Prototype — 研究方案

> **日期**: 2026-04-28
> **性质**: research-only 方案设计，不改 src，不跑回测，不提交 git
> **定位**: B 线（趋势跟随），与 A 线（M1 Toxic State Avoidance / Pinbar 优化）互补
> **基线参照**: ETH 1h LONG-only Pinbar + EMA50 + MTF 4h EMA60, TP=[1.0R, 3.5R], BE=False

---

## 0. 为什么需要 T1

M0 Strategy Ecology Map 的结论：当前 Pinbar baseline 更像**顺大背景下的回撤修复策略**（逆小顺大），不是真正吃大段趋势。

| 维度 | Pinbar (当前) | T1 目标 |
|------|--------------|---------|
| 入场 | 趋势中回撤到极端位置时反转入场 | 趋势突破确认时顺势入场 |
| 出场 | 固定 TP=[1.0R, 3.5R]，主动止盈 | ATR trailing，让利润奔跑 |
| 胜率 | 27-33%（低） | 预期 25-35%（允许更低） |
| 盈亏比 | TP 几何固定，上限受限 | 无固定上限，趋势越长收益越大 |
| 持仓 | 17h-335h（年份差异大） | 预期 2-10 天（趋势驱动） |
| 2023 行为 | 趋势不延续 → 频繁止损 → -3,924 | 突破少 + trailing 保护 → 预期亏损可控 |

**核心差异**: Pinbar 是均值回归入场 + 固定止盈；T1 是动量突破入场 + 动态止盈。两者在市场微观结构上互补。

---

## A. T1 推荐策略

### 推荐: 4h Donchian 20-bar Breakout + ATR Trailing Exit

**一句话定义**: 4h 收盘价突破过去 20 根 4h K 线的最高价时做多，用 ATR 动态 trailing stop 替代固定 TP，让趋势利润奔跑。

### 为什么是 4h Donchian + ATR Trailing，而不是其他三个方向

| 候选 | 优点 | 致命缺陷 | 判定 |
|------|------|----------|------|
| **4h Donchian + ATR trailing** | 信号少、通道宽、trailing 无上限 | 通道可能滞后 | **推荐** |
| 4h EMA trend continuation | 简单 | 入场时机模糊（EMA 交叉滞后严重），无法精确定义"入场点" | 不推荐 |
| 4h breakout + ATR trailing（无 Donchian） | 和推荐方案接近 | 缺少明确的突破定义，"breakout" 需要具体化 | 等价于推荐方案 |
| 1h entry + 4h trend + trailing | 精细 | 过于复杂，原型阶段应最小化变量；1h 入场仍有噪音 | 过早 |

### 核心设计参数

| 参数 | 值 | 理由 |
|------|-----|------|
| timeframe | **4h** | 20-bar = 80h = 3.3 天通道，过滤 1h 噪音 |
| lookback | **20 bars** (80h) | Donchian 经典参数；4h 下覆盖一周趋势 |
| entry | close > max(high[-20:]) | 收盘确认突破，减少假突破 |
| initial SL | min(low[-20:]) | 通道底部，逻辑清晰 |
| exit | **ATR(14) trailing**，无固定 TP | 核心差异点——让利润奔跑 |
| trailing activation | 1.5R profit | 过早激活会被噪音震出 |
| trailing distance | 2.0 × ATR(14) | 适应当前波动率，不是固定百分比 |
| direction | LONG-only（原型阶段） | 与 Pinbar 对比公平 |
| risk per trade | 1% (max_loss_percent) | 与 Pinbar baseline 一致 |
| max_total_exposure | 2.0 (Research 口径) | 与 Pinbar baseline 一致 |
| fee + slippage | 0.0405% + 0.01% | 与 Pinbar baseline 一致 |

---

## B. 和 Pinbar Baseline 的互补逻辑

### 相关性来源分析

| 维度 | Pinbar | T1 Donchian | 互补机制 |
|------|--------|-------------|----------|
| 入场触发 | 回撤到极值 → 反转 | 突破通道 → 顺势 | 方向一致但时机不同 |
| 趋势中行为 | 捕捉回调入场点，吃回撤恢复段 | 突破确认后入场，吃趋势延续段 | 同一趋势的不同阶段 |
| 2023 行为 | 趋势不延续 → 61% SL | 通道窄 → 突破少 → 少入场 | 预期 T1 在 2023 信号更少 |
| 2024/2025 行为 | TP2 达成率 20%，avg hold 335h | trailing 让趋势跑满 | T1 可能在趋势段捕获更多 |
| 出场逻辑 | 固定 TP，利润封顶 | ATR trailing，利润无上限 | T1 在强趋势年份应显著优于 Pinbar |

### 年度相关性预期

| 年份 | Pinbar | T1 预期行为 | 相关性 |
|------|--------|------------|--------|
| 2023 | -3,924 | 趋势不延续 → 假突破多 → 小亏或持平 | **低相关**（T1 亏损应远小于 Pinbar） |
| 2024 | +8,501 | 强趋势 → 突破后 trailing 跑满 → 大赚 | **中正相关**（同方向但捕获机制不同） |
| 2025 | +4,490 | 趋势适中 → 突破+trailing → 正收益 | **中正相关** |

**关键差异点**: 如果 2023 T1 亏损远小于 Pinbar（因为信号少 + trailing 保护），而 2024/2025 T1 收益不低于 Pinbar，则组合后 Sharpe 改善。

---

## C. 和 H6a 失败模式的区别

H6a Donchian 20-bar **1h** 失败了。T1 是 Donchian 20-bar **4h**。区别不是"换个周期试试"，而是结构性差异：

### 通道宽度

| 维度 | H6a (1h) | T1 (4h) |
|------|----------|---------|
| 20-bar 窗口 | 20h（不到 1 天） | 80h（3.3 天） |
| 通道宽度（ETH 典型） | ~1-2% | ~4-8% |
| 突破意义 | 噪音级别，频繁触发 | 周级别突破，更有意义 |
| 假突破概率 | 极高（日内波动频繁穿透） | 较低（需要持续 3+ 天趋势） |

### 信号频率

| 维度 | H6a (1h) | T1 (4h) |
|------|----------|---------|
| 年均 signals | ~648 | ~162（4x 少） |
| 年均 trades | ~424 | ~100（预估） |
| 费用侵蚀 | $1,795/yr (2022) | 预估 < $500/yr |
| 过度交易 | 严重 | 可控 |

### 出场机制（最关键差异）

| 维度 | H6a | T1 |
|------|-----|-----|
| TP 结构 | 固定 TP=[1.0R, 3.5R] | **无固定 TP，ATR trailing** |
| 趋势捕获上限 | 3.5R 封顶 | **无上限** |
| 止损后行为 | 被动止损，等待下一次突破 | trailing 主动保护利润 |
| 与 H2/H3 失败的关系 | 同样受困于固定 TP 几何 | **脱离固定 TP，从根本上不同** |

### 一句话区别

> H6a 失败于"信号过频 + 固定 TP 出场"；T1 用更宽时间框架解决信号过频，用 ATR trailing 解决固定 TP 上限。两处都做了结构性改变，不是参数微调。

---

## D. 入场 / 出场 / 止损逻辑

### 入场逻辑

```
SIGNAL BAR (4h, closed):
  signal_high = max(high[-20:])    # 过去 20 根 4h K 线最高价（不含 signal bar）
  signal_low  = min(low[-20:])     # 过去 20 根 4h K 线最低价（不含 signal bar）

LONG ENTRY:
  if signal_bar.close > signal_high:
    direction = LONG
    entry_price = next_4h_bar.open × (1 + slippage)
    initial_stop = signal_low       # 通道底部
    risk_per_unit = entry_price - initial_stop
```

**反前瞻保证**:
- `signal_high/low` 使用 `history[-20:]`，不含 signal bar 本身
- 入场价用 next bar open（T+1 延迟）
- 只在 signal bar **closed** 后触发

### 止损逻辑

```
INITIAL STOP:
  LONG: stop_price = signal_low (Donchian 20 通道底部)

  → 这比 Pinbar 的 "signal_k.low" 更宽（80h 通道 vs 1h K 线）
  → 容忍更大回撤，减少被噪音震出

POSITION SIZE (与 Pinbar 相同):
  risk_amount = account_balance × max_loss_percent (1%)
  position_size = risk_amount / (entry_price - initial_stop)
```

### 出场逻辑（核心创新：ATR Trailing，无固定 TP）

```
PHASE 1 — 等待激活（profit < 1.5R）:
  保持 initial stop 不变
  不设 TP 目标

PHASE 2 — Trailing 激活（profit >= 1.5R）:
  trail_price = watermark_high - 2.0 × ATR(14, 4h)
  stop_price = max(current_stop, trail_price)    # 只向上移动，不回退

PHASE 3 — 持续跟踪:
  每根 4h K 线收盘后更新:
    watermark_high = max(watermark_high, bar.high)
    new_trail = watermark_high - 2.0 × ATR(14, 4h)
    stop_price = max(stop_price, new_trail)      # 单调递增

EXIT:
  当 bar.low <= stop_price:
    exit_price = stop_price × (1 - slippage)
    pnl = (exit_price - entry_price) × position_size - fees
```

### 为什么不用固定 TP

| 固定 TP 问题 | T1 解决方式 |
|-------------|------------|
| H2 证明 TP=[1.0, 3.5] 系统性 missed winners（2024 missed 56%） | Trailing 无上限，不 missed |
| H3 证明固定 TP 无法区分好坏环境 | ATR trailing 自适应波动率 |
| H6a TP1=1.0R 过早兑现，大段趋势被截断 | Trailing 在 1.5R 后才激活，之前不动 |
| 2023 趋势短促，固定 TP 在好年份同样受限 | Trailing 在短趋势中退化为固定止损（自然适应） |

### 持仓周期预期

| 环境 | 预期持仓 | 原因 |
|------|----------|------|
| 2023 (趋势不延续) | 2-5 天 | 突破后很快回落触发 trailing → 快速出场 |
| 2024 (强趋势) | 1-4 周 | trailing 跟随趋势，直到趋势反转 |
| 2025 (适中趋势) | 5-15 天 | 中等持仓 |

### 胜率预期

| 指标 | Pinbar baseline | T1 预期 |
|------|----------------|---------|
| Win Rate | 27-33% | **25-35%**（允许更低） |
| Avg Win / Avg Loss | ~1.0-1.3R（受 TP 封顶） | **2.0-4.0R**（trailing 无上限） |
| Profit Factor | ~0.9-1.2 | **目标 > 1.0** |

**核心理念**: 趋势跟随策略的数学特征是低胜率 + 高盈亏比。胜率不重要，avg win / avg loss 才是关键。

---

## E. 主要风险

| 风险 | 描述 | 缓解 |
|------|------|------|
| **假突破** | 4h 收盘突破但很快回落 | Trailing 在 1.5R 前用固定止损保护；20-bar 通道已过滤大部分噪音 |
| **通道滞后** | 20-bar 4h = 3.3 天，入场可能偏晚 | 可接受——trend following 的本质就是确认后入场，牺牲入场点换确定性 |
| **Trailing 被震出** | 趋势中的正常回调触发 trailing | 2.0×ATR trailing 距离足够宽（ETH 4h ATR ~1.5-3%，trailing 距 3-6%） |
| **2023 假突破密集** | 震荡市中通道频繁突破又回落 | 预期信号少（4h 20-bar），单笔亏损有限（1% risk），总亏损可控 |
| **ATR 周期选择** | ATR(14) 4h = 56h 窗口，可能不适应所有环境 | 原型阶段先固定，后续可做 ATR period sensitivity |
| **与 Pinbar 持仓重叠** | 同时持有 Pinbar LONG + T1 LONG | max_total_exposure=2.0 限制总敞口；实际运行时需协调 |

---

## F. 反前瞻保证

| 检查项 | 实现方式 |
|--------|----------|
| Donchian high/low | `history[-20:]`，不含 signal bar |
| 入场价 | next 4h bar open + slippage (T+1) |
| ATR(14) | 用 signal bar 及之前 14 根 4h K 线计算（已收盘数据） |
| Trailing stop 更新 | 每根 4h K 线 **收盘后** 更新，不使用盘中数据 |
| TP/SL 检查 | 后续 bar 上检查（非 signal bar 同 bar） |

---

## G. Research-Only Proxy 可行性

### 可行，且已有完整基础设施

| 需要的能力 | 已有基础设施 | 来源 |
|-----------|-------------|------|
| 4h K 线数据 | `HistoricalDataRepository` 支持 4h（11,496 bars in v3_dev.db） | H5a 验证 |
| ATR(14) 计算 | `ATRVolatilityFilter`（Wilder's ATR, period=14） | filter_factory.py |
| Trailing exit 执行 | `trailing_exit_enabled` + `_execute_trailing_exit()` | backtester.py (ADR-2026-04-20) |
| Backtest 撮合 | `Backtester` + `BacktestRuntimeOverrides` | 已有 |
| 外部 gating 模式 | H0/H6a 脚本模式 | 已验证 |
| kline_history 支持 | H5a 修复后已可用 | strategy_engine.py |

### 实现路径

**方案 A（推荐）: 纯 proxy 脚本 + backtester trailing exit**

```
1. 脚本加载 4h K 线数据
2. 对每根 4h K 线:
   a. 检查是否 closed
   b. 计算 Donchian 20 high/low（用 history[-20:]）
   c. 如果 close > Donchian 20 high → 生成 LONG signal
3. 将信号传入 Backtester:
   - strategy: custom Donchian breakout
   - trailing_exit_enabled=True
   - trailing_exit_activation_rr=1.5
   - trailing_exit_percent=2.0 × ATR(14) / entry_price（动态计算）
4. Backtester 撮合 + trailing exit 执行
5. 输出: 分年 PnL, Trades, WR, Sharpe, MaxDD, Avg Hold, Profit Factor
```

**方案 B（更轻量）: 独立 proxy，不依赖 backtester trailing**

```
1. 脚本加载 4h K 线
2. 生成 Donchian 突破信号
3. 用简单循环模拟:
   - 入场: next bar open
   - 每 bar 检查 trailing stop
   - 退出: stop 被触发
4. 计算 proxy metrics
```

**推荐方案 A**：复用 backtester 撮合逻辑，结果更可信。方案 B 可作为快速验证。

---

## H. 最小 Proxy 实验设计

### 实验矩阵

| 实验 | Entry | Exit | Filter | 目的 |
|------|-------|------|--------|------|
| **E0** | Donchian 4h 20-bar breakout | ATR trailing (2.0×ATR14, activation=1.5R) | 无 | 主实验 |
| **E1** | Donchian 4h 20-bar breakout | ATR trailing (2.0×ATR14, activation=1.5R) | EMA50 4h bullish | 趋势过滤变体 |
| **E2** | Donchian 4h 20-bar breakout | ATR trailing (3.0×ATR14, activation=2.0R) | 无 | trailing 宽度敏感度 |
| **E3** | Donchian 4h **30-bar** breakout | ATR trailing (2.0×ATR14, activation=1.5R) | 无 | lookback 敏感度 |
| **Pinbar ref** | Pinbar 1h EMA50 MTF | TP=[1.0, 3.5] | EMA50+MTF | 对照组（已有数据） |

### 数据范围

- **主测试**: 2022, 2023, 2024, 2025（4 年完整）
- **OOS 验证**: 2026 Q1（如数据可用）
- **风险口径**: Research (exposure=2.0) + Sim-1 (exposure=1.0) 双口径

### 输出指标

**必须输出**:
- 分年: PnL, Trades, Win Rate, Sharpe, MaxDD, Avg Hold (h)
- Profit Factor = gross_profit / gross_loss
- Avg Win / Avg Loss (R 倍数)
- 单笔最大盈利（占总 PnL 比例）
- Trailing exit 触发次数和 avg trail duration

**Pinbar 对比输出**:
- 年度 PnL 相关系数
- 组合 PnL（假设 50/50 资金分配）
- 组合 MaxDD

### 判定标准

| 指标 | 通过门槛 | 说明 |
|------|----------|------|
| **3yr PnL** | > 0 | 基本要求 |
| **Profit Factor** | > 1.0 | 正期望 |
| **Avg Win / Avg Loss** | > 1.5R | 高盈亏比是核心目标 |
| **2024+2025 PnL** | > 0 | 趋势年份必须正收益 |
| **2023 PnL** | > -2,000 | 亏损可控（Pinbar 2023 = -3,924） |
| **MaxDD** | 记录但不硬门槛 | 不以 MaxDD<30% 作为通过条件 |
| **与 Pinbar 年度相关性** | < 0.7 | 低相关才有组合价值 |
| **单笔最大盈利 / 总 PnL** | < 50% | 不能依赖单笔 |

### 判定逻辑

```
IF 3yr PnL > 0 AND PF > 1.0 AND AvgWin/AvgLoss > 1.5R:
  → T1 通过，进入下一阶段（参数精调 / SHORT shadow / 多品种测试）
ELIF 3yr PnL > 0 AND PF > 0.8:
  → 边界通过，检查是否参数可调
ELSE:
  → T1 不通过，检查失败模式
```

---

## I. 如果 T1 失败，下一步是否继续趋势线

### 失败模式分类

| 失败模式 | 含义 | 下一步 |
|----------|------|--------|
| **信号过频** (trades > 300/yr) | 4h 20-bar 仍太窄 | 放宽到 4h 40-bar 或 1d 20-bar，或加 EMA 趋势过滤 |
| **假突破主导** (WR < 20%) | 突破后无法延续 | 检查是否需要成交量确认，或换入场逻辑（如 EMA crossover） |
| **Trailing 太紧** (avg win < 1.5R) | 趋势中被震出 | 放宽 trailing 距离（3.0×ATR → 4.0×ATR）或提高 activation |
| **Trailing 太松** (avg win 很大但 WR 极低) | 出场太晚，利润回吐 | 收紧 trailing 或加时间止损 |
| **全面亏损** (所有年份 < 0) | 策略逻辑本身不成立 | **停止趋势线研究**，回到 Pinbar 优化 |

### 决策树

```
T1 E0 失败？
├─ 信号过频 → T1 E3 (放宽 lookback) 或加 EMA filter
├─ 假突破 → 换入场逻辑（非 Donchian）
├─ Trailing 参数问题 → T1 E2 (调参)
├─ 全面亏损 → 检查 T1 E1 (加 EMA filter)
│   ├─ E1 仍亏损 → **停止趋势线**
│   └─ E1 正收益 → 继续 EMA+Donchian 组合方向
└─ 边界（3yr PnL ~0）→ 检查 2024/2025 是否正收益
    ├─ 是 → 2023 拖累，考虑是否接受
    └─ 否 → 策略不成立，停止
```

### 如果 T1 失败但有边界信号

不放弃趋势线，但调整方向：
1. **1d Donchian 20-bar** — 更长周期，更少信号，更强趋势过滤
2. **EMA crossover + trailing** — 放弃 Donchian，用趋势方向判断
3. **Multi-timeframe confirmation** — 4h 突破 + 1d 趋势确认

---

## J. 实验执行计划

### Phase 1: Proxy 脚本开发（~3h）

1. 编写 `scripts/run_t1_donchian_4h_proxy.py`
2. 加载 4h K 线数据（从 v3_dev.db）
3. 实现 Donchian 20-bar signal generation
4. 集成 backtester trailing exit 或独立模拟
5. 跑 E0-E3 四个实验

### Phase 2: 结果分析（~1h）

1. 输出分年 PnL / WR / Sharpe / MaxDD / PF
2. 与 Pinbar baseline 年度对比
3. 计算相关性
4. 检查单笔最大盈利占比

### Phase 3: 判定 + 决策（~0.5h）

1. 对照判定标准
2. 如通过 → 进入下一阶段设计
3. 如失败 → 按决策树分析

### 总耗时预估: ~4.5h

---

## K. 产出文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 本方案 | `docs/planning/2026-04-28-t1-true-trend-follower-prototype.md` | 研究方案 |
| Proxy 脚本 | `scripts/run_t1_donchian_4h_proxy.py` | E0-E3 实验 |
| 结果 JSON | `reports/research/t1_donchian_4h_proxy_2026-04-XX.json` | 原始数据 |
| 结果 MD | `docs/planning/2026-04-XX-t1-donchian-4h-results.md` | 分析报告 |

---

*方案完成时间: 2026-04-28*
*性质: research-only 方案设计，不改 src，不跑回测，不提交 git*
