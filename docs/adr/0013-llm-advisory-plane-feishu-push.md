# ADR-0013: LLM Advisory Plane and Feishu Push-Only Owner Copilot

Date: 2026-06-10
Status: ACCEPTED

## Context

BRC is converging on strategy runtime governance. The Owner wants LLM support
for market/context synthesis, strategy-family recommendation, audit digestion,
and Feishu notifications, while preserving the existing rule that Owner
confirmation and runtime execution must go through the canonical governance
path.

The useful LLM role is not autonomous trading. It is Owner assistance:

- consume typed system events;
- read structured context packets;
- summarize market/runtime/audit evidence;
- recommend registered strategy families for Owner review;
- push review cards or digests to Feishu;
- help explain blockers and review completed trades.

## Decision

Introduce an additive LLM Advisory Plane:

```text
LLMConsumableEvent
-> LLMContextPacket
-> LLM Advisory Engine
-> AdvisoryRecommendation Ledger
-> Feishu Push-only Card / Console Review
-> Canonical Owner Action, if Owner later acts
```

The advisory plane is event-driven. First-class event types include:

- `market_regime_changed`
- `strategy_candidate_observed`
- `runtime_budget_changed`
- `final_gate_blocked`
- `order_candidate_created`
- `protection_anomaly_detected`
- `reconciliation_mismatch`
- `trade_closed`
- `review_due`
- `daily_audit_digest`
- `owner_requested_analysis`

The LLM may recommend only registered strategy families from the current
StrategySemantics catalog. Unknown ideas must be recorded as research notes,
not runtime-eligible recommendations.

Feishu is a delivery channel only. In the first phase it is push-only: no
interactive Feishu confirmation is accepted as a direct trading action.

## Hard Boundaries

LLM advisory output must not:

- decide buy/sell/short/size/leverage;
- create `SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`, `Order`, or
  `Position`;
- call exchange, `OwnerBoundedExecution`, `OrderLifecycle`, or withdrawal /
  transfer code;
- bypass `RequiredFacts`, runtime boundary, FinalGate, account facts, active
  position checks, protection readiness, or idempotency gates;
- become an audit fact source for market/account/exchange truth.

Feishu confirmation is not part of this phase. A future Feishu button, if
implemented, must create a canonical Owner decision record and re-enter the
normal runtime governance path.

## Consequences

- LLM can help the Owner move faster without becoming an execution authority.
- Audit summaries become easier to consume.
- Strategy-family recommendations can be pushed to the Owner without creating
  an order path.
- The advisory ledger allows later review of LLM recommendations versus Owner
  action and strategy outcomes.
- Notification failure must not block or mutate trading state. It may mark the
  advisory recommendation as `push_failed`.

## Implementation Notes

The first implementation slice adds:

- pure domain models for `LlmConsumableEvent`, `LlmContextPacket`, and
  `LlmAdvisoryRecommendation`;
- PG ledgers for events and recommendations;
- an application service that validates registered strategy families, calls an
  OpenAI-compatible provider, persists advisory output, and optionally pushes
  Feishu through the existing notification service;
- BRC Console API endpoints under `/api/brc/llm/advisory`;
- check constraints that keep advisory records non-authoritative and
  non-executing.

The enhanced implementation slice adds:

- an advisory inbox summary for Owner review of pushed, generated, blocked, and
  failed-push recommendations;
- reusable `LLMContextPacket` builders for market/runtime/strategy/audit/review
  facts, including right-tail trade review summaries;
- provider-output safety checks that block side, size, leverage, order,
  exchange, transfer, withdrawal, and live-ready instructions before persistence
  or push;
- push-only Feishu card templates for candidate review, FinalGate blockers,
  daily audit digests, market context, and closed-trade review;
- local fake provider, recording push adapter, in-memory repository, and eval
  harness so the advisory plane can be tested without real LLM credentials;
- explicit review notes and card-type metadata on advisory recommendations.

The event-auto and operator-facing enhancement slice adds:

- an advisory-only auto-publisher skeleton for `strategy_candidate_observed`,
  `final_gate_blocked`, `reconciliation_mismatch`, and `trade_closed` events;
- default allowed-action routing per event type so publisher-created events can
  explain market context, explain blockers, summarize audits, or review closed
  trades without creating execution authority;
- expanded local golden cases for registered strategy recommendations,
  unregistered strategy blocking, order-submit instruction blocking, sizing /
  leverage instruction blocking, provider errors, and push failures;
- Chinese-primary Feishu card text for candidate review, FinalGate blockers,
  audit digests, market context, and closed-trade review, while preserving the
  English hard-boundary phrases `Feishu is push-only` and `No ExecutionIntent`.

These additions remain outside the execution chain. They do not create
`SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`, `Order`, budget
mutation, exchange call, transfer, or withdrawal instruction.
