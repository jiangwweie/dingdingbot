# M0 Strategy Ecology Map — Pinbar Baseline 市场状态 × 策略表现诊断

**日期**: 2026-04-28  
**假设**: M0 — 市场状态特征能区分 Pinbar 盈利/亏损状态  
**类型**: Proxy result（独立撮合，不等同正式 Backtester v3_pms result）  
**判定**: **PASS** — 6+ 特征有显著解释力，M0 有价值

---

## 实验目标

在盲目换 entry 策略之前，先建立市场状态与 Pinbar 表现的映射。如果能识别"什么环境下 Pinbar 赚钱、什么环境下亏钱"，就能指导下一步是补 entry、补 exit、还是补 regime filter。

## 方法

1. 独立 Pinbar 检测（复刻 src PinbarStrategy.detect() 逻辑）
2. 独立撮合（TP1=1.0R 50%, TP2=3.5R 50%, SL at signal K low/high, BE after TP1）
3. 在每个 signal time 计算 10 个 market state features
4. 按 feature tercile 分桶（low/mid/high）
5. 输出每桶的 trade_count / PnL / WR / avg_R / MaxDD

---

## 年度总览

| 年份 | Trades | PnL | WR | 状态 |
|------|--------|-----|-----|------|
| 2021 | 85 | -7,567 | 9.4% | warmup |
| 2022 | 82 | -2,099 | 12.2% | boundary |
| 2023 | 74 | -2,513 | 12.2% | failed |
| 2024 | 88 | +1,854 | 22.7% | adapted |
| 2025 | 82 | -1,499 | 13.4% | failed |

**注意**: 2021 包含 warmup 数据，不作为判定依据。Proxy PnL 与 official baseline 有差异（proxy 使用 2x exposure cap 简化撮合），但 WR 和 trade count 方向一致。

---

## 核心发现：10 特征分桶分析

### Tier 1: 强解释力（spread > 10,000）

| 特征 | Spread PnL | Best Bucket | Worst Bucket | 模式 |
|------|-----------|-------------|--------------|------|
| **ema_4h_slope** | 12,899 | low (+656) | high (-12,243) | 低斜率赚钱，高斜率亏钱 |
| **recent_72h_return** | 12,545 | low (+990) | high (-11,555) | 近期涨得多 → Pinbar 亏 |
| **distance_to_donchian_20_high** | 12,337 | mid (+654) | low (-11,682) | 接近通道顶部 → 亏 |
| **realized_volatility_24h** | 10,381 | low (-397) | high (-10,778) | 高波动 → Pinbar 亏 |
| **ema_1h_slope** | 10,020 | low (+267) | high (-9,753) | 低斜率赚钱，高斜率亏钱 |

### Tier 2: 中等解释力（spread 5,000-10,000）

| 特征 | Spread PnL | Best Bucket | Worst Bucket | 模式 |
|------|-----------|-------------|--------------|------|
| **price_dist_ema50** | 6,879 | mid (-1,533) | high (-8,413) | 远离 EMA → 亏 |
| **range_compression_24h** | 6,410 | high (-1,529) | mid (-7,939) | 非单调 |
| **atr_percentile** | 6,166 | low (-1,584) | high (-7,750) | 高 ATR → 亏 |

### Tier 3: 弱解释力（spread < 5,000）

| 特征 | Spread PnL | 模式 |
|------|-----------|------|
| recent_24h_return | 4,732 | 低收益赚钱（弱） |
| distance_to_donchian_20_low | 1,298 | 几乎无区分度 |

---

## 关键洞见

### 1. Pinbar 是反趋势策略

最强信号来自 **ema_4h_slope** 和 **ema_1h_slope**:
- 低斜率（横盘/弱趋势）→ Pinbar 赚钱
- 高斜率（强趋势）→ Pinbar 亏钱

**这解释了为什么 Donchian 20 (趋势跟踪) 和 Pinbar (趋势反转) 表现相反。**

### 2. 近期涨幅是 Pinbar 的毒药

**recent_72h_return** 是第二强特征:
- 近 3 天涨幅低 → Pinbar WR 18.8%, PnL +990
- 近 3 天涨幅高 → Pinbar WR 7.3%, PnL -11,555

**含义**: Pinbar 在"刚刚涨过一波"的环境中频繁失败。这可能是追顶/抄底失败。

### 3. 高波动杀死 Pinbar

**realized_volatility_24h** 和 **atr_percentile** 一致:
- 低波动 → Pinbar 表现最好（虽然仍然小亏）
- 高波动 → Pinbar 表现最差

**2023 vs 2024/2025 的关键差异**: ATR percentile 2023=0.625 vs 2024/25=0.531。2023 波动更高，这直接解释了为什么 2023 Pinbar 更差。

### 4. Donchian 距离揭示入场位置

**distance_to_donchian_20_high**:
- mid（价格在通道中间）→ Pinbar 赚钱 (+654)
- low（价格接近通道顶部）→ Pinbar 亏钱 (-11,682)

**含义**: Pinbar 在价格已经突破到通道顶部时最差 — 这正是 Donchian 突破策略入场的位置。两者在市场位置上互补。

### 5. 2023 vs 2024/2025 状态差异

| 特征 | 2023 均值 | 2024/25 均值 | 差异 | 解读 |
|------|----------|-------------|------|------|
| atr_percentile | 0.625 | 0.531 | +0.094 | 2023 波动更高 → Pinbar 更差 |
| ema_4h_slope | 0.115 | 0.139 | -0.024 | 2023 趋势更弱（但 Pinbar 在弱趋势更好） |
| recent_72h_return | 0.035 | 0.050 | -0.015 | 2023 近期涨幅更低（Pinbar 应更好） |

**悖论**: 2023 的 ema slope 和 72h return 对 Pinbar 更友好，但 ATR 更高。ATR 的负面效应可能压倒了其他正面因素。

---

## 盈利/亏损 Profile

| 指标 | Winners (58) | Losers (353) |
|------|-------------|-------------|
| WR | 100% | 0% |
| Total | 58 trades | 353 trades |

**特征对比**（盈利 vs 亏损交易的市场状态均值差异）:

盈利交易更可能出现在:
- 低 ema_4h_slope 环境
- 低 recent_72h_return 环境
- 低 realized_volatility 环境
- 价格在 Donchian 通道中间（而非顶部）

---

## M0 判定

**PASS** — M0 有价值，原因:

1. **6+ 特征有显著解释力**（spread > 5,000 USDT）
2. **2023 状态分布确实不同**（ATR percentile 高 9.4pp）
3. **特征模式一致且可解释**（Pinbar = 反趋势 = 低动量/低波动环境）
4. **为下一步策略选择提供了清晰方向**

---

## 下一步建议（按优先级）

### 1. Regime Filter（最高优先级）

**发现**: Pinbar 在高 ema_slope / 高 volatility 环境系统性亏损。

**建议**: 不是加新 entry，而是**给现有 Pinbar 加 regime filter**。
- 当 ema_4h_slope > 阈值 或 atr_percentile > 阈值 时，暂停 Pinbar 信号
- 这可能比任何新 entry 策略都更有效
- 需要验证：过滤后 2023 亏损是否显著减少

### 2. Exit Policy 优化

**发现**: Pinbar WR 仅 14.1%，大量小亏。

**建议**: 当前 TP2=3.5R 可能太远。如果 regime filter 无法实施，可考虑:
- 更紧的 TP2（如 2.0R）
- 但这需要新实验验证

### 3. 暂停新 Entry 策略（Donchian / Breakout）

**发现**: Donchian 在高动量环境赚钱（与 Pinbar 互补），但 Donchian 20 太短，噪音太大。

**建议**: 
- 不继续 Donchian 参数搜索
- 如果要探索趋势跟踪，需要更长窗口（50+）+ Volume filter，这需要改 src
- 当前 research-only 约束下，优先做 regime filter

### 4. Multi-Symbol 扩展（低优先级）

**发现**: 当前只测了 ETH。

**建议**: 先在 ETH 上验证 regime filter 有效，再扩展到 BTC/SOL/BNB。

### 5. Multi-Timeframe（低优先级）

**发现**: 4h slope 是最强特征之一。

**建议**: 已经在用 MTF 4h EMA60 filter。如果 regime filter 实施，可以进一步利用 4h 信息。

---

## 不建议的方向

| 方向 | 理由 |
|------|------|
| 继续换 entry（Engulfing / Doji / Hammer） | M0 证明问题在 regime，不在 entry |
| 参数搜索 | 约束禁止，且 M0 证明是环境问题 |
| 加更多特征 | 10 个特征已有 6+ 个有解释力，够用了 |
| 复杂多因子模型 | 单特征分桶已有清晰结论，不需要 |

---

## 未来函数检查

| 检查项 | 状态 |
|--------|------|
| 所有特征只用 signal_time 当时已知数据 | ✅ |
| 4h 特征只用 close_time <= signal_time 的 4h K | ✅ |
| EMA50 用当前已收盘 signal K（可接受） | ✅ |
| ATR percentile 用过去 500 bars（不含当前） | ✅ |
| Donchian 20 只用 history[-20:]（不含当前） | ✅ |
| 入场价用 next bar open + slippage（T+1） | ✅ |

---

## 技术说明

- 本报告使用独立 proxy 撮合引擎，不经过 Backtester v3_pms
- Pinbar 检测复刻 src PinbarStrategy.detect() 逻辑
- 仓位大小受 max_total_exposure=2.0x 截断
- 2021 年数据包含 warmup，不作为判定依据
- 所有价格使用 Decimal 精度计算
- 数据来源：v3_dev.db（ETH/USDT:USDT 1h + 4h）

---

## 产出文件

| 文件 | 说明 |
|------|------|
| `scripts/run_strategy_ecology_m0.py` | 独立撮合 + 特征计算 + 分桶分析 |
| `reports/research/strategy_ecology_m0_2026-04-28.json` | 完整结果 JSON |
| `docs/planning/2026-04-28-strategy-ecology-map-m0.md` | 本报告 |
