# Research To Runtime Promotion Gate

Last updated: 2026-05-25
Status: Promotion gate / action authorization required
Runtime effect: none
Trading permission effect: none

## Purpose

This template defines the gate for moving a research output toward runtime,
paper, testnet, tiny-live-style rehearsal, live, or real-funds use.

Current state:

- no promoted runtime research output has been approved by this file alone;
- no paper/testnet/tiny-live action may execute without a scoped request,
  reasonable verification, and explicit Owner authorization;
- real live trading remains prohibited unless separately and explicitly
  authorized by Owner.

2026-05-25 note: the Owner accepted the Personal Leveraged Campaign Business
Chain as the business mainline. The Owner later clarified in ADR-0009 that
runtime, paper, testnet, tiny-live-style rehearsal, and other non-real-live work
can proceed after scoped verification and explicit Owner authorization for the
specific action.

## Promotion Requires Separate Review

Any promotion toward runtime, paper, testnet, tiny-live-style, live, or
real-funds use must be a separate task and must explicitly state:

- research artifact being promoted;
- evidence label before promotion;
- intended mode: observe, demo, paper, testnet, live, or tiny-live;
- runtime effect;
- trading permission effect;
- secrets required or not required;
- default enabled/disabled state;
- tests required;
- tests or verification already completed before execution;
- exact command, endpoint, script, or operational step requested;
- expected external systems touched;
- maximum order/action count and maximum notional or abstract cap when orders
  are involved;
- stop condition;
- rollback path;
- why LLM/Agent output cannot directly decide buy/sell/short/size/leverage.

Owner confirmation is required before every runtime, paper, testnet,
tiny-live-style, exchange-connected, account-action, push, deployment, or direct
research-to-order step. Real live trading requires a separate explicit Owner
authorization decision.

## Current Candidate Table

| Candidate | Source artifact | Requested mode | Status |
|---|---|---|---|
| None | None | None | No specific runtime, paper, testnet, live, or tiny-live action is approved by this table. |

## Design-Skeleton Candidate Table

| Candidate | Source artifact | Requested mode | Status |
|---|---|---|---|
| `SQ02_DOWNSIDE_CONT_V0` | `reports/orh-007-sq02-public-universe-retest-20260524/`, `reports/sq02-manual-semi-auto-review-design-20260524/`, `reports/semi-auto-momentum-synthesis-20260524/`, `reports/semi-auto-control-sheet-readability-audit-20260525/` | Strategy-contract skeleton / local sandbox | Current local design and sandbox work is allowed. Scanner, alert, watchlist, runtime, paper, testnet, tiny-live-style, account, leverage, sizing, or order-path use requires a separate action request under ADR-0009. |

## Business Chain Promotion Objects

Any future promotion must explicitly define and review these objects before
execution-path use:

- `StrategyContract`;
- `TradeIntent`;
- `RiskOrderPlan`;
- `ExecutionReceipt`;
- `PositionLifecycleState`;
- `CampaignState`.

The `RiskOrderPlan` boundary is mandatory. A strategy contract may emit a trade
intent only; it must not bypass order-level, position-level, and campaign-level
risk checks.

Withdrawal is Owner-external and must not be represented as a promotion object,
automation target, LLM suggestion, or strategy signal.

## Standing Boundary

This template does not by itself authorize a specific runtime, paper, testnet,
tiny-live-style, real API, order, or account deployment action. It defines how
to request one.

Real live trading, live real-account order placement, live transfer,
withdrawal, rebalancing, and real-funds deployment remain prohibited unless
separately and explicitly authorized by Owner.
