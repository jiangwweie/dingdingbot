# 策略独立标的池与美股合约 RSR + VCB + 15m 全量接入设计

**状态：** `OWNER_APPROVED_IMPLEMENTATION_BASELINE`

**日期：** 2026-07-27

**目标版本：** `0002_strategy_universe_us_equity`

**新增 StrategyGroup：** `RSRVCB-001`

**新增 Event：** `RSRVCB-LONG-15M`

**实施边界：** 完整实盘能力；提交后停在部署确认之前

## 1. 执行摘要

### 1.1 核心结论

本次改造在**唯一 Trading Kernel 执行链**内完成两件事：

1. 让现有六个 Event 拥有**各自独立、可版本化、可无感切换的加密合约标的池**；
2. 增加一组完整的**美股合约 RSR + VCB + 15m Trigger 策略组**，复用现有准入、Ticket、Exchange Command、Lifecycle、Reconciliation、Settlement 与 Review。

```text
Versioned Strategy Universe
        |
        +--> Crypto Event observations
        |
        +--> 1h US-equity RSR projection
                   |
                   +--> top-2 VCB armed structures
                              |
                              +--> closed-15m trigger
                                         |
                                         v
Observation -> StrategySignal -> Readiness/Authority
-> CapacityClaim -> immutable Ticket -> durable Exchange Command
-> protected lifecycle -> reconciliation -> settlement -> review
```

系统不得创建美股专用执行器、第二套订单服务、跨策略信号合并器或文件型运行时权威。

### 1.2 已批准的 Owner 决策

| 决策域 | 已批准结果 | 本期实现 |
|---|---|---|
| 加密标的池 | 每个 Event 独立配置，移除 AVAX | 是 |
| 美股策略 | `RSRVCB-001`，1h RSR + 1h VCB + 完整 15m Trigger | 是 |
| 实盘能力 | 首次接入即具备完整能力，不设 observe-only 产品阶段 | 是 |
| 资金 | 加密与美股共同计算全局 Ticket、止损风险、保证金 | 是 |
| 相关性 | 从本期实现完全移除 | 否，仅保留未来设计附录 |
| 杠杆 | 固定配置 **5x**，不用动态降杠杆替代仓位控制 | 是 |
| 时段 | regular、premarket、afterhours、overnight、周末/节假日完整覆盖 | 是 |
| 老状态 | Owner 部署前手动平仓；执行一次前向 DML 闭环 | 是 |
| 候选替换 | 新范围先预热，原子切换；既有 Ticket 不被改写 | 是 |
| 部署 | 完成代码、集成测试、验收和提交后等待 Owner 确认 | 硬停止 |

### 1.3 实施前代码事实与设计判断

#### 已知客观事实

1. 实施前 Registry 把候选标的直接写在 `RegisteredStrategyContract` 中，候选变化会改变语义哈希；来源：基线 commit `49b87b5f9c3e4c74d5bfb6baa34448146a2ea961` 的 `src/trading_kernel/domain/strategy_registry.py`。
2. 实施前 runtime authority 固定播种 **22 个 scope**；来源：同一基线的 `src/trading_kernel/infrastructure/runtime_authority_seed.py`。
3. 实施前 detector 通过 Event ID 条件分派，且比较强度候选来自静态 contract；来源：同一基线的 `src/trading_kernel/domain/detector.py`、`src/trading_kernel/application/observe_strategy_scope.py`。
4. 实施前执行链已具备全局 ENTRY 串行、Netting Domain、CapacityClaim、Ticket、持久化 Exchange Command 与四类常驻 worker；来源：`docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md` 与基线 `src/trading_kernel/**`。
5. Binance USDⓈ-M 官方 `exchangeInfo` 当前把目标产品标识为 `TRADIFI_PERPETUAL`、`EQUITY`、`USDT`，官方说明产品支持 24/7 交易并可提供最高 10x 杠杆；来源：[Binance Futures exchangeInfo](https://fapi.binance.com/fapi/v1/exchangeInfo)、[Binance Academy TradFi Perpetuals](https://academy.binance.com/ur-PK/articles/tradfi-assets-you-can-trade-on-binance-futures)。
6. 美股核心交易时段与休市/提前收市日历由交易所发布；来源：[NYSE Hours & Calendars](https://www.nyse.com/trade/hours-calendars)、[Nasdaq Trader Calendar](https://www.nasdaqtrader.com/Trader.aspx?id=calendar)。

#### 基于事实的设计判断

**最佳改造点不是让策略代码读取任意币种列表，而是把“策略语义”和“候选成员资格”拆开。** 语义仍由代码和不可变版本定义；候选池由 PostgreSQL 中的版本化 Universe 定义。这样能够实现配置级替换，同时不让运行时执行任意代码，也不破坏既有 Ticket 的身份。

本次属于**中等规模纵向扩展**：执行和订单主干不重写，Registry、Observation、市场事实、准入快照、Capacity、ExitPolicy、PostgreSQL schema 与运行时装配需要协同扩展。

### 1.4 本地实施结论

本设计已经在独立工作区完成实现与本地验收。当前代码具备：

1. **七个静态 Strategy Plugin** 与成员解耦的版本化 Universe；
2. **36 个加密 scope + 13 个美股候选 scope**，AVAX 为零，QQQ/SPY 仅为 reference；
3. **RSR Projection → VCB Armed → 第一根闭合 15m Trigger** 的完整语义与持久化 lineage；
4. **产品、Session、日历、Earnings、Corporate Action** 的行动时 fail-closed 准入；
5. **共享 3 Ticket、9% stop-risk、90% initial margin** 与美股固定 5x；
6. **无重启候选替换**、旧 Ticket 生命周期不变、split reprofile/rewarm；
7. `0002_strategy_universe_us_equity` migration、前向 DML、运维脚本、full-chain mock 与故障恢复测试。

本地实现状态不等于生产状态。Tokyo 仍以 `docs/current/MAIN_CONTROL_ROADMAP.md` 的行动时事实为准，本分支保持 **DEPLOYMENT_BLOCKED**。

## 2. 设计原则与非目标

### 2.1 必须保持的原则

1. **单链：** 所有 Signal 进入同一 Readiness、Authority、Capacity、Ticket 与 Exchange Command 链。
2. **数据库权威：** 运行时只从 PostgreSQL 和行动时交易所事实读取当前状态。
3. **身份不可变：** Signal、Claim、Ticket 冻结所使用的策略、Universe、产品政策、时段政策和退出政策版本。
4. **先持久化后写交易所：** 每次交易所写操作继续先生成 durable Exchange Command。
5. **Fail-closed：** 产品、时段、企业事件、市场数据或版本身份不完整时禁止新 ENTRY。
6. **Lifecycle 不停：** 任意新 ENTRY 冻结都不得中断保护、退出、对账、结算和 Review。
7. **Decimal：** 价格、数量、收益率、风险与政策阈值全部使用 `decimal.Decimal`。
8. **纯领域层：** detector、session、universe、capacity、exit 计算不依赖 SQLAlchemy、网络或文件系统。

### 2.2 明确非目标

1. 不实现跨标的或跨策略**相关性计算、聚类、拒绝或降仓**；
2. 不实现动态 Python 插件加载；
3. 不支持一个 Exposure Episode 加仓；
4. 不按时段自动改变既有 Ticket 的仓位或杠杆；
5. 不把 Markdown、JSON、缓存或生成报告变成生产权威；
6. 不提供旧 schema 的 runtime 兼容读取、双写或 fallback；
7. 不在本分支部署、启服务或执行真实交易所写入。

## 3. 目标架构

### 3.1 三层职责

| 层 | 权威内容 | 允许变化方式 | 不允许承担 |
|---|---|---|---|
| Strategy Plugin | Event 语义、所需事实、detector、exit policy 构造 | 代码发布与不可变版本 | 候选池热更新、数据库 I/O |
| Strategy Universe | 候选、参考标的、排序资格、当前版本 | PostgreSQL 版本安装、预热、原子激活 | 下单、执行任意代码 |
| Trading Kernel | Signal 到 Review 的完整生命周期 | 当前受控运行时 | 美股旁路或策略私有订单链 |

### 3.2 静态 Strategy Plugin Registry

新增纯代码接口：

```python
@dataclass(frozen=True)
class StrategyPlugin:
    event_id: EventId
    detector: StrategyDetector
    market_plan_factory: MarketPlanFactory
    exit_policy_factory: ExitPolicyFactory
    universe_kind: UniverseKind


class StrategyPluginRegistry:
    def get(self, event_id: EventId) -> StrategyPlugin: ...
```

当前六个 Event 与 `RSRVCB-LONG-15M` 都注册为静态插件。Registry 只解决条件分派和可维护性，不允许从数据库加载类名、模块路径或代码。

### 3.3 版本身份

一个可执行 Signal 至少绑定：

```text
StrategyGroupVersion
EventVersion
UniverseVersion + universe_digest
ProductPolicyVersion
SessionPolicyVersion
ExitPolicyVersion
RuntimePolicyVersion
```

其中：

- **Strategy/Event 版本**表示公式、所需事实和行为语义；
- **Universe 版本**表示候选和参考成员；
- **产品/时段版本**表示行动时准入；
- **ExitPolicy 版本**在 Ticket 创建时冻结；
- Universe 成员替换不需要修改 Strategy/Event 版本。

## 4. 独立策略标的池

### 4.1 已批准的加密合约池

| Event | 时间框架 | 候选标的 | 数量 |
|---|---:|---|---:|
| `CPM-LONG-1H` | 1h | ETH、SOL、SUI、BNB、LINK、XRP | 6 |
| `MPG-LONG-1H` | 1h | OP、SOL、SUI、ADA、AAVE、NEAR | 6 |
| `MI-TO-LONG-1H` | 1h | ETH、SOL、DOGE、SUI、AAVE、NEAR | 6 |
| `SOR-LONG-15M` | 15m | BTC、ETH、SOL、BNB、XRP、DOGE | 6 |
| `SOR-SHORT-15M` | 15m | BTC、ETH、SOL、BNB、XRP、DOGE | 6 |
| `BRF2-LONG-1H` | 1h | BTC、ETH、SOL、BNB、LINK、XRP | 6 |

合计 **36 个可观察、可进入 ENTRY 准入的 Event-instrument scope**。**AVAX** 不再属于任何当前 Universe。

### 4.2 美股合约初始 Universe

#### 候选成员

```text
MSTRUSDT  COINUSDT  CRCLUSDT  HOODUSDT  PLTRUSDT
MUUSDT    SNDKUSDT  TSLAUSDT  NVDAUSDT  METAUSDT
GOOGLUSDT AVGOUSDT  SOXLUSDT
```

#### 参考成员

```text
QQQUSDT  SPYUSDT
```

候选 **13 个**，参考 **2 个**。参考成员只参与 RSR/Regime，不创建 runtime Ticket scope。完全激活后总候选 scope 为 **49 个**：36 个加密 scope + 13 个美股 scope。

该初始集合来自策略研究 handoff，并在 2026-07-27 通过 Binance 官方 `exchangeInfo` 核对为当前可交易产品。它是初始业务配置，不代表盈利性结论。

### 4.3 Universe 生命周期

```text
DRAFT -> INSTALLED -> WARMING -> ACTIVE -> RETIRING -> RETIRED
```

1. **DRAFT：** 完整成员、角色、优先级与 digest 已生成，但不可供 runtime 使用；
2. **INSTALLED：** 单事务写入版本、成员与 scope；
3. **WARMING：** `observation_enabled=true`、`entry_enabled=false`；
4. **ACTIVE：** 原子切换 current pointer，新 scope 允许新 ENTRY；
5. **RETIRING：** 旧 scope 禁止新 ENTRY，既有 Ticket 继续；
6. **RETIRED：** 无既有 Ticket 依赖后进入终态。

### 4.4 原子激活条件

激活事务必须验证：

1. Universe 状态为 `WARMING`；
2. 所有候选的 instrument/product profile 已存在且有效；
3. 每个候选已取得插件声明的最小闭合 K 线；
4. reference 成员已满足 RSR/Regime 窗口；
5. 最近一次 projection 成功且 digest 匹配；
6. 没有 scope 身份冲突；
7. 当前 schema、代码 runtime identity 与 policy identity 一致。

成功时同一事务完成：

```text
old current -> RETIRING + entry_enabled=false
new current -> ACTIVE + entry_enabled=true
current pointer -> new universe
append activation audit event
```

不存在“先改配置、稍后再补 scope”的中间可交易状态。

## 5. RSR + VCB + 15m 策略语义

### 5.1 单一 Event 语义

**RSR 不是独立下单策略，VCB 不是独立下单策略。** 两者与 15m Trigger 共同组成一个 `RSRVCB-LONG-15M` Event，并且每次有效触发只产生一个 `StrategySignal`。

```text
4h reference regime eligible
AND 1h RSR candidate is current top-2
AND 1h VCB structure is armed
AND first closed-15m breakout trigger is valid
= one long StrategySignal
```

### 5.2 数据窗口与闭合要求

| 计算 | 周期 | 最小闭合窗口 | 使用对象 | 结果 |
|---|---:|---:|---|---|
| Regime | 4h | 200 | QQQ、SPY | eligible / blocked |
| RSR | 1h | 744 | 13 candidates + 2 refs | ranked projection |
| VCB | 1h | 260 | 当前排名候选 | armed structure |
| Trigger | 15m | 120 | 当前 top-2 且 armed | valid / invalid |
| ATR stop | 1h | 20 | 触发标的 | initial stop |

所有窗口只接受**已经闭合**的 K 线。市场适配器需要按 `close_time` 分页、去重、升序校验，不得把正在形成的最后一根 K 线计入。

### 5.3 4h Regime

参考标的分别计算：

```text
ema_fast = EMA(close, 50)
ema_slow = EMA(close, 200)
regime_member_eligible =
    close[-1] > ema_fast[-1]
    AND ema_fast[-1] > ema_slow[-1]
```

组合准入：

```text
regime_eligible =
    QQQ.regime_member_eligible
    AND SPY.regime_member_eligible
```

任一参考标的数据缺失、超时、Universe 不匹配或产品不可用时，新的美股 ENTRY fail-closed。

### 5.4 1h RSR 排名

对每个候选与两个参考标的计算闭合窗口收益率：

```text
r24(x) = close[-1] / close[-25] - 1
r72(x) = close[-1] / close[-73] - 1
ref24 = (r24(QQQ) + r24(SPY)) / 2
ref72 = (r72(QQQ) + r72(SPY)) / 2
rs24 = r24(candidate) - ref24
rs72 = r72(candidate) - ref72
volume_ratio = quote_volume_last_24h / quote_volume_previous_24h
trend_ok = close[-1] > EMA20[-1] > EMA50[-1]
```

候选资格：

```text
trend_ok
AND rs24 > 0
AND rs72 > 0
AND volume_ratio >= 1.00
```

确定性排序键：

```text
(-rs72, -rs24, -volume_ratio, instrument_id)
```

只选择前 **2** 名进入 VCB/15m 深度观察。少于 2 名时按实际合格数量运行，不补不合格标的。

Projection 必须保存：

- `as_of_close_time`；
- Universe version/digest；
- reference 输入 digest；
- 每个成员原始度量、资格和 rank；
- projection status 与失败原因；
- 唯一性键，保证同一输入幂等。

### 5.5 1h VCB Armed Structure

对 RSR top-2 计算：

```text
bb_mid = SMA(close, 20)
bb_std = sample_stddev(close, 20)
bb_width = (bb_mid + 2*bb_std - (bb_mid - 2*bb_std)) / bb_mid
width_threshold = shifted_quantile(previous_240_widths, 0.35)
compression_ratio = bb_width[-1] / width_threshold
prior_72h_high = max(high[-73:-1])
ema50 = EMA(close, 50)
```

`shifted_quantile` 只使用当前闭合 K 线之前的历史宽度，避免前视。

Armed 条件：

```text
compression_ratio <= 0.90
AND close[-1] > ema50[-1]
AND prior_72h_high > 0
AND regime_eligible
```

Armed Structure 保存 `boundary=prior_72h_high`、`armed_at`、输入 digest 与过期时间。RSR rank 跌出 top-2、Universe 激活版本变化、Regime 失效或结构窗口超时都会使其失效。

### 5.6 完整 15m Trigger

只对当前 top-2 且 armed 的标的计算：

```text
crossed =
    previous_close <= breakout_boundary
    AND current_close > breakout_boundary

bullish = current_close > current_open

volume_ratio =
    current_quote_volume
    / median(previous_20_closed_quote_volumes)

trigger_valid =
    crossed
    AND bullish
    AND volume_ratio >= 1.80
```

完整语义还必须满足：

1. 当前 K 线闭合；
2. Trigger K 线时间晚于 armed 时间；
3. Projection、armed structure 与当前 Universe digest 一致；
4. 产品、Session 与企业事件行动时准入通过；
5. 同一 `instrument + breakout_boundary + armed_generation` 在 **24h** 内不重复；
6. 仅“第一根有效闭合突破 K 线”触发；后续保持在边界上方不重复触发。

Signal facts 至少包括：

```text
rsr_rank, rs24, rs72, volume_ratio_24h
compression_ratio, breakout_boundary
trigger_close, trigger_volume_ratio
regime_digest, projection_id, armed_structure_id
universe_version_id, universe_digest
session_code, session_multiplier
product_policy_version_id
```

### 5.7 Initial Stop

```text
structural_stop = breakout_boundary - ATR14_1h
floor_stop = min(low of previous 20 closed 1h candles)
initial_stop = max(structural_stop, floor_stop)
```

必须满足：

```text
0 < initial_stop < action_time_mark_price
```

若 stop 距离过小而不能通过 instrument rules，或者会使最小可交易数量超过 stop-risk 预算，则拒绝，不放宽 stop。

## 6. 产品、Session 与企业事件

### 6.1 Instrument Product Profile

美股候选需要版本化产品事实：

```text
venue = BINANCE_USDM
contract_type = TRADIFI_PERPETUAL
underlying_type = EQUITY
margin_asset = USDT
status = TRADING
position_mode = HEDGE
configured_leverage = 5
margin_mode = CROSS
```

产品 profile 从官方 exchange facts 采集，保存 source timestamp、payload digest、validity 与版本。关键字段不匹配时禁止新 ENTRY。

### 6.2 Session 分类

所有 Session 计算使用 `America/New_York`：

| Session | 纽约时间 | stop-risk multiplier | 新 ENTRY |
|---|---|---:|---|
| `US_REGULAR` | 09:30–16:00 | 1.00 | 允许 |
| `US_PREMARKET` | 04:00–09:30 | 0.50 | 允许 |
| `US_AFTERHOURS` | 16:00–20:00 | 0.50 | 允许 |
| `US_OVERNIGHT` | 20:00–04:00 | 0.25 | 允许 |
| `US_WEEKEND_HOLIDAY` | 周末、官方休市 | 0.25 | 允许 |
| `UNKNOWN` | 日历缺失或矛盾 | 0 | 禁止 |

提前收市日以版本化官方日历的 `regular_close_at` 为边界；收市后进入 `US_AFTERHOURS`。本次内置并播种 **2026–2028** 官方日历，超出覆盖期 fail-closed，避免把第三方 Python 日历库变成生产权威。

Session 在 Signal 时记录，在 Capacity Claim 的行动时重新计算并冻结。若二者不同，使用行动时 Session 及 multiplier，并记录变化原因。

### 6.3 流动性与 basis 政策

初始政策阈值属于**可版本化的保守运行配置**，不是盈利性或最优性结论：

| Session | 最大 spread | 最大 mark-index 偏离 | top-5 depth / order notional |
|---|---:|---:|---:|
| `US_REGULAR` | 25 bps | 50 bps | ≥ 5 |
| `US_PREMARKET` | 50 bps | 75 bps | ≥ 5 |
| `US_AFTERHOURS` | 50 bps | 75 bps | ≥ 5 |
| `US_OVERNIGHT` | 75 bps | 100 bps | ≥ 5 |
| `US_WEEKEND_HOLIDAY` | 100 bps | 150 bps | ≥ 5 |

行动时 ProductAdmissionSnapshot 包括：

- bid、ask、spread bps；
- mark、index、mark-index deviation bps；
- top-5 双边深度与拟下单 notional 比率；
- funding rate、funding timestamp；
- 产品状态、规则版本和 digest；
- Session、日历版本和 digest；
- corporate-event coverage 与 block 状态。

任一事实缺失、过期、非有限值、版本矛盾或超过阈值都拒绝新 ENTRY。

### 6.4 Earnings 与 Corporate Action

#### Earnings

- 已知准确发布时间：发布前 **4 小时**冻结，发布后等待 **2 根闭合 15m K 线**；
- 只有日期、没有时间：该纽约自然日整日冻结；
- coverage 缺失、过期或来源冲突：禁止该标的新 ENTRY。

#### Split / Contract Adjustment

当拆股、合股、代码变更、合约乘数或交易所规则调整生效：

1. 立即冻结新 ENTRY；
2. 使现有 armed structure 与未消费 trigger 失效；
3. 刷新 product profile 和 instrument rules；
4. 重新预热所需窗口；
5. 通过新的 profile/version 后恢复。

实现中，scope 冻结会写入 `reprofile_required_at_ms`、清空旧 warm readiness/current facts，并使当前 armed structure 失效。恢复必须同时证明：

- `ProductProfile.profile_version` 已递增且在调整生效后观测；
- instrument rules projection version 已刷新；
- 所需市场窗口为调整生效后的闭合数据；
- 当前 Universe 身份仍然精确匹配。

既有 Ticket 的 Lifecycle 始终继续，不因 Session 或企业事件被自动改仓。

## 7. 共享资金、杠杆与 Capacity

### 7.1 全局共享边界

加密和美股共同使用一份 RuntimePolicy 与 CapacityUsage：

```text
max_active_tickets = 3
base_ticket_stop_risk = 3% of current account equity
max_portfolio_stop_risk = 9% of current account equity
max_initial_margin_utilization = 90%
configured_leverage = 5x
maximum_allowed_leverage = 10x
margin_mode = CROSS
```

**9%** 是 `3 Tickets × 3%` 的显式组合止损上限，用于把当前隐含边界变成可审计约束，不扩大当前理论风险。

### 7.2 美股 Session 缩放

```text
effective_ticket_stop_risk =
    base_ticket_stop_risk * session_multiplier
```

缩放的是**新 Ticket 的止损风险预算**，不是杠杆：

| Session | 基础预算 | multiplier | 有效单 Ticket stop-risk |
|---|---:|---:|---:|
| Regular | 3% | 1.00 | 3.00% |
| Pre/After | 3% | 0.50 | 1.50% |
| Overnight | 3% | 0.25 | 0.75% |
| Weekend/Holiday | 3% | 0.25 | 0.75% |

加密策略 multiplier 固定为 1.00。

### 7.3 Action-time Capacity 顺序

1. 刷新账户 equity、余额、持仓、订单；
2. 校验 Netting Domain 空闲；
3. 重新验证 Signal 的当前 Universe；
4. 获取并验证产品、Session、企业事件、流动性与 basis；
5. 计算 session-adjusted stop-risk；
6. 检查 `current gross_risk_at_stop + new risk <= 9% equity`；
7. 检查全局 Ticket capacity；
8. 以 stop 距离计算原始数量；
9. 按 instrument rules 量化；
10. 检查 5x 下初始保证金与 90% 全局边界；
11. 构造不可变 CapacityClaim。

为避免交易所账户快照尚未反映刚签发但未成交的内部预留，检查使用：

```text
effective_initial_margin_before =
    max(exchange_total_initial_margin, active_internal_reserved_margin)
```

`issue_ticket` 在同一事务内锁定目标账户的预算行并再次校验 90% 上限，从而使并发 Claim 不能各自基于同一份旧余额通过。

不允许通过提高杠杆、放宽 stop、忽略企业事件或跳过深度事实来挽救本应被拒绝的 Claim。

## 8. Arbitration、Ticket 与退出

### 8.1 Arbitration

当多个候选同时准备：

```text
event priority
-> universe activation generation
-> RSR rank
-> signal closed_at
-> instrument_id
```

RSR rank 只影响 `RSRVCB-LONG-15M` 内部候选顺序，不改变其他 Event 的业务优先级。最终 ENTRY 仍由全局串行 lane 保证。

### 8.2 Ticket 冻结字段

新增 Ticket 必须冻结或可追溯到：

- StrategyGroup/Event version；
- Universe version/digest；
- projection、armed structure 与 trigger lineage；
- ProductPolicy、SessionPolicy、Calendar、CorporateEvent coverage；
- action-time Session/multiplier；
- action-time product admission digest；
- ExitPolicy version/payload；
- fixed leverage、stop、数量与 CapacityClaim。

Universe 后续切换不得重解释既有 Ticket。

### 8.3 退出政策

`RSRVCB-001` 使用通用可组合 ExitPolicy：

1. **Fast breakout failure：** TP1 前，任一闭合 15m 收盘重新跌破 breakout boundary，退出全部剩余仓位；
2. **TP1：** 达到 **1R**，退出初始数量的 **50%**；
3. **Break-even：** TP1 确认后把保护价提升至不劣于 entry；
4. **Structural runner：** 剩余仓位使用既有结构型 trailing 语义；
5. **Pre-TP1 time stop：** 入场后 **24h** 仍未完成 TP1，退出全部；
6. **Maximum holding：** 入场后 **72h** 退出剩余仓位。

优先级：

```text
protective stop / liquidation safety
-> fast breakout failure
-> max holding
-> pre-TP1 time stop
-> TP1
-> structural trailing
```

实现为通用 `BreakoutFailureRule` 与 `PhaseTimeStopRule`，不能在 worker 中写美股 Event 的条件分支。

## 9. PostgreSQL 设计

### 9.1 前向 schema 版本

新增 Alembic revision：

```text
0002_strategy_universe_us_equity
down_revision = 0001_initial
```

生产 runtime identity 从 `0001_initial` 升级到该 revision。旧 runtime 不允许读取新 schema；新 runtime 不提供旧 schema fallback。

### 9.2 新增与扩展表

| 表/对象 | 目的 | 关键约束 |
|---|---|---|
| `strategy_universe_versions` | Universe 不可变版本 | event/version 唯一、digest 唯一、状态机 |
| `strategy_universe_members` | candidate/reference 成员 | version + instrument 唯一、有效角色 |
| `strategy_universe_current` | 每个 Event 当前指针 | event 唯一、只指向 ACTIVE |
| `strategy_universe_activations` | 激活审计 | append-only、old/new identity |
| `universe_projection_runs` | RSR 运行 | input digest 幂等、status/reason |
| `universe_projection_members` | 每成员度量与 rank | run + instrument 唯一 |
| `armed_structures` | VCB 结构状态 | generation 唯一、不可变 lineage |
| `instrument_product_profiles` | 产品事实版本 | instrument/version 唯一、validity |
| `instrument_product_current` | 当前产品 profile | instrument 唯一 |
| `market_calendar_versions` | 日历版本 | timezone/horizon/digest |
| `market_calendar_sessions` | 交易日与提前收市 | calendar/date 唯一 |
| `corporate_event_versions` | Earnings/split 事件 | instrument/source identity 唯一 |
| `corporate_event_coverage` | 数据覆盖证明 | instrument/range/status |
| `product_admission_policies` | spread/basis/depth/session 政策 | version 唯一、不可变 |

### 9.3 现有表扩展

1. `strategy_runtime_scopes`
   - `universe_version_id`
   - `observation_enabled`
   - `entry_enabled`
   - `scope_state`
   - `warm_ready_at`
2. `strategy_signal_events`
   - `universe_version_id`
   - `universe_digest`
   - `projection_run_id`
   - `armed_structure_id`
   - `session_code`
   - `session_multiplier`
   - `product_policy_version_id`
3. `capacity_claims`
   - `portfolio_stop_risk_before/after`
   - `session_code`
   - `session_multiplier`
   - `product_admission_digest`
4. `instruments`
   - 明确 `asset_class`、venue product identity 与 underlying identity。

所有外键使用数据库主键，业务 identity 与 digest 同时用于审计。append-only 表不允许原地修改业务事实。

### 9.4 幂等与并发

- Projection：`UNIQUE(event_id, universe_version_id, as_of_close_time, input_digest)`；
- Trigger consumption：`UNIQUE(event_id, instrument_id, armed_structure_id, trigger_close_time)`；
- Universe current pointer：激活时 `SELECT ... FOR UPDATE`；
- Scope activation：与 current pointer 同一事务；
- ENTRY lane、Netting Domain 与 Capacity 继续使用现有串行/锁语义；
- 网络 I/O 不进入数据库事务。

## 10. Observation 与市场适配器

### 10.1 Observation 作业

Observation 保持一个 worker，但增加两类可认领作业：

1. **scope observation：** 当前加密 scope 与美股 top-2 深度观察；
2. **universe projection：** 每个闭合 1h 周期为 `RSRVCB-001` 生成一次共享 projection。

Projection 作业使用 PostgreSQL lease，支持崩溃后超时重领；成功写入后才能推动 top-2 的 VCB/15m 观察。

### 10.2 分页市场数据

将 market port 扩展为显式游标分页：

```python
@dataclass(frozen=True)
class ClosedCandlePageRequest:
    instrument: InstrumentId
    timeframe: Timeframe
    end_time_exclusive: datetime
    limit: int


@dataclass(frozen=True)
class ClosedCandlePage:
    candles: tuple[ClosedCandle, ...]
    source_timestamp: datetime
    exhausted: bool
```

Infrastructure 负责 Binance limit 分页；application 负责窗口需求；domain 只消费已验证的闭合序列。

必须拒绝：

- 重复 open/close time；
- 缺口超出 timeframe 容忍；
- 非升序；
- 非闭合尾 K；
- 不同 instrument/timeframe 混合；
- source timestamp 超过 freshness。

### 10.3 性能边界

1. 每个 1h close 对候选和 reference 只构建一次 projection；
2. 15m 深度数据只获取 top-2，而不是 13 个候选全量；
3. 历史窗口增量续接，不在每 tick 重拉 744 根；
4. 运行时查询使用 current pointer、bounded status 和精确 identity；
5. 禁止 full-history scan 和生产 cadence 文件输出。

## 11. 失败语义与可观测性

### 11.1 分类

| 类别 | 示例 | 新 ENTRY 行为 | 既有 Ticket |
|---|---|---|---|
| 数据暂缺 | K 线不闭合、projection 超时 | 等待/记录 | 继续 |
| 权威缺失 | Universe/current policy 不存在 | fail-closed | 继续 |
| 产品不合格 | 非 TRADIFI_PERPETUAL、状态非 TRADING | 拒绝 | 继续并告警 |
| Session 未知 | 日历超期或矛盾 | 拒绝 | 继续 |
| 企业事件未知 | coverage 缺失/过期 | 拒绝 | 继续 |
| 流动性不合格 | spread/basis/depth 超阈值 | 拒绝 | 继续 |
| 资源不足 | stop-risk、margin、Ticket 满 | 拒绝 | 继续 |
| 交易所结果未知 | ENTRY command outcome unknown | 不重发 | 现有恢复链处理 |
| runtime identity 不一致 | commit/schema/profile mismatch | Runtime Fence | 保护链按现有约束运行 |

### 11.2 审计字段

每个 no-trade/rejection 需要稳定 reason code，且带上：

```text
event_id, instrument_id, universe_version_id
projection_id, armed_structure_id, signal_id
session_code, product_policy_version_id
runtime_policy_version_id, observed_at
```

日志只输出 digest 和非敏感 identity，不输出凭证、完整账户载荷或秘密配置。

## 12. 一次性 DML 闭环

### 12.1 部署前置条件

DML 只有在 Owner 明确部署确认后才允许运行，且必须同时满足：

1. `new_entry_submit_enabled=false`；
2. 四个服务已停止；
3. 交易所精确核实所有目标 instrument/side 仓位为零；
4. 交易所目标订单为零；
5. schema/code/release identity 与目标包一致；
6. Owner 已完成需要的手动平仓。

### 12.2 DML 内容

单一事务、按精确主键执行：

1. 保留历史 StrategySignal、Ticket、Exchange Command、Reconciliation、Settlement 与 Review；
2. 对仍占用 current projection 的旧 active Ticket 写入显式 cutover terminal event；
3. 释放对应 Capacity reservation、Netting Domain 与 ENTRY lane；
4. 关闭或解决由旧状态产生的 current Incident；
5. 清理仅表示“当前”的派生投影；
6. 安装新 Universe、36 个加密 scope、13 个美股 warming scope；
7. 设置新 runtime policy/current pointers；
8. 写入 cutover audit 与 before/after 计数。

禁止按 symbol 批量猜测清理，禁止删除 append-only 审计链，禁止保留运行时旧表读取逻辑。

### 12.3 回滚边界

迁移和 DML 在事务提交前可以数据库回滚；提交并接受后为前向切换。部署失败时只能恢复到已认证的新 schema/code 组合或继续修复，不恢复退役 runtime generation。

## 13. 测试与验收设计

### 13.1 测试层级

| 层级 | 核心覆盖 | 是否可作为单独验收 |
|---|---|---|
| Domain unit | RSR/VCB/Trigger、Session、Capacity、ExitPolicy 边界 | 否 |
| Application integration | Universe 激活、projection、Signal、Claim、Ticket | 否 |
| PostgreSQL integration | migration、约束、锁、事务、幂等、DML | 否 |
| Adapter contract | 分页 K 线、exchangeInfo、book/index/funding mock | 否 |
| Full-chain mock | Observation 到 Review 的完整链路 | 是，必须 |
| Fault/recovery | lease、重复、未知结果、服务重启 | 是，必须 |
| Architecture/static | 单链、依赖边界、无文件权威、Ruff/Mypy | 是，必须 |

### 13.2 必须通过的全链场景

1. 新 Crypto Universe 预热并激活，36 个 scope 可观察，AVAX 为零；
2. 美股 1h projection 生成确定性 top-2，VCB armed，完整 15m Trigger 只发一次 Signal；
3. Regular Session 下 Signal 经 readiness、authority、capacity、Ticket、ENTRY mock fill、保护、TP1、BE、runner、settlement、review；
4. Premarket/Afterhours/Overnight/Weekend 分别验证 0.50/0.50/0.25/0.25 stop-risk；
5. 加密和美股同时候选时共同竞争全局 3 Ticket、9% stop-risk、90% margin；
6. Universe 无感切换：新 scope 预热、原子切 current，旧 Ticket 生命周期不变；
7. Earnings 前 4h、时间不确定整日、发布后两根 15m、split rewarm；
8. spread、basis、depth、产品状态与 Session UNKNOWN 分别 fail-closed；
9. fast breakout failure、24h pre-TP1、72h max holding；
10. 投影重试、Signal 重放、worker restart 不产生重复 Ticket 或 Exchange Command；
11. 交易所 ENTRY outcome unknown 不盲目重发；
12. migration + seed + DML 在 disposable PostgreSQL 完成并验证 before/after 不变量。

### 13.3 Mock 边界

允许 mock：

- Binance 公共 K 线、exchangeInfo、mark/index/funding/order book；
- 账户余额、仓位、订单；
- 交易所 command dispatch/result；
- 官方日历与企业事件 provider 输入。

不得 mock：

- domain 公式本身；
- PostgreSQL transaction、外键、唯一约束与并发锁；
- Signal/Claim/Ticket/Command 的真实 repository；
- worker lease、幂等键与状态转换；
- Capacity 与 ExitPolicy 的业务判断。

### 13.4 完成门槛

1. 新增测试先 RED 后 GREEN；
2. 全部 `tests/trading_kernel` 回归通过，不能只跑新增测试；
3. PostgreSQL 集成套件通过；
4. full-chain mock 和 fault/recovery 套件通过；
5. Ruff、Mypy、architecture tests、migration head 检查通过；
6. `git diff --check` 通过；
7. 生成验收矩阵，逐项映射需求、代码、测试与证据；
8. 所有修改提交到隔离分支；
9. 不部署、不启服务、不写交易所，等待 Owner 确认。

## 14. 可维护性与扩展性

### 14.1 新增加密标的

正常路径只需：

1. 安装新 Universe version；
2. 创建 warming scope；
3. 满足插件市场数据窗口；
4. 原子激活。

不修改 detector、worker 或订单代码。

### 14.2 替换美股候选

候选替换同样只变更 Universe version。若仍为相同 `TRADIFI_PERPETUAL/EQUITY` 产品与相同策略语义，无需创建新 StrategyVersion；新增 profile、预热、激活即可。

### 14.3 新增不同类型的美股产品

如果 underlying type、contract type、结算、Session 或规则语义不同，则需要新的 ProductPolicyVersion；只有 detector 公式改变时才升级 EventVersion。

### 14.4 扩展原则

- 新策略以静态 StrategyPlugin 接入；
- 新候选以 Universe version 接入；
- 新产品以 ProductProfile/Policy version 接入；
- 新退出组合以不可变 ExitPolicy version 接入；
- 任何扩展最终仍只产生标准 StrategySignal。

## 15. 相关性未来设计附录

### 15.1 本期明确隔离

本期数据库、领域模型、Capacity、拒绝原因、测试、DML 和运行时都**不增加任何相关性字段或分支**。相关性不会隐含在 sector、reference 或 RSR rank 中。

### 15.2 未来可能语义

若未来单独立项，Owner 已表达的方向是：

```text
相关性升高 -> 降低新 Ticket 仓位
```

而不是：

```text
相关性升高 -> 同一组只允许持有一个
```

未来设计必须独立回答相关矩阵来源、窗口、缺失值、极端行情、组合边际风险、版本冻结、行动时重算与 Lifecycle 不回缩等问题。本附录不构成任何实现授权。

## 16. 最终边界

本设计完成后的目标状态是：

```text
策略语义由代码版本定义
候选成员由 PostgreSQL Universe 版本定义
产品与 Session 由行动时版本化事实定义
加密与美股共用一套 Capacity 和执行链
相关性不参与当前交易决策
完整开发、集成测试、验收、提交后停在部署前
```

任何真实部署、DML、systemd 变更或交易所写入仍需要 Owner 在提交验收后单独确认。
