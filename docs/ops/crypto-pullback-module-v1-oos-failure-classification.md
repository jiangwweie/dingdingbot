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

# Crypto Pullback Module v1 — OOS Failure Classification / RCA

**Task ID:** CPM-OOS-FAILURE-CLASSIFY-001
**Date:** 2026-05-06
**Status:** Active — Failure classification complete
**Scope:** Diagnostic / classification only. No strategy, parameter, runtime, risk, or live changes.
**Affects Runtime Automatically**: No

---

## 0. Version / Audit Caveat

- bc64238 = actual 2021 OOS run artifact commit.
- Current local HEAD = a8b47b4.
- A commit f7d9f90 was previously referenced but is not present in the current local history.
- All analysis in this document uses the current working tree and `reports/oos_runs/cpm1_2021_oos/result.json` as ground truth, unless explicitly noted otherwise.
- If f7d9f90 is recovered in the future, its relationship to this analysis should be re-examined.

---

## 1. Evidence Summary

### 1.1 2021 OOS (Bull Year)

| Metric | Value |
|--------|-------|
| Total PnL | -2,153.76 USDT |
| Total return | -21.54% |
| Max drawdown | 22.18% |
| Win rate | 29.5% |
| Profit factor | 0.466 |
| Sharpe | -2.466 |
| Positions | 74 |
| Winning months | 3/12 (Jan, Apr, Jul) |
| Gross PnL (before costs) | -573.84 USDT |
| Total cost drag | 1,579.93 USDT (fees 519.97 + slippage 1,040.85 + funding 19.10) |
| Largest loss cluster | 16 consecutive losses, -1,079.84 USDT (Aug–Oct) |
| May 2021 PnL | -147.68 USDT (7.6% of position-level loss) |

### 1.2 2022 OOS (Bear Year)

| Metric | Value |
|--------|-------|
| Total PnL | -971.71 USDT |
| Total return | -9.72% |
| Max drawdown | 10.48% |
| Win rate | 31.1% |
| Profit factor | 0.624 |
| Sharpe | -1.399 |
| Positions | 51 |
| Winning months | 0/12 |
| Gross PnL (before costs, estimated) | +80.51 USDT |
| Total cost drag (estimated) | 1,052.22 USDT (fees 387.04 + slippage ~644.33 + funding 20.85) |
| Largest loss cluster | 7 consecutive losses, -437.95 USDT (Jul) |

### 1.3 In-Sample Reference (from Scope Note)

| Year | PnL | WR | Sharpe | MaxDD |
|------|-----|----|--------|-------|
| 2023 | -3,924 USDT | 16.1% | -2.63 | 49.19% |
| 2024 | +8,501 USDT | 32.3% | 1.91 | 17.39% |
| 2025 | +4,490 USDT | 31.7% | 2.01 | 11.56% |

---

## 2. Mandatory Questions

### Q1: Does 2021 failure directly challenge CPM-1 profit hypothesis?

**Yes.** The profit hypothesis states:

> Pinbar reversal signals in an EMA50 uptrend, confirmed by 4h EMA60, produce positive expectancy over a full market cycle.

2021 is the most favorable year in the available data window for this hypothesis:
- ETH rose from ~$730 to ~$4,878 (strong bull).
- LONG-only is structurally aligned with market direction.
- EMA50 uptrend filter should be frequently active.
- 4h EMA60 should be rising for most of the year.

Yet CPM-1 produced -21.54% return, worse than the 2022 bear year (-9.72%). This is a direct challenge — the mechanism fails in the environment where it is most expected to work.

### Q2: Is 2021 loss concentrated in few months / loss clusters?

**Yes, significantly concentrated.**

Loss concentration analysis (position-level):

| Period | Positions | PnL | % of Total Position-Level Loss |
|--------|-----------|-----|-------------------------------|
| Aug–Oct 2021 | 23 | -1,059.91 | 54.7% |
| Feb–Mar 2021 | 19 | -550.20 | 28.4% |
| **Combined** | **42** | **-1,610.11** | **83.1%** |

Only 3 of 12 months are profitable (Jan, Apr, Jul), and they contribute only +292.77 USDT combined.

The four largest consecutive loss clusters account for -2,875.21 USDT (148% of position-level loss, overlapping with profitable months):

| Cluster | Size | Loss | Period |
|---------|------|------|--------|
| 1 | 16 consecutive | -1,079.84 | Aug 2 – Oct 15 |
| 2 | 11 consecutive | -717.67 | Apr 15 – Jul 6 |
| 3 | 9 consecutive | -536.81 | Feb 20 – Mar 28 |
| 4 | 9 consecutive | -540.90 | Oct 21 – Dec 25 |

**Interpretation**: Losses are not uniformly distributed. They cluster in two distinct sub-regimes within the bull year:
1. **Mid-year correction** (Feb–Mar, Apr–Jul): Pullbacks that turned into deeper corrections. Pinbar entries caught falling knives within corrections.
2. **Post-ATH decline** (Aug–Dec): The strategy continued entering during the late-stage bull and post-ATH decline, when the EMA50 was still rising but price was entering distribution/reversal.

### Q3: May 2021 crash impact?

**Small.** May 2021 accounts for only -147.68 USDT (7.6% of position-level loss, 6.9% of total PnL loss). Only 2 positions were taken in May, both stopped out. The May crash is not the driver of the 2021 failure.

The dominant losses come from Aug–Oct (-1,059.91 USDT, 54.7%) and Feb–Mar (-550.20 USDT, 28.4%). These are not crash-related — they are sustained whipsaw periods within what was overall a bull year.

### Q4: Is trade count sufficient?

**Yes.** 74 positions (88 trade legs) is well above the 40-position threshold defined in CPM-OOS-2021-PLAN-001 Section 6.1. It is also above the 60-position threshold for direct regime comparison with 2022 (51 positions).

The trade count is sufficient for statistical interpretation. The negative result cannot be dismissed as thin-sample noise.

### Q5: Is slippage 1,040.85 USDT the primary failure source, or just an amplifier?

**Amplifier, not primary cause.** This is a critical finding:

- Gross PnL (before all costs): **-573.84 USDT** — already negative.
- Cost drag: 1,579.93 USDT — amplifies the loss by 2.75x.
- Without costs, the strategy would still have lost money in 2021.

Compare with 2022:
- Gross PnL (before costs, estimated): **+80.51 USDT** — marginally positive.
- Cost drag (estimated): 1,052.22 USDT — turns a small gross profit into a net loss.

**Key asymmetry**: In 2022, cost drag is the difference between gross profit and net loss. In 2021, the gross edge is already negative — cost drag makes it worse but is not the root cause.

### Q6: Fee / funding / slippage as proportion of gross loss?

| Component | 2021 Amount | 2021 % of Gross Loss (position-level) | 2022 Amount (est.) | 2022 % of Gross Loss (position-level) |
|-----------|-------------|---------------------------------------|---------------------|---------------------------------------|
| Fees | 519.97 | 14.3% | 387.04 | 18.0% |
| Slippage | 1,040.85 | 28.6% | ~644.33 | 30.0% |
| Funding | 19.10 | 0.5% | 20.85 | 1.0% |
| **Total cost** | **1,579.93** | **43.4%** | **~1,052.22** | **48.9%** |

Costs represent 43–49% of gross loss in both years. Slippage is the dominant cost component in both years (~65–66% of total cost drag).

### Q7: Is gross edge still negative without costs?

**Yes for 2021, no for 2022.**

- 2021 gross PnL: -573.84 USDT (negative even before costs).
- 2022 gross PnL: +80.51 USDT (marginally positive before costs).

This is a structural difference. In 2022, the strategy has a small positive gross edge that is consumed by costs. In 2021, the strategy has a negative gross edge — the signal itself is unprofitable, not just cost-eroded.

### Q8: Are 2021 and 2022 failures isomorphic?

**No. They are structurally different failures.**

| Dimension | 2021 Failure | 2022 Failure |
|-----------|-------------|-------------|
| Gross edge | Negative (-573.84) | Marginally positive (+80.51) |
| Failure mechanism | Signal is unprofitable; cost amplifies | Signal is marginally profitable; cost dominates |
| Market regime | Bull year (favorable) | Bear year (unfavorable) |
| Consistent with failure hypothesis? | No — failure hypothesis predicts bear-market failure only | Yes — failure hypothesis predicts bear-market failure |
| Consistent with profit hypothesis? | No — profit hypothesis predicts bull-market profit | N/A — bear market is outside profit hypothesis scope |
| Loss concentration | Extreme (83.1% in 2 sub-periods) | Moderate (48% in Nov–Dec FTX) |
| Largest cluster | 16 consecutive losses | 7 consecutive losses |
| Win rate | 29.5% | 31.1% |

2022 failure is **cost-dominated in an unfavorable regime** — consistent with the documented failure hypothesis. 2021 failure is **signal-level in a favorable regime** — inconsistent with both the profit hypothesis and the failure hypothesis.

### Q9: Is 2021 similar to 2023-style boundary cost, or more serious?

**More serious. 2021 represents a module-level problem, not a boundary cost.**

2023 was classified as boundary cost because:
- 2023 is a high-volatility, choppy recovery year — outside CPM-1's applicable market.
- The failure hypothesis predicts loss in such regimes.
- Five rescue experiments (H0–H3a) confirmed no parameter adjustment could fix 2023 without destroying good-year behavior.
- 2023 failure is **consistent with the documented module boundaries**.

2021 cannot be classified as boundary cost because:
- 2021 is a bull year with established uptrends — **inside CPM-1's applicable market**.
- The profit hypothesis explicitly predicts positive expectancy in this environment.
- The result is worse than the bear year, which is the opposite of what the hypothesis predicts.
- The gross edge is negative, meaning the signal mechanism itself fails — not just the cost model or market boundary.

**2021 is not a 2023-style boundary cost. It is evidence that the profit hypothesis does not hold even in the module's stated applicable market.**

### Q10: What explains the difference between 2021 OOS and 2024/2025 in-sample?

This is the central puzzle. Several hypotheses:

1. **Sub-regime sensitivity within bull years**: 2021 had two major corrections (May crash, post-ATH decline) that created extended whipsaw periods. 2024/2025 may have had gentler pullbacks that the Pinbar entry captured more effectively. The strategy may require not just "an uptrend" but a **specific type of uptrend** — one with moderate slope, shallow pullbacks, and low volatility. 2021's bull had aggressive legs and sharp corrections that violated this unstated requirement.

2. **M0 ecology finding — counter-trend structure**: The M0 Strategy Ecology Map found that CPM-1 is structurally counter-trend: it earns in low-slope, low-volatility environments and loses in high-slope, high-volatility environments. 2021 had periods of very high slope (parabolic moves to ATH) and high volatility (May crash, post-ATH decline). Even though the year was net bullish, the sub-regimes where CPM-1 entered may have been high-slope/high-volatility moments within the uptrend.

3. **Cost scaling with price level**: 2021 ETH ranged from $730 to $4,878. At higher price levels, the same percentage slippage produces larger absolute costs. The 1,040.85 USDT slippage in 2021 vs ~644 USDT in 2022 reflects this. However, this does not explain the negative gross edge.

4. **In-sample overfitting**: 2024/2025 are in-sample. The positive results may reflect some degree of overfitting to the specific sub-regime structure of those years. The 2021 OOS result would then be a more honest assessment of the strategy's true edge.

5. **EMA50 whipsaw during corrections**: In 2021, the EMA50 uptrend filter may have remained active during corrections (EMA50 lags price), causing entries during pullbacks that were actually trend reversals within the broader uptrend. The 16-consecutive-loss cluster from Aug–Oct aligns with this — EMA50 was likely still rising while price was entering distribution.

**Most likely explanation**: A combination of (1), (2), and (5). CPM-1's applicable market is narrower than documented — it requires not just "an uptrend" but a **low-slope, low-volatility uptrend with shallow pullbacks**. 2021 had uptrends, but they were aggressive and volatile. The EMA50 filter does not distinguish between gentle and aggressive uptrends, leading to entries in hostile sub-regimes within a nominally favorable year.

### Q11: Should CPM-1 remain frozen, or enter Pause / Reopen Research / Reject?

**Pause CPM-1 for classification.** The evidence supports Pause, not Continue Observation, because:

1. The 2021 OOS result directly undermines the core profit hypothesis (Pause Criterion 1 from CPM-CRITERIA-001 Section 5).
2. The result is inconsistent with the documented failure hypothesis (Pause Criterion 2).
3. No data quality, cost, or assumption caveat explains the result.
4. The gross edge is negative in a favorable year — this is not a boundary cost issue.

Pause does not mean rejection. It means promotion movement stops until the failure is classified and Owner decides the next state.

### Q12: Is a comparable rerun needed, rather than new OOS?

**A comparable rerun is not the priority. The priority is understanding why the gross edge is negative in a favorable year.**

Additional OOS years (2020, 2023) would add evidence breadth but would not resolve the core question: why does CPM-1's signal mechanism fail in a bull year? This is a diagnostic question, not an evidence-quantity question.

A 2023 OOS run would be informative because:
- 2023 is already classified as boundary cost (in-sample).
- Running it OOS would test whether the in-sample classification holds out-of-sample.
- But 2023 is expected to be negative (high-volatility regime), so it would not resolve the 2021 puzzle.

A multi-year OOS (2021–2022 or 2020–2022) would show aggregate behavior but would be dominated by the 2021 loss and would not provide sub-regime insight.

**Recommendation**: Before additional OOS runs, conduct position-level sub-regime analysis on the existing 2021 data to understand which sub-regimes within the bull year produced losses vs. profits. This is a diagnostic task, not a new OOS run.

### Q13: Is Small-live Candidate review allowed?

**No.** A negative result in a favorable year is a stronger blocker than a negative result in a bear year. CPM-1 cannot enter Small-live Candidate review while the profit hypothesis is directly challenged by OOS evidence.

Per CPM-CRITERIA-001 Section 4, Promotion Criterion 6 requires: "Evidence supports a coherent profit/failure hypothesis." With 2021 OOS contradicting the profit hypothesis and 2022 OOS supporting the failure hypothesis but not the profit hypothesis, the evidence does not support a coherent story. Promotion Criterion 3 requires Owner decision on OOS gates — both 2021 and 2022 are now negative, which closes the gate rather than opening it.

---

## 3. Failure Classification

### 3.1 Primary Classification

**Favorable-regime profit hypothesis failure** (Category 2) combined with **Loss-concentration issue** (Category 7).

The 2021 failure is primarily a profit hypothesis failure: CPM-1 does not produce positive expectancy in the market conditions where its hypothesis predicts it should. This is not a boundary cost (the market is inside the applicable range), not a cost-dominated failure (gross edge is negative), and not a data/caveat issue (data is clean, assumptions are consistent).

The loss-concentration aspect is secondary but important: losses are not uniformly distributed but cluster in specific sub-regimes within the bull year (mid-year correction and post-ATH decline), suggesting the applicable market definition is too broad.

### 3.2 Secondary Classifications

| Category | Present? | Evidence |
|----------|----------|----------|
| 1. Module hypothesis failure | Partial | The pullback-continuation mechanism fails in 2021, but 2024/2025 in-sample shows it can work. The hypothesis may be conditionally valid (narrow applicable market) rather than universally invalid. |
| 2. Favorable-regime profit hypothesis failure | **Yes (primary)** | 2021 is a favorable regime; result is negative and worse than bear year. |
| 3. Market-boundary cost | No | 2021 is inside the documented applicable market. |
| 4. Cost / slippage dominated failure | No | Gross edge is negative; cost amplifies but does not cause. |
| 5. Data / funding / same-bar / engine caveat | No | Data complete, assumptions consistent, engine verified. |
| 6. Trade-count insufficiency | No | 74 positions is sufficient. |
| 7. Loss-concentration issue | **Yes (secondary)** | 83.1% of loss in 2 sub-periods; 4 clusters of 9–16 consecutive losses. |
| 8. Methodology inconsistency | Partial | 2022 slippage tracking was legacy (total_slippage_cost=0), but this is reconciled via CPM-OOS-RECON-001 and does not affect PnL comparability. |
| 9. Inconclusive / require additional evidence | No | The evidence is sufficient to classify. |

### 3.3 Why Not Module Hypothesis Failure (Category 1) Outright?

Module hypothesis failure would mean the pullback-continuation concept is fundamentally invalid. But 2024/2025 in-sample shows positive results (+8,501 / +4,490 USDT) with the same frozen baseline. The mechanism can work — but apparently only in a narrower set of conditions than the profit hypothesis claims.

This is more precisely a **profit hypothesis scope failure**: the hypothesis claims positive expectancy "over a full market cycle" and in "established uptrends," but the 2021 evidence shows the applicable conditions are narrower than stated. The mechanism works in low-slope, low-volatility uptrends (2024/2025) but fails in high-slope, high-volatility uptrends (2021) and in bear markets (2022).

---

## 4. Root Cause Analysis

### 4.1 Why Does CPM-1 Lose More in a Bull Year Than a Bear Year?

This paradox is explained by the interaction of three factors:

**Factor 1: EMA50 lag creates hostile entries during corrections within uptrends.**

In a bull year, the EMA50 uptrend filter remains active even during corrections (because EMA50 lags price). This causes CPM-1 to enter during pullbacks that are actually deeper corrections or the start of reversals within the broader uptrend. In a bear year, the EMA50 filter is rarely active, so fewer entries occur — and while those entries also lose, there are fewer of them.

2021 had 74 positions vs 2022's 51 — more entries in a bull year, but with a 29.5% win rate vs 31.1%. More entries × lower win rate = larger absolute loss.

**Factor 2: M0 ecology finding — CPM-1 is structurally counter-trend.**

The M0 Strategy Ecology Map found that CPM-1 earns in low-slope, low-volatility environments and loses in high-slope, high-volatility environments. A bull year with aggressive moves (2021) creates more high-slope entries than a gentle uptrend (2024). The Pinbar trigger fires during pullbacks in aggressive uptrends, but these pullbacks are more likely to be trend interruptions than resumptions.

**Factor 3: Cost scaling amplifies the signal-level failure.**

2021 had higher price levels ($730–$4,878 vs $1,200–$3,700 in 2022), producing larger absolute slippage per trade (1,040.85 vs ~644 USDT). This amplifies the negative gross edge into a larger net loss.

### 4.2 Sub-Regime Analysis

The 2021 losses cluster in two distinct sub-regimes:

**Sub-regime A: Mid-year correction (Feb–Jul)**
- 11-consecutive-loss cluster (Apr–Jul): -717.67 USDT
- 9-consecutive-loss cluster (Feb–Mar): -536.81 USDT
- Characterized by: EMA50 still rising, but price undergoing 20–40% corrections. Pinbar entries catch falling knives within corrections that exceed the 1R stop-loss before resuming.

**Sub-regime B: Post-ATH decline (Aug–Dec)**
- 16-consecutive-loss cluster (Aug–Oct): -1,079.84 USDT
- 9-consecutive-loss cluster (Oct–Dec): -540.90 USDT
- Characterized by: Price at or near all-time highs, EMA50 still rising from lag, but price entering distribution and then decline. Pinbar entries in this zone are near-Donchian-top entries — identified by M0 as a systematic loss factor.

The 3 profitable months (Jan, Apr, Jul) correspond to periods of gentle, low-volatility uptrend — consistent with M0's finding that CPM-1 earns in low-slope, low-volatility environments.

### 4.3 The Applicable Market Is Narrower Than Documented

The CPM-1 scope note defines the applicable market as "established uptrend with moderate slope, moderate volatility, price below recent highs." The 2021 evidence shows this definition is too broad:

- "Moderate slope" is not enforced by any filter. The EMA50 uptrend filter admits any slope above the min_distance_pct threshold.
- "Moderate volatility" is not enforced (ATR filter is disabled).
- "Price below recent highs" is not enforced (E4/Donchian-distance is not a hard filter).

In practice, CPM-1's applicable market appears to be **low-slope, low-volatility uptrends with price below recent highs** — a narrower set than "established uptrend." The 2021 bull year had uptrends, but they were frequently high-slope and high-volatility, placing them outside CPM-1's true (but undocumented) applicable market.

---

## 5. Cross-Year Evidence Synthesis

| Year | Regime | Result | Gross Edge | Consistent With | Challenge To |
|------|--------|--------|------------|-----------------|-------------|
| 2021 | Bull (favorable) | -21.54% | Negative | Neither hypothesis | Profit hypothesis (direct) |
| 2022 | Bear (unfavorable) | -9.72% | Marginally positive | Failure hypothesis | — |
| 2023 | Choppy recovery | -39.24% | Unknown | Failure hypothesis / boundary cost | — |
| 2024 | Gentle bull (in-sample) | +85.01% | Positive | Profit hypothesis (narrow) | — |
| 2025 | Gentle bull (in-sample) | +44.90% | Positive | Profit hypothesis (narrow) | — |

**Synthesis**: CPM-1's profit hypothesis holds only in a narrow sub-regime (low-slope, low-volatility uptrends). It fails in:
- Aggressive/volatile uptrends (2021) — profit hypothesis failure
- Bear markets (2022) — failure hypothesis confirmation
- High-volatility choppy markets (2023) — boundary cost

The strategy does not have positive expectancy "over a full market cycle" as the profit hypothesis claims. It has positive expectancy only in a specific sub-regime that constitutes a minority of market conditions.

---

## 6. Output Conclusions

### 6.1 Final Classification

**Pause CPM-1**

Not Reopen Research (yet), because the failure is classified — we understand why it fails. Not Reject current baseline, because the mechanism works in a narrow sub-regime (2024/2025) and rejection would require Owner decision on whether that narrow applicability is worth preserving.

### 6.2 Failure Primary Cause

**Favorable-regime profit hypothesis failure**: CPM-1 does not produce positive expectancy in the market conditions where its hypothesis predicts it should. The applicable market is narrower than documented — the mechanism requires low-slope, low-volatility uptrends, not merely "established uptrends."

### 6.3 Evidence Confidence

**High.** The evidence is clean:
- Data complete (0 gaps, 0 duplicates).
- Cost model consistent across 2021/2022.
- Slippage tracking corrected (CPM-BT-METRIC-001 fix active in 2021; 2022 reconciled).
- Trade count sufficient (74 positions).
- No same-bar conflicts.
- Funding is a minor component (1.2% of cost).
- May 2021 crash is not the driver (7.6% of loss).
- Gross edge is independently negative (not a cost artifact).

### 6.4 Additional OOS Needed?

**Not as the immediate priority.** The core question is diagnostic (why does the signal fail in favorable conditions?), not evidential (do more years also fail?). A 2023 OOS would be informative but expected-negative. A 2020 OOS would add another bull-year data point.

The more valuable next step is **position-level sub-regime analysis** on existing 2021 data: classify each position by slope, volatility, and Donchian-distance at entry time to confirm the M0 ecology finding that losses concentrate in high-slope/high-volatility/near-Donchian-top entries.

### 6.5 Small-live Candidate Review Allowed?

**No.** Per CPM-CRITERIA-001 Section 4, Promotion Criterion 6 requires coherent profit/failure hypothesis support. With 2021 contradicting the profit hypothesis, the evidence does not support candidate status. Per the 2021 OOS report Section 13: "a negative result in a favorable year is a stronger blocker than a negative result in a bear year."

### 6.6 Should CPM-1 Remain Frozen?

**Yes, during Pause.** The baseline should remain frozen. Unfreezing parameters to address the 2021 failure would be parameter rescue, which is explicitly prohibited by the task boundaries and by CPM-CRITERIA-001 Section 9 (Not-Now List).

If Owner decides to Reopen Research after reviewing this classification, any research would need a separate bounded task card with explicit scope — it would not be parameter tuning under the current frozen baseline.

### 6.7 Should the Current Baseline's Promotion Path Be Stopped?

**Yes.** The promotion path from frozen observation → Small-live Candidate is blocked by:
1. 2021 OOS negative in favorable conditions (profit hypothesis failure).
2. 2022 OOS negative (failure hypothesis confirmation, but no profit hypothesis support).
3. No OOS year supports the profit hypothesis.

The promotion path can only resume if:
- A future OOS year (e.g., 2020) produces a positive result in favorable conditions, OR
- Owner accepts that CPM-1's applicable market is narrower than documented and the narrow positive sub-regime (2024/2025-style) is sufficient for Small-live consideration, OR
- A bounded research task identifies a non-parameter modification (e.g., E4 as risk-state label, or a new applicable market definition) that separates the hostile sub-regimes from the favorable ones.

### 6.8 Runtime Auto-Change

**runtime_auto_change: No.** No automatic changes to runtime profile, strategy parameters, risk rules, or live enablement. This classification is diagnostic only.

---

## 7. Relationship to Existing Governance

| Document | Relationship |
|----------|-------------|
| CPM-CRITERIA-001 (promotion/rejection criteria) | This classification triggers Pause Criterion 1 (new evidence directly undermines profit hypothesis) and Pause Criterion 2 (OOS exposes loss behavior inconsistent with failure hypothesis). |
| CPM-OOS-2021-PLAN-001 (2021 gate inspect plan) | This classification follows Decision Matrix row 4 (severe negative with clean assumptions and enough trades → Pause) and row 7 (conflicts with profit hypothesis → Pause or Reopen Research). |
| CPM-OOS-PLAN-001 (2022 gate inspect plan) | 2022 result is recontextualized: it is no longer "require additional evidence" in isolation but part of a joint 2021+2022 negative evidence set. |
| CPM-1 Scope Note | The applicable market definition (Section 5) is challenged by this finding. The documented applicable market is too broad. |
| M0 Strategy Ecology Map | This classification is consistent with M0's finding that CPM-1 is structurally counter-trend and earns only in low-slope, low-volatility environments. |
| Live-safe v1 | No impact. CPM-1 Pause does not change live-safe guardrails. |

---

## 8. Not-Now List (Reaffirmed)

The following remain explicitly not authorized:

- No parameter change.
- No E4 hard filter.
- No SHORT runtime.
- No BTC/SOL expansion.
- No ETH 15m or 4h primary-timeframe expansion.
- No cross-asset or cross-timeframe expansion.
- No regime system.
- No portfolio engine.
- No multi-strategy routing.
- No runtime profile change.
- No research-to-runtime promotion.
- No live-safe change.
- No backtester or research engine change.
- No live enablement or small-live approval.
- No parameter rescue based on 2021 failure.
- No strategy rewrite.

---

## 9. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-06 | Initial OOS failure classification / RCA | Claude Code (CPM-OOS-FAILURE-CLASSIFY-001) |
