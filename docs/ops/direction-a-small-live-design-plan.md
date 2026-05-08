# Direction A Docs-only Small-live Design Plan

**Status:** Draft / Owner-reviewable design only
**Date:** 2026-05-08
**Classification:** `SMALL_LIVE_DESIGN_NEEDS_RUNTIME_CHECKLIST`
**Recommendation:** C first; D only after successful rehearsal
**Affects Runtime Automatically:** No

---

## 1. Boundary

This is a docs-only design plan. It does not authorize small-live execution,
runtime activation, exchange/API activation, live orders, capital allocation,
strategy changes, parameter optimization, deployment, portfolio/router
implementation, TE execution, CPM reopening, or promotion.

Direction A remains:

`CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`

Owner approval is required before any paper/live-safe rehearsal or small-live
execution.

## 2. Small-live Objective

Observe whether Direction A's cross-asset smart-beta trend timing mechanism can
be executed operationally at very small risk while preserving research
discipline.

The objective is not to maximize PnL, prove deployment readiness, optimize
sizing, or validate profitability over a short window. A few trades cannot
validate a sparse trend system.

## 3. Candidate Symbols

Initial symbols under consideration:

- BTC/USDT:USDT
- ETH/USDT:USDT
- SOL/USDT:USDT

Recommended design stance:

- Phase 1: BTC and ETH only.
- SOL: optional Phase 2 only after rehearsal and only with low vol-normalized
  sizing plus a strict SOL risk share cap.

Reasoning: P2 shows low vol-normalized sizing reduces SOL absolute PnL share
from 32.1% under fixed-risk 0.50% to 24.1%. That supports including SOL only
when the sizing policy actively suppresses high-volatility dominance.

## 4. Capital Envelope

Owner context: total project capital reference within approximately 3wU.

Candidate observation sleeves:

| Sleeve | Percent of 3wU | Approx amount |
| --- | ---: | ---: |
| Ultra-small | 5% | 1500U |
| Conservative | 10% | 3000U |
| Maximum design cap | 15% | 4500U |

Recommended design sleeve: 5% first, with 10% as a later Owner-reviewed cap.
Do not use 15% at start. Full capital must not be used for observation.

## 5. Risk Per Trade

Risk is defined as percent of the small-live sleeve, not total project capital.

Candidate levels:

| Risk level | Use |
| --- | --- |
| 0.25% of sleeve | Recommended default |
| 0.50% of sleeve | Upper normal design band after rehearsal |
| 1.00% of sleeve | Upper bound only; not recommended default |

P2 shows fixed-risk 0.50% performed well in research, but small-live should
prioritize survival, execution integrity, and discipline. Direction A has low
win rate and sparse payoff dependence; small-live loss streak tolerance matters
more than return capture.

## 6. Sizing Policy

Recommended design: hybrid fixed-risk cap plus vol-normalized adjustment.

Policy proposal:

- Base risk target: 0.25% of sleeve per trade.
- Optional post-rehearsal band: up to 0.50% of sleeve per trade.
- 20-day realized volatility adjustment may reduce risk for high-volatility
  assets.
- No leverage by default.
- Hard max notional cap per asset must be enforced before execution.
- No optimized target volatility and no performance-selected sizing target.

This follows P2: low vol-normalized sizing reduced drawdown to 3.06% in the
research scenario while preserving positive sparse trend payoff.

## 7. Exposure Caps

Default exposure caps:

- Max concurrent positions: 2.
- Max concurrent positions 3: Owner approval required.
- Max total open initial risk: 1.0% of sleeve default; 1.5% hard design cap.
- Max single-asset initial risk: 0.50% of sleeve.
- Max SOL risk share: 25% of open risk if SOL is enabled.
- Max correlated crypto exposure: all open Direction A exposure must be treated
  as one correlated crypto trend sleeve.

P2 reference:

- Max-2 exposure cap: net 6496.39, DD 4.19%.
- Low vol-normalized sizing: DD 3.06%.
- SOL share under low vol-normalized sizing: 24.1%.

## 8. Entry / Exit Operational Rules

Frozen Direction A only:

- 4h Donchian20 close breakout.
- Next 4h open entry.
- Previous-20-low initial stop.
- EMA60 close-break exit.
- No discretionary entries.
- No Donchian, EMA, stop, exit, symbol, or sizing optimization.
- No manual override except emergency kill-switch.

Signal cadence:

- Evaluate only after fully closed 4h bars.
- No intrabar signal chasing.
- Orders may be staged only after closed-bar confirmation.
- All timestamps should be recorded in UTC and reconciled to exchange time.

## 9. Kill Switches

Design proposals only; exact values require Owner approval before execution.

Hard stop / pause conditions:

- Pause if sleeve drawdown exceeds 5%.
- Hard stop if sleeve drawdown exceeds 8%.
- Pause after 8 consecutive losing trades across the basket.
- Pause if daily realized loss exceeds 1.0% of sleeve.
- Pause if weekly realized loss exceeds 2.5% of sleeve.
- Pause if total open risk would exceed 1.0% default or 1.5% hard cap.
- Pause if any symbol has abnormal missing data, stale candles, or timestamp
  mismatch.
- Pause on exchange/API/order state mismatch.
- Pause if realized slippage materially exceeds model assumptions for two
  consecutive orders.
- Pause if funding exceeds a pre-defined stress threshold for the held symbol.
- Manual Owner pause always overrides automation.

## 10. Monitoring Metrics

Required monitoring:

- Trades taken and skipped.
- Active positions.
- Open initial risk and notional exposure.
- Realized PnL and MTM PnL.
- Sleeve drawdown.
- Funding cost.
- Slippage vs model.
- Signal latency.
- Order fill quality.
- Max simultaneous exposure.
- Asset risk contribution.
- Rule-match audit: every trade must match frozen Direction A.
- Skipped-trade log with reason.
- Data quality, exchange status, and reconciliation status.

## 11. Observation Duration

Minimum observation duration:

- Not less than 3 months.
- Prefer 6 months.
- Minimum evidence floor: 30 closed trades across the basket before any
  interpretation review.

Sparse trend systems cannot be judged over a few trades. A profitable early
sample is not success, and an early loss streak is not automatically failure
unless kill switches trigger.

## 12. Success / Failure Criteria

Success criteria:

- Frozen rule execution integrity maintained.
- No operational violations.
- Signal generation matches research logic.
- Risk caps and exposure caps function correctly.
- Realized slippage and funding remain within expected design bands.
- Drawdown remains within design limits.
- All skipped trades are documented.
- Reconciliation and logging are reliable.

Failure criteria:

- Any kill switch triggered.
- Rule mismatch or unapproved discretionary action.
- Unexpected slippage/funding that invalidates assumptions.
- Correlated drawdown exceeds cap.
- Manual intervention required outside emergency pause.
- Inability to maintain monitoring or reconciliation discipline.

## 13. Promotion Rules

Small-live observation cannot automatically promote Direction A.

Even if profitable, any promotion requires:

- separate review;
- SRR-002 reassessment;
- live evidence interpretation;
- updated risk report;
- explicit Owner decision.

Profit during observation is operational evidence only, not deployment proof.

## 14. Implementation Preconditions

Before any paper/live-safe rehearsal or small-live execution:

- Runtime environment reviewed.
- Exchange API permissions restricted.
- Max order size enforced.
- Paper/dry-run rehearsal completed.
- Risk limits configured.
- Logging verified.
- Reconciliation verified.
- Kill switch tested.
- Signal-to-order audit path verified.
- Funding/slippage monitoring verified.
- Owner approves exact capital sleeve, symbols, risk per trade, exposure caps,
  and stop conditions.

## 15. Recommendation

Recommendation: C first, then D only after successful rehearsal.

- C: Owner may consider paper/live-safe rehearsal first.
- D: Owner may consider ultra-small small-live only after implementation
  checklist, rehearsal, and explicit Owner approval.

Do not proceed directly to live execution. Preserve this plan as the design
baseline for Owner review.

## 16. Inputs Inspected

- `docs/ops/direction-a-p2-risk-shape-diagnostic.md`
- `reports/direction-a-p2-risk-shape-diagnostic/p2_summary.json`
- `reports/direction-a-p2-risk-shape-diagnostic/risk_shape_scenarios.json`
- `reports/direction-a-p2-risk-shape-diagnostic/risk_shape_scenarios.md`
- `reports/direction-a-p2-risk-shape-diagnostic/portfolio_drawdown_summary.json`
- `reports/direction-a-p2-risk-shape-diagnostic/risk_contribution_summary.json`
- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/sma-001-strategy-module-applicability-map.md`

Direction A small-live design plan is docs-only. It does not authorize runtime activation, live orders, capital allocation, strategy changes, parameter optimization, or deployment. Any paper/live-safe rehearsal or small-live execution requires separate Owner approval and must satisfy SRR-002 and live-safe operational gates.
