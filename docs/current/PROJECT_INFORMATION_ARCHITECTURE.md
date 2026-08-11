---
title: PROJECT_INFORMATION_ARCHITECTURE
status: CURRENT
last_verified: 2026-08-11
---

# Project Information Architecture

## Authority

```text
Owner explicit decision
-> current tracked code and git state
-> current PostgreSQL and exchange facts
-> current documents
-> historical material only for explicit recovery
```

## Source Classes

| Source | Owns | Must not own |
| --- | --- | --- |
| Strategy Registry | StrategyGroup, event, side, and version semantics | Current order authority |
| Owner Policy | Enabled scope, capital, profile, and capacity | Signal truth or exchange outcome |
| PostgreSQL Current | Runtime scope, facts, readiness, Exposure Episodes, AdmissionDecisions, Shadow Outcomes, Tickets, aggregates, commands, positions, incidents, monitor state | Historical document interpretation |
| PostgreSQL Events | Append-only policy, signal, admission, lifecycle, command, and review lineage | Mutable current projection |
| Exchange Readonly Facts | External account, order, position, and fill truth | Internal policy |
| Documents | Architecture, contracts, and operating rules | Runtime decisions |
| Generated Output | Human display and bounded diagnostics | Any production authority |

## Document Fact Ownership

Documents are separated by subject and volatility. A fact has one canonical
owner; other documents summarize stable meaning and link to that owner.

| Information | Canonical owner | Volatility | Other documents |
| --- | --- | --- | --- |
| Product objective and experiment-capital premise | `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Low | Summarize without redefining |
| Strategy right-tail evaluation | `STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` | Medium | Link to the evaluation contract |
| Target architecture and invariants | `P0_TRADING_KERNEL_REBUILD_DESIGN.md` | Low | Reuse the canonical chain only |
| Implementation stages and acceptance checklist | `P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md` | Medium | Do not treat as runtime state |
| Multi-asset StrategyGroup program stages, dependencies, and workload envelope | `MULTI_ASSET_STRATEGYGROUP_ROADMAP.md` | Medium | Defer implementation details and current runtime state |
| Current commit, tag, certification, runtime state, and blockers | `MAIN_CONTROL_ROADMAP.md` | High | Link; never copy current values |
| Deployment procedure and resource limits | `TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` | Medium | Do not copy current runtime values |
| Entry navigation | repository `README.md` and `docs/README.md` | Low | Stay short and point to owners |

`MAIN_CONTROL_ROADMAP.md` is the only document that records volatile production
identity and measured runtime snapshots. Stable documents must not embed a
production SHA, dated production tag, exact test count, Ticket ID, or transient
acceptance-stage name.

The P0 rebuild documents own the completed implementation baseline and the
remaining acceptance checklist. Stable scheduling, certification, Entry
promotion, deployment recovery, migration, and capacity semantics are already
consolidated into the P0 design, experiment profile, and deployment contract.
Completed repair task cards are historical material and must not return to
`docs/current` as a second authority.

`MULTI_ASSET_STRATEGYGROUP_ROADMAP.md` owns only the stable M0-M7 program shape
for product expansion. It does not own current Venue products, production
identity, current Universe members, capital policy, implementation status, or
deployment authority. Those facts remain with their existing canonical sources.

## Current Runtime Authority

The only production execution package is `src/trading_kernel`. Schema authority
is one unbranched forward Alembic chain:

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
-> 0003_portfolio_admission_observability
-> 0004_owner_control_plane
-> 0005_tradfi_instrument_center
```

`0001` is a frozen historical schema snapshot. `0002 -> 0003` is a stopped,
flat, forward-only preservation-gated upgrade; it retains certified terminal
lineage while adding Episode, AdmissionDecision, Shadow Outcome, Policy v4,
and Exposure Family authority. `0003 -> 0004` is another stopped, flat,
forward-only upgrade that adds explicit StrategyGroup ENTRY controls, Owner
authorizations, and durable flatten-all Operation projections without changing
Ticket or exchange-command semantics. No runtime reads an old schema, performs dual
writes, falls back, downgrades, or hands active exposure between schemas. The
deployed schema identity remains a volatile fact owned only by
`MAIN_CONTROL_ROADMAP.md`.

`0004 -> 0005` is the stopped, flat, forward-only Product Authority upgrade.
It preserves the existing Crypto Registry, Owner Policy versions, Strategy
Controls, terminal lineage and StrategyUniverse rows, then adds Product
Compatibility, the bounded Instrument Center projections and the independent
observation-only `SOR-US-EQ-PERP-001` authority. The main Crypto Policy never
inherits TradFi Events; TradFi ENTRY remains disabled and its Strategy Control
starts paused.

Strategy semantics live in the Registry, while concrete instrument membership,
certification, warming, current activation, and frozen Signal/Ticket lineage
live in PostgreSQL StrategyUniverse projections. Repository Markdown and CLI
output are never runtime authority.

An Exposure Episode identifies one continuous eligible structure and may own at
most one Ticket. Every final admission result is an immutable
`AdmissionDecision`: an admitted Decision freezes its Claim and Ticket lineage;
a rejected Decision freezes the first blocker and creates no command. A
`Shadow Outcome` is Signal-owned, bounded, read-only market-path evidence. Its
source is either an eligible portfolio rejection or a strategy observation
whose Entry Admission is intentionally not run. It cannot create a Ticket,
reserve capital, dispatch a command, or write to a venue.

Production runtime must not depend on repository Markdown, generated JSON,
report directories, local caches, or archived database rows. Current state is
read by exact key from PostgreSQL and reconciled against exchange facts.

## Retention

- Current projections are upserted.
- Trade Events, Exchange Commands, and Trade Review revisions are append-only;
  the Aggregate owns the current effective Review pointer.
- Ticket Owner state uses the canonical `owner:ticket:<ticket_id>` projection;
  readonly access never materializes or refreshes it.
- Healthy no-signal and reconciliation ticks do not create report files.
- Manual exports are bounded, display-only, and disposable.
- Retired program generations are deleted rather than preserved as current
  compatibility surfaces.
