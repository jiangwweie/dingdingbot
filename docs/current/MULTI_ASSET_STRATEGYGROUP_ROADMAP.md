---
title: MULTI_ASSET_STRATEGYGROUP_ROADMAP
status: CURRENT_PLAN
program_id: MASG-P1
last_verified: 2026-08-23
---

# Multi-Asset StrategyGroup Roadmap

## Decision

后续产品主线以 **StrategyGroup** 为核心，把现有加密永续实验平台扩展为
一个可管理多个 Venue、产品类别、StrategyVersion 和 StrategyUniverse 的
个人多资产量化实验平台。

本路线图确认以下稳定方向：

1. 现有加密 **`SOR-001`** 保持独立谱系，其暂停或恢复状态继续由当前
   Owner Control 和 PostgreSQL 事实决定；
2. 美股参考资产永续合约的 15m SOR 使用新的 StrategyGroup 谱系，规划身份为
   **`SOR-US-EQ-PERP-001`**，不作为 `SOR-001` 的新版本；
3. StrategyGroup、StrategyVersion、Event 和 StrategyUniverse 分层管理，
   标的成员变化不要求修改策略公式版本；
4. 所有资产继续共享一个 Trading Kernel、一个 PostgreSQL 权威和同一条
   Ticket/Command/Lifecycle/Reconciliation/Review 链；
5. 因子目录不是当前一级产品对象。因子只作为 StrategyVersion 的输入证据，
   待策略组、标的中心和跨资产运行底座稳定后再评估；
6. 任何新 Venue、账户、标的、资本和真实 ENTRY 都必须在对应阶段单独确认，
   不能由本路线图隐含授权。
7. 在多资产开发前插入 **M0.5：Deployment Simplification**。日常发布按
   静态前端、Owner API、同 Schema Kernel 和 Schema/Authority Upgrade 分级，
   Controlled Flatten 不再作为普通部署的默认步骤。
8. Owner 已于 **2026-08-11** 采纳 M1，并授权本地实施 M2–M5；本授权不包含
   生产部署、真实 TradFi ENTRY、资本增加或加密 `SOR-001` 恢复；
9. M5 **只暂停 TradFi Ticket** 的生产准入，不删除未来实盘能力。
   Observation Outcome 不构造模拟 Ticket、模拟订单或第二执行链；M6 恢复权限后
   仍接回正式 Readiness、CapacityClaim、Ticket 和 Command 链。
10. Owner 已于 **2026-08-12** 明确 M6 采用上线即小额实盘：R4 认证完成后不等待
    Observation 天数或样本数，直接通过 StrategyGroup resume 开放
    `SOR-US-EQ-PERP-001` 新 ENTRY；异常时复用 StrategyGroup pause，既有 Ticket
    继续安全闭环。
11. Owner 已明确 **TradFi 不拥有独立资金 Policy 或单 Ticket 参数**。Crypto 与 TradFi
    共同使用 `policy-main / Policy v4` 的 Ticket、风险、方向、保证金、杠杆和
    Exposure Family 约束；产品差异仅由 RuntimeProfile、Product Compatibility、
    Universe、Event 和 StrategyGroup Control 表达。
12. Owner 的主观市场判断将以未来的 **Owner Regime Gate** 表达：它只限制新 ENTRY
    的方向与允许参与的 StrategyGroup，不创建指定订单，也不改写任何 Ticket 的
    Initial Stop、TP1、Runner、退出或对账语义；每一次判断必须留下不可事后改写的
    Journal。
13. 风险阶梯、回撤降档和本金提取属于后续 **资本治理** 轨道。它们不构成当前
    `policy-main / Policy v4` 的变更，不自动提高风险、并发、杠杆或资本，也不授权
    交易所提现或转账。
14. **`SOR-INSTRUMENT-EFFECT-v1`** 已完成第一轮 Instrument Effect 研究。结果支持
    “历史横截面差异存在”，但不支持静态“好币名单”：固定 Symbol 排名未形成稳定的
    滚动样本外优势。因此静态 Universe 排名路线停止，研究对象转为
    **Strategy × Instrument × Current State**。（来源：冻结研究包 `decision.json`、
    `headline.json`、`rolling_oos_bootstrap.json`）
15. 当前进入 **P3-X：SOR Dynamic Selection & Trading V0**。第一版不是 AI 选币、综合 Fit Score
    或机器学习，而是从 SOR 的 **Compression → Expansion** 语义推导少量可解释状态，
    以 `UTC 01:00` 可知的 Pre-trigger `OR Width / ATR` 为 Primary Feature，Activity 为
    最低选择前提，Pre-session Extension 等只作 Shadow Diagnostic。
16. P3-X 明确区分 **Source Integrity、Qualification、Selection 与 Dynamic Universe**：
    Source Integrity要求固定24-member输入全部完整，否则whole-attempt `SOURCE_FAILED`；资格
    回答source完整后标的是否具备最低产品/Activity/几何条件，选择回答有限名额下谁更符合
    当前EventSpec，Dynamic Universe是承载已批准Selection结果的运行方式。相对排名靠后不
    等于不具备交易资格。
17. Historical Replay 已完成并通过全部冻结 Gate：Dynamic 7 相对 Static 7 的
    Tail3/directional slot-day 提升 **24.1%**，高于全部 100 个 Random controls，且形成
    `Selected > Near > Not Selected`、`9/10` 正向 90-day blocks 与 LONG/SHORT 双向改善。
    原始 Replay decision 为 `ADVANCE_TO_FORWARD_SHADOW`；Owner 后续明确淘汰独立 Forward
    Shadow，把下一阶段改为生产详细设计。（来源：`/Users/jiangwei/Downloads/REPORT.md`，
    SHA-256 `de8edc672552097ad6f9e3988e08254f75b46d33433ad2cd12fd1e56de59a298`）
    DS-00进一步确认该外部报告使用binary64 Feature arithmetic；批准的Decimal Golden在7个
    相等OR/ATR cohort边界冻结`Tail3=1,323`而非`1,324`。这只修正数值表示与稳定tie-break，
    不修改Feature、Activity floor、Top N、Candidate Panel或Outcome。（来源：DS-00 manifest）
18. 生产语义已冻结为：Candidate 直接读取 Binance public market data；任一Candidate缺Kline/
    窗口或source integrity失败时whole-attempt=`SOURCE_FAILED`且不得Rank补位；`Ready=1..7`形成
    同等数量 Desired members，`Ready=0` 是不 fallback 的 **`VALID_EMPTY`**；相同成员走
    **`NO_CHANGE`**；变化时先建立 **Strategy Entry Vacuum**，停止新交易并撤销unfinished
    ENTRY，真空归因的部分成交只有在实际数量形成合法TP1+Runner双腿时才保留，否则
    controlled flatten；任何未连续覆盖eligible close的SOR Authority都必须在grant前完成durable
    Authority Gap Audit，Vacuum activation/fallback使用`previous ∪ desired`，late continuity和
    late普通`NO_CHANGE`只审计current pair，checked-negative与positive suppression均可证明；
    LONG/SHORT串行warming、最终原子切换。每个已经处于dynamic mode的Session在Selection结果
    出现前建立`PRE_FENCE_CONTINUITY`，并一直延续exact current pair到普通`NO_CHANGE`替换或
    Vacuum commit原子切断；Selection失败只追加reason，不决定continuity。post-fence运行失败仅在
    Owner Enabled、previous pair operationally valid、ENTRY已drain且union audit完整新鲜时显式
    `FALLBACK_PREVIOUS`。Owner Pause优先级最高；Resume同成员也必须drain/audit/resolve Pause
    Vacuum后提交新`NO_CHANGE`。每个Authority冻结`first_eligible_close_time_ms`，跨close提交必须
    rollback、扩展audit并顺延。Generation Desired facts不预分配Universe ID、不复制Dynamic
    target members；actual Universe创建transaction直接写唯一Generation FK，不创建第二linkage
    table、direct Snapshot FK或rollback member副本；新合法Selection可`SUPERSEDED`尚未生效的旧Desired。
    首次Static-to-Dynamic尝试保留Static authority直到首个Dynamic outcome；post-fence失败复用
    `FALLBACK_PREVIOUS + STATIC_BASELINE`冻结Gap Audit/suppression/first eligible close并保持Static
    mode。`session_start_ms=D 00:00`只标识SOR Session，Authority Period从`D 01:00`decision boundary
    开始。`VALID_EMPTY`只向前阻止new ENTRY，不追溯撤销合法Ticket/fill或protected lifecycle。
    Release compatibility只复用现有Release Certification manifest的薄投影，不建立第二发布
    系统。（来源：Owner active-task decision）
19. 防止 **Researcher Overfitting** 的边界保持不变：Selection Clock、候选集、
    Point-in-Time 输入、Feature 定义、排序、名额、Baseline、Random seed、Path 口径和
    判定规则在读取 V0 Replay 结果前冻结。已用于提出 OR/ATR 假设的历史结果只能作为
    Development Evidence；Owner 选择在不提高风险的正式小资金运行中取得下一层证据，
    不把 Historical Tail3 lift 重新描述为真实 Net PnL 或未来稳定性证明。

## Authority Boundary

本文件只拥有 **M0–M7（含 M0.5）与 Post-M6 P0–P4 的稳定阶段顺序、目标、依赖、
工作量区间和阶段门**。
它不拥有以下易变或运行时事实：

| 信息 | 唯一权威 |
| --- | --- |
| 当前生产 Commit、Schema、服务、Ticket、持仓、订单和剩余阻塞 | `MAIN_CONTROL_ROADMAP.md` 与行动时直接事实 |
| 当前 StrategyGroup、Event 和版本语义 | Strategy Registry |
| 当前 Universe 成员、Warming、Certification 和 Active 指针 | PostgreSQL StrategyUniverse |
| 当前资本、容量、风险和允许范围 | Owner Policy 与实验 Profile |
| Owner Regime Journal、有效方向范围和 Owner 操作审计 | PostgreSQL 的追加事实与当前 Owner Control 投影 |
| 当前账户、产品、订单、仓位和成交事实 | Venue 只读事实 |
| 具体页面、API、Schema 和 Adapter 设计 | 后续逐项批准的设计规格 |

历史美股研究分支及其设计、测试和验收矩阵只能作为设计来源。它们不是当前
Schema、Policy、运行时或部署权威，也不能整体合并为当前执行链。

## Product Model

前端和运行时围绕以下产品层级组织：

```text
RuntimeProfile / Venue
-> StrategyGroup
-> StrategyVersion / Event
-> StrategyUniverse
-> Observation / StrategySignal
-> Ticket lifecycle
-> Settlement / Review
```

实际交易仍严格沿用唯一执行链：

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

策略代码在 `StrategySignal` 结束。任何跨资产扩展都不得增加美股专用执行器、
第二套订单系统、并行数据库权威或 Venue 私有生命周期。

## Planned Owner Regime Boundary

Owner 的市场判断是对既有范围的**附加限制**，不是另一条下单路径。未来实现时，
每个新 ENTRY 必须同时通过下列范围；既有 Ticket 不重新受 Gate 约束，仍按冻结的
生命周期继续保护、退出、对账、结算和 Review：

```text
Global Entry
AND Owner Regime Gate
AND StrategyGroup Control
AND Strategy × Instrument Scope
AND normal Readiness / Capacity / Netting Domain admission
```

| Regime 状态 | 新 ENTRY 范围 | 既有 Ticket |
| --- | --- | --- |
| `BOTH` 或无有效 Gate | 不因方向额外收缩当前已允许范围 | 不变 |
| `LONG_ONLY` | 仅 Long 方向且在允许 StrategyGroup 范围内 | 不变 |
| `SHORT_ONLY` | 仅 Short 方向且在允许 StrategyGroup 范围内 | 不变 |
| `FLAT` | 禁止全部新 ENTRY；可由 Global Entry freeze 表达 | 不变 |

Regime Journal 至少冻结决策时间、生效和到期时间、方向、允许 StrategyGroup、参考
市场事实与价格、失效条件、简短理由和 Owner 操作身份。理由是审计证据，不是策略
信号、价格预测或订单授权。具体 Schema、TOTP、事务与失败恢复在 P1.2 设计阶段确定；
在实现前，系统不推定存在有效 Regime Gate。

## Planned Strategy Identity

```text
SOR Family
├── SOR · Crypto Perpetual · 15m
│   └── SOR-001
└── SOR · US Equity Perpetual · 15m
    └── SOR-US-EQ-PERP-001
        ├── SOR-US-LONG-15M
        └── SOR-US-SHORT-15M
```

两个 StrategyGroup 的 StrategyVersion、Universe、Owner Control、Admission、
Ticket、收益和 Review 必须独立统计。LONG 与 SHORT 可共享初始候选研究，但
必须保持独立 Event 和独立准入证据。

## Program Stages

| 阶段 | 目标结果 | 主要范围 | 阶段完成条件 |
| --- | --- | --- | --- |
| **M0：现有内核收尾** | 关闭既有 P0 重建计划 | `promote-full`、最终需求审计、文档状态收口 | `MAIN_CONTROL_ROADMAP.md` 从行动时直接证据记录 P0 完成 |
| **M0.5：部署精简** | 日常改动按影响面进入独立发布通道 | 静态前端、Owner API、同 Schema Kernel、Schema/Authority Upgrade；自然空仓优先 | 前端/API 不再触发 Kernel 停机或空仓；Kernel 和 Migration 保留相称门禁 |
| **M1：Venue/Product 决策** | 形成当前可执行的 Capability Matrix | Venue、账户、产品、Session、方向、数据、企业事件、故障语义 | Owner 明确 Venue、账户隔离、首批候选和首期方向范围 |
| **M2：产品化前端** | StrategyGroup 驾驶舱、标的中心和 Universe 管理 | 只读标的状态、归属、Universe Diff、Warming、Activation、审计记录 | 日常策略与标的管理不依赖手工 SQL 或拼装多处事实 |
| **M3：跨资产运行底座** | 当前 Kernel 能表达目标 Venue/Product | 保留 canonical Instrument ID，扩展 RuntimeProfile、Product Profile、Session、Corporate Action 和当前 Venue capability | 新 Profile 可完成只读认证和 Observation，且现有加密 Profile 无行为漂移 |
| **M4：美股 SOR** | 新 StrategyGroup 可以自然产生标准 Signal | 美股 Opening Range、LONG/SHORT Event、Market Plan、Exit Policy、版本身份 | `SOR-US-EQ-PERP-001` 在 Entry 禁用状态完成 Live/Replay 一致的 Observation |
| **M5：Observation/Shadow** | 获得产品微观结构和策略路径证据 | Spread、Top-of-book quantity、Mark/Index、Opening Range、TP1、MFE/MAE、失败退出、Session 分布；不把报价摩擦称为真实 Slippage | Signal-owned Outcome 可稳定形成并在 M6 与真实 Ticket 并行；不作为实盘解锁门槛 |
| **M6：小规模实盘闭环** | 上线后直接进入受控小额真实交易 | 统一 Policy v4、StrategyGroup pause/resume、ENTRY 准入、保护、退出、结算、Review | R4 认证后无观察等待期；Crypto/TradFi 共用账户预算，自然 Ticket 完整闭环且无残留或未解决 Incident |
| **M7：第二策略族** | 评估当前内核上的 `RSRVCB-001` | 按当前 Schema/Policy 重写可复用领域模块 | 仅在美股产品底座和 SOR 闭环稳定后进入实施 |

### TradFi Strategy Backlog

本轮只实现 `SOR-US-EQ-PERP-001`。其他策略保留为明确待办，不直接把加密版本迁移到
美股产品，也不与本轮 Registry、Universe 或收益统计混合。

| 策略族 | 拟议独立身份 | 需要重新验证的产品语义 | 排序 |
| --- | --- | --- | --- |
| **MPG** | `MPG-US-EQ-PERP-001` | REGULAR 动量、跨标的排名、开盘后追价和 Session 收尾 | SOR M5 后优先评估 |
| **BRF2** | `BRF2-US-EQ-PERP-001` | 反弹失败、指数背景、企业事件和隔夜 Gap | MPG 后 |
| **CPM** | `CPM-US-EQ-PERP-001` | Session 化回调、Stop distance、Time Stop | 暂缓 |
| **MI** | `MI-US-EQ-PERP-001` | 12h impulse 重定义、Session 连续性和追价控制 | 暂缓 |
| **RSRVCB** | `RSRVCB-001` | 当前 Kernel 上的全量重写与产品适配 | M7 |

## Workload Envelope

以下区间用于排序，不构成交付承诺。估算假设一名开发者、复用当前 Kernel 和
Owner Console，并采用与风险相称的聚焦测试。真实市场观察和自然 Ticket 等待
时间与净开发时间分开计算。

| 阶段 | 净开发工作量 | 典型日历时间 | 主要不确定性 | 影响等级 |
| --- | ---: | ---: | --- | --- |
| **M0** | 1–2 天 | 1–2 天 | 行动时生产事实和最终审计发现 | 低 |
| **M0.5** | 10–17 天 | 2–3.5 周 | Owner API 解耦和自然空仓发布边界 | 中，部署控制面 |
| **M1** | 2–4 天 | 2–4 天 | 目标 Venue 当前官方产品与账户能力 | 极低，只读 |
| **M2** | 10–16 天 | 2–3 周 | 只读页面与受控 Universe 写能力的边界 | 低至中 |
| **M3，同一 Venue** | 10–15 天 | 2–3 周 | 当前 Binance 绑定点和产品事实扩展 | 中 |
| **M3，全新 Venue** | 20–30 天 | 4–6 周 | Adapter、账户模式、命令和对账语义 | 中至高 |
| **M4** | 7–12 天 | 1.5–2.5 周 | Opening Range、Session 和退出语义 | 低至中 |
| **M5** | 4–8 天开发 | 已完成本地候选；生产后持续积累 | 自然市场日和有效 Observation 数量 | 极低 |
| **M6** | 4–8 天开发 | 上线后等待自然 Ticket 闭环，不等待 Observation 解锁 | 同一 Policy 下的跨 Profile 账户容量、行动时 Product 准入和自然 Ticket 生命周期 | 高但有界 |
| **M7** | 15–25 天 | 3–5 周 | 旧设计向当前 Schema/Policy 的重写范围 | 中 |

M0.5 全部完成后，如果目标产品可以继续使用当前 Venue，预计约 **7–10 周净开发时间**
进入 Observation；如果必须接入全新 Venue，预计约 **10–14 周净开发时间**
进入 Observation。M1 的只读研究可以在 M0.5 期间交错进行；M2 的只读信息架构
可以在 M1 后开始，受控 Universe 操作则依赖 M3 的正式后端契约。

## M0.5 Release Model

M0.5 的具体分类器、独立 Release 路径、服务单元、认证 Manifest 和恢复行为由
`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` 统一定义。其生产安装状态继续只由
`MAIN_CONTROL_ROADMAP.md` 记录；在该状态明确切换前，既有生产流程保持有效。

| 发布级别 | 适用范围 | 空仓要求 | 受影响服务 | 目标操作时间 |
| --- | --- | --- | --- | ---: |
| **R0：无需部署** | 文档、研究、规划 | 否 | 无 | 0 |
| **R1：静态前端** | React、CSS、图表、路由和文案 | 否 | 仅静态 Release Symlink | 1–3 分钟 |
| **R2：Owner API** | 查询、展示模型、认证和兼容的 Owner Control API | 否 | 仅 Owner API | 3–8 分钟 |
| **R3：同 Schema Kernel** | 策略、Worker、Lifecycle、Risk、Venue Adapter | 是 | 四类 Kernel Worker | 空仓后 12–20 分钟 |
| **R4：Schema/Authority Upgrade** | Migration、Registry、Policy、RuntimeProfile | 是 | Kernel 与 PostgreSQL Authority | 空仓后 20–60 分钟 |

M0.5 必须实现以下稳定语义：

1. 变更范围只能向更重发布级别升级；未知或共享 Kernel 文件默认进入 R3；
2. R1 不运行 Kernel 全量认证，不停止 Worker，不访问交易所；
3. R2 使用独立 Owner API Release 身份，只执行聚焦契约、认证、数据库兼容和
   Unix Socket/HTTPS Smoke；
4. R3 保留完整 Kernel 认证、精确 Runtime Identity、内外部空仓、Entry 最后
   启动和失败后 Fence；
5. R4 保留停止、空仓、前向 Migration、历史保留验证和 Fix-forward；
6. 普通 Kernel 发布优先 Stage 后等待自然空仓，现有 Ticket 正常保护和退出；
7. Controlled Flatten 仅用于紧急安全修复、不能等待的 Migration 或独立 Owner
   平仓决策，不由普通部署自动触发；
8. 发布输出应显示 Release 类型、受影响服务、当前阶段、单一首要 Blocker 和
   每阶段耗时，避免人工拼装多处日志；
9. 前端可只读展示发布状态，但实际发布继续由本地 SSH 控制面执行。

## Dependency Order

```text
M0
 ↓
M0.5: Deployment Simplification
 ↓
M1
 ├── M2A: 标的中心与 StrategyGroup 只读驾驶舱
 └── M3: 跨资产与 Venue 底座
       ├── M2B: Universe 受控编辑
       └── M4: SOR-US-EQ-PERP-001
              ↓
             M5: Observation / Shadow evidence
              ↓（无样本解锁门槛）
             M6: 上线即小规模实盘
              ↓
             M7: RSRVCB-001
```

M0 是当前既有程序的收尾，不应被新的产品设计长期拖延。M0.5 优先解决后续
频繁前端、API 和 Kernel 迭代的发布成本；M1 的只读调研可与其交错，但 M2–M4
的实施不应继续扩大现有发布耦合。M1 是 M3 和 M4 的前置决策；M2A 可以先行，
但 M2B 不得在后端版本、事务和审计语义未确定时通过前端直接修改运行时表。

## M1 Owner Decision Package

M1 只要求 Owner 确定产品边界，具体 API、表结构和失败恢复由后续设计负责。

2026-08-11 的官方 API、官方产品说明、当前代码和 Binance 只读产品事实已经把
推荐方向收敛为：**继续使用 Binance USDⓈ-M，同一 Venue 下增加 TradFi Equity
Perpetual Product Family，不建设新 Venue Adapter，也不迁移现有 canonical
instrument identity。** 详细事实、Capability Matrix、候选池、Session、账户和
M2–M4 影响记录在
`docs/superpowers/specs/2026-08-11-binance-usdm-tradfi-perpetual-m1-decision.md`。

该记录当前为 `OWNER_ADOPTED / M2_M4_IMPLEMENTATION_AUTHORIZED`。M1 已完成，
M2–M4 进入本地实现；该状态不改变生产 Registry、PostgreSQL Universe、Owner Policy、
生产账户或真实 ENTRY 权限。

| 决策主题 | 初始推荐 | 本阶段不提前锁定的细节 |
| --- | --- | --- |
| **Venue** | `binance-usdm`；复用当前 CCXT/REST adapter | Product/Session port 和 API 参数 |
| **账户** | 同一 USDⓈ-M account、独立 RuntimeProfile；暂不增加子账户 | M6 真实资本和是否需要物理隔离 |
| **标的池** | AAPL、GOOGL、MSFT、NVDA、META、AMZN、TSLA、SNDK；QQQ/SPY 仅 reference | M4 是否使用 reference regime；M5 后是否替换成员 |
| **Session** | 全时段 Observation；首版仅 US Regular Session 允许 ENTRY | 具体日历表和时间分类实现 |
| **方向** | LONG、SHORT 都观察；M6 上线直接实盘，最终 Active Universe 与方向范围由部署包冻结 | 两侧成员是否分化 |
| **资本** | M1–M5 不增加真实资本；M6 完整复用 Policy v4，不设置 TradFi 独立单 Ticket 或账户参数 | 不扩大既有 Policy v4 边界 |
| **企业事件** | `blocked` 禁止新 ENTRY；M6 v1 对 `unavailable` 显式告警和冻结证据，不以其单独阻断 | 机构级数据供应源和未来硬门禁版本 |
| **产品异常** | 阻止新 ENTRY，既有 Ticket 继续保护、退出和对账 | Venue 特定错误码映射 |

## Frontend Product Boundary

现有 Owner Console 不重建。M2 在当前页面体系上增加两个产品入口：

1. **StrategyGroup 驾驶舱**
   - 当前 StrategyVersion、Event、RuntimeProfile 和 Venue；
   - Entry 状态、Active/Warming Universe；
   - Signal、Ticket、Review 和 Owner 变更记录；
   - 策略版本隔离后的收益和路径证据。
2. **标的中心**
   - Product、Session、Spread、Mark/Index、Earnings 和 Corporate Action 状态；
   - StrategyGroup/Event 归属；
   - Active/Warming Universe 成员；
   - 加入、移出和影响预览。

受控 Universe 操作遵循：

```text
Active Universe
-> 编辑成员
-> Diff 与影响预览
-> TOTP Owner 授权
-> 新 Warming Universe
-> Certification / Prewarm
-> 自动原子激活
```

前端继续采用手动刷新。只读请求必须有界、分页并优先读取当前投影；页面不得
通过加载完整历史来推导运行时状态。

## Owner Control Product Backlog

StrategyGroup 暂停/恢复、策略标的热加载和单 Ticket Owner 平仓是 Owner
控制面的起点，不是完整产品边界。后续能力必须服务单 Owner、小资金、可承受亏损的
右尾实验，不扩展为任意策略编辑或手工下单平台。

| 能力 | 稳定产品语义 | Owner 价值 | 状态 |
| --- | --- | --- | --- |
| StrategyGroup 暂停/恢复 | 只控制该 StrategyGroup 的新 ENTRY；已有 Ticket 继续保护、退出、结算和 Review | 快速隔离一个失效策略而不停止系统 | 已实现 |
| Effective Entry Scope | 聚合 Global Entry、Strategy Control、StrategyVersion、Active Universe、Product/Session、Readiness、Netting Domain 和 Policy Capacity，返回当前是否可创建 Ticket 及第一阻塞点 | 不再从多个页面和日志拼装“为什么没有交易” | 待设计实施 |
| Owner Regime Gate + Journal | 以 `BOTH`、`LONG_ONLY`、`SHORT_ONLY`、`FLAT` 限制新 ENTRY 的方向和允许 StrategyGroup；每次变更追加审计记录并带明确到期 | Owner 可以表达市场参与边界，而不指定一笔订单或破坏既有 Ticket 纪律 | 待设计实施 |
| 策略运行模式 | 明确区分 `live`、`observe_only`、`entry_paused` 和 `retired`；Worker active 不等于策略允许 ENTRY | 看清策略正在运行、观察、暂停还是已经退出产品线 | 待语义收敛 |
| Instrument 生命周期与 Universe 热加载 | 全局 Instrument Catalog 管理 Candidate、Certification、Eligible、Suspended、Retired；每个 EventSpec 独立拥有 StrategyUniverse，Warming 认证后原子激活 | 一个 Product 可被多个策略复用，而每个策略独立决定成员 | 已实现 Universe 基础能力；Catalog 新增和生命周期操作待完善 |
| Strategy-Instrument 临时禁入 | 独立暂停某个 StrategyGroup/EventSpec 与 Instrument 组合的新 ENTRY，不修改全局 Product，也不改写 Active Ticket | 在单一标的异常时避免暂停整个策略 | 待设计实施 |
| 单 Ticket Owner 平仓 | 前端选择一个活动 Ticket，经 Preview、TOTP 和持久化授权后复用正式 `request_exit()`、Lifecycle、Reconciliation、Settlement 和 Review；退出标记为 Owner 手动平仓 | 处理单笔风险而不影响其他 Ticket 和策略 | 待设计实施 |
| Owner 操作审计与异常收件箱 | 用 Owner 可读语义展示操作意图、范围、结果、Incident、未知 Command、保护缺失和身份漂移；不要求阅读原始日志 | 每天只处理需要行动的问题 | 待设计实施 |
| StrategyVersion 生命周期 | 区分候选、认证、当前、历史和退休版本；收益、Ticket 和 Review 按版本隔离，不原地修改活动版本 | 防止历史右尾掩盖当前版本表现 | 待设计实施 |
| Owner 注释与实验决策 | 机器交易事实保持不可变；Owner 以追加记录保存手动退出原因及 Continue、Observe、Pause、Retire 决策 | 把复盘结论沉淀为可追溯实验决策 | 待设计实施 |
| 策略参数解耦 | 使用类型化、不可变的参数版本；参数变化不得原地改变当前 StrategyVersion 或活动 Ticket，也不得成为任意 JSON 配置入口 | 后期减少代码部署，同时保留策略身份和证据边界 | 明确待办，当前暂缓 |

Instrument Catalog 与 StrategyUniverse 保持两层结构：标的先成为全局已知且已认证的
Product，再通过 EventSpec-to-Instrument 成员关系决定某个策略方向是否使用它。前端的
“热加载”表示无需重启 Worker 或重新部署代码；它不表示原地修改 Active Universe，
也不改写已存在的 Signal、Claim 或 Ticket。

单 Ticket Owner 平仓与后续 Entry 范围调整保持两个独立 Operation。手动平仓默认
不暂停 StrategyGroup、Strategy-Instrument 或 Global Entry；如果 Owner 希望避免
同一策略标的再次进入，应另行提交可审计的临时禁入或 Universe 变更。

## Owner Product Architecture

Owner Console 后续收敛为四个产品中心。页面只是呈现方式，稳定边界由 PostgreSQL
版本化权威和正式 Kernel 链路拥有。

| 产品中心 | 核心职责 | 明确边界 |
| --- | --- | --- |
| **策略中心** | 运行模式、当前版本、StrategyUniverse、Effective Entry Scope、版本隔离表现和实验决策 | 不在前端编写策略代码或任意 JSON 参数 |
| **标的中心** | Instrument Catalog、Product 认证、生命周期、Venue 事实和策略成员关系 | Product 全局唯一，是否交易由 EventSpec-to-Instrument 关系决定 |
| **Ticket / Review 中心** | 当前风险、保护状态、单 Ticket 平仓、K 线价格路径、Settlement、Review 和 Owner 注释 | 不直接编辑 Ticket、Command、成交或机器事实 |
| **运行与控制中心** | Global Entry、Owner Regime、Worker/Runtime Identity、Owner Operation、异常收件箱和发布准备度 | 不直接暴露任意 SQL、systemd 或 Exchange 写接口 |

前端负责表达和变更 Owner 意图；PostgreSQL 保存版本化权威与追加事实；四类 Worker
执行唯一正式链路；Ticket、Command、Settlement 和 Review 事实不得被 UI 原地改写。

## Post-M6 Engineering Priorities

优先级编号沿用阶段性复盘中的 Owner 语义。**P0 在后台等待市场，P2 的基础设施工作
先于 P1 产品增强实施**；编号不代表串行执行顺序。

| 轨道 | 目标 | 下一批工作 | 完成条件 |
| --- | --- | --- | --- |
| **P0：自然市场验收** | 关闭现有 Kernel 与 TradFi SOR 的真实生命周期证据 | 保持只读监控；自然 Signal 出现后观察 Admission、Ticket、保护、退出、Reconciliation、Settlement 和 Review；闭环后执行 `promote-full` 与最终需求审计 | 自然 TradFi Ticket 内外部完整闭环、零残留、零未解决 Incident，`promote-full` 和最终审计通过 |
| **P2：工程基础设施** | 降低每次开发、测试和部署的固定成本，并统一产品语义 | 测试资产治理；发布流程状态化和精确候选认证复用；Canonical Exit Attribution；Effective Entry Scope 投影/API | 日常开发使用 Focused/Fast 层；完整认证只对冻结候选运行一次；发布显示单一阶段和阻塞点；退出原因和 Entry 能力有唯一权威 |
| **P3-X：动态标的生产实验** | 把已通过 Replay 的 SOR 选择规则接入唯一 Instrument membership 与 time-bounded ENTRY authority，并以原风险小资金取得真实证据 | 已批准三 Plane设计与P3-X.3A Implementation Plan；DS-00至DS-08已经完成，现已具备Selection Runner、immutable Snapshot、Selection-Period`PRE_FENCE_CONTINUITY`、`NO_CHANGE/VALID_EMPTY`、durable Generation handoff、Entry Vacuum全边界negative fence、durable cancel/unknown recovery、合法双腿partial protection、通用Authority Gap Audit、trigger suppression、`first_eligible_close_time_ms`、串行warming、staged pair、原子切换、supersession、exact post-fence fallback、四个new-ENTRY边界birth Authority lineage、三个独立runtime loop/lease、Owner Pause闭环、bounded readonly和exact Release Compatibility Fact持久化；当前进入DS-09 exact candidate integrated certification | 设计状态`DESIGN_APPROVED`；计划状态`PLAN_APPROVED / CODE_AND_TEST_ONLY / DS-09`；Owner已授权DS-02至DS-10本地顺序实施，首次Dynamic Session仍须独立授权，且不提高风险或绕过Strategy Control |
| **P1：Owner 产品控制** | 让日常策略、标的和 Ticket 操作主要在前端完成 | 单 Ticket Owner 平仓；Owner Regime Gate + Journal；可读操作审计；策略运行模式；Instrument 生命周期；Strategy-Instrument 临时禁入；异常收件箱 | Owner 无需 SQL、SSH 或拼装日志即可完成日常范围控制、市场参与门控和单笔风险处置 |
| **P3：实验学习与扩展** | 把交易结果和 Owner 门控证据转化为版本隔离的策略决策，再决定新增策略 | 标准化 Performance Review Query；StrategyVersion 生命周期；Runner/右尾统计；P3-X 结论；Owner Regime 归因；Owner 注释；Continue/Observe/Pause/Retire 决策；类型化参数版本待办；后续 MPG/BRF2/RSRVCB 评估 | 当前版本证据、自然退出、Owner 干预和实验结果可区分，新增策略不复用未经验证的历史总收益 |
| **P4：资本治理** | 在充分证据后将实验收益转化为可控资本制度 | 风险档位资格、回撤降档建议、资本高水位和提款账本 | 仅输出资格与建议；每次风险档位变更仍须 Owner 明确授权的 Policy 发布，提款/转账仍不由系统执行 |

### Owner Regime And Performance Attribution

P1.2 先建立 Owner 对市场参与范围的可审计控制，P3 再评价它是否有价值。两者不能
倒置：没有事前 Journal，就无法可靠地区分 Owner 判断、策略本身和偶然市场路径。

| 结果类别 | 证据语义 | 是否计入真实净收益 |
| --- | --- | --- |
| Gate 内自然 Ticket | 真实成交、费用、资金费、退出和 Review 完整链路 | 是，按完整经济字段统计 |
| Gate 外 Signal 的 Shadow Outcome | 已冻结信号的有界 MFE/MAE 或路径证据 | 否，不是模拟成交或 PnL |
| “若未 Gate 会怎样”分析 | 依赖明确价格、成本和退出假设的模型估算 | 否，必须与真实结果分列 |

因此，P3 不把“全策略持续运行的收益”伪装为已知事实；它同时呈现 Gate 后实际收益、
Gate 外机会路径和明确标注假设的反事实模拟。Owner 判断的边际价值只能在这三类证据
分开的前提下评价。

### SOR Dynamic Selection Experiment

P3-X 已完成前两层研究，并把下一步收敛为生产实验链：

1. **Instrument Effect v1**：相同 Crypto SOR v4 在不同 Instrument 上存在历史差异，
   但静态 Symbol 排名无法样本外持续；
2. **Dynamic Selection V0 Replay**：`UTC 01:00` 事前 Selection 已通过全部冻结定量 Gate；
3. **Production design / Implementation Plan / certification**：生产设计与Implementation Plan
   已经批准；DS-00至DS-08已经完成并通过各自Focused/Fast/affected integration验证，当前Active Execution Scope为
   `DS-09`。实现为三个经PostgreSQL durable handoff解耦的Plane：Selection只提交
   Snapshot；Materializer独立拥有time-bounded Authority、Entry
   Vacuum、unfinished ENTRY drain、Desired generation、串行warming、通用Authority Gap Audit、
   双边原子切换和受限post-fence fallback；每个已处于Dynamic mode的Session都在Selection结果前
   建立`PRE_FENCE_CONTINUITY`并持续到Vacuum，late continuity/`NO_CHANGE`也必须审计Authority
   gap；Deployment独立恢复权威且不等待materialization；
4. **Small-capital activation**：Owner 单独授权，以当前 SOR 风险边界获取真实交易结果。

```text
Instrument Effect v1
-> reject static good-symbol list
-> Selection Thesis: Compression -> Expansion
-> Pre-trigger qualification + OR/ATR ranking
-> Historical Replay: Dynamic vs Static vs Random vs All Selection-ready / All Panel
-> Production detailed design
-> Golden parity + Migration/Release certification
-> separately approved small-capital Dynamic activation
```

V0 的 **Source Integrity** 要求24个Candidate的Point-in-Time窗口全部完整；任一Candidate
缺Kline或窗口不完整时整个attempt=`SOURCE_FAILED`，不允许Rank补位。Source完整后，
**Qualification** 才排除Activity不足、几何无效或产品不合格的标的，**Selection** 再按冻结
规则分配有限名额。Primary Feature 是 Opening Range 完成后、任何
Trigger 之前可知的 `OR Width / pre-session ATR14`。原研究中的 Trigger-time OR/ATR 只
作为支持假设的 Development Evidence，不能直接成为未来信息输入。

第一阶段使用固定 24-symbol Research Panel，但按每个 Session 的实际数据可用性形成
Point-in-Time Eligible Set。它是固定面板动态状态回放，不冒充历史全市场 Universe
Backtest。Current Static 7 是生产配置基线，Random Selection-ready 7 判断“选 7 个”本身是否
足够，All Selection-ready 表达通过最低资格后的机会供给，All Panel Diagnostic 记录固定
面板的完整机会供给，Near/Not Selected 用于衡量梯度与 Opportunity Loss。零 Trigger
Session 必须进入分母。

Historical Replay 只产生研究证据；当前生产设计新增 PostgreSQL Schema、new-ENTRY
authority和FinalGate验证，但不强制新增第五个systemd Worker、不改变Alpha或资本边界，也不
自行恢复Crypto `SOR-001`。Selection Runner、Materialization Coordinator和Observation Runner
必须具有独立application entry point和DB lease，即使V0暂时托管于现有进程。Owner冻结的
unfinished ENTRY撤销和真空partial-retained规则会窄幅扩展Ticket lineage、durable cancel
Command和Lifecycle reducer；actual quantity只有能形成正数量TP1+Runner时才保留，否则
controlled flatten。所有未连续覆盖eligible close的Authority都必须在grant前完成durable Gap
Audit；Vacuum activation/fallback审计`previous ∪ desired`，late continuity/普通`NO_CHANGE`
审计current pair。没有suppression row只有在audit COMPLETE时才表示已检查无trigger；Authority
以`first_eligible_close_time_ms`形成不相交的audit/Observation close边界。
固定 24-member Candidate Panel 直接读取 Binance public market data，不进入
StrategyUniverse；Snapshot 的 `Ready=1..7` 全部成为Desired members，`Ready=0`记录
`VALID_EMPTY`并保持无新增交易。相同集合走`NO_CHANGE`；变化集合先打开Entry Vacuum并
drain旧ENTRY。LONG/SHORT复用global queue串行warming，在两侧staged后原子切换；每个已处于
Dynamic mode的Selection Period在`D 01:00`先建立`PRE_FENCE_CONTINUITY`，previous pair持续到普通`NO_CHANGE`替换
或Vacuum commit，Selection失败只追加reason且不记fallback。Vacuum后失败只有完成drain与union
audit并通过其余fallback gates才恢复previous pair。Pause Resume同成员必须解析Pause Vacuum后
写新`NO_CHANGE`。Desired target不包含Universe ID且不复制Dynamic selected members；actual
Universe创建transaction直接写唯一Generation FK。Universe digest保持membership-only；首次
Static-to-Dynamic失败保持Static authority/mode；release compatibility只是既有
certification manifest的薄投影，发布仍区分`COMPATIBLE_RESTART`与
`REQUIRES_RUNTIME_REMATERIALIZATION`。CPM/BRF2只在SOR V0
证明通用 Selection primitive 值得复制后进入研究；MPG/MI 仍需先分离 ComparisonUniverse。

### Immediate Execution Order

P2.1–P2.4 的工程基础设施能力已经完成。本节从当前第一个未完成事项开始排序：

1. **P3-X.3A DS-00 Golden/Evidence/Test Portfolio**：**已完成**。已冻结961×24 member-level
   Decimal Golden、输入/源码/规则digest和Focused/Fast/Release测试组合；Artifact仅用于测试，
   `src/trading_kernel/**`零依赖。Decimal Golden已批准为DS-03/DS-09唯一Selection parity baseline；
   DS-01已完成并通过Codex定向审查。Owner已授权DS-02至DS-10整个本地开发、测试和认证流程，
   DS-02已经通过本地Migration/Schema/Repository验收；DS-03 SelectionCore/Runner已完成961×24 Golden parity与本地PostgreSQL验收；DS-04已完成continuity、Disposition、Vacuum intent、Generation handoff与Gap Audit；DS-05已完成Admission/Ticket/dispatch Vacuum enforcement、durable cancel、unknown recovery、retained partial和`VALID_EMPTY`原子闭环并通过228项focused和916项Fast验证；DS-06已完成串行warming、staged无Signal authority、双边原子切换、Static/Dynamic fallback、supersession、Owner Pause precedence及terminal Authority幂等恢复；DS-07已完成Observation/Signal/Admission/Ticket/dispatch四边界Authority enforcement、compatible successor lineage、terminal Vacuum blocker和existing lifecycle隔离；DS-08已完成independent runtime hosting/recovery、Reconciliation Vacuum facts、Owner Pause、bounded readonly和exact Release Compatibility Fact持久化，当前Active Execution Scope为`DS-09`；生产Migration、部署和首次Dynamic activation仍无授权。
2. **P3-X.3B Implementation/Certification**：DS-00至DS-08已经完成；当前执行DS-09
   Decimal Golden、Migration、full-chain fault、architecture和exact release candidate certification；
   规则修改创建V1，不原地重写V0。
3. **P1.1 单 Ticket Owner 平仓**：补齐持久化授权、Operation、正式 `request_exit()`
   调用、进度投影、Review 归因和前端 Preview/TOTP；不建立第二退出路径。
4. **P1.2 Owner Regime Gate + Journal**：在 Global Entry 之下、正式 Admission 之前
   增加方向和 StrategyGroup 范围的 Gate；冻结 Journal、到期语义、审计投影和
   Admission blocker，不引入手工下单或 Ticket 参数修改。
5. **P1.3 Owner 控制面补齐**：依次完成运行模式、Instrument 生命周期、
   Strategy-Instrument 临时禁入、可读审计和异常收件箱。
6. **P3-X.4 Small-capital Activation**：仅在 exact release、Schema、24 Candidate operational
   audit、Owner Strategy Control 和 exchange readonly gates 全部通过后，由 Owner 单独授权
   首个 Dynamic Session；不提高 Policy v4 风险。
7. **P3 实验学习**：并行完善标准化 Performance Review Query、版本隔离的 Runner/
    右尾统计、Owner Regime 归因、Owner 注释、实验决策和类型化参数版本。
8. **P4 资本治理**：只在 P3 的版本隔离经济证据充分后设计风险阶梯、回撤降档和
   资本提取账本；不自动加风险，不执行提现或转账。

## Runtime And Resource Boundary

1. 当前 **2C4G** 服务器仍使用四类常驻 Worker，不新增每个资产或策略一套服务；SOR Dynamic
   V0 的Selection/Materialization/Observation是三个独立逻辑组件和lease，但不强制第五个
   systemd Worker；
2. 一般首期 Universe 维持有界小集合；SOR Dynamic V0 明确为 `1..7` 个标的，保持在当前
   1–10 成员边界内；
3. 15m 策略按闭合 K 线增量运行，不在每次 cadence 重拉完整历史窗口；
4. Depth、Mark/Index 和高成本事实只在有界候选范围获取；
5. 新 RuntimeProfile 在 M1–M5 本地候选保持 ENTRY 禁用；M6 首次生产 R4 认证后不等待
   Observation 样本，通过 StrategyGroup resume 直接开放小额 ENTRY；
6. 新 Schema 只能走停止、空仓、前向、历史保留的 migration；
7. 新 Venue 必须复用 durable Exchange Command、unknown outcome、partial fill、
   reconciliation 和 controlled exit 语义；
8. 任意新 ENTRY 冻结不得停止既有 Ticket 的保护、退出、对账、结算和 Review。
9. P3-X 的Selection Runner、Materialization Coordinator、Observation Runner分别拥有独立
   application entry point和DB lease；V0可托管于现有Observation/Reconciliation process，但
   禁止同一call stack跨组件保存进度。Reconciliation Worker仍拥有Desired Universe
   certification；不强制第五个Worker、不新增全市场扫描服务或文件型Runtime authority。每
   Session只处理固定24 members × 96 closed 15m bars。
10. P3-X 的 Strategy Entry Vacuum 只阻断新 Admission/Ticket/ENTRY dispatch；已有Position的
    Stop、TP1、Runner、Exit、Settlement和Review继续。真空partial-retained仅允许合法TP1+
    Runner双腿，普通partial fill和无法双腿物化的actual fill仍执行既有controlled flatten。
11. P3-X发布区分`COMPATIBLE_RESTART`与`REQUIRES_RUNTIME_REMATERIALIZATION`；Software
    Deployment完成不等待Dynamic Universe materialization，pending Generation由后台恢复；
    compatibility fact仅为现有Release Certification manifest的薄投影，不建设第二release
    engine、classifier或deployment orchestrator。

## Explicit Non-Goals

当前路线图不包含：

- 建设独立因子库产品；
- 建设综合 Fit Score、AI 选币、机器学习平台、通用因子编辑器或完整 Selector；
- 把 Minimal Historical SOR Replay 扩张为历史数据平台、Point-in-time Universe、
  全市场常驻 Collector、Research Service、复杂特征 ETL 或 Research Registry 系统；
- 同时铺开 SOR、CPM、BRF2、MPG 和 MI 的标的研究；
- 把单次历史结果、主观解释或 Owner 点击确认冒充未来统计证明或真实净收益；
- 让本地 Parquet、CSV、缓存、Notebook 输出或研究报告成为生产运行时权威；
- 把研究 Path R、MFE/MAE 或反事实模型称为真实 PnL；
- 把主观先验概率、固定 Event 数或单次历史回放设为生产解锁门槛；
- 由 AI、文件产物或绕过 PostgreSQL Generation/StrategyUniverse 的路径修改 Active
  Universe、恢复 StrategyGroup 或获得 ENTRY 权限；
- 仅凭 Selector 历史结果恢复加密 `SOR-001`；
- 自动扩大资本、止损风险、杠杆或并发容量；
- 自动执行风险档位提升、回撤降档、提现或转账；
- 立即恢复加密 `SOR-001`；
- 将多个 StrategyVersion 合并后决定当前版本能力；
- 直接合并旧 US-equity 分支；
- 建立第二套美股订单或生命周期系统；
- 以 M5 样本量、观察天数或人工收益判断作为 M6 实盘解锁门槛；
- 在 M6 稳定前启动 M7 实施；
- 由本规划文件授权生产部署或交易所写入。
- 为追求速度而取消 Runtime Identity、Unknown Outcome、Partial Fill、
  Reconciliation 或 Schema Preservation 边界；
- 让普通发布自动触发 Controlled Flatten；
- 引入新旧 Kernel 混合运行、活动持仓蓝绿交接或 Kubernetes。

## Follow-Up Design Records

每个阶段开始前再形成与该阶段匹配的具体设计，不在本路线图提前冻结：

1. M0.5：分级发布、Owner API 独立 Release、自然空仓 Cutover、阶段耗时和
   失败恢复设计；
2. M1：`docs/superpowers/specs/2026-08-11-binance-usdm-tradfi-perpetual-m1-decision.md`
   记录 Venue/Product/Account Capability Matrix 与待 Owner 采纳的推荐；
3. M2：Owner Console Instrument Center 与 Universe Control 设计；
4. M3：保持 canonical Instrument ID 的 RuntimeProfile、Product Profile、当前
   Venue capability、Session/Corporate Action 架构设计和前向 migration 计划；
5. M4：`SOR-US-EQ-PERP-001` 策略语义、退出政策和 Live/Replay 验收矩阵；
6. M5：Observation 指标、证据窗口和 go/hold/stop 判定合同；
7. M6：`docs/superpowers/specs/2026-08-12-tradfi-sor-m6-live-entry-design.md`
   记录上线即小额实盘、StrategyGroup pause、统一 Policy 账户容量和联合 R4 部署边界；
8. M7：旧 RSRVCB 设计的可移植模块审计与当前内核重写计划。
9. P1.2：Owner Regime Gate、Journal、有效范围投影、Admission blocker、TOTP 与
   失败恢复设计；不包含手工下单、Ticket 参数编辑或 Policy 风险扩张。
10. P3-X 概览：
    `docs/superpowers/specs/2026-08-18-eventspec-instrument-fit-research-overview.md`
    记录 Instrument Effect v1 结论、Dynamic Selection 阶段边界与后续分叉。
11. P3-X 详细设计：
    `docs/superpowers/specs/2026-08-20-sor-dynamic-selection-research-v0-design.md`
    冻结 Selection Clock、Candidate Panel、Feature、资格、排名、对照、指标、判定规则、
    输出和必要测试；该 Historical Replay 已完成，原 `ADVANCE_TO_FORWARD_SHADOW` 只保留
    为研究原始判定。
12. P3-X 被淘汰路线：
    `docs/superpowers/specs/2026-08-20-sor-dynamic-selection-forward-shadow-design.md`
    已标记 `SUPERSEDED`，不授权 W30/W60、外部 evidence store 或实现。
13. P3-X 生产详细设计：
    `docs/superpowers/specs/2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md`
    记录Selection/Runtime Materialization/Deployment三Plane、独立DB handoff/lease、generic
    Selection facts、SelectionSessionAuthority、`1..7` Desired members、
    `PRE_FENCE_CONTINUITY/VALID_EMPTY/NO_CHANGE/SUPERSEDED`、Strategy Entry Vacuum、
    unfinished ENTRY drain、通用Authority Gap Audit与`first_eligible_close_time_ms`、Pause Resume、
    双腿partial-retained保护、serial warming、atomic pair switch、唯一Generation→Universe linkage、
    first Static-to-Dynamic特例、post-fence`FALLBACK_PREVIOUS`、thin release compatibility projection、Migration、
    rollback和测试矩阵。
14. P3-X 实施计划：
    `docs/superpowers/plans/2026-08-23-sor-dynamic-instrument-selection-trading-v0-implementation-plan.md`
    将批准设计拆成DS-00至DS-10顺序Task、RED测试、文件边界、认证和生产硬停止；计划已批准，
    DS-00与DS-01已完成；Owner已授权DS-02至DS-10按Task Card验收顺序自动推进。该授权不包含
    生产Migration执行、Tokyo部署、Crypto SOR resume或首次Dynamic activation。
15. P3：统一绩效查询契约、版本隔离、Runner/右尾指标、Owner Gate 实际归因与
    假设性反事实呈现边界。
16. P4：风险阶梯资格、回撤降档、资本高水位和提款账本设计；任何 Policy 修改或
    资金划转均保持独立 Owner 授权与发布边界。

任何阶段的实现、迁移和部署状态仍由当前代码、PostgreSQL、Venue 事实和
`MAIN_CONTROL_ROADMAP.md` 记录，本路线图不自行宣告阶段完成。
