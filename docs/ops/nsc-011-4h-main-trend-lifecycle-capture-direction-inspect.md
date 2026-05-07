# NSC-011 — 4h Main Trend Lifecycle Capture Direction Inspect

**Task ID:** NSC-011
**Date:** 2026-05-06
**Status:** Proposed / Direction Inspect Only
**Scope:** Docs-only direction inspect
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a direction-level inspect only. It does not authorize
running experiments, implementing strategies, changing runtime profiles,
changing risk rules, modifying backtester / research engine core, or making
any promotion, small-live, or live deployment decision.

This task did not run backtests, write code, create adapters, implement
strategies, modify runtime, modify profiles, modify risk, or modify
backtester / research engine core.

Inspected material:

- `docs/ops/nsc-007-next-strategy-candidate-direction-inspect.md`
- `docs/ops/nsc-008-t1-lite-4h-first-main-trend-capture-minimal-experiment-plan.md`
- `docs/ops/nsc-010-t1a-thin-sample-fragility-closure-review.md`
- `docs/ops/strategy-candidate-direction-map-v1.md`
- `reports/nsc-009-t1a-4h-main-trend-capture/**`
- T1/T1-R historical evidence under `archive/**`

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; INSUFFICIENT_EVIDENCE_THIN_SAMPLE |
| T1-B | Reserve-only; not executed |
| Direction A | This inspect |
| Direction E | Pending companion inspect (NSC-012) |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. What NSC-011 Is And Is Not

NSC-011 defines Direction A: 4h Main Trend Lifecycle Capture.

**It is:**

- A direction-level inspect for the P0 candidate from the Strategy Candidate
  Direction Map v1;
- A structural analysis of what 4h main trend lifecycle capture means;
- A comparison of candidate structural dimensions (entry, exit, risk);
- A foundation for a future NSC-013 minimal experiment plan if the inspect
  concludes `PROCEED_TO_EXPERIMENT_PLAN`.

**It is not:**

- A rerun of T1-A;
- A T1-A parameter rescue;
- A Donchian / ATR / EMA / lookback sweep;
- An experiment authorization;
- A promotion conclusion;
- A small-live conclusion;
- A live deployment recommendation.

---

## 3. Lessons From NSC-009 / T1-A

T1-A was the first attempt at 4h main trend lifecycle capture. Its result
is direction evidence, not validation.

### 3.1 What T1-A Showed

| Evidence | Read |
| --- | --- |
| Standalone adapter was feasible | 4h main trend capture can be expressed without forbidden core/runtime changes |
| Gross PnL was positive | There is some trend signal in 4h ETH; the direction is not completely signal-free |
| Net PnL was positive (+368) | After the frozen cost model, the signal survived — but barely |
| PF 1.07 | Above 1.0 but thin; no margin for error |
| Hold duration was trend-like | Trades held beyond local intraday pops; evidence of trend lifecycle capture |
| 2023 and 2024 were positive | Directionally relevant given CPM weakness in those years |

### 3.2 What T1-A's Failure Teaches

| Failure | Lesson for Direction A |
| --- | --- |
| 2023+2024+2025 trade floor not met (54 vs 60) | 4h trend-following is low-frequency; the frozen entry rule may be too restrictive, or the exit may be cutting trends too early |
| Top-1 winner = 98.47% of net | Extreme concentration; the edge may depend on one captured trend, not structural trend capture ability |
| Net excluding top 3 winners = -663 | Most trades are losers or near-breakeven; the losing side is not being managed |
| 2022 and 2025 were negative | Bear year and choppy year costs; expected for LONG-only trend-following but the magnitude matters |
| ATR trailing gave back too much | T1-A's 3x ATR14 trailing stop may be too loose; trends may give back too much open profit before triggering |

### 3.3 What This Means For Direction A

Direction A is not a continuation of T1-A. It is a redefinition of the same
hypothesis with structural differences:

1. **Exit is the primary change.** T1-A used ATR trailing. Direction A should
   test a different exit hypothesis: EMA60 close-break exit as the primary
   trend-lifecycle exit.

2. **Entry may need adjustment.** T1-A's Donchian20 breakout produced 85
   trades over 5 years — enough for the total floor but not for the
   reference-period floor. Direction A should consider whether a less
   restrictive entry condition is needed, without doing a parameter sweep.

3. **Fragility must be addressed structurally.** The T1-A fragility was not
   just a parameter problem — it was a structural consequence of a trend
   strategy that captures too few main trends and gives back too much.
   Direction A must test whether a better exit reduces giveback and
   broadens the winner base.

---

## 4. Direction A — 4h Main Trend Lifecycle Capture

### 4.1 Strategy Hypothesis

> ETH 4h main trends can be captured by entering on structural trend
> confirmation and exiting when the trend structure breaks, as measured by
> a 4h EMA close-break exit. The strategy aims to capture the main segment
> of sustained ETH trends while accepting low win rate, sparse profits,
> profit giveback, and rare-winner dependence — provided the edge is
> structurally robust across years.

### 4.2 Structural Dimensions

Direction A has five structural dimensions. Each must be defined before an
experiment plan.

| Dimension | Role | Notes |
| --- | --- | --- |
| Main trend definition | What qualifies as a "main trend" | Determines when the strategy is active |
| Entry trigger | How the strategy enters the trend | Determines signal frequency and timing |
| Initial risk stop | How the strategy defines initial risk | Determines max loss per trade |
| Trend-lifecycle exit | How the strategy exits the trend | Determines profit capture and giveback |
| Position sizing / partial TP | Whether to scale out or hold full size | Determines winner shape |

Each dimension is inspected separately below.

---

## 5. Main Trend Definition Candidates

The main trend definition determines when the strategy considers a trend to
be in progress. This is the foundation of the entire approach.

### 5.1 Candidate Definitions

| # | Definition | Hypothesis | Structural Character |
| --- | --- | --- | --- |
| D1 | 4h EMA trend state | 4h close above EMA60 (or similar) qualifies a trend | Indicator-based; smooth; lags at trend start and end |
| D2 | 4h higher-high / higher-low structure | Consecutive higher highs and higher lows define a trend | Structure-based; adapts to price action; subjective in choppy markets |
| D3 | 4h Donchian breakout / continuation | 4h close above a Donchian channel high signals trend initiation | Breakout-based; early entry; prone to false breakouts |
| D4 | 4h volatility contraction then expansion | Narrow range followed by expansion signals trend start | Pattern-based; rare; potentially robust when it fires |
| D5 | 4h price above long-memory trend line / EMA zone | Price staying above a long EMA (e.g., EMA120) or EMA zone qualifies a trend | Very smooth; very lagging; captures only sustained trends |

### 5.2 Direction-level Comparison

| Dimension | D1 EMA Trend | D2 HH/HL Structure | D3 Donchian Breakout | D4 Vol Contraction | D5 Long-memory |
| --- | --- | --- | --- | --- | --- |
| Signal frequency | Moderate | Low-Moderate | Moderate | Low | Very low |
| Entry timing | Late (EMA lag) | Moderate (waits for structure) | Early (breakout) | Late (waits for expansion) | Very late |
| False signal rate | Low | Moderate | High | Low | Very low |
| Trend capture breadth | Good (holds through EMA trend) | Good (holds through structure) | Moderate (may exit on pullback) | Good | Excellent |
| Complexity | Low | Moderate | Low | Moderate | Low |
| Overfit risk | Low | Moderate (structure definition is tunable) | Low | High (contraction parameters) | Low |
| Sample size risk | Low | Moderate | Low | High | Low |

### 5.3 Inspect Conclusion — Main Trend Definition

**Recommended first-round direction:** D1 (4h EMA trend state) as the primary
trend qualifier, combined with D3-style entry trigger.

Rationale:

- D1 provides a clean, low-parameter trend filter that determines when the
  strategy is "in trend mode."
- D2 is worth testing as an alternative but has higher structural definition
  complexity.
- D3 was used in T1-A (Donchian20) and produced some signal. It is
  acceptable as an entry trigger but should not be the sole trend definition.
- D4 has high sample size risk and high overfit risk.
- D5 is too lagging; it would miss most trend initiations.

**The trend definition should be separated from the entry trigger.** The
trend definition answers "is there a trend?" The entry trigger answers
"when do I enter?" These are different questions and should use different
rules.

This separation was implicit in NSC-008 (T1-A used Donchian20 as both
trend definition and entry trigger). Direction A should make it explicit.

---

## 6. Entry Trigger Candidates

Once a trend is defined, the entry trigger determines when the strategy
enters.

### 6.1 Candidate Triggers

| # | Trigger | Hypothesis | Notes |
| --- | --- | --- | --- |
| T1 | Donchian breakout (close above previous N-bar high) | Trend confirmation through range expansion | Tested in T1-A (N=20); 85 trades over 5 years; workable |
| T2 | EMA cross / price-above-EMA confirmation | Trend confirmed when price crosses above a shorter EMA | Smooth; may lag |
| T3 | Structure break (close above previous swing high) | Trend confirmed when a structural resistance is broken | Adaptive; more subjective |
| T4 | Pullback-to-value-zone entry (wait for retrace after trend qualification) | Enter on a pullback within a confirmed trend, not on the breakout itself | Better price; fewer signals; drifts toward Direction B |
| T5 | Breakout + confirmation (breakout + follow-through bar) | Wait for the breakout bar plus one follow-through bar to reduce false breakouts | Reduces false signals; delays entry |

### 6.2 Direction-level Comparison

| Dimension | T1 Donchian | T2 EMA Cross | T3 Structure Break | T4 Pullback-to-Value | T5 Breakout+Confirm |
| --- | --- | --- | --- | --- | --- |
| Signal frequency | Moderate | Moderate | Low-Moderate | Low | Moderate |
| Entry price quality | Average (breakout level) | Average | Average | Good (retrace) | Below average (later entry) |
| False signal rate | Moderate | Low | Moderate | Low | Low |
| Complexity | Low | Low | Moderate | Moderate | Low |
| CPM drift risk | None | None | None | High (becomes pullback entry) | None |
| Sample size risk | Low | Low | Moderate | High | Low |

### 6.3 Inspect Conclusion — Entry Trigger

**Recommended first-round trigger:** T1 (Donchian breakout), consistent with
T1-A's entry mechanism.

Rationale:

- T1 was tested in T1-A and produced 85 trades. It is a known, low-parameter
  entry mechanism.
- T4 has high CPM drift risk — it could easily become a pullback entry
  strategy, which is Direction B, not Direction A.
- T5 is worth testing later but adds a parameter (confirmation bar count).
- T2 and T3 are alternatives for a second pass.

**First-round recommendation:** Keep T1 (Donchian breakout) as the entry
trigger. The primary change from T1-A is the exit, not the entry. This
isolates the effect of the exit hypothesis.

---

## 7. Initial Risk Stop Candidates

The initial risk stop defines the maximum loss per trade and the initial
position risk.

### 7.1 Candidate Stops

| # | Stop | Hypothesis | Notes |
| --- | --- | --- | --- |
| S1 | Previous N-bar 4h structure low | The trend is invalidated if price breaks below the recent swing low | Tested in T1-A (previous-20 low); adaptive to structure |
| S2 | ATR-based initial stop (e.g., 2x ATR below entry) | Risk is proportional to current volatility | Standard; not tested in T1-A |
| S3 | Fixed percentage below entry | Simple; does not adapt to volatility | Simple but crude |
| S4 | Donchian channel lower bound | The trend is invalidated if price breaks below the Donchian channel | Ties risk to the same channel as entry |

### 7.2 Inspect Conclusion — Initial Risk Stop

**Recommended first-round stop:** S1 (previous N-bar structure low),
consistent with T1-A.

Rationale:

- S1 was used in T1-A and is adaptive to market structure.
- S2 is an alternative for a second pass but introduces an ATR parameter.
- S3 is too crude for a trend-lifecycle strategy.
- S4 ties the risk to the entry mechanism, which could create correlated
  failure modes.

**First-round recommendation:** Keep S1. The primary change is the exit, not
the initial risk stop.

---

## 8. Trend-Lifecycle Exit Candidates — Main Focus

The exit is the primary structural change from T1-A. T1-A used ATR trailing
(3x ATR14, 1.5R activation). Direction A should test a different exit
hypothesis first.

### 8.1 Exit Family

| # | Exit | Type | Hypothesis | T1-A Status |
| --- | --- | --- | --- | --- |
| E1 | 4h EMA60 close-break exit | Trend-structure exit | When a fully closed 4h candle closes below EMA60, the trend is over or weakening. Exit. | **Not tested** — this is the primary new hypothesis |
| E2 | 4h ATR trailing | Volatility trailing | Trail stop at N×ATR from peak. | Tested in T1-A (3x ATR14). Showed concentration risk and giveback. |
| E3 | 4h structure-low trailing | Structure trailing | Trail stop below the most recent 4h swing low. | Not tested. |
| E4 | N-bar low break | Time-structure exit | Exit if price makes a new N-bar low. | Not tested. |
| E5 | Partial TP + runner | Hybrid | Take partial profit at 1R or 2R, let remainder run with trailing. | Not tested. Introduces TP-level parameter. |
| E6 | Hybrid: initial stop + trend-lifecycle exit | Combined | Use initial risk stop for early failure; use trend-lifecycle exit (E1, E3, or E4) for trend continuation. | Not tested. This is the recommended first-round structure. |

### 8.2 EMA60 Close-break Exit — Detailed Analysis

The EMA60 close-break exit is the primary trend-lifecycle exit hypothesis for
Direction A. It is **not** a T1-A ATR trailing parameter rescue.

#### 8.2.1 What It Is

A structural trend-invalidation exit. When a fully closed 4h candle closes
below the 4h EMA60, the trend is considered to be weakening or ending. The
strategy exits at the next 4h bar open.

#### 8.2.2 What It Is Not

- Not an ATR trailing parameter variant.
- Not a tighter ATR multiplier.
- Not a parameter rescue of T1-A's trailing stop.
- Not an intrabar touch exit — only a fully closed 4h candle counts.

#### 8.2.3 Why It May Work

- EMA60 on 4h is a widely-used trend filter. When price closes below it,
  the trend consensus has shifted.
- It adapts to volatility (EMA is smoother than SMA) without requiring an
  ATR parameter.
- It directly measures trend lifecycle: trend in progress while above EMA60,
  trend ended when below EMA60.
- It may reduce giveback compared to ATR trailing: ATR trailing gives back
  on volatility spikes, while EMA60 close-break holds through volatility
  spikes as long as the trend structure holds.

#### 8.2.4 Why It May Fail

- EMA60 is a lagging indicator. By the time price closes below it, a
  significant portion of the trend may have already been given back.
- In choppy, range-bound markets, price may oscillate around EMA60, creating
  repeated false exits and re-entries.
- EMA60 period is a parameter. Testing EMA60 specifically (vs EMA40, EMA80,
  etc.) is acceptable only as a frozen choice, not as a sweep.

#### 8.2.5 Required Convention

If EMA60 close-break exit is used in an experiment:

- **Signal:** A fully closed 4h candle whose close is below 4h EMA60.
  No intrabar touch. The close must be below EMA60 at the time of the 4h
  candle close.
- **Execution:** Exit at the next 4h bar open after the close-break signal.
- **Exit trigger bar:** The 4h candle that closed below EMA60.
- **Exit execution bar:** The next 4h candle after the trigger bar.
- **Exit price:** Next 4h bar open with frozen exit slippage.
- **Initial stop remains active:** EMA60 close-break is a trend-lifecycle
  exit. The initial risk stop (S1) remains active as a max-loss stop. If
  the initial stop is hit before the EMA60 exit triggers, the trade exits
  on the initial stop.
- **No EMA period sweep:** EMA60 is frozen. Do not test EMA40, EMA80,
  EMA120 in the same experiment.

#### 8.2.6 Required Metrics For EMA60 Exit Experiment

Any experiment using EMA60 close-break exit must report:

- MTM drawdown (mark-to-market, not just realized);
- Maximum giveback from peak open profit to exit;
- MFE (maximum favorable excursion) per trade;
- MAE (maximum adverse excursion) per trade;
- Hold duration (average, median, max, distribution);
- Funding exposure (intervals held, funding cost by year);
- Top-winner concentration (top 1, top 3, top 5 as % of net);
- Year-by-year breakdown of all the above.

### 8.3 Recommended First-round Exit Structure

**Recommended:** E6 (Hybrid) with E1 (EMA60 close-break) as the
trend-lifecycle exit and S1 (previous-20 low) as the initial risk stop.

```text
Initial risk:    S1 (previous N-bar 4h structure low)
Trend exit:      E1 (fully closed 4h candle close below 4h EMA60)
Exit convention: next 4h bar open with frozen exit slippage
```

This hybrid means:

- If the trade fails quickly (before the trend develops), the initial stop
  catches it. This is the "cost of being wrong."
- If the trend develops and then ends, the EMA60 close-break exit catches
  it. This is the "profit capture from being right."
- There is no ATR trailing. The exit is purely structural.

**Why not ATR trailing first:** T1-A already tested ATR trailing and showed
concentration risk and excessive giveback. Testing a different exit family
first is a structural hypothesis, not a parameter rescue.

**Why not structure-low trailing first:** Structure-low trailing is a valid
alternative but has more structural definition subjectivity (what counts as
a "swing low" on 4h?). EMA60 is more precisely defined.

**Why not N-bar low first:** N-bar low is simple but ties the exit to a
fixed lookback, which is essentially a parameterized version of structure
trailing. EMA60 is more adaptive.

**Why not partial TP + runner first:** Partial TP introduces a TP-level
parameter and a runner-exit rule. It should be tested after a baseline
lifecycle exit has been established.

---

## 9. Partial TP + Runner Consideration

Partial TP + runner (E5) is a valid future exit variant but should not be
the first-round exit.

### 9.1 What It Offers

- Locks in some profit early (reducing giveback on trends that reverse).
- Lets the remainder run for larger gains.
- May improve win rate (partial wins count as wins).

### 9.2 What It Costs

- Introduces a TP-level parameter (where to take partial profit?).
- Introduces a runner-exit rule (how does the remainder exit?).
- Reduces the size of winners (partial exit reduces trend capture).
- May conflict with the Owner's thesis of "letting winners run."

### 9.3 When To Test It

After Direction A has a baseline with the EMA60 close-break exit. If the
EMA60 exit shows excessive giveback, partial TP + runner can be tested as a
second-pass refinement.

**Not in the first round.**

---

## 10. 1h Positioning

### 10.1 Allowed Roles

| Role | Allowed | Boundary |
| --- | --- | --- |
| Validation proxy for 4h trend state | Yes | 1h can confirm whether a 4h trend signal is holding or weakening |
| Entry timing within 4h-qualified trend | Yes | 1h can improve entry price after 4h qualifies the trend |
| Confirmation of 4h signal | Yes | 1h follow-through after 4h breakout can reduce false signals |

### 10.2 Not Allowed

| Role | Not Allowed | Why |
| --- | --- | --- |
| Primary trend judgment layer | No | Direction A is 4h-first. 1h must not become the decision layer. |
| Standalone strategy layer | No | 1h as a standalone strategy would be CPM-1 or H6a, not Direction A. |
| CPM-style local segment strategy | No | This is the structural failure that Direction A departs from. |
| Entry rule sweep (1h patterns) | No | Do not search 1h patterns for the best entry. |

### 10.3 First-round Positioning

**First round should not use 1h.** The purpose of the first round is to
establish whether 4h main trend lifecycle capture has standalone edge with
a clean exit hypothesis (EMA60 close-break). Adding 1h would confound the
result.

If the first-round result is promising but needs entry refinement, 1h can
be introduced in a second pass (Direction B, after Direction A has a
baseline).

---

## 11. Direction E Relationship

Direction E (Trend Failure / False Breakout Avoidance Rule) is the companion
inspect to Direction A.

### 11.1 What Direction E Is

A filter or exit rule that identifies when a trend is failing and either
prevents entry or triggers early exit. It targets the losing side of trend
trading.

### 11.2 What Direction E Is Not

- Not a regime system.
- Not an independent strategy.
- Not a portfolio / multi-strategy enabler.
- Not a broad market-state classifier.

### 11.3 How It Relates To Direction A

Direction E should be inspected separately in NSC-012. If NSC-012 defines a
frozen failure-avoidance rule, it can be integrated into Direction A's
experiment plan (NSC-013) as an overlay.

**Order of operations:**

1. NSC-011 (this inspect) — define Direction A structure.
2. NSC-012 (companion inspect) — define Direction E failure-avoidance rules.
3. NSC-013 (experiment plan) — freeze Direction A baseline with or without
   Direction E overlay, depending on NSC-012 findings.

**Direction E must not delay Direction A.** If NSC-012 is not ready when
NSC-013 is drafted, NSC-013 should proceed with Direction A only and add
Direction E as a follow-up experiment.

### 11.4 How Direction E Could Address T1-A Fragility

T1-A's main weakness was that most trades were losers or near-breakeven.
Direction E could help by:

- Identifying high-failure-probability entries and skipping them (reducing
  the number of losing trades);
- Identifying trend failure earlier and exiting before the full initial stop
  is hit (reducing average loss per failed trade);
- Both mechanisms would reduce the dependence on rare large winners.

However, Direction E must be defined before it can be tested. The inspect
must specify what "trend failure" means in a frozen, non-hindsight way.

---

## 12. Sparse Trend Edge Principles

These principles from SCDM-001 apply fully to Direction A:

| # | Principle | Application To Direction A |
| --- | --- | --- |
| 1 | Low win rate is acceptable | Direction A may have 20-35% win rate. Payoff ratio must compensate. |
| 2 | Profit concentration is expected | Large winners are the structural profit source. Not a defect. |
| 3 | Profit giveback is acceptable | Holding through retracements is the cost of capturing full moves. EMA60 exit defines acceptable giveback. |
| 4 | No single-anomaly-year dependency | Direction A must be explainable year-by-year. One good year does not validate. |
| 5 | Top-winner fragility must be tested | Removing top-1 and top-3 winners must not make the strategy net-negative. Non-negotiable. |
| 6 | Cost/funding/slippage must not be relaxed | SSOT cost model. No relaxation. |
| 7 | No parameter sweep | If the frozen rule fails, classify. Do not sweep. |
| 8 | Research proxy ≠ official validation | Research adapter evidence is not promotion evidence. |

**T1-A violated principle 5 (fragility).** Direction A must address this
structurally through the exit hypothesis, not through post-result parameter
adjustment.

---

## 13. Trade Count Floor For Direction A

SCDM-001 proposed adjusted floors for 4h-based candidates. NSC-011 confirms
these for Direction A:

| Metric | NSC-008 Floor (T1-A) | Direction A Floor | Rationale |
| --- | --- | --- | --- |
| 2021+2022 minimum | 20 positions | 15 positions | 4h produces fewer signals; EMA60 exit may produce fewer trades than ATR trailing |
| 2023+2024+2025 minimum | 60 positions | 40 positions | Same rationale; must still demonstrate repeatability |
| Total minimum | 80 positions | 55 positions | Must still be sufficient for meaningful statistics |
| Fragility gate | Top-1 removal must keep net positive | Same | Non-negotiable |

**Note:** These floors are for the experiment plan, not for this inspect.
They are included here for reference. The experiment plan (NSC-013) must
confirm or adjust them before execution.

---

## 14. Next Step Recommendation

### 14.1 Is Direction A Worth Proceeding To Experiment Plan?

**Yes, with conditions.**

Direction A is worth proceeding because:

- T1-A showed that 4h main trend capture is not completely signal-free;
- The primary change (EMA60 close-break exit) is a structurally different
  exit hypothesis, not a parameter rescue;
- The direction is clean, low-parameter, and standalone;
- The failure modes are well-understood (thin sample, fragility, giveback);
- The Owner's thesis explicitly prefers trend lifecycle capture.

Conditions:

- The experiment plan (NSC-013) must freeze one entry + one exit before
  execution;
- The EMA60 close-break exit must be the first-round exit baseline;
- The fragility gate from NSC-008 must be retained;
- No parameter sweep in the first round;
- Direction E overlay should be deferred to a second pass unless NSC-012
  produces a clean, frozen failure-avoidance rule before NSC-013 is drafted.

### 14.2 Recommended Next Steps

| # | Task | Type | Depends On | Rationale |
| --- | --- | --- | --- | --- |
| 1 | NSC-012 | Docs-only inspect | None | Direction E companion inspect. Can run in parallel with NSC-013 drafting. |
| 2 | NSC-013 | Docs-only experiment plan | NSC-011 (this), NSC-012 (optional) | Freeze the Direction A baseline rule: Donchian breakout entry + EMA60 close-break exit + initial risk stop. |
| 3 | NSC-014 | Experiment execution (if Owner approves) | NSC-013 | Run the frozen Direction A baseline. |

**NSC-013 should proceed even if NSC-012 is not ready.** Direction E is an
enhancement, not a prerequisite. The first pass should establish a clean
Direction A baseline without Direction E.

### 14.3 What NSC-013 Should Freeze

NSC-013 (the experiment plan) should freeze:

1. **Entry:** 4h Donchian breakout (consistent with T1-A entry).
2. **Trend definition:** 4h EMA trend state (e.g., price above EMA60 as
   trend filter).
3. **Initial risk stop:** Previous N-bar 4h structure low (consistent with
   T1-A).
4. **Trend-lifecycle exit:** Fully closed 4h candle close below 4h EMA60.
5. **Exit convention:** Next 4h bar open with frozen exit slippage.
6. **Data windows:** 2021-2025 full year (consistent with NSC-008).
7. **Cost model:** SSOT from NSC-008.
8. **Trade count floors:** As defined in Section 13.
9. **Fragility gates:** As defined in NSC-008 Section 3.6.
10. **Anti-lookahead proof:** As defined in NSC-008 Section 3.4.
11. **MTM drawdown requirement:** As defined in NSC-008 Section 3.5.
12. **Year-by-year requirements:** As defined in NSC-008 Section 3.8.

**Not in first pass:**

- 1h entry timing (Direction B);
- Direction E failure-avoidance overlay;
- Partial TP + runner;
- Structure-low trailing (E3);
- N-bar low break (E4);
- Any parameter sweep.

---

## 15. Not-now List

The following are explicitly not authorized by this direction inspect:

- No T1-A parameter rescue.
- No Donchian / ATR / EMA / lookback sweep.
- No T1-B experiment.
- No T1 + CPM-1 portfolio combination.
- No portfolio engine.
- No regime system.
- No multi-strategy runtime.
- No multi-asset expansion.
- No full data feature store.
- No complex ML.
- No tick / orderbook simulator.
- No code implementation.
- No backtest execution.
- No adapter creation.
- No strategy implementation.
- No runtime change.
- No profile change.
- No risk-rule change.
- No backtester or research engine core change.
- No promotion conclusion.
- No small-live conclusion.
- No live deployment recommendation.
- No CPM-1 rescue.
- No CPM-2 A/B rescue.
- No Candidate C auto-start.

---

## 16. Inspect Classification

| Field | Value |
| --- | --- |
| Direction | A — 4h Main Trend Lifecycle Capture |
| Inspect conclusion | `PROCEED_TO_EXPERIMENT_PLAN` |
| Recommended first-round entry | 4h Donchian breakout (consistent with T1-A) |
| Recommended first-round exit | 4h EMA60 close-break exit (new hypothesis) |
| Recommended first-round initial stop | Previous N-bar 4h structure low (consistent with T1-A) |
| 1h involvement in first round | None |
| Direction E involvement in first round | None (deferred to NSC-012 / second pass) |
| Requires new data? | No |
| Requires portfolio / regime / multi-strategy? | No |
| Promotion conclusion | None |
| Small-live conclusion | None |

---

## 17. Relationship To Existing Governance

| Document | Relationship |
| --- | --- |
| project-roadmap-v2.md | Direction A is within Baseline Strategy Module Stabilization track |
| live-safe-v1-program.md | No live-safe code, runtime, or risk-rule changes |
| agent-working-rules.md | Any future implementation requires a Codex-issued task card |
| codex-claude-handoff-template.md | NSC-013 (if created) uses the handoff template |
| strategy-candidate-direction-map-v1.md | NSC-011 implements the P0 Direction A inspect from the direction map |
| NSC-007 | NSC-011 supersedes NSC-007's direction recommendation for Direction A |
| NSC-008 | NSC-011 reuses NSC-008's experiment contract (cost model, same-bar, fragility gates) but changes the exit hypothesis |
| NSC-009/010 | T1-A closure evidence informs Direction A design; NSC-011 is not a T1-A continuation |
| CPM-CRITERIA-001 | Promotion/rejection criteria framework still applies to any future candidate |

---

## 18. Final Boundary

This inspect recommends proceeding to a docs-only experiment plan (NSC-013)
for Direction A, with EMA60 close-break exit as the primary trend-lifecycle
exit hypothesis.

This inspect does not:

- authorize NSC-013 automatically;
- authorize runtime implementation;
- make Direction A a small-live candidate;
- make any promotion conclusion;
- revive CPM-1;
- rescue CPM-2 A/B;
- start Candidate C;
- start portfolio, regime, multi-strategy, multi-asset, feature-store, or ML
  work.

Small-live readiness gate remains unmet.

---

## 19. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial 4h Main Trend Lifecycle Capture direction inspect | Claude (NSC-011) |
