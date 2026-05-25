# PLC Phase 5B Repeated Testnet Rehearsal

Date: 2026-05-25
Status: REVIEW / REPEATED_TESTNET_PASSED

## Boundary

Phase 5B is still non-real-live. It does not authorize real live trading,
mainnet order placement, real-funds operation, runtime profile changes,
credential changes, transfer, withdrawal, multi-symbol runtime, portfolio
routing, or strategy-return optimization.

Owner authorized this Phase 5B bounded Binance testnet run. The authorization
is limited to repeated controlled testnet rehearsal under the existing
`sim1_eth_runtime` profile and existing runtime-controlled test endpoints.

## Goal

Prove that Phase 5A gates remain clean across repeated runtime processes and
that the next multi-symbol step is still blocked until symbol-isolation evidence
is stronger.

## Phase 5B Scope

Implemented in this slice:

- order-watch runtime state now tracks symbol-specific running flags while
  retaining the legacy global shutdown flag;
- recent order-update evidence is indexed by symbol before order confirmation,
  preventing same-id cross-symbol overwrite from being treated as confirmation
  evidence;
- added a pure Phase 5B symbol-isolation audit report that marks
  order-watch/cache checks as passed, reconciliation/read-model checks as
  review, and multi-symbol runtime as blocked;
- repeated Binance testnet rehearsal will run as separate runtime processes
  because the controlled endpoint intentionally enforces one entry and one
  close per process.
- repeated Binance testnet rehearsal passed with 2 cycles.

## Commands

Local verification:

```bash
python3 -m compileall -q \
  src/infrastructure/exchange_gateway.py \
  src/application/runtime_symbol_isolation_audit.py \
  tests/unit/test_phase5b_symbol_isolation.py

pytest -q \
  tests/unit/test_phase5b_symbol_isolation.py \
  tests/unit/test_ls001_order_watch_runtime.py \
  tests/unit/test_tm003_order_update_parse_observability.py \
  tests/unit/test_tiny001d1b_sl_confirmation.py
```

Integration regression:

```bash
pytest -q \
  tests/unit/test_arch_p4_runtime_context.py \
  tests/unit/test_p4_account_risk_service.py \
  tests/unit/test_p4_campaign_state_service.py \
  tests/unit/test_gks_v0_global_kill_switch.py \
  tests/unit/test_ls003a_reconciliation_read_model.py \
  tests/unit/test_tiny001d1b_sl_confirmation.py \
  tests/unit/test_rtg002_ws_api_task_lifecycle.py \
  tests/unit/test_tiny001d4_controlled_close.py \
  tests/unit/test_personal_campaign_promotion_gate.py \
  tests/unit/test_phase5b_symbol_isolation.py \
  tests/unit/test_ls001_order_watch_runtime.py \
  tests/unit/test_tm003_order_update_parse_observability.py
```

Authorized repeated Binance testnet rehearsal:

- run two cycles;
- each cycle starts a fresh `python3 -m src.main` process;
- environment must include `BACKEND_PORT=8001`,
  `RUNTIME_PROFILE=sim1_eth_runtime`, `EXCHANGE_TESTNET=true`,
  `RUNTIME_CONTROL_API_ENABLED=true`, and
  `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`;
- each cycle must do one controlled entry and one runtime controlled close;
- each cycle must restore GKS active, campaign `observe`, startup guard blocked,
  flat runtime positions, local active orders `0`, clean shutdown, and port
  release.

## Caps

- Environment: Binance testnet only.
- Profile: `sim1_eth_runtime` only.
- Symbol: `ETH/USDT:USDT` only.
- Cycles: `2`.
- Per cycle: one controlled entry and one runtime controlled close.
- Max entry: existing controlled endpoint cap, currently `0.01 ETH`.
- No user-supplied symbol, side, amount, price, stop loss, or take-profit body.

## Stop Conditions

Stop the rehearsal immediately if any cycle has:

- preflight runtime positions not equal to `0`;
- failed GKS/campaign/startup-guard read or restore;
- controlled entry blocked;
- controlled close not `FILLED`;
- final runtime positions not equal to `0`;
- final local active orders not equal to `0`;
- missing-stop or orphan protection-health block in the log;
- runtime shutdown requiring force kill;
- port `8001` not released.

## Symbol-Isolation Verdict

Current status:

- single-symbol repeated testnet rehearsal is eligible for review;
- multi-symbol runtime remains blocked;
- reconciliation and read-model symbol isolation require a two-symbol synthetic
  fixture suite before any multi-symbol profile or exchange-connected expansion.

## Completion Evidence

Local verification:

- symbol-isolation/order-watch/STOP_MARKET-adjacent tests passed with
  18 tests;
- integration regression passed with 107 tests;
- compileall and `git diff --check` passed.

Repeated Binance testnet rehearsal:

- Cycle 1:
  - controlled ENTRY `intent_3c08be13f081` /
    `sig_0a7446591611`, amount `0.01`, notional `21.1515`;
  - controlled close `FILLED`, `exit_controlled_67c1002181d4`,
    exchange order `8728615333`, terminalized protection orders `3`;
  - pre positions `0`, mid positions `1`, final positions `0`, final active
    local orders `0`;
  - GKS restored active, campaign `observe`, startup guard reset, natural
    runtime exit, port `8001` released;
  - no non-daemon thread warning, missing-stop block, or orphan protection
    block.
- Cycle 2:
  - controlled ENTRY `intent_a931c7dbf03b` /
    `sig_226d23b1c6d1`, amount `0.01`, notional `21.1607`;
  - controlled close `FILLED`, `exit_controlled_7e1641a544ef`,
    exchange order `8728616546`, terminalized protection orders `3`;
  - pre positions `0`, mid positions `1`, final positions `0`, final active
    local orders `0`;
  - GKS restored active, campaign `observe`, startup guard reset, natural
    runtime exit, port `8001` released;
  - no non-daemon thread warning, missing-stop block, or orphan protection
    block.

## Verdict

`phase5b_repeated_testnet_passed / multi_symbol_runtime_blocked / real_live_not_authorized`
