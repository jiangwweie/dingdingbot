# BRC Current Documentation

Status: current Trading Kernel authority index

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

[BRC-ALPHA delivery record and prospective research boundaries](superpowers/plans/2026-10-14-brc-alpha-research-status-and-plan.md)
records the Owner-reported offline ALPHA-01 delivery and the approved three-stage
direction: SOR-1H release/natural evidence, generic ALPHA-02 path Observation,
then evidence-driven iteration. ALPHA-02 design can proceed in parallel with
natural evidence accumulation; implementation is not claimed.
Repository receipt, independent reproduction and runtime integration are not
claimed. Research does not authorize strategy changes; SOR-1H deployment uses
the explicit Owner flatness-contingent authorization recorded in that plan,
and does not close deferred engineering acceptance. Economic interpretation
remains owned by the Strategy Experiment Evaluation Contract.

## Version Nodes

Project releases under `docs/releases/` are immutable publication notes, not
runtime authority. `release-YYYY.MM.DD.N` tags identify published `main` nodes;
`tokyo-runtime-YYYY.MM.DD.N` tags identify deployed code. Historical decisions
and superseded measured snapshots live outside `docs/current`.
