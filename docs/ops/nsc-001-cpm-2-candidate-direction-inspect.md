# NSC-001 — CPM-2 Candidate Direction Inspect

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

This task did not run backtests, implement strategies, change runtime profiles, change risk rules, or modify `src/`, `configs/`, `tests/`, or `migrations/`.

CPM-1 remains frozen. This report does not provide a promotion conclusion.

---

## 1. Current State

CPM-1 has completed 2021/2022 OOS failure classification and the promotion path is paused.

Current facts:

- There is no deployable small-live strategy candidate.
- Live-safe foundation remains valuable as system infrastructure, but it does not imply strategy readiness.
- CPM-1 frozen baseline must not be rescued through parameter tuning.
- Any CPM-2 direction must be a new candidate module direction, not a Pinbar parameter variant.
- The small-live readiness gate remains unmet until a new candidate module passes an Owner-approved minimum evidence gate.

---

## 2. Evidence Read

### 2.1 CPM-1 failure classification

Primary current evidence:

- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-report.md`
- `reports/oos_runs/cpm1_2021_oos/result.json`
- `reports/oos_runs/cpm1_2022_oos/result.json`

Key points:

- 2021 OOS was a favorable bull year but CPM-1 lost -21.54%, with 29.5% win rate, PF 0.466, and negative gross edge before costs.
- 2021 loss was concentrated in sub-periods, especially Feb-Mar and Aug-Oct, not just the May crash.
- 2022 OOS also failed, but its failure is more consistent with LONG-only cost and whipsaw in a bear market.
- The 2021 failure is more serious because it directly challenges the CPM-1 profit hypothesis in the regime where it was expected to work.

### 2.2 Lower-wick confirmation evidence

Relevant historical evidence:

- `archive/2026-04-29-pre-live-safe-replan/docs/diagnostic-reports/DA-20260419-003-pinbar-component-analysis.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/continuation-ability-diagnosis-report.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-h3a-followthrough-feature-check.md`

Interpretation:

- Pinbar wick geometry alone has weak explanatory power. `wick_ratio` correlation with win rate was only +0.0583, and `body_ratio` was also not meaningfully predictive.
- The continuation diagnosis showed the key failure mode is weak post-entry favorable excursion: 2023 MFE was materially below 2024/2025 while MAE was similar.
- H3a found some pre-entry feature separation for follow-through, but fixed thresholds could not separate bad-year trades from good-year trades without killing good-year winners.

Conclusion:

CPM-1 failure is consistent with lower-wick confirmation being too weak, but the evidence does not support the narrower claim that "stronger Pinbar geometry" fixes it. The problem is broader: a single lower-wick reversal mark does not reliably confirm that the pullback has ended and that continuation has restarted.

### 2.3 Stronger pullback-ending confirmation evidence

Relevant historical evidence:

- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-strategy-ecology-map-m0.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-pinbar-toxic-state-avoidance-m1.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-pinbar-toxic-state-m1b-parity.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-m1c-donchian-distance-official-check.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-h5b-engulfing-pnl-proxy.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-t1-donchian-4h-results.md`

Interpretation:

- Market-location evidence around Donchian distance was the most stable historical signal for removing toxic CPM-1 trades across M1/M1b/M1c proxy/parity checks.
- Standalone Engulfing failed in full PnL proxy despite healthy reach-rate slices, mainly due to signal density and noise.
- H3a shows that features like EMA distance/slope and recent returns have statistical separation but are unsafe as simple fixed skip filters.
- T1 4h Donchian looked strong, but it is a different strategy family: 4h breakout/trend-following, not ETH 1h pullback-continuation.

Conclusion:

The strongest "nearby" evidence for CPM-2 is not another candlestick geometry. It is a stricter pullback-ending confirmation that combines the existing pullback structure with either local range-location discipline or a delayed continuation/reclaim confirmation.

---

## 3. CPM-2 Candidate Trigger Families

### Candidate A — One-Bar Continuation Reclaim

**Strategy hypothesis**

After a pullback signal, CPM-2 should wait for a continuation-confirming close before entry. A valid long setup would require the pullback marker plus a subsequent 1h candle that reclaims local structure, such as closing above the signal candle high, above a short local pivot, or back into the EMA-aligned continuation zone.

**Difference from CPM-1**

CPM-1 enters on lower-wick reversal geometry. Candidate A treats the wick as a setup marker only; the actual trigger is delayed confirmation that buyers followed through after the pullback.

**Failure it tries to address**

It targets fake rebound / falling-knife failures and the 2021 loss clusters where EMA trend remained active but lower-wick confirmation did not prove that the correction had ended.

**New data needed**

No new external data. It needs existing 1h OHLCV plus already available EMA/MTF context.

**Complexity impact**

Low to moderate. It adds a delayed trigger state and may reduce trades. It does not require portfolio, regime, ML, or multi-asset infrastructure.

**Minimum evidence gate**

- Compare CPM-1 frozen baseline vs Candidate A on 2021 and 2022 OOS plus 2023/2024/2025 reference years, under the same cost and same-bar policy.
- Must improve 2021 gross edge or materially reduce 2021 loss clusters without destroying 2024/2025 positive behavior.
- Must not rely on a single threshold selected to rescue one year.
- Trade count must remain sufficient for interpretation.

**Reject / pause conditions**

- Reject if it mainly reduces trades without improving gross expectancy.
- Reject if 2024/2025 winners are systematically missed in the same pattern seen in the 0.382 limit-entry proxy.
- Pause if the improvement depends on parameterized variants of Pinbar geometry rather than the new continuation-confirmation step.

### Candidate B — Donchian-Location Pullback Confirmation

**Strategy hypothesis**

A pullback-continuation setup should be accepted only when the pullback ends in a healthy local range location, not in historically toxic positions relative to the recent Donchian channel. The trigger remains a pullback-ending confirmation; Donchian location acts as the structure discipline around that trigger.

**Difference from CPM-1**

CPM-1 only asks whether a lower-wick reversal appears inside EMA/MTF trend context. Candidate B asks whether the apparent pullback end is located in a historically survivable part of the recent range.

**Failure it tries to address**

It targets toxic state entries, especially trades that win often but lose more when they lose. M1/M1b/M1c evidence suggests Donchian-distance filtering improved CPM-1 proxy/parity outcomes and reduced drawdown, though it has not become CPM-2 evidence yet.

**New data needed**

No new external data. It needs rolling 1h highs/lows from existing OHLCV.

**Complexity impact**

Moderate. It introduces a stateful rolling-range calculation, but avoids portfolio, regime, ML, multi-asset, and feature-store scope.

**Minimum evidence gate**

- First define the Donchian-location rule as a pullback-continuation confirmation, not as Donchian breakout.
- Re-test on 2021/2022 OOS and 2023/2024/2025 references with official backtester semantics, not only proxy.
- Demonstrate that skipped trades are net toxic in 2021/2022 and not merely overfit to 2023.
- Confirm current-bar exclusion / anti-lookahead behavior.

**Reject / pause conditions**

- Reject if the rule becomes a Donchian breakout entry.
- Reject if official backtester results fail to reproduce proxy/parity improvement.
- Pause if the threshold needs broad tuning or multiple rescue filters to work.

### Candidate C — Two-Candle Pullback-End Pattern, Not Standalone Engulfing

**Strategy hypothesis**

The pullback end may require a two-candle confirmation family, such as rejection plus bullish follow-up, inside the existing EMA/MTF pullback context. The candidate is not "Engulfing strategy"; it is a low-density, pullback-scoped confirmation pattern.

**Difference from CPM-1**

CPM-1 treats a single Pinbar candle as enough confirmation. Candidate C requires a second candle to validate that the market accepted the reversal and began continuation.

**Failure it tries to address**

It tries to reduce single-candle noise and lower-wick false positives. It is closest to the "lower-wick confirmation is too weak" hypothesis.

**New data needed**

No new external data. Existing `kline_history` support is enough for multi-candle pattern inspection.

**Complexity impact**

Low to moderate technically, but higher research risk because standalone Engulfing already failed.

**Minimum evidence gate**

- Signal density must remain close to CPM-1 scale, not Engulfing scale.
- Full PnL proxy must pass before any parameter search.
- Must show incremental improvement over Candidate A or B, not only better raw reach rate.

**Reject / pause conditions**

- Reject if it becomes standalone Engulfing or another high-density candlestick strategy.
- Reject if reach rate looks healthy but PnL is negative, repeating H5a/H5b.
- Pause if it requires adding filters after a failed dense trigger.

---

## 4. Family Boundary

Still eligible for CPM-2:

- ETH 1h pullback-continuation.
- Existing higher-timeframe directional bias.
- Existing OHLCV-derived confirmation.
- Delayed pullback-end confirmation.
- Local range-location confirmation, if used to validate pullback quality rather than enter breakouts.

Not CPM-2:

- Pinbar parameter variants.
- 4h Donchian breakout / trend-following.
- Standalone Engulfing.
- Regime gate as the main strategy.
- Portfolio construction.
- Multi-strategy allocator.
- Multi-asset expansion.
- Feature store / complex ML.

---

## 5. Not Now

NSC-001 does not authorize:

- Backtests.
- Strategy implementation.
- Changes to `src/`, `configs/`, `tests/`, or `migrations/`.
- Runtime profile changes.
- Risk rule changes.
- Portfolio, regime, multi-strategy, multi-asset, feature-store, or complex-ML work.
- Any promotion or small-live decision.

---

## 6. Inspect Recommendation

It is worth entering a later Owner-approved experiment-plan step, but only under tight boundaries.

Recommended order:

1. Candidate A — One-Bar Continuation Reclaim.
2. Candidate B — Donchian-Location Pullback Confirmation.
3. Candidate C only if A/B fail to produce enough evidence and the design stays low-density and pullback-scoped.

The next step should be an experiment plan, not implementation. The plan should specify frozen baselines, windows, exact metrics, reject gates, allowed files, and a prohibition on parameter rescue.

Until a new candidate module passes its minimum evidence gate, the project still does not satisfy small-live readiness.
