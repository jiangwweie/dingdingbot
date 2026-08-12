---
title: TRADFI_SOR_M6_LIVE_ENTRY_DESIGN
status: OWNER_DIRECTION_ADOPTED_DESIGN_BASELINE
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
3. 当前 TradFi 本地候选使用 `policy-tradfi-observe` 和
   `tradfi-equity-observe-v1`，并以 Policy Entry disabled、StrategyGroup paused 安装；
   这些身份尚未进入生产，可以在首次 R4 部署前直接替换，不能保留误导性的兼容别名。
4. Crypto 与 TradFi RuntimeProfile 使用同一个 Binance USDⓈ-M account。当前账户 Exposure
   投影按 `venue_id + account_id` 聚合 Ticket 数、Stop Risk 和 Reserved Margin，因此两类
   产品不是物理隔离资金池。
5. Binance Product Snapshot 当前可提供 Product、Session、Mark、Index、Funding、
   best bid/ask 和 Top-of-book；`corporate_event_status` 仍可能为 `unavailable`。

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

### TradFi Policy 控制

独立 TradFi Owner Policy 仍有实际价值：它拥有 Product/Event scope、单 Ticket 小额风险、
Family capacity 和 live-submit authority。首期只有一个 TradFi StrategyGroup，因此前端不
增加一个与 Strategy pause 语义重复的 TradFi Policy 开关：

| 控制 | 首期前端 | 作用 |
| --- | --- | --- |
| **Runtime Entry Fence** | 状态只读 | 部署、身份不一致和故障时阻止整个 Writer |
| **TradFi Owner Policy** | 状态与风险只读 | 定义 TradFi 产品域范围和资本边界 |
| **StrategyGroup pause/resume** | 主操作按钮 | Owner 日常暂停或恢复美股 SOR 新 ENTRY |

M6 首次部署前，将尚未生产化的本地身份改为状态中性的
**`tradfi-equity-usdm-v1`** 和 **`policy-tradfi-main`**。不得保留
`*-observe*` alias、双读或兼容 adapter。

## 同账户跨 Policy 资金边界

M6 不建立第二资金池，也不能让两个 Policy 使用互相矛盾的账户总风险上限。推荐使用
现有 account exposure 投影并增加一个 Seed/Certification 不变量：

1. 同一 `venue_id + account_id` 下的所有启用 Policy 必须拥有相同的账户级上限：
   `max_concurrent_tickets`、`max_gross_stop_risk_fraction`、
   `max_gross_initial_margin_utilization`、`directional_stop_risk_limit_fraction`、
   `max_leverage` 和 `supported_margin_mode`；
2. Policy 仍可拥有不同的单 Ticket 上限、Event scope、Family limit、最小成单比例和
   Entry 状态；
3. TradFi 首期维持 **单 Ticket Stop Risk 上限 0.005**、**单 Ticket Initial Margin
   上限 0.10**，并通过 `opening_range` Family limit 限制同类并发；
4. CapacityClaim 冻结当前 account usage 和 TradFi Policy 版本，Ticket 签发与 dispatch
   前继续使用同一 account exposure 重新验证；
5. 若行动时 Crypto Reservation 已占用账户风险或保证金，TradFi 只使用剩余容量，不能
   以独立 Policy 为由重复计算余额。

该设计避免为首期引入新的“虚拟子账户”概念，也关闭了不同 Policy 总风险上限造成的
顺序依赖。具体账户总上限继续由实验 Profile 和行动时 Owner 批准的 PostgreSQL Policy
事实拥有，本设计不自行扩大资本、杠杆或总风险。

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
3. 小额风险摘要：单 Ticket Stop Risk、单 Ticket Margin、Family capacity 和账户剩余
   Ticket/Stop Risk/Margin；
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

1. TradFi live Profile/Policy 的状态中性身份和 Seed；
2. 同账户多 Policy 的账户级字段一致性认证；
3. TradFi Product/Session/Spread/Mark-Index 的 Readiness 与 action-time revalidation；
4. `unavailable` Corporate Event 的显式 evidence 语义；
5. live Signal 同时创建 Observation Outcome，并允许它与 AdmissionDecision/Ticket 并存；
6. Owner Console 的 Strategy live status、账户剩余容量和 Observation/Ticket 双向链接；
7. R4 Postflight 后通过一次 Strategy resume 开放新 ENTRY，不新增 TradFi 专用执行器。

## 联合部署

M6 完成后，将 **M0.5、M2-M6** 合并为一个精确 R4 候选，不先部署 M5
observation-only 生产阶段：

```text
current production 0004
-> wait for exact internal/external flatness
-> fence Entry and stop old writers
-> preserve 0004 history digest
-> migrate once to final 0005 authority
-> install final neutral TradFi Profile/Policy identities
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
| **单 Ticket Stop Risk** | 账户权益的 `0.005` 上限 | 部署前冻结 |
| **单 Ticket Initial Margin** | 账户 Margin Balance 的 `0.10` 上限 | 部署前冻结 |
| **账户总容量** | 与同账户 Crypto Policy 使用同一组账户级上限 | 代码审查后冻结 |
| **Corporate Event unavailable** | 显式告警和冻结证据，但 M6 v1 不单独阻止 ENTRY | 部署前冻结 |

这些值不由 Migration 推断，也不从文档直接读取；最终由 PostgreSQL Owner Policy、
StrategyUniverse 和对应 Certification evidence 成为运行时权威。

## 聚焦验收

只保留与真实风险和产品语义直接相关的验收：

1. 一个自然 TradFi Signal 可通过正式链创建 immutable Ticket 和 durable ENTRY Command；
2. Pause 在 Signal、Ticket issue 和 dispatch revalidation 边界阻止新 ENTRY；
3. Pause 后既有 Ticket 仍完成 protection、exit、reconciliation、settlement 和 review；
4. Crypto 与 TradFi 共用 account exposure，不能重复使用风险或保证金；
5. 同账户 Policy 账户级字段不一致时 Seed/Certification 失败；
6. 非 REGULAR、stale Product/Schedule、非法 Spread/Mark-Index、错误身份和 occupied
   Netting Domain 均拒绝 ENTRY；
7. live Signal 的 Observation 与真实 Ticket 可并存并双向访问；
8. 既有 Crypto Signal、Ticket、Lifecycle 和 Owner controls 的聚焦回归不变；
9. 部署前只运行受影响的领域、Entry、Lifecycle、Migration、Owner API、前端 build 和
   R4 必需认证，不重复执行无关测试组合。

## 非目标

- 不以 Observation 样本量、观察天数或人工收益判断作为 M6 Entry 前置条件；
- 不自动扩大账户总风险、杠杆、保证金利用率或资本；
- 不恢复加密 `SOR-001`；
- 不引入美股专用 Ticket、Command、Lifecycle 或数据库权威；
- 不把 Strategy pause 解释为平仓；
- 不建设完整企业事件供应链、自动策略优化或自动根据亏损暂停策略；
- 不在本设计记录中执行生产部署或交易所写入。
