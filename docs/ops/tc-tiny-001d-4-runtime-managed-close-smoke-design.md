# TC-TINY-001D-4 Runtime-Managed Close Smoke Design

Date: 2026-05-25
Status: REVIEW

## Goal

Replace direct exchange cleanup in the controlled Binance testnet smoke with a
runtime-owned controlled close path. The smoke should validate the full
runtime lifecycle: controlled ENTRY, exchange-native protection mounting,
runtime-managed reduce-only close, position projection, daily stats,
local order terminalization, reconciliation, and final flat exchange state.

## Boundary

- Testnet only: `EXCHANGE_TESTNET=true`.
- Profile only: `RUNTIME_PROFILE=sim1_eth_runtime`.
- Symbol only: `ETH/USDT:USDT`.
- Max close quantity: the active controlled position quantity, capped at
  `0.01 ETH`.
- No request body may override symbol, side, quantity, order type, or price.
- Real live / mainnet execution is forbidden.
- Runtime profile, credentials, sizing defaults, and strategy parameters are
  out of scope.

## Implemented Runtime Shape

The narrow test endpoint is now implemented:

`POST /api/runtime/test/smoke/execute-controlled-close`

The endpoint:

1. Require local/internal access, `RUNTIME_CONTROL_API_ENABLED=true`, and
   `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.
2. Require `EXCHANGE_TESTNET=true` and `sim1_eth_runtime`.
3. Reject any non-empty request body.
4. Require exactly one active local controlled-smoke position for
   `ETH/USDT:USDT`.
5. Places one exchange-native reduce-only market close through
   `ExchangeGateway.place_order`.
6. Persists a local `EXIT` order before exchange submission, then advances it
   through existing lifecycle/projection services after exchange evidence.
7. Cancels or terminalizes remaining local/exchange protection orders only after
   the close is confirmed.
8. Emits a structured trace event with no secrets:
   `control.test_controlled_close`.
9. Enforces once-per-session execution separately from controlled entry.

Implemented artifacts:

- `ExecutionOrchestrator.execute_controlled_close()`.
- `POST /api/runtime/test/smoke/execute-controlled-close`.
- `OrderRole.EXIT` plus PG/ORM check-constraint migration support.
- `tests/unit/test_tiny001d4_controlled_close.py`.

## Acceptance

- Controlled close succeeds only on Binance testnet + `sim1_eth_runtime`.
- It cannot open or increase exposure; `reduce_only=True` is mandatory.
- It uses existing runtime services; it must not shell out to ccxt scripts.
- Position projection marks the local position closed and updates realized PnL.
- Daily risk stats closed-trade count increments for a full close.
- Periodic reconciliation reports no severe mismatch after the close.
- Final read-only Binance testnet check shows position amount `0` and open
  orders `0`.

## Implementation Ownership

Codex should own the first implementation because it touches execution-chain
service boundaries. Claude can later receive bounded tests after Codex defines
the final service method and allowed files.

## Stop Points

- If no existing lifecycle method can represent a runtime-managed close without
  abusing TP/SL roles, stop and add a small domain/lifecycle close role via a
  separate Codex-owned design.
- If Binance testnet returns partial fill or delayed market-close evidence,
  stop and add bounded confirmation/reconciliation handling before another
  smoke run.

## Current Verdict

`implemented_locally / awaiting_scoped_verification_and_testnet_authorization`

The runtime close blocker is cleared at implementation level. Phase 3 testnet
execution still requires local verification, PG schema readiness, read-only
testnet preflight, and a specific ADR-0009 Owner authorization.
