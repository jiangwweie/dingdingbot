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

## Phase 5C - Two-Symbol Synthetic Fixture Proof

Status: REVIEW / SYNTHETIC_FIXTURE_PASSED.

Design artifact:

- `docs/ops/plc-phase5c-two-symbol-synthetic-fixture-proof.md`

Scope:

- prove BTC/ETH local symbol isolation without starting multi-symbol runtime;
- add optional symbol filters to runtime positions and execution-intents read
  models;
- verify reconciliation `build_read_model(symbol)` does not include mismatches
  from the other symbol;
- verify portfolio remains account-level aggregation.

Current status:

- local BTC/ETH synthetic fixture passed;
- runtime positions, orders, and execution intents respect symbol filters in
  the fixture;
- portfolio aggregates both symbols as account-level view;
- multi-symbol runtime remains blocked.

Phase 5C verdict:

`phase5c_two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`

## Phase 5D - Two-Symbol Exchange Read-Only Rehearsal

Status: REVIEW / EXCHANGE_READONLY_PASSED_AFTER_TESTNET_CLEANUP.

Design artifact:

- `docs/ops/plc-phase5d-two-symbol-exchange-readonly-rehearsal.md`

Scope:

- run BTC/ETH exchange-connected read-only visibility checks against Binance
  testnet;
- verify ticker, position, normal open-order, and conditional STOP-order
  visibility for both symbols;
- require final BTC/ETH flat/no-open-order state before any future
  multi-symbol runtime discussion;
- do not start runtime or change runtime profile/config.

Current status:

- official Binance plugin returned public USDS futures book ticker data for
  `ETHUSDT` and `BTCUSDT`;
- initial project Binance testnet read-only check found BTC flat with 6
  reduce-only orphan conditional orders;
- bounded testnet cleanup canceled the 6 BTC reduce-only orphan conditional
  orders after verifying BTC position `0` and normal open orders `0`;
- final project Binance testnet read-only rehearsal passed for ETH and BTC:
  positions `0`, normal open orders `0`, conditional open orders `0`;
- multi-symbol runtime remains blocked.

Phase 5D verdict:

`phase5d_two_symbol_exchange_readonly_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`

## Phase 5E - Controlled Multi-Symbol Testnet Runtime Rehearsal

Status: REVIEW / ETH_AND_BTC_TESTNET_LEGS_PASSED.

Design artifact:

- `docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md`

Scope:

- design one controlled BTC/ETH Binance testnet runtime rehearsal;
- use one new readonly testnet profile
  `phase5e_btc_eth_testnet_runtime`;
- preserve `sim1_eth_runtime` unchanged;
- add minimal multi-symbol market-scope config support;
- use one runtime process with sequential ETH then BTC controlled exposure;
- forbid simultaneous BTC+ETH exposure in the first 5E rehearsal.

Proposed caps:

- ETH max `0.01 ETH` / `25 USDT`;
- BTC exchange-minimum viable quantity with `250 USDT` ceiling;
- combined open exposure cap `250 USDT` because at most one symbol may be open
  at a time;
- max `5` order submissions per symbol;
- final BTC/ETH positions `0`, exchange open orders `0`, and local active
  orders `0`.

Phase 5E verdict:

`phase5e_eth_leg_passed / phase5e_btc_leg_blocked_by_min_notional_without_order / final_exchange_flat / real_live_not_authorized`

`phase5e_btc_leg_passed / final_exchange_flat / final_pg_flat / controls_restored / real_live_not_authorized`

Current status:

- Owner authorized bounded Phase 5E testnet after design review;
- minimal multi-symbol runtime scope and Phase 5E controlled endpoints were
  implemented;
- one runtime process started with BTC/ETH warmup and order-watch;
- ETH controlled entry and runtime close passed;
- BTC controlled entry was blocked before order placement because fixed
  `0.001 BTC` notional was below min_notional and cap was not raised;
- BTC blocker handling now reports next viable exchange-step evidence:
  `0.002 BTC`, estimated `155.1012 USDT` at the observed blocked price, and
  `25.1012 USDT` cap shortfall versus the previous `130 USDT` cap;
- Owner later approved testnet operations without the prior minimum-capital
  limitation, so the Phase 5E BTC retry spec is now `0.002 BTC` with max
  notional `250 USDT`, testnet-only;
- BTC retry passed with controlled entry `intent_ed2c999769bd` /
  `sig_929aabc7d2ce`, runtime close `exit_controlled_657fa92707ee` /
  exchange order `13192655923`, and terminalized protection orders `3`;
- read-only Phase 5E inventory endpoint now standardizes BTC/ETH preflight and
  final flatness evidence across exchange and PG state;
- final direct Binance testnet and PG state were flat/no-open-orders.

## Phase 5F - Long-Term Capability Planning

Status: REVIEW / AMENDED_BY_PLAYBOOK_GOVERNANCE_R0.

Planning artifact:

- `docs/ops/plc-long-term-capability-roadmap-v1.md`
- `docs/ops/playbook-governance-r0-plan.md`
- `docs/adr/0011-playbook-governance-before-strategy-contract.md`

Scope:

- convert the post-Phase-5E state into a long-term capability roadmap;
- prioritize Playbook Governance R0 before more Strategy Contract/runtime
  implementation;
- keep local campaign state-machine evidence as governance backbone, while
  deferring account runtime expansion, multi-symbol runtime foundation,
  Strategy Contract v2 implementation, and runtime evidence expansion;
- avoid treating testnet authorization as authorization for real live,
  simultaneous exposure, runtime default changes, or automatic
  research-to-trade wiring.

Phase 5F verdict:

`long_term_capability_roadmap_added / next_recommended_task_campaign_state_transition_table / no_runtime_action / real_live_not_authorized`

`playbook_governance_r0_accepted_with_amendments / strategy_contract_runtime_branch_deferred / no_runtime_action / real_live_not_authorized`

## Phase 5G - Playbook Governance R0

Status: ACCEPTED_WITH_AMENDMENTS / PAPER_ONLY.

Planning artifact:

- `docs/ops/playbook-governance-r0-plan.md`

Scope:

- define playbook registry, switch decision log, switching gate rules,
  cooldown/review governance, CPV0_2 continuity, and dry-run review;
- make `PB-000-OBSERVE-ONLY` the default safe state;
- treat `PB-003-MANUAL-DISCRETIONARY` as highest-risk governed manual posture;
- forbid runtime, exchange API, order path, strategy implementation,
  paper/testnet wrapping, and real live.

Phase 5G verdict:

`playbook_governance_r0_next / paper_only_docs_governance / no_runtime_action / real_live_not_authorized`
