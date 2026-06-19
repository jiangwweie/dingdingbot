---
title: STRATEGY_OPPORTUNITY_REVIEW_LEDGER
status: CURRENT
authority: docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
last_verified: 2026-06-19
---

# Strategy Opportunity Review Ledger

## Purpose

The Strategy Opportunity Review Ledger is the pre-live learning ledger for the
StrategyGroup runtime pilot.

Its job is to turn market observations into repeatable strategy decisions:

```text
read-only market observation
-> no-action / would-enter / stale / missing-fact row
-> replay match or replay gap
-> classifier / facts / freshness / cost / tier diagnosis
-> decision action
-> future StrategyGroup tier or research handoff input
```

This ledger exists because the project has moved beyond pure runtime-chain
construction. `P0` stays ready for the first selected allocated-subaccount live
closure. During healthy no-signal periods, `P0.5` must use local and read-only
market evidence to improve StrategyGroup quality instead of waiting passively
for live signals.

## Relationship To Existing Ledgers

| Ledger | Stage | Purpose | Real-order authority |
| --- | --- | --- | --- |
| Strategy Opportunity Review Ledger | Before live submit | Learn from no-action, would-enter, replay, and strategy gaps | No |
| Trade Intent Ledger | Before live submit | Preserve non-executable intent or observe-only evidence | No |
| Gate Failure Ledger | Runtime gate review | Explain why a runtime gate stopped | No |
| Review Ledger | After live action | Record entry, exit, protection, PnL, costs, and review decision | No direct submit authority |

The opportunity ledger does not authorize shadow candidates, FinalGate,
Operation Layer, exchange writes, or real orders. It is a decision-support
surface for strategy learning and tier governance.

## Required Row Shape

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | StrategyGroup that produced or missed the opportunity |
| `symbol` | Observed symbol or normalized market |
| `side` | `long`, `short`, or `none` |
| `signal_type` | `would_enter`, `no_action`, `stale_signal`, `missing_fact`, or `classifier_conflict` |
| `reason_codes` | Why the row exists |
| `coverage_review_priority` | `P0_5`, `P1`, `P2`, or parked priority |
| `replay_match_status` | `matched`, `missing_replay`, `partial`, or `not_applicable` |
| `gap_type` | `classifier`, `facts`, `freshness`, `cost`, `edge`, `tier`, or `none` |
| `decision_action` | `keep_observe_only`, `add_replay`, `repair_classifier`, `map_required_facts`, `prepare_l2_intake`, `continue_l2_shadow`, `park`, or `kill` |
| `tier_effect` | Whether this supports L1 observation, L2 shadow review, L3 armed observation, or future L4 review |
| `source_artifacts` | Diagnostic, replay, readiness, and decision-loop artifact paths |
| `real_order_authority` | Must remain `false` |

## Current StrategyGroup Use

| StrategyGroup | Current role | Opportunity-ledger use |
| --- | --- | --- |
| `MPG-001` | First `L4` allocated-subaccount live lane | Preserve P0 waiting/live outcomes; live results later update Review Ledger |
| `BTPC-001` | `L2` shadow candidate | Track stale, missing derivatives facts, strong-uptrend disable, and shadow quality rows |
| `BRF-001` | `L1` observe-only | Track bear-rally-failure no-action, rally context, and short-squeeze classifier gaps |
| `VCB-001` | `L1` observe-only | Track compression breakout, volume expansion, and false-breakout disable gaps |
| `LSR-001` | `L1` observe-only | Track long-preview conflict and short-revival rewrite gaps |
| `RBR-001` | `L1` low-priority parked vocabulary | Keep parked unless materially new edge evidence appears |

## Replay Policy

Replay is required strategy-learning input, not live evidence.

Replay may prove:

- no-action was likely correct filtering;
- no-action may be a classifier or facts miss;
- would-enter needs cost, slippage, or funding survival review;
- a StrategyGroup should keep observing, revise, prepare L2 intake, park, or
  kill.

Replay must not be represented as:

- a live market signal;
- live RequiredFacts;
- FinalGate evidence;
- Operation Layer evidence;
- real-submit authority;
- proof of profitability.

## Mainline Next Checkpoint

The next deploy-worthy local checkpoint is:

```text
high-priority no-action rows
-> Strategy Opportunity Review Ledger rows
-> replay-to-review matching
-> decision_action
-> local monitor sequence integration
```

The checkpoint is complete only when current `BRF-001`, `BTPC-001`, `LSR-001`,
and `VCB-001` high-priority no-action rows produce ledger/decision rows without
creating FinalGate, Operation Layer, exchange-write, or real-order authority.
