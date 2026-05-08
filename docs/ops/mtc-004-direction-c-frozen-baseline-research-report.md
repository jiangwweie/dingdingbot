# MTC-004 — Direction C Frozen Baseline Research Report

**Task ID:** MTC-004
**Date:** 2026-05-07
**Status:** Completed / Research-only Standalone Adapter Evidence
**Authorization Level:** Level 3 research-only

---

## 0. Boundary

This report presents research-only standalone adapter evidence for
Direction C. It is not:

- official validation;
- a promotion conclusion;
- a small-live readiness review;
- a runtime implementation approval;
- a live deployment recommendation;
- a parameter optimization result.

No runtime, profile, risk, or backtester-core changes follow from this
report. Small-live readiness gate remains unmet. No deployable strategy
candidate exists.

---

## 1. Frozen Specification

### 1.1 Entry Mechanism

| Field | Frozen Value | Structural Rationale |
|-------|-------------|---------------------|
| Entry family | Volatility contraction + bullish re-expansion in uptrend | Direction C hypothesis |
| Trend context | 4h close > EMA60 | Inherited from Direction A; uptrend prerequisite |
| Contraction metric | avg_range(6) / avg_range(20) | Recent 24h range vs 80h norm; ratio captures compression |
| Contraction threshold | < 0.7 | Recent range ≤ 70% of norm = material compression |
| Re-expansion condition | Current bar range ≥ 1.2 × avg_range(6) | Current candle expands beyond recent norm |
| Re-expansion direction | Close > Open (bullish candle) | Must be in trend direction |
| Entry execution | Next 4h bar open + entry slippage | Anti-lookahead; consistent with Direction A |
| Same-bar entry | Not allowed | — |

### 1.2 Initial Stop

| Field | Frozen Value |
|-------|-------------|
| Stop level | Lowest low of prior 6 closed 4h bars (signal bar excluded) |
| Stop status | Active throughout trade |
| Stop execution | Pessimistic ordering: stop checked before EMA60 same-bar |

### 1.3 Exit

| Field | Frozen Value |
|-------|-------------|
| Exit family | 4h EMA60 close-break trend-lifecycle exit (inherited from Direction A) |
| Exit trigger | Fully closed 4h candle close below EMA60 |
| Intrabar EMA60 touch | Does not trigger exit |
| Exit execution | Next 4h bar open after trigger, less exit slippage |

### 1.4 Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| ATR short period | 6 (24h) | Contraction window |
| ATR long period | 20 (80h) | Norm reference |
| ATR ratio threshold | 0.7 | Structural: ≤70% of norm |
| Re-expansion multiple | 1.2 | Structural: ≥120% of recent range |
| Stop lookback | 6 | Matches contraction window |
| Trend EMA | 60 | Direction A |
| Exit EMA | 60 | Direction A |
| Timeframe | 4h | Direction A |
| Symbol | ETH/USDT:USDT | Direction A |

### 1.5 Cost Model

Inherited verbatim from NSC-014 / CPM-1 OOS SSOT:

| Parameter | Value |
|-----------|-------|
| fee_rate | 0.0004 |
| entry_slippage_rate | 0.001 |
| exit_slippage_rate | 0.001 |
| funding_enabled | True |
| funding_rate_per_8h | 0.0001 |

### 1.6 Same-Bar / Next-Bar Policy

- Signal uses fully closed 4h candle only.
- Contraction and range calculations use only prior closed bars.
- Entry at next 4h bar open after signal candle close.
- Initial stop checked before same-bar EMA close-break (pessimistic).
- EMA60 exit requires fully closed 4h close below EMA60.
- EMA60 exit execution at next 4h bar open after trigger.
- No unclosed candle decisions.

### 1.7 Data Window

| Window | Period |
|--------|--------|
| Base | 2021-01-01 00:00:00 UTC — 2025-12-31 20:00:00 UTC |
| Year-by-year | 2021, 2022, 2023, 2024, 2025 individually |

### 1.8 Evidence Gaps

- **Funding exposure**: Computed using frozen 0.0001/8h model. No
  real historical funding rates used. Funding as % of gross PnL: 8.0%.
  Not flagged (> 15% threshold).
- **Supplemental pre-2021 data**: Available from 2020-01-01 but not
  used in base window. Can be used for appendices if Owner requests.

---

## 2. Aggregate Results

| Metric | Direction C | Direction A (NSC-014) | Delta |
|--------| ---: | ---: | ---: |
| Signal count | 63 | 173 | -110 |
| Closed positions | 63 | 173 | -110 |
| Gross PnL before costs | +3309.67 | +4102.71 | -793.04 |
| Net PnL after costs | +2039.29 | +3001.66 | -962.37 |
| PF | 1.405 | 1.517 | -0.112 |
| Win rate | 15.87% | 19.65% | -3.78 pp |
| Winners | 10 | 34 | -24 |
| Losers | 53 | 139 | -86 |
| Realized MaxDD | 11.78% | 6.08% | +5.70 pp (worse) |
| MTM MaxDD | 15.01% | 8.33% | +6.68 pp (worse) |
| MFE | +2326.26 | +1646.45 | +679.81 |
| MAE | -248.27 | -112.32 | -135.95 (worse) |
| Max giveback | 720.15 | 506.89 | +213.26 (worse) |
| Avg hold hours | 85.65 | 98.45 | -12.80 |
| Median hold hours | 20 | 48 | -28 |
| Max hold hours | 608 | 884 | -276 |
| Funding cost | 265.90 | 336.47 | -70.57 |
| Fee cost | 286.99 | 218.45 | +68.54 |
| Slippage cost | 717.49 | 546.13 | +171.36 |
| Funding % of gross | 8.0% | 8.2% | — |

### Hold Duration Distribution

| Bucket | Direction C | Direction A |
|--------| ---: | ---: |
| < 1 day | 33 (52.4%) | 59 (34.1%) |
| 1-3 days | 11 (17.5%) | 45 (26.0%) |
| 3-7 days | 9 (14.3%) | 33 (19.1%) |
| 7-14 days | 4 (6.3%) | 26 (15.0%) |
| > 14 days | 6 (9.5%) | 10 (5.8%) |

**Observation:** Direction C has a more polarized hold distribution — over
half the trades are < 1 day (quick stops or failed re-expansion), but the
winners hold longer (> 14 days: 6 vs 10, proportionally 9.5% vs 5.8%).
The median hold is much shorter (20h vs 48h), suggesting more trades fail
quickly.

---

## 3. Top-N Winner Concentration

| Metric | Direction C | Direction A (NSC-014) | Delta |
|--------| ---: | ---: | ---: |
| Top-1 PnL | +1677.25 | +1373.64 | +303.61 |
| Top-1 % of abs total net | 82.25% | 45.76% | +36.49 pp (worse) |
| Top-1 net excluding | +362.04 | +1628.03 | **Better** (positive vs positive) |
| Top-3 PnL | +4510.41 | +3445.57 | +1064.84 |
| Top-3 % of abs total net | 221.18% | 114.79% | +106.39 pp (worse) |
| Top-3 net excluding | **-2471.12** | **-443.91** | **Worse** |
| Top-5 PnL | +5900.33 | +4495.00 | +1405.33 |
| Top-5 net excluding | **-3861.04** | **-1493.33** | **Worse** |

### Interpretation

**Top-1:** Direction C's top-1 exclusion remains positive (+362.04). This
is an improvement over Direction A's top-1 exclusion (+1628.03 is also
positive, but Direction C's top-1 share is higher at 82.25%). Both pass
the top-1 gate.

**Top-3:** Direction C's top-3 exclusion is -2471.12, significantly worse
than Direction A's -443.91. Direction C fails the top-3 gate more
severely.

**Top-5:** Direction C's top-5 exclusion is -3861.04, worse than Direction
A's -1493.33.

**Conclusion:** Direction C is more concentrated than Direction A, not
less. The contraction filter reduced signal count (63 vs 173) but did not
widen the winner cluster. The winners are larger (top-1: 1677 vs 1374),
but fewer trades survive to become winners (10 vs 34), making the
concentration worse.

---

## 4. Year-by-Year Results

| Year | Trades | Net PnL | Gross PnL | PF | Win Rate | Realized DD | MTM DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 8 | +982.70 | +1064.60 | 3.528 | 37.50% | 2.16% | 4.82% |
| 2022 | 6 | -170.15 | -41.42 | 0.599 | 16.67% | 3.68% | 6.09% |
| 2023 | 18 | +695.02 | +1208.54 | 1.468 | 16.67% | 10.11% | 15.01% |
| 2024 | 12 | +539.27 | +788.09 | 1.514 | 16.67% | 8.01% | 12.69% |
| 2025 | 19 | -7.55 | +289.87 | 0.996 | 5.26% | 11.78% | 14.59% |

### Year-by-Year vs Direction A

| Year | Dir C Net | Dir A Net | Delta | Dir C Trades | Dir A Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | +982.70 | +722.57 | +260.13 | 8 | 33 |
| 2022 | -170.15 | -76.80 | -93.35 | 6 | 36 |
| 2023 | +695.02 | +918.93 | -223.91 | 18 | 29 |
| 2024 | +539.27 | +1465.75 | -926.48 | 12 | 34 |
| 2025 | -7.55 | -28.79 | +21.24 | 19 | 41 |

### Interpretation

- **2021:** Direction C outperforms Direction A (+260) with far fewer
  trades (8 vs 33). High win rate (37.5%) and strong PF (3.53). The
  contraction filter was selective and effective in this bull year.

- **2022:** Both negative. Direction C is worse (-170 vs -77). Bear year
  cost drag with few signals.

- **2023:** Both positive but Direction C captures less (+695 vs +919).
  Fewer trades (18 vs 29). The contraction filter missed some of
  Direction A's winners.

- **2024:** Both positive but Direction C significantly underperforms
  (+539 vs +1466). This is where Direction A's dominant winner cluster
  lives. Direction C captured only part of it.

- **2025:** Both near breakeven. Direction C is slightly better (-8 vs
  -29). Very low win rate (5.26%) but 19 trades — more signals than
  2021-2023 individually.

**Year concentration:** Direction C has 3 positive years (2021, 2023, 2024)
and 2 negative/near-zero years (2022, 2025). This passes MTC-001's
"≥ 2 years independently positive" gate. However, 2021 contributes 48.2%
of total net — approaching the 60% single-year concentration threshold.

---

## 5. Winner Attribution

### Top-5 Winners

| Rank | Timestamp | Year | Net PnL | Hold Hours | ATR Ratio | Re-expansion Ratio | Exit |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 2025-07-06 | 2025 | +1677.25 | 608 (25.3 days) | 0.607 | 3.103 | EMA60 break |
| 2 | 2023-01-08 | 2023 | +1547.95 | 392 (16.3 days) | 0.552 | 2.837 | EMA60 break |
| 3 | 2024-02-18 | 2024 | +1285.21 | 596 (24.8 days) | 0.677 | 1.687 | EMA60 break |
| 4 | 2021-04-25 | 2021 | +809.56 | 428 (17.8 days) | 0.650 | 1.884 | EMA60 break |
| 5 | 2023-10-29 | 2023 | +580.36 | 384 (16.0 days) | 0.582 | 1.574 | EMA60 break |

### Attribution Assessment

All top-5 winners:

- Are multi-day trend captures (16-25 days hold).
- Exited via EMA60 close-break (trend lifecycle exit).
- Occurred after clear ATR contraction (ratios 0.55-0.68, all below 0.7).
- Showed strong re-expansion (1.57-3.10x recent range).
- Are distributed across 4 different years (2021, 2023, 2024, 2025).

**Assessment:** Winner attribution is structurally explainable. The frozen
rule naturally identified these trades through its contraction + re-expansion
mechanism. These are not event spikes or data artifacts. The mechanism is
working as designed.

However, the concentration remains extreme: top-1 = 82.25% of net PnL.
This is a structural property of Direction C's low signal count and low
win rate, not a data quality issue.

---

## 6. MFE / MAE / Giveback

| Metric | Direction C | Direction A | Interpretation |
|--------| ---: | ---: | --- |
| MFE | +2326.26 | +1646.45 | Higher MFE — winners run further |
| MAE | -248.27 | -112.32 | Worse MAE — losers lose more before stop |
| Max giveback | 720.15 | 506.89 | Worse giveback — more profit surrendered |

**Interpretation:** Direction C's winners are larger (higher MFE) but its
losers are also worse (higher MAE). The wider stop (6-bar low vs 20-bar
low) allows more adverse movement before exit. The higher max giveback
suggests that even winning trades surrender significant open profit.

The MFE/MAE profile is consistent with a strategy that has fewer but larger
winners and worse-controlled losers — more fragile, not less.

---

## 7. MTC-001 Fragility Gate Assessment

| Gate | Threshold | Direction C Result | Pass? |
|------|-----------|-------------------|-------|
| Trade count: total | ≥ 55 | 63 | Yes |
| Trade count: 2023-2025 | ≥ 40 | 49 | Yes |
| Trade count: 2021+2022 | ≥ 15 | **14** | **No (by 1)** |
| Winner count | ≥ 15 | **10** | **No** |
| Top-1 net excluding | > 0 | +362.04 | Yes |
| Top-3 net excluding | > 0 | **-2471.12** | **No** |
| Top-5 net excluding | near 0 or > 0 | -3861.04 | No |
| Net PnL | > 0 | +2039.29 | Yes |
| PF | > 1.0 | 1.405 | Yes |
| Years positive | ≥ 2 | 3 (2021, 2023, 2024) | Yes |
| No year > 60% of net | < 60% | 48.2% (2021) | Yes |
| Funding % of gross | < 15% | 8.0% | Yes |

**Failed gates:** Trade count (2021+2022 by 1), winner count, top-3
exclusion, top-5 exclusion.

---

## 8. Direction A Signal Overlap

| Metric | Value |
|--------|-------|
| Direction C signals | 63 |
| Direction A signals | 173 |
| Overlapping signals | 9 |
| Overlap % of Direction C | 14.29% |
| Stop condition (> 80%) | **Not triggered** |

**Assessment:** Direction C is structurally different from Direction A.
Only 14.3% of Direction C's signals overlap with Direction A. The
contraction filter produces a genuinely different signal set — it is not
a Direction A subset or variant.

This confirms that Direction C is a distinct entry mechanism as defined in
MTC-003.

---

## 9. Classification

| Field | Value |
|-------|-------|
| Classification | **INSUFFICIENT_EVIDENCE** |
| Primary reason | Trade count floor not met (2021+2022: 14 vs 15 minimum) |
| Secondary reason | Winner count < 15 (10 vs 15 minimum) |
| Tertiary reason | Top-3 net excluding negative (-2471) |
| Stop conditions triggered | None (overlap 14.3% < 80%; no parameter search; no CPM drift) |
| Direction A variant? | No (14.3% overlap) |
| Runtime/profile/risk change? | No |
| Promotion conclusion | None |
| Small-live conclusion | None |

### What INSUFFICIENT_EVIDENCE Means Here

The classification is driven by two factors:

1. **Trade count (2021+2022):** 14 trades, 1 below the 15-trade floor.
   This is a marginal miss. The 2023-2025 window (49 trades) and total
   (63 trades) pass their floors.

2. **Winner count:** 10 winners out of 63 trades. Below the 15-winner
   minimum. With only 10 winners, the payoff ratio and winner distribution
   estimates are statistically unreliable.

The result is not REJECT because net PnL is positive (+2039), PF is above
1.0 (1.405), and the mechanism is structurally explainable. But the
evidence is too thin for meaningful fragility assessment.

---

## 10. Module Applicability / Dynamic Enablement Hypothesis

### 10.1 Is Direction C Better As A Start/Stop Module Than A Year-Round Strategy?

**Hypothesis: Possibly yes.**

Direction C's year-by-year pattern is uneven:

| Year | Net PnL | Trades | PF | Market Phase (approximate) |
| --- | ---: | ---: | ---: | --- |
| 2021 | +983 | 8 | 3.53 | Bull / trending |
| 2022 | -170 | 6 | 0.60 | Bear / choppy |
| 2023 | +695 | 18 | 1.47 | Recovery / trending |
| 2024 | +539 | 12 | 1.51 | Bull / trending |
| 2025 | -8 | 19 | 1.00 | Choppy / mixed |

The profitable years (2021, 2023, 2024) coincide with directional trend
phases. The unprofitable years (2022, 2025) coincide with bear or choppy
conditions. This is consistent with the Main Trend Capture thesis: trend
strategies earn during trends and lose or break even during non-trending
periods.

**However**, this observation is made after seeing the results. It is a
research hypothesis, not a pre-registered no-trade condition.

### 10.2 Can Profitable Market Phases Be Explained By Pre-Observables?

**Hypothesis: Potentially, but not yet validated.**

Possible pre-observable conditions:

- ETH in a sustained trend (price above 200-bar MA for extended period).
- Directional breakout frequency above a threshold (market is "trending").
- Average true range expanding (volatility regime supports trend capture).

None of these are validated. They are research hypotheses only. Using them
as no-trade conditions without out-of-sample validation would be parameter
fitting.

### 10.3 Can Losing Market Phases Be Explained By Pre-Observables?

**Hypothesis: Yes, directionally.**

2022 was a sustained bear market with frequent whipsaws — trend-following
strategies generally struggled. 2025 showed mixed conditions with very low
win rates across both Direction A and Direction C.

A "bear market" or "choppy market" filter could theoretically avoid these
periods, but:

- Defining "bear market" or "choppy market" objectively is a regime
  classification problem.
- Any such filter would need out-of-sample validation.
- Using 2022/2025 losses to backfit a filter is explicitly prohibited.

### 10.4 Would No-Trade Conditions Become Parameter Fitting?

**Risk: High.**

If we add no-trade conditions based on this result (e.g., "skip signals
when ATR is below X" or "skip signals when price below 200 MA"), we are
fitting parameters to the observed loss periods. This violates the sparse
trend profit principles.

The only safe approach: define no-trade conditions before seeing results,
then validate on unseen data. This requires a separate docs-only plan
with pre-registered conditions.

### 10.5 Module Validity Gate vs Strategy Router?

**Current assessment: Module validity gate is sufficient.**

Direction C does not need a strategy router at this stage. A strategy
router would imply:

- Multiple active modules.
- Dynamic switching between modules.
- Regime classification driving module selection.

None of these are justified by the current evidence. Direction C has 63
trades and INSUFFICIENT_EVIDENCE classification. Building a router around
an unvalidated module would be premature infrastructure.

A module validity gate is the right framing: "Is Direction C's edge real
enough to justify further research?" The answer from this report is:
promising but insufficient evidence.

### 10.6 Future Complementarity With Direction D / Other Modules?

**Hypothesis: Possible but unvalidated.**

Direction C (contraction + re-expansion) and Direction D (value-zone
pullback entry) target different market microstructures:

- Direction C enters on volatility expansion after compression.
- Direction D enters on price retracement to a value zone.

If both modules have edge in different sub-conditions, they could
complement each other. But this requires:

1. Both modules to have independent RESEARCH_PASS evidence.
2. A docs-only plan for how they would interact (not portfolio, not
   regime router — just a complementarity hypothesis).
3. Owner approval to explore the combination.

Current status: Direction C has INSUFFICIENT_EVIDENCE. Direction D has
not been inspected. Complementarity is a future research question, not
a current action item.

---

## 11. What Direction C Results Mean

### 11.1 The Contraction Filter Works — But Too Well

The contraction filter successfully identifies a different signal set from
Direction A (only 14.3% overlap). The signals it produces are genuine
contraction-then-expansion events, not Donchian breakouts.

But the filter is too selective. With only 63 signals over 5 years and
10 winners, the evidence is statistically thin. The 2021+2022 floor
misses by 1 trade. The winner count misses by 5.

### 11.2 More Concentrated, Not Less

Direction C was hypothesized to reduce top-winner fragility. It did not.
The top-1 winner is 82.25% of net PnL (vs Direction A's 45.76%). The
top-3 exclusion is -2471 (vs Direction A's -444).

The contraction filter reduced signal count more than it reduced the
concentration of the remaining signals. Fewer trades + same concentration
= worse fragility.

### 11.3 Higher Drawdown

MTM MaxDD is 15.01% vs Direction A's 8.33%. This is driven by:

- Wider initial stop (6-bar low vs 20-bar low) allowing more adverse
  movement.
- Fewer diversification signals (63 vs 173 trades).
- Larger individual trade risk from wider stop distance.

### 11.4 Not A Direction A Variant

The 14.3% signal overlap confirms Direction C is a genuinely different
entry mechanism. This validates MTC-003's hypothesis that contraction +
re-expansion is structurally distinct from Donchian breakout.

### 11.5 Positive Net, But Evidence Too Thin

Net +2039 after costs is positive. PF 1.405 is above 1.0. The mechanism
is structurally explainable. But with only 10 winners and a missed trade
floor, the evidence cannot support any classification beyond
INSUFFICIENT_EVIDENCE.

---

## 12. Stop Condition Assessment

| Stop Condition | Status | Detail |
|---------------|--------|--------|
| Direction A variant (> 80% overlap) | **Not triggered** | 14.3% overlap |
| Parameter search required | **Not triggered** | Frozen threshold with structural rationale |
| Trade count below floor | **Triggered** | 2021+2022: 14 vs 15 minimum |
| New data required | **Not triggered** | OHLCV only |
| Winner attribution failure | **Not triggered** | All top-5 winners structurally explainable |
| CPM / pullback drift | **Not triggered** | No pullback / value-zone / Pinbar elements |

---

## 13. Classification And Recommendation

### Classification

**INSUFFICIENT_EVIDENCE**

Primary: Trade count floor not met (2021+2022 = 14, minimum 15).
Secondary: Winner count < 15 (10 winners).
Tertiary: Top-3 exclusion negative (-2471).

### Recommendation

**Do not upgrade. Do not reject. Pause as insufficient evidence.**

Reasoning:

1. Direction C is a structurally different mechanism from Direction A.
   The 14.3% signal overlap validates this.

2. The mechanism is working as designed: winners are genuine trend
   captures, not artifacts.

3. But the evidence is too thin for meaningful fragility assessment:
   10 winners and 63 trades over 5 years.

4. The top-3 fragility is worse than Direction A, not better. The
   contraction filter did not achieve its primary goal (reducing
   fragility).

5. The 2021+2022 floor miss is marginal (14 vs 15). A slightly
   looser contraction threshold could produce 1-2 more signals in
   that window. But adjusting the threshold after seeing results
   would be parameter fitting.

### Possible Next Steps (Owner Decision)

| Option | Action | Risk |
|--------|--------|------|
| A | Pause Direction C as INSUFFICIENT_EVIDENCE. Move to Direction D inspect. | May miss a viable direction. |
| B | Re-run with a slightly looser ATR ratio threshold (e.g., 0.75). | Parameter fitting after seeing results. Prohibited unless Owner explicitly approves as a sensitivity check. |
| C | Expand data window to include 2019-2020 supplemental. | May add noise; 2019-Q4 data has known coverage gaps. |
| D | Accept INSUFFICIENT_EVIDENCE and treat Direction C as a data point for the module applicability hypothesis. | No immediate action; informs future direction design. |

**Recommendation:** Option A or D. Direction C's fragility profile is
worse than Direction A's, and the mechanism is too selective. The primary
lesson is that the contraction filter, as frozen, produces too few signals
for sparse-trend evaluation at 4h timeframe.

---

## 14. Explicit Non-Goals

- This report does not authorize runtime, profile, or risk changes.
- This report does not authorize promotion or small-live conclusions.
- This report does not authorize parameter sweeps or threshold adjustments.
- This report does not authorize Direction D parallel execution.
- This report does not establish Direction C as a runtime candidate.
- This report does not design a regime router or strategy switch.
- This report does not implement dynamic enablement.
- This report does not reopen Direction A.

---

## 15. Evidence Gaps

| Gap | Impact | Action |
|-----|--------|--------|
| Real historical funding rates not used | Funding cost may be understated or overstated | Accept frozen model for now; flag if funding > 15% of gross |
| 2019-Q4 data coverage gaps | Not used in base window | Not relevant for this report |
| No OOS validation | Result is in-sample only | Would require separate Owner-approved plan |

---

## 16. Files Changed

| File | Change |
|------|--------|
| `reports/mtc-004-direction-c-frozen-baseline/mtc_004_direction_c_research_adapter.py` | New: Direction C research adapter |
| `reports/mtc-004-direction-c-frozen-baseline/summary.json` | Generated: full metrics and classification |
| `reports/mtc-004-direction-c-frozen-baseline/signals.jsonl` | Generated: 63 signal records |
| `reports/mtc-004-direction-c-frozen-baseline/trades.jsonl` | Generated: 63 trade records |
| `reports/mtc-004-direction-c-frozen-baseline/equity_curve.jsonl` | Generated: equity curve |
| `docs/ops/mtc-004-direction-c-frozen-baseline-research-report.md` | This report |

No `src/`, `configs/`, `tests/`, `migrations/`, runtime, profile, risk,
or backtester-core files were modified.

---

## 17. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Initial Direction C frozen baseline research report | Claude |
