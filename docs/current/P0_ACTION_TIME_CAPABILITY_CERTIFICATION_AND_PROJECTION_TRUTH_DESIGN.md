---
title: P0_ACTION_TIME_CAPABILITY_CERTIFICATION_AND_PROJECTION_TRUTH_DESIGN
status: APPROVED_FOR_IMPLEMENTATION
authority: docs/current/P0_ACTION_TIME_CAPABILITY_CERTIFICATION_AND_PROJECTION_TRUTH_DESIGN.md
last_verified: 2026-07-12
---

# P0 Action-Time Capability Certification And Projection Truth Design

## Decision

The next medium-scale program is:

```text
P0-AT Action-Time Capability Certification And Projection Truth
```

The program turns the already test-proven production-shaped Action-Time path
into one release-bound PG certification fact, then makes Candidate Pool,
Tradeability Decision, Daily Table, Goal Status, and Server Monitor consume the
same capability truth and preserve the same first blocker.

It does not change strategy semantics, Owner policy, dynamic sizing, runtime
scope, FinalGate, Operation Layer, or exchange-write authority.

## Current Defect

The current code has two incompatible meanings for `action_time_path_ready`:

| Surface | Current meaning | Failure |
| --- | --- | --- |
| Production-shaped test matrix | Current evaluator and materializers can traverse raw facts through Ticket, Runtime Safety State, FinalGate handoff, Operation Layer handoff, and disabled smoke | Proof is not represented as current release capability |
| Action-Time current row | A current fresh signal already has private Action-Time facts or an open lane | Correct event-state fact, but false during ordinary no-signal observation |
| Tradeability static inference | EventSpec, RequiredFacts, policy, and runtime binding are structurally eligible | Does not prove the deployed release passed the production-shaped chain |
| Daily Table | Treats absent private Action-Time facts as missing path capability | False `action_time_boundary_not_reproduced` during no-signal state |
| Goal Status | Ignores Daily Table's failed checklist and trusts Candidate Pool market wait | Cross-projection disagreement |

The core modeling error is mixing **current event readiness** with **deployed
engineering capability**.

## Options

| Option | Benefit | Cost / risk | Decision |
| --- | --- | --- | --- |
| Patch Goal Status to copy Daily Table | Small change | Preserves the false capability conclusion and duplicated logic | Rejected |
| Add a new capability-certification table | Explicit schema | Adds another truth owner and migration for semantics already supported by process outcomes | Rejected |
| Reuse `brc_runtime_process_outcomes` and one shared reducer | Release-bound, bounded, PG-backed, invalidatable, no second truth | Requires a deploy certification step and projection integration | **Selected** |

## State Model

### Event Readiness

Current event readiness answers whether one current fresh event has the live
facts needed to advance now:

```text
fresh signal
+ public facts
+ private Action-Time facts
+ account/open-order/position facts
+ lane state
```

It may be false during a healthy no-signal period and must not by itself imply
an engineering blocker.

### Capability Certification

Capability certification answers whether the currently deployed release can
process a future eligible event for one lane. Its identity binds:

```text
runtime_head
+ candidate_scope_id
+ strategy_group_version_id
+ event_spec_id + event_spec_version_id
+ sorted RequiredFacts contract identity
+ runtime_scope_binding_id
+ owner_policy_version_id
+ runtime_profile_id
```

The stable identity is hashed into `source_watermark`. The current row uses:

```text
process_name = action_time_capability_certification
scope_key = lane:<StrategyGroup>:<symbol>:<side>
process_state = succeeded
runtime_head = exact deployed commit
source_watermark = action_time_capability:<sha256>
```

Because `brc_runtime_process_outcomes` upserts by `process_name + scope_key`,
recertification remains one bounded row per lane instead of append-only tick
growth.

### Canonical Truth

One pure reducer returns per lane:

```text
certified
first_blocker
runtime_head_matches
lineage_matches
certification_ref
source_watermark
```

Certification is current only when the latest successful server-monitor
runtime head and every bound identity still match. A missing or stale
certification produces `action_time_boundary_not_reproduced`.

## Certification Workflow

```text
run 22-scope production-shaped disabled-smoke matrix
-> verify zero exchange write and one Ticket/Runtime Safety path per scope
-> deploy exact commit
-> read PG current registry/policy/runtime bindings
-> write/update 22 release-bound capability process outcomes
-> republish Candidate Pool, Daily Table, Goal Status
-> require first-blocker consistency
```

The production-shaped matrix uses in-memory/temporary test state and cannot
grant runtime authority. The PG certification command cannot create a signal,
promotion, lane, Ticket, Runtime Safety State, FinalGate pass, Operation Layer
handoff, exchange command, order, or policy change.

## Projection Rules

1. Candidate Pool owns the per-lane capability annotation and first blocker.
2. Tradeability Decision uses the shared reducer, not a private static copy.
3. Daily Table distinguishes `event_ready_now` from `capability_certified`.
4. Goal Status derives non-market blockers from canonical Candidate Pool rows.
5. The current projection publisher fails closed before persistence when the
   same lane has conflicting first blockers across Candidate Pool, Daily Table,
   and Goal Status.
6. Server Monitor treats projection inconsistency or stale capability
   certification as engineering work, not market wait and not a service crash.

`market_wait_validated` requires current capability certification plus the
existing admission, scope, policy, detector, watcher, fact, classification, and
fresh-signal-absent checks.

## Failure Handling

| Failure | Result |
| --- | --- |
| 22-scope production-shaped matrix fails | No certification write; deploy is not accepted for market-wait classification |
| Runtime head missing or changed | Certification stale; `action_time_boundary_not_reproduced` |
| EventSpec/RequiredFacts/policy/binding changed | Lineage hash mismatch; recertification required |
| A lane cannot build a complete identity | Exact identity blocker; no partial certification |
| Projection blockers disagree | Publisher fails closed before replacing current snapshots |
| Certification command fails mid-run | Transaction rollback; prior certification remains but becomes stale on head mismatch |

## Cadence And Performance

| Dimension | Boundary |
| --- | --- |
| Certification cadence | Deploy/postdeploy or bound identity version change only |
| No-signal cadence | Pure bounded read of at most 22 current certification rows |
| PG growth | One upserted process-outcome row per active lane; no per-tick growth |
| Files | Zero JSON/MD/report writes |
| CPU-heavy work | 22-scope matrix is explicit deploy/test work, never watcher cadence |
| Network | No exchange call; database calls remain transaction-bounded |
| Timeout | Deploy/test command remains externally timeout-bounded |
| Retention | Superseded identity is overwritten in current process outcome; git/test history preserves provenance |

## Acceptance

1. All 22 active scopes have one current capability identity.
2. The production-shaped matrix reaches disabled smoke for all six EventSpecs
   and all 22 scopes with zero exchange write.
3. A matching deployed head and lineage produce `certified=true`.
4. Head or lineage drift produces `action_time_boundary_not_reproduced`.
5. Candidate Pool, Tradeability, Daily Table, Goal Status, and Server Monitor
   preserve one first blocker.
6. `market_wait_validated` is impossible without current capability
   certification.
7. No runtime file authority, new projection table, live-profile/sizing change,
   synthetic production authority, or exchange write is introduced.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001 / MPG-001 / MI-001 / SOR-001 / BRF2-001
symbol: 22 active candidate scopes
stage: test_proven_but_not_release_certified
first_blocker: action_time_boundary_not_reproduced
evidence: 22-scope matrix passes locally while PG/current has no release-bound capability certification and current projections disagree
next_action: implement release-bound certification plus shared projection truth
stop_condition: 22 current lanes are certified for the deployed head and all current projections conserve one blocker
owner_action_required: no
authority_boundary: no strategy/policy/risk/scope/FinalGate/Operation Layer/exchange-write expansion
```
