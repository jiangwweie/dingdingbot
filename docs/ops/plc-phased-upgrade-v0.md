# PLC Phased Upgrade v0

Date: 2026-05-25
Status: Phase 5E bounded testnet partial pass; real live not authorized

## Boundary

PLC promotion remains staged. This document does not authorize real live
trading, mainnet order placement, runtime profile changes, or credential
changes.

## Phase 0 - Local Sandbox

Status: REVIEW

Scope:

- Local deterministic objects and sandbox trace only.
- `ModeAdvice -> HumanArmDecision -> StrategyContract -> FeatureSnapshot ->
  TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState ->
  CampaignState`.
- Disabled by default.

Evidence:

- `src/domain/personal_campaign.py`
- `src/application/personal_campaign_sandbox.py`
- `tests/unit/test_personal_campaign_sandbox.py`

## Phase 1 - Read-Only Runtime Adapter

Status: REVIEW

Scope:

- Add a pure adapter from `FeatureSnapshot + StrategyContract` to a read-only
  `TradeIntent` preview.
- Require frozen contract semantics and closed/prior feature timestamps.
- Return explicit `read_only_no_order_authority`.
- No execution, exchange, order, account, repository, config, or profile
  authority.

Implemented artifacts:

- `src/application/personal_campaign_runtime_adapter.py`
- `ReadOnlyRuntimeAdapterPreview`
- `docs/schemas/personal_campaign/read_only_runtime_adapter_preview.schema.json`
- `docs/schemas/personal_campaign/examples/read_only_runtime_adapter_preview_sq02.example.json`
- `tests/unit/test_personal_campaign_runtime_adapter.py`

Acceptance:

- Closed/prior snapshot plus frozen contract returns one read-only preview.
- Future/current snapshot is rejected.
- Non-frozen contract is rejected.
- Adapter output contains no order id or exchange order id.
- Domain and adapter code do not import I/O frameworks.

## Phase 2 - Paper Observation Packet

Status: REVIEW

Scope:

- Persist or export read-only previews as observation packets.
- Add review status and operator notes.
- No paper orders, no exchange mutations, and no account authority.

Entry requirements:

- Phase 1 review accepted.
- Observation packet schema defined.
- Redaction/secret-free structured logs ready.

Implemented artifacts:

- `src/application/personal_campaign_paper_observation.py`
- `PaperObservationPacket`
- `docs/schemas/personal_campaign/paper_observation_packet.schema.json`
- `docs/schemas/personal_campaign/examples/paper_observation_packet_sq02.example.json`
- `tests/unit/test_personal_campaign_paper_observation.py`

Acceptance:

- Packets wrap only read-only previews.
- Packets carry `paper_observation_no_order_authority`.
- Packets include review status, operator notes, and optional review
  provenance.
- Reviewed packets require `reviewed_by` and `reviewed_at_ms`.
- Packet export is JSON-ready and does not write files or call services.

## Phase 3 - Testnet Rehearsal Package

Status: REVIEW / COMPLETED_TESTNET_REHEARSAL

Scope:

- Define a bounded testnet rehearsal for PLC intent-to-plan validation.
- Must pass through ADR-0009 scoped action review.
- Must remain separate from real live/mainnet.

Design artifacts:

- `docs/ops/plc-phase3-testnet-rehearsal-design.md`
- `docs/ops/plc-phase3-adr0009-authorization-request.md`
- `docs/ops/plc-campaign-risk-state-machine-spec.md`
- `docs/ops/plc-account-risk-liquidation-safety-spec.md`
- `docs/ops/tc-tiny-001d-4-runtime-managed-close-smoke-design.md`

Entry requirements:

- Phase 2 review accepted.
- Runtime-managed close smoke implemented and locally verified.
- Campaign risk state machine specified to design-review quality.
- Account risk/liquidation safety checks specified to design-review quality.

Pre-authorization evidence:

- Scoped local verification passed: 126 targeted tests.
- `compileall` passed for touched modules.
- `git diff --check` passed.
- Local PG active orders were backed up and terminalized without exchange
  mutation; active local orders are now `0`.
- Local PG `orders.ck_orders_order_role` now allows `EXIT`.
- Binance official plugin returned public `ETHUSDT` futures book ticker data.
- Project read-only Binance testnet preflight returned no nonzero
  `ETH/USDT:USDT` position and open orders `0`.

Completion evidence:

- Owner authorized an initial attempt and one retry under ADR-0009.
- Initial attempt reached exchange-flat/local-flat state but exposed a
  post-close protection cleanup idempotency gap.
- Retry after the cleanup patch passed:
  - one controlled ENTRY;
  - one reduce-only controlled EXIT;
  - 3 protection orders terminalized by runtime cleanup;
  - daily stats updated;
  - local active orders `0`;
  - local active positions `0`;
  - Binance testnet final nonzero position `0` and open orders `0`;
  - reconciliation read model severe `0`, warning `0`;
  - GKS restored active and runtime stopped.

## Phase 4 - Tiny-Live-Style Review

Status: REVIEW / NON_REAL_LIVE_HARDENING_SMOKED / NOT_READY_FOR_REAL_LIVE

Scope:

- Review only. No real funds activation from this document.

Entry requirements:

- Phase 3 evidence accepted.
- Owner explicitly requests a separate real-live readiness review.
- Real live authorization remains separate and explicit.

Review artifact:

- `docs/ops/plc-phase4-tiny-live-style-readiness-review.md`

Completion evidence:

- account/liquidation gate active before CapitalProtection;
- PG-backed campaign state machine gates new entries;
- reconciliation reads normal plus conditional STOP_MARKET open-order views;
- startup guard resets to `RUNTIME_SHUTDOWN_RESET` during runtime shutdown;
- no-order lifecycle smoke exited naturally and released port `8001`;
- active Binance testnet smoke opened and closed one controlled `0.01 ETH`
  exposure through runtime, then ended flat with local active orders `0`.

Phase 4 verdict:

- `phase4_p4_001_to_p4_004_non_real_live_smoke_complete / real_live_not_authorized / strategy_promotion_still_blocked`

Main blockers:

- no strategy contract is promoted to real-live use.

## Phase 5 - Small-Scale Rehearsal Readiness

Status: DESIGN_AND_FIRST_GATES_IN_REVIEW / BOUNDED_TESTNET_SMOKED

Scope:

- Prepare the system for longer non-real-live rehearsal without increasing
  real-live authority.
- Keep ETH single-symbol runtime as the current execution scope.
- Strengthen account-level risk, campaign-state runtime transitions,
  symbol-isolation proof, and Strategy Contract promotion governance before
  repeated or longer testnet rehearsal.

Design artifact:

- `docs/ops/plc-phase5-small-scale-rehearsal-design.md`

Current Phase 5A evidence:

- `dev` is the current integration candidate and remains unpushed until Owner
  requests remote publication;
- account-risk now prefers account-scope positions and can block a new ETH
  entry because of critical risk on another symbol;
- account-risk computes total account exposure and blocks when the exposure
  multiple cap is exceeded;
- campaign state service accepts runtime events for profit-protect, stop-loss
  lock, position close, entry-filled, and risk-critical transitions;
- Strategy Contract promotion gate preserves
  `promotion_review_no_order_authority` and cannot grant order or exchange
  authority.
- bounded Binance testnet smoke passed after the Phase 5A changes with one
  controlled entry, one runtime controlled close, final positions `0`, local
  active orders `0`, restored GKS/campaign/startup-guard state, clean shutdown,
  and port `8001` release.

Phase 5 verdict:

- `phase5a_first_gates_smoked_on_testnet / real_live_not_authorized / repeated_rehearsal_still_separate_gate`

### Phase 5B - Repeated Testnet Rehearsal

Status: REVIEW / REPEATED_TESTNET_PASSED

Design artifact:

- `docs/ops/plc-phase5b-repeated-testnet-rehearsal.md`

Scope:

- run two controlled Binance testnet cycles in separate runtime processes;
- preserve one controlled entry and one runtime controlled close per process;
- harden order-watch and order-confirmation evidence against basic
  cross-symbol state bleed;
- keep multi-symbol runtime blocked until reconciliation/read-model
  two-symbol fixture proof exists.

Current Phase 5B evidence:

- order-watch now tracks symbol-specific running flags while retaining the
  legacy global shutdown flag;
- recent order-update evidence is indexed by symbol before order confirmation;
- symbol-isolation audit marks order-watch/cache checks as passed,
  reconciliation/read-model checks as review, and multi-symbol runtime as
  blocked.
- two repeated Binance testnet cycles passed with controlled entry, runtime
  controlled close, final flat state, active local orders `0`, restored
  controls, and clean shutdown in each cycle.

Phase 5B verdict:

- `phase5b_repeated_testnet_passed / multi_symbol_runtime_blocked / real_live_not_authorized`

### Phase 5C - Two-Symbol Synthetic Fixture Proof

Status: REVIEW / SYNTHETIC_FIXTURE_PASSED

Design artifact:

- `docs/ops/plc-phase5c-two-symbol-synthetic-fixture-proof.md`

Scope:

- prove BTC/ETH local symbol isolation for reconciliation and runtime read
  models without starting multi-symbol runtime;
- add optional symbol filters to positions and execution-intents read models;
- preserve portfolio as account-level aggregation;
- keep multi-symbol runtime blocked.

Current Phase 5C evidence:

- reconciliation `build_read_model(ETH)` excludes BTC mismatches in a local
  two-symbol fixture;
- runtime orders, execution intents, and positions filter by symbol in the
  fixture;
- portfolio aggregates BTC and ETH as account-level state;
- local Phase 5B/5C symbol-isolation tests passed with 8 tests.

Phase 5C verdict:

- `phase5c_two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`

### Phase 5D - Two-Symbol Exchange Read-Only Rehearsal

Status: REVIEW / EXCHANGE_READONLY_PASSED_AFTER_TESTNET_CLEANUP

Design artifact:

- `docs/ops/plc-phase5d-two-symbol-exchange-readonly-rehearsal.md`

Scope:

- exchange-connected read-only BTC/ETH visibility check;
- no runtime profile/config change;
- no multi-symbol execution runtime;
- no order placement;
- no real live.

Current Phase 5D evidence:

- official Binance plugin returned public USDS futures book ticker for
  `ETHUSDT` and `BTCUSDT`;
- initial project Binance testnet read-only check found BTC was flat but had
  6 reduce-only orphan conditional orders;
- bounded testnet cleanup canceled those 6 BTC reduce-only orphan conditional
  orders after verifying BTC position `0` and normal open orders `0`;
- final project Binance testnet read-only check passed for ETH and BTC:
  position `0`, normal open orders `0`, conditional open orders `0`.

Phase 5D verdict:

- `phase5d_two_symbol_exchange_readonly_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`

### Phase 5E - Controlled Multi-Symbol Testnet Runtime Rehearsal

Status: REVIEW / ETH_AND_BTC_TESTNET_LEGS_PASSED

Design artifact:

- `docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md`

Scope:

- design a controlled BTC/ETH Binance testnet runtime rehearsal;
- use one new readonly testnet profile,
  `phase5e_btc_eth_testnet_runtime`;
- preserve `sim1_eth_runtime` unchanged;
- add only minimal multi-symbol market-scope config support;
- run one runtime process with sequential ETH then BTC controlled exposure;
- forbid simultaneous BTC+ETH exposure in the first 5E rehearsal;
- keep real live, portfolio routing, strategy optimization, and autonomous
  trade decisions blocked.

Proposed caps:

- ETH max amount `0.01 ETH` and max notional `25 USDT`;
- BTC exchange-minimum viable quantity only, with max notional `250 USDT`;
- combined open exposure cap `250 USDT` because at most one symbol may be open
  at a time;
- max `5` order submissions per symbol:
  one ENTRY, two TP, one SL, one reduce-only CLOSE;
- final BTC/ETH positions `0`, normal open orders `0`, conditional open orders
  `0`, and local active orders `0`.

Current Phase 5E evidence:

- optional multi-symbol market scope added without breaking legacy
  single-symbol profiles;
- readonly inactive `phase5e_btc_eth_testnet_runtime` profile seeded;
- one 5E runtime process started with BTC/ETH warmup `4/4`, BTC/ETH
  reconciliation, and BTC/ETH order-watch;
- ETH leg passed with controlled entry `intent_fca06be68891` /
  `sig_39cb35ab8b3e` and runtime close
  `exit_controlled_18ff201e1ec3` / exchange order `8728698638`;
- BTC leg was blocked before order placement because `0.001 BTC` notional
  `77.5506` was below min_notional default `100`; cap was not raised;
- BTC blocker handling now reports next viable exchange-step evidence:
  `0.002 BTC` at the observed price would be `155.1012 USDT`, exceeding the
  previous `130 USDT` cap by `25.1012 USDT`;
- Owner later approved testnet operations without the prior minimum-capital
  limitation; the Phase 5E BTC retry spec is now `0.002 BTC` with max notional
  `250 USDT`, testnet-only;
- BTC retry passed with controlled entry `intent_ed2c999769bd` /
  `sig_929aabc7d2ce`, amount `0.002`, notional `154.7836`, and runtime close
  `exit_controlled_657fa92707ee` / exchange order `13192655923`;
- BTC retry final direct Binance testnet and PG state were flat/no-open-orders,
  controls restored, runtime stopped;
- read-only Phase 5E inventory endpoint added for future BTC/ETH preflight and
  final flatness evidence across exchange and PG state;
- final direct Binance testnet state was ETH/BTC position `0`, normal open
  orders `0`, conditional open orders `0`;
- PG active positions and ETH/BTC open orders were empty;
- runtime stopped and port `8001` released.

Phase 5E verdict:

- `phase5e_eth_leg_passed / phase5e_btc_leg_blocked_by_min_notional_without_order / final_exchange_flat / real_live_not_authorized`
- `phase5e_btc_next_viable_decision_evidence_available`
- `phase5e_btc_retry_authorized_for_testnet_only / btc_cap_250_usdt`
- `phase5e_btc_leg_passed / final_exchange_flat / final_pg_flat / controls_restored / real_live_not_authorized`

### Phase 5F - Long-Term Capability Planning

Status: REVIEW / PLANNING_AUTHORITY_ONLY

Planning artifact:

- `docs/ops/plc-long-term-capability-roadmap-v1.md`

Scope:

- translate the Owner's long-term target into staged capabilities:
  `controlled testnet tool -> reliable personal strategy execution platform`;
- keep the next work focused on capability closure, not bigger testnet size;
- separate campaign state, account state, multi-symbol foundation, Strategy
  Contract promotion, and evidence/rollback into independent gates;
- keep all runtime, paper, testnet, small-scale, and real-live moves behind
  scoped verification plus explicit Owner authorization.

Phase 5F verdict:

- `long_term_capability_roadmap_added / next_recommended_task_campaign_state_transition_table / no_runtime_action / real_live_not_authorized`
