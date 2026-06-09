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

# MTC-001 — Main Trend Capture Fragility Evaluation Framework v0

**Task ID:** MTC-001
**Date:** 2026-05-07
**Status:** Proposed / Framework Definition
**Scope:** Docs-only evaluation framework
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document defines an evaluation framework for top-winner concentration
and fragility in sparse-trend, low-win-rate, high-payoff-ratio strategies.

This document is not:

- an experiment authorization;
- a promotion review;
- a small-live readiness review;
- a runtime implementation approval;
- a live deployment recommendation;
- a defense of Direction A;
- an approval of Direction A promotion;
- a parameter tuning guide;
- a backtester or research engine specification.

No code, no backtest, no adapter, no strategy implementation, no runtime
change, no profile change, no risk-rule change, and no promotion decision
follows from this document.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

---

## 1. Purpose And Motivation

### 1.1 Why This Framework Exists

The project has encountered top-winner fragility as a recurring blocker:

- T1-A (NSC-009): top-1 winner = 98.47% of net PnL. Classified
  `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`.
- Direction A clean baseline (NSC-014): top-3 removal turns net negative.
  Classified `PAUSE_FRAGILE`.
- E-A overlay (NSC-017): failed to reduce fragility; cut main winners.
  Classified `REJECT_OVERFILTERS`.

Each evaluation used ad-hoc judgment. There is no pre-registered, reusable
framework that defines:

- what the top-N removal tests actually measure;
- when concentration is an expected feature of sparse trend capture versus
  a structural fragility that blocks deployment;
- how to combine top-N removal with year-by-year contribution, MFE/MAE,
  giveback, MTM drawdown, winner attribution, trade count, and funding
  exposure into a single classification.

This framework exists to answer those questions before the next strategy
direction (Direction C / D / F or any new direction) enters inspect or
experiment.

### 1.2 What This Framework Does Not Do

- It does not lower the evidence bar for any existing strategy.
- It does not reclassify Direction A.
- It does not replace Owner judgment.
- It does not define what constitutes a "good" strategy in general.
- It does not apply to CPM-style pullback-continuation strategies with
  moderate win rates and lower payoff ratios.

---

## 2. Sparse Trend Edge: What Top-Winner Concentration Means

### 2.1 The Structural Reality

A sparse-trend strategy with 15-25% win rate and 4-8x payoff ratio is
expected to have concentrated profit. This is not a defect. It is a
structural consequence of the strategy type:

- Few trades capture multi-day or multi-week trend moves.
- Many trades hit the initial stop or trend-exit trigger at small loss.
- The large winners must, by definition, exceed the cumulative small losses.
- Therefore a handful of winners will always account for a disproportionate
  share of total net PnL.

The question is never "does the strategy have concentrated winners?" It
always does. The question is whether the concentration is survivable or
whether it means the edge is illusory.

### 2.2 What Concentration Tells You

Top-winner concentration answers one question:

> **If the best trades had not occurred — or had been merely average — would
> the strategy still have a positive edge?**

If yes: the strategy has structural trend-capture ability. The large winners
are the expected payoff for enduring many small losses.

If no: the strategy is lottery-ticket-dependent. The positive result is an
artifact of a few outlier trades, not evidence of a repeatable edge.

### 2.3 The Spectrum

Concentration exists on a spectrum:

```
Full dependence          Fragile-but-real          Robust sparse edge
         |                        |                          |
  top-1 = 100%+ net     top-N removal tests         top-N removal
  net w/o top-1 < 0     are mixed / borderline     stays positive
  (lottery ticket)       (requires owner judgment)  (structural edge)
```

Most real sparse-trend strategies land in the middle zone. The framework's
job is to classify where on this spectrum a result falls, not to force a
binary pass/reject.

---

## 3. Top-N Removal Tests: Definitions And Interpretation

### 3.1 Definition

For a set of closed trades sorted by individual trade net PnL descending:

- **Top-1 net excluding** = total net PnL minus the single largest winner.
- **Top-3 net excluding** = total net PnL minus the 3 largest winners.
- **Top-5 net excluding** = total net PnL minus the 5 largest winners.

A positive value means the strategy is net profitable even without those
top winners. A negative value means the strategy depends on those winners
to be net positive.

### 3.2 What Each Test Represents

| Test | What It Probes | Failure Means |
|------|---------------|---------------|
| Top-1 removal | Single-trade dependency | Strategy is one-trade-or-nothing; result is an outlier artifact |
| Top-3 removal | Winner-cluster dependency | Strategy needs a small cluster of best trades to survive; without them, the losing majority dominates |
| Top-5 removal | Extended winner-cluster dependency | Even removing 5 best trades collapses the edge; very high concentration risk |

### 3.3 Progressive Severity

The tests are progressive. Top-3 failure is more informative than top-1
failure for sparse-trend strategies:

- Top-1 removal failing alone could mean one anomalous trade. This is the
  most fragile shape.
- Top-1 passing but top-3 failing means the strategy has a real winner
  cluster, but the cluster is narrow. This is the typical sparse-trend
  fragility shape.
- Top-3 passing but top-5 failing means the edge extends beyond the core
  cluster but is still concentrated. This may be acceptable depending on
  total trade count and year-by-year distribution.

For sparse-trend strategies, top-3 removal is the primary gate.
Top-1 removal is the minimum viability check.
Top-5 removal is the extended robustness check.

### 3.4 What Top-N Removal Does Not Tell You

Top-N removal is a necessary but not sufficient fragility test. It does not:

- tell you which years the top winners came from;
- distinguish between one anomalous year and broad trend capture;
- tell you whether the top winners are repeatable;
- account for the number of total trades (100 trades minus top-3 is
  different from 50 trades minus top-3);
- tell you whether drawdown was acceptable during the losing stretches;
- tell you whether the strategy would survive real execution costs,
  slippage variance, and funding rate changes.

---

## 4. Fragility Evaluation: Combined Framework

A single metric cannot classify sparse-trend fragility. The following
dimensions must be evaluated together.

### 4.1 Dimension 1: Top-N Removal Survival

| Gate | PASS Threshold | PAUSE_FRAGILE Zone | REJECT Threshold |
|------|---------------|-------------------|-----------------|
| Top-1 net excluding | > 0 | >= 0 but marginally | < 0 |
| Top-3 net excluding | > 0 | Near 0 (within 10% of total net) | < 0 |
| Top-5 net excluding | > 0 | Near 0 | < 0 and magnitude > 50% of total net |

Primary gate: **Top-3 net excluding > 0** is the minimum for PASS.
Top-3 negative with top-1 positive is the defining shape of PAUSE_FRAGILE.

### 4.2 Dimension 2: Year-by-Year Contribution

Evaluate whether net profit is distributed across multiple years or
concentrated in one or two:

| Shape | Classification |
|-------|---------------|
| 3+ years independently positive, remaining years near breakeven | Strong |
| 2 years positive and dominant, others near breakeven or slightly negative | Acceptable but flag concentration |
| 1 year dominates all profit | Fragile — year is an outlier risk |
| Profit only in a single narrow period | Reject-level fragility |

Year-by-year must be evaluated net of costs, not gross.

For a 5-year backtest (2021-2025), the minimum acceptable shape is:

- At least 2 years independently positive after costs.
- No single year contributing more than 60% of total net PnL.
- If only 2 years are positive, they must not be adjacent-only (i.e.,
  2023+2024-only is weaker than 2021+2023).

### 4.3 Dimension 3: Winner Attribution And Regime Explainability

For each top-5 winner, the following must be answerable:

- What was the market condition (trend, breakout direction, volatility)?
- Is the winner the result of a structural trend capture (long hold,
  multi-day move) or an anomalous event (gap, flash crash, liquidation
  cascade)?
- Could the entry and exit rules, as frozen, reasonably identify and
  capture a similar move in future market conditions?

If top winners are explainable by the frozen rule's structural logic
(Donchian breakout into sustained trend with EMA60 exit), that supports
the edge being real. If top winners are driven by events the rule cannot
systematically identify, that weakens the edge claim.

This dimension requires Owner judgment. It cannot be fully automated.

### 4.4 Dimension 4: MFE / MAE / Giveback

| Metric | What It Shows | Acceptable Range |
|--------|--------------|-----------------|
| MFE (Maximum Favorable Excursion) | Best-case open profit for winners | Should be materially larger than realized winner — shows trend was real |
| MAE (Maximum Adverse Excursion) | Worst-case open drawdown per trade | Should be bounded by initial stop; outlier MAE beyond stop = execution risk |
| Maximum Giveback | Largest MFE-to-realized-PnL decline | Should not exceed 2x average winner; otherwise the exit is too slow |

For sparse-trend strategies, some giveback is expected. The question is
whether giveback is bounded and whether the exit rule captures enough of
the MFE to make the trade worthwhile.

High MFE / moderate realized PnL / bounded giveback = the rule captures
real trends but leaves room. This is acceptable.

High MFE / low realized PnL / high giveback = the rule identifies trends
but fails to capture them. This weakens the edge.

### 4.5 Dimension 5: MTM Drawdown And Equity Shape

| Metric | What It Shows |
|--------|--------------|
| Realized MaxDD | Worst peak-to-trough on closed trades only |
| MTM MaxDD | Worst peak-to-trough including open-position mark-to-market |

For sparse-trend strategies:

- MTM MaxDD will be higher than Realized MaxDD because positions are held
  through retracements.
- MTM MaxDD up to 15% may be acceptable for research evidence if the
  strategy recovers and the drawdown period is explainable.
- MTM MaxDD is more important than Realized MaxDD for deployment risk
  assessment because real execution faces open-position risk.

Drawdown periods must be cross-referenced with year-by-year data. A
strategy with 8% MTM MaxDD concentrated in one bad year is different from
8% MTM MaxDD spread across multiple years.

### 4.6 Dimension 6: Trade Count And Statistical Grounding

| Gate | Minimum | Rationale |
|------|---------|-----------|
| Total closed trades | >= 100 | Below 100, top-N removal is dominated by noise |
| 2023+2024+2025 trade floor | >= 60 | Recent-regime sample must be sufficient |
| Independent positive years | >= 2 | Single-year profit is an outlier risk |
| Winner count | >= 15 | Below 15 winners, payoff ratio estimate is unreliable |

If trade count floors are not met, the result is `INSUFFICIENT_EVIDENCE`
regardless of other metrics. Top-N removal on 50 trades is meaningless.

### 4.7 Dimension 7: Funding Exposure

For perpetual-futures strategies:

- Funding cost is a real ongoing cost that varies with market conditions.
- Research funding cost from historical data is a lower bound; live funding
  can be materially worse in high-open-interest periods.
- If funding cost exceeds 20% of gross PnL, the strategy's net edge is
  heavily dependent on favorable funding conditions.
- Funding cost should be reported per trade and in aggregate.

Funding does not independently classify fragility, but it must be visible
in the evaluation. A strategy that is fragile on top-N removal AND has
high funding exposure is more fragile than the top-N test alone suggests.

---

## 5. Classification Definitions

### 5.1 INSUFFICIENT_EVIDENCE

The result does not have enough data to evaluate fragility.

**Criteria (any one is sufficient):**

- Trade count floors not met.
- Winner count < 15.
- Backtest window < 3 years.
- Research-only adapter with known harness gaps.

**Next step:** Increase sample or improve harness before re-evaluation.

### 5.2 REJECT

The result has enough data and clearly fails fragility gates.

**Criteria (any one is sufficient):**

- Top-1 net excluding < 0 (single-trade dependency).
- Net PnL < 0 after costs.
- PF < 1.0 after costs.
- Single year contributes > 80% of total net PnL.
- Winner attribution reveals top winners are driven by events the frozen
  rule cannot systematically identify.
- A tested overlay worsens fragility and no other overlay path is available
  within the current direction scope (as with E-A / NSC-017).

**Next step:** Archive the result. Return to Strategy Direction Map.

### 5.3 PAUSE_FRAGILE

The result has enough data, shows a real positive signal, but does not
pass the minimum fragility gates.

**Criteria (defining shape):**

- Top-1 net excluding > 0 (not single-trade dependent).
- Top-3 net excluding < 0 (winner-cluster dependent).
- Net PnL > 0 after costs.
- PF > 1.0 after costs.
- Trade count floors may or may not be met (if met, the pause is more
  informative).
- Year-by-year shows concentration but not single-year-only dependency.

**What PAUSE_FRAGILE means:**

- The direction has real signal. It is not noise.
- The signal has not yet proven robustness.
- The result cannot enter promotion, small-live, or runtime.
- Continued research within the same direction is permitted but must
  produce a new classification, not a re-run of the same experiment.

**What PAUSE_FRAGILE does not mean:**

- It is not a permanent hold. The Owner may later decide to reject.
- It is not a pass. The direction is not deployable.
- It does not authorize parameter rescue, overlay stacking, or
  after-the-fact selection.

### 5.4 PASS / RESEARCH_PASS

The result passes minimum fragility gates and shows robustness.

**Criteria (all required):**

- Top-3 net excluding > 0.
- Top-5 net excluding > 0 or near 0 (within 5% of total net).
- Net PnL > 0 after costs.
- PF > 1.1 after costs.
- At least 2 years independently positive after costs.
- No single year contributes > 60% of total net PnL.
- Trade count floors met.
- Winner count >= 15.
- Winner attribution supports structural edge.

**What RESEARCH_PASS means:**

- The result clears the fragility bar.
- It may proceed to OOS validation or official validation.
- It does not automatically become a runtime candidate.

### 5.5 RUNTIME_CANDIDATE

The result has passed RESEARCH_PASS, survived OOS validation on unseen
data, and passed any additional gates defined by the current program.

**Criteria (all required):**

- RESEARCH_PASS classification on in-sample or primary window.
- OOS validation on a held-out period with consistent classification.
- No unresolved data coverage issues in the OOS window.
- Owner approval to advance.

**What RUNTIME_CANDIDATE means:**

- The strategy may enter small-live readiness evaluation.
- It still requires execution safety review, risk rule definition, and
  Owner approval before any live deployment.

---

## 6. Decision Flow

```
[Experiment Result]
        |
        v
[Trade count floors met?] --- No ---> INSUFFICIENT_EVIDENCE
        | Yes
        v
[Net PnL > 0 after costs?] --- No ---> REJECT
        | Yes
        v
[PF > 1.0 after costs?] --- No ---> REJECT
        | Yes
        v
[Top-1 net excluding > 0?] --- No ---> REJECT (single-trade dependent)
        | Yes
        v
[Top-3 net excluding > 0?]
        |          |
       Yes         No
        |          |
        v          v
[Top-5 net      PAUSE_FRAGILE
 excluding > 0?]   (requires further
   |        |      dimension review)
  Yes       No
   |        |
   v        v
[Year-by-   [Year-by-year
 year ok?]    ok?]
   |   |      |   |
  Yes  No    Yes  No
   |    |     |    |
   v    v     v    v
 PASS  Owner  Owner REJECT
       judges judges
       (may    (likely
       remain  reject)
       PASS)
```

Owner judgment is required at every branch point where the metrics are
borderline. The framework provides structure; it does not replace the
Owner.

---

## 7. Why Top-Winner Fragility Is Not Automatic Reject

### 7.1 The Trend-Following Reality

Every published trend-following system — from managed futures CTAs to
discretionary commodity traders — reports that a small number of large
winners pay for the majority of losing trades. This is a structural
feature, not a bug.

A sparse-trend strategy that shows zero top-winner concentration is
either:

- not actually capturing trends (winners are too small), or
- overfit to have artificially uniform outcomes.

Some concentration is expected and healthy.

### 7.2 When Concentration Becomes Fragility

Concentration crosses from expected to fragile when:

- The strategy cannot survive the removal of its best 3 trades.
- The best trades come from a narrow time window that may not repeat.
- The best trades are driven by events the rule does not systematically
  identify.
- Year-by-year profit depends on the same narrow cluster.
- Overlay testing confirms that the losing side cannot be managed without
  also cutting winners (as NSC-017 demonstrated).

### 7.3 The Correct Framing

Top-winner fragility is a **risk dimension**, not a binary verdict. It
must be evaluated alongside other dimensions:

- A strategy with top-3 negative but 3 independent positive years and
  high payoff ratio is fragile but has structural signal.
- A strategy with top-3 negative and only 1 positive year is more fragile.
- A strategy with top-3 negative, 1 positive year, and high funding
  exposure is most fragile.

The framework classifies the combined shape, not one metric.

---

## 8. Application To Future Direction Inspections

### 8.1 How This Framework Is Used

When a new strategy direction (Direction C, D, F, or any new direction)
completes an experiment:

1. Report top-1, top-3, top-5 net excluding.
2. Report year-by-year net PnL after costs.
3. Report MFE, MAE, maximum giveback.
4. Report realized and MTM MaxDD.
5. Report winner count and trade count.
6. Report funding cost in aggregate and per trade.
7. Apply the classification flow from Section 5.
8. If classification is PAUSE_FRAGILE, apply full dimension review from
   Section 4 before finalizing.

### 8.2 Pre-Registration

Each experiment plan (NSC series or equivalent) must state the fragility
gates before execution. The gates from this framework are the default.
Deviations require explicit Owner approval in the experiment plan.

### 8.3 No Retroactive Reclassification

This framework does not retroactively reclassify existing results.
Direction A remains `PAUSE_FRAGILE` under its own evaluation. If the
Owner wishes to re-evaluate Direction A using this framework, that
requires a separate, explicit task.

### 8.4 Direction-Specific Notes

| Direction | Status | Framework Application |
|-----------|--------|---------------------|
| Direction A (4h trend lifecycle) | PAUSE_FRAGILE | Already classified; not re-opened by this framework |
| Direction C | Reserve-only | Future inspect must apply Section 4 and 5 |
| Direction D | Reserve-only | Future inspect must apply Section 4 and 5 |
| Direction F | Reserve-only | Future inspect must apply Section 4 and 5 |
| Any new direction | Not yet defined | Must apply Section 4 and 5 |

---

## 9. Required Owner Judgment

The following decisions cannot be automated and require explicit Owner
input:

1. **Borderline top-3 removal**: When top-3 net excluding is near zero
   (within 10% of total net), the Owner decides whether to classify as
   PAUSE_FRAGILE or PASS based on other dimensions.

2. **Year concentration weight**: When 2 years dominate profit, the Owner
   decides whether the remaining years' near-breakeven is acceptable or
   whether it signals fragility.

3. **Winner attribution**: Whether top winners represent structural trend
   capture or event-driven outliers requires market-knowledge judgment.

4. **Overlay interaction**: Whether a tested overlay that worsens fragility
   means the direction is dead or means the overlay was wrong requires
   structural analysis.

5. **Progression from PAUSE_FRAGILE**: Whether continued research in the
   same direction is worthwhile versus returning to the Direction Map
   requires strategic judgment about research budget and direction
   potential.

6. **Funding exposure tolerance**: Whether a specific level of funding
   cost dependency is acceptable depends on the Owner's risk preferences
   and market outlook.

---

## 10. Connection To Strategy Direction Map Refresh

This framework is a prerequisite for the Strategy Direction Map refresh.

Before opening a new direction inspect:

- The framework provides default fragility gates that must be pre-registered
  in each new experiment plan.
- The framework eliminates the need for ad-hoc fragility judgment on each
  new result.
- The framework ensures that all directions are evaluated on the same
  dimensions with the same classification definitions.

The Direction Map refresh should:

1. Adopt this framework as the standard fragility evaluation method.
2. Pre-register these gates in each new direction's experiment plan.
3. Report all Section 4 dimensions in every experiment report.
4. Apply the Section 5 classification flow to every result.

---

## 11. Limitations And Known Gaps

1. **No automated winner attribution**: Determining whether a top winner
   is a structural trend capture or an event outlier requires human
   judgment and market context.

2. **No regime classification**: This framework does not define market
   regimes or require regime-level evaluation. That is a separate
   capability.

3. **No cross-strategy comparison**: This framework evaluates one strategy
   at a time. Portfolio-level fragility is out of scope.

4. **Research proxy caveat**: All thresholds assume the research adapter's
   cost model is realistic. If the cost model understates real execution
   costs, the fragility classification is optimistic.

5. **No live forward-test guidance**: This framework applies to backtest
   and OOS evidence. Live forward-test evaluation may require additional
   dimensions (execution latency, fill rate variance, exchange-specific
   funding patterns).

---

## 12. Explicit Non-Goals

- This document does not reclassify Direction A.
- This document does not approve Direction A promotion.
- This document does not authorize any experiment.
- This document does not authorize any runtime or profile change.
- This document does not reduce the evidence bar.
- This document does not override Owner judgment.
- This document does not define what constitutes a "good" strategy.
- This document does not apply to CPM-family pullback-continuation
  strategies.

---

## 13. Glossary

| Term | Definition |
|------|-----------|
| Top-N net excluding | Total net PnL minus the N largest individual winners |
| Sparse trend edge | A strategy with low win rate, high payoff ratio, and concentrated profit in rare large winners |
| Winner cluster | The group of top-N winners whose removal collapses net PnL |
| Giveback | The decline from MFE to realized PnL on a single trade |
| MTM MaxDD | Maximum drawdown including open-position mark-to-market |
| Winner attribution | Analysis of why a specific winner occurred and whether the frozen rule could systematically capture similar trades |
| PAUSE_FRAGILE | Classification meaning: real positive signal, but not robust enough for deployment |
| RESEARCH_PASS | Classification meaning: passes minimum fragility gates, may proceed to OOS |
| RUNTIME_CANDIDATE | Classification meaning: passed OOS validation, may enter small-live readiness |

---

## 14. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Initial framework v0 | Claude |
