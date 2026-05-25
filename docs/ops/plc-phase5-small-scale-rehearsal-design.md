# PLC Phase 5 Small-Scale Rehearsal Design

Date: 2026-05-25
Status: DESIGN_AND_FIRST_GATES_IN_REVIEW / BOUNDED_TESTNET_SMOKED

## Boundary

Phase 5 is a non-real-live rehearsal readiness phase. It does not authorize
real live trading, mainnet order placement, real-funds operation, runtime
profile changes, credential changes, transfer, withdrawal, or strategy-return
optimization.

The Owner authorized testnet execution for this Phase 5 preparation turn. The
authorization applies only to bounded Binance testnet smoke/rehearsal actions
under the existing `sim1_eth_runtime` profile and existing controlled runtime
test endpoints.

## Goal

Move the system from a controllable testnet tool toward a reliable personal
strategy execution platform without skipping gates.

The next platform capability is not "trade live". It is:

- account-level risk decisions that look across the account, not only the next
  order;
- durable campaign state transitions that can be advanced by runtime events;
- symbol-isolation proof before any multi-symbol runtime expansion;
- Strategy Contract promotion review that cannot directly grant trading
  authority;
- longer testnet rehearsal only after the safety gates above stay clean.

## Phase 5A - Current Scope

Phase 5A is the first small-scope preparation slice.

Implemented or accepted in this slice:

- `dev` is treated as the current integration candidate and remains unpushed
  until Owner requests remote publication.
- Account-risk reads account-scope positions where the gateway supports it,
  so critical risk on another symbol can block new ETH entries.
- Account-risk computes total account exposure from active positions and can
  block new entries when exposure exceeds the configured balance multiple.
- Campaign state service exposes runtime-event transitions for
  `entry_filled`, `profit_protect_triggered`, `stop_loss_filled`,
  `position_closed`, and `risk_critical`.
- Strategy Contract promotion gate accepts only reviewed paper-observation
  packets into the next non-order gate and preserves explicit
  `promotion_review_no_order_authority`.
- Bounded Binance testnet smoke passed after the Phase 5A gate changes:
  controlled entry `intent_99fdcaa96287` / `sig_3d42cc1b8bf0`, amount
  `0.01`, notional `21.1324`; controlled close `FILLED` with
  `exit_controlled_48409f3fc46a` / exchange order `8728597319`; final runtime
  positions `0`, local active orders `0`, GKS active, campaign `observe`,
  startup guard blocked/reset, port `8001` released, and no missing-stop or
  orphan protection-health block logged.

## Commands

Local verification:

```bash
python3 -m compileall -q \
  src/application/account_risk_service.py \
  src/application/campaign_state_service.py \
  src/application/personal_campaign_promotion_gate.py

pytest -q \
  tests/unit/test_p4_account_risk_service.py \
  tests/unit/test_p4_campaign_state_service.py \
  tests/unit/test_personal_campaign_promotion_gate.py
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
  tests/unit/test_personal_campaign_promotion_gate.py
```

Authorized Binance testnet smoke:

- start `python3 -m src.main` with `BACKEND_PORT=8001`,
  `RUNTIME_PROFILE=sim1_eth_runtime`, `EXCHANGE_TESTNET=true`,
  `RUNTIME_CONTROL_API_ENABLED=true`, and
  `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`;
- confirm `/api/health` is `ok`;
- verify preflight local runtime positions are `0`;
- temporarily set GKS inactive, campaign state `armed`, and startup guard
  armed;
- execute one controlled entry via
  `POST /api/runtime/test/smoke/execute-controlled-entry`;
- execute one runtime controlled close via
  `POST /api/runtime/test/smoke/execute-controlled-close`;
- restore GKS active, campaign state `observe`, and startup guard blocked;
- terminate runtime and verify port `8001` is released.

## Caps

- Environment: Binance testnet only.
- Profile: `sim1_eth_runtime` only.
- Symbol: current controlled endpoint symbol only, `ETH/USDT:USDT`.
- Max entry: existing controlled endpoint cap, currently `0.01 ETH`.
- Session: one controlled entry and one controlled close per runtime process.
- No user-supplied symbol, side, amount, price, stop loss, or take-profit body
  is accepted by the controlled endpoint.

## Stop Conditions

Stop immediately and restore safe controls if any condition appears:

- preflight local runtime positions are nonzero;
- GKS/campaign/startup-guard controls cannot be read or restored;
- controlled entry is blocked by account risk, campaign state, startup guard,
  GKS, protection health, or circuit breaker;
- controlled close is not `FILLED`;
- final local runtime positions are nonzero;
- final local active orders are nonzero;
- runtime shutdown does not release port `8001`;
- runtime logs include non-daemon thread warnings;
- protection-health emits missing-stop or orphan reduce-only blocks during the
  bounded exposure window.

## Rollback

Rollback is operational, not trading-promotional:

- restore GKS active;
- move campaign state through a legal close path back to `observe`;
- block startup guard;
- run runtime-managed controlled close if a local active position exists;
- stop runtime and verify no `src.main` process and no port `8001` listener;
- do not use direct exchange cleanup unless runtime close cannot run and Owner
  explicitly authorizes a cleanup exception.

## Phase 5B - Repeated Testnet Rehearsal

Status: REVIEW / REPEATED_TESTNET_PASSED.

Design artifact:

- `docs/ops/plc-phase5b-repeated-testnet-rehearsal.md`

Scope:

- run repeated controlled Binance testnet cycles as separate runtime processes;
- harden order-watch and order-confirmation evidence against obvious
  cross-symbol state bleed;
- record a symbol-isolation audit that keeps multi-symbol runtime blocked until
  reconciliation/read-model two-symbol fixture proof exists.

Current status:

- order-watch running state is now symbol-scoped while preserving the legacy
  global shutdown flag;
- recent order-update evidence is now indexed by symbol before confirmation;
- two repeated Binance testnet cycles passed with controlled entry, runtime
  controlled close, final flat state, active local orders `0`, restored
  controls, and clean shutdown in each cycle;
- multi-symbol runtime remains blocked.

## Verdict

`phase5b_repeated_testnet_passed / multi_symbol_runtime_blocked / real_live_not_authorized`
