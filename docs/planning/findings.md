# Findings Log

> Last updated: 2026-04-20 18:00

---

## 2026-04-20 -- 回测参数配置全景审计

### 结论

当前回测器有 **三级配置优先级**：BacktestRequest (最高) → KV Store (config_entries_v2) → 代码硬编码 (最低)。

### 已支持 KV 配置（16 个参数）

全部存储在 `config_entries_v2` 表，`backtest.*` 前缀，定义于 `config_entry_repository.py:455-475`。

| 参数 | 默认值 | Request 可覆盖 | 读取位置 |
|------|--------|:---:|----------|
| `slippage_rate` | 0.1% | ✅ | backtester.py:1224 (3-way merge) |
| `fee_rate` | 0.04% | ✅ | backtester.py:1225 |
| `initial_balance` | 10000 | ✅ | backtester.py:1226 |
| `tp_slippage_rate` | 0.05% | ✅ | backtester.py:1227 |
| `funding_rate_enabled` | True | ✅ | backtester.py:1228 |
| `funding_rate` | 0.01%/8h | ❌ | backtester.py:1232 |
| `tp_trailing_enabled` | False | ❌ | backtester.py:1343 |
| `tp_trailing_percent` | 1% | ❌ | backtester.py:1347 |
| `tp_step_threshold` | 0.3% | ❌ | backtester.py:1348 |
| `tp_trailing_enabled_levels` | ["TP1"] | ❌ | backtester.py:1349 |
| `tp_trailing_activation_rr` | 0.5 | ❌ | backtester.py:1350 |
| `trailing_exit_enabled` | False | ❌ | backtester.py:1367 |
| `trailing_exit_percent` | 1.5% | ❌ | backtester.py:1371 |
| `trailing_exit_activation_rr` | 0.3 | ❌ | backtester.py:1375 |
| `trailing_exit_slippage_rate` | 0.1% | ❌ | backtester.py:1379 |
| `breakeven_enabled` | True | ❌ | backtester.py:1388 |

### 硬编码参数（待后续提升为可配置）

**高优先级**（影响策略收益，Optuna 优化必须改动）：

| 参数 | 硬编码值 | 位置 | 影响 |
|------|---------|------|------|
| EMA 周期 | `60` | `_build_strategy_config()` L503 | 趋势判断灵敏度 |
| EMA 距离阈值 | `0.5%` | `IsolatedStrategyRunner` L95 | 信号过滤强度 |
| Pinbar 默认参数 | `0.6/0.3/0.1` | L487-489 fallback | 形态检测灵敏度 |
| Trailing SL 参数 | `2% / 0.5%` | `DynamicRiskManager` L1394-1395 | 止损追踪行为 |
| 默认双 TP | `1.0R×60%, 2.5R×40%` | L1477-1486 fallback | 止盈结构 |
| MTF 映射 | `15m→1h→4h→1d→1w` | class constant L216-221 | 多周期对齐 |

**中优先级**：

| 参数 | 硬编码值 | 位置 | 影响 |
|------|---------|------|------|
| 风控默认值 | `max_loss=1%, leverage=20` | L171-172 | 仓位计算（leverage 与 DB 默认 10 不一致） |
| v2 默认余额 | `10000` | L311 | v2 模式起始资金 |
| 简单回测 TP | `2R` | L905-908 `_simulate_win_rate` | v2 简单回测固定 RR |

### 已知 Bug（已修复）

- ~~`validate_breakeven_off.py`~~: `run_single(be_enabled)` 的 `be_enabled` 参数是 dead code，未写入 KV，ON/OFF 对比两端都是 ON。**已删除此脚本**。实际 +5607 USDT 结论来自 `run_breakeven_yearly.py`（L30 正确写入 `breakeven_enabled` 到 KV），结论有效。

### 配置管道架构

```
[BacktestRequest] ----+
                      |
[config_entries_v2] --+--> [_run_v3_pms_backtest()]
  (KV store)          |       |
                      |       +-- slippage/fee/balance (3-way merge: request > KV > code)
                      |       +-- TTP / Trailing Exit / BE (KV only, 无 request 覆盖)
                      |       +-- DynamicRiskManager(config)
                      |       +-- MockMatchingEngine(slippage, fee, tp_slippage)
                      |
[Code Defaults] ------+
  (backtester.py) — EMA period, distance, pinbar params, default TP, trailing SL
```

### 行动

- **当前阶段**：不改配置管道，先跑通盈利模式
- **后续 Optuna 阶段**：必须将 6 个高优先级硬编码参数提升为 KV 可配置，否则无法搜索最优参数组合

---

## 2026-04-20 -- Breakeven Stop 回测验证：关闭 BE 净改善 +5607 USDT

### 实验设计

- **对比方案**: BE=ON（TP1 成交后将 SL 移至入场价） vs BE=OFF（SL 保持原始位置）
- **锁定变量**: 双 TP (1.0R/2.5R, 60%/40%), Pinbar + EMA + MTF, Trailing Exit 关闭, TTP 关闭
- **数据范围**: 3 币种 × 2 年 (2023-2024), 1h 周期
- **代码改动**: `RiskManagerConfig.breakeven_enabled` 字段 + `risk_manager.py` guard

### 回测数据

#### 按币种×年份

| 币种 | 年份 | BE=ON PnL | BE=OFF PnL | 差异 | BE数 | ΔSL | ΔTP2 |
|------|------|-----------|------------|------|------|-----|------|
| BTC | 2023 | -78.51 | +372.12 | **+451** | 15 | +12 | +3 |
| BTC | 2024 | -6880.74 | -7022.73 | **-142** | 21 | +15 | +6 |
| ETH | 2023 | -4665.16 | -4888.64 | **-223** | 9 | +7 | +2 |
| ETH | 2024 | -102.58 | +1242.71 | **+1345** | 17 | +10 | +5 |
| SOL | 2023 | -2087.85 | -2039.56 | **+48** | 9 | +7 | +3 |
| SOL | 2024 | -1908.40 | -1779.68 | **+129** | 14 | +9 | +5 |

#### 合计

| 币种 | BE=ON PnL | BE=OFF PnL | 差异 | BE数 | 变TP2 | 被击穿 | 转化率 |
|------|-----------|------------|------|------|-------|--------|--------|
| BTC | -6959 | -6651 | **+309** | 36 | 9 | 27 | 25% |
| ETH | -4768 | +354 | **+1122** | 26 | 7 | 17 | 27% |
| SOL | -3996 | -3819 | **+177** | 23 | 8 | 16 | 35% |
| **合计** | **-15723** | **-10116** | **+5607** | 85 | 24 | 60 | 28% |

### 结论

- 关闭 BE 在所有 3 个币种上都有效，合计 **+5607 USDT**（策略 PnL 改善 36%）
- 85 笔 BE 触发中：24 笔变 TP2 命中，60 笔被 SL 击穿（28% 转化率）
- ETH 2024 效果最显著（-103 → +1243，转正）
- 代码改动：1 行配置（`trailing_stop_enabled: False`）

### 行动

- `OrderStrategy.trailing_stop_enabled` 默认改为 `False`
- `backtester.py` 默认策略改为 `trailing_stop_enabled=False`
- 后续：信号质量优化（BTC/SOL 仍为负，需提高胜率）

---

## 2026-04-19 -- 最终诊断：Pinbar 策略在当前市场不可行

### 核心结论

**Pinbar 策略在所有时间周期（1h/4h/1d）都严重亏损，概念本身在当前加密市场不可行。**

---

### 完整回测证据

| 周期 | MTF | 交易数 | 胜率 | 总 PnL | 单笔 PnL | Sharpe |
|------|-----|--------|------|--------|----------|--------|
| 1h | 4h | 974 | 55.7% | -18099 | -18.58 | - |
| 4h | 1d | 276 | 44.1% | -8628 | -31.26 | -1.76 |
| 1d | 无 | 66 | 29.2% | -1517 | -22.98 | -1.52 |
| 1d | 1w | 37 | **9.0%** | -1281 | -34.62 | -1.65 |

**结论**：周期越长，胜率越低，亏损越严重。

---

### 90 天盈利的真相

之前 90 天回测结果（+592.64 PnL, 70.3% 胜率）是**幸存者偏差**：

- 90 天正好是 2026 年 1-4 月，唯一盈利的时段
- 3 年完整周期中，27/40 个月亏损（67.5%）
- 2023-2025 年累计亏损 -15712.31

---

### 月度分析发现

| 年份 | BTC | ETH | SOL | 合计 |
|------|------|------|------|------|
| 2023 | +545.16 | -4257.76 | -1801.19 | **-5513.79** |
| 2024 | -6336.16 | +433.03 | -1129.17 | **-7032.29** |
| 2025 | -790.79 | -1107.62 | -1267.82 | **-3166.22** |
| 2026 (1-4月) | +571.34 | +114.61 | +257.86 | **+943.81** |

**盈利月份**：2023-08, 2023-09, 2023-10, 2024-08, 2025-09, 2026-01（共 6 个月）

**亏损月份**：34 个月（85%）

---

### 为什么 Pinbar 失效？

#### 1. 市场结构变化

- **2023-2025 加密市场特征**：高波动震荡 + 频繁清算瀑布
- Pinbar 长影线在传统市场代表"反转信号"
- 在加密市场，长影线往往是**清算瀑布**，不是真实反转

#### 2. EMA 过滤器问题

- EMA period=60 在 1h 周期 = 60 小时 ≈ 2.5 天
- EMA period=60 在 1d 周期 = 60 天 ≈ 2 个月
- **时间维度变化，EMA 含义完全不同**，但参数没调整

#### 3. MTF 过滤器问题

- 1h → 4h MTF：4h 趋势变化快，噪音多
- 1d → 1w MTF：1w 趋势太慢，信号被过度过滤
- MTF 在不同周期的效果不一致

#### 4. 双 TP 配置问题

- TP1=1.0R, TP2=2.5R 需要 **60% 胜率** 才能盈亏平衡
- 实际胜率 44-55%，低于盈亏平衡线
- 在低胜率环境下，双 TP 加速亏损

---

### Opus 深度分析

#### 假设验证结果

| 假设 | 验证方式 | 结果 |
|------|---------|------|
| 90 天盈利是策略有效 | 跑 3 年回测 | ❌ 假，是幸存者偏差 |
| 问题在时间维度（1h 噪音大）| 跑 4h 回测 | ❌ 假，4h 更差 |
| 问题在时间维度（4h 仍不够）| 跑 1d 回测 | ❌ 假，1d 最差 |
| Pinbar 概念本身不可行 | 所有周期都亏损 | ✅ 真 |

#### 根本原因

**Pinbar 的理论假设在当前加密市场不成立**：

1. **假设**：长影线 = 市场拒绝该价格 = 反转信号
2. **现实**：长影线 = 清算瀑布 = 继续原方向

加密市场的高杠杆特性导致：
- 价格触及某个价位 → 触发大量清算 → 价格被推得更远 → 形成长影线
- 这不是"市场拒绝"，而是"清算连锁反应"
- Pinbar 检测到的"反转信号"，实际上是清算后的**惯性延续**

---

### 下一步方向

#### 优先级 P0：优化 Pinbar 信号质量（根本问题）

**根本原因**：当前 Pinbar 检测是纯形态过滤，任何地方的长影线都会触发，没有考虑"在哪里形成"。

**三个独立维度的质量过滤**：

| 过滤器 | 维度 | 建议参数 | 解决的问题 |
|--------|------|---------|-----------|
| EMA 触碰 | 位置质量（有无依托）| wick 进入 EMA ± 1% 范围 | 确保在支撑/阻力位形成 |
| ADX 趋势强度 | 市场状态（趋势 vs 震荡）| ADX > 20 | 过滤震荡市磨损 |
| ATR 修复 | 形态质量（幅度够不够）| candle_range ≥ 0.5 × ATR | 过滤微小波动 |

**注意**：ATR 和 EMA 触碰不重叠，解决不同问题。EMA 距离过滤器（当前已有）也不能替代 EMA 触碰。

**优先级**：ADX 最容易实现，且最直接解决"震荡市磨损"。

---

#### 优先级 P1：止盈策略改进（在信号质量确认后）

**根本原因**：Pinbar 的核心价值是识别趋势起点，但固定 TP2=2.5R 把大行情封死了。

**当前问题**：
- TP1(1.0R) → TP2(2.5R) → 全部出场
- 真实行情可能：继续走到 10R、20R → 策略早已离场

**改进方向**：去掉固定 TP2，改为 Trailing Stop

```
TP1=1.0R → 平 50% 仓位，SL 移至 Breakeven
剩余 50% → 只用 Trailing Stop，不设固定目标
  小行情：Trailing Stop 收割，保住 TP1 收益
  大行情：Trailing Stop 跟随，捕获 5R、10R+
```

---

#### 止盈变体测试结论（今日已验证）

**所有 TP 变体均已测试，全部在 3 年维度失败**：

| TP 方案 | 90天 | 3年 |
|---------|------|-----|
| 单 TP 1.0R / 1.2R / 1.5R | 全部负 | - |
| 双 TP [1.0R, 2.5R] | +661 ✅ | -18099 ❌ |
| Trailing Stop | 负 | - |

**结论**：止盈不是根本问题。底层信号没有 edge，改 TP 是在磨损中调姿势。

---

#### 明天执行顺序（修正版）

**Step 1：先测信号质量组合过滤（根本问题）**

```
EMA 触碰 + ADX > 20 + ATR 修复
目标：胜率从 55.7% 提升到 60%+
跑 3 年 1h 回测
```

**Step 2：信号质量确认有效后，再测止盈变体**

```
在高质量信号上测 Trailing Stop vs 双 TP
高质量信号才值得讨论用什么 TP 最大化收益
```

**⚠️ 警告**：不要在信号 edge 未确认前调 TP，样本可能骗人（90天 +661 → 3年 -18099 的教训）

---

### EMA 追踪止盈方案（Opus 讨论）

#### 背景

当前 trailing stop 是基于固定百分比回撤，但 Pinbar 策略的核心逻辑是 EMA 趋势：

- **入场条件**：价格在 EMA 上方，Pinbar 在 EMA 支撑处形成
- **出场条件**：价格收盘跌破 EMA → 趋势结束，离场

**用同一根 EMA 做入场和出场判断，不引入新参数，逻辑一致性最强。**

#### 三种移动止盈对比

| 类型 | 逻辑 | 适合场景 |
|------|------|---------|
| 固定 % 移动 | 价格回撤 X% 就出 | 太简单，震荡市容易被扫 |
| ATR 移动 | 价格回撤 N × ATR 就出 | ✅ 自适应波动率，更鲁棒 |
| **EMA 追踪** | 价格收盘跌破 EMA 就出 | ✅ **最契合 Pinbar 策略逻辑** |

#### 技术实现方案

**当前架构限制**：
- trailing stop 是静态的：SL 下单时是固定价格
- EMA trailing 要求动态的：每根 K 线收盘后，SL 价格 = 当前 EMA 值

**需要改动的三个地方**：

1. **回测器主循环（backtester.py）**

```python
for kline in klines:
    runner.update_state(kline)   # EMA 更新
    
    # 新增：EMA trailing 的仓位，更新 SL 价格
    ema_value = runner.get_ema(kline.symbol, kline.timeframe)
    for order in active_sl_orders:
        if order.trailing_type == "EMA":
            order.price = ema_value  # SL 跟着 EMA 移动
    
    # 撮合（用更新后的 SL 价格）
    matching_engine.process(kline, active_orders)
```

2. **OrderStrategy 加新字段**

```python
trailing_type: Literal["PERCENT", "EMA"] = "PERCENT"
```

3. **实盘执行**

每根 K 线收盘 → 计算新 EMA → 调用交易所 API 修改 SL 订单价格。
频率：1h K 线每小时一次。

#### 难度评估

| 层面 | 难度 | 原因 |
|------|------|------|
| 回测器 | ⭐⭐ 中等 | 需要把 EMA 值从 runner 透传到主循环的订单更新步骤 |
| 领域模型 | ⭐ 简单 | 加一个字段 |
| 实盘执行 | ⭐⭐⭐ 稍难 | 需要 amend order API，不是所有交易所都支持 |

**结论**：架构上完全支持，不需要大重构。主要工作量在回测器主循环和 EMA 值的透传。

---

#### 下一步

- **优先级 P0**：优化 Pinbar 信号质量（EMA 追踪止盈）
- **优先级 P1**：如果 P0 后仍亏损，考虑换策略方向

---

#### 选项 A：放弃 Pinbar，换策略

**推荐方向**：
1. **趋势跟踪策略**（均线交叉、突破）
2. **均值回归策略**（布林带、RSI 超卖）
3. **波动率策略**（ATR 突破、波动率收缩）

**理由**：
- 不再试图"预测反转"
- 顺应市场特性（趋势延续 > 反转）

#### 选项 B：修改 Pinbar 检测逻辑

**可能的改进**：
1. 加入**清算数据**过滤（排除清算瀑布）
2. 加入**成交量分析**（真实反转 vs 清算）
3. 加入**波动率背景**（高波动 vs 低波动环境）

**风险**：
- 需要额外数据源（清算数据）
- 参数更多，过拟合风险更高

#### 选项 C：多策略组合

**思路**：
- Pinbar 作为信号之一（权重降低）
- 结合趋势跟踪、均值回归
- 通过权重分配降低单一策略风险

---

### 技术踩坑记录

#### 坑 1：ATR 过滤器无效

- 阈值 `min_atr_ratio=0.001` 差 1000 倍
- 实际 ATR ≈ 660 USDT，过滤阈值 = 0.66 USDT
- 无任何信号被过滤

#### 坑 2：MTF 过滤器路径差异

- `MtfFilter`（旧版）`check()` 直接返回 `passed=True`
- `MtfFilterDynamic`（新版）正常检查
- IsolatedStrategyRunner 和 DynamicStrategyRunner 结果差异巨大

#### 坑 3：BNB 数据缺口

- BNB 4h 数据仅 186 根（31 天）
- MTF 因数据缺失返回 `passed=False`
- 导致 BNB 信号被错误过滤

#### 坑 4：limit 最大 1000 限制

- 3 年数据约 28000 根 K 线
- 需要修改 `BacktestRequest.limit` 上限
- 临时改为 `le=30000`

#### 坑 5：1w 数据下载不完整

- Binance Vision 没有 2024-05 ~ 2026-03 的完整 1w 数据
- 部分月份 404
- 最终导入 256 条 1w 数据（足够 EMA 预热）

---

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/domain/models.py` | `limit` 上限改为 30000 |
| `scripts/phase0_3year_backtest.py` | 3 年回测脚本 |
| `scripts/phase0_monthly_analysis.py` | 月度分析脚本 |
| `scripts/import_1w_data.py` | 1w 数据导入脚本 |

---

### 数据变更

| 数据 | 变更 |
|------|------|
| 1w K 线 | 新增 256 条（BTC/ETH/SOL, 2021-11 ~ 2024-01）|

---

## 2026-04-19 -- ATR 过滤器影响验证

### 实验结果

| 实验 | 交易数 | 胜率 | 总PnL | 单笔PnL |
|------|--------|------|--------|----------|
| 不含 ATR | 52 | 65.2% | -143.68 | -2.76 |
| 含 ATR | 52 | 65.2% | -143.68 | -2.76 |

**ATR 过滤信号数：0**（阈值 0.001 太小，无效）

### 详细报告

`docs/diagnostic-reports/DA-20260419-004-atr-filter-impact.json`

---

## 2026-04-19 -- EMA 距离过滤验证（DynamicStrategyRunner 路径）

### 实验结果

| 实验 | min_distance | 交易数 | 胜率 | 总PnL | 单笔PnL |
|------|-------------|--------|------|--------|----------|
| 无距离过滤 | 0.0 | 68 | 60.5% | -323.71 | -4.76 |
| 有距离过滤 (0.5%) | 0.005 | 52 | 65.2% | -143.68 | -2.76 |

**效果**：过滤 23.5% 信号，PnL 改善 +180 USDT

### 详细报告

`docs/diagnostic-reports/DA-20260419-003-ema-distance-validation.json`

---

*Last updated: 2026-04-19 22:15*
