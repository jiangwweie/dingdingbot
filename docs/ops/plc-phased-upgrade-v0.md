# PLC Phased Upgrade v0

Date: 2026-05-25
Status: Phase 5B repeated testnet passed; real live not authorized

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
