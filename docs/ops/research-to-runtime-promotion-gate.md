# Research To Runtime Promotion Gate

Last updated: 2026-05-25
Status: Promotion gate / no runtime candidates
Runtime effect: none
Trading permission effect: none

## Purpose

This template defines the future gate for moving a research output toward
runtime, paper, testnet, live, tiny-live, or real-funds use.

Current state:

- no promoted runtime research output;
- no runtime candidate;
- no paper candidate;
- no testnet candidate;
- no live candidate;
- no tiny-live candidate.

2026-05-25 note: the Owner accepted the Personal Leveraged Campaign Business
Chain as the business mainline. That creates a docs/design direction, not a
runtime candidate.

## Promotion Requires Separate Review

Any promotion toward runtime, paper, testnet, live, tiny-live, or real-funds use
must be a separate task and must explicitly state:

- research artifact being promoted;
- evidence label before promotion;
- intended mode: observe, demo, paper, testnet, live, or tiny-live;
- runtime effect;
- trading permission effect;
- secrets required or not required;
- default enabled/disabled state;
- tests required;
- rollback path;
- why LLM/Agent output cannot directly decide buy/sell/short/size/leverage.

Owner confirmation is required when the promotion touches real secrets, real
trading permissions, real account actions, push, real-account deployment, or
direct research-to-real-order wiring.

## Current Candidate Table

| Candidate | Source artifact | Requested mode | Status |
|---|---|---|---|
| None | None | None | No runtime, paper, testnet, live, or tiny-live candidate exists. |

## Design-Skeleton Candidate Table

| Candidate | Source artifact | Requested mode | Status |
|---|---|---|---|
| `SQ02_DOWNSIDE_CONT_V0` | `reports/orh-007-sq02-public-universe-retest-20260524/`, `reports/sq02-manual-semi-auto-review-design-20260524/`, `reports/semi-auto-momentum-synthesis-20260524/`, `reports/semi-auto-control-sheet-readability-audit-20260525/` | Docs-only strategy-contract skeleton | Allowed as design-only. Not approved for scanner, alert, watchlist, runtime, paper, testnet, tiny-live, live, account, leverage, sizing, or real order path. |

## Business Chain Promotion Objects

Any future promotion must explicitly define and review these objects before
execution-path use:

- `StrategyContract`;
- `TradeIntent`;
- `RiskOrderPlan`;
- `ExecutionReceipt`;
- `PositionLifecycleState`;
- `CampaignState`;
- `WithdrawalInstruction`.

The `RiskOrderPlan` boundary is mandatory. A strategy contract may emit a trade
intent only; it must not bypass order-level, position-level, and campaign-level
risk checks.

## Non-Authorization

This template does not authorize runtime integration, paper/testnet/live,
tiny-live, real API keys, real orders, or real account deployment.
