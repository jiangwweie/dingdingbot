# Personal Leveraged Campaign Local Sandbox v0

Last updated: 2026-05-25

Status: Local sandbox implemented

Runtime effect: none

Trading permission effect: none

Default state: disabled by default / local-only

## Purpose

This document records the minimum local development loop for the Personal
Leveraged Campaign business chain.

The loop itself is intentionally limited to docs/design/sandbox/test. It does
not connect to real APIs, real accounts, exchange gateways, runtime profiles,
paper/testnet/live/tiny-live modes, order placement, cancellation, transfer, or
withdrawal. Withdrawal is Owner-external and is not modeled here.

Promotion out of this local sandbox is not globally forbidden anymore. Under
ADR-0009, a specific non-real-live runtime, paper, testnet, tiny-live-style, or
exchange-connected step may be requested after scoped verification and explicit
Owner authorization. Real live trading remains separately prohibited.

## Minimum Verifiable Loop

The first local loop is:

`ModeAdvice -> HumanArmDecision -> StrategyContract + FeatureSnapshot -> TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState -> CampaignState`

Implemented files:

- `src/domain/personal_campaign.py`
- `src/application/personal_campaign_sandbox.py`
- `tests/unit/test_personal_campaign_sandbox.py`
- `tests/unit/test_personal_campaign_schema_docs.py`

Design/schema files:

- `docs/schemas/personal_campaign/*.schema.json`
- `docs/schemas/personal_campaign/examples/*.example.json`
- `docs/ops/personal-campaign-risk-rule-matrix-v0.md`
- `docs/ops/personal-campaign-promotion-checklist-v0.md`
- `docs/ops/sq02-downside-cont-strategy-contract-skeleton-v0.md`

The end-to-end runner is `run_campaign_sandbox_trace`. It defaults to disabled
through `CampaignSandboxSettings(enabled=False)`. Local tests must explicitly
pass `enabled=True` to produce a trace.

The repeatable scenario catalog is `build_campaign_sandbox_scenario_catalog`.
It is a local verification matrix, not a runtime entry point.

The invariant evaluator is `evaluate_campaign_sandbox_trace_invariants`. It
checks each completed trace for local-only effects, default-disabled strategy
contracts, LLM role containment, order-plan protection requirements,
hard-lock consistency, profit-protect reduce/close requirements, and complete
safety assertions.

## Object Boundary

`ModeAdvice`

- explains why a mode is surfaced;
- carries evidence and caveats;
- marks LLM scope as explain/audit/suggest only.

`HumanArmDecision`

- records Owner arm/pause/reject authority;
- scopes the decision to a campaign, session, and expiry window;
- does not require per-order manual confirmation.

`StrategyContract`

- is deterministic and disabled by default;
- evaluates setup and invalidation keys from a local feature snapshot;
- emits only `TradeIntent`, never an order.

`FeatureSnapshot`

- is closed/prior-input only;
- forbids lookahead, LLM trade decisions, real account state, and exchange API
  state;
- binds to exactly one strategy contract id;
- carries deterministic boolean conditions consumed by the strategy contract.

`TradeIntent`

- expresses desired strategy action with no exchange side effect;
- can be allow or reject;
- carries trigger and invalidation reasons.

`RiskOrderPlan`

- enforces owner-fixed order, position, and campaign caps;
- can allow or reject before simulated execution;
- requires protective stop, position lifecycle monitor, and campaign loss lock
  for allowed plans.

`ExecutionReceipt`

- is local simulated acknowledgement only;
- has no exchange order id and no exchange side effect.

`PositionLifecycleState`

- enforces protection presence;
- can require reduce/close;
- can force hard-lock when protection is missing or loss cap is reached.

`CampaignState`

- tracks arm/pause/hard-lock state;
- enforces loss lock and profit-protect state;
- remains local and replayable.

`CampaignSandboxTrace`

- records every object in the local chain;
- records `runtime_effect=none` and `trading_permission_effect=none`;
- records safety assertions for no exchange API, no real account, no order side
  effect, and no transfer or withdrawal path.

`CampaignTraceInvariantReport`

- reports `pass` or `fail` for a local sandbox trace;
- lists checks passed and violations;
- is used by tests to ensure scenario traces remain inside the approved local
  boundary.

## Scenario Catalog

The local scenario catalog currently contains:

| Scenario | Purpose | Expected boundary |
|---|---|---|
| `allow_open_protected` | Armed session allows capped order plan and protected simulated position. | `TradeIntent=allow`, `RiskOrderPlan=allow`, position remains protected. |
| `reject_contract_invalidated` | Contract invalidation rejects the intent before order planning. | `TradeIntent=reject`, simulated receipt is blocked. |
| `reject_order_caps` | Owner-fixed order caps reject the plan before simulated execution. | Intent can allow, but `RiskOrderPlan=reject`. |
| `pause_blocks_session` | Owner pause blocks intent and order plan without per-order review. | Campaign remains paused and plan rejects. |
| `hard_lock_missing_protection` | Missing protection forces close requirement and campaign hard-lock. | Position requires close and campaign is hard-locked. |
| `profit_protect_reduce` | Profit threshold activates reduction requirement. | Position requires reduce/close; Owner handles withdrawal outside the system. |

## Covered Scenarios

Targeted unit tests cover:

- allow: armed session, valid setup, capped order plan, simulated receipt,
  protected position;
- reject: setup absent, setup invalidated, and order cap breaches;
- pause: Owner pause blocks intent and order plan;
- hard-lock: missing protection locks campaign and blocks future plans;
- loss-lock: campaign loss cap forces hard-lock and close/reduce requirement;
- profit-protect: profit threshold marks reduce requirement;
- default disabled: the end-to-end sandbox runner raises unless explicitly
  enabled for local tests;
- side-effect guard: settings reject external side effects;
- scenario catalog: all catalog scenarios serialize with `runtime_effect=none`,
  `trading_permission_effect=none`, and no external side effects;
- invariant evaluator: all catalog traces pass, and deliberate unsafe traces
  fail when a strategy contract is not disabled or profit protection loses the
  reduce/close requirement;
- schema docs: local JSON schema files parse and preserve disabled/local-only
  safety fields;
- schema examples: SQ02 docs-only examples parse against local Pydantic models
  and preserve default-disabled, closed/prior feature snapshot, no-side-effect,
  and protection fields.

## Non-Authorization

This sandbox does not by itself authorize:

- real API keys, account data, or exchange calls;
- paper/testnet/tiny-live-style execution;
- real live trading;
- live real-account orders, cancellations, transfers, withdrawals, or
  rebalancing;
- withdrawal instructions, schedules, amounts, or automation;
- strategy promotion to runtime;
- LLM/agent buy, sell, direction, size, or leverage decisions;
- runtime profile, risk parameter, or exchange gateway changes.

Any non-real-live promotion must follow the ADR-0009 action gate.

## Rollback

Remove the three implementation/test files above and this docs entry. No
runtime state, database schema, profile, exchange configuration, or account
permission needs rollback because none is touched.
