---
title: P1_OPPORTUNITY_FEEDBACK_CALIBRATION_DESIGN
status: IN_PROGRESS_DEPLOYMENT_AND_HISTORICAL_CALIBRATION
authority: docs/current/P1_OPPORTUNITY_FEEDBACK_CALIBRATION_DESIGN.md
last_verified: 2026-07-12
---

# P1 Opportunity Feedback Calibration Design

## Decision

The next bounded medium-scale program is:

```text
P1-OFC Strategy Opportunity And Live Feedback Calibration
```

P1-OFC uses the current production Event Spec and runtime evaluator semantics as
a fixed baseline. It measures opportunity supply, near misses, and replay/live
parity, then emits non-authority engineering or strategy-review proposals. It
must not automatically mutate strategy semantics, Owner policy, candidate
scope, risk, leverage, FinalGate, Operation Layer, or exchange-write authority.

The Owner-selected mode is **evidence-to-decision**:

```text
fixed production semantics
-> replay/live evaluated observations
-> typed opportunity calibration
-> exact engineering mismatch or review proposal
-> Owner policy change only after separate confirmation
```

## Why This Program Exists

The deployed runtime is currently `market_wait_validated`: five active
StrategyGroups and 22 scopes have no known non-market pre-submit blocker, while
there is no current fresh signal or Ticket. A low-frequency system cannot use
the absence of recent orders as proof that the market supplied no opportunity.

P1-OFC must distinguish:

| Condition | Meaning | Next owner |
| --- | --- | --- |
| `market_opportunity_absent` | Current production semantics ran and no eligible event occurred | Market |
| `computed_near_miss` | The evaluator ran, but named facts were false | Strategy review |
| `replay_live_parity_gap` | Same versioned observation produces different result or facts | Engineering |
| `live_coverage_gap` | Production did not evaluate the comparable scope/time identity | Engineering/runtime |
| `strategy_revision_proposal` | Current semantics are internally consistent but produce evidence worth revising | Owner/strategy review |

## Options Considered

| Option | Result | Decision |
| --- | --- | --- |
| Pure diagnostics | Produces frequency tables but may stop at explanation | Rejected |
| Evidence-to-decision | Produces exact repair actions or bounded review proposals without automatic mutation | **Selected** |
| Automatic tuning | Changes thresholds or scopes from replay results | Rejected until reliable live samples exist |

## Chain Position

```text
chain_position: replay_live_parity
strategy_group_id: CPM-RO-001 / MPG-001 / MI-001 / SOR-001 / BRF2-001
symbol: current 22 candidate scopes
stage: market_wait_validated_and_live_outcome_uncalibrated
first_blocker: natural_fresh_eligible_signal_absent_for_live_calibration
evidence: Tokyo release 2df39c1c; active Ticket=0; latest monitor quiet; blocker_classes=[none]
next_action: calibrate opportunity frequency and parity without modifying live authority
stop_condition: six Event Specs have typed frequency/near-miss/parity results and post-trade economics can consume real ticket facts
owner_action_required: no for calibration; yes only for a later semantic/scope/policy mutation
authority_boundary: replay cannot create live signal, Ticket, FinalGate, Operation Layer, or exchange write
```

## Scope

### Included

- current five StrategyGroups;
- current six Event Specs;
- current 22 candidate scopes;
- 90-day and 365-day calibration windows;
- exact evaluated result counts;
- per-fact near-miss counts;
- replay/live parity by versioned observation identity;
- evidence-to-decision proposals;
- ticket-bound actual funding ingestion;
- ticket-bound exit slippage using the actual exit order reference;
- regression, authority, cadence, and file-I/O validation.

### Excluded

- new StrategyGroups;
- unsupported side mirroring;
- automatic threshold tuning;
- automatic symbol-scope expansion;
- automatic Owner policy events;
- capital allocation changes;
- multi-asset execution changes;
- live-submit or sizing expansion;
- a new report directory, JSON/Markdown runtime writer, or second PG truth.

## Architecture

### 1. Production Semantics Adapter

`RuntimeStrategySignalEvaluationService` remains the only evaluator router for
the current strategy versions. Historical/replay callers must construct the
same typed `StrategyFamilySignalInput` used by production and call this service.
P1-OFC must not copy evaluator rules into a calibration module.

### 2. Typed Calibration Core

A new pure domain module accepts already evaluated observations. Each
observation identifies:

```text
strategy_group_id
strategy_group_version_id
evaluator_version_id
event_spec_id
event_spec_version_id
symbol
side
timeframe
trigger_candle_close_time_ms
source = replay | live
result = signal | near_miss | no_signal | invalid
fact_results
failed_facts
```

The core produces 90-day and 365-day counts, normalized observations, signals,
and near misses per 30 days, top failed facts, missing replay/live counterparts,
result/fact parity mismatches, one bounded next action, and a non-authority
proposal.

The module is deterministic, uses `Decimal`, performs no I/O, and rejects any
payload that claims order or execution authority.

### 3. Decision Boundary

Allowed proposals are:

```text
keep_observing
repair_replay_live_parity
repair_live_coverage
review_strategy_revision
review_scope_expansion
review_park
needs_more_samples
```

Only `repair_replay_live_parity` and `repair_live_coverage` may directly create
engineering work. Strategy, scope, and park proposals remain review-only and
must not mutate PG Owner policy.

### 4. Real Outcome Economics

The existing ticket-bound exchange snapshot path is extended with a read-only
funding-income view. Binance USD-M funding rows are associated only when all of
these are true:

- exact exchange account;
- exact exchange instrument;
- `incomeType=FUNDING_FEE`;
- income timestamp is within the ticket entry-to-final-exit interval;
- the ticket owns the only active position in the current single-position
  runtime boundary.

If attribution is ambiguous, funding remains `null`; it is never estimated and
never blocks entry, protection, reconciliation, or closure.

Exit slippage uses the reference price on the exact filled exit-protection
order. For SL/RUNNER_SL this is the trigger price. For TP1 or explicit limit
exit it is the order price. Unknown reference remains `null`.

Net PnL is:

```text
realized_pnl - fees + funding
```

Funding follows the exchange signed-income convention, so funding paid is
negative and funding received is positive.

### 5. Historical Replay Lab

Historical calibration runs only as a manual, explicit lab. It reads current
Event Spec and candidate-scope identity from PG, fetches Binance USD-M public
closed candles, builds the same typed `StrategyFamilySignalInput` consumed by
production evaluators, and emits one stdout result. It does not write replay
rows, JSON/Markdown reports, live signals, candidate state, Tickets, policy, or
execution authority.

The lab evaluates all current 22 candidate scopes over 90-day and 365-day
windows. One-hour strategies use aligned 1h/4h windows. MPG and MI compute
comparative-strength snapshots from the complete PG-owned symbol universe.
SOR uses each UTC session's first four closed 15m candles as its opening range.

Multi-side evaluators are projected through the selected Event Spec. A signal
for the opposite side is not accepted as the selected event and does not abort
the replay. The observation records `event_side_matched=false` and remains
non-authoritative.

Production evaluators must emit known false facts on `NO_ACTION`, not only true
facts on `WOULD_ENTER`. This is observability-only: fact emission must not
change thresholds, signal type, side, grade, required execution mode, scope, or
authority.

## Data And Authority Flow

```text
historical/public candles
-> typed StrategyFamilySignalInput
-> RuntimeStrategySignalEvaluationService
-> non-authority replay observation
                           \
PG current/audit live facts -> typed live observation
                           /
-> pure calibration core
-> engineering action or review-only proposal
-> no policy mutation
```

```text
real Ticket
-> ticket-bound exchange fills/orders/income reads
-> existing Live Outcome Ledger
-> fees + signed funding + entry/exit slippage + net PnL + R
-> governance review only
```

## Cadence And Performance

| Dimension | Required behavior |
| --- | --- |
| Calibration cadence | Manual, explicit PG-trigger, or strategy-version-change only |
| No-signal file writes | `0` JSON/MD files |
| PG writes | No per-candle calibration writes; current live runtime rows remain unchanged |
| CPU | Historical evaluation runs outside watcher cadence |
| Exchange reads | Funding is fetched only for an existing real submitted Ticket during settlement/finalization |
| Historical market reads | Manual Replay Lab uses public Binance USD-M closed candles only; never watcher cadence |
| Timeout | All exchange reads remain under the existing bounded snapshot timeout |
| Disk | No recurring report or sidecar files |
| Retention | Real outcome rows retained; replay raw material remains research-side provenance |

## Failure Handling

| Failure | Result |
| --- | --- |
| Unknown Event Spec/version | Calibration observation rejected |
| Replay/live identity mismatch | `replay_live_parity_gap` |
| Missing live counterpart | `live_coverage_gap` |
| Missing fact result | Exact missing fact; no inferred success |
| Funding endpoint unavailable | Outcome funding remains `null`; lifecycle continues |
| Funding attribution ambiguous | Outcome funding remains `null`; review notes incomplete economics |
| Exit reference unavailable | Exit slippage remains `null` |
| Replay payload claims authority | Fail closed during model validation |

## Test Strategy

### Calibration Core

- same identity and facts produce parity;
- result mismatch produces one engineering blocker;
- fact mismatch preserves exact fact keys;
- missing live/replay counterpart is classified;
- 90-day and 365-day windows are deterministic;
- proposal types never mutate authority;
- forbidden execution fields are rejected.
- opposite-side evaluator output is projected without becoming the selected Event Spec signal;
- production `NO_ACTION` outputs retain each known false required fact;
- a 22-scope historical lab run creates no PG rows and no JSON/Markdown files.

### Outcome Economics

- funding paid and received preserve sign;
- unrelated symbol/account/time rows are excluded;
- ambiguous attribution remains `null`;
- SL/TP1/RUNNER_SL exit references produce signed exit slippage;
- fees plus funding produce net PnL and R;
- exchange-read timeout does not block lifecycle closure.

### Regression

- existing Action-Time and lifecycle tests;
- production file-I/O audit;
- current-doc authority validation;
- output artifact scope validation;
- full suite before completion.

## Rollback

Calibration code is non-authoritative and can be removed without changing
runtime state. Funding/exit enrichment is nullable and additive to the existing
Outcome calculation. Rollback returns those fields to `null`; it does not
change Ticket, order, position, protection, or settlement state.

## Acceptance

P1-OFC engineering is complete only when:

1. one typed calibration core covers both windows and all six current Event
   Spec identities;
2. parity, coverage, near-miss, and proposal behavior are test-proven;
3. replay results cannot create runtime authority;
4. actual ticket-bound funding and exit slippage can enrich the existing Live
   Outcome Ledger without entering pre-submit gates;
5. no-signal ticks create zero JSON/MD files;
6. full tests and required validators pass;
7. only natural venue calibration and strategy/scope proposals remain
   dependent on market evidence or Owner policy.
