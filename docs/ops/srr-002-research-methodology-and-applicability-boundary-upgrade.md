# SRR-002 - Research Methodology and Applicability Boundary Upgrade

**Task ID:** SRR-002
**Date:** 2026-05-08
**Status:** Completed / Docs-only methodology upgrade
**Authorization Level:** Level 1/2 - docs-only
**Source:** SRR-001 Option D recommendation; SMA-001 applicability map; VEI-003 Level 3 report; SSD-003 Level 3 report; MTC-006 Level 3 report; CPM-MOD-002 frozen diagnostic; LTF-002 15m role freeze; TE-007A validation task card
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a research methodology and applicability boundary upgrade.

It is not:

- a new strategy experiment;
- a direction task card;
- a backtest;
- a parameter search;
- a runtime or small-live admission review;
- a research adapter, strategy script, router, portfolio, or regime-engine plan;
- a gate relaxation;
- a rescue authorization for any paused or rejected module.

No backtest, script, adapter, parameter sweep, data pipeline, runtime/profile/
risk/backtester-core change, strategy promotion, small-live interpretation, or
automatic backlog promotion is authorized by SRR-002.

Binding current state:

- There is no runtime candidate.
- There is no deployable small-live strategy.
- The small-live readiness gate remains unmet.
- This document defines methodology standards; it does not satisfy them.
- Satisfying these standards requires future empirical evidence, not this
  document alone.

Primary docs inspected:

- `docs/ops/srr-001-strategy-research-reset-evidence-state-review.md`
- `docs/ops/sma-001-strategy-module-applicability-map.md`
- `docs/ops/vei-003-volatility-expansion-impulse-participation-level3-research-report.md`
- `docs/ops/ssd-003-short-side-breakdown-continuation-level3-research-report.md`
- `docs/ops/mtc-006-direction-d-structured-pullback-frozen-baseline-research-report.md`
- `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md`
- `docs/ops/ltf-002-15m-role-freeze-data-caveat-handling-plan.md`
- `docs/ops/te-007a-direction-a-official-validation-task-card.md`
- `docs/ops/mtc-001-main-trend-capture-fragility-evaluation-framework-v0.md`

---

## 1. Current Evidence-State Recap

### 1.1 Direction-Level Summary

| Direction | Classification | Key positive | Key negative | Hypothesis status |
| --- | --- | --- | --- | --- |
| Direction A | `PAUSE_FRAGILE` | 172 positions, net +2332.51, PF 1.42, real trend signal | Top-3 removal -935.73; top-5 -1812.81; 2023/2024 carry most net; 2022/2025 weak | Weakens standalone deployability; trend capture is real but too concentrated |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` | 14.3% overlap with A; net +2039.29, PF 1.405; structurally distinct | 63 trades, 10 winners; top-1 is 82.25% of net; top-3 removal -2471.12; MTM DD 15.01% | Thin sample; distinct signal but insufficient independent evidence |
| CPM-1 / CPM-MOD-002 | Paused; `HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION` | 2024/2025 preserved; ATR gate improved 2021 by +933.37, MTM DD 22.18% -> 10.59% | 2023 boundary unchanged; overall PF still below 1 after gate; favorable-year fragility | CPM-1 not deployable; one narrow gate partially supported; applicability incomplete |
| Direction D | `REJECTED_FROZEN_BASELINE` | 417 trades, 66 winners; structurally distinct from CPM-1 | Net -262.57, PF 0.985, MTM DD 29.78%; top-1 removal -3021.88; cost/churn dominate | Closed; lowers pullback-continuation family priority |
| SSD-003 | `REJECTED_FROZEN_BASELINE` | 0% overlap with A/C; structurally distinct | Net -1699.88, PF 0.317, 23 trades, 1 winner; 2021 strongly negative; 2022-2024 no trades | Closed; non-pullback short-side exhausted for this mechanism |
| VEI-003 | `PAUSE_FRAGILE` | 118 trades, 56 winners, net +630.49, PF 1.21; overlap gates passed | Independent signals net -329.02 PF 0.86; all positive PnL from A-overlap echo; top-3 removal -286.85 | Distinct signal set but not distinct alpha; bar-level impulse is Direction A echo |
| 15m auxiliary | `ROLE_FROZEN`; `NOT_LEVEL_3_READY` | Data available 2021-2025; role bounded as execution timing | Zero-volume bars; aggregation caveats; no frozen parent thesis | Auxiliary only; no 15m strategy path authorized |

### 1.2 Maximum Common Blocker (from SRR-001)

> No module has a validated, pre-observable applicability boundary that
> survives enough trades, enough winners, top-winner fragility, year
> concentration, independent-signal checks, MTM drawdown, and realistic costs.

### 1.3 Common Failure Pattern (from SRR-001 Section 2)

| Failure pattern | Where observed |
| --- | --- |
| Top-winner fragility | A, C, D, VEI, SSD |
| Top-3/top-5 removal turns negative | A, C, D, VEI |
| Year concentration without prior enablement rule | A, C, CPM-1, D, SSD |
| Independent signal failure | VEI |
| Positive evidence depends on overlap echo | VEI with A; A/D asymmetric |
| Trade or winner count insufficiency | C; SSD |
| Cost drag exceeds gross edge | CPM-1, D, VEI, SSD |
| MTM DD too high | C, D, SSD, CPM-1 OOS |
| Applicability boundary missing | All directions |
| OHLCV continuation vs exhaustion ambiguity | CPM-1, D, VEI, SSD |

---

## 2. Pre-Observable Applicability Boundary

### 2.1 Definition

A **pre-observable applicability boundary** for a module M is a rule B such that:

1. **B is computable before the trade/enablement decision.** B uses only
   information available at time t or earlier. It does not use the outcome of
   the trade that B is deciding about.

2. **B is not selected after seeing winning or losing years.** The boundary
   feature set, window, and threshold must be specified before any empirical
   check on the data that B will govern. If B is proposed after examining
   year-by-year results, it carries a post-hoc fitting penalty that must be
   explicitly disclosed and discounted.

3. **B survives realistic costs.** The boundary must be evaluated under the
   same fee, slippage, and funding assumptions as the module's frozen
   baseline. A boundary that works gross but fails net is not valid.

4. **B survives trade count and winner count floors.** The module must produce
   enough trades and enough winners inside B's valid state to support
   statistical evaluation. A boundary that admits 5 trades per year is not
   validated just because those 5 are profitable.

5. **B survives top-N removal.** Removing the top 1, 3, and 5 winners from
   the valid-state trade set must not turn aggregate net PnL negative. If
   top-3 removal turns negative, the boundary does not survive fragility
   testing.

6. **B survives winner-concentration check.** If a single winner contributes
   more than X% of valid-state net PnL, the boundary must disclose this
   concentration. The default X is 50%. Owner may adjust X; research may not.

7. **B survives year-concentration check.** If a single year contributes more
   than Y% of valid-state net PnL, the boundary must disclose this
   concentration. The default Y is 60%. Owner may adjust Y; research may not.

8. **B explains both valid and invalid states.** B must partition the
   backtest period into regions where the module is expected to be valid and
   regions where it is expected to be invalid. Both partitions must be
   non-empty. The invalid partition must contain at least one full calendar
   year or 20% of the total bars, whichever is smaller. B must not simply
   label all losing periods as "invalid" after the fact.

### 2.2 Post-Hoc Fitting Penalty

If a boundary B is proposed after examining year-by-year or period-by-period
results (i.e., the researcher saw which years were good and bad before choosing
B's features or threshold), B carries a **post-hoc fitting penalty**:

- The boundary must be tested on at least one period not used in its
  formulation. If the full sample was used to formulate B, B is automatically
  downgraded to `HYPOTHESIS_NOT_VALIDATED`.
- A boundary formulated on IS data and tested on OOS data without modification
  carries no penalty.
- A boundary formulated after seeing full-sample results, even if later
  "verified" on the same data, carries the maximum penalty and must be
  disclosed as `POST_HOC_BOUNDARY`.

### 2.3 Boundary Validation Checklist

Before any module claims a validated applicability boundary, the following
must be documented:

| Check | Requirement | Default threshold |
| --- | --- | --- |
| Pre-observable | B computable from information at time t or earlier | Mandatory |
| Not post-hoc selected | Features/window/threshold specified before empirical check | Mandatory |
| Cost survival | Net PnL positive under frozen cost model | Mandatory |
| Trade floor | >= 30 trades in valid state over full sample | 30 |
| Winner floor | >= 10 winners in valid state over full sample | 10 |
| Top-1 removal | Net PnL remains positive after removing top-1 winner | Mandatory |
| Top-3 removal | Net PnL remains positive after removing top-3 winners | Mandatory |
| Top-5 removal | Disclosed even if not blocking | Disclosure |
| Winner concentration | No single winner > 50% of valid-state net PnL | 50% |
| Year concentration | No single year > 60% of valid-state net PnL | 60% |
| MTM DD | MTM MaxDD < 15% in valid state | 15% |
| Invalid state non-empty | >= 1 full calendar year or 20% of bars | Mandatory |
| Both partitions explained | Valid and invalid states have stated market-feature explanations | Mandatory |

If any mandatory check fails, the boundary is not validated. The module
remains at its current classification. Disclosure items do not block
validation but must appear in any Level 3 report.

### 2.4 Current Status

No existing module has a validated pre-observable applicability boundary under
Section 2.3. This is the maximum common blocker identified by SRR-001 and
confirmed by SMA-001.

---

## 3. Independent Alpha vs Overlap Echo

### 3.1 Motivation

VEI-003 demonstrated that signal-set distinctness is not the same as
independent alpha. VEI passed overlap gates (Direction A 27.1%, Direction C
2.5%) but the 85 independent signals (no A/C overlap) were net negative
(-329.02, PF 0.86). All positive PnL came from the 33 A-overlapping signals
(+959.51). VEI's bar-level impulse detection is an echo of Direction A's
trend capture, not an independent profit source.

This section defines the standard for distinguishing independent alpha from
overlap echo in future research.

### 3.2 Definitions

**Signal overlap** between module M and reference module R is the fraction of
M's signals that occur within +/- K bars of an R signal, where K is the
overlap window (default: 2 bars for 4h, 4 bars for 1h).

**Overlap echo** occurs when:

1. M's overlapping signals produce positive PnL, AND
2. M's non-overlapping signals (independent signals) produce negative or
   insignificant PnL, AND
3. M's total positive PnL is explained by the overlapping subset.

If all three conditions hold, M is an overlap echo of R, regardless of
whether M passes the overlap percentage gate.

**Independent alpha** requires:

1. M's non-overlapping signals produce positive net PnL with PF >= 1.0, AND
2. M's non-overlapping signals contain enough winners to survive top-N
   fragility checks independently, AND
3. M's profit-source attribution shows that independent signals contribute a
   meaningful fraction of total positive PnL (default: >= 30%).

### 3.3 Independent Alpha Standard

For a module M to claim independent alpha relative to reference set {R1, R2, ...}:

| Check | Requirement | Default threshold |
| --- | --- | --- |
| Overlap gate | Signal overlap with each Ri < 50% | 50% per reference |
| Independent PnL | Non-overlapping signals net PnL > 0 | Mandatory |
| Independent PF | Non-overlapping signals PF >= 1.0 | 1.0 |
| Independent winner count | Non-overlapping signals >= 10 winners | 10 |
| Independent top-3 survival | Non-overlapping net PnL positive after top-3 removal | Mandatory |
| Profit-source attribution | Independent signals >= 30% of total positive PnL | 30% |
| Top-winner overlap accounting | If top-3 winners overlap R, disclose and discount | Disclosure |

If the overlap gate passes but independent PnL, PF, or winner count fails,
the module is classified as `PAUSE_FRAGILE` with notation "overlap echo of
[Ri]" rather than "independent alpha."

### 3.4 Profit-Source Attribution

Every Level 3 report must include a profit-source attribution table:

| Source | Signal count | Net PnL | PF | Winner count | Top-3 PnL | Top-3 overlap with R? |
| --- | --- | --- | --- | --- | --- | --- |
| Overlapping with R1 | ... | ... | ... | ... | ... | ... |
| Overlapping with R2 | ... | ... | ... | ... | ... | ... |
| Independent (no overlap) | ... | ... | ... | ... | ... | ... |
| Total | ... | ... | ... | ... | ... | ... |

If the independent row is negative or insignificant, the module must state
that its profit source is overlap echo, not independent alpha.

### 3.5 Application to Current Evidence

| Module | Overlap gate | Independent PnL | Independent alpha? | Classification impact |
| --- | --- | --- | --- | --- |
| VEI vs Direction A | Passed (27.1%) | -329.02, PF 0.86 | No | Confirmed as overlap echo of A |
| Direction C vs Direction A | Passed (14.3%) | Not separately computed in MTC-004 | Unknown | Requires attribution if reopened |
| Direction D vs Direction A | 29.50% overlap | Not separately computed | Unknown | Rejected on own evidence; attribution not needed |
| SSD-003 vs A/C | 0% / 0% | N/A (net negative overall) | N/A | Rejected on own evidence |

---

## 4. Sparse Trend Fragility Standard

### 4.1 Motivation

Direction A (19.19% win rate, average winner ~6x average loser) and Direction
C (15.9% win rate, top-1 = 82.25% of net) demonstrate that sparse trend
systems naturally concentrate winners. This concentration is expected and not
automatically invalid.

However, current candidates fail top-3/top-5 removal too often. The standard
must balance two truths:

1. **Sparse trend winners are expected.** A trend-capture system that catches
   3-5 major moves per year and loses on many false breakouts is structurally
   sound. Top winners are not automatically invalid.

2. **Concentration beyond a threshold is a deployment blocker.** If removing
   the top 3 winners turns the system negative, the system's positive
   expectation depends on a cluster that cannot be predicted in advance. This
   is not deployable.

### 4.2 Acceptable vs Unacceptable Concentration

| Metric | Acceptable | Unacceptable | Deployment blocker |
| --- | --- | --- | --- |
| Top-1 as % of net PnL | < 40% | >= 40% | No (disclosure only) |
| Top-3 removal net PnL | Remains positive | Turns negative | Yes |
| Top-5 removal net PnL | Remains positive | Turns negative | Yes |
| Top-3 as % of gross winners | < 60% | >= 60% | No (disclosure only) |
| Single year as % of net PnL | < 60% | >= 60% | Yes (unless pre-observable boundary explains) |
| Cross-year positive year count | >= 3 of 5 | < 3 of 5 | Yes |

### 4.3 Top-Winner Attribution Requirements

If top-3 winners contribute > 50% of net PnL, the Level 3 report must
include:

1. **Market context for each top winner.** What was the market state (trend
   phase, volatility regime, ATR percentile, recent return) when each top
   winner was entered?

2. **Cross-year distribution.** Do top winners cluster in one year or
   distribute across years? If all top-3 are in one year, that is a stronger
   fragility signal than if they span three years.

3. **Regime attribution.** Can a pre-observable feature distinguish the
   regimes that produced top winners from regimes that did not? If not, the
   concentration is unexplained and the module remains `PAUSE_FRAGILE`.

4. **Independent-signal check for top winners.** If top winners overlap with
   a reference module's signals, the attribution must disclose this. A module
   whose top winners are also another module's top winners is not
   independently deployable.

### 4.4 Sparse Trend Acceptance Band

A module M with sparse trend characteristics passes the fragility standard if:

- Top-3 removal net PnL remains positive (mandatory).
- Top-5 removal net PnL remains positive (mandatory).
- Top winners are distributed across >= 2 calendar years (mandatory).
- Top-3 winners have stated market-feature explanations (mandatory).
- If top-1 > 40% of net, this is disclosed but does not block research-only
  classification (Owner decision for deployment).

A module that passes the acceptance band may be classified as
`PAUSE_FRAGILE` (research evidence preserved) but not as `DEPLOYABLE` or
`SMALL_LIVE_READY` unless the pre-observable applicability boundary (Section
2) is also validated.

### 4.5 Application to Current Evidence

| Module | Top-3 removal | Top-5 removal | Cross-year | Passes? |
| --- | --- | --- | --- | --- |
| Direction A | -935.73 (negative) | -1812.81 (negative) | 2023/2024 carry most | No |
| Direction C | -2471.12 (negative) | -3861.04 (negative) | 3 positive years but thin | No |
| Direction D | -5788.16 (negative) | -7331.08 (negative) | 2024 only | No |
| VEI-003 | -286.85 (negative) | Not computed | 2022-2025 positive | No |
| SSD-003 | -2488.50 (1 winner) | N/A | 2025 only | No |

No current module passes the sparse trend fragility standard.

---

## 5. Conditional Module Evidence Standard

### 5.1 Motivation

CPM-MOD-002 demonstrated that a module may have applicable-market evidence
without deployment permission. The frozen ATR percentile gate improved 2021
by +933.37 and cut MTM DD from 22.18% to 10.59%, but:

- The 2023 failure boundary remains unidentified.
- The gate was formulated after examining year-by-year results (post-hoc
  fitting penalty applies).
- The gate does not validate CPM-1 dynamic enablement in general.

This section defines how to evaluate a module that should only trade in
certain regimes, and how to prevent post-hoc no-trade gate fitting.

### 5.2 Conditional Module Definition

A **conditional module** M is a module that is expected to be valid only in
certain market states S_valid and invalid in other states S_invalid, where:

- S_valid and S_invalid are defined by pre-observable features (Section 2).
- S_valid union S_invalid covers the full sample.
- S_valid and S_invalid are both non-empty.
- The partition is stated before any empirical check on the data it governs.

### 5.3 Evidence Requirements for Conditional Validity

For a conditional module M with boundary B to claim conditional validity:

| Check | Requirement |
| --- | --- |
| Boundary B is pre-observable | Section 2.1 all conditions |
| B was not formulated post-hoc | Section 2.2 penalty rules apply |
| Valid-state evidence | M passes sparse trend fragility standard (Section 4) inside S_valid |
| Invalid-state explanation | S_invalid has a stated market-feature explanation for why M fails there |
| Invalid-state non-empty | S_invalid contains >= 1 full calendar year or 20% of bars |
| Cost survival in valid state | Net PnL positive under frozen cost model inside S_valid |
| MTM DD in valid state | MTM MaxDD < 15% inside S_valid |
| No cherry-picked valid state | B's valid state must not be equivalent to "skip the losing years" |

### 5.4 Post-Hoc No-Trade Gate Prevention

A **no-trade gate** is any rule that disables trading in certain periods. A
no-trade gate is **post-hoc** if it was designed after seeing which periods
were profitable and which were not.

Prevention rules:

1. **Gate features must be specified before empirical check.** If the
   researcher proposes a gate after examining year-by-year results, the gate
   carries a post-hoc fitting penalty (Section 2.2).

2. **Gate must improve a period not used in formulation.** CPM-MOD-002's
   ATR percentile gate was formulated after seeing 2021-2025 results. It
   improves 2021 but does not change 2022-2025 trade sets. This is partial
   evidence with post-hoc penalty, not validated conditional enablement.

3. **Gate must not be equivalent to "skip bad years."** If the gate's valid
   state is approximately the set of positive-PnL years, the gate is a
   relabeled year filter, not a market-state boundary.

4. **Gate must have a stated invalid-state mechanism.** The gate must explain
   *why* the module fails in the invalid state, not just *that* it fails.
   "High volatility causes stop-outs" is a mechanism. "2023 was bad" is not.

5. **Multiple gates compound the penalty.** If a second gate is added after
   the first gate's results are known, the compound post-hoc penalty
   increases. Each additional gate must be justified by a pre-observable
   hypothesis stated before the first gate's results were examined.

### 5.5 Dynamic Enablement Discussion Prerequisites

Before any dynamic enablement discussion (runtime switching, router input,
regime engine input) is authorized for a conditional module:

1. The module must have a validated pre-observable applicability boundary
   (Section 2.3 all checks passed).
2. The boundary must have no post-hoc fitting penalty (Section 2.2).
3. The valid-state evidence must pass the sparse trend fragility standard
   (Section 4.4).
4. The invalid-state explanation must be documented and non-trivial.
5. At least one independent validation period must confirm the boundary
   outside the formulation sample.

No current module satisfies these prerequisites. CPM-MOD-002 satisfies #4
partially (high-volatility damage mechanism stated) but fails #1 (boundary
not fully validated), #2 (post-hoc penalty applies), #3 (top-N fragility
remains), and #5 (no independent validation period).

---

## 6. Extra-Data Dependency Standard

### 6.1 Motivation

SRR-001 identified "Missing extra data such as funding/OI/liquidation/
taker-flow" as a plausible future hypothesis but not proven. The recurring
OHLCV-only continuation vs exhaustion ambiguity suggests that some failures
may be asking questions OHLCV cannot answer.

However, introducing extra data carries risks:

- Scope creep into data pipeline or feature store.
- Funding/OI rescue of failed modules without a separate inspect.
- Hidden overfitting from larger feature spaces.
- Data quality, alignment, and survival issues.

### 6.2 When Extra Data Is Legitimate

Extra data source D is legitimate for hypothesis H if:

1. **H is a named hypothesis with a stated failure mechanism.** "Funding rate
   may identify crowded long positions that precede sharp reversals" is a
   named hypothesis. "Extra data might help CPM-1" is not.

2. **D addresses a specific ambiguity that OHLCV cannot resolve.** The
   current recurring ambiguity is continuation vs exhaustion: closed OHLCV
   detects movement but not whether that movement is continuation, exhaustion,
   squeeze, or churn. If D can plausibly distinguish these states, D is
   legitimate for inspect.

3. **D is proposed before examining D's empirical relationship with the
   module's outcomes.** If D is proposed after seeing that a module fails
   and then checking whether D correlates with the failures, D carries a
   post-hoc rescue penalty.

4. **D does not require a data pipeline before the hypothesis is accepted.**
   The inspect must be docs-only. No ingestion, schema, adapter, or data
   repair is authorized until the hypothesis is accepted by Owner.

5. **D's data quality, availability, and survival characteristics are
   documented.** Funding rate availability, historical depth, exchange
   coverage, and known gaps must be stated before any empirical claim.

### 6.3 When Extra Data Is Rescue Narrative

Extra data source D is a **rescue narrative** if:

1. **D is proposed after a module's frozen baseline fails, without a
   separate hypothesis.** "Maybe funding rate would fix CPM-1" after CPM-1
   OOS failure is rescue narrative unless a named hypothesis states exactly
   how and why.

2. **D is proposed for multiple failed modules simultaneously.** If the same
   extra data source is claimed to rescue CPM-1, Direction D, and VEI, the
   claim is likely overfitting to a common failure pattern rather than
   addressing a specific mechanism.

3. **D's proposed role is not bounded.** "Funding rate as a filter" is
   bounded. "Funding rate plus OI plus liquidations plus taker flow plus
   mark-index spread" is unbounded and likely rescue narrative.

4. **D would require runtime infrastructure changes before evidence.** If
   the proposal requires building a data pipeline, feature store, or
   router before producing any evidence, it is premature.

### 6.4 Extra-Data Decision Framework

| Condition | Classification | Next step |
| --- | --- | --- |
| Named hypothesis + specific ambiguity + docs-only inspect | Legitimate | Proceed with Level 1/2 inspect |
| Named hypothesis + specific ambiguity + requires pipeline | Legitimate but premature | Accept hypothesis; defer pipeline to Owner decision |
| No named hypothesis + proposed after failure | Rescue narrative | Reject; do not authorize |
| Multiple failed modules + same data source | Likely rescue narrative | Require separate hypothesis per module |
| Unbounded data role | Rescue narrative | Reject; require bounded role definition |

### 6.5 Current Status

No extra-data hypothesis has been proposed or accepted. The OHLCV-only
continuation vs exhaustion ambiguity is a legitimate motivation for a future
data-dependency inspect (SRR-001 Option B), but:

- No specific data source has been named.
- No named hypothesis has been formulated.
- No data pipeline is authorized.
- No failed module may claim extra-data rescue without a separate inspect.

---

## 7. Future Level 3 Admission Gate

### 7.1 Motivation

SMA-001 Section 9 defined Level 3 admission requirements. SRR-002 upgrades
these requirements based on the methodology standards defined in Sections 2-6.

### 7.2 Admission Requirements

A future Level 3 request for module M is admissible only if all of the
following are satisfied:

| # | Requirement | Rationale |
| --- | --- | --- |
| 1 | **Frozen mechanism.** M's entry, exit, lifecycle, same-bar policy, and cost model are fully specified and frozen before any empirical run. | Prevents in-flight adaptation |
| 2 | **Clear information gain.** The Level 3 run will produce evidence that changes future routing decisions regardless of outcome. If both success and failure lead to the same next step, the run has no information gain. | Prevents low-value branches |
| 3 | **Failure closure statement.** Before the run, state what hypothesis H will be closed or weakened if the run fails. "H: mechanism X produces independent alpha under constraints Y" is a valid hypothesis. "Maybe this will work" is not. | Ensures runs close questions rather than spawn branches |
| 4 | **No variants if failed.** If the Level 3 run fails, no parameter variant, threshold adjustment, feature addition, timeframe change, or data rescue is automatically authorized. Any follow-up requires a new Owner-approved Level 1/2 inspect. | Prevents rescue branch generation |
| 5 | **No runtime interpretation.** The Level 3 run is research-only. A positive result does not imply runtime readiness, small-live readiness, or deployment permission. Runtime readiness requires separate validation of the pre-observable applicability boundary (Section 2). | Prevents promotion by positive result |
| 6 | **No automatic promotion.** A positive Level 3 result changes the module's classification (e.g., from `INSUFFICIENT_EVIDENCE` to `PAUSE_FRAGILE` or `CONDITIONAL_EVIDENCE`) but does not promote to `DEPLOYABLE` or `SMALL_LIVE_READY`. | Prevents skipping governance |
| 7 | **Pre-observable applicability hypothesis.** M must state its expected valid and invalid market states before the run, even if the boundary is not yet validated. | Ensures boundary awareness from design |
| 8 | **Overlap and independence plan.** M must state how overlap with existing modules will be measured and how independent alpha will be assessed (Section 3). | Prevents overlap echo from being discovered only post-hoc |
| 9 | **Fragility gates pre-registered.** M must state which top-N removal checks and concentration checks will be applied before seeing results. | Prevents gate relaxation after result |
| 10 | **Data dependency declared.** If M requires any data beyond OHLCV, the data source, hypothesis, and quality characteristics must be declared (Section 6). | Prevents hidden data pipeline |

### 7.3 Inadmissible Requests

A Level 3 request is **inadmissible** if:

- It would only create a new branch on failure (no closure statement).
- It is a parameter variant of a failed or paused module.
- It adds a feature to a failed module without a new named hypothesis.
- It changes timeframe, overlay, or exit of a paused module.
- It proposes dynamic enablement without validated boundary (Section 5.5).
- It requires extra data without a named hypothesis (Section 6.2).
- Its mechanism is not structurally distinct from existing family members
  (overlap > 50% or same profit source).

### 7.4 Current Admissibility Status

| Module | Admissible? | Blocking reason |
| --- | --- | --- |
| Direction A variants | No | Parameter variant of paused module |
| Direction C threshold adjustment | No | Parameter variant of paused module |
| CPM-MOD-003 | No | Second gate on paused module; compound post-hoc penalty |
| Direction D variants | No | Parameter/zone/EMA/confirmation variant of rejected module |
| SSD-003 variants | No | Variant of rejected module |
| VEI variants | No | Variant of paused module |
| 15m pullback-entry | No | Pullback-continuation family rescue; no different mechanism |
| 15m independent strategy | No | Not Level 3 ready; role frozen as auxiliary |
| New direction (if proposed) | Conditional | Must satisfy all 10 requirements above |

---

## 8. TE Path

### 8.1 Motivation

Direction A's official validation (TE-007A) is a separate evidence-hardening
path. It must not be conflated with strategy promotion, small-live readiness,
or methodology upgrade.

### 8.2 TE-007A Framing Rules

1. **Direction A official validation can remain a separate evidence-hardening
   path.** TE-007A tests whether Direction A's sparse trend signal survives
   longer-window validation with supplemental data. This is a legitimate
   research question independent of the methodology upgrade.

2. **TE-007A must not be framed as promotion.** A positive TE-007A result
   means Direction A's evidence is hardened, not that Direction A is
   deployable. Deployment requires validated applicability boundary (Section
   2), independent alpha (Section 3), and fragility standard passage (Section
   4).

3. **TE-007A must not be framed as small-live readiness.** Small-live
   readiness requires all gates in Sections 2-5 to be satisfied. TE-007A
   addresses only one dimension (longer-window evidence quality).

4. **TE-005 2019-Q4 data inconsistency must be resolved or supplemental
   window adjusted before TE-007A execution.** If the 2019-Q4 data used in
   the supplemental window has known inconsistencies, running TE-007A on
   that data would produce unreliable evidence. The inconsistency must be
   resolved first, or the supplemental window must be adjusted to exclude
   the inconsistent period.

5. **TE-007A results must be evaluated under SRR-002 methodology.** Even if
   TE-007A produces positive results, the evaluation must apply the
   pre-observable applicability boundary standard (Section 2), independent
   alpha standard (Section 3), and sparse trend fragility standard (Section
   4). A longer-window positive that fails top-3 removal is still
   `PAUSE_FRAGILE`.

### 8.3 TE Path and Methodology Upgrade Relationship

The TE path and the SRR-002 methodology upgrade are complementary but
independent:

- SRR-002 defines *how* to evaluate evidence. It does not produce new
  evidence.
- TE-007A produces *new evidence* for one direction. It must be evaluated
  using SRR-002 standards.
- A positive TE-007A does not validate the methodology. The methodology is
  validated by its logical structure, not by empirical outcomes.
- A negative TE-007A does not invalidate the methodology. The methodology
  would still apply to any future module.

---

## 9. Summary of Standards

| Standard | Section | What it defines | Current satisfaction |
| --- | --- | --- | --- |
| Pre-observable applicability boundary | 2 | What qualifies as a validated boundary | No module satisfies |
| Independent alpha vs overlap echo | 3 | How to distinguish independent profit from overlap echo | VEI confirmed as echo; no module claims independent alpha |
| Sparse trend fragility | 4 | Acceptable vs unacceptable concentration for sparse systems | No module passes |
| Conditional module evidence | 5 | How to evaluate regime-conditional modules without post-hoc fitting | CPM-MOD-002 partial; no module satisfies all prerequisites |
| Extra-data dependency | 6 | When extra data is legitimate vs rescue narrative | No hypothesis proposed; no data authorized |
| Level 3 admission gate | 7 | What makes a future Level 3 request admissible | No current request admissible |
| TE path framing | 8 | How TE-007A relates to methodology and promotion | TE-007A must not be framed as promotion or small-live readiness |

---

## 10. Explicit Prohibitions

SRR-002 explicitly prohibits:

- backtests;
- research scripts or adapters;
- parameter sweeps;
- runtime/profile/risk/backtester-core changes;
- small-live approval;
- strategy promotion;
- strategy router, portfolio engine, or regime engine;
- new data pipelines;
- CPM rescue or CPM-MOD-003;
- Direction A rescue;
- Direction C rescue;
- Direction D variants;
- SSD-003 variants;
- VEI variants;
- 15m pullback-entry Level 3;
- 15m independent strategy Level 3;
- 1h entry search;
- overlay stacking;
- funding/OI rescue without named hypothesis;
- automatic data pipeline work;
- interpreting any methodology standard as satisfied without empirical evidence;
- interpreting this document as satisfying the small-live readiness gate;
- interpreting TE-007A as promotion or small-live readiness;
- relaxing any default threshold (50% winner concentration, 60% year
  concentration, 30% independent PnL attribution, 15% MTM DD) without Owner
  decision;
- proposing a Level 3 request that does not satisfy all 10 admission
  requirements in Section 7.2;
- automatic promotion of any backlog candidate.

---

## 11. Owner Summary

### 11.1 What SRR-002 Does

SRR-002 defines seven methodology standards that address the maximum common
blocker identified by SRR-001:

1. Pre-observable applicability boundary (Section 2).
2. Independent alpha vs overlap echo (Section 3).
3. Sparse trend fragility (Section 4).
4. Conditional module evidence (Section 5).
5. Extra-data dependency (Section 6).
6. Level 3 admission gate (Section 7).
7. TE path framing (Section 8).

These standards are logical frameworks. They do not produce empirical evidence
or runtime candidates. They define what evidence must look like before it can
change a module's classification or deployment state.

### 11.2 What SRR-002 Does Not Do

- It does not relax any gate.
- It does not authorize any backtest, script, adapter, or data pipeline.
- It does not produce a runtime candidate or small-live candidate.
- It does not satisfy the small-live readiness gate.
- It does not rescue any paused or rejected module.
- It does not authorize TE-007A execution (that requires separate Owner
  approval).
- It does not change any module's current classification.

### 11.3 Impact on Current Classifications

| Module | Classification before SRR-002 | Classification after SRR-002 | Change |
| --- | --- | --- | --- |
| Direction A | `PAUSE_FRAGILE` | `PAUSE_FRAGILE` | None |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` | None |
| CPM-1 | Paused; partial hypothesis | Paused; partial hypothesis | None |
| Direction D | `REJECTED_FROZEN_BASELINE` | `REJECTED_FROZEN_BASELINE` | None |
| SSD-003 | `REJECTED_FROZEN_BASELINE` | `REJECTED_FROZEN_BASELINE` | None |
| VEI-003 | `PAUSE_FRAGILE` | `PAUSE_FRAGILE` | None |
| 15m auxiliary | `ROLE_FROZEN`; `NOT_LEVEL_3_READY` | `ROLE_FROZEN`; `NOT_LEVEL_3_READY` | None |

### 11.4 Impact on Future Research

Any future Level 3 request must satisfy all 10 admission requirements in
Section 7.2. This raises the evidence bar for future research but does not
close the research space. A genuinely new mechanism with a pre-observable
boundary hypothesis, overlap plan, and failure closure statement can still
be proposed.

### 11.5 Recommended Next Steps

1. Apply SRR-002 standards to any future Level 3 request.
2. TE-007A may proceed as a separate evidence-hardening path if Owner
   approves, subject to Section 8 framing rules and TE-005 data consistency
   resolution.
3. Data-dependency inspect (SRR-001 Option B) may proceed as a docs-only
   inspect if Owner approves, subject to Section 6 standards.
4. Strategy direction refresh (SRR-001 Option F) may proceed after SRR-002
   methodology is accepted, subject to Section 7 admission requirements for
   any resulting Level 3 request.
5. No rescue, variant, or parameter adjustment of any paused or rejected
   module is authorized.

### 11.6 Small-Live Readiness

Small-live readiness gate remains unmet.

There is still:

- no runtime candidate;
- no deployable small-live strategy;
- no strategy module ready for promotion;
- no authorization to change runtime/profile/risk or live behavior.

SRR-002 defines the standards that a future module must satisfy to reach
small-live readiness. Satisfying those standards requires empirical evidence
that does not currently exist.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-08 | Initial SRR-002 research methodology and applicability boundary upgrade | Codex |
