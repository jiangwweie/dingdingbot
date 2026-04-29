# ADR: 回测研究真源审计

> 2026-04-21 补充：本文最初用于审计“真源分叉风险”。截至 2026-04-21 晚间，已完成关键修复：
> - 回测/实盘 `mtf_ema_period` 与 `mtf_mapping` 真源统一（system config overlay）
> - 回测 `MTF` 趋势定义修正为 higher TF `close vs EMA(mtf_ema_period)`，并加入 warmup
> - `equity_curve` 升级为 true equity（含未实现盈亏），`max_drawdown` 峰谷调试输出修复
> 其余“研究结论升级门槛/参数语义口径”仍按本文建议继续执行。

## 背景

`2026-04-20` 的回测研究把 “ETH 在真实滑点 / BNB9 下盈利” 上升为 “策略 alpha 已确认”，并据此推进了：

- ETH 主线优先
- Optuna 搜索方向
- 参数锁定与先验缩窄
- 测试盘预期

`2026-04-21` 复盘后确认，问题不只是单个回测结果，而是研究语义、代码实现、实盘语义、planning 口径之间缺少单一真源（SSOT）。

本审计不做实现改动，只确认哪些概念已经收敛，哪些概念仍存在“名字像一回事、代码却是另一回事”的风险。

## 决策

采取 **方案 B：完整审计**，先完成四类研究真源核对，再恢复搜索：

1. MTF 真源收口
2. EMA / ATR 参数语义核对
3. TP / SL / BE 语义一致性核对
4. 研究结论升级门槛收口

结论：

- 当前 **可以继续保留工程链路**
  - `runtime overrides > request > KV > default`
  - `BacktestRuntimeOverrides / ResolvedBacktestParams`
  - Optuna runtime overrides 注入能力
  - 时间顺序修正、funding 净值闭环
- 当前 **不能继续保留研究结论**
  - ETH alpha 已确认
  - ETH 主线优先
  - 昨天的参数锁定可直接作为搜索先验
  - 跨币强弱排序

## 架构设计

### 1. MTF 真源矩阵

| 维度 | 回测实现 | 实盘实现 | 当前状态 |
|------|------|------|------|
| higher timeframe 趋势定义 | `close vs EMA` | `close vs EMA` | 表面一致 |
| `mtf_ema_period` 来源 | **硬编码 60** | `user_config.mtf_ema_period` | **不一致，P0** |
| `mtf_mapping` 来源 | `Backtester.MTF_MAPPING` 类常量 | `user_config.mtf_mapping` | **不一致，P0** |
| closed-candle rule | `_get_closest_higher_tf_trends()` 按 `timestamp + period <= current_timestamp` | `get_last_closed_kline_index()` | 基本一致 |
| planning / findings 口径 | 仍引用旧语义 | N/A | **失真，P0** |

### 2. EMA / ATR 参数真源矩阵

| 参数 | 研究里常见说法 | 代码真实语义 | 当前状态 |
|------|------|------|------|
| `min_distance_pct` | 趋势强度 / EMA 过滤优化参数 | **价格与 EMA 的最小距离阈值，用于横盘过滤** | 需要纠正文案，P0 |
| `max_atr_ratio` | ATR 过滤优化参数 | **ATR / close 上限，过滤高波动环境** | 语义比研究表述更窄，P0 |
| `min_atr_ratio` | ATR 过滤基础阈值 | **candle_range / ATR 下限** | 已实现，但不是本轮搜索主参数 |

### 3. TP / SL / BE 语义矩阵

| 维度 | 回测实现 | 实盘实现 | 当前状态 |
|------|------|------|------|
| ENTRY 锚点 | `kline.open ± slippage` 成交 | 交易所真实成交 | 允许存在环境差异 |
| TP 价格生成 | `actual_entry + RR × stop_distance` | `handle_order_filled()` 动态挂单 | 基本一致 |
| SL 价格生成 | `initial_stop_loss_rr` / 默认 `-1.0` | 同 `OrderManager` | 基本一致 |
| BE 触发条件 | `TP1 FILLED` 后将 `SL -> entry` 并切换 `TRAILING_STOP` | 同 `RiskManager` 逻辑 | 基本一致 |
| 撮合顺序 | `SL` 优先于 `TP`，同一根 K 线内极端保守 | 实盘由交易所真实成交顺序决定 | **有意差异，需标注为 stress 口径** |

### 4. 研究结论升级门槛

后续任何“alpha / 主线 / 优先上线 / 搜索先验”结论，必须至少满足：

1. 相关概念在回测 / 实盘 / 配置 / planning 中只有一个真源
2. 最小验证矩阵通过
3. 结论先写成“候选假设”，不得直接写成主线
4. 只有跨窗口复验通过后，才允许进入 `task_plan.md`

## 接口契约

本次为研究真源审计，不新增 API，不涉及 OpenAPI 变更。

## 关联影响

| 受影响模块 | 影响类型 | 风险等级 | 处理方案 |
|-----------|---------|---------|---------|
| `src/application/backtester.py` | MTF 参数来源与 planning 口径不一致 | P0 | 后续统一 `mtf_ema_period` 与 `mtf_mapping` 真源 |
| `src/application/signal_pipeline.py` | 作为实盘 MTF 参考真源 | P0 | 作为收敛目标比对回测路径 |
| `src/domain/filter_factory.py` | `min_distance_pct` / `max_atr_ratio` 语义需重新标注 | P0 | 统一参数说明与 research 文案 |
| `src/domain/risk_manager.py` | BE / trailing 逻辑属于执行语义真源 | P1 | 保留为执行层基准 |
| `src/domain/order_manager.py` | TP / SL 生成逻辑影响回测与实盘一致性 | P1 | 继续作为订单编排真源 |
| `src/domain/matching_engine.py` | Stress 口径与真实成交存在预期差 | P1 | 在 planning 中显式标为 stress |
| `docs/planning/*` | 研究结论升级过快 | P0 | 改为 gate 驱动，先候选后升级 |

## 技术债

1. `MTF` 仍无统一 provider；回测和实盘各自维护 higher timeframe trend 计算
2. `Backtester` 仍使用类常量 `MTF_MAPPING` 和硬编码 `EMA60`
3. 参数名与研究文案之间存在“概念外延扩大”的问题
4. planning 文档中历史结论很多，后续需要持续归档，避免旧口径反复污染当前决策

## 我的建议

恢复搜索前，先完成以下 gate：

1. 统一 `MTF` 的 `ema_period / mapping / closed-candle rule`
2. 把 `min_distance_pct` 和 `max_atr_ratio` 的真实语义写入 planning
3. 明确回测撮合属于 `stress`，不能直接当 `expected`
4. 只在最小验证通过后，才允许恢复 ETH 主线和 Optuna 搜索
