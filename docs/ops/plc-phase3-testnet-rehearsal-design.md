# PLC Phase 3 Testnet Rehearsal Design

Date: 2026-05-25
Status: DESIGN / NOT AUTHORIZED FOR EXECUTION

## Goal

Define a bounded Binance testnet rehearsal for the Personal Leveraged Campaign
chain after Phase 2 paper observation packets. This document is a design and
authorization package only. It does not execute testnet, place orders, cancel
orders, modify runtime profiles, or authorize real live trading.

## Rehearsal Thesis

Phase 3 should prove that a reviewed PLC paper observation can be rehearsed
through runtime safety gates without giving PLC autonomous order authority.

The rehearsal validates plumbing and safety behavior, not strategy edge:

`PaperObservationPacket -> reviewed testnet rehearsal request -> runtime-owned controlled entry/close path -> order lifecycle -> protection -> position projection -> daily stats -> reconciliation -> final flat testnet state`

## Hard Boundary

- Real live trading: forbidden.
- Mainnet order placement/cancellation: forbidden.
- Runtime profile changes: forbidden.
- Exchange credentials changes: forbidden.
- Strategy parameter tuning or return optimization: forbidden.
- LLM/agent output as autonomous buy/sell/short/size/leverage decision:
  forbidden.
- PLC paper packets cannot directly place orders. They can only nominate a
  bounded rehearsal candidate after Owner authorization.

## Required Preconditions

Phase 3 execution must not start until all are true:

1. Phase 2 paper observation packet implementation is reviewed.
2. `TC-TINY-001D-4` runtime-managed controlled close is implemented and tested.
3. Campaign risk state machine is specified at least to design-review quality.
4. Account risk/liquidation safety checks are specified at least to
   design-review quality.
5. Local verification passes:
   - PLC paper observation tests;
   - controlled entry tests;
   - controlled close tests;
   - reconciliation/protection-health tests.
6. Binance testnet read-only preflight shows no active position and no open
   orders for the rehearsal symbol.
7. Owner explicitly authorizes the exact ADR-0009 action request for one
   rehearsal cycle.

## Proposed Rehearsal Scope

Default rehearsal:

- Mode: Binance testnet.
- Profile: `sim1_eth_runtime`.
- Symbol: `ETH/USDT:USDT`.
- Direction: runtime-controlled only. PLC packet may identify the candidate
  contract, but runtime test endpoint owns the side and amount.
- Max endpoint calls: one controlled entry and one controlled close per runtime
  session.
- Max test amount: `0.01 ETH`.
- Max order count: one ENTRY, exchange-native protection orders, one
  reduce-only controlled close, plus required cleanup/terminalization.
- Expected final state: exchange position `0`, open orders `0`, local active
  position closed, no severe reconciliation mismatch.

## Runtime Shape

No PLC packet should call `ExecutionOrchestrator` directly.

The rehearsal should use test-only runtime endpoints:

1. Existing controlled entry:
   `POST /api/runtime/test/smoke/execute-controlled-entry`
2. Required controlled close:
   `POST /api/runtime/test/smoke/execute-controlled-close`

The close endpoint remains a blocker until implemented. Direct ccxt cleanup is
not acceptable for PLC Phase 3 because the rehearsal must validate the runtime
close/projection/daily-stats path.

## ADR-0009 Action Request Template

Before execution, request Owner authorization with:

- Intended mode: Binance testnet controlled PLC rehearsal.
- Exact commands/endpoints:
  - start local runtime with `RUNTIME_PROFILE=sim1_eth_runtime`,
    `EXCHANGE_TESTNET=true`,
    `RUNTIME_CONTROL_API_ENABLED=true`, and
    `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`;
  - call controlled entry once;
  - call controlled close once;
  - run read-only reconciliation/status checks;
  - stop runtime.
- External systems touched: Binance testnet only.
- Credentials: Binance testnet API credentials only.
- Orders: maximum one controlled ENTRY, native TP/SL protection, one
  reduce-only close.
- Maximum size: `0.01 ETH`.
- Transfers/withdrawals: none.
- Verification already run: list exact pytest/compile/read-only preflight
  commands.
- Stop conditions:
  - runtime starts with wrong profile or `EXCHANGE_TESTNET=false`;
  - GKS/startup/protection-health gates fail;
  - preflight detects active exchange position or open orders;
  - controlled entry does not mount SL;
  - controlled close fails or is partial/delayed beyond bounded confirmation;
  - reconciliation severe mismatch remains after bounded cleanup.
- Rollback path:
  - stop runtime;
  - keep GKS active;
  - use runtime-managed close if position exists;
  - only if runtime-managed close is unavailable and Owner separately
    authorizes emergency testnet cleanup, use direct testnet cleanup;
  - preserve logs and PG rows for review.

## Evidence To Capture

- Git commit hash.
- Runtime profile and `EXCHANGE_TESTNET=true` proof.
- Paper observation packet id and review status.
- Controlled entry response.
- Controlled close response.
- Order ids and statuses.
- Protection SL confirmation evidence.
- Position projection and daily stats update.
- Periodic reconciliation summary.
- Binance testnet final read-only state.
- Runtime shutdown proof.

## Binance Official Plugin Use

When available, prefer the installed Binance official plugin for read-only
market/testnet state checks or metadata lookups. Do not use it to bypass the
runtime lifecycle for order placement, cancellation, or cleanup.

## Ownership

Codex owns Phase 3 design and first rehearsal review because it crosses PLC,
runtime safety, and execution lifecycle boundaries. Claude can receive bounded
tests only after Codex implements the controlled close interface and writes a
small task card with allowed files.

## Current Verdict

`phase3_design_ready / execution_blocked`

The design is ready for review, but execution remains blocked by:

- missing runtime-managed controlled close implementation;
- campaign risk state machine still TODO;
- account risk/liquidation safety still TODO;
- no specific Owner authorization for a Phase 3 rehearsal cycle yet.
