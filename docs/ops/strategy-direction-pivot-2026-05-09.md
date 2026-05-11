# Strategy Direction Pivot — 2026-05-09

**Status:** Owner-confirmed strategic direction
**Date:** 2026-05-09
**Scope:** Strategy research methodology, architecture, and roadmap
**Supersedes:** SRB-001 regime-hypothesis-first approach (paused, not invalidated)
**Affects Runtime Automatically:** No

---

## 0. Summary

This document captures the strategic reasoning and conclusions from a
structured Owner–Claude consultation session on 2026-05-09. It should be
treated as the current single source of truth for strategy research direction.

**Core pivot:** From "build a fully automated OHLCV regime classifier" to
"human-gated strategy execution with LLM-assisted regime analysis."

**Core rationale:** Two rounds of exploratory observation (E0-001, E0-002)
proved that simple OHLCV statistical features cannot distinguish "healthy
trend" from "hostile volatility" in ETH 4h. The regime boundary that CPM-1
and Direction A lacked cannot be built from OHLCV alone. But it CAN be
provided by a human operator assisted by LLM analysis of multi-source
information.

---

## 1. What Was Tried and What It Proved

### 1.1 Full Automated Strategy Research (2024–2026)

Six frozen baselines were tested: CPM-1, Direction A, Direction C,
Direction D, SSD-003, VEI-003. All found some signal structure. None
produced a validated pre-observable applicability boundary.

**Common failure pattern:** Every strategy was entry-signal-first. None
defined "when NOT to trade" before defining "when to trade." The result was
strategies that worked in favorable periods but bled in unfavorable ones,
with no automated way to distinguish the two.

### 1.2 Regime-Hypothesis-First Approach (SRB-001)

SRB-001 proposed HTPA-1: Higher-Timeframe Trend Persistence with
Overextension Avoidance. The core idea was to define valid/invalid market
states using OHLCV features before designing an entry signal.

Codex inspect returned PROCEED_WITH_MODIFICATIONS. The hypothesis was
structurally sound but untested.

### 1.3 Exploratory Observations (E0 Series)

Two low-cost observations were run to test whether OHLCV features could
serve as regime discriminators:

**E0-001: EMA50 slope + ATR20 percentile**
- Result: WEAK
- EMA50 slope separates bull/bear direction but not "participation quality"
- ATR percentile does NOT follow "high = hostile" pattern:
  - 2021 Q1 (should-earn): ATR percentile 0.731 (high)
  - 2022 H1 (should-lose): ATR percentile 0.214 (low)
  - Both healthy trends and crashes can have high ATR

**E0-002: Directional Efficiency + EMA50 Cross Frequency**
- Result: WEAK
- Directional Efficiency did NOT distinguish healthy uptrend from hostile
  selloff. 2021 May-Jul (hostile) had HIGHER DE than 2021 Q1 (should-earn).
- EMA50 Cross Frequency was uninformative (median 0-1 across all periods)
- Direction A echo risk remained material

### 1.4 Combined E0 Conclusion

> Simple rolling-window OHLCV statistical features (slope, ATR, efficiency,
> cross count) can answer "which direction is the market moving" but cannot
> answer "is it safe to participate in this direction right now."

This is a real, valuable negative finding. It closes the path of building
a fully automated OHLCV-only regime classifier for ETH 4h trend strategies.

---

## 2. The "Why Not Just Buy Spot" Analysis

### 2.1 The Challenge

Direction A's best conservative scenario (A1) produces 4,324U over 5 years
(2.7% annualized) with 2.6% MaxDD. Over the same period, buying BTC spot
returns 201%, buying ETH spot returns 301%.

At first glance, Direction A looks pointless next to buy-and-hold.

### 2.2 The Risk-Scaling Argument (From Existing Docs)

The capital-efficiency comparison (docs/ops/direction-a-same-risk-capital-
efficiency-comparison.md) argues that when benchmarks are scaled to match
Direction A's 2.6% MaxDD, Direction A produces 14-53% more net.

This is mathematically correct but hides a practical reality: if you
allocate just 10% of your capital to ETH spot, your portfolio-level MaxDD
is ~2.6% and your 5-year return is 9,040U — more than double Direction A.

### 2.3 The Resolution: It Depends on Your Goal

**If the goal is wealth building:** Buy spot. Simple, zero complexity,
higher absolute return.

**If the goal is building quantitative trading capability:** Direction A
has value as a learning vehicle (execution integrity, reconciliation,
risk management), but not as a return generator.

**If the goal is outperforming spot during a bull cycle:** An active
strategy that captures multiple swing legs SHOULD beat buy-and-hold —
but only if the signal quality is high enough that re-entry costs don't
eat the advantage. Direction A's 70% loss rate means it's currently
paying too much in re-entry costs.

### 2.4 Owner Position

The Owner's goal is NOT 10-year all-weather performance. The goal is to
capture the next BTC bull cycle (2-3 years) using leveraged contracts to
outperform spot-hold. This changes the evaluation framework entirely:

- Strategies don't need to survive bear markets (just turn off)
- Strategies don't need to be profitable every year (just during bull)
- Regime identification can be human-provided (not algorithmic)
- The "vs spot" comparison should be within the bull window, not full-cycle

---

## 3. The Architecture Pivot

### 3.1 Old Architecture (Abandoned)

```
OHLCV data → Automated regime classifier → Automated entry signal → Execution
```

**Why it failed:** OHLCV regime classifier is not feasible (E0 proved this).
Building a non-OHLCV classifier (funding/OI/ML) requires massive additional
engineering with uncertain payoff.

### 3.2 New Architecture (Confirmed)

```
┌─────────────────────────────────────┐
│           Information Layer          │
│  Market data, news, on-chain,       │
│  funding, sentiment, macro          │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│         LLM Analysis Layer           │
│  Structured regime assessment        │
│  Devil's advocate / counter-bias     │
│  Risk event alerting                 │
│  Post-trade review                   │
│  DOES NOT make decisions             │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│      Human Decision Layer (Owner)    │
│  Reviews LLM analysis + own judgment │
│  Makes ONE decision: ON / OFF / SIZE │
│  Does NOT monitor every trade        │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│     Algorithmic Execution Layer      │
│  CPM signal detection + auto order   │
│  Risk management (kill switches)     │
│  Reconciliation                      │
│  Status reporting (Web UI / DingDing)│
│  (Already built)                     │
└─────────────────────────────────────┘
```

### 3.3 Why Each Layer Exists

| Layer | Does | Does NOT |
|---|---|---|
| LLM | Synthesize multi-source info; structured analysis; risk alerting; counter-bias argumentation | Predict prices; make on/off decisions; place orders |
| Human | Judge "is this a valid bull trend?"; set position size; decide on/off | Monitor every 4h bar; manually place orders; do reconciliation |
| Algorithm | Execute CPM signals; enforce kill switches; reconcile; report status | Judge market regime; decide whether to trade |

### 3.4 Why This Is NOT a CPM-1 Rescue

CPM-1 failed because it ran 24/7 without regime awareness. Human-gated
CPM is a fundamentally different architecture:

| Dimension | CPM-1 (failed) | Human-Gated CPM (proposed) |
|---|---|---|
| Regime decision | None (runs always) | Human + LLM (runs only when activated) |
| Operating window | All market conditions | Bull market segments only |
| Failure mode | Bleeds in hostile regimes | Human misjudgment (mitigated by LLM counter-bias + kill switches) |
| 2021 behavior | Ran through May crash, lost heavily | Human would have turned off in May; re-enabled when trend resumed |
| Evaluation period | Must pass all years | Only needs to work in bull segments |

---

## 4. What Has Already Been Built (Asset Map)

| Component | Status | Role in New Architecture |
|---|---|---|
| Execution engine (exchange gateway, order lifecycle) | Built | Algorithmic execution layer |
| Risk management (kill switches, DD limits, consecutive loss pause) | Built | Algorithmic execution layer |
| Reconciliation (startup, ongoing) | Built | Algorithmic execution layer |
| Web UI (runtime monitoring, research display) | Built | Status reporting |
| DingDing bot framework | Built | Alert delivery + LLM analysis delivery |
| CPM-1 signal logic | Exists (frozen) | Parked / weak candidate after CPM-BULL-SEG-001 |
| Direction A signal logic | Exists (frozen) | Alternative entry signal |
| 100+ docs in docs/ops/ | Exists | Evidence base (what works, what doesn't) |
| E0 negative evidence | Exists | Proves need for human regime layer |
| LLM analysis integration | **Not built** | Needs to be added |
| Human on/off control interface | **Not built** | Needs to be added |
| CPM exit logic improvement | **Not done** | Optional forensic diagnostic only after Owner choice |

---

## 5. CPM Signal Quality in Bull Segments — Checked

The most important checked question was: **Does CPM-1 actually work
within bull market segments?**

CPM-1 was rejected based on full-cycle results (2021-2025). But if the
human provides regime gating, the relevant question is different:

- CPM-1 in 2021 Q1 (Jan-Apr): positive or negative?
- CPM-1 in 2023 Q4 - 2024 Q1: positive or negative?
- CPM-1 in 2024 Q4 (if applicable): positive or negative?

If CPM-1 is net positive in these segments, human-gated CPM has data
support. If it's net negative even in these segments, the signal itself
needs redesign.

This was completed by CPM-BULL-SEG-001 using existing trade-level data,
without running new backtests.

### 5.1 CPM-BULL-SEG-001 Result — 2026-05-09

This question has now been checked using existing trade-level data in
`docs/ops/cpm-bull-segment-readonly-evidence-2026-05-09.md`.

Result: **WEAK / INCONCLUSIVE, leaning weak**.

Fixed segment evidence:

| Segment | Read | Evidence |
|---|---|---|
| 2021 Q1 | Negative | 24 positions, -459.92 USDT position-level PnL |
| 2021 Jan-Apr | Negative | 39 positions, -320.14 USDT position-level PnL |
| 2023 Q4 | Negative but too thin | 1 position |
| 2024 Q1 | Positive but thin | 7 positions |
| 2024 Q4 | Positive but very thin | 3 positions |

Interpretation:

- CPM-1 is **not validated** inside fixed bull segments.
- The strongest evidence is the official 2021 OOS bull-segment data, and
  both pre-declared 2021 windows are negative.
- The positive 2024 segments are thin and come from secondary diagnostic
  baseline artifacts, not official OOS artifacts.
- Human-gated + LLM-assisted + algorithmic execution remains a possible
  future architecture, but CPM-1 should no longer be treated as the default
  execution signal for that architecture.
- Exit-logic investigation is **WEAK_CONDITIONAL** only: optional forensic
  diagnosis, not a mainline path and not CPM validation.

---

## 6. Exit Logic — Optional Forensic Area

Direction A and CPM-1 share a core weakness: **exit too early, re-entry
too expensive.**

Analysis from this session identified three leaks:

1. **Late entry:** Donchian 20 breakout requires 20-period highs,
   missing early trend legs (~3 days on 4h)
2. **Sensitive exit:** EMA60 close-break exits during normal trend
   pullbacks, not just trend endings
3. **Expensive re-entry:** 70% of re-entries hit stop-loss. Each failed
   re-entry costs spread + slippage + stop-loss loss

For the "capture multiple swing legs" thesis to work, the exit may need to
be more tolerant of intra-trend noise. However, CPM-BULL-SEG-001 weakens
CPM-1 as the default execution signal, so exit work is no longer a mainline
next step. It is only an optional forensic diagnostic if the Owner explicitly
chooses to spend effort understanding why thin 2024 winners worked and why
2021 bull-window trades failed.

Possible diagnostic questions, if explicitly authorized:

- Wider trailing stop (ATR-based instead of EMA close-break)
- Longer EMA period for exit (not EMA60 but EMA100+)
- Time-based minimum hold (don't exit within N bars of entry)
- Structural exit (lower-low on higher timeframe, not single bar EMA breach)

**This is NOT a parameter sweep.** It's a structural change in exit
philosophy: from "exit on first sign of weakness" to "exit when the trend
is actually over." It is also **not CPM validation**, not runtime approval,
and not a trigger to proceed to paper, testnet, live, or LLM implementation.

---

## 7. LLM Analysis Layer — Design Notes

### 7.1 Regime Briefing (Daily/Weekly)

**Input to LLM:**
- BTC/ETH current price, weekly/daily EMA positions
- 7-day and 30-day return
- Funding rate average and percentile
- Fear & Greed Index
- Top 3-5 recent news headlines (manual or scraped)
- (Optional) Open Interest change, long/short ratio

**Prompt structure:**
1. What market phase is this? (early bull / mid bull / overheated / distribution / bear / accumulation)
2. Risk score for running long-only trend strategy: 1-5
3. Top 3 risks to current trend
4. If I'm currently running the selected strategy, should I consider
   turning off? Why?

### 7.2 Counter-Bias (On Demand)

When Owner wants to turn a selected strategy on or off, feed LLM the
Owner's reasoning and ask it to argue against. This fights confirmation
bias — the biggest risk for a solo discretionary trader.

### 7.3 Event Alerting (Automated)

Monitor for and push alerts on:
- Extreme funding rate (>0.1% or <-0.05%)
- Price drop >5% in 4h
- FOMC / CPI / major regulatory events
- Selected strategy consecutive stop-loss count >= 3

### 7.4 Post-Trade Review (Weekly)

Feed LLM the week's strategy trades and ask:
- Were these trades consistent with the current regime?
- Are there signs the regime is changing?
- Recommendation: continue / reduce size / consider shutdown

### 7.5 Implementation Path

The dingdingbot framework already supports bot messaging. The LLM layer
can be implemented as:
1. A scheduled job that fetches market data and calls LLM API
2. Results pushed to DingDing and/or displayed in web UI
3. On-demand counter-bias via chat command
4. Alert rules checked alongside the selected execution signal

This layer is not automatically approved by CPM-BULL-SEG-001. It remains a
possible architecture component after the execution signal candidate is
refreshed.

---

## 8. Roadmap

### Phase 0: Validate CPM in Bull Segments (Completed)

- Pull existing CPM-1 trade-level data
- Slice by "human-judged bull segments" (2021 Q1, 2023 Q4-2024 Q1, etc.)
- Answer: is CPM-1 net positive in these windows?
- Completed by CPM-BULL-SEG-001 on 2026-05-09
- Result: **WEAK / INCONCLUSIVE, leaning weak**
- Consequence: CPM-1 is parked / weak as the default execution signal for
  the human-gated architecture.
- This result does not automatically advance the roadmap to exit logic,
  LLM implementation, paper, testnet, or live work.

### Phase 1: Refresh Human-Gated Execution Signal Candidates

- Re-evaluate which frozen or candidate execution signal, if any, is suitable
  for a human-gated bull-cycle architecture.
- CPM-1 is no longer the default candidate.
- Direction A, CPM variants, or new candidate structures require separate
  evidence framing before implementation work.
- No runtime/profile/risk changes are implied.

### Phase 1b: Optional CPM Exit Forensic Diagnostic

- Optional only if Owner explicitly chooses to spend effort.
- Compare why 2024 thin winners worked and why 2021 bull-window trades failed.
- Not a mainline phase.
- Not CPM validation.
- Not a parameter sweep.
- Not exit logic implementation.
- Not a path to paper, testnet, live, or automatic LLM implementation.

### Phase 2: LLM Analysis Layer (2-3 weeks)

- Build regime briefing job on dingdingbot framework only after the execution
  signal candidate is refreshed and Owner approves implementation scope.
- Implement counter-bias prompt
- Implement basic event alerting
- Manual testing for 2-4 weeks (run briefings, see if they're useful)
- Effort: moderate engineering, uses existing infra

### Phase 3: Future Validation Track

- No paper/testnet/live step is approved by this pivot update.
- Any future validation track requires a refreshed signal candidate and
  separate Owner approval.
- Human controls on/off based on own judgment + LLM analysis
- Track PnL, regime decisions, LLM accuracy
- Build confidence in the hybrid system
- Effort: time, not engineering

### Phase 4: Future Capital Deployment Track

- No real-funds activation is approved.
- Any future capital deployment track requires separate approval after
  candidate signal validation.
- Algorithmic execution, human on/off control, and LLM review remain possible
  architecture components.
- Kill switches active (max DD, consecutive loss pause)
- LLM daily briefing and weekly review only if separately approved.

### Phase 5: Scale (Mid Bull)

- No scale step is approved by this document.
- Any scale rules would require separate evidence and Owner approval.
- LLM counter-bias becomes critical (fights FOMO)
- Strict shutdown conditions remain in force

### Phase 6: Exit (Late Bull / Bear Onset)

- No late-cycle exit process is approved by this document.
- Any future exit process requires a refreshed signal candidate and separate
  Owner approval.
- Pre-defined exit conditions (weekly EMA break, extreme funding, etc.)
- LLM provides persistent "why you should consider stopping" argumentation
- This is the hardest phase psychologically — the LLM's job is to keep
  you rational when everything feels like it'll go up forever

---

## 9. Relationship to Existing Governance

### What Remains Valid

- SRR-002 methodology standards apply IF a fully automated strategy is
  ever proposed again
- Kill switch specifications from live-safe-v1 apply to execution layer
- Reconciliation requirements apply unchanged
- Engineering quality standards (decimal, masking, domain purity) unchanged

### What Is Superseded

- SRB-001 (HTPA-1 regime-hypothesis-first) is PAUSED, not dead. If
  someone later wants to build a fully automated OHLCV regime classifier,
  SRB-001 is the starting point. But it's no longer the active research
  direction.
- The "10-point Level 3 admission gate" is designed for fully automated
  strategies. Human-gated strategies need different validation criteria
  if such a path is separately approved.
- CPM-1 work is no longer a default path. CPM-BULL-SEG-001 shows weak /
  inconclusive bull-segment evidence, so CPM-1 is parked as the execution
  signal for the human-gated architecture unless the Owner explicitly
  authorizes a bounded forensic diagnostic.

### What Is New

- Human-gated operation requires new governance: when can the human
  override kill switches? What happens if the human is unavailable?
  What if the human ignores LLM warnings?
- LLM analysis layer needs its own quality checks: is the briefing
  actually useful? Is the counter-bias too conservative or too aggressive?
- No paper, testnet, or live phase is approved by this document.

---

## 10. Closed Paths (Still Closed)

- No fully automated OHLCV regime classifier (E0 proved it doesn't work)
- No parameter sweep on CPM-1 entry rules
- No VEI, SSD-003, Direction C, Direction D revival
- No 15m pullback-entry rescue
- No router / portfolio / multi-strategy engine
- No strategy-return optimization for runtime profiles
- No paper/testnet/live or real-funds activation from this pivot update

---

## 11. Key Insights From This Session

1. **The governance framework became the biggest blocker.** 98 docs in
   docs/ops/, most about why things can't be done yet. The ratio of
   docs-to-experiments was too high. Research stalled because the cost
   of starting any investigation exceeded the cost of the investigation
   itself.

2. **OHLCV can tell you WHAT is happening, not WHETHER to participate.**
   EMA slope knows direction. ATR knows volatility. Neither knows whether
   the current trend is "participable" or "about to collapse." This is
   the fundamental limitation of OHLCV-only regime classification.

3. **The "why not buy spot" question reframes the entire project.**
   Direction A's 2.7% annualized return is not competitive with simple
   spot allocation at matched risk. The justification for active trading
   must be "capture more of the bull cycle than spot" — which requires
   multi-leg swing capture, not conservative trend-following.

4. **Human-in-the-loop is not a weakness.** For a solo operator targeting
   a 2-3 year bull cycle, human regime judgment + LLM analysis + algorithmic
   execution is more practical and potentially more effective than a fully
   automated system that doesn't yet exist.

5. **The engineering infrastructure IS the product.** Execution, risk,
   reconciliation, monitoring, alerting — these are exactly what a
   human-gated strategy needs. The year+ of engineering wasn't wasted;
   it built the execution layer for a hybrid system.

6. **CPM's failure includes regime blindness, but signal weakness remains
   material.** CPM-BULL-SEG-001 found that fixed 2021 bull segments were
   negative in official OOS evidence. Human-gated execution may still be a
   valid architecture, but CPM-1 should not be treated as the default signal
   for it.

---

## 12. Action Items

| # | Action | Owner | Effort | Dependency |
|---|---|---|---|---|
| 1 | Validate CPM-1 PnL in bull segments (existing data) — completed; result WEAK / INCONCLUSIVE | Owner + Codex | Done | None |
| 2 | Refresh human-gated execution signal candidates | Owner + Codex | TBD | #1 complete |
| 3 | Optional bounded forensic diagnostic: compare why 2024 thin winners worked and why 2021 bull-window trades failed | Owner + Codex | TBD | Explicit Owner choice |
| 4 | Design LLM regime briefing prompt and delivery | Owner + Codex | TBD | Refreshed signal candidate and explicit Owner approval |
| 5 | Implement LLM briefing in dingdingbot | Owner + Claude | TBD | #4 and explicit implementation approval |
| 6 | Build human on/off control in execution layer | Owner + Codex | TBD | Refreshed signal candidate and explicit Owner approval |

---

## 13. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-09 | Initial strategy direction pivot document | Owner + Claude |
