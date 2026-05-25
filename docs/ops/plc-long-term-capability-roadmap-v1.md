# PLC Long-Term Capability Roadmap v1

Date: 2026-05-25
Status: REVIEW / PLANNING_AUTHORITY_ONLY

## Document Role

This document translates the Owner's long-term goal into a staged capability
roadmap:

`controlled testnet tool -> reliable personal strategy execution platform`

It is a planning authority for sequencing and boundaries. It is not a runtime
profile, strategy contract, trading permission, order-sizing rule, leverage
rule, deployment plan, or real-live authorization.

## Boundary

Real live trading remains unauthorized.

This roadmap does not authorize:

- real live order placement;
- mainnet runtime activation;
- real-funds operation;
- transfer or withdrawal automation;
- automatic research-to-trade promotion;
- LLM or agent autonomous buy/sell/short/size/leverage decisions;
- simultaneous BTC/ETH exposure;
- new runtime profile defaults.

Every move from local/design to paper, testnet, small-scale rehearsal, or real
live requires scoped verification plus explicit Owner authorization for that
specific action.

## Current Baseline

As of Phase 5E:

- Phase 0 local PLC sandbox is implemented for review.
- Phase 1 read-only runtime adapter is implemented for review.
- Phase 2 paper observation packet is implemented for review.
- Phase 3 controlled Binance testnet rehearsal passed.
- Phase 4 non-real-live runtime hardening smoke passed.
- Phase 5A first account/campaign/contract gates passed bounded testnet smoke.
- Phase 5B repeated ETH-only testnet rehearsal passed.
- Phase 5C BTC/ETH local symbol-filtering fixture passed.
- Phase 5D BTC/ETH exchange read-only rehearsal passed after BTC orphan
  conditional cleanup.
- Phase 5E one-process BTC/ETH testnet runtime rehearsal passed sequential ETH
  and BTC controlled legs, ended exchange-flat and PG-flat, and added a
  read-only inventory endpoint.

This proves the system can run controlled non-real-live rehearsals under narrow
caps. It does not prove that the system is a reliable personal strategy
execution platform yet.

## Capability Principles

1. State before action.
   Runtime should know campaign, account, symbol, order, and promotion state
   before it can safely decide whether an action is allowed.
2. Account before symbol.
   Single-symbol correctness is insufficient if account-level daily loss,
   margin, liquidation distance, total exposure, or stale orders should block
   new entries.
3. Research freezes before runtime.
   A research opportunity must become an immutable Strategy Contract with
   provenance, validation status, and Owner authorization before any runtime
   stage can consume it.
4. Sequential before simultaneous.
   BTC/ETH sequential single-process rehearsal must remain the ceiling until
   symbol-isolated order-watch, reconciliation, inventory, and account-risk
   evidence are accepted.
5. Evidence before promotion.
   Each stage must produce preflight evidence, runtime evidence, final
   inventory evidence, rollback evidence, and a clear stop/continue verdict.
6. Human arm gate before trade intent.
   Strategy Contract eligibility cannot by itself create order authority.

## Capability Tracks

### Track A - Campaign Risk State Machine

Goal:

- Make a personal leveraged campaign explicit, durable, and auditable.

Target states:

- `observe`;
- `ready_to_arm`;
- `armed`;
- `exposure_open`;
- `profit_protecting`;
- `paused`;
- `hard_locked`;
- `loss_locked`;
- `ended`.

Required capabilities:

- deterministic transition table;
- runtime event ingestion from entry filled, protection mounted, profit
  threshold reached, reduce-only close, stop-loss event, risk-critical event,
  Owner pause/resume, and campaign end;
- entry gate that denies new exposure from paused, locked, ended, or
  inconsistent states;
- reduce-only close remains allowed when it reduces risk;
- state transition audit that includes symbol, profile, position id, signal id,
  and Owner/control provenance where applicable.

Acceptance direction:

- local transition-table tests first;
- PG-backed state replay tests next;
- runtime event wiring only after the transition table is accepted;
- testnet rehearsal only after event coverage and rollback are verified.

### Track B - Account-Level Risk State Machine

Goal:

- Treat the whole account as the risk object, not a single trade.

Target account states:

- `normal`;
- `caution`;
- `degraded`;
- `critical`;
- `reduce_only`;
- `blocked`;
- `unknown_fail_closed`.

Required capabilities:

- account equity and available balance snapshot;
- total account exposure by symbol and aggregate notional;
- liquidation-distance assessment per active position;
- daily loss and daily trade count using account-level `runtime:default`;
- stale/open order pressure;
- margin or exchange-health unknown state that fails closed for new entries;
- clear action policy: allow new entry, require Owner review, reduce-only only,
  or block.

Acceptance direction:

- pure policy model and table-driven tests first;
- runtime read-only snapshot integration second;
- entry-gate enforcement third;
- testnet rehearsal after evidence shows unknown/degraded/critical states block
  new entries without blocking risk-reducing closes.

### Track C - Multi-Symbol Runtime Foundation

Goal:

- Make symbol isolation reliable before any broader multi-symbol or
  simultaneous exposure plan.

Required capabilities:

- symbol-keyed order-watch running state;
- symbol-keyed recent order-update evidence;
- symbol-filtered reconciliation reports;
- symbol-filtered positions, orders, and execution-intent read models;
- symbol-keyed runtime inventory endpoint;
- account-level aggregation that does not pollute per-symbol state;
- startup/shutdown cleanup that restores all symbols to known safe state;
- no hidden cross-symbol cache reuse in order lifecycle, projection, or
  protection-health.

Acceptance direction:

- local two-symbol fixture tests;
- exchange read-only inventory tests;
- sequential one-process testnet rehearsal;
- only then consider a design for simultaneous exposure, still under separate
  Owner authorization.

### Track D - Strategy Contract Promotion Pipeline

Goal:

- Convert research output into governed contracts without allowing direct
  research-to-order execution.

Required stages:

1. `research_observation`
2. `frozen_strategy_contract`
3. `schema_validated`
4. `evidence_reviewed`
5. `owner_approved_for_read_only`
6. `owner_approved_for_paper`
7. `owner_approved_for_testnet`
8. `owner_approved_for_small_scale_rehearsal`
9. `real_live_design_review_only`

Required capabilities:

- immutable contract id and content hash;
- provenance linking research brief, feature snapshot boundary, validation
  result, review decision, and Owner approval;
- explicit no-order authority until a later action gate grants a specific
  non-real-live stage;
- revocation and pause path;
- rejected/parked family cannot be resurrected by relabeling.

Acceptance direction:

- docs/schema freeze first;
- local contract registry or validation report second;
- read-only preview integration third;
- paper/testnet stages only after Owner authorization.

### Track E - Runtime Evidence, Stop, And Rollback

Goal:

- Make rehearsals repeatable and reviewable without relying on ad hoc terminal
  notes.

Required evidence packet:

- requested scope and authorization;
- effective runtime profile and safe summary;
- preflight inventory;
- feasibility and cap evidence;
- control-state evidence before entry window;
- order lifecycle evidence;
- protection visibility evidence;
- daily/account risk evidence;
- final exchange and PG inventory;
- rollback actions and final controls;
- final verdict and blockers.

Acceptance direction:

- standardize the evidence shape for future Phase 5+ rehearsals;
- keep cleanup/mutation out of read-only evidence endpoints;
- require final flatness evidence before another runtime action.

## Staged Roadmap

### Phase 5F - Long-Term Capability Planning

Status: REVIEW

Scope:

- maintain this roadmap as the long-term planning authority;
- choose the next capability by risk reduction, not by market excitement;
- do not run new runtime/testnet actions by default.

Recommended next output:

- task card or Codex implementation plan for Track A transition-table coverage.

### Phase 5G - Campaign State Machine Completion

Status: PROPOSED

Scope:

- complete campaign transition table;
- add replay/invariant tests;
- wire missing runtime lifecycle events after the table is accepted.

Owner gate:

- required before any new exchange-connected rehearsal using expanded campaign
  event wiring.

### Phase 5H - Account Risk State Machine Completion

Status: PROPOSED

Scope:

- define account risk states and action policy;
- use account-level daily stats scope;
- integrate margin/liquidation/exposure freshness;
- fail closed for new entries on unknown/degraded/critical account state.

Owner gate:

- required before larger notional, simultaneous exposure, or longer testnet
  rehearsal.

### Phase 5I - Multi-Symbol Runtime Foundation

Status: PROPOSED

Scope:

- audit and harden symbol isolation across order-watch, reconciliation,
  read-models, protection-health, runtime caches, and startup/shutdown state;
- keep exposure sequential.

Owner gate:

- required before any simultaneous BTC/ETH testnet design.

### Phase 5J - Strategy Contract Promotion Governance

Status: PROPOSED

Scope:

- freeze Strategy Contract lifecycle and provenance;
- ensure research findings cannot directly create TradeIntent or runtime
  authority;
- add revocation/parking rules.

Owner gate:

- required before any research candidate can enter paper or testnet runtime
  stages.

### Phase 6 - Personal Strategy Paper/Testnet Runtime

Status: RESERVED

Scope:

- only after Tracks A-D have accepted evidence;
- paper first, then testnet by explicit Owner action;
- no real live.

### Phase 7 - Small-Scale Non-Real-Live Campaign Rehearsal

Status: RESERVED

Scope:

- longer but still non-real-live campaign rehearsal;
- bounded by account state, campaign state, inventory, and rollback evidence;
- separate authorization required.

### Phase 8 - Real-Live Design Review

Status: BLOCKED / NOT_AUTHORIZED

Scope:

- design review only unless Owner separately authorizes real live.

Minimum blockers before discussion:

- accepted campaign risk state machine;
- accepted account risk state machine;
- accepted Strategy Contract promotion pipeline;
- accepted runtime evidence packet;
- accepted rollback drill;
- no unresolved stale order, stale position, protection-health, or daily-risk
  accounting blocker;
- explicit Owner decision for real live.

## Recommended Immediate Next Task

Next task should stay with Codex:

`PLC-STATE-001 - Campaign Risk State Machine transition table and replay proof`

Why:

- it is the central long-term capability for personal leveraged campaigns;
- it reduces risk before more testnet exposure;
- it can be implemented and tested locally without exchange calls;
- it gives later account-risk, strategy-promotion, and multi-symbol work a
  stable state model to integrate with.

Claude can later receive bounded tests or docs cleanup after Codex freezes the
state model and allowed files.
