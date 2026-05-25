# PLC Phase 3 ADR-0009 Authorization Request

Status: DRAFT / DO NOT EXECUTE

This is the reusable authorization request for one future PLC Phase 3 Binance
testnet rehearsal. It is intentionally not approved by being committed.

## Requested Action

Authorize one bounded PLC Phase 3 Binance testnet rehearsal cycle after all
listed preconditions pass.

## Intended Mode

Binance testnet controlled runtime rehearsal.

## Exact Operational Steps

1. Verify git commit and clean worktree.
2. Run targeted local tests.
3. Run Binance testnet read-only preflight for `ETH/USDT:USDT`.
4. Start local runtime with:
   - `RUNTIME_PROFILE=sim1_eth_runtime`
   - `EXCHANGE_TESTNET=true`
   - `RUNTIME_CONTROL_API_ENABLED=true`
   - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`
5. Confirm startup guard, GKS, and protection-health state.
6. Call `POST /api/runtime/test/smoke/execute-controlled-entry` once.
7. Verify ENTRY and protection mounting.
8. Call `POST /api/runtime/test/smoke/execute-controlled-close` once.
9. Verify projection, daily stats, terminalization, and reconciliation.
10. Verify Binance testnet final read-only state: position `0`, open orders
    `0`.
11. Restore safe control state and stop runtime.

## External Systems Touched

- Binance testnet only.
- Local PostgreSQL runtime database.
- Local runtime process.

## Credentials / Account State / Orders

- Credentials: Binance testnet API credentials only.
- Account state: Binance testnet read/write only for the bounded controlled
  cycle.
- Orders: maximum one controlled ENTRY, native protection orders, one
  reduce-only controlled close.
- Transfers or withdrawals: none.

## Caps

- Symbol: `ETH/USDT:USDT`.
- Maximum controlled amount: `0.01 ETH`.
- Maximum endpoint calls: one entry and one close per runtime session.
- Runtime profile: `sim1_eth_runtime` only.

## Required Verification Before Requesting Owner Approval

- PLC paper observation tests pass.
- Controlled entry tests pass.
- Controlled close tests pass.
- Reconciliation/protection-health tests pass.
- `compileall` passes for touched modules.
- `git diff --check` passes.
- Binance testnet read-only preflight returns no active position and no open
  orders for `ETH/USDT:USDT`.

## Stop Conditions

- Wrong runtime profile or `EXCHANGE_TESTNET=false`.
- Active testnet position or open orders before start.
- Startup guard/GKS/protection-health gates are not in expected state.
- ENTRY does not mount confirmed SL.
- Controlled close fails, is not reduce-only, or cannot be confirmed.
- Reconciliation severe mismatch remains after bounded refresh.
- Any real live/mainnet endpoint or credential is detected.

## Rollback

1. Stop runtime.
2. Keep or restore GKS active.
3. Prefer runtime-managed close if a testnet position exists.
4. If runtime-managed close is unavailable, stop and request separate Owner
   authorization for emergency direct testnet cleanup.
5. Preserve logs, trace events, PG rows, and final read-only exchange state for
   review.

## Owner Approval Phrase

Use a specific approval such as:

`Authorize PLC Phase 3 under ADR-0009: one Binance testnet controlled rehearsal, sim1_eth_runtime only, max 0.01 ETH, one entry and one reduce-only close, restore safe state and stop runtime after verification.`
