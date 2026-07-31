---
title: PROJECT_INFORMATION_ARCHITECTURE
status: CURRENT
last_verified: 2026-07-31
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
| PostgreSQL Current | Runtime scope, facts, readiness, Tickets, aggregates, commands, positions, incidents, monitor state | Historical document interpretation |
| PostgreSQL Events | Append-only policy, signal, lifecycle, command, and review lineage | Mutable current projection |
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

## Current Runtime Authority

The only production execution package is `src/trading_kernel`. Schema authority
is one unbranched forward Alembic chain:

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
```

`0001` is a frozen historical schema snapshot; current runtime metadata owns
the single head. The exact flat `0001 -> 0002` operation preserves certified
terminal history through the migration, but no runtime reads the old schema,
performs dual writes, or falls back to `0001`. The deployed schema identity
remains a volatile fact owned only by `MAIN_CONTROL_ROADMAP.md`.

Strategy semantics live in the Registry, while concrete instrument membership,
certification, warming, current activation, and frozen Signal/Ticket lineage
live in PostgreSQL StrategyUniverse projections. Repository Markdown and CLI
output are never runtime authority.

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
