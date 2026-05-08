# VEI-002: Volatility Expansion / Impulse Participation Frozen Experiment Plan

**Task ID:** VEI-002
**Level:** 2 docs-only frozen experiment plan
**Date:** 2026-05-07
**Status:** COMPLETE
**Classification:** RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER
**Upstream:** VEI-001 (MARGINAL — conditional RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN)

---

## 0. Upstream State Note

VEI-001 used the phrase "Live-safe P0: 2/7 complete" in its upstream state summary. The current accurate framing is: **live-safe foundation has been substantially completed** (LS-001, LS-002 merged; LS-107, LS-108 merged; decision trace backbone done; ADR-0002 done). However, live-safe foundation completion does not equal strategy readiness. No runtime candidate exists, no deployable small-live strategy exists, and the small-live readiness gate remains unmet.

---

## 1. Frozen Concept Summary

### One Sentence

VEI is a long-only, 4h OHLCV-only strategy that enters when a bar shows volatility expansion with directional close control and the next bar confirms directional continuation, then exits after a fixed 5-bar holding window or ATR-based protective stop, whichever comes first.

### Profit Source Hypothesis

Participate in the directional continuation phase that follows a high-energy impulse bar. The impulse bar signals a regime shift in directional energy; the follow-through confirmation filters exhaustion spikes; the fixed 5-bar holding window captures the continuation window before impulse energy decays.

### What This Is Not

| Concept | Why VEI Is Not This |
|---------|-------------------|
| Direction A rescue | VEI does not use Donchian channels or price-level extreme breakout. |
| Direction C rescue | VEI does not require a prior ATR contraction phase. |
| Direction D / pullback-continuation | No value-zone touch, no EMA reclaim, no pullback-ending detection. |
| CPM rescue | No Pinbar, no 1h, no fixed TP geometry, no pullback-ending question. |
| CPM-MOD-002 variant | VEI does not gate a module; it is a standalone entry+exit concept. |

---

## 2. Frozen Direction Scope

| Element | Frozen Value |
|---------|-------------|
| Direction | **Long-only** |
| Short-side | Not authorized; requires separate inspect |
| Two-sided | Not authorized; requires router/regime (forbidden) |
| Router / regime / portfolio | Not in scope |

---

## 3. Frozen Timeframe Scope

| Element | Frozen Value |
|---------|-------------|
| Primary timeframe | **4h closed OHLCV** |
| 1h entry timing | Not used |
| 15m | Not in scope |
| Data source | v3_dev.db klines table, 2020-01-01 through 2026-03-31 |
| Funding / OI / liquidation / orderbook | Not used; constant funding approximation caveat only |

---

## 4. Frozen Entry: Impulse State Detection

### 4.1 Impulse Bar Definition (Long)

An impulse bar is a fully closed 4h candle satisfying ALL of:

| Condition | Formula | Rationale |
|-----------|---------|-----------|
| Range expansion | `(High - Low) > 1.5 × SMA(High - Low, 20)` | Bar range must significantly exceed the 20-bar rolling average range. Uses SMA of bar ranges, NOT ATR (which includes prior close). The 1.5x threshold is moderate — high enough to filter normal bars, low enough to generate a viable signal count. |
| Close-location control | `Close >= Low + 0.75 × (High - Low)` | Close must be in the top 25% of the bar, indicating that buyers maintained directional control into the close. Rejects bars where price spiked but reversed into the close (exhaustion signature). |
| Trend filter | `Close > EMA60 AND EMA60[0] > EMA60[5]` | Price above EMA60 prevents counter-trend impulse entries. EMA60 slope positive (current > 5 bars ago) prevents entries during trend rollover. Minimal — does not define trend structure, only baseline direction. |

### 4.2 Prohibited Entry Components

| Prohibited | Rationale |
|-----------|-----------|
| Donchian channel | Direction A trigger; not allowed |
| ATR ratio contraction | Direction C precondition; not allowed |
| Pullback / value-zone touch | Direction D / CPM trigger; not allowed |
| Pinbar / wick rejection | CPM trigger; not allowed |
| EMA20 reclaim | Direction D confirmation; not allowed |
| Breakdown / support level | SSD-003 trigger; not allowed |

### 4.3 Parameters (All Frozen)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Expansion multiplier (K) | **1.5** | Moderate: filters ~80-90% of bars while remaining sensitive to genuine expansion. Not a threshold sweep candidate. |
| Rolling lookback (N) | **20 bars (80h)** | Matches Direction A's Donchian20 period at the lookback level (not the trigger level). Provides stable average range estimate. |
| Close-location threshold (P) | **0.75** | Top 25% of bar. Strict enough to reject exhaustion wicks, loose enough to include bars with modest lower shadows. |
| Trend EMA period | **60 bars (240h)** | Matches Direction A/C EMA60 for consistency. Enables direct overlap measurement. |
| Slope lookback | **5 bars (20h)** | Short enough to detect recent rollover, long enough to avoid noise from single-bar EMA fluctuations. |

### 4.4 Parameter Count

**5 frozen parameters** (K, N, P, EMA period, slope lookback). No alternatives, no variants, no sweep.

---

## 5. Frozen Follow-Through Confirmation

### 5.1 Definition

After a fully closed impulse bar at time T, the follow-through confirmation bar at time T+1 must satisfy:

```
Close[T+1] > Close[T]
```

The follow-through bar's close must exceed the impulse bar's close.

### 5.2 Why Follow-Through Is a Natural Component (Not Post-Hoc Filter)

Follow-through is intrinsic to the impulse participation hypothesis, not an afterthought:

1. **The hypothesis is "impulse continuation," not "impulse occurrence."** A single impulse bar may be exhaustion (spike + reversal) or continuation (breakout + follow-through). The distinction between these two states is whether the next bar confirms or negates the directional move.

2. **Without follow-through, the concept degenerates to "trade big bars."** Trading all large-range bars is a noise-trading strategy. The follow-through requirement is what makes the concept about *participation in continuation* rather than *reaction to volatility*.

3. **Follow-through is computable before entry.** The confirmation bar must be fully closed before entry is considered. No lookahead.

4. **One confirmation rule, no alternatives.** No multi-bar confirmation, no percentage-threshold confirmation, no volume confirmation. Close[T+1] > Close[T] is the sole rule.

### 5.3 Cooldown After Follow-Through

If the follow-through bar at T+1 is itself an impulse bar (satisfies Section 4.1 conditions), it is eligible to become the impulse bar for a new signal. The follow-through bar for this new signal would be at T+2.

This is NOT a parameter; it is the natural consequence of the rule that every impulse bar must independently satisfy all conditions.

---

## 6. Frozen Entry Timing

| Element | Frozen Value |
|---------|-------------|
| Signal bar | Impulse bar at T must be **fully closed** |
| Confirmation bar | Follow-through bar at T+1 must be **fully closed** |
| Entry | **Open of bar T+2** (next 4h open after confirmation bar closes) |
| Entry slippage | `entry_price = Open[T+2] × 1.001` |
| Signal-close lookahead | **Prohibited.** Entry never occurs on the impulse bar or confirmation bar. |

### Timeline

```
T:     Impulse bar closes (fully closed, satisfies Section 4.1)
T+1:   Follow-through bar closes (Close[T+1] > Close[T])
T+2:   Entry at Open[T+2] + slippage
```

**Confirmation lag: 1 bar (4h) after follow-through bar closes.** Total lag from impulse event to entry: 2 bars (8h).

---

## 7. Frozen Exit Lifecycle

### 7.1 Exit Components

| Component | Rule | Execution |
|-----------|------|-----------|
| **Maximum holding period** | **5 bars (20h)** from entry | At bar T+7 close (5 bars after entry at T+2): exit at **Open[T+8] + exit slippage** |
| **Protective stop** | **2 × ATR14** below entry price | If any bar's Low ≤ stop level: exit at **stop level + exit slippage** |

### 7.2 Exit Logic (First-Trigger Wins)

```
For each bar after entry:
  1. Check stop: if Low ≤ entry_price - 2 × ATR14:
       exit at stop_level (with exit slippage)
  2. Check time: if this is the 5th bar after entry:
       exit at next bar's open (with exit slippage)
  3. If neither triggers, continue holding
```

### 7.3 Why This Exit Serves the Impulse Hypothesis

| Element | Impulse Hypothesis Alignment |
|---------|----------------------------|
| **5-bar max hold** | Impulse energy is short-lived. The continuation window after a volatility expansion is typically 1-5 bars (20h). Holding longer captures trend, not impulse. A fixed hold tests whether impulse continuation has a natural time boundary. |
| **ATR14 stop** | Limits downside when the impulse fails (exhaustion, reversal). ATR14 adapts to current volatility — tight in low-vol, loose in high-vol. Matches the bar-level energy detection philosophy. |
| **No EMA60 exit** | Using EMA60 lifecycle exit would make VEI a trend-following strategy with impulse entry, not an impulse participation strategy. The exit must match the entry's time horizon. |
| **No trailing stop** | Trailing introduces path-dependency and parameter choice (trail distance, activation level). The fixed hold + protective stop is a cleaner test of the hypothesis. |

### 7.4 What This Exit Does NOT Do

- Does not use EMA60 close-break (that is Direction A/C exit logic).
- Does not use trailing stop or breakeven stop (introduces path-dependency).
- Does not use fixed TP geometry (CPM-style).
- Does not use support-level reclaim (SSD-003-style).
- Does not hold indefinitely until a trend indicator fires.

### 7.5 ATR14 Calculation

ATR14 is computed at the **impulse bar** (time T), using the standard 14-period Wilder ATR formula on 4h bars. The stop level is fixed at entry and does not update.

```
stop_level = entry_price - 2 × ATR14[T]
```

This is an **initial stop**, not a trailing stop. It does not move.

---

## 8. Frozen Same-Bar / Next-Bar Policy

### 8.1 Conflict Definition

A "same-bar conflict" occurs when the protective stop is triggered on the **entry bar** itself (the bar whose open is used for entry). This means the market moved against the position immediately.

### 8.2 Resolution: Pessimistic Policy

| Conflict Type | Resolution |
|--------------|------------|
| Stop triggered on entry bar | **Stop wins.** Exit at stop level. |
| Stop triggered on same bar as time exit | **Stop wins.** |
| Both stop and time exit on same bar | **Stop wins.** |

The pessimistic policy ensures that the experiment does not benefit from optimistic intrabar ordering.

### 8.3 Reporting Requirement

If Level 3 is authorized, the following must be reported:
- Count of same-bar stop-on-entry conflicts.
- Count of trades where stop triggered within 1 bar of entry (<8h hold).
- Percentage of total trades affected by same-bar conflicts.

---

## 9. Frozen Cost Model

Identical to all prior frozen experiments (MTC-004, MTC-006, SSD-003):

| Parameter | Value | Notes |
|-----------|-------|-------|
| Fee rate | **0.04% per side (0.0004)** | Applied on entry and exit |
| Entry slippage | **0.10% (0.001)** | `entry_price = raw_open × 1.001` |
| Exit slippage | **0.10% (0.001)** | `exit_price = raw_exit × 0.999` (stop/TP); `exit_price = raw_open × 0.999` (time exit) |
| Funding rate | **0.01% per 8h (0.0001)** | Constant approximation; applied proportionally to holding time |
| Initial balance | **10,000 USDT** | |
| Risk fraction | **1% of current realized equity** | Per trade |
| Max exposure | **2.0x** | |

### 9.1 Cost Drag Formula

```
total_cost_per_trade = entry_fee + exit_fee + entry_slippage + exit_slippage + funding
                     = 0.0004 × notional + 0.0004 × notional + 0.001 × notional + 0.001 × notional + 0.0001 × notional × (hold_bars / 2)
```

Where `hold_bars` is the number of 4h bars held (1-5), and each 2 bars = 8h = one funding period.

### 9.2 Funding Caveat

Funding is a constant approximation. Real funding rates vary and can be negative (long receives). If funding constitutes >15% of gross PnL, the evidence must be flagged as funding-dependent and downgraded.

---

## 10. Frozen Overlap Gates

### 10.1 Purpose

Overlap gates determine whether VEI produces a **structurally distinct signal set** from existing directions. They are defined here but can only be measured during a future Owner-approved Level 3 run.

### 10.2 Direction A Overlap Gate

| Element | Frozen Value |
|---------|-------------|
| Reference signals | Direction A frozen baseline signal set (from MTC-002 or equivalent) |
| Matching method | Timestamp-based: signal at bar T matches if Direction A also has a signal at T, T-1, or T+1 |
| Timestamp tolerance | **±1 bar (4h)** |
| Overlap ratio | `(VEI signals matching Direction A) / (total VEI signals)` |
| **Threshold** | **If overlap ratio ≥ 50%: classify as "Direction A partial variant" and STOP** |

### 10.3 Direction C Overlap Gate

| Element | Frozen Value |
|---------|-------------|
| Reference signals | Direction C frozen baseline signal set (from MTC-004) |
| Matching method | Timestamp-based: same as Direction A gate |
| Timestamp tolerance | **±1 bar (4h)** |
| Overlap ratio | `(VEI signals matching Direction C) / (total VEI signals)` |
| **Threshold** | **If overlap ratio ≥ 50%: classify as "Direction C partial variant" and STOP** |

### 10.4 Additional Overlap Checks (Reported, Not Gating)

| Check | Method |
|-------|--------|
| CPM-1 overlap | Timestamp match ±1 bar; reported but not gating |
| Direction D overlap | Timestamp match ±1 bar; reported but not gating |
| SSD-003 overlap | Timestamp match ±1 bar; reported but not gating |
| Top-5 winner overlap with Direction A | Identify VEI's top-5 winners; check how many overlap with Direction A's top-5 winners |
| Top-5 winner overlap with Direction C | Same method |
| Independent signal performance | VEI signals with NO Direction A or C overlap; report separate PnL/PF/win-rate |

### 10.5 What Happens If Overlap Gates Fail

If VEI is reclassified as Direction A partial variant OR Direction C partial variant:
- VEI is classified as **REJECT_AS_OLD_PATH_DRIFT**.
- No rescue variants are permitted (see Section 13).
- The hypothesis "bar-level impulse detection is a distinct profit source" is closed.

---

## 11. Frozen Required Level 3 Metrics

If Owner authorizes VEI-003, the following metrics must be reported:

### 11.1 Primary Metrics

| Metric | Definition |
|--------|-----------|
| Net PnL | Total PnL after all costs |
| Profit Factor (PF) | Gross winners / abs(gross losers) |
| Win rate | Winners / total trades |
| Trade count | Total executed trades |
| Winner count | Trades with net PnL > 0 |
| Realized MaxDD | Maximum peak-to-trough drawdown on realized equity |
| MTM MaxDD | Maximum peak-to-trough drawdown on mark-to-market equity |

### 11.2 Fragility Metrics

| Metric | Definition |
|--------|-----------|
| Top-1 removal | Net PnL excluding the single largest winner |
| Top-3 removal | Net PnL excluding top-3 winners |
| Top-5 removal | Net PnL excluding top-5 winners |
| Top winner contribution | Top-1 winner as % of gross winners |

### 11.3 Year-by-Year Breakdown

Per year (2021, 2022, 2023, 2024, 2025): Net PnL, PF, trade count, winner count, realized MaxDD.

### 11.4 Trade-Level Diagnostics

| Metric | Definition |
|--------|-----------|
| MFE | Mean Favorable Excursion per trade |
| MAE | Mean Adverse Excursion per trade |
| Giveback | Mean (MFE - realized PnL) per trade |
| Average holding time | Mean bars held (expected: 1-5) |
| Stop hit rate | % of trades exited by protective stop vs. time exit |
| Same-bar conflict count | Trades where stop triggered on entry bar |

### 11.5 Cost Analysis

| Metric | Definition |
|--------|-----------|
| Gross PnL | PnL before costs |
| Total cost drag | Gross PnL - Net PnL |
| Cost as % of gross | Total cost drag / abs(gross PnL) |
| Funding as % of gross | Funding component / abs(gross PnL) |

### 11.6 Overlap Metrics

| Metric | Definition |
|--------|-----------|
| Direction A overlap ratio | % of VEI signals matching Direction A (±1 bar) |
| Direction C overlap ratio | % of VEI signals matching Direction C (±1 bar) |
| CPM-1 overlap ratio | % matching CPM-1 |
| Direction D overlap ratio | % matching Direction D |
| Top-5 winner overlap | VEI top-5 vs Direction A top-5, Direction C top-5 |
| Independent signal count | VEI signals with no Direction A or C overlap |
| Independent signal PnL | Net PnL of independent signals only |

### 11.7 Exhaustion Diagnostics

| Metric | Definition |
|--------|-----------|
| Failed impulse count | Impulse bars where follow-through bar fails (Close[T+1] ≤ Close[T]) |
| Failed impulse rate | Failed / total impulse bars |
| Exhaustion stop count | Trades exited by stop within 1 bar of entry |
| Stop-on-entry-bar count | Same-bar conflicts (pessimistic resolution) |
| Impulse bar range distribution | P25/P50/P75 of impulse bar range as multiple of avg range |

---

## 12. Frozen Failure Closure

### 12.1 Hypotheses That Close If Level 3 Fails

| # | Hypothesis | Closes When |
|---|-----------|-------------|
| H1 | Bar-level impulse detection is a distinct profit source from Direction A price-level breakout | Direction A overlap ≥ 50%, OR independent signals net negative |
| H2 | Volatility expansion without contraction precondition is structurally different from Direction C | Direction C overlap ≥ 50%, OR same failure pattern (thin evidence + concentration) |
| H3 | OHLCV-only impulse + follow-through can distinguish continuation from exhaustion | Net PnL negative due to exhaustion stops, OR follow-through filter does not improve win rate vs. raw impulse bars |
| H4 | Impulse participation has lower top-winner fragility than existing directions | Top-1 > 60% of gross winners, OR top-3 removal turns net negative |
| H5 | Fixed-hold exit matches impulse energy decay | Average hold < 1 bar (enter-and-stop same bar), OR average hold = 5 bars with majority at stop (hold too short) |

### 12.2 What Level 3 Failure Contributes to the Meta-Hypothesis

If VEI fails, it adds to the evidence for the meta-hypothesis from SR-001: "No OHLCV-only strategy module on ETH 4h has a validated, pre-observable applicability boundary that survives enough trades, enough winners, top-winner fragility, year concentration, and realistic costs."

Combined with Direction A (PAUSE_FRAGILE), Direction C (INSUFFICIENT_EVIDENCE), Direction D (REJECTED), and SSD-003 (REJECTED), VEI failure would close the last non-pullback, non-old-rescue direction in the current research pipeline.

---

## 13. Prohibited Failure Follow-Ups

If VEI-003 Level 3 fails, the following are **permanently prohibited**:

| # | Prohibited Follow-Up | Rationale |
|---|---------------------|-----------|
| P1 | Expansion threshold variants (K = 1.3, 1.7, 2.0, ...) | Parameter rescue of failed concept |
| P2 | Lookback period variants (N = 10, 15, 30, ...) | Parameter rescue |
| P3 | Close-location variants (P = 0.60, 0.70, 0.80, ...) | Parameter rescue |
| P4 | Trend EMA period sweep (EMA20, EMA40, EMA100, ...) | Parameter rescue |
| P5 | Slope lookback variants | Parameter rescue |
| P6 | Direction A breakout rescue (add Donchian back) | Old-path drift; concept was supposed to be distinct |
| P7 | Direction C re-expansion rescue (add contraction precondition) | Old-path drift |
| P8 | Pullback-entry rescue (add EMA zone / pullback detection) | Concept was explicitly non-pullback |
| P9 | 1h / 15m entry timing search | Timeframe scope creep; LTF-001/002 constraints |
| P10 | Funding / OI rescue | Different hypothesis; requires separate BACKLOG_DATA_DEPENDENT authorization |
| P11 | Short-side mirror | Different direction scope; requires separate inspect |
| P12 | Router / portfolio / regime | Infrastructure, not strategy |
| P13 | Multi-bar confirmation variants | Parameter rescue of confirmation rule |
| P14 | Trailing stop / breakeven variants | Exit lifecycle rescue |
| P15 | ATR multiplier variants (1x, 1.5x, 3x stop) | Stop geometry rescue |
| P16 | Holding period variants (3, 7, 10 bars) | Exit lifecycle rescue |

---

## 14. Structural Comparison With Prior Directions

### 14.1 Entry Mechanism

| Dimension | Direction A | Direction C | Direction D | VEI |
|-----------|------------|------------|------------|-----|
| Trigger | Donchian20 high breakout | ATR ratio < 0.7 → > 1.2x | EMA60 touch + EMA20 reclaim | Range > 1.5×avg + CLV ≥ 0.75 + follow-through |
| Object | Price-level (channel extreme) | Ratio-level (volatility state) | Zone-level (EMA touch) | Bar-level (energy detection) |
| Trend filter | EMA60 | EMA60 | EMA60 (implicit via zone) | EMA60 + slope |
| Confirmation | None | None (re-expansion IS confirmation) | EMA20 reclaim | Next bar close > impulse close |
| Pullback component | No | No | Yes | No |

### 14.2 Exit Mechanism

| Dimension | Direction A | Direction C | Direction D | VEI |
|-----------|------------|------------|------------|-----|
| Lifecycle exit | EMA60 close-break | EMA60 close-break | EMA60 close-break | **5-bar fixed hold** |
| Stop | Swing low (6-bar) | Swing low (6-bar) | Swing low (6-bar) | **2×ATR14 initial stop** |
| Maximum hold | Indefinite (until EMA break) | Indefinite | Indefinite | **5 bars (20h)** |
| Trailing | No | No | No | No |

**Key distinction:** VEI uses a time-bounded exit (5-bar max hold) instead of an EMA lifecycle exit. This makes VEI fundamentally a short-duration impulse capture, not a trend-following strategy. The hypothesis is that impulse energy has a natural time boundary (~20h on 4h), and holding longer captures trend noise, not impulse continuation.

### 14.3 Stop Mechanism

| Dimension | Direction A/C/D | VEI |
|-----------|----------------|-----|
| Type | Swing low (lowest low of prior N bars) | ATR-distance from entry |
| Adaptivity | Fixed lookback; adapts only to recent swing levels | Adapts to current volatility via ATR14 |
| Distance | Variable (depends on swing depth) | Fixed formula: 2×ATR14 |
| Rationale | Structural invalidation (price breaks below recent support) | Volatility-based invalidation (impulse failed if price drops 2×ATR from entry) |

VEI's ATR-based stop is structurally different from the swing-low stop used in all prior directions. It tests whether volatility-adapted risk management better suits impulse capture than structural support levels.

---

## 15. Frozen Signal Set Overlap Estimation (Pre-Run)

### 15.1 Qualitative Overlap Estimate

| Scenario | Direction A Signal? | VEI Signal? | Overlap? |
|----------|-------------------|-------------|----------|
| Strong bullish breakout to new 20-bar high on expanding range, close near high | Yes | Yes | OVERLAP |
| New 20-bar high on low-volatility drift, no range expansion | Yes | No | DISTINCT |
| Expanding range impulse bar NOT at 20-bar high (mid-range expansion) | No | Yes | DISTINCT |
| Impulse bar with exhaustion follow-through (close reverses) | N/A | No (filtered) | N/A |
| Counter-trend impulse in downtrend (price < EMA60) | No | No (filtered) | N/A |
| Impulse bar at 20-bar high with EMA60 slope negative | Yes | No (slope filter) | DISTINCT |

### 15.2 Estimated Overlap Range

**Direction A: 30-55%.** The overlap occurs when price breaks to a new high AND shows impulse expansion simultaneously. The non-overlap region (VEI signals where Direction A does not fire) depends on how many "mid-range expansion" signals exist.

**Direction C: 10-25%.** Lower overlap because Direction C requires a prior contraction phase. VEI fires on expansion from any baseline, including moderate-volatility baselines.

**These are pre-run estimates.** Actual overlap can only be measured in Level 3.

### 15.3 What Makes VEI Plausibly Distinct

1. **Different trigger object:** Bar-level energy (range + close location) vs. price-level extreme (Donchian) vs. ratio-level state (ATR).
2. **Follow-through requirement:** Neither Direction A nor Direction C has a confirmation bar.
3. **Time-bounded exit:** 5-bar max hold vs. indefinite EMA lifecycle exit.
4. **ATR-based stop:** vs. swing-low stop in all prior directions.
5. **No contraction precondition:** Unlike Direction C, VEI fires on expansion from any baseline, not only after contraction.

### 15.4 What Makes VEI Potentially Not Distinct

1. **Same trend neighborhood:** All signals require EMA60 uptrend — same market state as Direction A/C.
2. **Expanding-range overlap:** The strongest trending moves (new highs on expanding range) trigger both Direction A and VEI.
3. **Profit source is the same:** Both capture directional trend continuation.
4. **EMA60 trend filter is shared:** Direction A, C, and VEI all use EMA60 for trend context.

---

## 16. VEI-003 Authorization Request Checklist

If Owner considers authorizing VEI-003 Level 3 frozen run, the following pre-conditions from this plan must be verified:

| # | Pre-Condition | Status |
|---|--------------|--------|
| 1 | Entry impulse state fully frozen (Section 4) | Frozen in VEI-002 |
| 2 | Follow-through confirmation frozen (Section 5) | Frozen in VEI-002 |
| 3 | Entry timing frozen (Section 6) | Frozen in VEI-002 |
| 4 | Exit lifecycle frozen (Section 7) | Frozen in VEI-002 |
| 5 | Same-bar policy frozen (Section 8) | Frozen in VEI-002 |
| 6 | Cost model frozen (Section 9) | Frozen in VEI-002 |
| 7 | Overlap gates frozen (Section 10) | Frozen in VEI-002 |
| 8 | Required metrics defined (Section 11) | Frozen in VEI-002 |
| 9 | Failure closure defined (Section 12) | Frozen in VEI-002 |
| 10 | Prohibited follow-ups defined (Section 13) | Frozen in VEI-002 |
| 11 | No parameter sweep | Confirmed: 5 frozen parameters, no variants |
| 12 | OHLCV-only | Confirmed: no new data dependency |
| 13 | Long-only, 4h | Confirmed |
| 14 | No runtime/profile/risk/backtester-core changes | Confirmed |
| 15 | Cannot be interpreted as runtime or small-live approval | Confirmed |

---

## 17. Owner Summary

### 1. Frozen VEI Concept

Long-only, 4h OHLCV, bar-level impulse participation: enter when a 4h bar shows range expansion (1.5×20-bar average) with close-location control (upper 25%) and trend context (EMA60 positive slope), confirmed by a follow-through bar (next bar close > impulse bar close), entry at next-bar open, exit after 5-bar max hold or 2×ATR14 protective stop, whichever first.

### 2. Still Long-Only / 4h / OHLCV-Only?

**Yes.** Long-only, 4h closed OHLCV, no 1h/15m, no funding/OI/liquidation/orderbook.

### 3. Exit Lifecycle Frozen?

**Yes.** 5-bar fixed hold + 2×ATR14 initial protective stop. No EMA60 lifecycle exit (that is Direction A/C logic). No trailing stop. No breakeven. No variants.

### 4. Overlap Gates

**Direction A: signal overlap ≥ 50% → REJECT_AS_OLD_PATH_DRIFT, stop.**
**Direction C: signal overlap ≥ 50% → REJECT_AS_OLD_PATH_DRIFT, stop.**
Timestamp tolerance: ±1 bar (4h). Additional checks for CPM/Direction D/SSD-003 overlap, top-winner overlap, and independent signal performance are reported but not gating.

### 5. Biggest Old-Path Drift Risk

**Direction A variant.** Both VEI and Direction A capture bullish trend continuation on expanding-range bars. The overlap region (new high + expanding range + directional close) is the most profitable scenario for both. If this region dominates VEI's signal set, VEI is a Direction A variant with different trigger notation but identical profit source. The 50% overlap gate exists specifically to detect this.

### 6. Recommend Future Owner Level 3?

**Yes, with caveats.** This plan is complete and frozen. If Owner authorizes VEI-003, all parameters, gates, metrics, and failure closures are pre-defined. However:
- VEI is classified as MARGINAL (from VEI-001).
- Old-path drift risk is MEDIUM-HIGH.
- The concept is the last non-pullback candidate in the current pipeline.
- Level 3 authorization is a research decision, not a deployment decision.
- The result (pass or fail) changes the direction map but does not create a small-live candidate.

### 7. Small-Live Readiness Gate

**Still not met.** VEI-002 is a docs-only frozen plan. Even if VEI-003 runs and passes all gates:
- No exit lifecycle has been validated on live data.
- No pre-observable applicability boundary has been empirically confirmed.
- Live-safe foundation is substantially complete but P0 tasks remain incomplete.
- A single frozen-baseline result does not constitute small-live readiness.
- Multiple validation stages (OOS testing, walk-forward, stress testing) would be needed before any deployment consideration.

**VEI-002 does not change the project's deployment readiness.** It is a frozen research plan awaiting Owner authorization.
