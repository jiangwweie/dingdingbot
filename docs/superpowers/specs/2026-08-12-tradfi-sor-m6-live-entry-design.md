---
title: TRADFI_SOR_M6_LIVE_ENTRY_DESIGN
status: IMPLEMENTED_LOCAL_CANDIDATE_PENDING_RELEASE_CERTIFICATION
date: 2026-08-12
---

# TradFi SOR M6 小额实盘设计

## Owner 决策

本系统是一个以盈利为单一目标、允许小额亏损的个人量化实验系统。Owner 已明确：

1. **`SOR-US-EQ-PERP-001` 上线后直接允许小额真实 ENTRY**，不设置先观察若干天、
   累积若干 Observation 或人工判定样本充分后才能交易的产品门槛；
2. **Observation Outcome 继续保留**，但它是与真实 Ticket 并行形成的策略路径和执行
   对照证据，不是实盘解锁条件；
3. **StrategyGroup pause/resume 是日常启停入口**。发现策略行为、产品状态或收益路径
   不符合预期时，Owner 暂停 `SOR-US-EQ-PERP-001` 的新 ENTRY；
4. 暂停 StrategyGroup 不撤销已存在 Ticket 的保护、退出、Reconciliation、Settlement
   和 Review 权限；
5. M6 仍须经过正式 Readiness、Authority、CapacityClaim、Ticket 和 durable Exchange
   Command 链。直接实盘不等于绕过产品事实、资金、风控、身份或交易所写入硬门禁。

## 已知客观事实

1. 当前本地 M2-M5 候选尚未部署，生产仍运行 `0004_owner_control_plane`；当前生产
   Commit、Schema、持仓和服务状态只由 `MAIN_CONTROL_ROADMAP.md` 与行动时直接事实
   拥有。
2. 当前内核已在 Signal 准入、Ticket 签发和 action-time dispatch revalidation 三处读取
   StrategyGroup Control；paused 状态阻止新的 ENTRY，既有 Ticket 生命周期不依赖恢复
   StrategyGroup Entry 权限。
3. M2-M5 曾使用的 `policy-tradfi-observe` 和
   `tradfi-equity-observe-v1` 已在 M6 本地候选中删除；当前实现使用唯一
   `policy-main` 和中性 `tradfi-equity-usdm-v1`，没有兼容别名或第二资金 Policy。
4. Crypto 与 TradFi RuntimeProfile 使用同一个 Binance USDⓈ-M account。当前账户 Exposure
   投影按 `venue_id + account_id` 聚合 Ticket 数、Stop Risk 和 Reserved Margin，因此两类
   产品不是物理隔离资金池。
5. Binance Product Snapshot 当前可提供 Product、Session、Mark、Index、Funding、
   best bid/ask 和 Top-of-book；`corporate_event_status` 仍可能为 `unavailable`。
6. Owner 已明确 **TradFi 不设计任何独立单 Ticket 资金参数**。Crypto 与 TradFi
   共同使用 `policy-main / Policy v4` 的 Ticket、总风险、方向风险、保证金、杠杆和
   Exposure Family 边界。

## 产品状态机

M6 删除“Observation 样本解锁 Entry”的旧状态，使用以下上线状态：

```text
local_candidate
-> R4_staged
-> schema_and_history_certified
-> TradFi_Universe_active
-> Entry_worker_healthy_while_strategy_paused
-> Owner_TOTP_strategy_resume
-> live_small_capital
```

运行后只保留明确的产品状态转换：

```text
live_small_capital
├── normal operation -> Signal + Observation + optional real Ticket
├── Owner pause      -> no new ENTRY; existing Tickets continue
├── Owner resume     -> only future eligible admission may create Ticket
└── safety blocker   -> fail closed; existing Tickets continue safety work
```

“上线即交易”表示 **R4 认证完成后不等待市场观察期**，不表示 Migration 自动写交易所。
Schema、Registry、Policy、Universe 和 Worker 必须先完成只读 Postflight；Entry Worker 在
StrategyGroup 仍 paused 时启动并验证健康，最后由现有 TOTP 保护的 Strategy resume 操作
开放新 ENTRY。

## Observation 与真实 Ticket

同一个 TradFi StrategySignal 可以同时拥有两条互补证据：

| 证据 | 回答的问题 | 权威事实 |
| --- | --- | --- |
| **Observation Outcome** | 如果按冻结的 Entry、Stop、TP1 和路径规则观察，行情首先发生了什么 | 闭合 K 线、冻结报价、MFE/MAE、Path |
| **真实 Ticket / Review** | 系统实际成交、保护、退出后赚亏多少，执行偏差来自哪里 | Exchange orders/fills、Fees、Funding、Slippage、Settlement、Review |

Observation 不创建模拟订单或模拟 PnL。真实 Ticket 继续通过 `signal_event_id` 与
Observation 关联，Owner Console 在 Observation 详情与 Ticket 详情之间提供双向路由和
原返回位置。

## 控制面设计

### StrategyGroup 控制

`SOR-US-EQ-PERP-001` 复用现有 StrategyGroup pause/resume API 和 TOTP 授权：

- **Pause**：立即阻止此 StrategyGroup 的新 Admission、Ticket 和 ENTRY Command；
- **Resume**：允许后续新鲜 Signal 重新参与正式准入；
- **既有 Signal**：已经因 paused 得到终局拒绝的 AdmissionDecision 不复活、不重试；
- **既有 Ticket**：继续保护、退出、对账、结算和 Review；
- **Controlled flatten**：仍是独立 Owner 操作，Strategy pause 不隐含平仓。

### 统一账户 Policy 控制

M6 删除独立 TradFi Owner Policy。**`policy-main / Policy v4` 是同一 Binance account
唯一的资本和 live-submit authority**，同时覆盖 Crypto 与 TradFi 的精确 Event/Profile
组合。产品和策略隔离不再通过第二套资金参数表达：

| 控制 | 首期前端 | 作用 |
| --- | --- | --- |
| **Runtime Entry Fence** | 状态只读 | 部署、身份不一致和故障时阻止整个 Writer |
| **Policy v4** | 统一账户风险与全局 Entry 控制 | Crypto + TradFi 共用一套 Ticket、风险和保证金边界 |
| **StrategyGroup pause/resume** | 主操作按钮 | Owner 日常暂停或恢复美股 SOR 新 ENTRY |

M6 首次部署前，将尚未生产化的 RuntimeProfile 改为状态中性的
**`tradfi-equity-usdm-v1`**，并删除本地候选 `policy-tradfi-observe`。不得保留
`*-observe*` Policy alias、双读或兼容 adapter。

## 统一账户资金边界

M6 不建立第二资金池或第二套单 Ticket 参数。现有 account exposure 投影继续按
`venue_id + account_id` 合并 Crypto 与 TradFi；所有准入只读取同一个 Policy v4：

1. Policy v4 的 `max_concurrent_tickets=3` 同时统计 Crypto 与 TradFi Ticket；
2. `max_ticket_stop_risk_fraction=0.02` 和
   `max_ticket_initial_margin_fraction=0.30` 对两类产品完全相同；
3. `max_gross_stop_risk_fraction=0.06`、
   `directional_stop_risk_limit_fraction=0.04` 和
   `max_gross_initial_margin_utilization=0.90` 是整个账户的共同上限；
4. `opening_range=2` 同时统计 Crypto SOR 与 TradFi SOR，不为 TradFi 增加 Family
   配额；
5. CapacityClaim 冻结当前 account usage 和同一个 Policy v4 版本，Ticket 签发与 dispatch
   前继续使用同一 account exposure 重新验证；
6. 若行动时任一产品 Reservation 已占用 Ticket、风险、方向或保证金容量，另一产品只
   使用 Policy v4 的剩余容量。

Owner Policy scope 从单一 `runtime_profile_id` 改为一个有界、精确、排序的
**Event-to-RuntimeProfile 映射**。每个 Event 只属于一个 Profile，但一个 Policy 可以覆盖
多个 Profile。这使 Policy v4 同时覆盖 `tiny-live-v1` 和 `tradfi-equity-usdm-v1`，而
Product Compatibility、RuntimeScope 和 StrategyUniverse 仍保持严格隔离。

该设计减少一个不必要的 Policy 概念，消除顺序依赖，也不会扩大 Policy v4 已有资本、
杠杆或总风险边界。

## Product 与 Corporate Event 准入

M6 的 action-time ENTRY 必须硬校验：

- Product active、合约规则与 Runtime identity 精确；
- 当前属于 U.S. `REGULAR` Session，Schedule 新鲜且无冲突；
- Mark、Index、best bid/ask 和 Spread 新鲜、有限且在批准范围内；
- Account agreement、position mode、cross margin、固定 leverage 和 API order authority
  已认证；
- Universe、StrategyVersion、Event、Policy 和 Profile 身份一致；
- Netting Domain 空闲，Stop、资金、保证金和保护计划完整；
- Runtime Commit、Schema 与 certified identity 一致。

Corporate Event 首期推荐采用可执行的分级语义，不能让永久 `unavailable` 伪装成
`clear`，也不能因缺少尚未选定的数据供应商永久阻塞所有实盘：

| 状态 | M6 v1 行为 |
| --- | --- |
| **blocked** | 阻止新 ENTRY，既有 Ticket 继续安全生命周期 |
| **clear** | 允许继续通过其他全部 action-time gates |
| **unavailable** | 作为显式证据冻结并在前端告警，但不单独阻止 M6 v1 ENTRY |

Product status/rules drift、异常 Spread、Mark/Index 偏差和 Schedule 冲突仍然 fail-closed。
未来接入机构级 Earnings/Split authority 后，可以用新的 Owner Policy 版本把
`unavailable` 升级为硬门禁，不回写既有 Signal、Ticket 或 Review。

该分级是 **M6 设计推荐**，不是 Owner 已确认的真实资金范围；它必须随首次实盘参数包
一起冻结。

## Owner Console

StrategyGroup 驾驶舱增加一个紧凑的 **Live Control** 区域：

1. 当前状态：`Live enabled`、`Paused`、`Temporarily unavailable` 或
   `Needs intervention`；
2. 新 ENTRY 状态：Strategy Control、Policy capability、Entry Fence 三层结果和首要
   blocker；
3. 统一 Policy v4 风险摘要：账户剩余 Ticket、Stop Risk、方向风险、Margin 和
   Exposure Family capacity；
4. Active Universe、当前 Session、下一可交易窗口和 Product facts 新鲜度；
5. 主按钮：`Pause strategy` 或 `Resume strategy`，使用现有 TOTP 确认；
6. 次按钮：查看 Signals、Observations、Tickets、Reviews 和受控平仓；
7. 不显示“观察满 N 天后启用”“样本达标后解锁”或重复的 TradFi Policy 开关。

## API 与后端边界

M6 复用：

- `POST /api/owner/v1/controls/strategies/{strategy_group_id}/pause`；
- `POST /api/owner/v1/controls/strategies/{strategy_group_id}/resume`；
- 现有 Controlled Flatten API；
- 现有 Universe Diff、TOTP、Warming、Certification 和 Activation 链。

M6 后端新增或完善：

1. TradFi live RuntimeProfile 的状态中性身份和 Seed，并删除第二 TradFi Policy；
2. Policy scope 支持一个 Policy 对多个精确 Event-to-RuntimeProfile 映射；
3. TradFi Product/Session/Spread/Mark-Index 的 Readiness 与 action-time revalidation；
4. `unavailable` Corporate Event 的显式 evidence 语义；
5. live Signal 同时创建 Observation Outcome，并允许它与 AdmissionDecision/Ticket 并存；
6. Owner Console 的 Strategy live status、账户剩余容量和 Observation/Ticket 双向链接；
7. R4 Postflight 后通过一次 Strategy resume 开放新 ENTRY，不新增 TradFi 专用执行器。

## 联合部署

M6 完成后，将 **M0.5、M2-M6** 合并为一个精确 R4 候选，不先部署 M5
独立观察阶段：

```text
current production 0004
-> wait for exact internal/external flatness
-> fence Entry and stop old writers
-> preserve 0004 history digest
-> migrate once to final 0005 authority
-> install final neutral TradFi Profile and extend policy-main scope
-> install + certify + activate approved TradFi Universes
-> start safety workers
-> start Entry while SOR-US-EQ-PERP-001 remains paused
-> readonly postflight and runtime identity certification
-> TOTP resume SOR-US-EQ-PERP-001
-> live small-capital ENTRY eligible
```

部署前必须重新读取 PostgreSQL、Binance positions/orders/account capability、systemd、
Nginx 和 exact Commit/Schema facts。Migration 不自动平仓、不自动签署 Binance agreement、
不恢复加密 `SOR-001`，也不改变无关 Nginx 服务。

## 首次实盘参数包

Owner 已确认“上线即交易”和“异常时暂停策略”，但以下真实资金范围仍必须在部署前形成
一个精确版本化参数包；设计和开发不需要因此停顿：

| 参数 | 当前设计推荐 | 状态 |
| --- | --- | --- |
| **方向** | LONG、SHORT 都可交易，使用独立 Event/Universe 和 Netting Domain | 部署前冻结 |
| **Active Universe** | 从 8 个候选中安装经行动时认证通过的 5–8 个成员；两侧可先相同 | 部署前冻结 |
| **全部资金参数** | 完整复用 `policy-main / Policy v4`，不增加 TradFi 专属字段或数值 | Owner 已确认 |
| **Corporate Event unavailable** | 显式告警和冻结证据，但 M6 v1 不单独阻止 ENTRY | 部署前冻结 |

这些值不由 Migration 推断，也不从文档直接读取；最终由 PostgreSQL Owner Policy、
StrategyUniverse 和对应 Certification evidence 成为运行时权威。

## 聚焦验收

只保留与真实风险和产品语义直接相关的验收：

1. 一个自然 TradFi Signal 可通过正式链创建 immutable Ticket 和 durable ENTRY Command；
2. Pause 在 Signal、Ticket issue 和 dispatch revalidation 边界阻止新 ENTRY；
3. Pause 后既有 Ticket 仍完成 protection、exit、reconciliation、settlement 和 review；
4. Crypto 与 TradFi 使用同一个 Policy v4 和 account exposure，不能重复使用 Ticket、
   风险、方向、Family 或保证金容量；
5. PostgreSQL 中不存在第二个 TradFi Owner Policy，所有 TradFi RuntimeScope 冻结
   `policy-main` 的精确版本；
6. 非 REGULAR、stale Product/Schedule、非法 Spread/Mark-Index、错误身份和 occupied
   Netting Domain 均拒绝 ENTRY；
7. live Signal 的 Observation 与真实 Ticket 可并存并双向访问；
8. 既有 Crypto Signal、Ticket、Lifecycle 和 Owner controls 的聚焦回归不变；
9. 部署前只运行受影响的领域、Entry、Lifecycle、Migration、Owner API、前端 build 和
   R4 必需认证，不重复执行无关测试组合。

## 非目标

- 不以 Observation 样本量、观察天数或人工收益判断作为 M6 Entry 前置条件；
- 不为 TradFi 增加单 Ticket Stop Risk、Margin、Leverage、并发或 Family 参数；
- 不自动扩大账户总风险、杠杆、保证金利用率或资本；
- 不恢复加密 `SOR-001`；
- 不引入美股专用 Ticket、Command、Lifecycle 或数据库权威；
- 不把 Strategy pause 解释为平仓；
- 不建设完整企业事件供应链、自动策略优化或自动根据亏损暂停策略；
- 不在本设计记录中执行生产部署或交易所写入。
