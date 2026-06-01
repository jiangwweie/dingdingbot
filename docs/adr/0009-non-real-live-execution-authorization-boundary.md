# ADR-0009 Non-Real-Live Execution Authorization Boundary

## Status

Accepted

Date: 2026-05-25

Runtime effect: boundary clarification only

Trading permission effect: no real live trading permission

2026-06-01 amendment: supersedes the original requirement that every
non-real-live runtime/testnet/account-action step must request separate Owner
authorization. Current agent baseline distinguishes real live / real funds from
testnet/dev/readiness/controlled rehearsal work.

## Context

The previous Personal Leveraged Campaign and Live-safe documents used a
conservative docs/design/sandbox-only boundary for the current stage. The Owner
has now clarified that the absolute prohibition is real live trading, not all
runtime or testnet work.

The project still needs explicit gates because runtime, paper, testnet, and
tiny-live style work can mutate state, contact external services, or create
operational risk even when no real live capital is used. Those gates are now
implemented as scoped verification, profile checks, safety gates, and hard
live/real-funds boundaries rather than a blanket Owner-authorization stop for
every testnet/dev action.

## Decision

All development and research work except real live trading may be executed when
it satisfies scoped safety verification:

1. reasonable scoped testing or verification has been completed for the work;
2. the work is not real live trading and does not place real-funds orders;
3. profile, symbol, side, cap, protection, exit/cleanup, logging, GKS, and
   credential safety gates pass where applicable.

Real live trading remains prohibited unless the Owner later gives a separate
explicit real-live authorization decision.

## Required Gate For Real Live / Real Funds

Before executing any real live or real-funds order step, the request to Owner
must state:

- intended mode and whether real funds are touched;
- exact command, endpoint, script, or operational step;
- expected external systems touched;
- whether credentials, account state, orders, cancellations, transfers, or
  withdrawals are involved;
- maximum order/action count and maximum notional or abstract cap when orders
  are involved;
- verification already run;
- stop condition and rollback path.

## Non-Real-Live Execution Handling

Testnet, dev, readiness, controlled rehearsal, PG non-live, console/API, and
profile-scoped cleanup/reset/repair work does not require an additional Owner
authorization step merely because it touches execution-chain concepts.

Agents must classify blockers before stopping:

- live / real-funds: hard stop unless separate explicit Owner authorization
  exists;
- testnet / dev / profile-scoped: inspect scope, safely repair/reset/cleanup
  where bounded, and continue;
- unknown unsafe: investigate; block only if safety cannot be established.

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
- Such work requires scoped verification and applicable hard safety gates, not a
  blanket Owner authorization step.
- Existing docs-only or local-sandbox artifacts remain local until a promotion
  request explicitly names the next non-real-live execution mode.
- The promotion gate should distinguish `not yet promoted` from `forbidden`.
