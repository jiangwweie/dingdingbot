# BRC Current Documentation

Status: current Trading Kernel authority index

## Independent App Manual Takeover Product Line

[App 人工接管 V1 沟通结论](superpowers/specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)
records Owner-approved requirements for the separate `codex/app-manual-takeover-v1`
product branch and a new isolated server/account. Default TP1/Runner automation
is retained; confirmed external intervention transfers the whole trade permanently
to manual management. This is an agreed target, not implemented or deployed
behavior, and does not change Tokyo or extend the current authority allowlist.

The [detailed design](superpowers/specs/2026-11-06-app-manual-takeover-v1-detailed-design.md)
defines management authority, external-order evidence, readonly manual lifecycle
and account admission. The [implementation plan](superpowers/plans/2026-11-06-app-manual-takeover-v1-implementation-plan.md)
maps these requirements to ordered tasks, failure tests, certification and new
environment acceptance. Both are design proposals; implementation has not started.

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
