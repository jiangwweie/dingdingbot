# ADR-0009 Non-Real-Live Execution Authorization Boundary

## Status

Accepted

Date: 2026-05-25

Runtime effect: boundary clarification only

Trading permission effect: no real live trading permission

## Context

The previous Personal Leveraged Campaign and Live-safe documents used a
conservative docs/design/sandbox-only boundary for the current stage. The Owner
has now clarified that the absolute prohibition is real live trading, not all
runtime or testnet work.

The project still needs explicit gates because runtime, paper, testnet, and
tiny-live style work can mutate state, contact external services, or create
operational risk even when no real live capital is used.

## Decision

All development and research work except real live trading may be executed when
it satisfies both conditions:

1. reasonable scoped testing or verification has been completed for the work;
2. Codex requests and receives explicit Owner authorization for the specific
   runtime, paper, testnet, tiny-live, exchange-connectivity, or account-action
   step before executing it.

Real live trading remains prohibited unless the Owner later gives a separate
explicit real-live authorization decision.

## Required Gate For Non-Real-Live Execution

Before executing a non-real-live runtime or exchange-connected step, the request
to Owner must state:

- intended mode: local runtime, demo, paper, testnet, tiny-live, read-only
  exchange sync, or other non-real-live mode;
- exact command, endpoint, script, or operational step;
- expected external systems touched;
- whether credentials, account state, orders, cancellations, transfers, or
  withdrawals are involved;
- maximum order/action count and maximum notional or abstract cap when orders
  are involved;
- verification already run;
- stop condition and rollback path.

## Still Prohibited Without Separate Real-Live Authorization

- real live trading;
- live exchange order placement, modification, or cancellation;
- live transfer, withdrawal, or rebalancing;
- enabling real trading permission on a real-money account;
- deploying a runtime connected to real funds;
- treating LLM/agent output as an autonomous buy/sell/short/size/leverage
  decision.

## Consequences

- Runtime, paper, testnet, tiny-live, and read-only exchange-sync work are not
  globally blocked anymore.
- Each such execution still requires scoped verification and Owner approval at
  the action boundary.
- Existing docs-only or local-sandbox artifacts remain local until a promotion
  request explicitly names the next non-real-live execution mode.
- The promotion gate should distinguish `not yet promoted` from `forbidden`.
