# P0-W3 Stage-Aware PG Truth And Remaining Event Certification

Status: approved for implementation  
Date: 2026-07-10  
Owner decision: combine PG truth/verification closure with Wave 3 SOR and BRF2 event certification

## Objective

Close one problem class across runtime projections, database bootstrap, tests,
and the remaining observe-only StrategyGroup events:

```text
event capability
-> pre-trade readiness
-> fresh live signal
-> promotion and allocation
-> one action-time lane
-> Action-Time Ticket
-> FinalGate
-> Operation Layer
-> protected submit
```

The result must preserve PG as the sole runtime truth and must not introduce a
JSON/Markdown runtime authority path.

## Verified Starting State

Tokyo is deployed at migration 109 and release
`9fef2d8bc219e94ece46722bca7fcfbb58c14908`.

- `CPM-LONG v2`, `MPG-LONG v2`, and `MI-LONG v2` are current trial-grade,
  trial-live eligible events.
- `SOR-LONG v1`, `SOR-SHORT v1`, and `BRF2-SHORT v1` are current observe-only
  events with execution eligibility disabled.
- The eleven SOR/BRF2 candidate rows are incorrectly classified as
  `action_time_boundary_not_reproduced` before a fresh signal or executable
  event exists.
- That early blocker makes the global Goal Status report `missing_fact` even
  though the three executable StrategyGroups are correctly waiting for market.
- Several action-time tests build migration-086/103 schemas without migration
  104 execution-eligibility columns.
- Migrations 107-109 are immutable deployed semantic migrations that require
  the deterministic strategy registry seed to exist before they run.
- The current SOR runtime evaluator is a one-hour short-only reference while
  the PG event contract is a fifteen-minute, side-specific long/short contract.
  The standalone SOR detector expresses the intended fifteen-minute rules but
  is not the canonical runtime evaluator.
- BRF2 routes through a BRF reference evaluator whose successful output remains
  observe-only and does not yet publish the exact BRF2 RequiredFacts manifest.

## Architecture Decision

### 1. Add an explicit pre-execution capability stage

Introduce the blocker class:

```text
event_execution_capability_not_certified
```

It means the current Event Spec is observe-only or its evaluator cannot produce
the declared execution grade/mode. It is earlier than action-time and must never
be mapped to `action_time_boundary_not_reproduced`.

The stage order is:

```text
observe_only_event
-> event_execution_capability_certified
-> market_wait_validated or computed_not_satisfied
-> fresh_signal
-> promotion
-> action_time
```

`action_time_boundary_not_reproduced` remains valid only after a fresh eligible
signal exists and cannot reach a non-executing action-time rehearsal object.

### 2. Separate per-event tradeability from global runtime health

Candidate Pool and Tradeability Decision retain
`event_execution_capability_not_certified` on observe-only lanes.

Global Goal Status does not treat observe-only capability work as a runtime
fact outage when at least one executable lane is healthy. It continues to show
healthy market waiting for the executable pool while preserving the SOR/BRF2
engineering blocker in per-StrategyGroup views.

This removes the current eleven-row false `missing_fact` result without hiding
the Wave 3 work.

### 3. Make one runtime evaluator own SOR semantics

Replace the split SOR meaning with one pure domain evaluator used by the
runtime signal evaluation service and by any read-only diagnostic wrapper.

The evaluator has two independent fifteen-minute events:

| Event | Trigger | Protection reference | Required facts |
| --- | --- | --- | --- |
| `SOR-LONG` | closed 15m break above UTC session opening range with follow-through | opening-range low | `opening_range_defined`, `breakout_confirmed`, `opening_range_low_reference` |
| `SOR-SHORT` | closed 15m break below UTC session opening range with follow-through | opening-range high | `opening_range_defined`, `breakdown_confirmed`, `opening_range_high_reference` |

Only a valid `WOULD_ENTER` output carries `trial_grade_signal` and `trial_live`.
No-action and invalid outputs remain observe-only. Generic SOR signals and side
mirroring are forbidden.

The existing standalone SOR script must consume the same pure evaluator or be
reduced to an archive/manual diagnostic wrapper; it must not remain a second
runtime rule authority.

### 4. Certify BRF2 through an event-specific wrapper

BRF2 remains short-only. The wrapper may reuse the pure BRF price-action
calculation but must translate its successful result into the BRF2 contract:

- `rally_failure_confirmed=true`;
- `short_side_not_disabled=true`;
- `rally_high_reference` exists;
- `strong_uptrend_disable=false` is explicit and fresh.

Missing or unknown disable state fails closed. Only an exact BRF2 short
`WOULD_ENTER` output carries trial grade/mode.

### 5. Version StrategyGroup semantics atomically

Use forward-only migrations after 109:

- one SOR v2 migration creates one group version and both side-specific v2
  Event Specs, RequiredFacts, execution policies, and active bindings;
- one BRF2 v2 migration creates the short-only v2 Event Spec, RequiredFacts,
  execution policy, and bindings;
- v1 event specs become retired and v1 bindings become revoked only after all
  v2 rows are present;
- downgrade is blocked when v2 signal lineage exists.

Applied migrations 107-109 are not rewritten.

### 6. Define the canonical fresh-database bootstrap

Historical semantic migrations require deterministic strategy rows, so the
supported fresh installation sequence is explicit and tested:

```text
alembic upgrade 106
-> seed_runtime_control_state_foundation
-> alembic upgrade head
```

Production upgrades continue directly from their current migration head. A
single bootstrap entrypoint owns this sequence; callers must not reproduce it
ad hoc.

### 7. Consolidate test schema setup

Create one test-support schema installer that applies the runtime-control
foundation and required forward migrations in a deterministic order. Existing
action-time tests use it instead of carrying partial local migration stacks.

The helper replaces duplicated fixture setup; it is test-only and cannot become
a production state source.

## Data Flow

```text
closed market candles
-> pure event evaluator
-> event-specific fact observations
-> runtime active observation monitor
-> active PG Event Spec capability resolution
-> PG live signal event
-> Candidate Pool readiness
-> promotion/allocation
-> action-time materializers
```

The active PG Event Spec and evaluator output must agree on signal grade and
execution mode. StrategyGroup identity alone never grants permission.

## Error Handling

- Observe-only Event Spec: classify
  `event_execution_capability_not_certified`; do not create a live-submit
  promotion.
- Evaluator/Event Spec grade mismatch: fail closed as execution-eligibility
  authority invalid.
- Missing SOR side-specific facts: invalid/no-action, never generic promotion.
- Missing BRF2 disable fact: fail closed with exact disable-fact blocker.
- Multiple active event bindings for one candidate scope: fail closed as
  ambiguous binding.
- Fresh signal without action-time materialization: only then classify
  `action_time_boundary_not_reproduced`.

## Test Strategy

Use strict red-green TDD for each behavior change.

1. Blocker classification tests distinguish observe-only capability from
   action-time failure.
2. Goal Status tests prove eleven observe-only rows do not poison executable
   healthy waiting.
3. SOR evaluator tests cover long, short, no-action, stale input, side identity,
   15m time authority, protection refs, and fact observations.
4. BRF2 tests cover confirmed short, active disable, missing disable, unknown
   disable, and rally-high reference.
5. Migration tests prove atomic v1 retirement/v2 activation, exact binding
   counts, downgrade safety, and no side expansion.
6. Canonical fixture tests prove migration-104 columns exist in all action-time
   suites.
7. Bootstrap tests prove the supported fresh sequence and production-head
   forward upgrade.
8. Non-executing full-chain tests prove each v2 event can reach a ticket-bound
   disabled-smoke boundary without exchange write.
9. File-I/O audit must report zero suspicious production authority and zero
   frequent report writers.

## Performance And Cadence

| Dimension | Decision |
| --- | --- |
| Cadence | Event evaluation stays on the existing watcher tick; action-time builders run only after PG trigger state exists |
| No-signal file writes | `0` JSON/MD files |
| PG writes | Existing bounded fact/coverage rows per candidate; signal lineage only on fresh events |
| CPU | SOR/BRF2 evaluators use bounded closed-candle windows; no heavy report builders on tick |
| Timeout | Existing watcher and exchange/API timeout boundaries remain unchanged |
| Disk | No new recurring files or sidecars |
| Retention | Existing PG retention policy; design and plan documents are repository provenance only |

## Authority Boundary

This design does not change Owner capital, leverage, notional, attempt cap,
runtime profile, credentials, or symbol scope. It does not authorize replay or
synthetic signals as live signals. It does not bypass FinalGate, Operation
Layer, protection, reconciliation, or duplicate-submit controls.

## Rollback

- Code rollback restores the previous projector/evaluator implementation.
- Semantic migration downgrade is allowed only when no v2 live signal lineage
  exists.
- If deployed acceptance fails before v2 signal creation, revoke v2 bindings,
  restore v1 observe-only rows, and keep the watcher read-only for the affected
  StrategyGroup.
- No destructive PG cleanup is part of this task.

## Live Enablement Transition

```text
Before:
SOR-001 and BRF2-001 -> observe-only -> falsely action-time blocked

After:
SOR-001 and BRF2-001 -> exact event capability decision
  -> certified v2 events: market_wait_validated / computed_not_satisfied
  -> uncertified events: event_execution_capability_not_certified
```

## Stop Conditions

Stop implementation if any of these becomes necessary:

- Owner capital/profile/symbol-side scope expansion;
- strategy threshold tuning beyond the already registered event semantics;
- rewriting applied migrations 107-109;
- live exchange write for testing;
- new JSON/Markdown runtime authority or recurring report cadence.

No such uncertainty is present at design completion.
