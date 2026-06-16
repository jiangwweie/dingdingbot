# Strategy Research Guide

Status: ACTIVE_STRATEGY_RESEARCH_GUIDE
Last updated: 2026-06-16

## Purpose

This guide defines how the strategy research line should produce, classify,
downgrade, revive, and hand off StrategyGroup candidates.

The project is a small-capital, strongly bounded, auditable, reviewable
right-tail strategy runtime-governance system. It is not a stable-income quant
platform, a single-strategy optimizer, a return-ranking dashboard, or a fully
autonomous black-box trading robot.

This guide is research-only. It carries no order, execution intent, execution
authority, exchange-write authority, deploy authority, credential authority,
live-profile authority, FinalGate authority, OrderLifecycle authority, exchange
gateway authority, or order-sizing authority.

## Research Objective

Find and maintain a portfolio of small-capital, regime-specific, right-tail
strategy candidates over crypto plus Binance-listed TradFi-like and
precious-metal instruments when reproducible public data exists.

The target is not one strategy that earns stable alpha in every month, symbol,
and market state. The target is a repeatable research system that discovers
strategies that can work unusually well in identifiable market states and can
be disabled, parked, or revived when those states disappear or reappear.

## Required Research Questions

Every candidate must answer these questions before it can be listed as an
active StrategyGroup candidate:

1. What market structure does this strategy try to capture?
2. What facts prove the market is in the intended regime?
3. What facts prove the regime is stale, broken, or unsafe?
4. Which symbols and sides are in scope?
5. Which data is available now and which data is only cached research evidence?
6. Can the evidence path be reproduced without lookahead bias?
7. Does the right-tail window survive basic cost, slippage, funding, liquidity,
   concentration, and drawdown checks?
8. What negative evidence should become disable facts, parking facts, or
   revival conditions?
9. Can the result be handed to main control as a non-executing packet?

## Evidence Standard

Best-window evidence is useful for discovery and prioritization, but it is not
runtime evidence and not a return promise.

| Evidence Type | Research Meaning | Promotion Meaning |
| --- | --- | --- |
| Best 30d / 60d / 90d window | Candidate is worth attribution and kill-tests. | Not sufficient without activation, disable, cost, fill, margin, and live-like fact readiness. |
| Positive full-sequence result | Stronger than window-only evidence. | Still blocked if drawdown, concentration, leverage, or fact quality fails. |
| High drawdown with high right-tail | Window may be real but boundary is incomplete. | Promotion blocked until disable and protection facts improve. |
| Short-history 2026 TradFi / metals evidence | Valid discovery lane. | Promotion blocker until current availability, session, mark, funding, liquidity, and margin facts exist. |
| Negative evidence | Input to disable facts, parking facts, and revival rules. | Must not be deleted. |
| Handoff sample packets | Main-control review shape. | Not execution authority. |

## Candidate Lifecycle

| Status | Meaning |
| --- | --- |
| `idea_pool` | Idea exists but is not structurally researched. |
| `research_candidate` | Candidate has a market-structure thesis and early evidence. |
| `right_tail_candidate` | Candidate has one or more strong local right-tail windows. |
| `observe_only` | Candidate can be watched without execution semantics. |
| `conditional_observation` | Candidate should be watched only in a narrow branch or session. |
| `handoff_ready` | Candidate has a StrategyGroup handoff pack for main-control review. |
| `handoff_ready_facts_heavy` | Handoff exists but the fact gate is unusually heavy. |
| `handoff_ready_low_history_blocked` | Handoff exists but short history and product facts block promotion. |
| `next_handoff_candidate` | Best next candidate to convert into handoff shape. |
| `facts_pipeline_required` | Strategy thesis is useful but required facts are not yet captured. |
| `observe_only_scorer` | Strategy is currently a ranking or scoring lens, not an action group. |
| `overlay_candidate` | Strategy is a filter, hedge, or context overlay. |
| `parked_or_research_vocab` | Strategy is not active, but its semantics remain useful. |
| `killed` | Current semantics are rejected unless explicitly revived. |

## Leverage Rule

Leverage is a boundary and stress tool, not a return-manufacturing tool.

Default interpretation:

| Lane | Meaning |
| --- | --- |
| `1x` | Default research view. |
| `2x` | Allowed research lane when costs, drawdown, mark, funding, fill, and margin facts do not contradict it. |
| `3x` | Stress-only unless a separate evidence packet proves otherwise. |
| `5x` | Disabled by default. |

Any candidate that relies on 3x or 5x to look attractive must be marked as
stress-only or disabled until real exchange-margin, fill/gap, funding, and
liquidation facts exist.

## Required Handoff Shape

Every candidate moving toward main control should provide:

1. `strategy_group_id` or candidate id.
2. Version.
3. Market structure thesis.
4. Supported symbols and sides.
5. Supported timeframe or observation cadence.
6. Signal-ready rule.
7. Activation facts.
8. Disable facts.
9. Parking and revival facts.
10. RequiredFacts and freshness expectations.
11. Leverage boundary.
12. Risk defaults as research proposals only.
13. Hard stops.
14. Right-tail windows and worst windows.
15. Symbol and regime attribution.
16. Lookahead-bias and recursive-data checks where applicable.
17. Cost, slippage, funding, liquidity, and margin assumptions.
18. Negative evidence.
19. Sample signal, no-signal, stale, and conflict packets if handoff-ready.
20. Non-execution flags.

## Current Strategy Cabinet

The active semantic registry is:

```text
docs/strategy-research/strategy-cabinet/strategy-cabinet.md
docs/strategy-research/strategy-cabinet/strategy-cabinet.json
```

The strategy cabinet is not a runtime registry, not a Strategy Picker
implementation, not an order authority, and not a return leaderboard. It is a
research governance artifact that records which strategy semantics are alive,
parked, blocked, or ready for main-control review.

## Standing Prohibitions

Strategy research must not modify:

1. OrderLifecycle.
2. FinalGate execution boundaries.
3. Exchange gateway.
4. Live profile.
5. Credentials.
6. Order-sizing defaults.
7. Deploy state.
8. Exchange write paths.
9. Real order paths.

Main control may consume only explicit handoff packs and validation evidence,
not raw research conclusions or attractive return numbers.
