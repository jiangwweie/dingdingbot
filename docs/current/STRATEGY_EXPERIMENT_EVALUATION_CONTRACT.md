---
title: STRATEGY_EXPERIMENT_EVALUATION_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# Strategy Experiment Evaluation Contract

## Objective

Evaluate whether a StrategyGroup is worth bounded real-capital experimentation,
not whether it can promise a fixed return or smooth equity curve.

## Required Evaluation

| Dimension | Required answer |
| --- | --- |
| Edge thesis | What market behavior creates the opportunity |
| Event identity | Which versioned event means the opportunity exists |
| Regime fit | Where the event is expected to work or fail |
| Side and instrument | Explicit supported scope |
| Downside envelope | Stop, invalidation, path, liquidation, fee, and funding risk |
| Right-tail path | How the strategy preserves materially larger winners |
| Evidence | Replay, paper, observation, or real outcome evidence with source boundary |
| Kill rule | Evidence that ends further experimentation |

High-return and leverage numbers are scenarios and aspiration anchors, not
automatic authorization or rejection. Runtime authority still comes from
current Owner policy, current facts, an immutable Ticket, and the official
kernel chain.

## Outcomes

Use one of:

```text
experiment_worthy
observe_only
revise
park
kill
```

Strategy evaluation never creates a Ticket or Exchange Command.
