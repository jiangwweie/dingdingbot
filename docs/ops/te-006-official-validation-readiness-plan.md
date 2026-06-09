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

# TE-006 - Official Validation Readiness Plan for Direction A / B-D1 Longer-window Evidence

**Task ID:** TE-006
**Date:** 2026-05-07
**Status:** Accepted / Validation Readiness Plan
**Authorization Level:** Level 2 — docs-only validation readiness plan

---

## 0. Boundary Statements

This document is a validation readiness plan only. It does not authorize
Direction A execution. It does not authorize Direction B-D1 execution. It does
not authorize extended backtests, strategy experiments, parameter sweeps,
adapter implementation, runtime/profile/risk/backtester-core modification,
promotion, small-live readiness review, or live deployment.

Passing TE-006 does not authorize TE-007 execution. TE-007 requires separate
Owner authorization.

There is no deployable small-live strategy candidate. Small-live readiness gate
remains unmet.

---

## 1. Validation Window Taxonomy

### 1.1 Window Definitions

| Window | Period | Span | Classification | Authority |
| --- | --- | --- | --- | --- |
| Base research window | 2021-01-01 to 2025-12-31 | 5 full years | Primary evidence source | Can independently support pass/pause/reject |
| Supplemental diagnostic window | 2019-10-05 to 2020-12-31 | ~14.9 months | Supplementary evidence only | Cannot independently determine pass/fail |
| Combined window | 2019-10-05 to 2025-12-31 | ~6.2 years | Full available evidence | Requires both windows to be QA-passed |

### 1.2 Window Authority Rules

1. **Base research window (2021-2025) is the primary decision authority.** If
   Direction A or B-D1 fails validation on the base window alone, the
   supplemental window cannot override that conclusion.

2. **Supplemental window (2019-2020) can only:**
   - Strengthen a base-window pass (by showing consistent behavior pre-2021).
   - Expose hidden fragility (by showing inconsistent behavior pre-2021).
   - Provide additional stress-test context (COVID crash, early-market regime).
   - It **cannot** independently pass or fail a direction.

3. **Combined window results must be interpreted as:**
   - "Base window result + supplemental window consistency check."
   - Not as a single monolithic 6.2-year backtest.

4. **2019-2020 regime differences must be documented.** If supplemental results
   diverge from base results, the divergence must be explained before the
   supplemental result is given any weight.

---

## 2. Eligibility Criteria

Before any official validation experiment (TE-007 or later) is authorized, the
following eligibility criteria must be met:

### 2.1 Data Eligibility

| Criterion | Status |
| --- | --- |
| Base window data QA-passed | MET (2021-2025, in use since project start) |
| Supplemental window data QA-passed | MET (TE-005, DATA_QA_PASSED) |
| 1h/4h alignment verified | MET (TE-005 QA 5.8) |
| Indicator warmup sufficient | MET (EMA60 first signal 2019-10-05) |
| No silent interpolation or forward-fill | MET (TE-005 import rules) |

### 2.2 Direction Eligibility

| Criterion | Direction A | Direction B-D1 |
| --- | --- | --- |
| Research-only proxy evidence exists | Yes (positive-but-fragile) | Yes (positive-but-fragile / mixed-partial) |
| Strategy logic is code-complete and frozen | TBD (Owner must confirm) | TBD (Owner must confirm) |
| Entry/exit rules are unambiguously specified | TBD (Owner must confirm) | TBD (Owner must confirm) |
| No pending parameter changes | TBD (Owner must confirm) | TBD (Owner must confirm) |

Direction eligibility must be confirmed by Owner before TE-007 is authorized.

### 2.3 Process Eligibility

| Criterion | Status |
| --- | --- |
| Validation plan (this document) exists | MET |
| Metrics and interpretation rules defined | MET (Section 3) |
| Pass/pause/reject rules defined | MET (Section 5) |
| Stop conditions defined | MET (Section 7) |
| Owner has reviewed and approved this plan | PENDING |

### 2.4 Pre-TE-007 Threshold Requirement

Owner must define realized MaxDD and MTM MaxDD tolerance thresholds before
TE-007 execution. These thresholds must be fixed before results are generated.
If thresholds are not defined prior to execution, the validation is not
official — it reverts to research-only proxy evidence.

**Update (2026-05-07):** Owner has defined thresholds for Direction A (TE-007A):
- Realized MaxDD <= 30% and MTM MaxDD <= 30%: acceptable upper bound.
- MaxDD > 30%: cannot classify as PASS.
- MaxDD <= 20%: supports PASS if other criteria met.
- MaxDD 20%–30%: maximum PASS_WITH_CAUTION or PAUSE.
- See TE-007A Section 4.2 for full classification guidance.

---

## 3. Metrics and Interpretation Rules

### 3.1 Core Metrics

All metrics must be computed separately for the base window (2021-2025) and
the supplemental window (2019-2020).

| Metric | Definition | Interpretation |
| --- | --- | --- |
| Net PnL | Sum of all trade PnL (after costs) | Positive = necessary but not sufficient |
| Profit Factor (PF) | Gross profit / Gross loss | >1.0 = profitable; >1.5 = meaningful; <1.0 = failing |
| Realized MaxDD | Maximum peak-to-trough drawdown of closed-trade equity | Lower is better; absolute threshold TBD by Owner |
| MTM MaxDD | Maximum peak-to-trough drawdown including mark-to-market | Must be reported; may differ from realized MaxDD |
| Trade count | Total number of closed trades | Must meet floor (see 3.2) |
| Win rate | Winning trades / total trades | Context metric; not a pass/fail criterion alone |
| Avg win / avg loss | Average winning trade PnL / average losing trade PnL | Must be reported; indicates reward/risk profile |
| Funding exposure | Cumulative funding paid/received | Must be reported; must not dominate PnL |

### 3.2 Sparse Trend Fragility Metrics

These metrics specifically address the concern that Direction A / B-D1 results
may be driven by a small number of large winning trades (sparse trend
fragility).

| Metric | Definition | Interpretation |
| --- | --- | --- |
| Top 1 removal | Recompute net PnL and PF after removing the single largest winning trade | If PF drops below 1.0, the strategy is critically fragile |
| Top 3 removal | Recompute after removing the 3 largest winning trades | If PF drops below 1.0, the strategy is fragile |
| Top 5 removal | Recompute after removing the 5 largest winning trades | If PF drops below 1.0, the strategy has significant concentration risk |
| Year-by-year contribution | Net PnL and PF broken down by calendar year | Every year must be positive, or the negative year must be explainable |
| Winner attribution | What fraction of total PnL comes from top 1/3/5/10 winners | High concentration = high fragility |
| Trade count floor | Minimum number of trades for statistical meaningfulness | <20 trades per year = insufficient sample; <10 total = not evaluable |
| MFE (Max Favorable Excursion) | Maximum unrealized profit reached during each trade | Indicates whether exits are capturing available profit |
| MAE (Max Adverse Excursion) | Maximum unrealified loss reached during each trade | Indicates risk exposure per trade |
| Giveback | MFE - realized PnL for winning trades | High giveback = exit timing concern |
| Funding exposure | Net funding paid/received as % of gross PnL | If funding > 20% of gross PnL, flag as funding-dependent |

### 3.3 2019 Partial-Month Treatment

2019-09-25 to 2019-09-30 is a partial month (6.7 days). Treatment rules:

1. **Do not include 2019-09 in year-by-year breakdown as a full month.**
2. **Either:** Exclude 2019-09 entirely from year-by-year analysis, or combine
   it with 2019-10 as "2019-Q4."
3. **EMA60 warmup period (2019-09-25 to 2019-10-05) must not produce any
   evaluable signals.** Any signal before 2019-10-05 08:00 UTC is a warmup
   artifact and must be excluded.
4. **Report 2019-09 row count and candle count separately** for transparency.

### 3.4 Supplemental Window Regime Notes

The supplemental window (2019-2020) contains structurally distinct market
regimes that must be documented in any validation report:

| Period | Regime | Notes |
| --- | --- | --- |
| 2019-Q4 | Early Binance USDT-M futures | Low liquidity, wide spreads, thin order book |
| 2020-Q1 (pre-COVID) | Normal market | Baseline pre-pandemic behavior |
| 2020-03 | COVID crash | Extreme volatility, 50%+ drawdown in ETH |
| 2020-Q2 | COVID recovery | V-shaped recovery, high volatility |
| 2020-Q3/Q4 | DeFi summer + consolidation | New market structure, increased retail participation |

Any validation report must include a regime-by-regime breakdown for the
supplemental window.

---

## 4. Direction A vs B-D1 Comparison Rules

### 4.1 Core Principle

B-D1 cannot automatically supersede Direction A based on marginal improvement
in net PnL or PF alone. B-D1 must demonstrate genuine improvement in entry
quality and fragility reduction.

### 4.2 Comparison Framework

| Check | Question | Required Outcome for B-D1 to Supersede A |
| --- | --- | --- |
| Net PnL | Does B-D1 improve net PnL? | Improvement is noted but not sufficient alone |
| Profit Factor | Does B-D1 improve PF? | Improvement is noted but not sufficient alone |
| Entry quality | Does B-D1 produce better-timed entries? | Must be demonstrated via MFE/MAE analysis |
| Top-winner preservation | Does B-D1 retain the top winners from Direction A? | B-D1 must not kill top winners; if it does, the trade-off must be explained |
| Fragility reduction | Does B-D1 reduce sparse trend fragility? | Must show improvement in top-1/3/5 removal tests |
| Trade count | Does B-D1 produce sufficient trade count? | Must meet the same trade count floor as Direction A |
| Regime consistency | Is B-D1 consistent across market regimes? | Must not show regime-dependent behavior that Direction A does not |

### 4.3 Decision Rules

1. **If B-D1 improves PF but kills top winners:** B-D1 does not supersede A.
   The improvement is from filtering, not from better entry timing.

2. **If B-D1 improves net PnL but increases fragility (worse top-3 removal):**
   B-D1 does not supersede A. Higher returns with higher concentration risk is
   not a genuine improvement.

3. **If B-D1 improves entry quality (better MFE/MAE) without killing top
   winners and without increasing fragility:** B-D1 may supersede A, subject to
   Owner decision.

4. **If B-D1 and Direction A are roughly equivalent:** No supersession. Both
   remain as research-only proxy evidence. Owner decides whether to pursue
   either, both, or neither.

5. **If B-D1 is worse than Direction A on any fragility metric:** B-D1 does not
   supersede A. B-D1 may still be reported as a separate result but must not
   be promoted as an improvement.

---

## 5. Pass / Pause / Reject Classification Rules

### 5.1 Classification Definitions

| Classification | Meaning | Next Step |
| --- | --- | --- |
| PASS | Direction meets all validation criteria on base window; supplemental window is consistent | Proceed to small-live readiness assessment (separate Owner decision) |
| PASS_WITH_CAUTION | Direction meets criteria on base window but supplemental window shows inconsistency or fragility | Document inconsistency; Owner decides whether to proceed |
| PAUSE | Direction shows promise but evidence is insufficient or fragile | Do not proceed; collect more evidence or refine strategy |
| REJECT | Direction fails validation criteria | Do not proceed; direction is closed |

### 5.2 Pass Criteria (Base Window, 2021-2025)

All of the following must be true for a PASS classification:

1. Net PnL > 0 (after costs, including funding).
2. PF > 1.5 on base window.
3. Realized MaxDD within Owner-specified tolerance (TBD).
4. Top-3 removal: PF remains > 1.0.
5. Every calendar year has positive net PnL, OR negative year is explainable
   and does not exceed 30% of cumulative PnL.
6. Trade count >= 20 per year on average (5 years = minimum 100 trades).
7. Funding exposure < 20% of gross PnL.
8. No single trade contributes > 50% of total PnL.

### 5.3 Pause Criteria

Any of the following triggers a PAUSE:

1. PF between 1.0 and 1.5 on base window.
2. Top-3 removal drops PF below 1.0.
3. One or more calendar years with negative PnL that exceeds 30% of
   cumulative PnL.
4. Trade count < 20 per year on average.
5. Single trade contributes > 50% of total PnL.
6. Supplemental window shows significant inconsistency with base window.

### 5.4 Reject Criteria

Any of the following triggers a REJECT:

1. PF < 1.0 on base window (strategy is unprofitable).
2. Top-1 removal drops PF below 1.0 (critically fragile).
3. Realized MaxDD exceeds Owner-specified maximum (TBD).
4. Fewer than 10 total trades across the entire base window.
5. Strategy logic produces zero trades in any calendar year.

### 5.5 Supplemental Window Impact Rules

| Base Result | Supplemental Result | Final Classification |
| --- | --- | --- |
| PASS | Consistent (PF > 1.0, same regime pattern) | PASS_WITH_CAUTION → Owner may upgrade to PASS |
| PASS | Inconsistent (PF < 1.0, different regime pattern) | PASS_WITH_CAUTION (document inconsistency) |
| PAUSE | Consistent | PAUSE (supplemental does not upgrade PAUSE to PASS) |
| PAUSE | Inconsistent | PAUSE (reinforced by supplemental inconsistency) |
| REJECT | Any | REJECT (supplemental cannot override base REJECT) |

**Key rule: Supplemental window can only downgrade or add caution, never
upgrade.** A PAUSE on the base window remains PAUSE regardless of supplemental
results. A PASS on the base window can become PASS_WITH_CAUTION if supplemental
shows inconsistency.

---

## 6. Official Validation vs Research-only Proxy Evidence

### 6.1 Definitions

| Category | Definition | Authority |
| --- | --- | --- |
| Research-only proxy evidence | Backtest results from research/development environment, not validated against official criteria | Can inform direction; cannot authorize deployment |
| Official validation | Backtest results evaluated against the criteria in this document, with both windows, full metrics, and classification | Can support promotion decision; still requires Owner approval for small-live |

### 6.2 Boundary

1. **All Direction A / B-D1 results to date are research-only proxy evidence.**
   They have not been evaluated against the criteria in this document.

2. **Official validation requires:**
   - Execution against both base and supplemental windows.
   - Full metrics computation per Section 3.
   - Classification per Section 5.
   - Independent review (Owner or designated reviewer).

3. **Research-only results cannot be cited as official validation.** Any
   document that cites Direction A or B-D1 results must clearly label them as
   "research-only proxy evidence, not officially validated."

4. **Official validation does not authorize deployment.** Even a PASS
   classification only supports a small-live readiness assessment, which is a
   separate Owner decision.

---

## 7. Stop Conditions

TE-006 is a docs-only plan. However, the following stop conditions apply to any
future validation execution (TE-007 or later):

| Condition | Action |
| --- | --- |
| Strategy logic is not code-frozen | Stop; do not validate against unfrozen logic |
| Entry/exit rules are ambiguous | Stop; clarify rules before validation |
| Data QA fails for either window | Stop; do not validate against un-QA'd data |
| 1h/4h alignment cannot be verified | Stop; alignment is prerequisite for B-D1 |
| Validation execution produces results that differ materially from research-only proxy | Stop; investigate divergence before classifying |
| Any metric computation error is discovered | Stop; recompute all metrics before proceeding |
| Owner revokes authorization | Stop immediately |

---

## 8. Owner Decision Options

After TE-006 is approved, the Owner has the following options:

### 8.1 Option A — Authorize TE-007 Validation Execution

Authorize running Direction A and/or B-D1 against both windows with full
metrics computation. This requires Level 3+ authorization (backtest execution
+ metrics computation + docs output).

### 8.2 Option B — Defer Validation

Defer official validation. Continue with research-only proxy evidence. Revisit
when Direction A or B-D1 evidence strengthens or when strategy logic is
code-frozen.

### 8.3 Option C — Validate Direction A Only

Authorize TE-007 for Direction A only. B-D1 validation is deferred until
Direction A results are classified.

### 8.4 Option D — Close Both Directions

Close Direction A and B-D1. No further validation. This is appropriate if
research-only proxy evidence is deemed insufficient to justify validation
effort.

---

## 9. TE-006 Does Not Authorize TE-007

This plan defines what official validation would look like. It does not
authorize executing that validation. TE-007 requires:

1. Owner review and approval of this plan.
2. Owner confirmation that Direction A and/or B-D1 strategy logic is
   code-frozen.
3. Owner confirmation of entry/exit rule specifications.
4. Separate TE-007 task card with explicit authorization for backtest
   execution.

---

## 10. Deliverables Checklist

- [x] Validation window taxonomy (Section 1)
- [x] Eligibility criteria (Section 2)
- [x] Core metrics and interpretation rules (Section 3.1)
- [x] Sparse trend fragility metrics (Section 3.2)
- [x] 2019 partial-month treatment (Section 3.3)
- [x] Supplemental window regime notes (Section 3.4)
- [x] Direction A vs B-D1 comparison rules (Section 4)
- [x] Pass/pause/reject classification rules (Section 5)
- [x] Official validation vs research-only boundary (Section 6)
- [x] Stop conditions (Section 7)
- [x] Owner decision options (Section 8)
- [x] TE-006 ≠ TE-007 authorization (Section 9)
- [x] No deployable small-live strategy candidate
- [x] Small-live readiness gate remains unmet

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-006 official validation readiness plan created | Codex |
| 2026-05-07 | Status updated to Accepted; section references corrected; Section 2.4 added with Owner MaxDD thresholds | Codex |
