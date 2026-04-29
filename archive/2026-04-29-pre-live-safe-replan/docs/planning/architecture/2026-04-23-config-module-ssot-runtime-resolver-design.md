# Config Module SSOT 与 Runtime Resolver 架构设计

> **Created**: 2026-04-23  
> **Status**: 架构设计初稿，已确认 Config 短中期继续保留 SQLite  
> **Scope**: Sim-1 ETH runtime config 收口、配置真源矩阵、五模块契约、Resolver 抽象  
> **Non-goals**: 不做 PG config 大迁移、不扩前端、不扩回测、不引入热改能力

---

## 1. 背景与目标

Sim-0 已阶段性跑通真实 testnet 链路，但使用的是 BTC 受控验证配置。Sim-1 目标切换为 ETH 1h LONG-only 自然模拟盘观察，当前最大风险不是执行链代码，而是配置真源不清：

1. `.env` 已是运行入口，但 `ConfigManager` 仍从 SQLite 读取 exchange / notification / system / risk / strategies。
2. SQLite 中的 BTC 受控配置不应作为 Sim-1 策略基准。
3. ETH baseline 主真源在 `docs/planning/backtest-parameters.md`，但运行时尚未形成冻结 profile。
4. 执行 TP/SL 当前由 `SignalPipeline._build_execution_strategy()` 从 `SignalResult.take_profit_levels` 派生，仍未有明确 execution config 真源。
5. Backtest / Optuna / Runtime 共享部分参数，但优先级和写入边界未彻底隔离。

本设计目标：

- 为 Sim-1 提供一份可冻结、可审计、可打印 hash 的 `sim1_eth_runtime` 配置。
- 明确 `.env / SQLite / YAML / code defaults / runtime overrides / PG state` 的职责边界。
- 引入 Runtime Resolver 抽象，让运行时只消费一个 `ResolvedRuntimeConfig`。
- 先完成最小收口，不在 Sim-1 前做 PG config SSOT 大迁移。

---

## 2. 架构原则

1. **运行配置先按业务模块划分，再映射到存储介质**
   - 不再直接按 `.env / SQLite / YAML` 讨论配置。
   - 先定义 `environment / market / strategy / risk / execution` 五模块。

2. **Secret 与业务配置分离**
   - `.env` 管 secret、环境、backend mode。
   - SQLite 短期只承载非 secret business config。
   - DB 中已有 secret 字段短期可保留兼容，但 Sim-1 runtime 不再把它们视为真源。

3. **Runtime 冻结，不热改**
   - Sim-1 启动时解析出 `ResolvedRuntimeConfig`。
   - 运行期间 strategy / risk / execution 不允许热改。
   - 允许 DB/API 写入未来配置，但不得影响当前进程，必须标记“next start effective”。

4. **Execution TP/SL 必须有唯一执行真源**
   - 实盘保护单只从 execution 模块生成 `OrderStrategy`。
   - `RiskCalculator.take_profit_levels` 只用于 signal preview / notification，不作为保护单真源。

5. **PG 继续只承担强执行状态**
   - `execution_intents / execution_recovery_tasks` 继续 PG。
   - Config module 短中期继续保留 SQLite。
   - 后续如迁 PG，属于实现层迁移工作，不阻塞 Sim-1。

6. **YAML 不参与启动**
   - YAML 只保留导入/导出/归档能力。
   - `config/user.yaml`、示例文件和历史备份不作为 runtime source。

---

## 3. 当前代码事实

| 事实 | 当前位置 | 架构影响 |
|---|---|---|
| `ConfigManager` 以 SQLite `data/v3_dev.db` 为主 | `src/application/config_manager.py` | Sim-1 不能直接信任当前 SQLite 内容，需 profile 冻结 |
| exchange API key / secret 从 SQLite `exchange_configs` 读取 | `ConfigManager._get_exchange_config_db()` | 需改为 `.env` runtime 真源，避免 secret 入业务 DB |
| webhook 从 SQLite `notifications` 读取 | `ConfigManager._build_notification_config()` | Sim-1 应改为 `.env` 真源或只在 DB 存非 secret channel flags |
| `system_configs` 同时管 symbols/timeframes/EMA/ATR/轮询 | `config_tables.sql` | 需按 market / strategy 拆语义，但短期仍可存 SQLite |
| `RiskConfig.daily_max_loss` 是金额字段 | `RiskConfig` / `ConfigManager.build_capital_protection_config()` | Sim-1 的 10% 权益口径需要 resolver 派生金额 |
| 执行策略从 signal TP 派生 | `SignalPipeline._build_execution_strategy()` | 需改为 execution module 真源 |
| Backtest 有独立 `ResolvedBacktestParams` | `src/domain/models.py` | 可借鉴 resolver 形态，但不能反向污染 runtime |
| Backtest KV 默认仍有旧 TP / BE 口径 | `ConfigEntryRepository.get_backtest_configs()` | 需隔离为 research/backtest，不进入 runtime |

---

## 4. 配置真源矩阵

| 配置域 | Sim-1 真源 | 短期存储 | 是否可热改 | 备注 |
|---|---|---|---|---|
| PG DSN | `.env` | `.env` | 否 | `PG_DATABASE_URL` |
| Core backend mode | `.env` | `.env` | 否 | `CORE_EXECUTION_INTENT_BACKEND=postgres`, `CORE_ORDER_BACKEND=sqlite` |
| Exchange name/testnet | `.env` | `.env` | 否 | `EXCHANGE_NAME=binance`, `EXCHANGE_TESTNET=true` |
| Exchange API key/secret | `.env` | `.env` | 否 | DB 字段仅兼容，不是真源 |
| Feishu webhook | `.env` | `.env` | 否 | DB 字段仅兼容，不是真源 |
| Backend port | `.env` | `.env` | 否 | `BACKEND_PORT` |
| Market symbol/timeframe | Runtime profile | SQLite profile/config tables | 否 | ETH 1h + 4h |
| Strategy trigger/filter | Runtime profile | SQLite profile/config tables | 否 | Pinbar + EMA50 + MTF + ATR disabled |
| Risk | Runtime profile | SQLite profile/config tables | 否 | 1% / 20x / 100% exposure / daily 10% |
| Execution TP/SL | Runtime profile | SQLite profile/config tables | 否 | TP `[1.0,3.5]`, ratios `[0.5,0.5]` |
| Execution state | PG | PG | 系统推进 | `execution_intents / execution_recovery_tasks` |
| Backtest request override | Request | Request payload | 单次有效 | 不写 runtime |
| Optuna trial params | Trial | Study/report | 单次 trial | 只输出 candidate |
| Code safety defaults | Code | Code | 否 | 仅兜底，启动日志必须标注 |
| YAML | 无 | 文件归档 | 否 | 不参与启动 |

---

## 5. 五模块契约

### 5.1 `environment`

职责：进程级环境、secret、backend 开关。

| 字段 | 类型 | Sim-1 值 | 来源 | 消费方 |
|---|---|---|---|---|
| `pg_database_url` | secret str | required | `.env` | PG engine |
| `core_execution_intent_backend` | enum | `postgres` | `.env` | repo factory |
| `core_order_backend` | enum | `sqlite` | `.env` | repo factory |
| `core_position_backend` | enum | `sqlite` | `.env` | repo factory |
| `exchange_name` | str | `binance` | `.env` | ExchangeGateway |
| `exchange_testnet` | bool | `true` | `.env` | ExchangeGateway |
| `exchange_api_key` | secret str | required | `.env` | ExchangeGateway |
| `exchange_api_secret` | secret str | required | `.env` | ExchangeGateway |
| `feishu_webhook_url` | secret str | required | `.env` | NotificationService |
| `backend_port` | int | existing | `.env` | API server |

### 5.2 `market`

职责：交易 universe、订阅范围、warmup、轮询。

| 字段 | 类型 | Sim-1 值 | 来源 | 消费方 |
|---|---|---|---|---|
| `primary_symbol` | str | `ETH/USDT:USDT` | runtime profile | SignalPipeline / warmup |
| `primary_timeframe` | str | `1h` | runtime profile | Strategy runner |
| `mtf_timeframe` | str | `4h` | runtime profile | MTF filter / warmup |
| `subscribed_pairs` | list[str] | `ETH:1h`, `ETH:4h` | derived | ExchangeGateway WS |
| `warmup_history_bars` | int | existing value | runtime profile / DB | warmup |
| `asset_polling_interval` | int | existing value | runtime profile / DB | polling |

### 5.3 `strategy`

职责：信号定义与过滤结构。

| 字段 | 类型 | Sim-1 值 | 来源 | 消费方 |
|---|---|---|---|---|
| `allowed_directions` | list[Direction] | `[LONG]` | runtime profile | DynamicStrategyRunner |
| `trigger.type` | enum | `pinbar` | runtime profile | Strategy runner |
| `pinbar.min_wick_ratio` | Decimal | `0.6` | baseline | Pinbar trigger |
| `pinbar.max_body_ratio` | Decimal | `0.3` | baseline | Pinbar trigger |
| `pinbar.body_position_tolerance` | Decimal | `0.1` | baseline | Pinbar trigger |
| `ema.enabled` | bool | `true` | baseline | EMA filter |
| `ema.period` | int | `50` | baseline | EMA filter |
| `ema.min_distance_pct` | Decimal | `0.005` | baseline | EMA filter |
| `mtf.enabled` | bool | `true` | baseline | MTF filter |
| `mtf.source_timeframe` | str | `4h` | derived | MTF filter |
| `mtf_ema_period` | int | `60` | baseline | MTF filter |
| `atr.enabled` | bool | `false` | baseline | runner filter construction |
| `atr.retained_for_compatibility` | bool | `true` | code/comment | migration note |

### 5.4 `risk`

职责：仓位、杠杆、账户级保护。

| 字段 | 类型 | Sim-1 值 | 来源 | 消费方 |
|---|---|---|---|---|
| `max_loss_percent` | Decimal | `0.01` | runtime profile | RiskCalculator |
| `max_leverage` | int | `20` | runtime profile | RiskCalculator / CapitalProtection |
| `max_total_exposure` | Decimal | `1.0` | runtime profile | CapitalProtection |
| `daily_max_trades` | int? | existing conservative | runtime profile / DB | CapitalProtection |
| `daily_max_loss_percent` | Decimal | `0.10` | runtime profile | Runtime resolver |
| `daily_max_loss_amount` | Decimal | derived at startup | account equity | CapitalProtection |

### 5.5 `execution`

职责：实盘订单和保护单结构。

| 字段 | 类型 | Sim-1 值 | 来源 | 消费方 |
|---|---|---|---|---|
| `tp_levels` | int | `2` | runtime profile | OrderStrategy |
| `tp_ratios` | list[Decimal] | `[0.5,0.5]` | baseline | OrderManager |
| `tp_targets` | list[Decimal] | `[1.0,3.5]` | baseline | OrderManager |
| `initial_stop_loss_rr` | Decimal | `-1.0` | runtime profile | OrderManager |
| `breakeven_enabled` | bool | `false` | runtime profile | RiskManager / future |
| `trailing_stop_enabled` | bool | `false` | runtime profile | OrderStrategy |
| `oco_enabled` | bool | `true` | runtime profile | OrderManager |

---

## 6. 目标抽象

### 6.1 数据模型

建议新增一组运行时配置模型，位置优先放在 `src/application/runtime_config.py` 或 `src/application/config/runtime_models.py`。

```python
class EnvironmentRuntimeConfig(BaseModel): ...
class MarketRuntimeConfig(BaseModel): ...
class StrategyRuntimeConfig(BaseModel): ...
class RiskRuntimeConfig(BaseModel): ...
class ExecutionRuntimeConfig(BaseModel): ...

class ResolvedRuntimeConfig(BaseModel):
    profile_name: str
    version: str
    config_hash: str
    environment: EnvironmentRuntimeConfig
    market: MarketRuntimeConfig
    strategy: StrategyRuntimeConfig
    risk: RiskRuntimeConfig
    execution: ExecutionRuntimeConfig

    def to_order_strategy(self) -> OrderStrategy: ...
    def to_risk_config(self) -> RiskConfig: ...
    def to_capital_protection_config(self, account_equity: Decimal) -> CapitalProtectionConfig: ...
```

### 6.2 Resolver

建议新增 `RuntimeConfigResolver`：

```python
class RuntimeConfigResolver:
    def __init__(self, env_provider, profile_repository, defaults):
        ...

    async def resolve(self, profile_name: str = "sim1_eth_runtime") -> ResolvedRuntimeConfig:
        ...
```

职责：

1. 从 `.env` 读取 environment。
2. 从 SQLite runtime profile 读取 market / strategy / risk / execution。
3. 套用 code safety defaults。
4. 校验 Sim-1 必填项。
5. 生成 `config_hash`。
6. 输出启动日志用的脱敏摘要。

### 6.3 Provider / Repository 边界

短期最小实现：

- `EnvironmentProvider`: 只读 `.env` / `os.environ`。
- `RuntimeProfileRepository`: 落 SQLite，承接非 secret profile。
- `RuntimeConfigResolver`: 组合 environment + profile + defaults。

中期原则：

- Config 继续保留 SQLite 是可接受设计。
- 后续迁 PG 不是 Sim-1 前置条件，也不应抢占执行链稳定性主线。
- 若未来迁 PG，按 repository adapter 迁移即可，不改变 Resolver / RuntimeConfig 契约。

---

## 7. Sim-1 前最小落地方案

> Phase 字母仅用于本文件内部阅读顺序；跨文档引用以 `docs/planning/sim-1-eth-runtime-config-plan.md` 的 `SIM1-R*` 为准。

### Phase A（SIM1-R0）: 契约与 Profile 冻结

1. 新增五模块字段契约文档。
2. 新增 `sim1_eth_runtime` profile 的机器可读版本。
3. 当前 SQLite BTC 配置标记为 `sim0_controlled_btc`。
4. ETH baseline 从 `docs/planning/backtest-parameters.md` 映射到 `eth_baseline_research`。

### Phase B（SIM1-R1）: Runtime Resolver 骨架

1. 新增 `ResolvedRuntimeConfig` 模型。
2. 新增 `RuntimeConfigResolver`。
3. 先支持 `sim1_eth_runtime` 读取和 hash 生成。
4. 启动日志打印脱敏 effective config。

### Phase C（SIM1-R2）: Secret 真源收口

1. `ExchangeGateway` 初始化改为使用 resolver 输出的 `.env` secret。
2. `NotificationService` webhook 改为使用 resolver 输出的 `.env` secret。
3. SQLite `exchange_configs` / `notifications.webhook_url` 暂保留兼容，但不作为 Sim-1 runtime 真源。

### Phase D（SIM1-R3）: Execution TP/SL 收口

1. `SignalPipeline` 不再从 `signal.take_profit_levels` 反推实盘 `OrderStrategy`。
2. `ResolvedRuntimeConfig.to_order_strategy()` 成为实盘保护单唯一入口。
3. `SignalResult.take_profit_levels` 继续用于通知、预览和研究，不作为执行真源。

### Phase E（SIM1-R4/SIM1-R5）: Market / Strategy / Risk 适配

1. warmup / subscribe 只订阅 ETH `1h` 与 `4h`。
2. Strategy runner 使用 ETH profile 的 Pinbar + EMA50 + MTF + ATR disabled。
3. Risk 使用 `0.01 / 20 / 1.0`。
4. daily loss amount 由启动账户权益派生。

### Phase F: Backtest 隔离（SIM1-R6）

1. Sim-1 前要求 Backtest 与 runtime profile 解耦：回测默认使用 `backtest_eth_baseline`，允许 request/overrides 覆盖，但不得反向污染 runtime。
2. 本 Phase 的详细口径与状态以 `docs/planning/sim-1-eth-runtime-config-plan.md` Phase F 为准。

### Phase G: Optuna 隔离（SIM1-R7）

1. Optuna 必须在 Backtest resolver 语义内运行，输出 candidate report，不写 runtime profile。
2. 本 Phase 的详细口径与状态以 `docs/planning/sim-1-eth-runtime-config-plan.md` Phase G 为准。

### Phase H（SIM1-R8）: Sim-1 启动前验收

1. `ResolvedRuntimeConfig.profile_name == "sim1_eth_runtime"`
2. `config_hash` 已生成并打印。
3. `market.primary_symbol == "ETH/USDT:USDT"`
4. `market.primary_timeframe == "1h"`
5. `market.mtf_timeframe == "4h"`
6. `strategy.atr.enabled is False`
7. `risk.max_loss_percent == Decimal("0.01")`
8. `risk.max_leverage == 20`
9. `risk.max_total_exposure == Decimal("1.0")`
10. `execution.tp_targets == [Decimal("1.0"), Decimal("3.5")]`
11. `execution.tp_ratios == [Decimal("0.5"), Decimal("0.5")]`
12. 热改 strategy / risk / execution 不影响当前进程。

---

## 8. 已确认项（原待用户确认项）

以下事项需要用户确认后再进入实现：

1. **daily max loss 10% 的权益基准**（已确认）
   - 启动后以 ExchangeGateway 首次账户权益快照派生金额，并冻结写入 effective snapshot。
   - 若启动瞬间尚无账户快照，则保留百分比口径回退（不伪造金额）。

2. **禁止热改的 API 行为**（已确认）
   - Sim-1 期间 strategy / risk / execution 对当前进程冻结。
   - 允许写入“下次启动生效”的配置，但不得影响当前进程。

3. **Signal preview TP 与 execution TP 的 UI/通知关系**（已确认）
   - preview 继续展示 signal TP（展示/通知/研究语义）。
   - execution TP/SL（OrderStrategy）是唯一执行真源，不从 preview 推导保护单。

### 已确认事项

1. **Runtime profile 短中期保留 SQLite**
   - Config 保留在 SQLite 问题不大。
   - 后续如迁 PG，成本主要是实现层 adapter 迁移。
   - 当前不为 config 迁 PG 预留复杂前置设计。

---

## 9. 给 Claude 的后续任务切片

在用户确认第 8 节后，可按以下切片交给 Claude：

1. **WP-C1: SQLite RuntimeProfileRepository 与 schema**
   - 新增或复用 SQLite profile 表承载 `sim1_eth_runtime`
   - 新增 Pydantic 模型最小实现
   - 不接主程序

2. **WP-C2: RuntimeConfigResolver 骨架**
   - 读取 env + profile + defaults
   - 生成 `ResolvedRuntimeConfig` 与 hash
   - 补最小单元测试（需用户确认后执行）

3. **WP-C3: main.py 启动接线**
   - ExchangeGateway / NotificationService 改吃 resolver output
   - 打印脱敏 effective config
   - 不改 SignalPipeline 行为

4. **WP-C4: Execution OrderStrategy 收口**
   - `SignalPipeline` 接收固定 execution strategy provider
   - 移除实盘执行从 signal TP 派生的主路径

5. **WP-C5: Sim-1 启动前验收脚本**
   - 只做配置解析验收，不跑真实交易
   - 输出 profile/hash/关键字段

---

## 10. 当前结论

Sim-1 前不应直接继续自然模拟盘，也不应继续在 SQLite 分散表里手工改参数。当前已确认 Config 短中期保留 SQLite，因此正确下一步是实现 SQLite `RuntimeProfileRepository` 与 `ResolvedRuntimeConfig` / `RuntimeConfigResolver`，让主程序从“历史配置库散读”过渡到“冻结 runtime profile 驱动”。
