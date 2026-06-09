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

# PLC Account Risk And Liquidation Safety Spec

Date: 2026-05-25
Status: DESIGN_REVIEW

Runtime effect: none

Trading permission effect: none

## Purpose

Define the minimum account and liquidation safety checks required before PLC
Phase 3 testnet rehearsal. This spec is intentionally conservative and does not
authorize execution.

## Account Risk States

| State | Meaning | Required Action |
| --- | --- | --- |
| `unknown` | Account snapshot unavailable or field mapping uncertain. | Fail closed for new entries; allow risk-reducing close. |
| `healthy` | Required fields present and no threshold is breached. | Rehearsal may continue if all other gates pass. |
| `degraded` | Non-critical fields missing or stale, but no immediate liquidation risk. | New entry blocked for Phase 3; read-only review required. |
| `critical` | Margin/liquidation threshold breached or account data contradictory. | Hard lock; close/reduce only; stop rehearsal after evidence capture. |

## Required Input Fields

Best-effort field mapping must tolerate exchange differences, but Phase 3
preflight needs:

- `exchange_testnet=true`;
- symbol position amount;
- entry price;
- mark price or last price;
- liquidation price if provided by exchange;
- margin mode if provided;
- leverage if provided;
- wallet/equity or margin balance if provided;
- open order count for the rehearsal symbol.

If liquidation price is missing, the check cannot be `healthy`; it is at best
`degraded` unless the rehearsal is explicitly read-only.

## Liquidation Distance Rule

For a position with liquidation price:

- LONG distance = `(mark_price - liquidation_price) / mark_price`;
- SHORT distance = `(liquidation_price - mark_price) / mark_price`.

Phase 3 default thresholds:

- `distance <= 0`: `critical`;
- `0 < distance < 5%`: `critical`;
- `5% <= distance < 10%`: `degraded`;
- `>= 10%`: eligible for `healthy` if other fields pass.

These are safety thresholds only, not strategy constraints or return targets.

## Phase 3 Preflight

Before any controlled testnet order:

1. Verify profile is `sim1_eth_runtime`.
2. Verify `EXCHANGE_TESTNET=true`.
3. Verify no active testnet position for `ETH/USDT:USDT`.
4. Verify no open testnet orders for `ETH/USDT:USDT`.
5. Verify account risk state is not `critical`.
6. If state is `unknown` or `degraded`, do not start entry; capture evidence
   and stop.

## Runtime Behavior During Rehearsal

- If account state becomes `critical`, block new entries and permit
  reduce-only close.
- If liquidation distance cannot be computed after entry, mark state
  `degraded`; continue only to close and evidence capture.
- If final read-only check is not flat with zero open orders, stop and request
  explicit cleanup authorization.

## Non-Goals

- No real live trading.
- No real account read for Phase 3 unless a separate real-live authorization is
  granted, which this document does not request.
- No transfer, withdrawal, rebalancing, or account allocation.
- No strategy sizing/leverage advice.
