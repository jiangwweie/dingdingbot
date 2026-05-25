# PLC Phase 5E Controlled Multi-Symbol Testnet Runtime Rehearsal

Date: 2026-05-25
Status: REVIEW / ETH_AND_BTC_TESTNET_LEGS_PASSED

## Boundary

Phase 5E is a design and authorization package for a controlled BTC/ETH
Binance testnet runtime rehearsal.

This document does not authorize real live trading, mainnet order placement,
real-funds operation, credential changes, live profile changes, transfer,
withdrawal, portfolio routing, strategy-return optimization, or autonomous
agent/LLM trade decisions.

Owner authorized Phase 5E implementation and bounded Binance testnet rehearsal
after this design was drafted. The authorization remains limited to the caps,
stop conditions, and rollback path in this document.

Owner later approved Binance testnet operations without the previous
minimum-capital limitation. This approval is interpreted as testnet-only
permission to raise the Phase 5E BTC controlled amount/cap enough to satisfy
Binance testnet minimum-notional constraints. It does not authorize real live,
mainnet, real funds, withdrawal, transfer, or generic strategy sizing changes.

## Why Phase 5E Exists

Phase 5C proved local BTC/ETH symbol filtering. Phase 5D proved BTC/ETH
exchange read-only visibility and cleaned stale BTC testnet conditional orders.

The next risk is not market edge. The next risk is whether one runtime process
can safely observe and manage two symbols under explicit caps without leaking
state between symbols or leaving testnet exposure/order residue.

## Current Blockers

The current runtime remains single-symbol by construction:

- `MarketRuntimeConfig` exposes `symbols` as `[primary_symbol]`;
- runtime warmup, subscriptions, order watch, and reconciliation are driven
  from that single-symbol market scope;
- controlled entry/close endpoints are hard-coded to `ETH/USDT:USDT`,
  `sim1_eth_runtime`, and one entry/close per process;
- existing Phase 5B rehearsal used separate runtime processes because the
  endpoint intentionally has once-per-session guards.

Phase 5E therefore must not be framed as "just change `RUNTIME_PROFILE`".
It needs a small, explicit runtime-profile/config design.

## Recommended Shape

Use one new inactive, readonly runtime profile for testnet rehearsal:

`phase5e_btc_eth_testnet_runtime`

Do not modify `sim1_eth_runtime`.

Add minimal multi-symbol market scope while preserving the old single-symbol
profile shape:

- keep `primary_symbol` for legacy strategy binding and log summaries;
- add optional `symbols`, defaulting to `[primary_symbol]` for old profiles;
- validate `primary_symbol in symbols`;
- derive warmup/subscription pairs as `symbols x {primary_timeframe,
  mtf_timeframe}`;
- keep strategy output deterministic and server-controlled for this rehearsal;
- do not introduce a portfolio router or strategy router.

Controlled rehearsal endpoints should be server-side only:

- allowed profile: `phase5e_btc_eth_testnet_runtime`;
- allowed symbols: `ETH/USDT:USDT`, `BTC/USDT:USDT`;
- allowed direction: `LONG`;
- allowed mode: controlled testnet entry and runtime-managed reduce-only close;
- no request body for side, amount, price, stop loss, take profit, leverage, or
  symbol list;
- per-symbol once guards replace the current process-global ETH-only guard;
- all emitted trace metadata must include symbol, profile, cap, order-count,
  and testnet fields.

## Rehearsal Flow

Phase 5E should use one runtime process and sequential symbol exposure:

1. Preflight BTC/ETH read-only state.
2. Start runtime with `RUNTIME_PROFILE=phase5e_btc_eth_testnet_runtime`,
   `EXCHANGE_TESTNET=true`, `BACKEND_PORT=8001`,
   `RUNTIME_CONTROL_API_ENABLED=true`, and
   `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.
3. Verify runtime safe summary shows both symbols and testnet mode.
4. Arm startup guard, disable GKS only for the bounded entry window, and arm
   campaign state for ETH.
5. Execute one controlled ETH entry.
6. Verify ETH active position and protection visibility while BTC remains flat
   and no BTC orders exist.
7. Execute one runtime-managed ETH close and verify ETH flat / orders `0`.
8. Restore ETH controls to safe state.
9. Repeat the same sequence for BTC in the same runtime process.
10. Run final BTC/ETH read-only inventory, reconciliation/read-model checks,
    control restoration, and runtime shutdown.

First 5E rehearsal should not hold BTC and ETH simultaneously. A later phase
can request simultaneous two-symbol exposure only after this sequential
single-process rehearsal passes.

## Caps

Environment and profile caps:

- environment: Binance testnet only;
- profile: `phase5e_btc_eth_testnet_runtime` only;
- process count: one runtime process;
- symbols: exactly `ETH/USDT:USDT` and `BTC/USDT:USDT`;
- directions: `LONG` only;
- leverage: `1x`;
- cycles: one ETH cycle and one BTC cycle;
- simultaneous open positions: `1` maximum;
- real live order authority: `0`.

Exposure caps:

- ETH max amount: `0.01 ETH`;
- ETH max controlled notional: `25 USDT`;
- BTC amount: `0.002 BTC`;
- BTC max controlled notional: `250 USDT`;
- combined BTC+ETH open exposure cap: `250 USDT` because exposure is
  sequential and at most one symbol may be open at a time;
- account-risk total-exposure gate must remain enabled and must block a new
  entry if total exposure exceeds the configured cap before the next entry.
- runtime `daily_max_trades` may stay at `10` for this rehearsal because the
  current daily stats scope is shared with earlier same-day testnet smokes;
  Phase 5E order count is enforced by per-symbol once guards and explicit
  order-count caps.

If Binance testnet minimum order constraints require BTC notional above
`250 USDT`, BTC entry must be skipped and the rehearsal verdict becomes
`phase5e_btc_leg_blocked_by_min_notional`, not a failed workaround.

Order-count caps:

- per symbol: at most one controlled ENTRY submission;
- per symbol: at most two TP submissions;
- per symbol: at most one SL submission;
- per symbol: at most one runtime-managed reduce-only CLOSE submission;
- per symbol max order submissions: `5`;
- per symbol max open exchange orders during active exposure: `3` reduce-only
  protection orders;
- per symbol final open exchange orders: `0`;
- account-level final local active orders: `0`.

The implementation must fail closed if observed local or exchange order counts
exceed these caps.

## Stop Conditions

Stop before any order action if:

- `EXCHANGE_TESTNET` is not true;
- profile is not `phase5e_btc_eth_testnet_runtime`;
- runtime safe summary does not contain exactly ETH and BTC;
- either symbol has preflight nonzero position;
- either symbol has preflight normal or conditional open orders;
- GKS, startup guard, campaign state, account-risk, protection-health, or
  circuit-breaker state cannot be read or restored;
- account balance, positions, mark price, liquidation price, or total exposure
  cannot be read for account-risk evaluation;
- BTC min-notional requires notional above `250 USDT`.
- BTC feasibility reports `next_viable_amount`, `next_viable_notional`, and
  `cap_shortfall` whenever the fixed BTC leg is not feasible. These
  fields are decision evidence only; they do not raise caps or resize orders.

Stop during the rehearsal if:

- controlled entry is blocked or partially ambiguous;
- controlled close is not `FILLED`;
- a symbol has more than one active local position;
- the non-active symbol gains any local or exchange position/order;
- any symbol exceeds the exposure cap or order-count cap;
- missing-stop or orphan protection-health block appears;
- reconciliation reports severe mismatch after the close/recovery window;
- daily stats, projection, terminalization, or read-model updates are missing
  after a runtime-managed close;
- runtime shutdown requires force kill or port `8001` is not released.

## Rollback Path

Profile/config rollback:

- keep `sim1_eth_runtime` unchanged;
- seed `phase5e_btc_eth_testnet_runtime` only after Owner approval, readonly
  and inactive by default;
- start 5E only by setting process-local `RUNTIME_PROFILE`;
- after rehearsal, return process env to `RUNTIME_PROFILE=sim1_eth_runtime`;
- do not delete or mutate profiles unless Owner separately requests cleanup.

Runtime/control rollback:

- set GKS active;
- reset startup guard to blocked;
- reset campaign state to `observe`;
- stop the runtime process;
- verify no `src.main` process remains and port `8001` is released.

Exchange/testnet rollback:

- preferred path: use runtime-managed reduce-only close for any open controlled
  position;
- if runtime close cannot execute, stop new entries, keep GKS active, collect
  read-only inventory, and request Owner approval for a bounded direct
  reduce-only testnet cleanup;
- cancel protection orders only after the exchange position is flat or after
  they are proven reduce-only orphan conditionals;
- final BTC/ETH read-only inventory must show positions `0`, normal open
  orders `0`, and conditional open orders `0`.

Local-state rollback:

- run reconciliation/read-model refresh for both symbols;
- terminalize stale local protection rows only through existing reconciliation
  hygiene paths;
- record any unresolved local rows as a blocker before another runtime action.

## Implementation Slices

Recommended sequence:

1. Add multi-symbol runtime profile contract support while preserving old
   single-symbol profiles.
2. Add a dry-run profile seed script for
   `phase5e_btc_eth_testnet_runtime`; default must print only.
3. Generalize controlled test endpoints from ETH-only globals to
   server-controlled per-symbol specs for ETH and BTC under the Phase 5E
   profile.
4. Add pure cap/order-count tests for ETH and BTC controlled specs.
5. Add runtime-scope tests proving warmup/order-watch/reconciliation receive
   both symbols.
6. Only after tests pass, request Owner authorization for one bounded Binance
   testnet rehearsal.

Implemented in this slice:

- added optional multi-symbol market scope to `MarketRuntimeConfig` while
  preserving legacy single-symbol profiles;
- added dry-run-by-default `scripts/seed_phase5e_profile.py`;
- seeded readonly inactive profile `phase5e_btc_eth_testnet_runtime`;
- added Phase 5E server-controlled BTC/ETH test endpoints:
  - `POST /api/runtime/test/phase5e/eth/execute-controlled-entry`;
  - `POST /api/runtime/test/phase5e/eth/execute-controlled-close`;
  - `POST /api/runtime/test/phase5e/btc/execute-controlled-entry`;
  - `POST /api/runtime/test/phase5e/btc/execute-controlled-close`;
- preserved legacy ETH-only `sim1_eth_runtime` controlled endpoints;
- added unit tests for multi-symbol config validation and Phase 5E endpoint
  gates/caps.
- follow-up hardening after BTC was blocked:
  - added pure `phase5e_rehearsal_feasibility` cap/min-notional assessment;
  - added read-only feasibility endpoint
    `GET /api/runtime/test/phase5e/{eth|btc}/feasibility`;
  - changed Phase 5E entry to reuse the same feasibility result before any
    order path is reached.
  - added `ExchangeGateway.get_min_notional(symbol)` so feasibility can use
    already-loaded exchange market metadata before falling back to defaults.

Core files likely affected by implementation:

- `src/application/runtime_config.py`;
- `src/main.py`;
- `src/interfaces/api_console_runtime.py`;
- `src/application/account_risk_service.py` only if the current account-risk
  cap wiring is insufficient;
- `src/infrastructure/exchange_gateway.py` only if order-watch/reconciliation
  two-symbol startup exposes a real gateway lifecycle issue.

## Verification Before Authorization

Required local checks before asking to run testnet:

```bash
python3 -m compileall -q \
  src/application/runtime_config.py \
  src/interfaces/api_console_runtime.py \
  src/main.py

pytest -q \
  tests/unit/test_phase5e_multi_symbol_runtime_config.py \
  tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py \
  tests/unit/test_phase5c_two_symbol_fixture.py \
  tests/unit/test_phase5d_two_symbol_exchange_rehearsal.py \
  tests/unit/test_p4_account_risk_service.py \
  tests/unit/test_tiny001d4_controlled_close.py

git diff --check
```

Authorization request must state exact profile, symbols, caps, order counts,
stop conditions, rollback path, and whether the BTC leg is allowed to skip when
minimum notional exceeds the cap.

## Owner Decision Needed

Resolved by Owner authorization for this turn:

- approve or revise the new profile name;
- approve the BTC cap of `250 USDT` or provide a different cap;
- confirm first 5E rehearsal is sequential single-process, not simultaneous
  BTC+ETH exposure;
- confirm BTC leg should skip rather than raise cap if Binance testnet minimum
  notional exceeds `250 USDT`.

## Completion Evidence

Local verification:

- `python3 -m compileall -q src/application/runtime_config.py src/interfaces/api_console_runtime.py scripts/seed_phase5e_profile.py tests/unit/test_phase5e_multi_symbol_runtime_config.py tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
  passed;
- `pytest -q tests/unit/test_phase5e_multi_symbol_runtime_config.py tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
  passed with 11 tests;
- targeted regression passed with 42 tests:
  `tests/unit/test_tiny001d1a_controlled_signal_injection.py`,
  `tests/unit/test_tiny001d4_controlled_close.py`,
  `tests/unit/test_phase5c_two_symbol_fixture.py`,
  `tests/unit/test_phase5d_two_symbol_exchange_rehearsal.py`,
  `tests/unit/test_p4_account_risk_service.py`;
- after feasibility hardening, targeted local verification passed with 43
  tests:
  `tests/unit/test_phase5e_rehearsal_feasibility.py`,
  `tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`,
  `tests/unit/test_tiny001d1a_controlled_signal_injection.py`,
  `tests/unit/test_tiny001d4_controlled_close.py`;
- after ExchangeGateway min_notional metadata hardening, targeted local
  verification passed with 23 tests:
  `tests/unit/test_phase5e_exchange_gateway_min_notional.py`,
  `tests/unit/test_phase5e_rehearsal_feasibility.py`,
  `tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`,
  `tests/unit/test_tiny001d1b_sl_confirmation.py`;
- `git diff --check` passed before runtime rehearsal.

Read-only Binance testnet preflight:

- ETH ticker visible, position `0`, normal open orders `0`, conditional open
  orders `0`;
- BTC ticker visible, position `0`, normal open orders `0`, conditional open
  orders `0`.

Runtime startup:

- started one runtime process on port `8001` with
  `RUNTIME_PROFILE=phase5e_btc_eth_testnet_runtime`;
- runtime resolved profile version `2`, hash `8c0f633708379804`;
- safe summary showed symbols `ETH/USDT:USDT` and `BTC/USDT:USDT`;
- warmup loaded `4/4` symbol/timeframe pairs;
- order-watch started for both ETH and BTC;
- startup reconciliation candidates `0`, failures `0`.

ETH leg:

- armed startup guard, disabled GKS only for the bounded window, and set
  campaign state to `armed`;
- controlled ETH entry succeeded:
  - intent `intent_fca06be68891`;
  - signal `sig_39cb35ab8b3e`;
  - amount `0.01`;
  - notional `21.1736`;
  - profile `phase5e_btc_eth_testnet_runtime`;
- mid-leg API state showed ETH active position `0.01` and BTC positions/orders
  empty;
- controlled ETH runtime close succeeded:
  - close order `exit_controlled_18ff201e1ec3`;
  - exchange order `8728698638`;
  - amount `0.01`;
  - average execution price `2117.18`;
  - terminalized protection orders `3`;
- daily risk stats updated trade count from `7` to `8`.

BTC leg:

- after ETH close, controls were restored to safe state, then re-armed for BTC;
- BTC controlled entry was blocked before order placement:
  `controlled entry notional below min_notional (77.5506 < 100, source=default)`;
- no BTC order was placed and no BTC position was opened;
- cap was not raised.

Final state:

- GKS restored active;
- startup guard blocked;
- campaign state restored to `observe`;
- direct Binance testnet read-only final check passed:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `0`;
- PG active positions `[]`;
- PG ETH/BTC open orders `[]`;
- runtime stopped naturally and port `8001` was released.

Operational note:

- `/api/runtime/positions` briefly showed a stale ETH position after close
  because the runtime account snapshot cache had not refreshed yet; direct
  Binance read-only state and PG repositories were flat.
- The BTC min-notional blocker is now visible through a read-only feasibility
  preflight before arming a new entry window. This does not raise BTC cap or
  authorize a retry.
- Feasibility now prefers loaded exchange market metadata through
  `ExchangeGateway.get_min_notional(symbol)`; defaults remain only a fallback
  when the gateway cannot expose minNotional.
- BTC blocker handling was tightened after the first rehearsal: the same
  feasibility response now includes the next exchange-step quantity needed to
  satisfy min-notional, its estimated notional, and any shortfall above the
  previous `130 USDT` cap. For the observed blocked price `77550.6`, the next
  `0.001 BTC` step is `0.002 BTC`, estimated notional `155.1012 USDT`, and cap
  shortfall `25.1012 USDT`. This remains an Owner decision gate, not an
  automatic cap increase.
- BTC blocker was then resolved for a bounded testnet retry after Owner
  approved testnet operations without the prior minimum-capital limitation.
  Phase 5E BTC controlled amount is now `0.002 BTC` with max controlled
  notional `250 USDT`; feasibility remains the pre-entry gate and real live is
  still unauthorized.

BTC retry evidence:

- read-only preflight before retry:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `0`;
- runtime feasibility before entry:
  - amount `0.002 BTC`;
  - price `77392.5`;
  - notional `154.7850`;
  - min_notional `50.0`, source `get_min_notional`;
  - max_notional `250`;
  - feasible `true`;
- controlled BTC entry succeeded:
  - intent `intent_ed2c999769bd`;
  - signal `sig_929aabc7d2ce`;
  - amount `0.002`;
  - entry price `77391.8`;
  - notional `154.7836`;
  - status `completed`;
- active BTC exposure after entry:
  - position quantity `0.002`;
  - exposure `154.812`;
  - protection orders `3` (`TP1`, `TP2`, `SL`);
- controlled BTC runtime close succeeded:
  - close order `exit_controlled_657fa92707ee`;
  - exchange order `13192655923`;
  - amount `0.002`;
  - average execution price `77396.67`;
  - terminalized protection orders `3`;
- daily risk stats updated to trade_count `9` with cumulative realized PnL
  `-0.015260000000000000000`;
- final direct Binance testnet read-only check:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `0`;
- final PG active positions `[]`;
- final PG ETH/BTC open orders `[]`;
- controls restored:
  - GKS active;
  - startup guard blocked;
  - campaign state `observe`;
- runtime stopped via SIGTERM shutdown path and port `8001` was released.
- During evidence review, console order read-model side mapping was fixed so
  enum directions such as `Direction.LONG` display as `BUY` instead of a false
  `SELL` fallback.
- Runtime positions read-model was hardened after the stale snapshot
  observation: when PG active-position lookup succeeds, PG active lifecycle is
  treated as authoritative for position existence and account snapshot is used
  only to enrich active PG rows. This prevents a stale snapshot-only position
  from reappearing in `/api/runtime/positions` after a runtime-managed close.
- Daily risk stats scope was intentionally kept account-level:
  `runtime:default` is shared across `sim1_eth_runtime` and
  `phase5e_btc_eth_testnet_runtime`. Phase 5E session isolation relies on
  endpoint once guards, fixed exposure/order caps, and control restoration, not
  on splitting daily risk aggregates by profile.
- Added read-only Phase 5E inventory endpoint for future preflight/final
  flatness checks:
  `GET /api/runtime/test/phase5e/inventory`.
  It reports, per ETH/BTC symbol, exchange position count, exchange normal
  open-order count, exchange conditional open-order count, PG active-position
  count, PG open-order count, per-symbol flatness, and account-level
  `all_flat`. It does not place, close, cancel, or resize orders.

## Verdict

`phase5e_eth_leg_passed / phase5e_btc_leg_passed / final_exchange_flat / final_pg_flat / controls_restored / runtime_stopped / real_live_not_authorized`
