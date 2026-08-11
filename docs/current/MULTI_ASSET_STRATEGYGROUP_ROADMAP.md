---
title: MULTI_ASSET_STRATEGYGROUP_ROADMAP
status: CURRENT_PLAN
program_id: MASG-P1
last_verified: 2026-08-11
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

## Authority Boundary

本文件只拥有 **M0–M7（含 M0.5）的稳定阶段顺序、目标、依赖、工作量区间和阶段门**。
它不拥有以下易变或运行时事实：

| 信息 | 唯一权威 |
| --- | --- |
| 当前生产 Commit、Schema、服务、Ticket、持仓、订单和剩余阻塞 | `MAIN_CONTROL_ROADMAP.md` 与行动时直接事实 |
| 当前 StrategyGroup、Event 和版本语义 | Strategy Registry |
| 当前 Universe 成员、Warming、Certification 和 Active 指针 | PostgreSQL StrategyUniverse |
| 当前资本、容量、风险和允许范围 | Owner Policy 与实验 Profile |
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
| **M3：跨资产运行底座** | 当前 Kernel 能表达目标 Venue/Product | 通用 Instrument Identity、Venue Adapter、RuntimeProfile、Product、Session、Corporate Action | 新 Profile 可完成只读认证和 Observation，且现有加密 Profile 无行为漂移 |
| **M4：美股 SOR** | 新 StrategyGroup 可以自然产生标准 Signal | 美股 Opening Range、LONG/SHORT Event、Market Plan、Exit Policy、版本身份 | `SOR-US-EQ-PERP-001` 在 Entry 禁用状态完成 Live/Replay 一致的 Observation |
| **M5：Observation/Shadow** | 获得产品微观结构和策略路径证据 | Spread、Depth、Slippage、Opening Range、TP1、MAE、失败退出、Session 分布 | 完成约定市场日窗口并形成独立的继续、修改或停止结论 |
| **M6：小规模实盘闭环** | 完成受控真实资金自然 Ticket | 独立 Owner Policy、ENTRY 准入、保护、退出、结算、Review | 自然 Ticket 完整闭环，交易所与 PostgreSQL 无残留或未解决 Incident |
| **M7：第二策略族** | 评估当前内核上的 `RSRVCB-001` | 按当前 Schema/Policy 重写可复用领域模块 | 仅在美股产品底座和 SOR 闭环稳定后进入实施 |

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
| **M5** | 4–8 天开发 | 另加 4–8 周观察 | 自然市场日和有效 Observation 数量 | 极低 |
| **M6** | 2–5 天开发 | 样本等待约 4–12 周 | 信号频率和自然 Ticket 生命周期 | 高但有界 |
| **M7** | 15–25 天 | 3–5 周 | 旧设计向当前 Schema/Policy 的重写范围 | 中 |

M0.5 全部完成后，如果目标产品可以继续使用当前 Venue，预计约 **7–10 周净开发时间**
进入 Observation；如果必须接入全新 Venue，预计约 **10–14 周净开发时间**
进入 Observation。M1 的只读研究可以在 M0.5 期间交错进行；M2 的只读信息架构
可以在 M1 后开始，受控 Universe 操作则依赖 M3 的正式后端契约。

## M0.5 Release Model

M0.5 只确认发布分级和安全边界，具体脚本、路径、服务单元、认证 Manifest 和
恢复行为由后续专项设计决定。在该设计部署完成前，当前
`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` 仍是唯一有效生产流程。

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
             M5: Observation / Shadow
              ↓
             M6: 小规模实盘
              ↓
             M7: RSRVCB-001
```

M0 是当前既有程序的收尾，不应被新的产品设计长期拖延。M0.5 优先解决后续
频繁前端、API 和 Kernel 迭代的发布成本；M1 的只读调研可与其交错，但 M2–M4
的实施不应继续扩大现有发布耦合。M1 是 M3 和 M4 的前置决策；M2A 可以先行，
但 M2B 不得在后端版本、事务和审计语义未确定时通过前端直接修改运行时表。

## M1 Owner Decision Package

M1 只要求 Owner 确定产品边界，具体 API、表结构和失败恢复由后续设计负责。

| 决策主题 | 初始推荐 | 本阶段不提前锁定的细节 |
| --- | --- | --- |
| **Venue** | 优先验证当前 Venue；能力不足时再接新 Venue | Adapter 类、API 参数和部署单元 |
| **账户** | 同一 Kernel、独立 RuntimeProfile；条件允许时使用独立账户或子账户 | 账户凭据和具体资本值 |
| **标的池** | 首批 5–8 个候选，全部以行动时官方产品事实为准 | AAPL、SNDK、GOOGL 等具体成员是否最终纳入 |
| **Session** | 全时段 Observation；首版仅 US Regular Session 允许 ENTRY | 具体日历表和时间分类实现 |
| **方向** | LONG、SHORT 都观察，M6 时分别批准实盘 | 两侧是否使用相同 Universe |
| **资本** | M1–M5 不增加真实资本；M6 单独批准小规模边界 | 风险比例、并发容量和保证金值 |
| **企业事件** | 数据缺失、过期或冲突时禁止新 ENTRY | 数据供应源和冻结窗口参数 |
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

## Runtime And Resource Boundary

1. 当前 **2C4G** 服务器仍使用四类常驻 Worker，不新增每个资产或策略一套服务；
2. 首期 Universe 限制为 5–8 个标的，保持在当前 1–10 成员边界内；
3. 15m 策略按闭合 K 线增量运行，不在每次 cadence 重拉完整历史窗口；
4. Depth、Mark/Index 和高成本事实只在有界候选范围获取；
5. 新 RuntimeProfile 在 M5 前保持 ENTRY 禁用；
6. 新 Schema 只能走停止、空仓、前向、历史保留的 migration；
7. 新 Venue 必须复用 durable Exchange Command、unknown outcome、partial fill、
   reconciliation 和 controlled exit 语义；
8. 任意新 ENTRY 冻结不得停止既有 Ticket 的保护、退出、对账、结算和 Review。

## Explicit Non-Goals

当前路线图不包含：

- 建设独立因子库产品；
- 自动扩大资本、止损风险、杠杆或并发容量；
- 立即恢复加密 `SOR-001`；
- 将多个 StrategyVersion 合并后决定当前版本能力；
- 直接合并旧 US-equity 分支；
- 建立第二套美股订单或生命周期系统；
- 在 M5 证据完成前开放美股永续真实 ENTRY；
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
2. M1：Venue/Product/Account Capability Matrix 与 Owner Decision Record；
3. M2：Owner Console Instrument Center 与 Universe Control 设计；
4. M3：Instrument、RuntimeProfile、Venue Adapter、Product/Session/Corporate
   Action 架构设计和前向 migration 计划；
5. M4：`SOR-US-EQ-PERP-001` 策略语义、退出政策和 Live/Replay 验收矩阵；
6. M5：Observation 指标、证据窗口和 go/hold/stop 判定合同；
7. M6：独立资本政策、受控实盘和自然 Ticket 验收计划；
8. M7：旧 RSRVCB 设计的可移植模块审计与当前内核重写计划。

任何阶段的实现、迁移和部署状态仍由当前代码、PostgreSQL、Venue 事实和
`MAIN_CONTROL_ROADMAP.md` 记录，本路线图不自行宣告阶段完成。
