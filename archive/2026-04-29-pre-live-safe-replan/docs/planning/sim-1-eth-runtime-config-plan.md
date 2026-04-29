# Sim-1 ETH Runtime Config 规划

> **Created**: 2026-04-23
> **Status**: 架构规划完成，待执行前审查
> **Scope**: Sim-1 前配置真源收口、ETH runtime profile 冻结、回测/Optuna 隔离

---

## 1. 背景

Sim-0 受控验证已经跑通主程序启动、SignalPipeline、策略/过滤器、风控、ExecutionOrchestrator、Binance testnet ENTRY、TP/SL 保护单、PG ExecutionIntent、PG recovery tasks、启动对账和 breaker 重建。

但 Sim-0 使用的是受控 BTC 配置，目标是验证执行链路，不是策略基准。当前更大的风险是 config module 真源混乱：

1. `.env` 已被确定为运行入口，但主程序仍从 SQLite config tables 读取 exchange / notification / system / risk / strategies。
2. Sim-0 脚本为了跑通，会把 `.env` 同步进 SQLite 兼容配置库。
3. 当前 SQLite BTC 参数是受控验证假配置，不应进入模拟盘策略基准。
4. ETH 1h LONG-only 才是当前研究基准。
5. 回测、Optuna、runtime、execution TP/SL 的配置边界尚未统一。
6. 模拟盘期间不允许热改策略和风控，后期再考虑拓展热改能力。

---

## 2. 已确认决策

### 2.1 Sim-1 策略目标

Sim-1 使用 ETH，不沿用 Sim-0 BTC 受控配置。

| 项 | 决策 |
|---|---|
| 模拟盘标的 | `ETH/USDT:USDT` |
| 主周期 | `1h` |
| MTF 辅助周期 | `4h` |
| 策略方向 | LONG-only |
| 当前 BTC 配置 | 仅标记为 `sim0_controlled_btc`，不得作为策略基准 |
| ETH 基准来源 | `docs/planning/backtest-parameters.md` 为主真源 |

### 2.2 Sim-1 风控口径

| 参数 | Sim-1 决策 |
|---|---|
| `max_loss_percent` | `0.01` |
| `max_leverage` | `20` |
| `max_total_exposure` | `1.0` |
| `daily_max_trades` | 低频策略，先保持现有形态 |
| `daily_max_loss` | 10% 权益口径，启动时派生金额 |

### 2.3 配置运行规则

1. `.env` 管环境和秘密。
2. DB 管非 secret 的业务配置。
3. YAML 不参与启动。
4. PG 继续承担 execution state / recovery / breaker，不在 Sim-1 前做 PG config 大迁移。
5. 模拟盘期间禁止热改 strategy / risk / execution config。
6. Optuna 最优参数不一键应用到模拟盘，只输出 candidate profile / report。

### 2.4 Phase Registry（SSOT）

为避免文档间 Phase 字母冲突，本项目对 Sim-1 收口工作引入跨文档稳定 ID：`SIM1-R*`。

- 跨文档引用一律使用 `SIM1-R*`（例如“SIM1-R2 已完成”）。
- `Phase A/B/C...` 只作为本文件的阅读顺序标签，不作为跨文档引用编号。

| Stable ID | 事项 | 对应本文件 Phase |
|---|---|---|
| `SIM1-R0` | 契约与 Profile 收口 | Phase A |
| `SIM1-R1` | Runtime Resolver 骨架 | Phase B |
| `SIM1-R2` | Secret 真源收口（.env） | Phase B（子事项） |
| `SIM1-R3` | Execution TP/SL 真源收口 | Phase C |
| `SIM1-R4` | Strategy/Market runtime 适配 | Phase D |
| `SIM1-R5` | Risk runtime 适配 | Phase E |
| `SIM1-R6` | Backtest 隔离 | Phase F |
| `SIM1-R7` | Optuna 隔离（candidate only） | Phase G |
| `SIM1-R8` | Sim-1 启动前验收 | Phase H |

---

## 3. 五模块配置模型

Sim-1 先按 5 个模块整理配置，不直接按存储介质划分。

| 模块 | 职责 | Sim-1 变更规则 |
|---|---|---|
| `environment` | 端口、PG DSN、backend mode、exchange key/secret、webhook | 启动前固定，运行中不可变 |
| `market` | exchange name、testnet、symbols、timeframes、warmup、订阅范围 | 冻结 |
| `strategy` | trigger、filters、Pinbar、EMA、MTF、direction、ATR enable/disable | 冻结 |
| `risk` | 单笔风险、杠杆、敞口、每日限制、CapitalProtection 派生参数 | 冻结 |
| `execution` | TP/SL、OrderStrategy、OCO、BE、trailing、DCA、保护单规则 | 冻结 |

### 3.1 Environment

| 字段 | 来源 | Sim-1 规则 |
|---|---|---|
| `PG_DATABASE_URL` | `.env` | 必填 |
| `CORE_EXECUTION_INTENT_BACKEND` | `.env` | `postgres` |
| `CORE_ORDER_BACKEND` | `.env` | 当前阶段 `sqlite` |
| `EXCHANGE_NAME` | `.env` | `binance` |
| `EXCHANGE_TESTNET` | `.env` | `true` |
| `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET` | `.env` | 只读 secret，不写入业务 DB |
| `FEISHU_WEBHOOK_URL` | `.env` | 只读 secret，不写入业务 DB |
| `BACKEND_PORT` | `.env` | 启动端口 |

### 3.2 Market

| 字段 | Sim-1 值 |
|---|---|
| `primary_symbol` | `ETH/USDT:USDT` |
| `primary_timeframe` | `1h` |
| `subscribed_pairs` | `ETH/USDT:USDT:1h`, `ETH/USDT:USDT:4h` |
| `warmup_history_bars` | 先沿用现有值 |
| `asset_polling_interval` | 先沿用现有值 |

### 3.3 Strategy

| 字段 | Sim-1 值 |
|---|---|
| `direction` | `LONG-only` |
| `trigger.type` | `pinbar` |
| `pinbar.min_wick_ratio` | `0.6` |
| `pinbar.max_body_ratio` | `0.3` |
| `pinbar.body_position_tolerance` | `0.1` |
| `ema.enabled` | `true` |
| `ema.period` | `50` |
| `ema.min_distance_pct` | `0.005` |
| `mtf.enabled` | `true` |
| `mtf.source_timeframe` | `4h` |
| `mtf_ema_period` | `60` |
| `atr.enabled` | `false` |
| `atr.retained_for_compatibility` | `true` |

### 3.4 Risk

| 字段 | Sim-1 值 |
|---|---|
| `max_loss_percent` | `0.01` |
| `max_leverage` | `20` |
| `max_total_exposure` | `1.0` |
| `daily_max_trades` | 先保持现有形态 |
| `daily_max_loss_percent` | `0.10` |
| `daily_max_loss_amount` | 启动时由权益口径派生 |

### 3.5 Execution

| 字段 | Sim-1 值 |
|---|---|
| `tp_levels` | `2` |
| `tp_ratios` | `[0.5, 0.5]` |
| `tp_targets` | `[1.0, 3.5]` |
| `initial_stop_loss_rr` | `-1.0` |
| `breakeven_enabled` | `false` |
| `trailing_stop_enabled` | `false` |
| `oco_enabled` | `true` |

---

## 4. Profile 设计

Profile 是模块组合，不是一坨任意 JSON。

| Profile | 用途 | 状态 |
|---|---|---|
| `sim0_controlled_btc` | Sim-0 执行链路验证归档 | 只读归档，不作为策略基准 |
| `eth_baseline_research` | ETH 1h LONG-only 研究基准 | 主真源来自 `backtest-parameters.md` |
| `sim1_eth_runtime` | Sim-1 模拟盘冻结运行配置 | 从 ETH baseline 派生 |
| `backtest_eth_baseline` | 回测页面/脚本默认基准 | 可按 request 覆盖 |
| `optuna_eth_study_base` | Optuna base profile | 只输出 candidate，不写 runtime |
| `optuna_candidate_*` | 优化结果候选 | 人工审查后才可 promoted |

---

## 5. 加载规则

### 5.1 Runtime

```text
.env environment
+ sim1_eth_runtime profile modules
+ code safety defaults
=> ResolvedRuntimeConfig
=> EffectiveConfigSnapshot
=> SignalPipeline / ExecutionOrchestrator / OrderManager
```

Runtime 不允许在运行中读取 mutable config 来改变 strategy / risk / execution。

### 5.2 Backtest

```text
explicit request
+ selected backtest profile
+ eth_baseline_research
+ code defaults
=> ResolvedBacktestConfig
=> Backtester
```

Backtest 可以覆盖 market / strategy / risk / execution / engine，但不允许写 runtime profile。

### 5.3 Optuna

```text
trial params
+ fixed study params
+ optuna_eth_study_base
+ code defaults
=> ResolvedBacktestConfig per trial
=> candidate profile / report
```

Optuna 不写 runtime DB，不一键应用到模拟盘。

---

## 6. 当前代码差距

| 模块 | 当前状态 | 差距 |
|---|---|---|
| `environment` | `.env` 已有关键变量，但 exchange/webhook 仍被主程序从 SQLite 消费 | 需要主程序直接从 `.env` 读取 secret，DB 不存真实 secret |
| `market` | 当前 SQLite `system_configs` 是 BTC / `15m,1h` | 需要 Sim-1 ETH `1h + 4h` runtime profile |
| `strategy` | 当前 SQLite strategy 是 BTC 受控假配置，ATR enabled | 需要 ETH baseline：EMA50、MTF、ATR disabled、LONG-only |
| `risk` | 当前 SQLite risk 是 `max_loss_percent=0.02`, `max_total_exposure=0.8` | 需要 Sim-1 `0.01 / 20 / 1.0 / daily loss 10%` |
| `execution` | TP/SL 口径分散在 `RiskCalculator`、`SignalPipeline._build_execution_strategy()`、`OrderStrategy` | 需要 `ExecutionStrategyConfig -> OrderStrategy` 唯一执行真源 |
| `backtest` | request / runtime_overrides / KV / code defaults 混合 | 需要 `ResolvedBacktestConfig` |
| `optuna` | optimizer 默认仍含 ATR 和旧 TP 默认，依赖 fixed_params 才接近 baseline | 需要显式 base profile + search space + candidate only |
| `YAML` | 仍有 import/export 与历史脚本语义 | 启动链不得读取 YAML，仅保留兼容/归档 |

---

## 6.1 ConfigManager 退役路径（时间盒）

当前主程序存在“双轨”：

- `ConfigManager` 负责历史配置表、API 配置仓库、KV/backtest 兼容等
- `RuntimeConfigResolver` / `ResolvedRuntimeConfig` 负责 Sim-1 冻结 runtime（market/strategy/risk/execution）

双轨的目的只是过渡，不能永久存在。退役路径定义如下：

1. 退役时间盒（建议）：Sim-1 启动后 2 周内必须做一次决策
   - 要么推进 “runtime 消费面继续扩大，ConfigManager 仅保留 API/兼容层”
   - 要么明确继续双轨的原因与新的截止条件

2. 退役的最小退出条件（逐条切断 runtime 消费依赖）
   - Exchange/通知：已由 `.env` secret 真源收口（不再从 ConfigManager 读取 secret）
   - 执行语义：execution TP/SL 以 runtime `OrderStrategy` 为唯一执行真源
   - 市场范围：symbols/timeframes/warmup/polling 全部来自 runtime market
   - 风控/策略：SignalPipeline 不再依赖 ConfigManager 的可变配置来影响本进程决策

3. 仍然允许 ConfigManager 保留的责任（短中期）
   - v1 配置 API 的仓库依赖（Phase 9 的多个 config repos）
   - backtest KV 配置与历史导入/导出兼容（不影响 runtime 冻结语义）

4. 退役落地方式（建议）
   - 给所有“runtime 冻结配置消费点”加显式注释与日志 marker（便于审计）
   - 将 ConfigManager 的 runtime fallback 标注为 `legacy_fallback` 并在日志中警告

## 7. 任务清单

### Phase A（SIM1-R0）: 契约与 Profile 收口

1. 定义五模块字段契约。
2. 定义字段类型、默认值、Sim-1 值、来源、消费方、是否可热改。
3. 将当前 BTC 配置标记为 `sim0_controlled_btc`。
4. 将 ETH baseline 映射为 `eth_baseline_research`。
5. 从 `eth_baseline_research` 派生 `sim1_eth_runtime`。

### Phase B（SIM1-R1/SIM1-R2）: Runtime Resolver

1. 新增或整理 `ResolvedRuntimeConfig`。
2. 启动时从 `.env` 读取 environment secret。
3. 启动时从 runtime profile 读取 market / strategy / risk / execution。
4. 生成 `EffectiveConfigSnapshot`，包含 version/hash/source profile。
5. 禁止运行中热改 strategy / risk / execution。
6. 启动日志打印 effective config，敏感字段脱敏。

### Phase C（SIM1-R3）: Execution TP/SL 收口

1. 定义 `ExecutionStrategyConfig`。
2. 从 execution 模块生成 `OrderStrategy`。
3. `ExecutionOrchestrator` 只消费 `OrderStrategy` 快照。
4. `OrderManager` 只根据 `OrderStrategy` 生成保护单。
5. `RiskCalculator.take_profit_config` 不再作为实盘保护单真源。
6. 明确 signal preview TP 与 execution TP 的关系。

### Phase D（SIM1-R4）: Strategy / Market Runtime 适配

1. Runtime 主 symbol/timeframe 切到 ETH `1h`。
2. 为 MTF 订阅 ETH `4h`。
3. Strategy runner 创建 EMA50 + MTF filter。
4. ATR 保留字段但 `enabled=false`，不创建有效 ATR filter。
5. Direction scope 限定 LONG-only。

### Phase E（SIM1-R5）: Risk Runtime 适配

1. 设置 `max_loss_percent=0.01`。
2. 设置 `max_leverage=20`。
3. 设置 `max_total_exposure=1.0`。
4. 设置 `daily_max_loss_percent=0.10`。
5. 启动时将 10% 权益口径派生成现有 `daily_max_loss` 金额字段。
6. 保持 daily trade count 现有保守形态。

### Phase F（SIM1-R6）: Backtest 隔离

1. ✅ 新增 `ResolvedBacktestConfig`。
2. ✅ 新增独立 `backtest_eth_baseline` profile。
3. ✅ Request 覆盖只影响本次回测。
4. ✅ Backtest engine 参数只存在于回测配置，不进入 Sim/Live runtime。
5. ✅ 新增 `BACKTEST_INJECTABLE_PARAMS`，显式声明可注入参数边界。
6. ✅ 标记 `optimizer_safe` 参数，供 Optuna search space 后续读取。
7. ⏸️ 回测 API 暂缓，当前不做 Web。
8. ⏳ 研究脚本入口可按需接入 `BacktestConfigResolver`。
9. ⏳ 回测可以显式选择 `use_runtime_snapshot`，但默认不跟随 mutable runtime。

### Phase G（SIM1-R7）: Optuna 隔离

1. ✅ Optuna 默认使用 `backtest_eth_baseline` 作为 base profile。
2. ✅ `StrategyOptimizer` 接入 `BacktestConfigResolver`。
3. ✅ Search space 只允许覆盖 `optimizer_safe=True` 的声明字段。
4. ✅ Fixed params 必须命中 `BACKTEST_INJECTABLE_PARAMS` 声明字段。
5. ✅ Trial request / strategy / risk / execution 从 profile resolver 生成，不再在 Optuna 内硬编码 ETH baseline。
6. ✅ Optuna 不写 runtime DB，不自动应用模拟盘。
7. ✅ candidate report 落盘能力已完成。
8. ⏳ 后续只剩真实小规模搜索运行。

### Phase H（SIM1-R8）: Sim-1 启动前验收

1. `.env` testnet 检查通过。
2. API key 无提现权限。
3. PG execution intent/recovery 初始化通过。
4. `CORE_EXECUTION_INTENT_BACKEND=postgres`。
5. `CORE_ORDER_BACKEND=sqlite` 当前阶段明确标注。
6. Effective runtime profile 为 `sim1_eth_runtime`。
7. Symbol/timeframe 为 ETH `1h` + MTF `4h`。
8. ATR disabled。
9. Risk 为 `0.01 / 20 / 1.0 / daily loss 10%`。
10. Execution 为 TP `[1.0,3.5]`、ratio `[0.5,0.5]`、BE off。
11. 运行中热改 strategy/risk/execution 被禁止或仅下次启动生效。
12. 启动后生成 effective config snapshot/hash。

---

## 8. 非目标

Sim-1 前不做：

1. 不做 PG config SSOT 大迁移。
2. 不做策略/风控热改能力。
3. 不做 Optuna 一键应用模拟盘。
4. 不继续扩大参数搜索。
5. 不把 backtest engine 参数带入 runtime。
6. 不恢复 YAML 启动链。

---

## 9. 待确认事项

当前已知待确认项较少，主要是实现细节：

1. ✅ 已定：优先使用启动账户权益冻结金额；若启动瞬间无账户快照，则保留百分比口径回退。
2. ✅ 已定：Runtime profile 短中期继续 SQLite（不做 PG config SSOT 大迁移）。
3. ✅ 已定：Sim-1 期间 strategy/risk/execution 对当前进程冻结；允许写入“下次启动生效”的配置，但不得影响当前进程。
4. ✅ 已定：Signal preview TP 保留展示/研究语义；execution TP/SL（OrderStrategy）是唯一执行真源。

---

## 10. 推荐执行顺序

1. 先完成 Phase A：模块契约和 `sim1_eth_runtime` profile。
2. 再完成 Phase B / C：runtime resolver 与 execution TP/SL 收口。
3. 再完成 Phase D / E：ETH market/strategy/risk runtime 适配。
4. 再完成 Phase H：Sim-1 启动前验收。
5. 最后处理 Phase F / G：Backtest 和 Optuna 规范化，避免研究链反向污染 runtime。
