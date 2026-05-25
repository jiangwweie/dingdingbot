# PLC Phase 4 Tiny-Live-Style Readiness Review

Date: 2026-05-25
Status: HARDENING_REVIEW / NOT_READY_FOR_REAL_LIVE

Runtime effect: local code and PG migration added; no real-live runtime executed

Trading permission effect: none

Default state: disabled

## Authorization Interpretation

Owner authorized Phase 4 on 2026-05-25. Under the current PLC phased ladder,
Phase 4 is a tiny-live-style readiness review only. This review does not
authorize real live trading, live exchange order placement, live order
cancellation, real-funds deployment, transfer, withdrawal, rebalancing, runtime
profile changes, credential changes, or enabling trading permissions on a real
account.

Any future real-live action still requires a separate explicit real-live
authorization decision.

## Reviewed Evidence

- Phase 0 local sandbox is implemented and disabled by default.
- Phase 1 read-only runtime adapter is implemented.
- Phase 2 paper observation packet is implemented.
- Phase 3 Binance testnet rehearsal completed after one retry:
  - one controlled ENTRY;
  - one reduce-only controlled EXIT;
  - runtime terminalized 3 protection orders;
  - daily stats updated;
  - final Binance testnet position was flat;
  - final Binance testnet open orders were `0`;
  - local active orders were `0`;
  - local active positions were `0`;
  - latest reconciliation read model was consistent with severe `0`,
    warning `0`, total `0`;
  - GKS was restored active and runtime stopped.
- Phase 3 root-cause learning was captured: post-close protection cleanup must
  be idempotent when Binance has already removed protection orders.

## Phase 4 Decision

`not_ready_for_real_live / continue_non_real_live_hardening`

Phase 4 review is accepted as started and completed for this evidence set, but
the system is not ready for real live or real-funds activation.

## Hardening Update - 2026-05-25

The first four Phase 4 blockers have been converted from design-only gaps into
runtime-enforced local code paths with targeted tests. This update did not run
real-live trading and did not authorize real-live activation.

- P4-001 account risk/liquidation: added `AccountRiskService`, exchange
  liquidation-price parsing, and a fail-closed `ExecutionOrchestrator` gate
  before `CapitalProtection`.
- P4-002 campaign state machine: added durable `runtime_campaign_state` PG
  table, repository, service, owner-control API, and new-entry enforcement. Only
  `armed` allows new entries; observe/paused/profit-protect/loss-locked/
  hard-locked/closed block new entries.
- P4-003 conditional SL visibility: reconciliation now reads normal open orders
  plus Binance conditional STOP_MARKET views and deduplicates raw exchange
  payloads before protection-health checks.
- P4-004 runtime lifecycle: startup guard now has explicit local
  `/api/runtime/control/startup-trading-guard/block` reset and shutdown paths
  reset the process-local guard to `RUNTIME_SHUTDOWN_RESET`.

Targeted verification:

- `pytest -q tests/unit/test_p4_account_risk_service.py tests/unit/test_p4_campaign_state_service.py tests/unit/test_gks_v0_global_kill_switch.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_rtg002_ws_api_task_lifecycle.py`
  - result: 75 passed.
- `python3 -m compileall -q ...`
  - result: passed for touched runtime, infrastructure, API, migration, and
    test files.
- `git diff --check`
  - result: passed.
- Local PG runtime schema:
  - direct Alembic clean upgrade is still blocked by older migration-chain
    ordering (`orders` migration references `signals` before the clean schema
    has `signals`);
  - after clearing the local PG `public` schema, `PGCoreBase.metadata.create_all()`
    completed and `CampaignStateService` restored/created
    `runtime:default` as `observe` from PG.

Remaining before any real-live readiness claim:

- repair or baseline the older Alembic chain so clean PG migration can reach
  head without relying on `create_all`;
- run an ADR-0009-scoped non-real-live runtime smoke proving startup guard
  reset and API port release without force kill;
- run an active-position testnet protection-health observation showing a
  confirmed exchange-native SL does not create false severe blocks.

## Blocking Gaps

### P4-BLOCK-001 Account Risk Is Design-Only

Status after hardening update: IMPLEMENTED_LOCAL / NEEDS_RUNTIME_SMOKE.

`docs/ops/plc-account-risk-liquidation-safety-spec.md` defines account states
and liquidation distance behavior, but runtime does not yet enforce account
`unknown`, `degraded`, or `critical` states as durable gates.

Required before any real-live readiness can be reconsidered:

- runtime account snapshot read model;
- fail-closed entry gate for unknown/degraded/critical account state;
- side-aware liquidation distance calculation;
- tests for missing, stale, zero, contradictory, and critical account fields.

### P4-BLOCK-002 Campaign Risk Is Design-Only

Status after hardening update: IMPLEMENTED_LOCAL / PG_CREATE_ALL_VERIFIED /
ALEMBIC_CHAIN_REPAIR_PENDING / NEEDS_RUNTIME_SMOKE.

`docs/ops/plc-campaign-risk-state-machine-spec.md` defines observe/armed/paused/
profit-protect/loss-locked/hard-locked/closed states, but runtime does not yet
persist and enforce the full state machine.

Required before any real-live readiness can be reconsidered:

- durable campaign state storage;
- Owner-gated arm/reset transitions;
- hard-lock semantics that block new entries;
- close/reduce allowance in risk-reducing states;
- audit trail tests for every transition.

### P4-BLOCK-003 Protection Health Still Has Conditional-Order Visibility Noise

Status after hardening update: IMPLEMENTED_LOCAL / NEEDS_ACTIVE_TESTNET_OBSERVATION.

During Phase 3, periodic reconciliation emitted temporary protection-health
critical warnings while the position was active because Binance conditional SL
visibility differs from normal open-order visibility. The final state healed
after close and manual reconciliation, but real-live readiness requires fewer
false criticals during active exposure.

Required before any real-live readiness can be reconsidered:

- reconcile conditional SL/STOP_MARKET visibility using the same evidence rules
  as order confirmation;
- distinguish active-exposure criticals from post-close cleanup observations;
- prove a bounded active-position window does not generate false
  protection-missing severe blocks when exchange-native SL exists.

### P4-BLOCK-004 Runtime Control Lifecycle Needs A Clean Close State

Status after hardening update: IMPLEMENTED_LOCAL / NEEDS_RUNTIME_PORT_RELEASE_SMOKE.

Phase 3 restored GKS and stopped runtime, but startup guard remains an arm-only
control surface and the runtime process required force stop after graceful
shutdown output in one run.

Required before any real-live readiness can be reconsidered:

- explicit startup-guard reset/disarm path;
- shutdown verification that releases the API port without force kill;
- tests or operational checks for safe control-state restoration after a smoke.

### P4-BLOCK-005 Strategy Promotion Is Not Approved

The current PLC chain validates plumbing and safety behavior. It does not
promote any strategy edge, sizing rule, leverage rule, or autonomous
research-to-order path.

Required before any real-live readiness can be reconsidered:

- separate promotion review for the specific strategy contract;
- evidence label before promotion;
- proof that LLM/agent output cannot decide buy/sell/short/size/leverage;
- no return/drawdown preference encoded as runtime constraint.

## Allowed Next Work

These are non-real-live hardening tasks. Each runtime/testnet execution still
requires ADR-0009 scoped authorization.

| ID | Task | Scope | Done When |
| --- | --- | --- | --- |
| P4-001 | Runtime account risk gate | IMPLEMENTED_LOCAL | Unit tests cover flat/unknown/degraded/critical/healthy account states and liquidation distance boundaries. Runtime smoke still pending. |
| P4-002 | Durable campaign state machine | IMPLEMENTED_LOCAL | PG table/repository/service/API/new-entry gate added. Local transition tests pass. PG runtime `create_all` verified; older Alembic clean-upgrade chain still needs repair. Runtime smoke pending. |
| P4-003 | Conditional protection visibility hardening | IMPLEMENTED_LOCAL | Reconciliation reads normal plus conditional STOP_MARKET open-order views. Active testnet observation still pending. |
| P4-004 | Runtime control lifecycle reset | IMPLEMENTED_LOCAL | Startup-guard block/reset API and shutdown reset tests pass. Port-release runtime smoke still pending. |
| P4-005 | Phase 4 non-real-live rehearsal design | Define a future tiny-live-style non-real-live rehearsal after P4-001 to P4-004. | ADR-0009 request names exact mode, commands, caps, stop conditions, and rollback path. |

## Explicit Non-Authorization

This review does not authorize:

- real live trading;
- real exchange order placement/cancellation/modification;
- live account read/write;
- real-funds deployment;
- transfer, withdrawal, or rebalancing;
- runtime profile change;
- credential change;
- strategy-return optimization;
- LLM/agent autonomous trading decisions.

## Current Verdict

`phase4_hardening_local_complete / real_live_not_authorized / runtime_smoke_pending`
