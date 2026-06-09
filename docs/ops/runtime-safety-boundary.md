> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical roadmap, readiness, rehearsal, safety, or phase artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
>
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> * `docs/canon/TECH_DEBT_BASELINE.md`
> * `docs/canon/DOCUMENT_GOVERNANCE.md`

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
profit-protection concepts. These are allowed as docs/design/sandbox objects.
Withdrawal is Owner-external and is not a system object.

2026-05-25 Owner boundary clarification: real live trading is the hard red
line. Runtime, paper, testnet, tiny-live-style rehearsal, read-only exchange
sync, and other non-real-live work may be executed after reasonable scoped
verification and explicit Owner authorization for the specific action. See
`docs/adr/0009-non-real-live-execution-authorization-boundary.md`.

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
7. executing any runtime, paper, testnet, tiny-live-style, exchange-connected,
   or account-action step, even when no real live funds are involved.

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

Risk-aware order building belongs to the execution boundary. Docs-only schemas
and local simulations may describe it. Wiring it to exchange gateway,
execution orchestrator, order lifecycle, account data, paper, testnet,
tiny-live-style rehearsal, or any real order path requires separate Owner
confirmation and must follow the ADR-0009 action gate.

## Standing Authorization Boundary

This file does not by itself execute or authorize a specific paper/testnet/
runtime action. It establishes that non-real-live work can be requested and
executed after scoped verification plus Owner approval.

This file still does not authorize real live trading, live real-account order
placement, live transfer/withdrawal/rebalancing, real-funds deployment, or
LLM/Agent autonomous trading decisions.
