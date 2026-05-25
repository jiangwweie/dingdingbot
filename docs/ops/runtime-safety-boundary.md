# Runtime Safety Boundary

Last updated: 2026-05-25
Status: Runtime-only boundary note
Runtime effect: none
Trading permission effect: none

## Purpose

This short note keeps runtime safety concepts out of the active research SSOT.

Live-safe, OwnerGate, StrategySignalV2, permission states, exchange gateway,
execution orchestrator, order lifecycle, risk profiles, runtime profiles, and
sizing are runtime safety zone concerns. They remain important, but they no
longer define the current opportunity research mainline.

2026-05-25 update: the accepted Personal Leveraged Campaign mainline introduces
`StrategyContract`, `TradeIntent`, `RiskOrderPlan`, `CampaignState`, and
withdrawal-control concepts. These are allowed as docs/design/sandbox objects.
They are not authorized runtime objects unless a separate promotion review
approves the transition.

## Owner Confirmation Required

Owner confirmation is required before:

1. using, reading, writing, pasting, or configuring real API key / secret /
   passphrase;
2. enabling real trading permission;
3. placing, canceling, modifying, transferring, withdrawing, or rebalancing on a
   real exchange account;
4. pushing to a remote repository;
5. deploying and connecting to a real account;
6. wiring research output directly into a real order path.

## Local Work Boundary

Local design, review, refactor drafts, tests, disabled-by-default experiments,
and sandbox-only modules may proceed without prior Owner confirmation when they
do not connect to real trading.

They must report:

- runtime effect;
- trading permission effect;
- default enabled/disabled state;
- tests run;
- rollback path.

Risk-aware order building belongs to the future execution boundary. Docs-only
schemas and local simulations may describe it, but wiring it to exchange
gateway, execution orchestrator, order lifecycle, real account data, paper,
testnet, tiny-live, live, or any real order path requires separate Owner
confirmation.

## Non-Authorization

This file does not authorize paper/testnet/live/tiny-live, real API keys, real
orders, real account deployment, or LLM/Agent trading decisions.
