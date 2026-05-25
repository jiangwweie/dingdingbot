# PLC Phase 4 Tiny-Live-Style Readiness Review

Date: 2026-05-25
Status: REVIEW / NOT_READY_FOR_REAL_LIVE

Runtime effect: none

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

## Blocking Gaps

### P4-BLOCK-001 Account Risk Is Design-Only

`docs/ops/plc-account-risk-liquidation-safety-spec.md` defines account states
and liquidation distance behavior, but runtime does not yet enforce account
`unknown`, `degraded`, or `critical` states as durable gates.

Required before any real-live readiness can be reconsidered:

- runtime account snapshot read model;
- fail-closed entry gate for unknown/degraded/critical account state;
- side-aware liquidation distance calculation;
- tests for missing, stale, zero, contradictory, and critical account fields.

### P4-BLOCK-002 Campaign Risk Is Design-Only

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
| P4-001 | Runtime account risk gate | Implement account state read model and fail-closed entry gate. | Unit tests cover unknown/degraded/critical/healthy account states and liquidation distance boundaries. |
| P4-002 | Durable campaign state machine | Implement campaign state persistence and transition audit. | Tests cover observe/armed/paused/profit-protect/loss-locked/hard-locked/closed transitions and close-only allowances. |
| P4-003 | Conditional protection visibility hardening | Align reconciliation/protection-health with Binance conditional SL evidence. | Active testnet position with confirmed SL no longer creates false severe protection block. |
| P4-004 | Runtime control lifecycle reset | Add startup-guard reset and shutdown/port-release verification. | Smoke run restores GKS, resets startup guard, and releases API port without force kill. |
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

`phase4_review_complete / real_live_not_authorized / continue_non_real_live_hardening`

