# Executable Event Contract And CPM-LONG v2 Design

> **Status:** Owner-approved direction; implementation may proceed after design self-review

## Purpose

This design closes the gap between a StrategyGroup event meaning and a signal
that may legally enter the trial-live chain. It does not rewrite all active
strategies. It introduces one reusable fact-truth boundary and certifies one
event, `CPM-LONG v2`, as the first trial-grade event.

The target transition is:

```text
CPM-LONG v1 observe-only history
-> explicit evaluator fact observations
-> versioned CPM-LONG v2 trial-grade declaration
-> eligible live signal only when exact event facts are observed
-> existing promotion / single-lane / ticket / safety chain
```

Deployment and real exchange action are outside this implementation batch.

## Current Evidence

Tokyo PG preserves real historical evidence that CPM and SOR reached deep
pre-submit states before execution eligibility became first-class. For example,
CPM/SOL reached ticket, Runtime Safety, and disabled-smoke without exchange
write. Migration 104 subsequently backfilled those historical rows to
`observe_only_signal`, `observe_only`, and `execution_eligible=false`.

The strategy events did not suddenly become invalid. The old chain was missing
an authority conjunct. Current Event Specs correctly fail closed.

The cross-strategy audit also found a fact-truth defect in
`src/application/action_time/fact_snapshots.py`: a missing observed fact may be
replaced by its contract `expected_value`, and `expr_ref` may become `True`
without an observation. Expected values are comparison targets, not market
facts.

## Event Selection

The first trial-grade event is selected by semantic distance, not roadmap rank.

| Event | Current evidence | Gap | Decision |
| --- | --- | --- | --- |
| `CPM-LONG` | Dedicated 1h/4h evaluator, explicit reclaim evidence and pullback-low reference, real signal/ticket/smoke history | Fact keys are not emitted as typed observations; Event Spec remains observe-only | **Certify first** |
| `SOR-SHORT` | Real signal/lane/ticket history | Event Spec is 15m while the shared evaluator prefers a 1h window; facts partly depend on reason-code inference | Keep observe-only |
| `MPG-LONG` | Dedicated evaluator and candidate semantics | `leader_strength_confirmed` is required but not actually computed | Keep observe-only |

This choice does not change CPM thresholds, candidate symbols, notional,
leverage, profile, or protection policy.

## Alternatives

### Option A: Flip The Existing CPM v1 Eligibility Fields

Rejected. It rewrites historical meaning and still permits fabricated facts.

### Option B: Add A Separate Certification Table Or JSON Packet

Rejected. Event Spec, RequiredFacts, PG fact snapshots, and the existing
Execution Eligibility Envelope are already the core abstractions. A parallel
certificate would become a second authority source.

### Option C: Extend The Existing Event Contract And Create CPM v2

Recommended. Add typed evaluator fact observations, remove expected-as-observed
fallback, version the StrategyGroup/Event Spec/RequiredFacts rows, and reuse the
existing authority envelope from signal through protected submit.

## Core Invariants

### Expected Is Not Observed

```text
expected_value = contract comparison target
observed_value = value emitted by evaluator or trusted fact source
```

Missing observed values remain missing. Neither `expected_value` nor
`operator=expr_ref` may synthesize satisfaction.

### Signal Is Not An Order

Trial-grade only permits a signal to enter the existing promotion chain.
`not_order=true` and `not_execution_intent=true` remain mandatory. Ticket,
FinalGate, Operation Layer, protection, account, position/open-order, budget,
and duplicate-submit gates remain independent.

### Versioned Promotion

CPM v1 remains observe-only historical authority. Promotion creates new rows:

```text
strategy_group_version = sgv:CPM-RO-001:v2
event_spec_id = event_spec:CPM-RO-001:CPM-LONG:v2
event_spec_version = v2
required_facts_version_id = rf:event_spec:CPM-RO-001:CPM-LONG:v2:v2
declared_signal_grade = trial_grade_signal
declared_required_execution_mode = trial_live
execution_eligibility_enabled = true
```

Future CPM signals bind v2. Existing signals, promotions, lanes, tickets,
safety snapshots, and attempts retain v1 history and remain ineligible.

## Typed Fact Observation Contract

Add a pure domain value object:

```text
StrategyFactObservation
  fact_key
  observed_value
  observed_at_ms
  valid_until_ms
  source_ref
```

Add `fact_observations: list[StrategyFactObservation]` to
`StrategyFamilySignalOutput`. It is strategy evidence, not execution intent.

For a CPM long `WOULD_ENTER`, the evaluator must emit exactly:

| Fact | Observed value | Source |
| --- | --- | --- |
| `htf_trend_intact` | `true` | evaluated 4h trend state |
| `reclaim_confirmed` | `true` | evaluated closed 1h reclaim condition |
| `pullback_low_reference` | positive Decimal | evaluated pullback lookback low |

The observation time is the trigger candle close. Validity is bounded by the
Event Spec freshness window. A missing or non-positive protection reference
prevents a trial-grade output.

CPM short output remains observe-only because the current registry and runtime
scope are long-only.

## Fact Materialization

Action-time fact materialization consumes typed observations from the PG signal
payload and trusted public facts. Resolution order is:

```text
typed fact observation
-> exact trusted public fact value
-> explicitly supported deterministic reference alias
-> missing
```

Delete these generic fallbacks:

```text
missing -> expected_value
expr_ref -> true
```

SOR reason-code derivation may remain temporarily for observe-only evidence,
but it cannot become execution eligible and is a later SOR certification target.

## Seed And Migration

Migration 107 is a bounded data-version migration. It does not call runtime or
the exchange.

It must:

1. Preserve `sgv:CPM-RO-001:v1` and CPM Event Spec v1 as historical rows.
2. Create CPM StrategyGroup version v2 by copying stable thesis/risk fields and
   recording execution-semantic certification provenance.
3. Create CPM Event Spec v2 with trial-grade/trial-live declaration.
4. Create v2 RequiredFacts rows for the same three canonical fact keys.
5. Create a v2 execution policy by copying the current CPM policy semantics.
6. Supersede v1 current rows only after every v2 row is complete.
7. Replace active CPM candidate-event bindings with v2 bindings in one
   transaction.
8. Update the StrategyGroup current version pointer to v2.
9. Leave all non-CPM StrategyGroups and all Owner policy/capital/profile rows
   unchanged.

The foundation seed becomes version-aware so a fresh database produces the same
CPM v2 state while other events remain v1 observe-only.

## Runtime Flow

```text
closed 1h/4h market input
-> CPM evaluator
-> CPM long WOULD_ENTER + typed facts + trial-grade request
-> current CPM v2 Event Spec authority resolution
-> PG live signal with execution_eligible=true
-> fact snapshot from observed facts only
-> per-symbol readiness
-> promotion arbitration
-> at most one real-submit candidate lane
-> Action-Time Ticket and existing hard gates
```

No fresh signal means no promotion and no new action-time lane.

## Failure Semantics

| Failure | Result |
| --- | --- |
| Required typed fact missing | `fact_missing` / non-market engineering blocker |
| Observed boolean false | `computed_not_satisfied` |
| Protection reference missing or non-positive | `fact_missing`; no trial-grade signal |
| Evaluator trial-grade exceeds Event Spec | schema/authority rejection; no signal progression |
| v1 signal reused against v2 | authority lineage mismatch |
| Short CPM signal | observe-only evidence; no promotion |
| Replay or synthetic signal | non-executing rehearsal only |

## Scope And WIP

This is one mainline task, not five strategy rewrites:

```text
P0 Executable Event Contract Truth + CPM-LONG v2
```

It may change the shared fact contract and CPM only. SOR, MPG, MI, and BRF2
remain observed and ineligible. Candidate coverage remains four CPM symbols,
with one action-time lane maximum.

## Test Strategy

Required RED/GREEN coverage:

1. Missing observed fact cannot be satisfied by `expected_value`.
2. `expr_ref` without an observation remains missing.
3. CPM long WOULD_ENTER emits trial-grade plus all three typed facts.
4. CPM short evidence remains observe-only.
5. Missing/non-positive pullback reference prevents trial-grade output.
6. Migration and fresh seed produce CPM v2 and preserve v1 history.
7. Other five Event Specs remain observe-only.
8. Watcher writes an eligible CPM signal only under CPM v2 exact authority.
9. Fact materialization writes satisfied CPM facts from explicit observations.
10. Forged/mismatched v1/v2 authority fails before promotion/ticket.
11. Non-executing full-chain CPM fixture reaches ticket/safety with no exchange
    write.

Focused suites run first. The existing P0 vertical regression and production
file-I/O validators run before completion. A repository-wide suite is not
required unless focused changes reveal unrelated failures.

## Cadence And Performance

| Dimension | Impact |
| --- | --- |
| Cadence | Constant-time validation per detected CPM event |
| No-signal files | `0` JSON/MD files |
| PG writes | No new recurring table; existing signal/fact rows only when an event exists |
| CPU | Three typed fact validations and existing authority comparisons |
| Heavy replay | Explicit local/test certification only, never production cadence |
| Disk | No sidecar, report, JSONL, or current artifact writer |
| Timeout | No new subprocess, HTTP, or exchange call |
| Retention | Existing PG signal/fact retention rules |

## Rollback

Code/schema rollback must not restore v1 as trial-grade or restore fabricated
facts.

Allowed rollback:

```text
disable CPM v2 eligibility
stop new CPM promotion
invalidate unsubmitted v2 promotions/lanes/tickets through official state changes
restore CPM v1 as current observe-only
forward-fix code while keeping migration columns/data
```

If a v2 ticket has already submitted, reconciliation and lifecycle closure run
before any policy/version rollback. No row deletion or file fallback is used.

## Acceptance And Stop Condition

The implementation is complete when:

1. Contract expected values can no longer fabricate observed facts.
2. CPM long is the only active trial-grade Event Spec.
3. All four CPM candidates consume the same v2 semantics without per-symbol
   code forks.
4. A real live CPM signal can become eligible only with three explicit facts.
5. Missing, false, stale, wrong-side, wrong-version, replay, and synthetic paths
   cannot gain exchange-write authority.
6. Existing ticket, FinalGate, Operation Layer, protection, budget, position,
   and reconciliation gates remain unchanged.
7. No exchange call, live profile change, sizing change, or production deploy is
   performed by this implementation batch.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001
symbol: ETHUSDT,SOLUSDT,AVAXUSDT,SUIUSDT
stage: observe_only_event_semantics
first_blocker: CPM facts are not carried as explicit observed facts and CPM-LONG is not a versioned trial-grade Event Spec
evidence: Tokyo historical CPM signals reached ticket/safety/smoke without execution eligibility; current v1 Event Spec is observe-only
next_action: implement typed fact truth, migration 107, and CPM-LONG v2 trial-grade authority under TDD
stop_condition: CPM v2 signals require explicit facts and may reach non-executing ticket/safety while every ineligible or mismatched path fails closed
owner_action_required: no; Owner approved the architecture direction and local implementation
authority_boundary: no production deploy, no exchange write, no FinalGate or Operation Layer bypass, no profile/sizing mutation
```
