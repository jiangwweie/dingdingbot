# H6a Donchian 20-bar Breakout LONG-only Proxy — 研究报告

**日期**: 2026-04-28  
**假设**: H6a — Donchian 20-bar 收盘突破 LONG-only 在 ETH/USDT:USDT 1h 上有基础 alpha 痕迹  
**类型**: Proxy result（独立撮合，不等同正式 Backtester v3_pms result）  
**判定**: **CLOSE** — 3yr PnL 明显为负，不进入参数搜索

---

## 策略定义

| 参数 | 值 |
|------|-----|
| Symbol | ETH/USDT:USDT |
| Timeframe | 1h |
| Lookback | 20 bars |
| 入场 | close > max(high[-20:]) |
| 入场价 | 下一根 K open + 0.01% slippage |
| 止损 | min(low[-20:]) |
| 方向 | LONG-only |
| TP | TP1=1.0R (50%), TP2=3.5R (50%) |
| BE | TP1 后止损移到 entry |
| 成本 | fee=0.0405%, entry_slippage=0.01% |
| 风控 | max_loss=1%, max_exposure=2.0x |
| Filter | EMA50 (min_distance=0.5%) + MTF 4h EMA60 bullish |

## 未来函数检查

| 检查项 | 状态 |
|--------|------|
| Donchian high/low 只用 history[-20:]，不含 signal K | ✅ |
| MTF 4h 只用 close_time <= signal_time 的 4h K | ✅ |
| EMA50 用当前已收盘 signal K（可接受） | ✅ |
| 入场价用 next bar open + slippage（T+1） | ✅ |
| TP/SL 在后续 bar 上检查（非同 bar） | ⚠️ 同 bar 内 TP1+SL 可能同时触发 |

---

## 年度结果

| 年份 | PnL | Trades | WR | MaxDD | TP1 | TP2 | SL | Signals | Avg Hold (h) |
|------|-----|--------|-----|-------|-----|-----|-----|---------|-------------|
| 2022 | -7,891 | 606 | 36.3% | 82.0% | 19 | 3 | 28 | 1,156 | 6.4 |
| 2023 | -3,435 | 436 | 38.3% | 64.3% | 14 | 4 | 17 | 777 | 15.8 |
| 2024 | +504 | 225 | 37.3% | 65.4% | 17 | 6 | 25 | 504 | 22.6 |
| 2025 | -6,483 | 31 | 19.4% | 74.0% | 11 | 6 | 25 | 155 | 156.0 |

### 3yr 合计 (2023-2025)

| 指标 | Donchian 20 | Pinbar Baseline |
|------|------------|-----------------|
| PnL | **-17,305** | +9,067 |
| Trades | 1,292 | 200 |
| WR | 36.7% | 27.5% |
| MaxDD | 74.0% | 58.1% |

### 对比分析

- Donchian WR (36.7%) 高于 Pinbar (27.5%)，但 PnL 远差
- Donchian 信号频率极高（年均 648 signals），导致过度交易
- 年均交易 424 笔 vs Pinbar 67 笔 — 6.3x turnover
- 费用侵蚀严重：2022 年费用 $1,795 占初始资金 18%
- 2025 年仅 31 笔交易但亏损 $6,483 — 单笔平均亏损 $209

---

## 判定

**CLOSE: Donchian 20-bar LONG-only — 关闭，不进入参数搜索**

| 判定条件 | 结果 |
|----------|------|
| 3yr PnL > 0 | ❌ PnL = -17,305 |
| 至少 2 年非负 | ❌ 仅 2024 非负 |
| trades < 10 | ❌ trades = 1,292 |
| MaxDD > 50% | ⚠️ MaxDD = 74.0% |

---

## 根因分析

### 为什么 Donchian 20 在 ETH 1h 上失败？

1. **信号过频 + 紧止损 = 死亡组合**
   - 20-bar 1h = 20h 窗口，ETH 波动大，频繁突破 20h high
   - 但突破后经常回撤到 20-bar low（止损），被止损出局
   - 典型 "whipsaw" 模式：突破→止损→突破→止损

2. **2025 极端案例**
   - 155 signals → 31 trades → 25 SL → 仅 6 wins
   - WR 19.4%，单笔平均亏损 $209
   - 可能处于长期震荡市，20-bar Donchian 不断触发假突破

3. **与 Pinbar 的本质差异**
   - Pinbar "逆小顺大" — 在趋势回调时入场，止损在回调极值
   - Donchian "顺大顺小" — 在突破时入场，止损在通道底部
   - ETH 1h 的 20-bar 通道太窄，无法过滤噪音

4. **2024 唯一正收益年**
   - 225 trades，WR 37.3%，PnL +504
   - 但 MaxDD 65.4%，风险调整后仍然很差
   - 可能因为 2024 有几段强趋势让 Donchian 捕捉到

---

## 与 H6 审计假设的对照

| 审计假设 | 实际结果 |
|----------|----------|
| Breakout 能补 Pinbar 漏掉的趋势启动段 | ❌ 信号太多，假突破主导 |
| Donchian 在高 follow-through 环境更优 | ❌ ETH 1h 20-bar 无足够 follow-through |
| 多空 breakout 比 Engulfing SHORT 更合理 | ⚠️ 未测试 SHORT，但 LONG 已关闭 |
| 2023 失败可能由反转形态不适配造成 | ❌ Donchian 2023 同样失败 (-3,435) |

---

## 下一步建议

1. **不进入 H6b OOS / SHORT shadow** — 主假设已关闭
2. **不进入参数搜索** — 约束明确禁止
3. **可选观察**：若仍对 breakout 家族有兴趣，可考虑：
   - Donchian 50+（更长窗口，更少信号，更高 follow-through）
   - 加入 Volume surge filter（需实现 placeholder）
   - 但这需要改 src，超出 research-only 约束

---

## 技术说明

- 本报告使用独立 proxy 撮合引擎，不经过 Backtester v3_pms
- 仓位大小受 max_total_exposure=2.0x 截断（非拒绝），与正式 backtester 行为一致
- TP1/TP2 partial exit 逻辑：TP1 后止损移到 entry，剩余仓位继续持有
- 所有价格使用 Decimal 精度计算
- 数据来源：v3_dev.db（ETH/USDT:USDT 1h + 4h）
