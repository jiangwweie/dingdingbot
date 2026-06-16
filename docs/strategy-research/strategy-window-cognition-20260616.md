# Strategy Window Cognition Update - 2026-06-16

Status: ACTIVE_RESEARCH_COGNITION
Source: Owner-provided evaluation note on project goal, return expectation,
strategy evidence quality, and right-tail research style.

## Scope

This note records the current cognition for the Strategy Research window after
absorbing the Owner-provided material on project objectives and realistic
return expectations.

This is research-only. It carries no order, execution intent, execution
authority, exchange-write authority, deploy authority, credential authority,
live-profile authority, FinalGate authority, OrderLifecycle authority, exchange
gateway authority, or order-sizing authority.

## Core Cognition

The project should be understood as a small-capital, strongly bounded,
auditable, reviewable right-tail strategy runtime-governance system.

It is not a stable-income quant platform, a single-strategy optimization
project, a return-ranking dashboard, or a fully autonomous black-box trading
robot.

The expected product shape remains:

```text
Owner selects or enables StrategyGroup
-> system observes within official boundaries
-> watcher checks strategy-specific facts
-> fresh signals become reviewable candidates
-> action-time gates remain mandatory
-> only the official runtime / Operation Layer path may approach funds
-> outcomes feed review-ledger promote / revise / park / kill decisions
```

## Return Expectation Semantics

The project has a return expectation, but only as a conditional right-tail
expectation.

Correct interpretation:

```text
Maintain multiple regime-specific StrategyGroups.
Risk very small capital per attempt.
Let many signals wait or fail cheaply.
Let a small number of right-tail windows pay for the observation and trial
costs.
Use RequiredFacts, hard stops, protection, reconciliation, and review to keep
non-strategy failures outside the allowed runtime boundary.
```

Incorrect interpretation:

```text
Find one strategy that produces stable monthly or annual alpha.
Treat best-window backtests as future return promises.
Use leverage as the primary way to manufacture returns.
Promote short-history TradFi-like or metals evidence into execution readiness
without current product, funding, mark, liquidity, fill, and margin facts.
```

## Evidence Quality Interpretation

Right-tail evidence is useful for discovery and prioritization, but not by
itself sufficient for runtime execution.

| Evidence Type | Research Meaning | Promotion Meaning |
| --- | --- | --- |
| Best 30d / 60d / 90d window | Candidate is worth attribution and kill-tests. | Not sufficient. Must attach activation, disable, cost, fill, margin, and live-like fact readiness. |
| Positive full-sequence result | Stronger than window-only evidence. | Still blocked if drawdown, concentration, leverage, or fact quality fails. |
| High drawdown with high right tail | Window may be real but boundary is incomplete. | Promotion blocked until disable and protection facts are stronger. |
| Short-history 2026 TradFi / metals evidence | Valid discovery lane. | Promotion blocker until current availability, session, mark, funding, liquidity, and margin facts exist. |
| Negative evidence | Useful for disable facts, parking facts, and revival rules. | Should not be discarded. |
| Sample signal packets | Handoff-ready shape for main control. | Still not execution authority. |

## Current StrategyGroup Cognition

| StrategyGroup | Current Cognition | Research Role |
| --- | --- | --- |
| `MPG-001` | Main momentum-persistence candidate family with strong right-tail evidence and unresolved drawdown / late-cycle risk. | Keep as core P1 research and handoff family; refine disable, exit-horizon, and drawdown facts. |
| `FBS-001` | Strongest funding/crowding right-tail lead, but most dependent on funding, mark, OI, margin, and concentration facts. | Keep as P1 direct funding-stress family; do not promote without fresh derivatives facts. |
| `TEQ-001` | Equity-like / bStocks / TradFi-perp thematic momentum lane with strong single-name and cluster windows. | Keep as short-history first-class discovery lane; promotion blocked by product/session/fill/margin facts. |
| `PMR-001` | Precious-metal overlay and XAG-led short/window-revival lane. | Treat as observe-only or overlay/filter unless role split improves. |
| `SOR-001` | Session opening-range and session-transfer semantics are useful but narrow and decay-prone. | Use as conditional session branch, not always-on strategy. |

## Strategy Pool Expansion Rule

Future strategy expansion should not add isolated numbered strategies forever.
New work should group candidates by market structure and convert useful
evidence into StrategyGroup candidates.

Preferred next pool expansion lanes:

| Lane | Intended Use |
| --- | --- |
| `NLD-001` new listing / contract event | Short-window, low-capacity discovery around new products and contract metadata changes. |
| `LCF-001` liquidation cascade follow-through | High-right-tail continuation after forced-flow events; requires strict liquidity and slippage facts. |
| `VCB-001` volatility compression breakout | Simple, explainable compression / expansion semantics for watcher observation. |
| `RBR-001` pullback reclaim / failed breakdown | Complements pure momentum continuation by catching reclaim regimes. |
| `RSR-001` relative strength rotation | Basket-relative leader/laggard logic for crypto, equity-like perps, and metals. |
| `MDS-001` metals dislocation / session mismatch | Precious-metal and commodity-specific session / relative-value opportunity lane. |

## Research Operating Rule

Every future candidate should preserve these fields before main-control
handoff:

1. `strategy_group_id` or candidate family id.
2. Market structure thesis.
3. Supported symbols and sides.
4. Activation facts.
5. Disable and parking facts.
6. RequiredFacts and freshness expectations.
7. Leverage interpretation, including explicit downshift or disable rules.
8. Cost, slippage, funding, liquidity, and margin assumptions.
9. Sample signal, no-signal, stale, and conflict packets if handoff-ready.
10. Negative evidence and revival condition.

## Standing Boundary

This cognition update does not authorize runtime registration, live profile
changes, credentials changes, deploy, exchange writes, OrderLifecycle changes,
FinalGate changes, exchange gateway changes, or order-sizing default changes.

Main control may consume only explicit handoff packs and validation evidence,
not raw research conclusions or attractive return numbers.
