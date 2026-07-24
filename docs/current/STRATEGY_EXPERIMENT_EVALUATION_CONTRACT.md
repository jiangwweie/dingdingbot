---
title: STRATEGY_EXPERIMENT_EVALUATION_CONTRACT
status: CURRENT
last_verified: 2026-07-24
---

# Strategy Experiment Evaluation Contract

## Objective

Evaluate whether a StrategyGroup is worth bounded real-capital experimentation,
not whether it can promise a fixed return or smooth equity curve.

The portfolio hypothesis is asymmetric: repeated bounded losses are acceptable
only when the strategy preserves a credible path for less frequent winners to
contribute materially more than one initial unit of risk.

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

## Required Economic Evidence

| Measure | Required interpretation |
| --- | --- |
| Net R | Realized PnL after fee, funding, and slippage divided by frozen initial stop risk |
| Payoff distribution | Win rate, median loss, median win, large-winner frequency, and concentration of gains |
| MFE and MAE | Maximum favorable and adverse excursion measured on one explicit price and fee basis |
| Runner contribution | Net R contributed after TP1 or the strategy's first risk-reduction event |
| Execution cost | Fee, funding, spread, slippage, and rejected or flattened execution cost |
| Tail dependence | How much total result depends on the largest winners and whether that dependence matches the thesis |
| Survival evidence | Observation count, losing streak, drawdown, incident count, and remaining experiment-capital capacity |

No single metric establishes an edge. Review must preserve per-Ticket facts and
show both the aggregate result and the contribution of tail outcomes. Missing
funding or execution evidence remains explicit rather than being treated as
zero.

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
