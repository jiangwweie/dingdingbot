> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical research artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# CPM-MOD-002: CPM-1 Frozen Volatility Regime Gate Diagnostic Report

**Task ID:** CPM-MOD-002
**Date:** 2026-05-07
**Authorization:** Level 3 research-only
**Status:** Completed; frozen spec was written before execution and was not changed after results

---

## 0. Scope Guard

This task is a single frozen diagnostic for CPM-1 module applicability. It is not CPM rescue, not parameter optimization, not a runtime candidate, not a small-live readiness review, and not a strategy-router design.

Hard prohibitions:

- No CPM-1 baseline parameter changes.
- No parameter sweep, sensitivity, or multi-threshold comparison.
- No composite M0 score.
- No E4 hard or soft label.
- No position sizing treatment.
- No multi-factor regime search.
- No strategy router, portfolio allocator, or regime engine.
- No runtime/profile/risk/backtester core modification.
- No new data pipeline.
- No small-live or canary-live conclusion.

---

## 1. Frozen Baseline

The diagnostic uses the current CPM-1 frozen baseline described by `docs/ops/crypto-pullback-module-v1-scope-note.md` and the CPM-1 OOS runners.

| Dimension | Frozen value |
|-----------|--------------|
| Asset | ETH/USDT:USDT |
| Primary timeframe | 1h |
| MTF timeframe | 4h |
| Direction | LONG-only |
| Trigger | Pinbar, min_wick_ratio=0.6, max_body_ratio=0.3, body_position_tolerance=0.1 |
| Trend filter | EMA50, min_distance_pct=0.005 |
| MTF confirmation | 4h EMA60 |
| ATR trade filter | Disabled; remains disabled |
| TP | TP1 1.0R 50%, TP2 3.5R 50% |
| SL | -1.0R, pinbar candle low |
| Breakeven | OFF |
| Trailing | OFF |
| OCO | ON |
| Cost model | fee_rate=0.0004, entry slippage=0.001, TP slippage=0.0005, funding enabled |
| Same-bar policy | pessimistic |
| Backtest mode | v3_pms with MockMatchingEngine |

No conflict was found between the scope note and the CPM-1 OOS runner configuration before writing this spec.

---

## 2. Frozen Gate Spec

### 2.1 Selected Feature

**Selected volatility feature:** rolling ATR percentile.

Rejected alternative for this diagnostic: rolling realized volatility percentile. It is not tested in CPM-MOD-002 because the task allows only one volatility feature.

### 2.2 Feature Definition

The gate uses only ex-ante OHLCV from closed ETH/USDT:USDT 1h candles.

- Compute 1h ATR14 with Wilder smoothing.
- For each 1h signal bar, compute the percentile rank of the latest closed ATR14 against the prior 90 calendar days of 1h ATR14 observations, excluding the current ATR value.
- The rolling window length is 2,160 bars.
- If the trailing percentile window is unavailable or incomplete, the module remains enabled. This avoids retroactively disabling early-history bars using data that was not yet observable.
- No funding, OI, orderbook, trade outcome, or future bar information is used.

### 2.3 Threshold

**Frozen threshold:** disable CPM-1 when `rolling_atr_percentile > 0.60`.

Rationale fixed before execution:

- CPM-MOD-001 observed year-level ATR percentile around 0.625 in 2023 and around 0.531 in 2024/2025.
- The CPM-1 scope note lists high-volatility regimes with ATR percentile above roughly 0.6 as not-applicable.
- Therefore 0.60 is a structural upper-bound test for the hypothesis: high-volatility regimes disable CPM-1 at module level.

This is not a threshold search. CPM-MOD-002 does not test 0.55, 0.65, sensitivity, or any alternative threshold.

### 2.4 Gate Semantics

This is a module-level enable/disable gate:

- When the gate is enabled, CPM-1 runs exactly as the frozen baseline.
- When the gate is disabled, CPM-1 does not open new positions.
- Existing open positions continue under the frozen CPM-1 lifecycle; exits are not changed.
- The gate is evaluated before signal-to-order creation using only closed-bar information.

The implementation is a report-local research adapter. It does not register a runtime strategy and does not modify backtester core.

---

## 3. Pre-Registered Judgment Criteria

### PASS / HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION

Only if all are true:

- 2021 or 2023 loss improves materially.
- 2024/2025 profit is mostly preserved.
- Favorable-year trade count and winner count are not over-compressed.
- Top-winner fragility does not clearly worsen.
- The result does not depend on boundary threshold micro-tuning.
- Gate behavior is explainable by the pre-registered volatility hypothesis.

### FAIL / CLOSED_DYNAMIC_ENABLEMENT

If any decisive failure appears:

- The gate improves only one bad year while killing 2024/2025.
- 2021 remains materially unimproved and unexplained.
- Key 2024/2025 winners are clearly disabled.
- Trade count or winner count is severely compressed.
- Top-winner fragility worsens.
- The result would require threshold tuning, added features, E4, position sizing, or post-hoc interpretation.

### INCONCLUSIVE_PAUSE

If:

- There is partial improvement but not enough to strengthen or close the hypothesis.
- Sample size becomes too thin.
- Year conclusions conflict.
- Further validation would be needed but cannot be justified as a direct upgrade path.

---

## 4. Stop Conditions

The diagnostic must stop or downgrade if it requires:

1. Parameter sweep.
2. More than one volatility feature.
3. Composite score.
4. E4 hard or soft label.
5. Position sizing.
6. Strategy router, portfolio allocation, or regime engine.
7. CPM-1 baseline changes.
8. New data pipeline.
9. Post-hoc explanation.
10. Runtime candidate interpretation.

---

## 5. Execution Results

Artifacts:

- Adapter: `reports/cpm-mod-002-cpm1-frozen-volatility-gate/cpm_mod_002_diagnostic_adapter.py`
- Summary: `reports/cpm-mod-002-cpm1-frozen-volatility-gate/summary.json`
- Per-year raw reports: `baseline_YYYY_result.json`, `gated_YYYY_result.json`

Execution notes:

- The adapter is report-local and monkeypatches only the in-process isolated strategy runner. No runtime/profile/risk/backtester core file was modified.
- Overall figures are the sum of independent yearly fixed-balance runs, not a continuous five-year compounding run.
- `MTM MaxDD` is the backtester-reported mark-to-market drawdown. `Realized MaxDD` is computed from closed-position PnL sequencing for diagnostic comparison.

### 5.1 Overall: Baseline vs Gated

| Metric | Baseline | Gated | Delta / read |
|--------|----------|-------|--------------|
| Net PnL | -2,490.74 | -1,557.37 | +933.37 |
| PF | 0.80 | 0.87 | Improved, still below 1 |
| Win rate | 38.82% | 39.42% | Slight improvement |
| Trade count | 255 | 208 | -47 trades |
| Winner count | 99 | 82 | -17 winners |
| Realized MaxDD | 36.11% | 25.72% | Improved |
| Worst yearly MTM MaxDD | 22.18% | 11.04% | Improved |
| Fees | 1,626.58 | 1,397.70 | Lower due fewer trades |
| Slippage | 3,097.57 | 2,654.26 | Lower due fewer trades |
| Funding | 115.19 | 109.33 | Slightly lower |

Overall improvement comes entirely from 2021. The gate did not change 2022, 2023, 2024, or 2025 trade sets.

### 5.2 Year-by-Year

| Year | Baseline PnL | Gated PnL | Delta | Baseline trades / winners | Gated trades / winners | PF base -> gated | MTM MaxDD base -> gated | Disabled baseline trades |
|------|--------------|-----------|-------|----------------------------|-------------------------|------------------|--------------------------|--------------------------|
| 2021 | -1,992.49 | -1,059.11 | +933.37 | 99 / 35 | 52 / 18 | 0.53 -> 0.57 | 22.18% -> 10.59% | 37 |
| 2022 | -763.72 | -763.72 | 0.00 | 51 / 16 | 51 / 16 | 0.66 -> 0.66 | 8.22% -> 8.22% | 0 |
| 2023 | -785.24 | -785.24 | 0.00 | 20 / 5 | 20 / 5 | 0.42 -> 0.42 | 11.04% -> 11.04% | 0 |
| 2024 | 850.61 | 850.61 | 0.00 | 44 / 26 | 44 / 26 | 1.96 -> 1.96 | 5.02% -> 5.02% | 0 |
| 2025 | 200.10 | 200.10 | 0.00 | 41 / 17 | 41 / 17 | 1.28 -> 1.28 | 4.81% -> 4.81% | 0 |

Disabled period summary:

| Year | Disabled days | Disabled periods | Longest disabled period | Actual baseline trades disabled |
|------|---------------|------------------|--------------------------|---------------------------------|
| 2021 | 195.13 | 130 | 2021-01-01 to 2021-02-12, 42.25 days | 37 |
| 2022 | 69.79 | 117 | 2022-05-09 to 2022-05-15, 5.79 days | 0 |
| 2023 | 170.96 | 147 | 2023-11-04 to 2023-11-19, 14.42 days | 0 |
| 2024 | 170.17 | 118 | 2024-02-25 to 2024-03-28, 32.42 days | 0 |
| 2025 | 140.58 | 131 | 2025-07-14 to 2025-07-26, 12.63 days | 0 |

Interpretation:

- The gate has real bite at the market-state level: it disables many high-volatility periods.
- The only year where this overlaps actual CPM-1 entries is 2021.
- 2023 remains a negative CPM-1 year because its actual CPM-1 entries occur outside this frozen high-volatility gate.
- 2024/2025 are fully preserved because none of their baseline entries are disabled.

### 5.3 Fragility

| Metric | Baseline | Gated | Read |
|--------|----------|-------|------|
| Position-level PnL | -1,799.12 | -955.28 | Improved |
| Top-1 removal PnL | -1,981.35 | -1,137.50 | Improved, still negative |
| Top-3 removal PnL | -2,341.54 | -1,497.70 | Improved, still negative |
| Top-5 removal PnL | -2,696.03 | -1,852.19 | Improved, still negative |
| Top winner PnL | 182.23 | 182.23 | Same top winner preserved |
| Top winner / gross wins | 3.0% | 3.0% | Overall top-winner concentration not worsened |

Disabled baseline trades:

- 37 baseline trades disabled, all in 2021.
- 7 disabled winners, with +797.39 position-level winner PnL.
- Disabled trade set total position-level PnL was -891.55, so the gate removed a net-negative 2021 cluster despite killing some winners.
- The top 10 baseline winners were all preserved; their ATR percentiles were below the frozen 0.60 threshold.

Residual fragility remains:

- 2024 remains positive after top-5 removal only barely: +72.37 position-level PnL.
- 2025 turns negative after top-3 removal: -203.14 position-level PnL.
- The gate does not solve favorable-year top-N dependence; it only avoids one 2021 loss cluster.

### 5.4 Trade Quality

Average MFE / MAE / giveback, position-level diagnostic:

| Year | Baseline avg MFE | Gated avg MFE | Baseline avg MAE | Gated avg MAE | Baseline avg giveback | Gated avg giveback |
|------|------------------|---------------|------------------|---------------|-----------------------|--------------------|
| 2021 | 139.23 | 167.86 | -156.25 | -155.46 | 161.58 | 189.80 |
| 2023 | 80.48 | 80.48 | -114.13 | -114.13 | 119.74 | 119.74 |
| 2024 | 876.16 | 876.16 | -172.48 | -172.48 | 844.90 | 844.90 |
| 2025 | 179.14 | 179.14 | -120.09 | -120.09 | 169.39 | 169.39 |

Observations:

- Trade-quality changes are limited to 2021 because no other year has disabled trades.
- 2021 average MFE improves and average MAE is roughly unchanged, which is consistent with removing weak high-volatility entries.
- 2021 average giveback increases among remaining trades, so the gate should not be interpreted as a lifecycle/exit improvement.
- 2023 quality is unchanged; this volatility gate does not explain 2023 CPM-1 failure.

### 5.5 Applicability Read

**2021:** Improved materially. Net PnL improves by +933.37, trade count compresses from 99 to 52, and MTM MaxDD falls from 22.18% to 10.59%. This supports the idea that at least one 2021 adverse CPM-1 sub-regime was ex-ante high-volatility.

**2023:** Not improved. The gate disables 170.96 days of 2023 market time, but none of the actual baseline CPM-1 trades. This is the main negative finding. A single ATR percentile upper-bound does not identify the 2023 CPM-1 loss boundary.

**2024:** Fully preserved. No trades disabled; PnL, trade count, winner count, PF, MaxDD, and fragility are unchanged.

**2025:** Fully preserved. No trades disabled; PnL, trade count, winner count, PF, MaxDD, and fragility are unchanged.

**Module validity gate interpretation:** The behavior is partially consistent with a module-level validity gate, not a trade-outcome filter: it uses only closed OHLCV, is frozen before execution, and disables market periods before signal-to-order creation. However, because it does not touch 2023, it is not sufficient as a CPM-1 applicability boundary.

---

## 6. Stop Condition Review

| Stop condition | Status |
|----------------|--------|
| Parameter sweep required | Not triggered |
| More than one volatility feature required | Not triggered |
| Composite score required | Not triggered |
| E4 hard/soft label required | Not triggered |
| Position sizing required | Not triggered |
| Strategy router / portfolio / regime engine required | Not triggered |
| CPM-1 baseline change required | Not triggered |
| New data pipeline required | Not triggered |
| Post-hoc explanation required | Not triggered |
| Runtime candidate interpretation | Not triggered |

No stop condition was violated.

---

## 7. Classification

**Final classification:** `HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION`.

Reason:

- The frozen ATR percentile gate materially improves 2021 while preserving 2024/2025 completely.
- Favorable-year trade count and winner count are not harmed.
- Top-N fragility does not worsen, and the largest winners are preserved.
- The result does not rely on threshold tuning or additional features.
- The behavior is explainable by the pre-registered volatility hypothesis.

Important limitation:

- The gate does not improve 2023 at all. Therefore it is not a validated CPM-1 applicability boundary and is not sufficient to reopen CPM-1 as a runtime or small-live candidate.

Recommended interpretation:

- CPM-MOD-002 strengthens the narrow hypothesis that a high-volatility module gate can avoid some 2021-style CPM-1 damage.
- It does not solve CPM-1 dynamic enablement, because the 2023 failure boundary remains unidentified under the only allowed frozen volatility gate.
- Any further work must remain under Strategy Module Applicability / Validity Gate governance and requires fresh Owner authorization.

---

## 8. Owner Summary

**Frozen gate spec:** ETH/USDT:USDT 1h ATR14 rolling percentile over the prior 90 days; disable CPM-1 when percentile > 0.60; warmup bars remain enabled; only closed OHLCV used.

**Selected volatility feature:** rolling ATR percentile. Realized volatility was not tested.

**Threshold rationale:** CPM-MOD-001 observed 2023 ATR percentile around 0.625 vs 2024/2025 around 0.531, and the CPM-1 scope note marks ATR percentile above roughly 0.6 as not-applicable.

**Core result:** baseline overall net PnL -2,490.74 vs gated -1,557.37. The +933.37 improvement comes entirely from 2021.

**2021 / 2023:** 2021 improves materially; 2023 is unchanged.

**2024 / 2025:** both fully preserved. No 2024 or 2025 baseline trades are disabled.

**Trade count / winner count:** overall trades compress from 255 to 208 and winners from 99 to 82. Favorable-year counts are unchanged: 2024 stays 44/26, 2025 stays 41/17.

**Top-N fragility:** not worsened overall; top 10 baseline winners are preserved. Favorable-year fragility still exists, especially 2025 after top-3 removal.

**MFE / MAE / giveback:** only 2021 changes; average MFE improves, MAE is roughly unchanged, and giveback increases among remaining trades. No lifecycle improvement should be inferred.

**Stop conditions:** none violated.

**Final classification:** `HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION`.

**Recommendation:** do not promote CPM-1, do not start CPM-2, do not design a router, and do not treat this as runtime readiness. If Owner wants follow-up, it should be an applicability-map update or a separately authorized validation task, not parameter rescue.

**Small-live gate:** still not satisfied. CPM-1 remains not a runtime candidate and not a deployable small-live strategy.
