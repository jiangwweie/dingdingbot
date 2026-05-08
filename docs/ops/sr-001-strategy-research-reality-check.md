# SR-001 - Strategy Research Reality Check / Strategy Module Applicability Review

**Task ID:** SR-001
**Date:** 2026-05-07
**Status:** Completed / Owner research-route review
**Authorization Level:** Level 1/2 - docs-only
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a total-control research review and strategy-route judgment.
It is not a new strategy experiment, parameter optimization, runtime task,
promotion review, small-live readiness review, live deployment recommendation,
or backtester-core task.

No backtest, adapter, code, runtime profile, risk rule, production strategy,
configuration, migration, or research-engine change is authorized by this
document.

Primary evidence inspected:

- Direction A / NSC-014 / TE-007A: 4h main trend lifecycle evidence.
- Direction B-D1 / NSC-020: 1h follow-through entry timing evidence.
- Direction C / MTC-004: volatility contraction frozen baseline report.
- CPM-1 OOS classification and CPM-MOD-001 applicability inspect.
- Direction D / MTC-005: structured pullback / value-zone inspect.
- MTC-001 fragility evaluation framework.
- MTC-002 strategy direction map refresh.
- Project roadmap and live-safe governance docs.

---

## 1. Current Research Value

### 1.1 Judgment

Strategy research still has value. The correct conclusion is not "there is no
hope." The correct conclusion is:

> There is currently no deployable candidate, and the research mode must shift
> from "find the next frozen baseline" to "understand module applicability and
> pre-observable validity gates."

The existing research has produced real information:

- Direction A shows a real 4h main-trend signal, but remains `PAUSE_FRAGILE`.
- Direction B-D1 shows that 1h entry timing provides only marginal improvement
  and does not solve fragility.
- Direction C shows a structurally different signal set with low overlap to
  Direction A, but sample and winner counts are too thin.
- CPM-1 shows that pullback-continuation can work in 2024/2025-like conditions,
  but failed badly in 2021 and 2023.
- Direction D may be structurally different from CPM-1, but it remains inside
  the pullback-continuation family and must carry a higher evidence burden.

### 1.2 Positive Evidence

| Evidence | Why it matters | Limitation |
| --- | --- | --- |
| Direction A net/PF/trade count positive | 4h ETH main-trend capture is not empty noise | Top-3/top-5 removal remains negative |
| Direction B-D1 preserves A's major winners | 1h confirmation did not destroy the payoff tail | Improvement is marginal and entry quality mixed |
| Direction C overlap with A is low | Distinct mechanisms can be found | Only 63 trades and 10 winners; worse concentration |
| CPM-1 2024/2025 positive years | Conditional module edge may exist | 2021/2023 are severe counter-evidence |
| Direction D mechanism is non-Pinbar, 4h, zone-based | Not merely a CPM-1 parameter tweak | Still asks the same pullback-ending question |

### 1.3 Negative Evidence

| Evidence | Meaning |
| --- | --- |
| A and B-D1 remain top-winner fragile | Incremental changes around Donchian20 do not solve the core blocker |
| C has only 10 winners | Payoff ratio and fragility estimates are not reliable |
| CPM-1 2021 OOS has negative gross edge | Pullback-continuation failed in a nominally favorable bull year |
| CPM hard filters / coarse gates have failed | Ex-ante enablement is plausible but unproven |
| Research-only adapters are not runtime candidates | Evidence cannot jump directly to deployment |

### 1.4 Maximum Blocker

The maximum blocker is not one bad metric. It is the absence of a validated,
pre-observable applicability boundary.

The project can tolerate a strategy module that does not trade all years. It
cannot tolerate a module whose no-trade or enablement rule is discovered only
after seeing which years won and lost.

---

## 2. Current Failure Modes

### 2.1 Top-Winner Fragility

This is the dominant repeated blocker.

- Direction A: top-1 survives, but top-3/top-5 removal turns net negative.
- Direction B-D1: top-3/top-5 removal remains negative despite marginally
  better net/PF/DD.
- Direction C: top-1 is 82.25% of net and top-3 exclusion is much worse than
  Direction A.

Sparse trend systems naturally depend on a small payoff tail, but current
results still rely on too narrow a winner cluster to justify promotion or
small-live candidacy.

### 2.2 Winner Count / Trade Count Insufficiency

Direction C is the cleanest example:

- total trades: 63;
- 2021+2022 trades: 14, just below floor;
- winners: 10, below the 15-winner minimum;
- top-N removal becomes statistically unstable.

When a direction produces too few trades or too few winners, a positive net/PF
is useful research signal but not enough evidence.

### 2.3 Year Concentration

Direction A and B-D1 are dominated by 2023/2024. Direction C has multiple
positive years, but its net is still carried by very few trades. CPM-1's
positive evidence is concentrated in 2024/2025, while 2021/2023 are severe
counter-evidence.

Year concentration is not automatic rejection, but it requires a prior
applicability hypothesis. "The strategy works in the years where it worked" is
not an acceptable gate.

### 2.4 Module Applicability Boundary Is Unclear

The Owner's updated principle is correct: a single module does not need to be
all-weather. But this raises the evidence bar for applicability.

Each module now needs:

- a defined market structure it claims to exploit;
- a market state where it is expected not to work;
- pre-observable conditions that identify those states;
- stop conditions if the boundary fails.

CPM-1 has the most explicit applicability question, but it has not yet proven
that volatility or ATR-style gates can separate good from bad periods without
post-hoc fitting.

### 2.5 No-Trade / Gate Post-Hoc Fitting Risk

This is now a first-class research risk.

No-trade conditions are invalid if they are selected after observing that 2021,
2022, 2023, or 2025 were bad. A gate is only research-valid if its feature,
window, threshold, and classification logic are defined before execution and
use only ex-ante observable data.

### 2.6 Pullback-Continuation Family Risk

CPM-1, CPM-2, CPM-MOD, Direction D, and any future 15m pullback-entry layer all
touch the same family question:

> Can an ETH trend pullback be identified as "ended" before continuation
> resumes?

CPM-1's failure does not conclusively reject the family, but it makes the
family suspect. Any further pullback-continuation experiment must prove it is
not just CPM-1 repackaged through a different trigger.

### 2.7 Why Existing Research Cannot Upgrade Runtime

None of the current results can upgrade to runtime because:

- Direction A / B-D1 are `PAUSE_FRAGILE`, not `RESEARCH_PASS`.
- Direction C is `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`.
- CPM-1 is paused after 2021/2022 OOS failure and is not a small-live
  candidate.
- CPM 2024/2025 are applicable-market evidence only, not deployment
  permission.
- Direction D is inspect-only and has no empirical result.
- 15m is only a lower-timeframe research possibility, not an authorized
  experiment.
- No module has a validated, pre-observable applicability gate.
- Research-only evidence does not modify runtime profiles, strategy
  enablement, risk rules, or deployment status.

---

## 3. Research Mode Adjustment

### 3.1 Should We Continue One Frozen Baseline After Another?

Not as the default mode.

Frozen baselines remain valuable when the mechanism is structurally clear and
the experiment has high information gain. But continuing a sequence of isolated
frozen baselines risks producing many "positive but fragile" artifacts without
answering the central question: when is each module valid?

Recommended adjustment:

- Stop micro-variants around already fragile branches.
- Do not continue Direction A/B-D1 variants.
- Do not loosen Direction C thresholds after seeing thin evidence.
- Do not start Direction D as "just another baseline" without applicability
  and CPM drift framing.

### 3.2 Shift To Strategy Module Applicability / Validity Gate

Yes. The research should shift toward a Strategy Module Applicability framework.

The framework should compare A / C / CPM / D on:

- mechanism identity;
- expected applicable market;
- expected non-applicable market;
- ex-ante observable validity features;
- trade/winner count feasibility;
- top-winner fragility profile;
- year and regime concentration;
- family overlap and drift risk;
- what result would close the module.

15m / sub-1h should be included as a lower-timeframe auxiliary-layer
candidate, not as an immediate independent strategy mainline.

This is not a strategy router. It is a research classification map that says
which modules are worth testing, under what validity hypothesis, and when to
stop.

The map should be created before the next single-point experiment because it
forces every candidate to declare its role, boundary, evidence burden, and
failure closure condition.

### 3.3 Lower Short-Term Small-Live Expectations

Yes. The short-term expectation should be lowered.

The current work should be treated as research triage and foundation hardening,
not as near-term small-live candidate discovery. Live-safe foundation work
remains valid, but it does not imply strategy readiness.

---

## 4. CPM-MOD-002 vs Direction D vs Applicability Map

### 4.1 Comparison

| Path | Question | Strength | Main Risk | Authorization |
| --- | --- | --- | --- | --- |
| CPM-MOD-002 | Can existing CPM-1 be enabled/disabled by one frozen, pre-registered volatility validity gate? | Uses known failure and known positive years; high family-level information gain | Gate may be post-hoc or too coarse; 2021 remains hard counter-evidence | Needs Owner Level 3 |
| Direction D Level 3 | Does a new 4h structured value-zone pullback mechanism work better than CPM-1 and A/C? | Tests a genuinely different pullback mechanism: 4h, zone, EMA20 reclaim, lifecycle exit | May still be CPM-family failure in different clothing | Needs Owner Level 3 |
| Strategy Module Applicability Map | How should A / C / CPM / D / 15m auxiliary layer be compared as conditional modules or candidate layers? | Docs-only, clarifies route before spending Level 3 budget | Does not produce empirical result by itself | Level 1/2 docs-only |

### 4.2 CPM-MOD-002 Scope Correction

CPM-MOD-001's earlier recommendation should be read as:

> **RECOMMEND_LEVEL_3_FROZEN_DIAGNOSTIC**

It should not be read as automatic experiment authorization.

If Owner later authorizes CPM-MOD-002, first-round scope must be:

- one pre-registered volatility gate only;
- no composite M0 score;
- no E4 soft label;
- no position sizing;
- no multi-factor regime search;
- no dynamic strategy router, portfolio allocation, or runtime switching;
- no CPM-1 parameter change;
- no automatic small-live conclusion even if the diagnostic is positive.

The 2024/2025 preservation tolerance and favorable-year trade-count floor are
Owner risk/reward choices, not automatic acceptance thresholds. A diagnostic
can report trade-off curves only if pre-authorized; SR-001 does not authorize
that.

### 4.3 Recommended Order

Recommended order:

1. **Strategy Module Applicability Map** - immediate Level 1/2 docs-only.
2. **15m inspect-only role definition inside that map** - candidate layer, not
   an experiment.
3. **CPM-MOD-002** - first Level 3 frozen diagnostic if Owner wants one
   empirical diagnostic.
4. **Direction D Level 3** - later Level 3, only after the map and preferably
   after CPM-MOD-002, unless Owner explicitly chooses to spend Level 3 budget
   on D first.
5. **Pause new experiments** if Owner does not want to authorize Level 3 now.

Rationale:

- The Applicability Map is cheapest and prevents the next experiment from
  becoming another isolated baseline.
- 15m can be captured as a candidate layer without silently becoming a
  backtest or mainline.
- CPM-MOD-002 has the highest immediate information gain for the
  pullback-continuation family because it tests whether the known CPM-1 regime
  split is identifiable ex-ante.
- Direction D is worth preserving, but should not leapfrog the CPM drift
  question unless Owner deliberately accepts that risk.

---

## 5. Pullback-Continuation Family Judgment

### 5.1 Does CPM-1 Failure Reject The Whole Family?

No. CPM-1 failure is not sufficient by itself to reject the entire
pullback-continuation family.

It rejects CPM-1 as a deployable candidate and blocks CPM-1 rescue. It also
raises the burden for every related direction. But Direction D changes the
timeframe, location definition, confirmation type, and exit philosophy enough
that one carefully bounded Level 3 experiment can still be justified.

### 5.2 Is Direction D Different Enough For One Level 3 Opportunity?

Yes, conditionally.

Direction D is different enough if and only if it remains:

- 4h primary;
- zone-based;
- structural confirmation based;
- open-ended trend lifecycle exit;
- free of Pinbar / 1h primary / fixed-TP CPM mechanics;
- evaluated with mandatory CPM drift checks.

It is not different enough if it becomes "CPM-1 with a better trigger."

### 5.3 If CPM-MOD-002 Fails, Should D Priority Drop?

Yes.

If CPM-MOD-002 fails to identify a pre-observable validity gate for CPM-1,
Direction D should move down in priority because the family-level
applicability problem remains unsolved. D would not be automatically rejected,
but it should require stronger Owner justification before Level 3 execution.

The priority drop should be strongest if CPM-MOD-002 fails because:

- 2021 high-volatility sub-regimes cannot be separated ex-ante;
- the gate kills 2024/2025 profitable periods;
- the result depends on selecting bad years after the fact.

### 5.4 If D Fails, Should The Whole Family Pause?

Yes, if D fails with CPM-like behavior.

Pause the pullback-continuation family if Direction D shows:

- negative 2021 gross edge;
- loss clustering similar to CPM-1;
- similar year-by-year profile to CPM-1;
- top-3 fragility not improved;
- no clear ex-ante applicability explanation.

If CPM-MOD-002 also fails, and D fails with CPM drift, the correct action is to
pause the entire pullback-continuation family and return to non-pullback
directions.

If D fails only because of thin sample or an implementation-specific issue,
pause D specifically, but do not automatically reject the entire family.

### 5.5 Family Management: CPM-1, D, And 15m Pullback Entry

CPM-1, Direction D, and any future 15m pullback-entry concept should be managed
as one broad pullback-continuation family, while preserving sub-family
distinctions:

| Candidate | Family relationship | Distinction |
| --- | --- | --- |
| CPM-1 | Pullback-continuation baseline failure case | 1h Pinbar trigger, fixed TP geometry |
| Direction D | Pullback-continuation MTC variant | 4h EMA60 value zone, EMA20 resumption, lifecycle exit |
| 15m pullback-entry | Potential lower-timeframe auxiliary layer | Only acceptable if subordinate to a 4h thesis unless separately approved |

They should not be treated as identical. But their failures should accumulate
at the family level. If CPM-MOD-002 cannot identify applicability, Direction D
drifts like CPM, and 15m pullback-entry shows poor signal quality, the family
should be paused rather than repeatedly re-entered through a new timeframe or
trigger.

---

## 6. Future Level 3 Admission Conditions

Future Level 3 upgrades should require all of the following:

| Condition | Requirement |
| --- | --- |
| Mechanism structure clear | The module's profit source and entry/exit mechanics are explicitly defined before execution |
| Non-parameter-search | One frozen rule, no sweep, no threshold rescue, no sensitivity pass masquerading as validation |
| Applicability hypothesis | The expected working and non-working market states are stated before execution |
| Ex-ante observability | Validity features are computable from data available before the trade or enablement decision |
| Stop conditions | Pre-registered conditions define reject, pause, insufficient evidence, and family-drift closure |
| No post-hoc no-trade gate | A losing year cannot be filtered only because it lost in the result |
| Runtime isolation | No runtime/profile/risk/backtester-core changes |
| Information gain | The result must answer a specific research question that changes future priority or closure |
| Evidence floor | Expected trade count and winner count must be plausible under MTC-001 or explicitly diagnosed as a sample-feasibility test |
| Family drift check | Any direction near CPM or Direction A must include overlap/drift diagnostics |
| Closure statement | The plan must state what hypothesis will be closed if the result fails |

Level 3 should be denied or deferred when the proposal only asks to "try a
variant" without a clear applicability hypothesis or stop condition.

The required closure statement should be concrete. Examples:

- CPM-MOD-002 failure would weaken or close the hypothesis that CPM-1 can be
  enabled by a simple volatility validity gate.
- Direction D failure with CPM drift would weaken or pause the hypothesis that
  4h structured pullback-continuation solves CPM-1's pullback-ending problem.
- A 15m auxiliary-layer failure would weaken the hypothesis that lower
  timeframe entry timing improves MTC evidence after realistic costs.

Level 3 is not allowed when a failed result would simply spawn a new branch
with a looser threshold, extra filter, new timeframe, or post-hoc no-trade
condition.

---

## 7. Lower-Timeframe Research Possibility: 15m / Sub-1h

### 7.1 Can 15m Help Trade Count / Winner Count?

Possibly, but this is not enough by itself.

Moving from 4h or 1h to 15m can mechanically increase signal count and may
increase winner count. That could help directions like Direction C, where
4h-only evidence is too thin for MTC-001-style evaluation.

But higher trade count is not the same as better evidence. On 15m, many trades
may be highly correlated slices of the same move, the same choppy period, or
the same false-breakout cluster. The relevant question is not only "do we get
more trades?" but:

- do we get more independent opportunities;
- do we get more independent winners;
- does the payoff tail survive costs;
- does top-N removal improve after adjusting for higher frequency;
- does 15m identify information that is not already visible on 1h/4h?

Therefore 15m may help sample-size pressure, but it is not automatically a cure
for MTC fragility.

### 7.2 Main 15m Risks

15m significantly increases the risks that currently matter most:

| Risk | 15m impact |
| --- | --- |
| Noise | Much higher; candle patterns and local breakouts become less reliable |
| Fees and slippage | More trades means more turnover and higher cost drag |
| Same-bar assumptions | More bars reduce bar duration but increase intrabar ambiguity and stop/entry ordering sensitivity |
| False breakouts | More frequent local structure breaks may create more failed signals |
| Overfitting | More knobs become tempting: windows, buffers, waiting periods, microstructure filters |
| Data quality | Missing candles, bad timestamps, and exchange anomalies matter more at higher frequency |
| Execution realism | Fill price, spread, latency, and stop execution assumptions become more important |

The cost model that is acceptable for sparse 4h research may be too optimistic
for 15m. A 15m module must prove that its edge survives harsher execution
assumptions.

### 7.3 Suitable 15m Roles

Current judgment:

| Role | Fit | Judgment |
| --- | --- | --- |
| Independent strategy main timeframe | Low for current stage | Prior CPM evidence makes this high-risk; not immediate mainline |
| 4h main trend + 15m precision entry | Medium | Plausible if 4h remains the decision layer and 15m only times entry |
| Risk compression / smaller-stop entry | Medium | Plausible but dangerous; tighter stops can increase churn and stop-outs |
| Execution timing | Medium-High | Best near-term conceptual role; reduce chase/slippage without changing thesis |
| Current-stage experiment | Low | Not authorized; needs data QA and inspect-only role definition first |

The safest future framing is not "15m strategy." It is:

> 4h primary thesis, 15m bounded entry/execution layer, with 15m prohibited from
> becoming the profit source unless a separate Owner-approved research path says
> otherwise.

### 7.4 Independent 15m Evaluation Gates

15m needs its own stricter gates. It should not inherit 4h gates unchanged.

Minimum additional requirements:

| Gate | 15m requirement |
| --- | --- |
| Cost model | Stricter fee/slippage/spread assumptions; report cost as % of gross and turnover |
| Trade count | Higher floor than 4h/1h because higher frequency creates more correlated samples |
| Winner count | Higher floor than 4h/1h; 15 winners is too low for a 15m module |
| Slippage sensitivity | Required; result must survive adverse slippage scenarios |
| Same-bar / intrabar handling | Explicit stop-entry ordering, same-candle conflict counts, and pessimistic execution rules |
| OOS | Stricter and cleaner OOS split; no result should rely only on 2023-2025-style in-sample behavior |
| Top-N removal | Stricter than top-3 only; top-5 and possibly top-10 should be reviewed for high-frequency candidates |
| Signal independence | Report clustering by day/week/regime so many small signals do not masquerade as independent evidence |

If 15m is used only as an execution timing layer under a 4h signal, the 15m
evaluation should compare against the same 4h baseline and prove it improves
entry/execution without deleting the 4h payoff tail.

### 7.5 Meaning Of Old CPM-1 15m Evidence

The CPM-1 scope note records ETH 15m as "too many trades" with poor signal
quality. That evidence should be interpreted narrowly:

- It rejects direct CPM-1 15m migration.
- It rejects treating Pinbar-style 15m pullback continuation as a ready path.
- It raises the evidence burden for any 15m proposal.

It does **not** reject all possible 15m research.

A bounded 15m layer under a 4h thesis is structurally different from CPM-1 on
15m as an independent primary timeframe. The old evidence is a warning label,
not a total family ban.

### 7.6 Recommended Future 15m Sequence

If Owner later wants to explore 15m, the sequence should be:

1. **Data QA**: inspect existing 15m ETH data coverage, gaps, duplicates,
   timestamp continuity, contract consistency, and funding/cost comparability.
2. **Inspect-only**: define whether 15m is being considered as entry timing,
   risk compression, execution timing, or an independent strategy.
3. **4h+15m role definition**: if 15m is used, freeze its subordinate role
   under a 4h primary thesis and define what it is forbidden to decide.
4. **Level 3 research** only after Owner approves a single frozen, high
   information-gain diagnostic with 15m-specific gates.

Do not start with Level 3. The first legitimate step is data QA plus
inspect-only role definition.

This does not authorize a new data pipeline. If required 15m data is missing or
not comparable, the correct result is a documented blocker, not ingestion work.

### 7.7 15m Non-Authorization

This SR-001 supplement explicitly does not authorize:

- any 15m backtest;
- any 15m strategy script;
- any backtester modification;
- any runtime/profile/risk change;
- any live, small-live, or canary-live use;
- making 15m the immediate strategy mainline;
- using 15m to rescue CPM-1, Direction A, Direction C, or Direction D after
  the fact.

### 7.8 15m Classification

15m should enter the research inventory as:

> **Candidate - inspect-only lower-timeframe layer, not immediate mainline.**

It is not `immediate`, because no Level 3 or experiment is authorized. It is
not `reject`, because CPM-1 15m evidence rejects a specific migration, not all
15m roles. It is stronger than generic backlog because the Owner has explicitly
placed 15m into research view. The current actionable classification is
candidate for docs-only data QA and role inspect.

---

## 8. Current Small-Live Readiness

Current readiness is clear:

- There is **no runtime candidate**.
- There is **no deployable small-live strategy**.
- There is **no small-live strategy module ready for promotion**.
- Live-safe foundation progress does **not** equal strategy readiness.
- CPM 2024/2025 positive evidence is not enough for small-live.
- No single positive window, including any future 15m positive result, can
  bypass applicability, OOS, fragility, and Owner approval gates.

Live-safe foundation remains valuable because it makes future execution safer
if a strategy eventually becomes ready. It does not solve the strategy evidence
gap.

---

## 9. Owner Summary

### 9.1 Should Research Continue?

Yes, but under a narrower research mode.

Continue strategy research as applicability and validity-gate investigation.
Do not continue it as a near-term deployment search or as a sequence of
micro-variants.

### 9.2 Recommended Next Step

Recommended next step:

1. Create a **Strategy Module Applicability Map** for A / C / CPM / D / 15m
   auxiliary layer.
2. Add **15m / sub-1h** to that map as an inspect-only lower-timeframe
   candidate layer, not an immediate experiment.
3. If Owner authorizes Level 3, run **CPM-MOD-002** as the first frozen
   module-level volatility gate diagnostic, using one pre-registered volatility
   gate only.
4. Run **Direction D Level 3** only after the map, and preferably after
   CPM-MOD-002, with mandatory CPM drift checks.
5. If Owner does not authorize Level 3 now, pause experiments and keep only
   docs-only applicability work active.

Current maximum blocker:

> No module has a validated, pre-observable applicability boundary that
> survives enough trades, enough winners, top-winner fragility, year
> concentration, and realistic costs.

### 9.3 Recommended Reason

This order maximizes information gain while minimizing overfit drift:

- The map clarifies the research frame.
- 15m is captured without accidentally becoming a backtest or mainline.
- CPM-MOD-002 tests whether conditional enablement is viable on a known module.
- Direction D remains available, but does not bypass the family-level CPM
  failure question.
- Pausing experiments remains preferable to generating new branches without
  closure conditions.

### 9.4 Explicitly Forbidden

The following remain forbidden:

- No backtest execution.
- No research scripts or adapters.
- No parameter sweep or sensitivity rescue.
- No runtime/profile/risk/backtester-core change.
- No live, small-live, or canary-live enablement.
- No strategy promotion.
- No CPM-1 parameter rescue.
- No Direction A/B-D1 reopening or micro-variant search.
- No Direction C threshold loosening after seeing thin evidence.
- No Direction D zone/EMA/confirmation sweep.
- No after-the-fact no-trade gate.
- No strategy router, portfolio engine, or regime system.
- No new data pipeline.
- No composite M0 score, E4 soft label, position sizing, or multi-factor regime
  search inside CPM-MOD-002 first round.
- No 15m backtest, script, backtester change, runtime/profile/risk change, or
  immediate 15m mainline.
- No treating live-safe foundation as strategy readiness.

### 9.5 Owner Level 3 Authorization Needed?

Yes, for any empirical diagnostic or experiment.

- Strategy Module Applicability Map: **No Level 3 needed** if docs-only.
- 15m data QA / inspect-only role definition: **No Level 3 needed** if
  docs-only and no backtest is run.
- Any 15m empirical research run: **Owner Level 3 required**.
- CPM-MOD-002 frozen diagnostic: **Owner Level 3 required**.
- Direction D frozen experiment: **Owner Level 3 required**.

Until Owner grants Level 3, the correct state is docs-only research planning
and no experiment execution.

Small-live readiness gate remains unmet.

---

## 10. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial SR-001 strategy research reality-check document | Codex |
| 2026-05-07 | Added 15m / sub-1h lower-timeframe research possibility supplement | Codex |
| 2026-05-07 | Tightened CPM-MOD-002 diagnostic scope, family management, and Level 3 closure conditions | Codex |
