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

# HTPA-001 — Lightweight Frozen Diagnostic Spec v0

## 0. Status and Boundary

**Status:** Draft / docs-only / research-only
**Object:** HTPA-1 — Higher-Timeframe Trend Persistence with Overextension Avoidance
**Purpose:** Lightweight frozen diagnostic spec draft for Owner review

This document is docs-only.

It authorizes:

- no experiment;
- no backtest;
- no adapter;
- no classifier/data check;
- no threshold setting;
- no runtime/profile/risk/parameter change;
- no Claude task card;
- no paper/testnet/live.

It does not start Phase 1 execution. It does not inspect price data, produce
charts, calculate thresholds, or modify strategy/runtime/backtester code.

## 1. Research Object

HTPA-1 means:

> Higher-Timeframe Trend Persistence with Overextension Avoidance.

HTPA-1 is a diagnostic research object for trend participation applicability.
It is not a generic trend classifier.

HTPA-1 is not:

- CPM-1 rescue;
- Direction A rescue;
- VEI rescue;
- short-side research;
- portfolio, router, or regime-engine implementation;
- runtime, paper, testnet, live, or small-live preparation.

Its research object is a **Trend Participation Applicability Classifier**:

> Does the current higher-timeframe trend state look suitable for long-side
> trend participation?

## 2. Core Design Question

The classifier is trying to classify whether a higher-timeframe trend state is
suitable for long-side trend participation.

It does not merely classify whether a trend exists.

**Trend Existence** asks:

- Is price above a moving average?
- Is a major EMA rising?
- Is there a breakout or directional slope?

This is insufficient. A market can be trending but unsuitable for long-side
participation because it is overextended, distribution-like, high-volatility
chop, late-cycle, or prone to whipsaw.

**Trend Participation Applicability** asks:

- Is the trend state healthy enough to participate from the long side?
- Is the trend persistent rather than exhausted?
- Is volatility supportive rather than toxic?
- Is the market avoiding post-ATH / distribution-like decline?
- Is the state distinguishable from Direction A-style generic trend following?

If HTPA-1 reduces to "EMA slope > 0" or "price above MA", it should be
classified as collapsed into generic trend following / Direction A echo.

## 3. State Taxonomy

### 3.1 VALID_TREND_PARTICIPATION

**Conceptual meaning:** A higher-timeframe uptrend state where directional
persistence is present and not obviously exhausted, distribution-like, or
choppy.

**Why HTPA-1 should trade there:** The edge claim is that healthy crypto trends
can persist longer than random and long-side participation can capture part of
that persistence.

**Failure mode prevented:** Avoids treating every uptrend as equal; focuses on
states where trend continuation is plausible rather than merely visible.

### 3.2 INVALID_NO_TREND_OR_RANGE

**Conceptual meaning:** A range, flat, or weak-directional state where major
trend structure does not show useful persistence.

**Why HTPA-1 should not trade there:** Long-side trend participation has no
clear payoff tail when directional persistence is absent.

**Failure mode prevented:** Churn, false starts, repeated small losses, and
participating in non-trending noise.

### 3.3 INVALID_OVEREXTENDED_TREND

**Conceptual meaning:** A trend state that may still be upward but is stretched
relative to its higher-timeframe structure, recent returns, or volatility.

**Why HTPA-1 should not trade there:** Late participation may be exposed to
mean reversion, liquidation cascades, or poor reward/risk after the easy trend
move has already occurred.

**Failure mode prevented:** Buying parabolic or late-cycle trend continuation
that is more likely to reverse or chop than persist.

### 3.4 INVALID_HIGH_VOL_CHOP

**Conceptual meaning:** A high-volatility state with poor directional
efficiency, frequent reversals, or range expansion without net progress.

**Why HTPA-1 should not trade there:** High volatility alone is not healthy
trend persistence. It can indicate toxic churn where entries get stopped or
whipsawed.

**Failure mode prevented:** CPM-1-like damage from volatile corrections and
whipsaw periods inside nominal trend environments.

### 3.5 INVALID_POST_ATH_OR_DISTRIBUTION

**Conceptual meaning:** A state near or after a major high where price shows
distribution-like decline, failed continuation, or weakening after a prior
surge.

**Why HTPA-1 should not trade there:** Trend labels can lag after peaks. A
still-positive slope can coexist with distribution and declining participation
quality.

**Failure mode prevented:** Entering long after the trend has transitioned from
participation opportunity to distribution / reversal risk.

### 3.6 MIXED_LOW_CONFIDENCE

**Conceptual meaning:** A state where trend, volatility, extension, and
distribution proxies conflict.

**Why HTPA-1 should not trade there by default:** The classifier is not
confident enough to label the state as healthy trend participation.

**Failure mode prevented:** Forcing ambiguous periods into valid or invalid
labels after seeing outcomes.

## 4. Feature Families

No thresholds are chosen in this document.

| Feature family | What it tries to measure | Helps distinguish | Post-hoc contamination risk | Why not sufficient alone |
| --- | --- | --- | --- | --- |
| Major EMA slope / trend structure | Higher-timeframe directional structure and slope persistence | Valid trend vs no-trend/range | Moderate, because prior work used EMA structure heavily | Can collapse into generic trend following or Direction A echo |
| Distance from major EMA | Extension away from trend structure | Healthy trend vs overextended trend | Moderate, because EMA-distance appears in prior failure analysis | Distance can stay elevated in strong trends and does not identify distribution alone |
| ATR percentile / volatility state | Volatility regime and whether conditions are calm, normal, or toxic | Healthy trend vs high-vol chop | High, because CPM-MOD-002 used ATR gating | Volatility alone did not explain all historical failures and can be trend-supportive |
| Recent return / surge | Whether price has moved too far too quickly | Healthy trend vs overextended / late trend | Moderate, because surge behavior is visible in prior failure review | Strong recent return can signal either persistence or exhaustion |
| Directional efficiency | Net directional progress relative to total movement | Valid persistence vs chop | Low to moderate | Efficiency can lag and may miss early trend formation |
| Whipsaw proxy | Reversal frequency, false-break frequency, or range expansion without progress | High-vol chop, mixed state | Moderate, because loss clustering motivated this family | Must be OHLCV-only and cannot use strategy PnL or trade outcomes |
| Distance to recent high / ATH / Donchian high | Whether price is near prior extremes or late in a move | Overextension, post-ATH/distribution | High, because CPM/M0 evidence identified near-high loss factors | Near-high can also be valid breakout / trend continuation |
| Distribution-like decline proxy | Decline from recent high, failed recovery, weakening after peak | Post-ATH/distribution vs valid trend | Moderate to high | Decline proxies can become hindsight labels unless frozen before data application |

## 5. Post-hoc Contamination Disclosure

HTPA-1 feature families are partly motivated by prior evidence:

- CPM-1 2021 failure;
- CPM-MOD-002 ATR gate;
- M0 ecology;
- Direction A fragility;
- VEI overlap echo.

This does not invalidate HTPA-1. It does mean future diagnostic execution must
handle post-hoc contamination explicitly.

Any future diagnostic execution must:

- disclose feature provenance;
- not reuse old thresholds as truth;
- freeze thresholds before data application;
- test scenario expectations beyond the exact failure evidence that inspired
  the features.

Feature families may be considered plausible at docs-only level. Thresholds,
windows, labels, and coverage rules must be frozen separately before any data
application.

## 6. Pre-registered Scenario Expectations

These are expectations only. No data check is authorized here.

### 6.1 2021 Q1

**Expected state:** VALID_TREND_PARTICIPATION candidate, caveated.

**Why:** ETH had strong trend persistence, making it an important should-earn
candidate for long-side trend participation.

**Caveat:** It is not unambiguously clean. CPM-1 2021 evidence shows stress
pockets and later Q1/Q2 loss clustering. Future scenario treatment may require
pre-specified sub-period handling, such as Jan–early Feb vs late Feb–Mar.

**What would falsify the hypothesis:** If a frozen classifier cannot identify
any coherent valid participation sub-state in the strongest persistence window,
or if valid-state participation there is negative without a pre-declared
explanation.

### 6.2 2021 May–Jul

**Expected state:** INVALID_HIGH_VOL_CHOP, INVALID_POST_ATH_OR_DISTRIBUTION,
or MIXED_LOW_CONFIDENCE.

**Why:** The period is expected to contain mid-year correction, high-volatility
chop, and distribution-like behavior.

**What would falsify the hypothesis:** If the classifier labels most of this
period as clean valid participation without explaining why it is not toxic
trend participation risk.

### 6.3 2022 H1

**Expected state:** INVALID_NO_TREND_OR_RANGE or invalid long-side
participation due to bear-market / downtrend conditions.

**Why:** Long-side trend participation should not be favored when the dominant
higher-timeframe state is bearish or structurally hostile.

**What would falsify the hypothesis:** If the classifier repeatedly labels
bear-market states as valid long-side participation without a distinct,
pre-observable recovery-state rationale.

### 6.4 2023 H1

**Expected state:** Mostly INVALID_NO_TREND_OR_RANGE or MIXED_LOW_CONFIDENCE.

**Why:** The period is expected to represent range/chop or weak directional
persistence rather than clean long-side trend participation.

**What would falsify the hypothesis:** If HTPA-1 cannot classify 2023 H1
coherently, or if the classifier treats weak/choppy recovery behavior as clean
valid participation.

### 6.5 2023 Q4

**Expected state:** Potentially VALID_TREND_PARTICIPATION, but fragile.

**Why:** The period may represent a recovery-onset regime where trend
participation begins to become valid, while still carrying concentration and
false-start risk.

**What would falsify the hypothesis:** If the classifier cannot distinguish
recovery-onset participation from generic "price above moving average" logic,
or if it labels all recovery behavior as valid without mixed-state handling.

### 6.6 2024 Trend-Friendly Periods

**Expected state:** Candidate VALID_TREND_PARTICIPATION periods.

**Why:** Some 2024 periods may be trend-friendly, but they must be concretely
specified later before diagnostic execution using pre-observable market-state
logic.

**What would falsify the hypothesis:** If future 2024 scenario definitions are
chosen only after seeing favorable outcomes, or if the classifier cannot
explain why a period is valid beyond generic trend existence.

## 7. Direction A Anti-collapse Logic

Overlap with Direction A during genuine ETH trend episodes is expected and is
not automatically a failure.

Collapse occurs if:

- HTPA-1 only renames Direction A winners;
- HTPA-1 cannot explain avoided invalid periods;
- HTPA-1 provides no new pre-observable regime information;
- valid-state profits come from the same Direction A episodes without improved
  invalid-state avoidance.

Any future diagnostic must compare:

- valid-state bars;
- accepted trades;
- top winners;
- shared profit episodes;
- avoided invalid periods;
- Direction A loss/chop periods.

No numeric overlap thresholds are set in this document.

## 8. Kill Criteria

HTPA-1 should be killed or paused if any of the following occur:

- the classifier reduces to a generic trend detector;
- it cannot classify 2023 coherently;
- it cannot distinguish valid trend participation from overextended trend;
- valid-state expectation fails in should-earn scenarios;
- invalid-state logic still captures major losses;
- information gain over Direction A is absent;
- survival requires post-hoc threshold adjustment;
- it requires using strategy PnL, trade outcomes, or post-entry information to
  classify states.

No numeric thresholds are defined here.

## 9. What Success Would Mean

Success means:

- HTPA-1 gives a plausible pre-observable applicability boundary;
- it can explain when long-side trend participation is valid vs invalid;
- it provides new information beyond Direction A;
- it justifies a future separately approved minimal diagnostic execution.

Success does NOT mean:

- runtime candidate;
- small-live candidate;
- strategy approval;
- backtest approval;
- parameter approval.

## 10. What Failure Would Mean

Failure means:

- HTPA-1 is not a useful methodology improvement;
- current OHLCV-only regime boundary may be insufficient;
- future Funding/OI may be considered only if the failure mode specifically
  shows OHLCV cannot distinguish healthy trend from crowded/late trend.

Failure does NOT automatically authorize:

- Funding/OI;
- short-side research;
- portfolio/router/regime work;
- new rescue variants;
- backtests, adapters, or classifier/data checks.

## 11. Next Gate

The next possible step, if Owner approves, is not a backtest.

It would be a separate frozen classifier spec or minimal diagnostic execution
plan.

That future step must still separately authorize:

- feature definitions;
- windows;
- thresholds;
- data source;
- visual plausibility method;
- no-threshold-adjustment rule;
- Direction A comparison method.

## 12. Risk Triage

| Risk | Triage | Handling |
| --- | --- | --- |
| Generic trend-classifier collapse | HIGH | Keep HTPA-1 framed as trend participation applicability, not trend existence. |
| Direction A old-path echo | HIGH | Require future comparison of valid-state bars, accepted trades, top winners, shared profit episodes, avoided invalid periods, and Direction A loss/chop periods. |
| Post-hoc contamination from CPM/M0/Direction A evidence | HIGH | Disclose feature provenance and freeze thresholds/windows before data application. |
| 2023 incoherence | HIGH | Require a pre-empirical stance on 2023 as invalid, mixed, or partially valid before diagnostic execution. |
| Threshold fitting | BLOCKER for execution, not for this draft | Future execution cannot proceed without frozen thresholds and no-adjustment rule. |
| Visual plausibility becoming fitting | HIGH | Visual checks may only reject a frozen spec or pass it forward; they cannot adjust labels, thresholds, windows, or feature families. |
| Funding/OI rescue drift | MODERATE | Preserve as future-only and only if OHLCV failure mode specifically requires extra data. |
| Short-side drift | LOW | This spec is long-side only and does not authorize short-side work. |
| Runtime / small-live interpretation | LOW | Boundary section explicitly blocks runtime, paper, testnet, live, and small-live implications. |
| Lightweight spec sufficiency | SUFFICIENT | Sufficient as a docs-only draft; future execution still needs a separate frozen classifier spec or minimal diagnostic plan. |
