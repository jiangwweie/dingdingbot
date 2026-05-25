# Personal Campaign Promotion Checklist v0

Last updated: 2026-05-25

Status: Promotion checklist / action authorization required

Runtime effect: none

Trading permission effect: none

Default state: disabled until scoped promotion and Owner authorization

## Purpose

This checklist defines the minimum evidence needed before any Personal
Leveraged Campaign artifact can be discussed for a later stage.

Current state:

- no specific runtime action is approved by this checklist alone;
- no specific paper/testnet/tiny-live-style action is approved by this
  checklist alone;
- real live trading remains prohibited unless separately and explicitly
  authorized by Owner;
- no withdrawal candidate, because withdrawal is Owner-external and out of
  system scope.

## Stage 1 To Stage 2: Schema To Local Simulation

Before a docs-only strategy contract skeleton can feed local simulated
intent-to-plan work, all checks must pass:

| Check | Requirement | Current PLC-001 Status |
|---|---|---|
| Object schemas | Core object schemas exist and parse as JSON. | Added for `ModeAdvice`, `HumanArmDecision`, `StrategyContract`, `TradeIntent`, `RiskOrderPlan`, `ExecutionReceipt`, `PositionLifecycleState`, `CampaignState`. |
| Default disabled | Strategy contract schema and sandbox settings enforce disabled/local-only defaults. | Present. |
| LLM containment | LLM role is fixed to explain/audit/suggest only. | Present. |
| No exchange side effect | `TradeIntent` and sandbox trace assert no exchange side effect. | Present. |
| Risk matrix | Order, position, campaign, and profit-protection rules are documented. | Present in `personal-campaign-risk-rule-matrix-v0.md`. |
| Test matrix | Allow/reject, pause, hard-lock, profit-protect, default-disabled, no-side-effect, and invariant pass/fail tests exist. | Present. |

Stage 2 remains local simulation only. Promotion from Stage 2 may be requested
under ADR-0009 after scoped verification.

## Stage 2 To Stage 3: Local Simulation To Demo Portfolio

This transition is not approved by this checklist alone. If requested, it must
explicitly
answer:

- Which strategy contract is being simulated?
- Which object schemas are frozen?
- Which rule matrix version is frozen?
- What local persistence, if any, is introduced?
- How are demo receipts distinguished from real exchange receipts?
- How does the demo state stop before any withdrawal instruction, amount,
  schedule, or automation?
- What rollback deletes all demo state?
- Which tests prove default-disabled behavior still holds?

Owner confirmation is required before Stage 3 work starts.

## Any Promotion Toward Exchange Connectivity

The following require scoped verification and explicit Owner approval before
execution:

- real API key, secret, or passphrase handling;
- read-only account sync;
- paper or testnet account connection;
- tiny-live-style non-real-live rehearsal;
- non-real-live order placement, modification, or cancellation;
- runtime profile or trading permission changes;
- direct research-to-order wiring.

The following remain prohibited unless separately and explicitly authorized as
real-live work:

- real live trading;
- live real-account order placement, modification, or cancellation;
- live transfer, withdrawal, or rebalancing;
- real-funds deployment.

## Required Non-Authorization Statement

Every future PLC task card that touches these objects must include:

```text
Runtime effect: none unless separately approved.
Trading permission effect: none unless separately approved.
Default state: disabled.
No real live trading or real-funds path unless separately and explicitly approved.
Non-real-live runtime, paper, testnet, or exchange-connected actions require scoped verification plus Owner authorization.
Withdrawal is Owner-external.
LLM may explain, audit, and suggest only; it must not decide buy/sell/short/size/leverage.
```

## Current Recommendation

Keep PLC at local docs/design/sandbox/test until a specific ADR-0009 action
request is prepared.

Next allowed work:

- refine SQ02 docs-only `StrategyContract` example;
- add schema examples under `docs/schemas/personal_campaign/examples/`;
- add rule-matrix coverage tests for any new local scenario.

Requires separate ADR-0009 action request:

- runtime wiring;
- paper/testnet/tiny-live-style non-real-live execution;
- real API/account/order access for non-real-live execution;
- separate real-live authorization for any live real-funds action;
- withdrawal instruction, schedule, amount, or automation;
- leverage or sizing advice;
- promotion by implication.
