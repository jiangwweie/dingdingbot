# SRD-002 - Non-Pullback Direction Map

**Task ID:** SRD-002
**Date:** 2026-05-07
**Status:** Completed / Docs-only direction map
**Authorization Level:** Level 1/2 - docs-only
**Source:** SRD-001 accepted direction refresh
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document maps non-pullback strategy research directions after SRD-001.

It is not:

- a strategy experiment;
- a backtest request;
- strategy script or adapter authorization;
- parameter optimization;
- Level 3 authorization;
- runtime/profile/risk/backtester-core work;
- new data pipeline authorization;
- router, portfolio, or regime-engine design;
- runtime candidate or small-live readiness review.

No candidate in this document is a runtime candidate. No small-live conclusion
follows from this map.

---

## 1. Non-Pullback Definition Boundary

### 1.1 What Is Not Non-Pullback

The following are not non-pullback directions and must not be reopened under a
new label:

| Excluded path | Why excluded |
| --- | --- |
| CPM-style pullback | Same 1h pullback-ending family already paused; CPM-MOD-002 only partially strengthened a narrow gate hypothesis |
| Direction D value-zone pullback | MTC-006 rejected the frozen 4h EMA60 value-zone / EMA20 resumption baseline |
| 15m pullback-entry | LTF-002 freezes 15m as execution timing under a frozen 4h thesis, not as a pullback-entry strategy |
| Direction A parameter rescue | Direction A is `PAUSE_FRAGILE`; no Donchian/EMA/exit micro-variant rescue |
| Direction C parameter rescue | Direction C is `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`; no ATR-ratio or re-expansion threshold rescue |
| Overlay stacking | Prior overlays/entry timing did not solve fragility and increase post-hoc fitting risk |
| 1h entry timing rescue | Direction B-D1 was marginal only; D2/D3/D4 and 1h rule search remain closed |
| Same family, new trigger | If the profit source is still "pullback ended, continuation resumes," it remains pullback-continuation |
| SSD-003 short-side breakdown continuation rescue | SSD-003 was a clean frozen Level 3 run; the specific OHLCV-only breakdown-continuation mechanism is `REJECTED_FROZEN_BASELINE`; no alternate thresholds, lookbacks, timing, or funding rescue |

### 1.2 What Can Count As Non-Pullback

A direction can count as non-pullback only if its primary profit source and
entry/lifecycle concept do not depend on buying a pullback or confirming that a
pullback has ended.

Allowed non-pullback buckets:

- short-side / two-sided directional lifecycle;
- volatility expansion / impulse participation;
- trend persistence without value-zone pullback;
- range / mean-reversion;
- trend exhaustion / avoidance map;
- funding/OI/crowding-informed future module;
- cross-timeframe execution-only auxiliary under a frozen parent thesis;
- other structurally distinct OHLCV-only candidates with pre-observable
  applicability boundaries.

Guardrail:

> If a proposal can be summarized as "enter after price retraces to a better
> level, then resumes," it is pullback-continuation unless proven otherwise.

---

## 2. Candidate Bucket Map

| Bucket | Profit source | Expected market condition | Failure mode | Required data | Current OHLCV enough for inspect? | Needs new data? | Thin-core conflict? | Old-path drift risk | Current classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. Short-side / two-sided directional lifecycle | Downside trend lifecycle capture; asymmetric participation in breakdowns and failed rallies | 4h bearish structure, breakdown continuation, lower-high sequence, downside volatility expansion | Short squeezes, whipsaw in chop, funding/cost caveats, mirror-copying long rules | 4h OHLCV; cost/funding caveat | Yes for Level 1/2 inspect | Real funding useful later but not required for docs-only inspect | Low if standalone research-only | Medium if it becomes Direction A mirrored mechanically | **SSD-003 frozen baseline rejected; 4h breakdown-continuation closed; bucket needs re-evaluation or new mechanism before any future inspect** |
| B. Volatility expansion / impulse participation | Entering directional impulse after expansion, not after pullback | Sudden range/ATR expansion with close-location follow-through or impulse persistence | False impulse, expansion into exhaustion, threshold mining, Donchian rescue | 4h OHLCV: range, ATR, close location, volume if available | Yes | No for first inspect | Low if threshold search is prohibited | High if it becomes Direction C/A rescue | **PAUSE_FRAGILE — VEI-003 frozen Level 3 completed; overlap gates passed (A 27.1%, C 2.5%); independent signals net negative (-329.02, PF 0.86); all positive PnL from Direction A echo; no variants authorized** |
| C. Trend persistence without value-zone pullback | Continuation from sustained trend state, not retracement-to-zone | Persistent 4h directional closes, structure continuation, trend strength without value-zone dependency | Late entries, year concentration, top-winner fragility, Direction A variant | 4h OHLCV | Yes | No | Low-Moderate | Medium if it becomes Donchian/EMA variant | **Candidate inspect after A/B** |
| D. Range / mean-reversion | Buying/selling range extremes inside bounded, non-trending markets | Low directional persistence, repeated support/resistance reactions, volatility contained | Boundary fitting, stop runs, breakout transition, cost drag | OHLCV for rough range; spread/orderbook useful for precision | Yes for concept inspect | Spread/orderbook optional future dependency | Moderate because it is a new family | Low pullback drift; high overfit risk | **Backlog / optional inspect** |
| E. Trend exhaustion / avoidance validity map | Loss avoidance by identifying toxic or exhausted trend states before entry | Extended trend, unstable volatility, overbought/oversold impulse, failed follow-through risk | Post-hoc no-trade gate, kills rare winners, overlay stacking | OHLCV for basic exhaustion; funding/OI for crowding | Yes for docs-only map only | Funding/OI if crowding-based | Moderate; can drift into regime engine | High if used to rescue A/C/CPM/D | **Backlog unless paired with frozen module** |
| F. Funding/OI-informed future module | Crowding, carry, leverage, or squeeze-state asymmetry | Extreme funding, OI expansion/flush, crowded trend or liquidation-prone state | Requires new data, threshold fitting, scope expansion | Historical funding, OI, possibly long/short, liquidation, mark/index | No | Yes | High under current thin-core roadmap | Medium; can become regime engine | **Backlog, not current** |
| G. Cross-timeframe execution-only auxiliary | Execution quality improvement under a frozen parent thesis | Parent 4h thesis active; lower timeframe only times execution | Role drift into 15m mainline, pullback-entry rescue, churn/cost increase | 15m/1h OHLCV plus frozen parent signal | Yes for docs-only role work | No new pipeline | Low only if role-bound | High if used as 15m pullback-entry | **Docs-only backlog** |

---

## 3. Short-Side / Two-Sided Focus Check

### 3.1 Structural Difference

Short-side / two-sided directional lifecycle is the first concrete inspect
target because it asks a genuinely different question:

> Does ETH have downside directional lifecycle states that are observable from
> closed 4h OHLCV and structurally distinct from long-only breakout, long-only
> pullback, and 4h value-zone continuation?

It differs from:

- **CPM-1**: not a 1h pullback-ending trigger.
- **Direction D**: not a value-zone retracement plus resumption.
- **15m pullback-entry**: not a lower-timeframe pullback rescue.
- **Long-only MTC / Direction A**: not necessarily the same signal mirrored;
  the lifecycle and failure modes must be specified separately.

### 3.2 Not Just A Direction A Mirror

A short-side inspect must not simply invert Direction A. ETH downside moves may
have different structure:

- faster downside volatility expansion;
- sharper short squeezes and relief rallies;
- different hold-duration and giveback behavior;
- different funding/carry implications;
- different failure state around capitulation and V-reversal.

The inspect should start with concept definitions, not a mirrored rule.

### 3.3 Independent Profit Source Hypothesis

The independent profit source hypothesis is:

> ETH downside regimes may produce faster and more directional lifecycle moves
> than long-side pullback continuation, and these moves may be identifiable by
> closed 4h structure before or during breakdown continuation.

This is not a deployment claim. It is only a reason to inspect whether a frozen
short/downside module can be specified.

### 3.4 Downside Lifecycle Concept

A downside lifecycle concept could include, at inspect level only:

- bearish structure state;
- breakdown from a prior range or support area;
- lower-high / lower-low continuation;
- downside expansion with follow-through;
- invalidation by failed breakdown, violent reversal, or squeeze.

No rule parameters are selected in SRD-002.

### 3.5 Failure Mode

Failure can be described before testing:

- low-volatility chop creates short churn;
- breakdowns fail into squeeze rallies;
- downside entries arrive after capitulation, not before continuation;
- funding/carry assumptions distort short PnL interpretation;
- short signal is only a mirrored long breakout and inherits Direction A
  fragility.

### 3.6 Data Sufficiency

Current OHLCV is enough for Level 1/2 inspect because the next step is only to
define:

- whether a short-side mechanism can be structurally specified;
- what observables would define applicable and failed states;
- what a future frozen spec would need to include.

Real historical funding is useful for future promotion-grade interpretation,
but not required for the first docs-only inspect. If a future hypothesis depends
on funding/OI/crowding, it must move to the funding/OI backlog and require
separate data authorization.

### 3.7 Failure Closure

SSD-003 has already closed the short-side 4h OHLCV-only breakdown continuation
hypothesis:

> ETH 4h OHLCV-only short-side breakdown continuation as a clean non-pullback
> standalone candidate under current constraints.

The frozen Level 3 run produced `REJECTED_FROZEN_BASELINE`: net PnL -1699.88,
PF 0.317, 23 trades, 1 winner, realized MaxDD 24.88%, MTM MaxDD 26.98%.
2021 was strongly negative, 2022-2024 had no trades, and 2025 was
single-winner concentrated.

SSD-003 was structurally distinct from all prior modules (0% Direction A/C
overlap, no pullback drift). The rejection is a pure evidence-quality failure.

Future short-side research is not permanently banned but cannot be derived from
SSD-003. Any future direction must be proposed through a new Owner-approved
Level 1/2 direction refresh with a clearly different mechanism.

If future short-side inspect fails before Level 3, it closes:

> The hypothesis that short/downside lifecycle capture is a clean immediate
> non-pullback candidate under current OHLCV-only scope.

If a later frozen Level 3 fails, it should close the specific frozen downside
mechanism, not generate mirrored variants, short-specific overlays, or 1h
entry timing branches.

---

## 4. Volatility Expansion / Impulse Participation Boundary

### 4.1 Difference From Direction C

Direction C was volatility contraction followed by re-expansion within trend.
It is paused because the frozen baseline had thin evidence and worse
concentration.

A new impulse-participation bucket is only distinct if it does not require:

- prior contraction threshold rescue;
- ATR-ratio loosening;
- re-expansion threshold tuning;
- reuse of Direction C's same entry logic.

It should ask a broader but still pre-definable question:

> Can ETH closed 4h OHLCV identify directional impulse participation states,
> including first impulses or acceleration phases, without relying on pullback
> or contraction rescue?

### 4.2 Difference From Direction A

Direction A is Donchian20 close breakout plus EMA60 lifecycle exit. A new
impulse bucket must not simply relabel Donchian breakout.

It must define impulse using a different concept such as:

- range expansion profile;
- close location inside the candle/range;
- multi-bar follow-through state;
- directional acceleration;
- volatility expansion relative to recent baseline without requiring a
  Donchian high/low breakout.

No specific threshold is selected here.

### 4.3 Profit Source

The profit source is participation in high-energy directional movement before
or during the impulse phase, with the expectation that impulse follow-through
can pay for false starts.

### 4.4 Failure Mode

Expected failures:

- expansion is exhaustion rather than continuation;
- one-bar news spikes reverse quickly;
- threshold choices overfit;
- signal overlap with Direction A or Direction C is too high;
- top-N fragility remains severe.

### 4.5 Inspect Ranking

Impulse participation is suitable as the second inspect candidate after
short-side / two-sided inspect, provided the next document can define why it is
not Direction A rescue and not Direction C rescue.

---

## 5. Range / Mean-Reversion Boundary

Range / mean-reversion conflicts with the current trend-first research thesis
more than the directional buckets, but it is structurally different enough to
remain in backlog.

### 5.1 Potential Complement

It may eventually provide a complementary module for non-trending states:

- range support/resistance reactions;
- failed breakouts back into range;
- volatility-contained chop.

However, current Owner guidance does not authorize router, portfolio, or regime
engine work. A range module must be evaluated as its own standalone research
module, not as a portfolio filler.

### 5.2 Data Sufficiency

OHLCV is enough for a rough Level 1/2 inspect:

- range width;
- range duration;
- repeated boundary reactions;
- volatility containment;
- breakout invalidation.

Spread/orderbook data may be useful later because mean-reversion often has
smaller per-trade edge and higher execution sensitivity. That is a future
dependency, not current authorization.

### 5.3 Main Overfit Risk

The main overfit risk is boundary fitting:

- choosing range highs/lows after seeing outcomes;
- selecting range duration thresholds;
- fitting stop/target geometry to specific years;
- adding filters after failed breakouts.

Classification: **Backlog / optional inspect**, not reject. It should not
outrank short-side or impulse participation.

---

## 6. Funding/OI Future Dependency

Funding/OI is relevant for:

- crowding-aware trend exhaustion;
- short squeeze / long squeeze risk;
- perp carry and funding-cost interpretation;
- liquidation-prone or leverage-flush hypotheses;
- toxic-state validity gates.

Current state:

- Existing OHLCV is not enough for true funding/OI-informed research.
- Current scope does not authorize a new data pipeline.
- Opening data capability before a precise hypothesis risks scope expansion.

Recommendation:

> Funding/OI-informed modules stay backlog until a separate Owner-approved data
> dependency task defines exact data, source, storage, cost model impact, and
> research question.

Avoid data-first scope creep:

- Do not build a general feature store "just in case."
- Do not add funding/OI to rescue CPM, Direction D, or Direction A.
- Do not introduce a regime engine under the name of crowding filter.
- Require a named hypothesis before any data work.

---

## 7. Applicability Boundary Requirements

| Bucket | Applicable market pre-observable? | Failure market pre-observable? | Post-hoc no-trade risk | Failure closure condition | Can become frozen spec later? |
| --- | --- | --- | --- | --- | --- |
| A. Short-side / two-sided | Potentially yes: bearish structure, breakdown, lower-high, downside expansion | Potentially yes: chop, squeeze, failed breakdown, capitulation reversal | Moderate | Close immediate OHLCV-only short/downside lifecycle candidate if no clean boundary | Yes, after Level 1/2 inspect |
| B. Volatility expansion / impulse | Potentially yes: closed-bar expansion/acceleration states | Potentially yes: failed impulse, exhaustion spike, overlap with A/C | High if thresholds are mined | Close impulse distinctness hypothesis if it collapses into A/C rescue | Yes, only with no threshold search |
| C. Trend persistence without pullback | Potentially yes: persistence/structure state | Potentially yes: mature exhaustion, late-entry state | Moderate | Close persistence-not-pullback hypothesis if it becomes A/D variant | Yes, but lower priority |
| D. Range / mean-reversion | Potentially yes but subjective | Potentially yes: breakout/expansion out of range | High | Backlog/reject if range boundaries cannot be objective | Maybe, after strict range-definition inspect |
| E. Exhaustion / avoidance map | Only if tied to pre-defined toxic state | Only if it predicts when not to disable | Very high | Close the specific toxic-state hypothesis; do not rescue parent strategy | Only paired with a frozen parent module |
| F. Funding/OI module | Yes in principle, no current data | Yes in principle, no current data | High | No closure now; backlog until data task | Not before data authorization |
| G. Cross-timeframe auxiliary | Only with frozen parent thesis | Yes: parent inactive, conflict, churn/cost | High | Close execution-layer improvement for that parent, not 15m strategy | Only after parent thesis exists |

Level 3 precondition:

> Before any candidate moves beyond Level 1/2, it must have a frozen mechanism,
> pre-observable applicability and failure boundaries, stop conditions, and a
> statement of what failure would close.

---

## 8. Level 1/2 Next-Step Ordering

### 8.1 Recommended Order

| Rank | Direction | Information gain | Risk | Authorization | Why not old path | Failure closes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Volatility expansion / impulse participation inspect | Tests whether impulse states can be defined outside A/C | Threshold mining; breakout rescue drift | Level 1/2 docs-only | Must avoid Donchian20 and Direction C ATR-ratio rescue | Impulse-participation distinctness hypothesis |
| 2 | Short-side / two-sided directional re-evaluation | SSD-003 closed breakdown continuation; a new mechanism would need Owner-approved direction refresh | Mirror-copy risk; squeeze/funding caveats; SSD-003 closure constraint | Level 1/2 docs-only; new direction refresh required | Not breakdown continuation; not SSD-003 rescue; not Direction A/C mirror | New short-side mechanism hypothesis |
| 3 | Trend persistence without value-zone pullback | Checks a non-zone continuation concept | Direction A variant risk; late-entry fragility | Level 1/2 docs-only | No value-zone pullback; no 1h entry timing | Persistence-state candidate if it collapses into A/D |
| 4 | Range / mean-reversion | Tests a different profit source | High boundary overfit; weaker thesis alignment | Level 1/2 optional inspect | Not pullback or trend continuation | OHLCV-defined range researchability |
| 5 | Exhaustion / avoidance validity map | Keeps applicability thinking alive without running gates | Highest post-hoc no-trade risk | Level 1/2 docs-only only | Not overlay rescue if not attached to failed modules | Specific toxic-state map only |
| 6 | Funding/OI future dependency | Identifies future data needs | Scope creep | Level 1/2 dependency note only | Not a current strategy; no data pipeline | No closure until data task |
| 7 | Cross-timeframe execution-only auxiliary | Preserves LTF-002 role | Drifts into 15m pullback-entry | Level 1/2 docs-only only | Not 15m mainline; parent thesis required | Parent-specific execution hypothesis |

### 8.2 Reject / Do-Not-Start

Reject or do not start:

- CPM rescue / CPM-MOD-003;
- Direction D follow-up;
- Direction A/C rescue;
- 15m pullback-entry;
- pullback-continuation new trigger branches;
- overlay stacking;
- 1h entry timing search;
- D2/D3/D4;
- funding/OI data pipeline without a named hypothesis;
- router / portfolio / regime engine.

---

## 9. Explicit Prohibitions

SRD-002 does not authorize:

- backtests;
- strategy scripts;
- research adapters;
- parameter sweeps;
- runtime/profile/risk/backtester-core changes;
- new data pipelines;
- Level 3 research runs;
- small-live approval;
- router / portfolio / regime engine design;
- reopening pullback-continuation family empirical experiments;
- Direction A rescue;
- Direction C rescue;
- CPM rescue or CPM-MOD-003;
- Direction D rescue or variants;
- 15m pullback-entry;
- SSD-003 rescue variants or alternate short-side lookbacks;
- treating any candidate bucket as a runtime candidate.

---

## 10. Owner Summary

### 10.1 Recommended New Direction Order

| Rank | Direction | Classification |
| --- | --- | --- |
| 1 | Volatility expansion / impulse participation | **Immediate Level 1/2 inspect** |
| 2 | Short-side / two-sided directional lifecycle re-evaluation | Closed for breakdown continuation (SSD-003); needs new Owner-approved direction refresh |
| 3 | Trend persistence without value-zone pullback | Candidate inspect after A/B |
| 4 | Range / mean-reversion | Backlog / optional inspect |
| 5 | Trend exhaustion / avoidance validity map | Backlog unless tied to frozen module |
| 6 | Funding/OI-informed module | Backlog; future data dependency |
| 7 | Cross-timeframe execution-only auxiliary | Docs-only backlog; parent thesis required |

### 10.2 First Recommendation

Recommended next task:

> **Volatility expansion / impulse participation Level 1/2 inspect.**

Reason:

- Short-side / two-sided directional lifecycle is no longer the first-rank
  target. SSD-003 closed the 4h breakdown continuation mechanism, and the
  bucket requires re-evaluation or a new Owner-approved direction refresh
  before any future short-side inspect proceeds.
- Impulse participation is now the next candidate in queue. It tests a genuinely
  different question from all prior modules.
- It can be inspected with current OHLCV.
- It must avoid Direction A Donchian rescue and Direction C ATR-ratio rescue.

### 10.3 Backlog / Reject

Backlog:

- range / mean-reversion;
- exhaustion / avoidance map unless tied to a frozen module;
- funding/OI-informed module until data dependency is separately authorized;
- cross-timeframe execution-only auxiliary until a parent 4h thesis exists.

Reject / do-not-start:

- pullback-continuation new triggers;
- Direction A/C/CPM/D rescue;
- 15m pullback-entry;
- overlay stacking;
- 1h entry timing search;
- SSD-003 rescue (variants, alternate lookbacks, bearish A/C mirror,
  failed-rally value-zone short, 1h/15m timing, funding/OI);
- router / portfolio / regime engine.

### 10.4 Owner Level 3

No Owner Level 3 is recommended by SRD-002.

Owner Level 3 would be needed only after a future Level 1/2 inspect produces a
frozen mechanism, pre-observable applicability boundary, explicit stop
conditions, and a clear failure-closure statement.

### 10.5 Small-Live Readiness

Small-live readiness gate remains unmet.

There is no runtime candidate and no deployable small-live strategy.

