---
title: STRATEGY_OPPORTUNITY_REVIEW_LEDGER
status: CURRENT
authority: docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
last_verified: 2026-06-23
---

# Strategy Asset State Pre-Live Evidence

Current contract path:

```text
docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
```

## Purpose

This document defines the pre-live evidence contract for **Strategy Asset
State**. In the current architecture, the active strategy-decision source is
Strategy Asset State, and lower-level replay, coverage, and no-action artifacts
feed it only as evidence.

Its job is not to record every opportunity or answer whether a strategy can
trade. Its job is to turn high-priority market observations into repeatable
Strategy Asset State evidence:

```text
read-only market observation
-> high-priority no-action / would-enter / stale / missing-fact evidence
-> replay support or replay gap
-> classifier / facts / freshness / cost / tier diagnosis
-> keep / revise / promote / park / kill / go-live / do-not-go-live / safety-block evidence
-> next checkpoint
```

This ledger exists because the project has moved beyond pure runtime-chain
construction. `P0` stays ready for the first selected allocated-subaccount live
closure. During healthy no-signal periods, Signal Observation grade evidence
uses local and read-only market evidence to improve StrategyGroup quality
instead of waiting passively for live signals.

Strategy decision language follows
`docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`. Rows should treat
high-return targets such as `100%` as aspiration anchors and leverage values
such as `5x` as review scenarios. They should not turn either into a fixed
intake pass/fail gate.

Tradeability language follows `docs/current/TRADEABILITY_DECISION_CONTRACT.md`.
Only Tradeability Decision answers whether a strategy can trade now. When
Strategy Asset State evidence informs tradeability, it should expose the first
non-runtime blocker as input evidence only. A candidate may be promising but
still blocked by asset admission, Owner policy, facts, runtime gate, strategy
quality, or hard safety. Do not flatten those states into
`waiting_for_market`.

The Strategy Asset State evidence surface is not a diagnostic archive. A record
belongs here only when it changes one of these Strategy Asset State decisions:

```text
go_live
do_not_go_live
keep_observing
revise
park
kill
promote
block_for_safety
```

New `promote` rows must include `promotion_scope`. Generic promotion is too
ambiguous because `intake_only`, `trial_admission`, `armed_observation`,
`tiny_live_ready_review`, and `l4_eligibility_review` mean different things.

## Relationship To Existing Ledgers

| Artifact | Stage | Purpose | Real-order authority |
| --- | --- | --- | --- |
| Strategy Asset State pre-live evidence | Before live submit | Preserve keep, revise, promote, park, kill, go live, do not go live, or safety-block evidence | No |
| Review Ledger | After live action | Record entry, exit, protection, PnL, costs, and review decision | No direct submit authority |
| Technical Debt Queue | After local review | Preserve non-urgent structure, test, and cleanup work | No |

The Strategy Asset State evidence output does not authorize shadow candidates,
FinalGate, Operation Layer, exchange writes, or real orders. It is a
decision-support evidence surface for strategy learning and tier governance.

Lower-level replay artifacts, diagnostics, no-action samples, and source-mapping
files remain evidence. They should not be copied into the main control layer
unless they change a decision.

## Row Shape

The first eight fields are the minimal required Strategy Asset State evidence
shape.
`promotion_scope` is required only when `decision=promote`.
`tradeability_first_blocker` is optional and should be present only when the row
feeds Tradeability Decision input evidence.

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | StrategyGroup that produced or missed the opportunity |
| `tier` | Current runtime tier, such as `L1`, `L2`, `L3`, or `L4` |
| `opportunity_type` | `would_enter`, `no_action`, `stale_signal`, `missing_fact`, `classifier_conflict`, `replay_gap`, or `live_outcome` |
| `decision` | `go_live`, `do_not_go_live`, `keep_observing`, `revise`, `park`, `kill`, `promote`, or `block_for_safety` |
| `reason` | One concise reason for the current decision |
| `required_next_evidence` | The next evidence needed to change the decision, or `none` |
| `authority_boundary` | Why this row does or does not affect live authority |
| `next_checkpoint` | The next concrete checkpoint for this StrategyGroup |
| `promotion_scope` | Required when `decision=promote`; examples: `intake_only`, `trial_admission`, `armed_observation`, `tiny_live_ready_review`, `l4_eligibility_review` |
| `tradeability_first_blocker` | Optional blocker used when the row feeds Tradeability Decision input evidence |

Each StrategyGroup should have at most one current main decision row. Historical
or superseded details belong in lower-level artifacts, not in the main-control
decision layer.

## Current StrategyGroup Use

| StrategyGroup | Current role | Strategy Asset State evidence use |
| --- | --- | --- |
| `MPG-001` | First `L4` allocated-subaccount live lane | Preserve P0 waiting/live outcomes; live results later update Review Ledger |
| `BTPC-001` | `L2` shadow candidate | Keep observing or revise based on shadow quality, live derivatives facts, and classifier evidence |
| `BRF-001` | `L1` observe-only | Revise, keep observing, or park based on bear-rally-failure replay and squeeze-risk evidence |
| `VCB-001` | `L1` observe-only | Revise, keep observing, or park based on compression breakout replay and false-breakout evidence |
| `LSR-001` | `L1` observe-only | Revise, keep observing, or park based on liquidity-sweep and short-revival classifier evidence |
| `RBR-001` | `L1` low-priority parked vocabulary | Keep parked unless materially new edge evidence appears |

## Replay Policy

Replay is required strategy-learning input, not live evidence.

Replay may support a decision when it proves:

- no-action was likely correct filtering;
- no-action may be a classifier or facts miss;
- would-enter needs cost, slippage, or funding survival review;
- a StrategyGroup should keep observing, revise, promote, park, kill, go live,
  avoid go-live, or remain safety-blocked.

Replay must not be represented as:

- a live market signal;
- live RequiredFacts;
- FinalGate evidence;
- Operation Layer evidence;
- real-submit authority;
- proof of profitability.

Replay may still make a strategy experiment-worthy when it exposes a clear
right-tail or portfolio-role thesis, known failure modes, bounded loss envelope,
and a useful next checkpoint.

## Current PG Checkpoint

The current checkpoint must be implemented as PG strategy-review/current
projection rows:

```text
high-priority no-action rows
-> PG strategy review evidence rows
-> replay-to-review matching
-> one current decision per StrategyGroup
-> Strategy Asset State current projection
```

The retired local producer and Strategy Asset State latest-export family are not
current authority. Useful historical conclusions must be imported as PG strategy
review rows or kept as archive-only provenance. Current runtime, Owner
explanation, Tradeability, Daily Table, Candidate Pool, and monitor paths must
not read old output files.

The current projection produces at most one decision row per StrategyGroup for
`BRF-001`, `BTPC-001`, `LSR-001`, `RBR-001`, and `VCB-001` without creating
FinalGate, Operation Layer, exchange-write, or real-order authority.

## Acceptance Constraints

A Strategy Asset State implementation is not accepted unless it proves all of the
following:

| Requirement | Acceptance rule |
| --- | --- |
| P0 priority preserved | The implementation cannot make `waiting_for_market` look blocked when P0 is merely waiting for a fresh signal |
| Current high-priority rows covered | `BRF-001`, `BTPC-001`, `LSR-001`, and `VCB-001` high-priority no-action rows must produce one current decision row or explicit no-row reasons |
| Decision present | Every Strategy Asset State row must carry a `decision` and `next_checkpoint`; explanatory rows without decisions are not mainline |
| Minimal shape preserved | Main rows use the 8 required fields and do not duplicate raw replay samples or source artifact details |
| Authority denial preserved | Strategy Asset State evidence must deny live/order authority and keep `calls_finalgate`, `calls_operation_layer`, `calls_exchange_write`, and `places_order` false |
| Capability status explicit | Owner/developer summaries must label the result as deployed, local, planned, blocked, or market-dependent |
| Monitor integration | Server-side monitor / Owner readmodel may show Strategy Asset State only from PG projection rows, never from local output files |

Rows may support future tier decisions, but Strategy Asset State output itself
is never tier promotion authority. Promotion still follows the runtime tier
policy and the official live chain.

Strategy Asset State evidence may feed Tradeability Decision input evidence,
but it must not replace Tradeability Decision. Strategy Asset State says why
strategy governance changes. Tradeability Decision says whether the strategy
can trade now and, if not, the first blocker.

## Anti-Overengineering Rule

Do not add a new main-control artifact unless it changes one of the eight
allowed decisions. Routine diagnostics should stay in existing replay,
coverage, readiness, or local monitor artifacts.

Each Signal Observation grade phase should have at most one main product. For
this phase, the main product is Strategy Asset State current projection backed
by PG review rows. Additional markdown summaries, script forests, generated
JSON, or broad opportunity ledgers are out of scope unless they are archive-only
material and are absent from runtime, Owner explanation, and tradeability paths.
