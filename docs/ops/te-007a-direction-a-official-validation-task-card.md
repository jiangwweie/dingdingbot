# TE-007A - Direction A Official Validation Execution Task Card

**Task ID:** TE-007A
**Date:** 2026-05-07
**Status:** Proposed / Task Card Only
**Authorization Level:** Level 2 — task card only; no execution authorization

---

## 0. Boundary Statements

This is a task card only. It does not authorize executing Direction A. It does
not authorize running Direction B-D1. It does not authorize backtest execution,
strategy experiments, parameter sweeps, adapter implementation,
runtime/profile/risk/backtester-core modification, promotion, small-live
readiness review, or live deployment.

Direction A and B-D1 results to date are research-only proxy evidence, not
officially validated.

TE-007A task card does not equal execution authorization. Executing Direction A
official validation requires Owner to separately approve Level 3 authorization.

There is no deployable small-live strategy candidate. Small-live readiness gate
remains unmet.

---

## 1. Goal

Create an official validation execution task card for Direction A, specifying
frozen rules, validation windows, required metrics, classification rules, and
stop conditions. This task card defines what execution would look like; it does
not authorize that execution.

---

## 2. Direction A — Frozen Rules

The following rules are frozen for TE-007A validation. No parameter changes,
overlay additions, or rule modifications are permitted during validation.

### 2.1 Entry

| Rule | Specification |
| --- | --- |
| Signal | 4h Donchian20 breakout — price closes above the upper channel (highest high of the previous 20 closed 4h candles) |
| Entry timing | Next 4h candle open after signal candle closes |
| Entry bar | The 4h candle that opens immediately after the signal candle |
| Confirmation | Signal candle must be fully closed before entry is taken |

### 2.2 Initial Stop

| Rule | Specification |
| --- | --- |
| Stop level | Lowest low of the previous 20 closed 4h candles at the time of entry |
| Stop type | Fixed at entry; does not trail during the trade |
| Stop trigger | If any 4h candle low touches or breaches the stop level, the stop is triggered |

### 2.3 Exit

| Rule | Specification |
| --- | --- |
| Exit signal | 4h candle closes below EMA60 |
| Exit timing | Next 4h candle open after exit signal candle closes |
| Exit bar | The 4h candle that opens immediately after the exit signal candle |
| Stop exit | If initial stop is triggered before EMA60 exit, exit at stop |

### 2.4 Overlays and Exclusions

| Overlay/Feature | Status |
| --- | --- |
| Direction E overlay | NOT INCLUDED — no post-entry early exit overlay |
| 1h entry timing | NOT INCLUDED — entry is on 4h open only |
| 1h exit timing | NOT INCLUDED — exit is on 4h open only |
| Trailing stop | NOT INCLUDED — initial stop is fixed |
| Partial position sizing | NOT INCLUDED — full entry/exit |
| Parameter changes | NOT PERMITTED — all parameters are frozen as specified above |

### 2.5 Parameters

| Parameter | Value | Frozen |
| --- | --- | --- |
| Donchian channel period | 20 (closed 4h candles) | Yes |
| EMA period | 60 (closed 4h candles) | Yes |
| Timeframe | 4h | Yes |
| Symbol | ETH/USDT:USDT | Yes |
| Entry timing | Next 4h open | Yes |
| Exit timing | Next 4h open | Yes |
| Initial stop lookback | 20 closed 4h candles | Yes |

---

## 3. Validation Windows

### 3.1 Base Window

| Field | Value |
| --- | --- |
| Period | 2021-01-01 00:00:00 UTC to 2025-12-31 20:00:00 UTC |
| Span | 5 full years |
| Classification | Primary evidence source |
| Authority | Can independently support pass/pause/reject |

### 3.2 Supplemental Window

| Field | Value |
| --- | --- |
| Period | 2019-10-05 08:00:00 UTC to 2020-12-31 20:00:00 UTC |
| Span | ~14.9 months (after EMA60 warmup) |
| Classification | Supplemental diagnostic window only |
| Authority | Cannot independently determine pass/fail |
| Regime notes | Early Binance USDT-M, COVID crash (2020-03), DeFi summer (2020-Q3/Q4) |

### 3.3 Combined Interpretation Rule

Combined results must be interpreted as **base window result + supplemental
window consistency check**. They must not be interpreted as a monolithic 6.2-year
proof.

If supplemental results diverge from base results, the divergence must be
documented and explained before the supplemental result is given any weight.

---

## 4. Required Metrics

All metrics must be computed separately for the base window and the
supplemental window, then reported side-by-side.

### 4.1 Core Metrics

| Metric | Definition |
| --- | --- |
| Net PnL | Sum of all trade PnL after costs (including funding) |
| Profit Factor (PF) | Gross profit / Gross loss |
| Realized MaxDD | Maximum peak-to-trough drawdown of closed-trade equity |
| MTM MaxDD | Maximum peak-to-trough drawdown including mark-to-market |
| Trade count | Total number of closed trades |
| Win rate | Winning trades / total trades |
| Avg win / avg loss | Average winning trade PnL / average losing trade PnL |
| Funding exposure | Cumulative funding paid/received; must report as absolute and as % of gross PnL |

### 4.2 Owner MaxDD Thresholds

Owner has defined the following hard risk tolerance bounds:

| Threshold | Value | Rule |
| --- | --- | --- |
| Realized MaxDD | <= 30% | Acceptable upper bound |
| MTM MaxDD | <= 30% | Acceptable upper bound |
| Realized MaxDD | > 30% | Cannot classify as PASS |
| MTM MaxDD | > 30% | Cannot classify as PASS |

MaxDD classification guidance:

| MaxDD Range | Maximum Classification | Notes |
| --- | --- | --- |
| <= 20% | PASS (if all other criteria met) | Low drawdown; if sparse trend fragility metrics also pass, supports PASS |
| 20%–30% | PASS_WITH_CAUTION or PAUSE | Must be explained in context of top-winner concentration, top-1/3/5 removal, year-by-year contribution, MFE/MAE, giveback, and funding exposure |
| > 30% | REJECT (or Owner复核 required) | Cannot enter PASS or PASS_WITH_CAUTION without Owner override |

**30% is the Owner risk tolerance upper bound, not an automatic pass condition.**
Direction A pass/fail is determined by the full metric suite, especially
top-winner fragility. Even if TE-007A classifies as PASS, that does not equal
runtime implementation, promotion, small-live readiness, or live deployment.

### 4.2 Sparse Trend Fragility Metrics

| Metric | Definition |
| --- | --- |
| Top 1 removal | Recompute net PnL and PF after removing the single largest winning trade |
| Top 3 removal | Recompute after removing the 3 largest winning trades |
| Top 5 removal | Recompute after removing the 5 largest winning trades |
| Year-by-year contribution | Net PnL and PF broken down by calendar year |
| Winner attribution | Fraction of total PnL from top 1/3/5/10 winners |
| Trade count floor | <20 trades/year average = insufficient sample; <10 total = not evaluable |
| MFE | Max favorable excursion per trade (max unrealized profit reached) |
| MAE | Max adverse excursion per trade (max unrealized loss reached) |
| Giveback | MFE - realized PnL for winning trades |

### 4.3 2019 Partial-Month Treatment

- 2019-09 is a partial month (6.7 days, starting 2019-09-25).
- EMA60 warmup period (2019-09-25 to 2019-10-05) must not produce any
  evaluable signals.
- Do not include 2019-09 in year-by-year breakdown as a full month. Either
  exclude it or combine with 2019-10 as "2019-Q4."

### 4.4 Supplemental Window Regime Breakdown

The supplemental window validation report must include a regime-by-regime
breakdown:

| Period | Regime |
| --- | --- |
| 2019-Q4 | Early Binance USDT-M futures (low liquidity, wide spreads) |
| 2020-Q1 (pre-COVID) | Normal market |
| 2020-03 | COVID crash (extreme volatility, 50%+ ETH drawdown) |
| 2020-Q2 | COVID recovery (V-shaped, high volatility) |
| 2020-Q3/Q4 | DeFi summer + consolidation (new market structure) |

---

## 5. Classification Rules

Classification follows TE-006 Section 5.

### 5.1 PASS

All of the following must be true on the base window:

1. Net PnL > 0 (after costs, including funding).
2. PF > 1.5.
3. Realized MaxDD <= 20% AND MTM MaxDD <= 20%.
4. Top-3 removal: PF remains > 1.0.
5. Every calendar year has positive net PnL, OR negative year is explainable
   and does not exceed 30% of cumulative PnL.
6. Trade count >= 20 per year on average (5 years = minimum 100 trades).
7. Funding exposure < 20% of gross PnL.
8. No single trade contributes > 50% of total PnL.

### 5.2 PASS_WITH_CAUTION

Base window meets PASS criteria for PF, trade count, top-3 removal, and
year-by-year contribution, but one or more of the following apply:

1. Realized MaxDD or MTM MaxDD is between 20% and 30% (requires explanation
   in context of top-winner concentration, top-1/3/5 removal, MFE/MAE,
   giveback, and funding exposure).
2. Supplemental window shows inconsistency or fragility.

Owner decides whether to proceed.

### 5.3 PAUSE

Any of the following on the base window:

1. PF between 1.0 and 1.5.
2. Top-3 removal drops PF below 1.0.
3. One or more calendar years with negative PnL exceeding 30% of cumulative.
4. Trade count < 20 per year on average.
5. Single trade contributes > 50% of total PnL.
6. Realized MaxDD or MTM MaxDD between 20% and 30% with unexplained fragility.
7. Supplemental window shows significant inconsistency with base window.

### 5.4 REJECT

Any of the following on the base window:

1. PF < 1.0.
2. Top-1 removal drops PF below 1.0.
3. Realized MaxDD > 30% or MTM MaxDD > 30%.
4. Fewer than 10 total trades across the entire base window.
5. Strategy logic produces zero trades in any calendar year.

### 5.5 Supplemental Window Impact

| Base Result | Supplemental Result | Final Classification |
| --- | --- | --- |
| PASS | Consistent | PASS_WITH_CAUTION → Owner may upgrade to PASS |
| PASS | Inconsistent | PASS_WITH_CAUTION |
| PAUSE | Any | PAUSE (supplemental cannot upgrade PAUSE) |
| REJECT | Any | REJECT (supplemental cannot override base REJECT) |

---

## 6. Stop Conditions

Stop conditions follow TE-006 Section 7. If any of the following occur during
validation execution, stop immediately and report:

| Condition | Action |
| --- | --- |
| Strategy logic is not code-frozen | Stop; do not validate against unfrozen logic |
| Entry/exit rules are ambiguous | Stop; clarify rules before validation |
| Data QA fails for either window | Stop; do not validate against un-QA'd data |
| 1h/4h alignment cannot be verified | Stop; alignment is prerequisite for B-D1 (not A, but flag if relevant) |
| Validation results differ materially from research-only proxy | Stop; investigate divergence before classifying |
| Any metric computation error is discovered | Stop; recompute all metrics before proceeding |
| Owner revokes authorization | Stop immediately |
| Owner has not defined MaxDD thresholds before execution | Stop; per TE-006 Section 2.4, thresholds must be fixed before results are generated |

---

## 7. Pre-Execution Checklist

Before TE-007A execution is authorized (Level 3), the following must be
confirmed:

- [ ] Owner has reviewed and approved TE-006 (this plan's parent document).
- [ ] Owner has defined realized MaxDD tolerance threshold (MET: <= 30% hard bound; see Section 4.2).
- [ ] Owner has defined MTM MaxDD tolerance threshold (MET: <= 30% hard bound; see Section 4.2).
- [ ] Direction A strategy logic is code-frozen and matches Section 2 of this
      task card.
- [ ] Entry/exit rules are unambiguously specified and match Section 2.
- [ ] No pending parameter changes.
- [ ] Base window data (2021-2025) is QA-passed.
- [ ] Supplemental window data (2019-2020) is QA-passed (TE-005).
- [ ] 1h/4h alignment verified (TE-005 QA 5.8).
- [ ] EMA60 warmup period correctly handled (2019-09-25 to 2019-10-05 excluded).

---

## 8. TE-007A ≠ Execution Authorization

This task card defines what Direction A official validation execution would
look like. It does not authorize that execution.

Executing Direction A official validation requires:

1. Owner review and approval of this task card.
2. Owner confirmation that all pre-execution checklist items (Section 7) are
   met.
3. Separate TE-007A execution task card with Level 3 authorization (backtest
   execution + metrics computation + docs output).
4. Owner-defined MaxDD thresholds (per Section 4.2; now defined: 30% hard bound).

---

## 9. Deliverables (Upon Execution Authorization)

When TE-007A execution is separately authorized, the deliverables will be:

1. **TE-007A validation report** at `docs/ops/te-007a-direction-a-official-validation-report.md`
   containing:
   - Base window metrics (Section 4.1 + 4.2).
   - Supplemental window metrics (Section 4.1 + 4.2).
   - Supplemental regime breakdown (Section 4.4).
   - Classification per Section 5.
   - Year-by-year breakdown.
   - Top-1/3/5 removal analysis.
   - Winner attribution analysis.
   - MFE/MAE/giveback analysis.
   - Funding exposure analysis.
   - 2019 partial-month treatment documentation.
   - Stop conditions encountered, if any.
   - Explicit statement: "This is official validation, not promotion
     authorization."
   - Explicit statement: "There is no deployable small-live strategy candidate.
     Small-live readiness gate remains unmet."

---

## 10. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial TE-007A task card created | Codex |
| 2026-05-07 | Owner defined MaxDD thresholds: 30% hard bound, 20% PASS support, 20-30% PASS_WITH_CAUTION/PAUSE | Codex |
