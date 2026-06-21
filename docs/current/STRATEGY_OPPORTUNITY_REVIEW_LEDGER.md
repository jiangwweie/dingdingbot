---
title: STRATEGY_OPPORTUNITY_REVIEW_LEDGER
status: CURRENT
authority: docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
last_verified: 2026-06-19
---

# StrategyGroup Decision Ledger

Compatibility path:

```text
docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
```

## Purpose

The StrategyGroup Decision Ledger is the minimal pre-live learning ledger for
the StrategyGroup runtime pilot.

Its job is not to record every opportunity. Its job is to turn high-priority
market observations into repeatable StrategyGroup decisions:

```text
read-only market observation
-> high-priority no-action / would-enter / stale / missing-fact evidence
-> replay support or replay gap
-> classifier / facts / freshness / cost / tier diagnosis
-> keep / revise / promote / park / kill / go-live / do-not-go-live / safety-block decision
-> next checkpoint
```

This ledger exists because the project has moved beyond pure runtime-chain
construction. `P0` stays ready for the first selected allocated-subaccount live
closure. During healthy no-signal periods, `P0.5` must use local and read-only
market evidence to improve StrategyGroup quality instead of waiting passively
for live signals.

The ledger is a decision surface, not a diagnostic archive. A record belongs
here only when it changes one of these decisions:

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

## Relationship To Existing Ledgers

| Ledger | Stage | Purpose | Real-order authority |
| --- | --- | --- | --- |
| StrategyGroup Decision Ledger | Before live submit | Decide keep, revise, promote, park, kill, go live, do not go live, or safety block | No |
| Review Ledger | After live action | Record entry, exit, protection, PnL, costs, and review decision | No direct submit authority |
| Technical Debt Queue | After local review | Preserve non-urgent structure, test, and cleanup work | No |

The decision ledger does not authorize shadow candidates, FinalGate,
Operation Layer, exchange writes, or real orders. It is a decision-support
surface for strategy learning and tier governance.

Lower-level replay packets, diagnostics, no-action samples, and source-mapping
files remain evidence. They should not be copied into the main control layer
unless they change a decision.

## Required Row Shape

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

Each StrategyGroup should have at most one current main decision row. Historical
or superseded details belong in lower-level artifacts, not in the main-control
decision layer.

## Current StrategyGroup Use

| StrategyGroup | Current role | Decision-ledger use |
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

## Current Local Checkpoint

The current local checkpoint is implemented:

```text
high-priority no-action rows
-> StrategyGroup Decision Ledger rows
-> replay-to-review matching
-> one current decision per StrategyGroup
-> local monitor sequence integration
```

`scripts/build_strategygroup_decision_ledger.py` is the single main producer.
It consumes lower-level signal coverage and opportunity decision loop evidence,
then emits `output/runtime-monitor/latest-strategygroup-decision-ledger.json`
and `output/runtime-monitor/latest-strategygroup-decision-ledger.md`.

The local monitor sequence runs this producer after the opportunity decision
loop and BTPC review-only fact/classifier steps. Current local output produces
one decision row for `BRF-001`, `BTPC-001`, `LSR-001`, `RBR-001`, and
`VCB-001` without creating FinalGate, Operation Layer, exchange-write, or
real-order authority.

## Acceptance Constraints

A decision-ledger implementation is not accepted unless it proves all of the
following:

| Requirement | Acceptance rule |
| --- | --- |
| P0 priority preserved | The implementation cannot make `waiting_for_market` look blocked when P0 is merely waiting for a fresh signal |
| Current high-priority rows covered | `BRF-001`, `BTPC-001`, `LSR-001`, and `VCB-001` high-priority no-action rows must produce one current decision row or explicit no-row reasons |
| Decision present | Every ledger row must carry a `decision` and `next_checkpoint`; explanatory rows without decisions are not mainline |
| Minimal shape preserved | Main rows use the 8 required fields and do not duplicate raw replay samples or source artifact details |
| Authority fields false | `real_order_authority`, `calls_finalgate`, `calls_operation_layer`, `calls_exchange_write`, and `places_order` must remain false |
| Capability status explicit | Owner/developer summaries must label the result as deployed, local, planned, blocked, or market-dependent |
| Monitor integration | The local monitor sequence must include the ledger status before the checkpoint is deploy-worthy |

Rows may support future tier decisions, but the ledger itself is never tier
promotion authority. Promotion still follows the runtime tier policy and the
official live chain.

## Anti-Overengineering Rule

Do not add a new main-control artifact unless it changes one of the eight
allowed decisions. Routine diagnostics should stay in existing replay,
coverage, readiness, or local monitor artifacts.

Each P0.5 phase should have at most one main product. For this phase, the main
product is the StrategyGroup Decision Ledger. Additional markdown summaries,
script forests, or broad opportunity ledgers are out of scope unless they
replace and reduce existing surfaces.
