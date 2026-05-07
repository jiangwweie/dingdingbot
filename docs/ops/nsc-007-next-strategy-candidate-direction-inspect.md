# NSC-007 — Next Strategy Candidate Direction Inspect

**Date:** 2026-05-06
**Status:** Draft inspect report
**Scope:** Docs-only / inspect-only
**Affects Runtime Automatically:** No

---

## 0. Inspect Boundary

This task inspected only:

- `docs/ops/**`
- `archive/**`
- `reports/**`

This task did not run backtests, implement strategies, tune parameters, change runtime profiles, change risk rules, modify the backtester / research engine core, or modify `src/`, `configs/`, `tests/`, or `migrations/`.

This report does not provide a promotion conclusion and does not authorize any experiment.

---

## 1. Current State

Current facts:

- CPM-1 completed 2021/2022 OOS failure classification.
- CPM-1 remains paused and is not a small-live candidate.
- CPM-2 Candidate A/B were closed in NSC-006 after NSC-005 research-only proxy evidence classified both as `INSUFFICIENT_EVIDENCE`.
- Candidate C remains reserve-only and is not automatically started.
- The Live-safe foundation remains a system foundation and should not be rolled back because strategy candidates failed.
- The project currently has no deployable small-live strategy candidate.
- The small-live readiness gate remains unmet until a new candidate module passes an Owner-approved minimum evidence gate.

The current task is to choose the next candidate direction, not to implement or test it.

---

## 2. Evidence Inspected

Primary current docs:

- `docs/ops/project-roadmap-v2.md`
- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/crypto-pullback-module-v1-promotion-rejection-criteria.md`
- `docs/ops/nsc-001-cpm-2-candidate-direction-inspect.md`
- `docs/ops/nsc-002-cpm2-minimal-experiment-plan.md`
- `reports/nsc-003-cpm2-minimal-experiment/feasibility_gap_report.md`
- `docs/ops/nsc-004-cpm2-research-only-adapter-design-plan.md`
- `reports/nsc-005-cpm2-frozen-candidate-ab-experiment/experiment_report.md`
- `docs/ops/nsc-006-cpm2-ab-insufficiency-closure.md`

Historical trend-continuation evidence:

- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-t1-true-trend-follower-prototype.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-t1-donchian-4h-results.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-t1r-audit-report.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-c1-pinbar-t1-portfolio-proxy.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-c2-pinbar-t1-portfolio-parity.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-h6a-donchian-breakout-proxy.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-strategy-ecology-map-m0.md`

---

## 3. What Failed Before

### CPM-1 Failure Shape

CPM-1 is a pullback-continuation module with lower-timeframe reversal confirmation. Its 2021/2022 OOS failures showed:

- 2021 was a signal-level failure even before costs;
- losses clustered inside bull-year sub-regimes;
- lower-wick confirmation did not prove the pullback had ended;
- the EMA/MTF context lagged through hostile corrections and distribution-like periods.

The M0 ecology map further suggested CPM-1 behaves more like a pullback repair / counter-move strategy than a true trend follower. It tends to be fragile in high-slope, high-volatility, recently extended states.

### CPM-2 A/B Failure Shape

CPM-2 A/B tried to repair the pullback-ending confirmation without changing the broad CPM family:

- Candidate A delayed entry until one-bar reclaim.
- Candidate B added Donchian-location structural confirmation.

NSC-005 research-only proxy results were insufficient:

| Candidate | Closed Positions | Net PnL | PF | MaxDD | Classification |
| --- | ---: | ---: | ---: | ---: | --- |
| Candidate A | 56 | -973.0352 | 0.74997 | 0.16424 | `INSUFFICIENT_EVIDENCE` |
| Candidate B | 135 | -5682.2921 | 0.50660 | 0.56925 | `INSUFFICIENT_EVIDENCE` |

NSC-006 closed CPM-2 A/B as current mainline. This means the next direction should not be another CPM-1/CPM-2 A/B rescue path.

---

## 4. T1-lite Standalone Direction

### 4.1 Strategy Hypothesis

T1-lite standalone trend-continuation should be evaluated as a separate strategy module:

> ETH 4h trend-continuation can produce interpretable low-frequency trend-following evidence by entering after a confirmed Donchian-style breakout and exiting with ATR trailing, without relying on CPM-1 pullback entries, portfolio combination, or regime routing.

The core difference from CPM is structural:

| Dimension | CPM-1 / CPM-2 A/B | T1-lite Standalone |
| --- | --- | --- |
| Family | Pullback-continuation | Trend-continuation / trend-following |
| Primary timeframe | 1h | 4h |
| Entry idea | Pullback ending after lower-wick or local confirmation | Breakout / continuation confirmation after local range expansion |
| Exit idea | Fixed TP structure | ATR trailing / let winners run |
| Failure it accepts | Can miss early pullback entries | Can have many small losses and rare large winners |
| Candidate identity | CPM module family | New standalone module family |

### 4.2 Failure It Tries To Address

T1-lite addresses a different failure than CPM-2:

- CPM-1/CPM-2 kept trying to decide whether a 1h pullback had ended.
- Historical T1 evidence suggests 2023 was not necessarily trendless; instead, the 1h pullback-follow-through path was weak while 4h trend segments still existed.
- T1-lite would stop asking for lower-wick pullback repair and instead ask whether a larger timeframe continuation breakout can carry enough asymmetry to survive costs and whipsaw.

This is a direction shift, not a CPM rescue.

### 4.3 Historical Evidence Read

The original T1 4h Donchian report looked very strong, but T1R later found the original result was heavily inflated by same-bar entry lookahead.

Important corrected evidence:

| Evidence | Read |
| --- | --- |
| T1 original 4h Donchian | Strong but contaminated by same-bar entry lookahead; cannot be used as-is. |
| T1-R audit | Corrected next-bar entry, anti-lookahead, ATR timing, and MTM drawdown. Corrected strategy remained positive but much weaker. |
| T1-R corrected metrics | 3yr PnL +1,949, PF 1.29, 2023 +1,358, MTM MaxDD 7.3–10.9%, 109 trades over 3yr. |
| T1-R fragility | Top 1 winner contributed 46.3% of total PnL; Top 3 winners exceeded total PnL. Fragile. |
| H6a 1h Donchian breakout | Closed: 1h Donchian 20 was overactive and deeply negative. This argues for 4h, not 1h, and for no parameter rescue of H6a. |
| M0 ecology map | Suggests CPM and trend-following occupy different market states; useful as direction evidence, not as implementation approval. |

Interpretation:

T1-lite has enough historical evidence to justify a standalone experiment plan, but not enough to claim it is validated. The corrected evidence is positive yet fragile. The next task must freeze a minimum experiment plan with a fragility gate before any run.

### 4.4 Standalone Requirement

T1-lite must remain standalone.

Allowed framing:

- one candidate module;
- ETH-first;
- 4h OHLCV-derived entry;
- ATR trailing exit;
- low-frequency trend-continuation;
- independent evidence gate.

Not allowed framing:

- CPM-1 add-on leg;
- Pinbar hedge;
- portfolio component;
- multi-strategy runtime pretext;
- regime-router dependency;
- T1 + CPM-1 combination;
- capital allocation search.

Historical C1/C2 portfolio proxy evidence must not be interpreted as T1-lite standalone validation. C1/C2 tested portfolio behavior and capital mixing with Pinbar. They are useful warnings about T1 fragility and correlation, but they do not establish that T1-lite alone is a deployable candidate.

### 4.5 Data And Complexity

T1-lite does not appear to require new data capability for first-pass planning:

- existing ETH 4h OHLCV is enough for Donchian breakout and ATR calculation;
- existing cost-model and same-bar policy concepts can be reused for research planning;
- no orderbook, tick, feature store, OI, funding alpha, or external data is required for the first direction-level plan.

Complexity impact is moderate if kept standalone:

- it introduces a new strategy family and trailing-exit evidence contract;
- it should not require portfolio, regime, multi-strategy runtime, or multi-asset infrastructure;
- if T1-lite only works when paired with Pinbar or routed by regime/portfolio logic, it should be paused or rejected under current scope rather than used to justify platform expansion.

### 4.6 Current-Stage Fit

T1-lite fits the current stage better than CPM-2 rescue because:

- CPM-1/CPM-2 pullback confirmation path has already produced negative or insufficient evidence;
- T1-lite explores a genuinely different module hypothesis;
- it can be inspected and planned as a standalone low-frequency candidate;
- it aligns with the roadmap rule that strategy need drives complexity, not the other way around.

It remains risky because:

- corrected T1 evidence is fragile;
- trend-following naturally depends on rare large winners;
- 4h holds may increase operational exposure duration;
- T1-lite requires a clear MTM drawdown and top-winner concentration gate before any evidence can be interpreted.

### 4.7 T1-lite Direction Conclusion

Recommended classification:

| Field | Value |
| --- | --- |
| Direction | T1-lite standalone trend-continuation |
| Inspect conclusion | `PROCEED_TO_EXPERIMENT_PLAN` |
| Priority | P1 / next primary candidate direction |
| Evidence strength | Promising but fragile |
| Requires new data? | No for first-pass plan |
| Requires portfolio engine? | No; if yes, pause/reject |
| Requires regime system? | No; if yes, pause/reject |
| Requires multi-strategy runtime? | No; if yes, pause/reject |
| Promotion conclusion | None |

---

## 5. Direction Candidates Ranking

### 1. T1-lite Standalone Trend-continuation

**Rank:** 1

**Conclusion:** Proceed to experiment plan.

Reason:

- It is a true direction change from CPM pullback repair.
- Historical T1-R evidence remains positive after lookahead correction.
- It can be framed as standalone and low-frequency.
- It does not require new data or platform expansion for first-pass planning.

Required next constraints:

- freeze one standalone rule before results are inspected;
- include anti-lookahead requirements;
- include MTM drawdown;
- include top-winner concentration / fragility gates;
- include trade-count and year-by-year gates;
- explicitly exclude Pinbar/T1 portfolio combination.

### 2. T1-lite Alternative Simpler 4h Trend Confirmation Variant

**Rank:** 2 / backup direction only

**Conclusion:** Pause until T1-lite Donchian plan is accepted or rejected.

This is not a separate immediate experiment. It is a fallback direction-level idea: a simpler 4h trend-continuation rule family using 4h structure confirmation without portfolio/regime dependencies.

It should not start now because opening multiple trend-continuation variants would become parameter or family search. If T1-lite Donchian is rejected at plan level due to fragility or rule ambiguity, this family can be inspected later as a separate NSC task.

### 3. Candidate C Two-candle Pullback-end Pattern

**Rank:** reserve only

**Conclusion:** Pause / reserve.

Candidate C remains reserve-only from NSC-001/NSC-006. It should not automatically replace A/B because that would keep the project inside the CPM rescue path after A/B insufficiency.

---

## 6. Explicit Not-now Directions

Do not start the following under NSC-007:

- portfolio engine;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- full data feature store;
- tick/orderbook simulator;
- complex ML;
- CPM-1 rescue;
- CPM-2 A/B rescue;
- Candidate C automatic fallback;
- T1 + CPM-1 portfolio combination;
- capital allocation search;
- T1 parameter sweep;
- Donchian lookback sweep;
- ATR multiplier sweep;
- runtime strategy implementation;
- runtime profile or risk-rule changes.

If T1-lite requires portfolio, regime, or multi-strategy infrastructure to be viable, it should be paused or rejected at the strategy-candidate level. Current scope should not expand the platform to rescue a candidate.

---

## 7. Recommended Next Task

Create a separate Owner-approved task:

**NSC-008 — T1-lite Standalone Trend-continuation Minimal Experiment Plan**

Suggested task type:

- docs-only experiment plan;
- no implementation;
- no backtest;
- no runtime/profile/risk changes.

NSC-008 should define:

- strategy hypothesis;
- frozen standalone rule definition;
- allowed data windows;
- cost model SSOT;
- same-bar and next-bar entry policy;
- anti-lookahead proof requirements;
- required metrics;
- minimum trade count floor;
- MTM drawdown gate;
- top-winner concentration / fragility gate;
- pass / pause / reject classifications;
- explicit prohibition on portfolio, regime, multi-strategy, multi-asset, feature store, and complex ML.

---

## 8. Final Inspect Conclusion

NSC-007 recommends reopening the next strategy candidate path with:

1. **Primary direction:** T1-lite standalone trend-continuation.
2. **Classification:** `PROCEED_TO_EXPERIMENT_PLAN`.
3. **Next task:** NSC-008 docs-only minimal experiment plan, Owner-approved separately.

This is not a promotion conclusion. T1-lite is not a small-live candidate. The project still has no deployable small-live strategy candidate.

Small-live readiness gate remains unmet until a new candidate module passes an Owner-approved minimum evidence gate and is separately reviewed for operational readiness.
