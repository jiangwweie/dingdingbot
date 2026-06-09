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

# VEI-003: Volatility Expansion / Impulse Participation Level 3 Research Report

**Task ID:** VEI-003
**Level:** 3 research-only frozen run
**Date:** 2026-05-07
**Status:** COMPLETE
**Classification:** **PAUSE_FRAGILE**
**Upstream:** VEI-002 (frozen experiment plan)

---

## 1. Frozen Rule Verification

The frozen rule from VEI-002 was implemented without modification.

### 1.1 Entry: Impulse State Detection

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Range expansion | `(High - Low) > 1.5 × SMA(High-Low, 20)` | Yes |
| Close-location control | `Close >= Low + 0.75 × (High - Low)` | Yes |
| Trend filter | `Close > EMA60 AND EMA60[0] > EMA60[5]` | Yes |
| Donchian channel | Prohibited | Not used |
| ATR contraction precondition | Prohibited | Not used |
| Pullback / value-zone / Pinbar | Prohibited | Not used |

### 1.2 Follow-Through Confirmation

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Confirmation rule | `Close[T+1] > Close[T]` (impulse bar close) | Yes |
| Multi-bar / volume / percentage confirmation | Prohibited | Not used |

### 1.3 Entry Timing

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Impulse bar | Fully closed | Yes |
| Confirmation bar | Fully closed | Yes |
| Entry | Open of bar T+2 | Yes |
| Signal-close lookahead | Prohibited | Not used |

### 1.4 Exit Lifecycle

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Max hold | 5 bars (20h) | Yes |
| Protective stop | 2×ATR14 below entry, initial (not trailing) | Yes |
| ATR14 computed at | Impulse bar T | Yes |
| EMA60 lifecycle exit | Not used | Not used |
| Trailing / breakeven / fixed TP | Not used | Not used |

### 1.5 Same-Bar / Next-Bar Policy

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Entry-bar stop conflict | Stop wins (pessimistic) | Yes |
| Stop and time exit same bar | Stop wins (pessimistic) | Yes |

### 1.6 Cost Model

| Element | Frozen Value | Implemented |
|---------|-------------|-------------|
| Fee rate | 0.04% per side | Yes |
| Entry slippage | 0.10% | Yes |
| Exit slippage | 0.10% | Yes |
| Funding | 0.01% per 8h constant | Yes |
| Initial balance | 10,000 USDT | Yes |
| Risk fraction | 1% current realized equity | Yes |
| Max exposure | 2.0x | Yes |

**Frozen rule: CONFIRMED PRESERVED.**

---

## 2. Primary Results

### 2.1 Aggregate Metrics

| Metric | Value |
|--------|-------|
| **Closed positions** | **118** |
| **Winner count** | **56** |
| **Loser count** | **62** |
| **Win rate** | **47.5%** |
| **Net PnL** | **+630.49** |
| **Gross PnL** | **+1,585.86** |
| **Profit Factor** | **1.21** |
| **Realized MaxDD** | **4.57%** |
| **MTM MaxDD** | **4.91%** |
| **MFE avg** | **+76.10** |
| **MAE avg** | **-50.31** |
| **Giveback avg** | **+62.67** |
| **Avg hold hours** | **18.6h** |
| **Avg hold bars** | **4.75** |

### 2.2 Cost Analysis

| Metric | Value |
|--------|-------|
| Fee cost | 256.00 |
| Slippage cost | 639.99 |
| Funding cost | 59.39 |
| **Total cost drag** | **955.37** |
| **Cost as % of gross** | **60.2%** |
| **Funding as % of gross** | **3.7%** |

Cost drag is 60.2% of gross PnL. This is high but the system is still net positive. Funding is not material (<15% threshold).

### 2.3 Exit Analysis

| Exit Type | Count | % of Trades |
|-----------|-------|-------------|
| Time exit (5 bars) | 104 | 88.1% |
| Protective stop | 14 | 11.9% |
| Same-bar stop (entry bar) | 2 | 1.7% |
| Stop within 1 bar of entry | 2 | 1.7% |
| Force close | 0 | 0% |

**88.1% of trades are exited by the 5-bar time limit.** The protective stop is rarely triggered. This indicates the 2×ATR14 stop is wide relative to the 5-bar holding window — price rarely moves 2×ATR against the position within 5 bars.

### 2.4 Hold Duration Distribution

| Duration | Count |
|----------|-------|
| 1 bar | 0 |
| 2 bars | 3 |
| 3 bars | 4 |
| 4 bars | 3 |
| 5 bars | 106 |

**106 of 118 trades (89.8%) held for the full 5 bars.** The strategy is effectively a fixed-hold system with a protective stop as a safety net.

### 2.5 Impulse Diagnostics

| Metric | Value |
|--------|-------|
| Total impulse bars detected | 232 |
| Failed impulse (no follow-through) | 114 |
| **Failed impulse rate** | **49.1%** |
| Follow-through confirmed (signal generated) | 118 |

Nearly half of all impulse bars fail the follow-through confirmation. The follow-through filter is doing meaningful work — removing ~49% of signals that would otherwise be false starts.

### 2.6 Impulse Bar Range Distribution

| Percentile | Range / Avg Range(20) |
|-----------|----------------------|
| P25 | 1.78× |
| P50 (median) | 2.07× |
| P75 | 2.60× |

Most impulse bars have range 1.8-2.6× the 20-bar average. The 1.5× threshold is at the lower end — most signals come from bars well above the minimum.

---

## 3. Top-N Fragility Analysis

### 3.1 Top-N Removal

| Metric | Value |
|--------|-------|
| Top-1 winner PnL | +393.14 |
| Top-1 as % of gross winners | 22.7% |
| **Net excluding top-1** | **+237.34** (positive) |
| Top-3 winners PnL | +917.34 |
| **Net excluding top-3** | **-286.85** (NEGATIVE) |
| Top-5 winners PnL | +1,277.48 |
| **Net excluding top-5** | **-647.00** (NEGATIVE) |

**Top-1 removal: positive.** Unlike Direction A (top-1 is still positive at +1,029), VEI's top-1 removal is also positive but much smaller (+237). The system does not depend on a single winner.

**Top-3 removal: NEGATIVE.** Removing the top 3 winners turns the system net negative (-286.85). This is the PAUSE_FRAGILE trigger.

### 3.2 Comparison to Prior Directions

| Direction | Top-1 Net Excl. | Top-3 Net Excl. | Top-5 Net Excl. |
|-----------|-----------------|-----------------|-----------------|
| Direction A | +1,029.57 | **-935.73** | -1,812.81 |
| Direction C | N/A | **-2,471.12** | N/A |
| **VEI** | **+237.34** | **-286.85** | **-647.00** |

VEI has **less severe** top-N fragility than Direction A or Direction C in absolute terms. The top-3 net excluding is -287 vs Direction A's -936 and Direction C's -2,471. However, the fragility shape is similar: removing 3 winners turns the system negative.

---

## 4. Year-by-Year Breakdown

| Year | Trades | Winners | Win Rate | Net PnL | PF | Realized DD |
|------|--------|---------|----------|---------|-----|-------------|
| 2021 | 36 | 17 | 47.2% | **-70.09** | 0.93 | 4.57% |
| 2022 | 13 | 8 | 61.5% | +154.85 | 1.65 | 3.59% |
| 2023 | 22 | 10 | 45.5% | +205.80 | 1.41 | 3.43% |
| 2024 | 25 | 11 | 44.0% | +157.70 | 1.25 | 2.38% |
| 2025 | 22 | 10 | 45.5% | +182.22 | 1.28 | 2.55% |

**2021 is the only negative year (-70.09).** 2022-2025 are all positive. The year-by-year pattern is more stable than Direction A (dominated by 2023/2024) or Direction C (10 winners total). VEI has 3+ positive years with 10+ winners each.

**Trade count floor: MET.** 118 total trades ≥ 55 minimum. 2021+2022 = 49, 2023-2025 = 69.

**Winner floor: MET.** 56 total winners ≥ 15 minimum.

---

## 5. Overlap Gates

### 5.1 Direction A Overlap Gate

| Metric | Value |
|--------|-------|
| VEI signals matching Direction A (±1 bar) | 32 |
| Total VEI signals | 118 |
| **Overlap ratio** | **27.1%** |
| **Gate threshold** | **≥50%** |
| **Gate result** | **PASS** |

VEI is NOT a Direction A variant. 72.9% of VEI signals occur in bars where Direction A does not fire. The structural distinctness is confirmed at the signal-set level.

### 5.2 Direction C Overlap Gate

| Metric | Value |
|--------|-------|
| VEI signals matching Direction C (±1 bar) | 3 |
| Total VEI signals | 118 |
| **Overlap ratio** | **2.5%** |
| **Gate threshold** | **≥50%** |
| **Gate result** | **PASS** |

VEI is NOT a Direction C variant. Overlap is minimal (2.5%). The "no contraction precondition" distinction is empirically validated — VEI fires in different market states than Direction C.

### 5.3 Additional Overlap (Reported, Not Gating)

| Direction | Overlap Count | Overlap % |
|-----------|--------------|-----------|
| Direction D | 22 | 18.6% |
| SSD-003 | 1 | 0.8% |
| CPM-1 | 5 | 4.2% |

No pullback-continuation drift detected. Direction D overlap is moderate (18.6%) but well below any concern threshold. CPM-1 overlap is minimal (4.2%).

### 5.4 Top-5 Winner Overlap

| Reference | Overlap Count | Details |
|-----------|--------------|---------|
| Direction A top-5 | **3/5** | Top 3 VEI winners overlap with Direction A signals |
| Direction C top-5 | **0/5** | No overlap |

**Critical finding: 3 of VEI's top-5 winners are also Direction A signals.** The top 3 winners (+393, +300, +225 = +917) are shared with Direction A. This means the most profitable VEI trades are not independent — they capture the same moves as Direction A.

### 5.5 Independent Signal Performance

| Metric | Value |
|--------|-------|
| VEI signals with NO Direction A or C overlap | 85 |
| Net PnL of independent signals | **-329.02** |
| Profit Factor | **0.86** |
| Win rate | 45.9% |
| Winner count | 39 |

**Independent signals are NET NEGATIVE.** VEI signals that do NOT overlap with Direction A or Direction C lose money (-329.02). The entire positive net PnL (+630.49) comes from the 33 signals that overlap with Direction A (+959.51).

**This is the most important finding of VEI-003.**

---

## 6. Failure Closure Assessment

### 6.1 Hypothesis Evaluation

| # | Hypothesis | Result | Evidence |
|---|-----------|--------|----------|
| H1 | Bar-level impulse detection is a distinct profit source from Direction A | **WEAKENED but not closed** | Signal overlap is only 27.1% (PASS). But independent signals are negative. Profitable signals come from Direction A overlap. |
| H2 | Volatility expansion without contraction precondition is structurally different from Direction C | **CONFIRMED DISTINCT** | Only 2.5% overlap. VEI fires in different market states. |
| H3 | OHLCV-only impulse + follow-through can distinguish continuation from exhaustion | **PARTIALLY CONFIRMED** | Follow-through filters 49% of false starts. But the remaining signals still show 88% time-exit (not strong continuation). |
| H4 | Impulse participation has lower top-winner fragility | **NOT CONFIRMED** | Top-3 removal is -286.85 (negative). Fragility shape is similar to Direction A, just less severe in absolute terms. |
| H5 | Fixed-hold exit matches impulse energy decay | **NOT CONFIRMED** | 89.8% of trades hold for the full 5 bars. The 5-bar hold does not appear to capture a distinct energy decay — it's just a fixed exit. |

### 6.2 Key Finding: VEI Is Direction A's Echo, Not an Independent Signal

The evidence shows:
1. Direction A overlap is 27.1% (below 50% gate).
2. BUT the 33 overlapping signals generate +959.51 net PnL.
3. The 85 independent signals generate -329.02 net PnL.
4. Removing Direction A overlap from VEI turns the system negative.

**Interpretation:** VEI's bar-level impulse detection is structurally distinct from Direction A's Donchian breakout (different signal sets, 27% overlap). But VEI's independent signals — the ones that fire when Direction A does NOT — are unprofitable. The profitable VEI signals are an echo of Direction A: they fire in the same trending moves, just detected through a different mechanism.

This is NOT the same as being a Direction A variant (overlap <50%, gate passed). But it means VEI does not generate independent alpha. Its positive PnL comes from partially capturing Direction A's winners through a different lens.

---

## 7. Classification

### 7.1 Primary Classification

**PAUSE_FRAGILE**

**Reason:** Top-3 net excluding is negative (-286.85). The system depends on its top-3 winners for all profitability. Independent (non-Direction-A) signals are net negative.

### 7.2 Evaluation Against SRD-001 Conditions

| Condition | Status | Detail |
|-----------|--------|--------|
| Mechanism structure clear | PASS | Frozen entry/exit completely defined |
| Structurally different from A, C, CPM-1, D | PASS | Signal overlap below 50% for all |
| No parameter search | PASS | 5 frozen parameters, no sweep |
| Uses current OHLCV | PASS | No new data |
| Applicability boundaries pre-observable | WEAK | Applicability overlaps with Direction A's trending market state |
| Stop conditions explicit | PASS | All stop conditions pre-defined |
| Information gain | HIGH | Key finding: independent signals are negative |
| Failure closes hypothesis | PASS | H1 partially closed; H2-H5 assessed |
| No runtime changes | PASS | |
| Cannot be interpreted as runtime approval | PASS | |

### 7.3 What PAUSE_FRAGILE Means for VEI

VEI is not rejected. The overlap gates passed (Direction A 27%, Direction C 2.5%). The mechanism IS structurally distinct. But the evidence shows that VEI's independent edge is negative — its profitability depends on capturing the same market moves as Direction A.

The PAUSE_FRAGILE classification means:
- The frozen concept does not generate independent alpha.
- Further work (variants, parameter search, rescue) is prohibited.
- The concept should be preserved as evidence, not promoted.

---

## 8. Failure Closure

### 8.1 Closed Hypotheses

| Hypothesis | Status |
|-----------|--------|
| Bar-level impulse detection as independent profit source (H1) | **WEAKENED** — signal set is distinct but independent signals are negative. Not fully closed because the signal mechanism IS different from Direction A. |
| OHLCV-only impulse + follow-through distinguishes continuation from exhaustion (H3) | **PARTIALLY CONFIRMED** — follow-through filter works (49% filtered), but remaining signals show weak continuation (88% time-exit). |
| Lower top-winner fragility (H4) | **NOT CONFIRMED** — PAUSE_FRAGILE. |
| Fixed-hold matches impulse energy decay (H5) | **NOT CONFIRMED** — 90% hold for full 5 bars. |

### 8.2 Preserved Evidence

The following evidence is preserved for future direction mapping:
- VEI signal set is structurally distinct from Direction A (27% overlap) and Direction C (2.5% overlap).
- Follow-through confirmation filters ~49% of false starts.
- The mechanism fires in 4 of 5 years (2022-2025 positive).
- Top-3 fragility is less severe than Direction A or C in absolute terms.
- Cost drag is high (60% of gross) but the system is still net positive overall.

### 8.3 Prohibited Follow-Ups (Per VEI-002 Failure Closure)

Since VEI-003 result is PAUSE_FRAGILE (not REJECTED), the strict failure closure prohibitions from VEI-002 Section 13 partially apply. The following are **prohibited**:

| # | Prohibited | Rationale |
|---|-----------|-----------|
| P1-P5 | Parameter variants (K, N, P, EMA, slope) | Parameter rescue |
| P6-P7 | Direction A/C breakout rescue | Old-path drift |
| P8 | Pullback-entry rescue | Concept was non-pullback |
| P9 | 1h/15m timing search | Timeframe scope creep |
| P10 | Funding/OI rescue | Different hypothesis |
| P11 | Short-side mirror | Different direction scope |
| P12 | Router/portfolio/regime | Infrastructure |
| P13-P16 | Confirmation/exit/stop/hold variants | Lifecycle rescue |

---

## 9. Implications for Direction Map

### 9.1 What VEI-003 Adds to the Map

| Direction | Status | Key Evidence |
|-----------|--------|-------------|
| Direction A | PAUSE_FRAGILE | Top-3 removal -936. |
| Direction C | INSUFFICIENT_EVIDENCE | 63 trades, 10 winners. |
| Direction D | REJECTED | Net -263, PF 0.985. |
| SSD-003 | REJECTED | Net -1,700, 1 winner. |
| **VEI** | **PAUSE_FRAGILE** | **Independent signals negative. Top-3 removal -287. Profit comes from Direction A overlap echo.** |
| CPM-1 | Paused | OOS failure. |

### 9.2 Meta-Hypothesis Update

VEI-003 adds to the evidence for the meta-hypothesis from SR-001:

> "No OHLCV-only strategy module on ETH 4h has a validated, pre-observable applicability boundary that survives enough trades, enough winners, top-winner fragility, year concentration, and realistic costs."

VEI passed trade count (118) and winner count (56) floors. It passed overlap gates (27% A, 2.5% C). But it failed the independent-alpha test: profitable signals are Direction A echoes, not independent captures.

Combined with Direction A (PAUSE_FRAGILE), Direction C (INSUFFICIENT_EVIDENCE), Direction D (REJECTED), SSD-003 (REJECTED), and CPM-1 (paused), **the non-pullback direction pipeline is now exhausted.** SRD-002's Rank 1 (VEI) has been inspected and paused. Rank 2 (short-side) was closed by SSD-003/SSD-004. No immediate non-pullback candidate remains.

---

## 10. Owner Summary

### 1. Frozen Rule Preserved?

**Yes.** All frozen elements from VEI-002 (entry, follow-through, timing, exit lifecycle, stop, cost model, same-bar policy) were implemented without modification.

### 2. Direction A Old-Path Drift?

**No (gate passed).** Direction A signal overlap is 27.1%, well below the 50% gate. VEI's signal set IS structurally distinct from Direction A.

**However:** 3 of VEI's top-5 winners overlap with Direction A. Independent (non-overlapping) signals are net negative (-329). VEI's profitable trades are an echo of Direction A, not an independent capture.

### 3. Direction C Old-Path Drift?

**No (gate passed).** Direction C overlap is 2.5%. VEI fires in genuinely different market states than Direction C.

### 4. CPM/D/SSD/Pullback Drift?

**No.** CPM-1 overlap 4.2%, Direction D 18.6%, SSD-003 0.8%. No pullback-continuation drift.

### 5. Performance / DD / Fragility?

- **Performance:** Net +630.49, PF 1.21. Positive but modest.
- **DD:** Realized 4.57%, MTM 4.91%. Acceptable.
- **Fragility:** PAUSE_FRAGILE. Top-3 removal -286.85. Independent signals negative.
- **Cost drag:** 60.2% of gross. High but system still net positive.

### 6. Independent Non-Overlap Signals Valuable?

**No.** 85 independent signals (no Direction A or C overlap) produce net -329.02, PF 0.86. The entire positive PnL comes from the 33 signals that overlap with Direction A.

### 7. Failure Closure?

VEI is classified PAUSE_FRAGILE, not REJECTED. The concept is preserved as evidence. All prohibited follow-ups from VEI-002 Section 13 apply. The hypothesis "bar-level impulse detection is a distinct profit source" is weakened (not closed) — the signal set is distinct but does not generate independent alpha.

### 8. Runtime Candidate / Small-Live Readiness?

**No.** VEI-003 result is PAUSE_FRAGILE. Not a runtime candidate. Not a small-live candidate. Live-safe foundation has been substantially completed but the strategy promotion pipeline is empty. The small-live readiness gate remains unmet.

---

## Appendix A: Reproducibility

| Element | Value |
|---------|-------|
| Adapter script | `reports/vei-003-volatility-expansion-impulse-participation/vei_003_research_adapter.py` |
| Summary JSON | `reports/vei-003-volatility-expansion-impulse-participation/summary.json` |
| Signals JSONL | `reports/vei-003-volatility-expansion-impulse-participation/signals.jsonl` |
| Trades JSONL | `reports/vei-003-volatility-expansion-impulse-participation/trades.jsonl` |
| Equity curve | `reports/vei-003-volatility-expansion-impulse-participation/equity_curve.jsonl` |
| Database | `data/v3_dev.db`, table `klines` |
| Symbol | ETH/USDT:USDT |
| Timeframe | 4h |
| Window | 2021-01-01 to 2025-12-31 |
| Reference Direction A | `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/signals.jsonl` |
| Reference Direction C | `reports/mtc-004-direction-c-frozen-baseline/signals.jsonl` |
| Reference Direction D | `reports/mtc-006-direction-d-structured-pullback/signals.jsonl` |
| Reference SSD-003 | `reports/ssd-003-short-side-breakdown-continuation/signals.jsonl` |
| Reference CPM-1 | `reports/oos_runs/cpm1_2021_oos/result.json`, `cpm1_2022_oos/result.json` |
