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

# PLC Phase 5D Two-Symbol Exchange Read-Only Rehearsal

Date: 2026-05-25
Status: REVIEW / EXCHANGE_READONLY_PASSED_AFTER_TESTNET_CLEANUP

## Boundary

Phase 5D is exchange-connected but read-only. It does not authorize real live
trading, mainnet order placement, order cancellation, order modification,
real-funds operation, runtime profile changes, credential changes, transfer,
withdrawal, multi-symbol execution runtime, portfolio routing, or
strategy-return optimization.

Owner authorized this Phase 5D action after Phase 5C. The authorization is
limited to BTC/ETH read-only visibility checks against Binance testnet using
the current credentials/profile environment.

## Goal

Move from local BTC/ETH synthetic proof to exchange-connected BTC/ETH
visibility proof without enabling multi-symbol trading.

The rehearsal checks:

- public market visibility for BTC and ETH;
- testnet ticker visibility through the project `ExchangeGateway`;
- testnet account position visibility per symbol;
- normal open-order visibility per symbol;
- conditional STOP order visibility per symbol;
- final state flat/no-open-orders before any future multi-symbol runtime
  discussion.

## Implemented Scope

- Added `two_symbol_exchange_rehearsal` read-only application module.
- Added tests proving:
  - flat/no-order BTC+ETH state passes;
  - any nonzero position, normal open order, or conditional open order fails
    the rehearsal.
- Used the official Binance plugin for public USDS futures BTCUSDT/ETHUSDT
  book-ticker visibility.
- Initial read-only rehearsal found BTC testnet orphan conditional orders while
  BTC position was flat.
- Under Owner's non-real-live authorization, executed a bounded testnet cleanup
  only after proving BTC position `0`, normal open orders `0`, and all 6
  conditional orders were reduce-only.
- Final BTC/ETH read-only rehearsal passed.

## Commands

Local verification:

```bash
python3 -m compileall -q \
  src/application/two_symbol_exchange_rehearsal.py \
  tests/unit/test_phase5d_two_symbol_exchange_rehearsal.py

pytest -q \
  tests/unit/test_phase5d_two_symbol_exchange_rehearsal.py
```

Authorized read-only Binance testnet rehearsal:

```bash
python3 - <<'PY'
# Load .env/.env.local, initialize ExchangeGateway(testnet=True), run
# run_two_symbol_readonly_rehearsal(gateway, symbols=["ETH/USDT:USDT",
# "BTC/USDT:USDT"]), print only non-secret summary fields, then close gateway.
PY
```

## Caps

- Environment: Binance testnet for project gateway checks.
- Symbols: `ETH/USDT:USDT`, `BTC/USDT:USDT`.
- Actions: read-only ticker, positions, normal open orders, conditional open
  orders.
- No order placement, cancellation, modification, runtime profile change, or
  config mutation.

## Stop Conditions

Stop and do not proceed to any runtime/profile step if:

- exchange initialization fails;
- either ticker is unavailable or non-positive;
- either symbol has nonzero position;
- either symbol has normal open orders;
- either symbol has conditional open orders;
- gateway cannot close cleanly.

## Rollback

No exchange mutation is performed, so rollback is process cleanup only:

- close the gateway;
- do not start runtime;
- do not change profile/config;
- report the failed read-only condition.

Cleanup exception executed during this task:

- canceled 6 BTC testnet reduce-only orphan conditional orders after read-only
  preflight proved flat BTC position and no normal BTC open orders;
- final BTC position remained `0`, normal open orders `0`, conditional open
  orders `0`;
- no runtime was started and no profile/config was changed.

## Completion Evidence

Official Binance plugin public USDS futures book ticker:

- `ETHUSDT` returned bid/ask book ticker.
- `BTCUSDT` returned bid/ask book ticker.

Initial project Binance testnet read-only rehearsal:

- ETH: position `0`, normal open orders `0`, conditional open orders `0`;
- BTC: position `0`, normal open orders `0`, conditional open orders `6`;
- verdict: `phase5d_two_symbol_exchange_readonly_needs_cleanup`.

Bounded BTC testnet cleanup:

- canceled 6 BTC reduce-only orphan conditional orders:
  `1000000047775774`, `1000000047775957`, `1000000047779744`,
  `1000000047779975`, `1000000048741712`, `1000000048741904`;
- final BTC position `0`, normal open orders `0`, conditional open orders `0`.

Final project Binance testnet read-only rehearsal:

- ETH ticker visible, position `0`, normal open orders `0`, conditional open
  orders `0`;
- BTC ticker visible, position `0`, normal open orders `0`, conditional open
  orders `0`;
- verdict: `phase5d_two_symbol_exchange_readonly_passed`.

## Verdict

`phase5d_two_symbol_exchange_readonly_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`
