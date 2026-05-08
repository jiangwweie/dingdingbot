# VEI-004: Archive VEI-003 Evidence And Update Direction Maps

**Task ID:** VEI-004
**Level:** 1/2 docs-only
**Date:** 2026-05-07
**Status:** COMPLETE
**Upstream:** VEI-003 (Level 3 research-only frozen run, PAUSE_FRAGILE)

---

## 0. Boundary

This document archives the VEI-003 Level 3 result and writes the final
classification into the direction maps. It is not:

- a new strategy experiment;
- a backtest request;
- strategy script or adapter authorization;
- parameter optimization;
- Level 3 authorization;
- runtime/profile/risk/backtester-core work;
- small-live readiness review;
- strategy promotion.

No runtime candidate, deployable small-live strategy, live profile change,
strategy enablement, or risk-rule change follows from this document.

---

## 1. VEI-003 Final Classification

**Classification: PAUSE_FRAGILE**

**Reason:** Top-3 winner removal turns system net negative (-286.85). All
positive PnL comes from 33 signals that overlap with Direction A. The 85
independent (non-Direction-A, non-Direction-C) signals are net negative
(-329.02, PF 0.86). VEI does not generate independent bar-level impulse alpha.

---

## 2. Positive Evidence

| # | Evidence | Detail |
|---|----------|--------|
| E1 | Overall net positive | Net PnL +630.49 across 118 closed trades |
| E2 | Profit Factor > 1.0 | PF 1.21 |
| E3 | Trade count floor met | 118 trades ≥ 55 minimum |
| E4 | Winner count floor met | 56 winners ≥ 15 minimum |
| E5 | Direction A overlap gate passed | 27.1% overlap < 50% gate threshold |
| E6 | Direction C overlap gate passed | 2.5% overlap < 50% gate threshold |
| E7 | Mechanism not direct old-path drift | Signal set is structurally distinct from both Direction A (Donchian breakout) and Direction C (ATR contraction/re-expansion) |
| E8 | Follow-through filter works | 49.1% of impulse bars fail follow-through — the filter removes meaningful false starts |
| E9 | Multi-year positive | 2022-2025 all positive; only 2021 negative (-70.09) |
| E10 | Less severe top-N fragility than prior directions | Top-3 net excluding is -287 vs Direction A's -936 and Direction C's -2,471 |
| E11 | Realized DD acceptable | 4.57% realized MaxDD, 4.91% MTM MaxDD |

---

## 3. Negative Evidence

| # | Evidence | Detail |
|---|----------|--------|
| N1 | Independent signals net negative | 85 signals with NO Direction A or C overlap: net -329.02, PF 0.86 |
| N2 | All positive PnL from Direction A overlap | The 33 signals overlapping Direction A produce +959.51; removing them turns VEI negative |
| N3 | Top-3 removal negative | Removing top-3 winners: net -286.85 (PAUSE_FRAGILE trigger) |
| N4 | Not an independent profit source | VEI captures Direction A's moves through a different mechanism but does not generate alpha beyond what Direction A already captures |
| N5 | 88% time-exit | 104 of 118 trades exit by 5-bar time limit; protective stop rarely triggered |
| N6 | 89.8% full hold | 106 of 118 trades hold for full 5 bars; fixed-hold does not capture distinct energy decay |
| N7 | Cost drag 60.2% of gross | Total cost 955.37 vs gross PnL 1,585.86 |
| N8 | H1 weakened but not closed | Bar-level impulse detection is structurally distinct at signal-set level but does not produce independent alpha |
| N9 | H4 not confirmed | Top-3 removal is negative; fragility shape is similar to Direction A, less severe only in absolute terms |
| N10 | H5 not confirmed | 90% hold for full 5 bars; fixed-hold exit does not match impulse energy decay |

---

## 4. Evidence Interpretation

### 4.1 What VEI-003 Proved

VEI proved that bar-level impulse detection (range expansion + close-location +
follow-through) produces a structurally distinct signal set from Direction A's
Donchian breakout (27.1% overlap) and Direction C's contraction/re-expansion
(2.5% overlap). The overlap gates passed.

The follow-through confirmation filter does meaningful work, removing ~49% of
impulse bars that fail the next-bar confirmation.

### 4.2 What VEI-003 Did Not Prove

VEI did not prove that its distinct signal set generates independent alpha.
The 85 signals that fire when Direction A does NOT fire are net negative
(-329.02, PF 0.86). The entire positive PnL (+630.49) comes from the 33
signals that overlap with Direction A (+959.51).

This means VEI's bar-level energy detection is an echo of Direction A's trend
capture, not an independent capture. The mechanism is different; the profit
source is the same.

### 4.3 Top-Winner Overlap

3 of VEI's top-5 winners overlap with Direction A signals. The top 3 VEI
winners (+393, +300, +225 = +917) are shared with Direction A. The most
profitable VEI trades capture the same trending moves that Direction A
captures.

---

## 5. Direction Map Updates

### 5.1 SMA-001 Update

VEI is added to the Strategy Module Applicability Map as follows:

| Object | Classification | Role | Family | Next Allowed Action |
|--------|---------------|------|--------|-------------------|
| VEI (volatility expansion / impulse participation) | `PAUSE_FRAGILE` | Paused non-pullback bar-level impulse evidence | Non-pullback / impulse capture | Preserve as evidence; no variants |

Evidence row in Section 5.1:

| Object | Positive evidence | Negative evidence | Trade/winner count | Top-winner fragility | Year concentration | MFE/MAE/giveback | MTM DD | Overlap/drift | Classification |
|--------|-------------------|-------------------|-------------------|----------------------|-------------------|------------------|--------|---------------|----------------|
| VEI | Structurally distinct from A/C (overlap gates passed); net +630.49; PF 1.21; trade/winner floors met; 2022-2025 positive; follow-through filters 49% false starts | Independent signals net -329.02 PF 0.86; all positive PnL from Direction A overlap echo; top-3 removal -286.85; 88% time-exit; cost drag 60.2% | 118 trades; 56 winners | Top-1 +237 net excl.; top-3 -286.85 | 2021 negative; 2022-2025 positive but modest | Avg MFE +76.10, avg MAE -50.31, avg giveback +62.67 | MTM DD 4.91% | Direction A 27.1%, Direction C 2.5%; independent signals negative | `PAUSE_FRAGILE` |

### 5.2 SRD-002 Update

VEI is moved from "Immediate Level 1/2 inspect" (Rank 1) to `PAUSE_FRAGILE`.
The non-pullback immediate candidate queue is now exhausted.

Updated ranking:

| Rank | Direction | Classification |
|------|-----------|---------------|
| 1 | Volatility expansion / impulse participation | **PAUSE_FRAGILE** — VEI-003 frozen Level 3 completed; independent signals negative; all positive PnL from Direction A echo |
| 2 | Short-side / two-sided directional re-evaluation | Closed for breakdown continuation (SSD-003); needs new Owner-approved direction refresh |
| 3 | Trend persistence without value-zone pullback | Candidate inspect; no immediate queue promotion |
| 4 | Range / mean-reversion | Backlog / optional inspect |
| 5 | Exhaustion / avoidance validity map | Backlog |
| 6 | Funding/OI-informed module | Backlog; future data dependency |
| 7 | Cross-timeframe execution-only auxiliary | Docs-only backlog |

### 5.3 Task Board Update

VEI-003 and VEI-004 are added to the Strategy Candidate Inspect section of
`live-safe-v1-task-board.md`.

---

## 6. What PAUSE_FRAGILE Means

### 6.1 Definition

VEI is not rejected. The overlap gates passed. The mechanism IS structurally
distinct. But the evidence shows VEI does not generate independent alpha.

PAUSE_FRAGILE means:

- The frozen concept does not generate independent alpha.
- The concept is preserved as evidence, not promoted.
- Further work (variants, parameter search, rescue) is prohibited.

### 6.2 Why Not Runtime / Not Small-Live

| Condition | Status |
|-----------|--------|
| Independent alpha demonstrated | **NO** — independent signals net negative |
| Top-winner robustness | **NO** — top-3 removal negative |
| Cost-robust | **WEAK** — cost drag 60.2% of gross |
| Applicability boundary validated | **NO** — no pre-observable boundary separates applicable from non-applicable states |
| Live-safe foundation ready | **PARTIAL** — live-safe foundation has been substantially completed, but no strategy candidate exists |

VEI is not a runtime candidate and not a small-live candidate. The
small-live readiness gate remains unmet.

---

## 7. Prohibited Follow-Ups

Per VEI-002 failure closure and VEI-003 Section 8.3, the following are
prohibited:

| # | Prohibited | Rationale |
|---|-----------|-----------|
| P1 | Expansion threshold variants (K) | Parameter rescue |
| P2 | Lookback period variants (N) | Parameter rescue |
| P3 | Close-location variants (P) | Parameter rescue |
| P4 | EMA period variants | Parameter rescue |
| P5 | Slope lookback variants | Parameter rescue |
| P6 | Direction A breakout rescue | Old-path drift |
| P7 | Direction C re-expansion rescue | Old-path drift |
| P8 | Pullback-entry rescue | Concept was non-pullback |
| P9 | 1h/15m timing search | Timeframe scope creep |
| P10 | Funding/OI rescue | Different hypothesis |
| P11 | Short-side mirror | Different direction scope |
| P12 | Router/portfolio/regime | Infrastructure |
| P13 | Confirmation rule variants | Lifecycle rescue |
| P14 | Exit rule variants | Lifecycle rescue |
| P15 | Stop rule variants | Lifecycle rescue |
| P16 | Holding period variants | Lifecycle rescue |

---

## 8. Non-Pullback Pipeline Status

### 8.1 Exhaustion Statement

The non-pullback immediate candidate queue from SRD-002 is now exhausted.

| Rank | Direction | Status |
|------|-----------|--------|
| 1 (was VEI) | Volatility expansion / impulse participation | **PAUSE_FRAGILE** |
| 2 (was short-side) | Short-side breakdown continuation | **REJECTED_FROZEN_BASELINE** (SSD-003) |

No immediate non-pullback candidate remains in the queue. Ranks 3-7
(trend persistence, range/mean-reversion, exhaustion map, funding/OI,
cross-timeframe) are backlog or docs-only.

### 8.2 What This Does NOT Mean

- This does NOT permanently close all non-pullback research.
- This does NOT mean no new direction can ever be proposed.
- It means the current ranked queue is empty after inspection.
- Future non-pullback work requires a new Strategy Research Direction Refresh
  or a new Owner-approved Level 1/2 inspect with a clearly different mechanism.

---

## 9. Next Steps

### 9.1 What Should NOT Happen

| Action | Why Not |
|--------|---------|
| VEI variants (expansion, lookback, CLV, EMA, holding, ATR) | Parameter rescue of paused concept |
| VEI Direction A rescue | Old-path drift |
| VEI Direction C rescue | Old-path drift |
| 1h/15m timing rescue for VEI | Timeframe scope creep |
| Funding/OI rescue for VEI | Different hypothesis |
| Auto-promoting backlog ranks 3-7 | No immediate queue promotion without inspect |
| Starting a new Level 3 from VEI | VEI-003 result is PAUSE_FRAGILE; not Level 3 eligible |

### 9.2 What Could Happen

| Option | Description | Authorization |
|--------|-------------|---------------|
| Strategy Research Reset | New Level 1/2 inspect to search for genuinely different mechanisms; could be non-pullback, pullback-continuation, or new family | Level 1/2 docs-only |
| Direction Refresh | Like SRD-001/SRD-002 but starting from current evidence state including VEI-003 | Level 1/2 docs-only |
| Methodology Review | Review whether OHLCV-only 4h ETH has exhausted its hypothesis space | Level 1/2 docs-only |
| Applicability-Boundary Review | Review whether the applicability boundary question itself needs reframing | Level 1/2 docs-only |
| Pause All Strategy Research | Preserve all evidence while focusing on live-safe infrastructure | Level 1/2 decision |

### 9.3 Recommendation

**Do not auto-derive new experiments from VEI-003.** The correct next step,
if strategy research continues, is a new Strategy Research Reset or Direction
Refresh that starts from the full evidence state (Direction A PAUSE_FRAGILE,
Direction C INSUFFICIENT_EVIDENCE, Direction D REJECTED, SSD-003 REJECTED,
VEI PAUSE_FRAGILE, CPM-1 paused).

This reset should ask whether the hypothesis space itself needs reframing
rather than continuing to generate Level 3 candidates from the same
OHLCV-only 4h framework.

---

## 10. Owner Summary

### 1. VEI-003 Final Classification

**PAUSE_FRAGILE.** 118 trades, net +630.49, PF 1.21. Overlap gates passed
(Direction A 27.1%, Direction C 2.5%). But independent signals are net
negative (-329.02, PF 0.86). All positive PnL comes from 33 signals
overlapping Direction A. Top-3 removal is -286.85.

### 2. Positive Evidence

- Overall net positive (+630.49), PF > 1 (1.21).
- 118 trades, 56 winners — floors met.
- Direction A / C overlap gates passed — mechanism is structurally distinct.
- Follow-through filter removes 49% false starts.
- 2022-2025 all positive; 2021 only slightly negative (-70.09).
- Top-N fragility less severe in absolute terms than Direction A or C.

### 3. Negative Evidence

- Independent (non-overlapping) signals: net -329.02, PF 0.86.
- All positive PnL from 33 Direction A-overlapping signals.
- Top-3 removal turns system negative.
- 88% time-exit; 90% hold for full 5 bars — fixed-hold exit, not energy capture.
- Cost drag 60.2% of gross.
- VEI does not prove an independent bar-level impulse profit source.

### 4. Why Not Runtime / Small-Live

- Independent alpha not demonstrated.
- Top-winner robustness not demonstrated.
- No pre-observable applicability boundary.
- Live-safe foundation substantially completed, but no strategy candidate exists.
- Small-live readiness gate remains unmet.

### 5. Non-Pullback Pipeline Exhausted?

**Yes.** SRD-002 Rank 1 (VEI) inspected and paused. Rank 2 (short-side)
closed by SSD-003/SSD-004. No immediate non-pullback candidate remains.
Ranks 3-7 are backlog.

### 6. Next Step Recommendation

**Strategy Research Reset** (new Level 1/2 direction refresh), not continued
Level 3 from VEI. The reset should start from the full evidence state and
ask whether the hypothesis space needs reframing. Do not auto-derive VEI
variants or promote backlog candidates without fresh inspect.

---

## Appendix A: Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | VEI-004 archive document created | Claude |
| 2026-05-07 | SMA-001 updated with VEI row | Claude |
| 2026-05-07 | SRD-002 updated with VEI PAUSE_FRAGILE | Claude |
| 2026-05-07 | live-safe-v1-task-board updated with VEI-003/VEI-004 | Claude |
| 2026-05-07 | VEI-001 stale live-safe phrasing corrected | Claude |
