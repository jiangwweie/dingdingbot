# BRC Current Documentation

Status: current Trading Kernel authority index

## 首尔 App 人工接管产品线

本目录属于 **`manual-dev` / `final-manual`** 的首尔独立产品。
**默认自动执行初始止损、TP1、Runner；识别到有效 App 人工干预后，整笔 Ticket 永久接管**。
接管后保留交易所已有订单，程序只读对账、核算风险和完成账务，不能自动纠正人工退出。
同标的跨多空仅允许一个非终态 Ticket；Tokyo `dev` 的产品语义不随本分支改变。

### 需求、实现与当前证据

| 入口 | 文档职责 | 证据边界 |
| --- | --- | --- |
| [Owner 决策](superpowers/specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md) | 冻结已同意的人工干预、残单、风险和隔离规则 | 不是当前生产授权或部署证书 |
| [详细设计](superpowers/specs/2026-11-06-app-manual-takeover-v1-detailed-design.md) | 状态与证据、统一写门、人工只读生命周期 | 起始缺口属于设计时基线，不是当前缺陷清单 |
| [实施计划](superpowers/plans/2026-11-06-app-manual-takeover-v1-implementation-plan.md) | 任务拆分、失败测试与验证步骤 | 历史阶段不恢复为新的审批要求 |
| [运行模型](current/OWNER_RUNTIME_OPERATING_MODEL.md) | Owner 控制台与币安 App 的不同职责 | 不把全局 ENTRY 暂停当成单笔接管 |
| [正式路线图](current/MAIN_CONTROL_ROADMAP.md) | 当前生产身份、Owner 状态和验收进展 | 本分支当前状态的唯一文档入口 |

代码已包含管理观察、干预识别、人工仓只读收尾、风险占用、跨方向禁入及通知路径。
软件认证与首尔安装记录、当前启用状态统一见路线图。真实 App 行为与自然投递仍依赖直接业务证据，不能用模拟测试宣称完成。
[M0记录](superpowers/plans/2026-11-06-app-manual-takeover-v1-protocol-evidence.md)及
[前置交付](superpowers/plans/2026-11-07-app-manual-takeover-prevalidation-handoff.md)是历史阶段记录。
[通知方案](superpowers/plans/2026-11-09-manual-notification-templates-v1.md)说明最终快照和可靠投递边界。

## 两条产品线与正式发布

[固定工作区规则](superpowers/plans/2026-11-08-two-product-workspaces.md)定义人工 `manual-dev` 与自动 `dev` 的隔离。
通用修复经独立审查后选择性移植，不整分支自动合并；数据库、活动 Ticket、授权、账户和证书不能互相复制。
[首尔安装方案](superpowers/plans/2026-11-08-manual-new-host-installation.md)与
[验证准备记录](superpowers/plans/2026-11-08-manual-validation-release-preparation.md)给出对应工具与阶段证据。
继承的 `TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` 提供共用发布安全基线，不授权对 Tokyo 操作；人工环境使用正式独立安装入口。

## Code-Based Learning Guide

[项目知识地图](knowledge/README.md) provides a Chinese reading path through the
actual Kernel, transaction boundaries, dynamic selection, Owner controls, risk,
data model and deployment recovery, with code and test references. It is an
explanatory knowledge base, not an addition to the current authority set or a
production-state source.

## Current Authority Set

| Document | Responsibility |
| --- | --- |
| `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` | Source classes, authority order, and document fact ownership |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner policy and supervision boundary |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | Agent implementation and safety constraints |
| `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md` | Approved target architecture and invariants |
| `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md` | Implementation stages and acceptance checklist |
| `docs/current/MULTI_ASSET_STRATEGYGROUP_ROADMAP.md` | Multi-asset StrategyGroup product stages, dependencies, workload envelope, and decision gates |
| `docs/current/MAIN_CONTROL_ROADMAP.md` | Sole current production identity, measured state, and critical path |
| `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` | Regular release, recovery, and resource contract |
| `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Product objective, experiment-capital premise, and order-capable profile |
| `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` | Active StrategyGroup and event semantics |
| `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` | Strategy experiment evaluation |
| `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md` | Strategy-to-kernel intake boundary |
| `docs/current/TRADEABILITY_DECISION_CONTRACT.md` | Current can-trade decision |
| `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` | Exact blocker vocabulary |

Only these files may exist under `docs/current`. Historical documents are not
current instructions and must not be wired into production runtime decisions.

Volatile production facts belong only in `MAIN_CONTROL_ROADMAP.md`. Entry,
architecture, implementation, and deployment documents link to that snapshot
instead of copying its commit, tag, certification count, Ticket identity, or
transient stage.

The P0 rebuild documents own the completed implementation baseline, stable
kernel invariants, and remaining acceptance checklist. Completed repair task
cards are historical material outside `docs/current`; their stable scheduling,
certification, promotion, deployment, migration, and capacity semantics are
consolidated into the P0 design, experiment profile, and deployment contract.

The multi-asset roadmap owns the stable expansion sequence only. Venue facts,
Universe membership, capital authority, implementation status, and deployment
state continue to come from code, PostgreSQL, exchange facts, and
`MAIN_CONTROL_ROADMAP.md`.

## Owner Dynamic Risk Budget

[Owner 动态风险预算 V1 设计](superpowers/specs/2026-10-29-owner-dynamic-risk-budget-v1-design.md)
and its [执行计划](superpowers/plans/2026-10-29-owner-dynamic-risk-budget-v1-implementation-plan.md)
define the Owner-controlled baseline and linked total/directional limits.
First installation retains 2%; later changes are explicit Owner actions.
The Owner authorized implementation and deployment. Exact production identity,
release verification and current ENTRY posture belong only to
[MAIN_CONTROL_ROADMAP.md](current/MAIN_CONTROL_ROADMAP.md).

## Release Experience Reference

[BRC joint-release retrospective](releases/2026-10-15-brc-joint-release-retrospective.md)
records the code defects, process omissions and legitimate waits from the joint
release. It provides a minimal future R3/R4 reference checklist and prioritizes
complete writer inventory and readonly preflight. It is a one-time experience
record, not current runtime authority or a new engineering program; the
[deployment contract](current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md) remains the
procedure authority. Current work ordering belongs to the
[main roadmap](current/MAIN_CONTROL_ROADMAP.md).

## Generic Selection Implementation And Evidence

[Generic Multi-Strategy Dynamic Selection V1 detailed design](superpowers/specs/2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md)
is the approved frozen design/provenance record, not a current execution-status
source. The
[Implementation Plan](superpowers/plans/2026-09-06-generic-multi-strategy-dynamic-selection-v1-implementation-plan.md)
records the approved implementation and historical task evidence. Generic
runtime, Owner controls and Capacity B have release-certified implementation;
long soak, offline projector and complete GS-13 acceptance are not claimed PASS.
Live deployment, Resume and per-strategy activation facts belong exclusively to
`docs/current/MAIN_CONTROL_ROADMAP.md`. The
[research overview](superpowers/specs/2026-08-18-eventspec-instrument-fit-research-overview.md)
records the evidence boundary and provenance amendment. These design/research
documents do not extend the `docs/current` runtime-authority allowlist.

## Alpha Research Delivery And Planning

[多策略真实收益归因 V1 工程推进方案](superpowers/plans/2026-10-29-multi-strategy-attribution-v1-implementation-plan.md)
defines the bounded offline delivery sequence: frozen inputs, contribution and
cost attribution, Ticket explanations, portfolio context and reproducible
acceptance. Active progress belongs to the
[main roadmap](current/MAIN_CONTROL_ROADMAP.md); research artifacts stay in the
separate strategy-research workspace. The plan does not authorize runtime or
strategy changes.

[BRC-ALPHA delivery record and prospective research boundaries](superpowers/plans/2026-10-14-brc-alpha-research-status-and-plan.md)
records the Owner-reported offline ALPHA-01 delivery and the earlier three-stage
direction: SOR-1H release/natural evidence, generic ALPHA-02 path Observation,
then evidence-driven iteration. It is dated provenance, not current work
ordering or a new deployment instruction. ALPHA-01 receipt and independent
reproduction remain separate from later runtime capabilities; exact delivered
state and remaining acceptance belong to the main roadmap. Economic
interpretation remains owned by the Strategy Experiment Evaluation Contract.

[Reconciliation Reliability Repair design](superpowers/specs/2026-10-14-reconciliation-reliability-repair-design.md)
records the earlier Owner-required joint repair gate for SOR-1H release.
Current implementation and certification evidence belongs to the main roadmap.

[Tokyo resource and capacity assessment](superpowers/plans/2026-10-15-tokyo-resource-capacity-assessment.md)
records the dated readonly baseline before ALPHA-02: host and worker resource
headroom, PostgreSQL size, Observation/Shadow scheduling costs, and bounded
workload scenarios. It is a one-time assessment, not current runtime authority,
a peak-load certification, or authorization to optimize or upgrade production.

## Owner Directional Risk V1 Design

[Owner 方向风险偏好 V1 设计](superpowers/specs/2026-10-25-owner-directional-risk-v1-design.md)
records the Owner-approved product baseline and engineering proposals for
bullish/neutral/bearish Crypto new-ENTRY risk preferences.
[实施计划](superpowers/plans/2026-10-25-owner-directional-risk-v1-implementation-plan.md)
orders concurrency proof, persisted authority, Capacity, dispatch recovery,
Owner Console V2 and evidence work. Local implementation exists; release
certification, production installation and activation are separately evidenced.
The existing experiment profile owns the approved numerical matrix; production
identity and activation remain solely with the main control roadmap. These
records do not add a new runtime authority or replace existing acceptance gates.

## Version Nodes

Project releases under `docs/releases/` are immutable publication notes, not
runtime authority. `release-YYYY.MM.DD.N` tags identify published `main` nodes;
`tokyo-runtime-YYYY.MM.DD.N` tags identify deployed code. Historical decisions
and superseded measured snapshots live outside `docs/current`.
