# HTPA-002 — Frozen Classifier Spec Draft v0

## 0. Status and Boundary

**Status:** Draft / docs-only / research-only
**Object:** HTPA-1 Trend Participation Applicability Classifier
**Purpose:** Translate HTPA-001 conceptual taxonomy into a classifier
specification draft for Owner review.

This document is docs-only.

It authorizes:

- no experiment;
- no backtest;
- no adapter;
- no data/classifier check;
- no threshold calculation from data;
- no runtime/profile/risk/parameter change;
- no Claude task card;
- no paper/testnet/live.

It does not query price data, inspect charts, run scripts, produce plots,
validate a classifier, or start diagnostic execution.

## 1. Relationship to HTPA-001

HTPA-001 defined the research object and state taxonomy for HTPA-1:

> Higher-Timeframe Trend Persistence with Overextension Avoidance.

HTPA-002 drafts the classifier specification that could later be frozen for a
minimal diagnostic, if the Owner separately approves that later step.

HTPA-002 does not execute the classifier.

HTPA-002 does not validate the classifier.

HTPA-002 does not inspect historical price data.

## 2. Classifier Objective

The classifier labels each eligible higher-timeframe bar or decision point into
one of:

- `VALID_TREND_PARTICIPATION`
- `INVALID_NO_TREND_OR_RANGE`
- `INVALID_OVEREXTENDED_TREND`
- `INVALID_HIGH_VOL_CHOP`
- `INVALID_POST_ATH_OR_DISTRIBUTION`
- `MIXED_LOW_CONFIDENCE`

The classification target is long-side trend participation suitability.

The classifier does not merely answer:

> Is ETH trending?

It answers:

> Is the current higher-timeframe trend state suitable for long-side trend
> participation?

If this specification reduces to "EMA slope > 0" or "price above MA", it has
collapsed into a generic trend detector / Direction A echo and should not
advance.

## 3. Candidate Input Features

All candidate inputs are OHLCV-only. No values are calculated in this document.

| Feature | Definition | Intended meaning | Proposed window options | Helps identify | Contamination risk | Why it cannot be used alone |
| --- | --- | --- | --- | --- | --- | --- |
| Major EMA slope / trend structure | Slope or direction of one or more higher-timeframe major EMAs, measured only from closed bars | Whether higher-timeframe directional structure exists | Owner decision: 4h EMA family, daily EMA family, or both | `VALID_TREND_PARTICIPATION`, `INVALID_NO_TREND_OR_RANGE` | HIGH: EMA structure appears in prior Direction A / CPM evidence | A rising EMA can lag distribution, overextension, and chop |
| Price position relative to major EMA | Closed price location above, near, or below major EMA family | Whether price is structurally aligned with trend | Owner decision: same timeframe as EMA slope, or higher timeframe only | `VALID_TREND_PARTICIPATION`, `INVALID_NO_TREND_OR_RANGE`, mixed states | MODERATE: common trend filter and Direction A echo risk | Price above MA is generic trend existence, not participation quality |
| Distance from major EMA, ATR-adjusted | Absolute or signed distance from major EMA normalized by ATR or another volatility unit | Extension away from trend structure | Owner decision: short, medium, or long ATR normalization window | `INVALID_OVEREXTENDED_TREND`, `MIXED_LOW_CONFIDENCE` | HIGH: distance/near-high concepts appear in CPM/M0 evidence | Strong trends can stay extended; distance alone cannot distinguish continuation from exhaustion |
| ATR percentile / volatility state | Current ATR or range volatility ranked against a prior closed-bar window | Whether volatility is normal, compressed, or toxic | Owner decision candidate: trailing volatility-rank window; value not chosen here | `INVALID_HIGH_VOL_CHOP`, `MIXED_LOW_CONFIDENCE` | HIGH: CPM-MOD-002 used ATR gate logic | High volatility may occur in valid breakouts; low volatility can also be range-bound |
| Recent return / surge | Closed-bar cumulative return over a recent lookback | Whether price has moved too far too quickly | Owner decision: short and medium return windows | `INVALID_OVEREXTENDED_TREND`, `INVALID_POST_ATH_OR_DISTRIBUTION` | MODERATE: prior failures involved surge / high-slope states | Surge can indicate either healthy momentum or late exhaustion |
| Directional efficiency | Net movement divided by total movement over a window, or equivalent OHLCV-only efficiency proxy | Whether movement is directional or noisy | Owner decision: one medium trend window plus optional shorter confirmation window | `VALID_TREND_PARTICIPATION`, `INVALID_HIGH_VOL_CHOP`, `INVALID_NO_TREND_OR_RANGE` | LOW to MODERATE | Efficiency can lag early trend transitions and can be distorted by sharp one-way moves |
| Whipsaw proxy | Closed-bar proxy for reversal frequency, EMA-cross frequency, false-break frequency, or range expansion without net progress | Whether the state is toxic chop rather than tradable trend | Owner decision: use one simple proxy only for first draft | `INVALID_HIGH_VOL_CHOP`, `MIXED_LOW_CONFIDENCE` | MODERATE: motivated by prior loss clusters | Must not use strategy PnL, trade outcomes, or post-entry information |
| Distance to recent high / ATH / Donchian high | Closed price relationship to recent high, all-time high, or Donchian high family | Whether price is near late-cycle extremes or breakout areas | Owner decision: recent high window vs ATH-style window | `INVALID_OVEREXTENDED_TREND`, `INVALID_POST_ATH_OR_DISTRIBUTION`, mixed states | HIGH: M0 and Direction A evidence include near-high / breakout context | Near-high can be valid breakout, trend persistence, or distribution |
| Distribution-like decline proxy | Drawdown or weakening from recent high using only closed bars | Whether a prior trend has entered decline / distribution | Owner decision: recent-high lookback and decline definition | `INVALID_POST_ATH_OR_DISTRIBUTION`, `MIXED_LOW_CONFIDENCE` | HIGH: directly motivated by CPM-1 2021 failure analysis | Can become hindsight labeling unless defined before data application |

## 4. Threshold Policy

No thresholds are calculated from data in this document.

Prior thresholds must not be reused as truth.

Threshold-setting policy:

1. Thresholds must be frozen before data application.
2. Thresholds must be justified by market-structure rationale, not outcome
   fitting.
3. Thresholds must not be adjusted after scenario visual plausibility check.
4. Thresholds may be proposed as Owner decision candidates if Codex cannot
   justify them without data.
5. Any threshold inspired by CPM/M0/Direction A evidence must be disclosed as
   contaminated.

Current threshold status:

| Threshold area | Status |
| --- | --- |
| EMA slope definition | Owner decision point |
| Price-above / near-EMA rule | Owner decision point |
| ATR-adjusted EMA distance | Owner decision point |
| ATR percentile / volatility state | Owner decision point |
| Recent return / surge | Owner decision point |
| Directional efficiency | Owner decision point |
| Whipsaw proxy | Owner decision point |
| Recent high / ATH / Donchian distance | Owner decision point |
| Distribution-like decline | Owner decision point |

No candidate numeric values are proposed here because doing so responsibly
would require either a separate Owner threshold decision or a separate
pre-data market-structure rationale.

## 5. Labeling Rule Draft

The draft rule hierarchy is intentionally simple. It prioritizes invalid-state
protection before valid-state approval.

1. If no higher-timeframe uptrend exists, label:
   `INVALID_NO_TREND_OR_RANGE`.

2. If post-ATH / distribution-like decline condition holds, label:
   `INVALID_POST_ATH_OR_DISTRIBUTION`.

3. If high-volatility chop / low directional efficiency condition holds, label:
   `INVALID_HIGH_VOL_CHOP`.

4. If overextension condition holds, label:
   `INVALID_OVEREXTENDED_TREND`.

5. If higher-timeframe trend exists and none of the invalid conditions hold,
   label:
   `VALID_TREND_PARTICIPATION`.

6. If feature signals conflict or required feature availability is ambiguous,
   label:
   `MIXED_LOW_CONFIDENCE`.

Rationale for this hierarchy:

- HTPA-1 is an applicability classifier, so invalid-state protection is more
  important than confirming generic trend existence.
- Distribution-like decline is checked before high-vol chop and overextension
  because trend labels can lag after major highs.
- Overextension is checked before valid-state approval because late trend
  participation is a core failure mode.

No numeric thresholds are set in this rule draft.

## 6. Scenario Classification Expectations

These are expectations only. No data is inspected.

| Scenario | Expected classification | Why | Falsification read |
| --- | --- | --- | --- |
| 2021 Q1 | Candidate `VALID_TREND_PARTICIPATION`, caveated; may require sub-period treatment | ETH had strong trend persistence, but the period is not unambiguously clean | Failure if no coherent valid participation sub-state can be identified in the strongest persistence window |
| 2021 May–Jul | `INVALID_HIGH_VOL_CHOP`, `INVALID_POST_ATH_OR_DISTRIBUTION`, or `MIXED_LOW_CONFIDENCE` | Mid-year correction / high-volatility chop / distribution-like behavior expected | Failure if most of the period is labeled clean valid participation without toxic-state explanation |
| 2022 H1 | Invalid for long-side participation, likely `INVALID_NO_TREND_OR_RANGE` or related invalid state | Bear-market / downtrend conditions should be hostile to long-side trend participation | Failure if bearish higher-timeframe states are repeatedly labeled valid without recovery-state rationale |
| 2023 H1 | Mostly `INVALID_NO_TREND_OR_RANGE` or `MIXED_LOW_CONFIDENCE` | Expected range/chop or weak directional persistence | Failure if HTPA-1 cannot classify 2023 coherently |
| 2023 Q4 | Potentially `VALID_TREND_PARTICIPATION`, but fragile | Recovery-onset regime may become valid but can be concentrated / false-start prone | Failure if recovery-onset is indistinguishable from generic MA trend logic |
| 2024 trend-friendly periods | Candidate `VALID_TREND_PARTICIPATION` | Some 2024 periods may be trend-friendly | Must be concretely specified later before diagnostic execution using pre-observable logic |

## 7. Direction A Anti-collapse Test Plan

Overlap with Direction A during genuine ETH trend episodes is expected and is
not automatically failure.

Failure is lack of new regime information.

Future diagnostic execution should compare:

- valid-state bars vs Direction A active periods;
- accepted trades if an entry rule is later added;
- top winners;
- shared profit episodes;
- Direction A loss/chop periods avoided by HTPA;
- invalid periods where Direction A would have traded or lost;
- whether HTPA gives a pre-observable reason for avoiding those periods.

Collapse should be declared if HTPA only renames Direction A winners, cannot
explain avoided invalid periods, or provides no new pre-observable regime
information beyond generic trend following.

No numeric overlap thresholds are set.

## 8. Anti-fitting Rules

Anti-fitting rules:

- no data application before thresholds, windows, labels, and feature families
  are frozen;
- no threshold adjustment after seeing scenario partitions;
- visual plausibility may only reject or pass a frozen spec;
- visual plausibility cannot change thresholds, windows, feature families,
  coverage rules, scenario definitions, or labels;
- strategy PnL, trade outcomes, and post-entry information cannot be used for
  classification;
- future diagnostic must record any failed classifier without rescue tuning.

## 9. Kill Criteria

HTPA-002 should be killed or paused before or during future diagnostic if:

- the classifier collapses into a generic trend detector;
- it cannot classify 2023 coherently;
- invalid states are conceptually too broad or too narrow;
- overextension cannot be distinguished from healthy trend using OHLCV;
- the feature set requires post-hoc thresholds to make sense;
- Direction A information gain is absent;
- the classifier requires strategy PnL, trade outcomes, or post-entry
  information.

## 10. Open Owner Decisions

The Owner must decide before any diagnostic execution:

- Which timeframe is the classifier evaluated on: 4h, daily, or both?
- Are thresholds chosen as conservative hand-set values or left to a separate
  threshold spec?
- Is 2021 Q1 split into sub-periods before execution?
- How is 2023 Q4 treated: valid candidate, mixed candidate, or explicit
  recovery-onset challenge?
- Must 2024 trend-friendly periods be specified now, or in a separate
  execution plan?
- What is the minimal Direction A comparison required?
- Should mixed/conflict states default to no-trade / invalid for the first
  diagnostic?
- Should the first diagnostic use one simple whipsaw proxy, or leave whipsaw
  proxy selection to a later threshold/spec decision?

## 11. What This Spec Authorizes / Does Not Authorize

This spec authorizes only Owner review of classifier design.

It does NOT authorize:

- implementation;
- data check;
- backtest;
- adapter;
- threshold calculation;
- runtime/profile/risk/parameter change;
- Claude task card;
- paper/testnet/live.

## 12. Risk Triage

| Risk | Triage | Handling |
| --- | --- | --- |
| Generic trend detector collapse | HIGH | Keep invalid-state hierarchy and require participation applicability, not trend existence. |
| Direction A echo | HIGH | Require future Direction A comparison across bars, trades, top winners, episodes, avoided losses, and invalid periods. |
| Threshold selection unresolved | HIGH | Owner decision required before execution; not a blocker for docs-only review. |
| Post-hoc contamination | HIGH | Disclose CPM/M0/Direction A provenance and do not reuse prior thresholds as truth. |
| 2023 classification incoherence | HIGH | Owner must choose pre-empirical 2023 treatment before execution. |
| Overextension vs healthy trend ambiguity | HIGH | Requires explicit owner-approved distance/surge/distribution definitions before execution. |
| Whipsaw proxy complexity | MODERATE | Use one simple proxy or defer proxy selection; avoid composite scoring by default. |
| Too many feature families | MODERATE | Keep rule hierarchy simple; avoid weighted composite classifier in v0. |
| Visual plausibility fitting | HIGH | Visual plausibility can only pass or reject frozen spec. |
| Runtime / small-live misinterpretation | LOW | Explicit non-authorizations block runtime and execution meaning. |
| Docs-only spec usefulness | SUFFICIENT | Sufficient for Owner review and threshold-decision discussion. |
