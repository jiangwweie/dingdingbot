# SSD-001 - Short-side / Two-sided Directional Lifecycle Inspect

**Task ID:** SSD-001
**Date:** 2026-05-07
**Status:** Completed / Docs-only concept inspect
**Authorization Level:** Level 1/2 - docs-only
**Source:** SRD-002 accepted non-pullback direction map
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document inspects whether ETH 4h short-side / two-sided directional
lifecycle is a structurally clear non-pullback candidate direction.

It is not:

- a backtest task;
- a strategy script or adapter task;
- parameter optimization;
- a Level 3 research run;
- runtime/profile/risk/backtester-core work;
- new data pipeline authorization;
- router, portfolio, or regime-engine design;
- runtime candidate or small-live readiness review.

No runtime candidate, deployable small-live strategy, live profile change, or
strategy enablement follows from this inspect.

---

## 1. Direction Identity

### 1.1 Research Identity

Short-side / two-sided directional lifecycle asks:

> Can ETH 4h closed OHLCV identify downside directional lifecycle states, or a
> clean two-sided directional lifecycle, without relying on pullback entries or
> failed pullback confirmation?

Candidate identity:

| Dimension | Inspect definition |
| --- | --- |
| Profit source | Downside trend lifecycle capture, breakdown continuation, failed-rally continuation, or downside expansion with follow-through |
| Primary timeframe | 4h concept level |
| Current recommended scope | Short-side-only conceptual inspect first |
| Non-pullback? | Yes, if entry is based on directional lifecycle / breakdown / downside structure, not pullback completion |
| Data scope | Current 4h OHLCV is enough for Level 1/2 inspect |
| Current status | `RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN` |

### 1.2 Mandatory Boundaries

This direction must not:

- buy pullbacks;
- confirm pullback endings;
- use value-zone entry;
- use Pinbar / wick trigger;
- use 15m pullback-entry;
- reopen Direction A, Direction C, CPM-1, or Direction D;
- become a 1h/15m entry-timing project;
- become a router, portfolio, or regime engine.

### 1.3 Difference From Direction A

Direction A is a long-only 4h breakout / main-trend lifecycle signal with
fragile but real positive evidence. A short-side lifecycle candidate cannot be
a mechanical mirror of Direction A because downside behavior can differ:

- downside moves may be faster and more discontinuous;
- short squeezes and V-reversals are distinct failure states;
- failed rallies may have different structure than bullish breakouts;
- funding/carry caveats differ for short exposure;
- capitulation late-entry risk is specific to downside participation.

The next inspect should define short-side lifecycle from first principles. It
should not invert Direction A's Donchian/EMA rule and call that new research.

### 1.4 Boundary From CPM / Direction D / 15m

| Prior family | Boundary |
| --- | --- |
| CPM-1 | No 1h Pinbar, lower-wick, pullback-ending, fixed TP pullback module |
| Direction D | No EMA60 value-zone touch, EMA20 resumption, or structured pullback continuation |
| 15m pullback-entry | No lower-timeframe pullback-entry or risk-compression rescue |
| Direction C | No ATR-ratio / contraction threshold rescue |
| Direction A | No Donchian/EMA parameter rescue or mirrored rule without independent short lifecycle logic |

---

## 2. Short-side Profit Hypotheses

### 2.1 H1 - Downside Trend Lifecycle Capture

Hypothesis:

> ETH downside trends may produce compressed but directional lifecycle moves
> that can be captured from closed 4h bearish structure before the full move
> completes.

Why it may hold on ETH:

- crypto downside moves can be fast, reflexive, and volatility-expanding;
- support failures can lead to multi-bar follow-through;
- participants may de-risk quickly during bearish structure shifts.

Difference from long-side trend capture:

- downside lifecycle may be shorter and sharper;
- squeeze risk is larger;
- late-entry after capitulation is a central failure state.

Expected market:

- clear bearish 4h structure;
- breakdown from range or support;
- lower-high / lower-low continuation;
- downside volatility expansion with follow-through.

Expected failure:

- low-volatility chop;
- violent short squeeze;
- failed breakdown;
- entry after capitulation exhaustion.

Failure closure:

> If no pre-observable downside lifecycle state can be defined without copying
> Direction A, close H1 as an immediate OHLCV-only candidate.

### 2.2 H2 - Failed Rally Continuation

Hypothesis:

> In bearish ETH conditions, rallies that fail to reclaim structure may resume
> the downside lifecycle without needing pullback/value-zone logic.

Boundary warning:

Failed rally continuation is allowed only if framed as failure to recover
bearish structure, not as "short the pullback to a value zone." If the concept
depends on retracement-to-zone entry, it drifts into Direction D-like pullback
continuation and must stop.

Expected market:

- existing bearish structure;
- rally fails to invalidate the downside thesis;
- subsequent downside continuation resumes.

Expected failure:

- failed rally becomes true reversal;
- squeeze through invalidation;
- range-bound chop where rallies and selloffs alternate without lifecycle.

Failure closure:

> If failed rally cannot be defined without value-zone pullback semantics, close
> H2 for current scope.

### 2.3 H3 - Breakdown Continuation

Hypothesis:

> Breakdowns from established support or range structures may produce downside
> continuation that is distinct from long-side breakout and pullback families.

Why it may hold:

- support breaks can trigger stop-driven continuation;
- bearish closes below structure may change participant behavior;
- downside expansion may produce follow-through before mean reversion.

Expected failure:

- false breakdown back into range;
- one-bar liquidation wick with immediate reversal;
- too much signal overlap with ordinary Direction A-style breakout mirror.

Failure closure:

> If breakdown continuation cannot be specified without becoming a mirrored
> Direction A breakout, close H3 or require a new concept.

### 2.4 H4 - Lower-high / Lower-low Structure

Hypothesis:

> A sequence of lower highs and lower lows may define a downside lifecycle more
> cleanly than single-bar breakdown triggers.

Why it may hold:

- multi-bar structure may reduce noise relative to one-candle triggers;
- it may better capture trend state rather than entry event;
- it can be observed from closed 4h OHLCV.

Expected failure:

- structure confirms too late;
- trend is already exhausted by the time the state is visible;
- rule becomes parameter-heavy around swing definitions.

Failure closure:

> If swing/structure definition requires parameter search or subjective labels,
> pause H4 as unclear boundary.

### 2.5 H5 - Downside Volatility Expansion With Follow-through

Hypothesis:

> Downside volatility expansion plus follow-through may identify high-energy
> bearish participation states distinct from Direction C and Direction A.

Why it may hold:

- bearish expansion can compress multi-day movement into fewer bars;
- follow-through may separate breakdown continuation from one-bar noise.

Expected failure:

- expansion marks exhaustion;
- false impulse reverses;
- thresholds become mined after result.

Failure closure:

> If the concept collapses into Direction C threshold rescue or Donchian-style
> breakout rescue, close H5 for SSD scope.

### 2.6 H6 - Liquidation / Panic Leg Participation

Hypothesis:

> Liquidation or panic legs may create directional downside participation
> opportunities.

Current scope classification:

`BACKLOG_DATA_DEPENDENT`.

Reason:

- reliable liquidation/panic identification likely needs liquidation data, OI,
  funding, long/short ratio, or taker-flow data;
- current OHLCV can only approximate panic after the fact;
- using OHLCV alone risks post-hoc narrative fitting.

Failure closure:

> No current closure. H6 remains future data-dependent until Owner separately
> authorizes data dependency work.

---

## 3. Short-only Or Two-sided?

Recommendation:

> Start with **short-side-only conceptual inspect**. Do not define a two-sided
> module yet.

Reason:

- two-sided framing risks importing Direction A's long-side old path;
- short-side has the clearest structural difference from CPM/D/15m pullback;
- the first open question is whether downside lifecycle can be specified on
  its own;
- adding long side now would blur failure closure.

Two-sided may be considered later only if:

- short-side lifecycle is structurally defined first;
- long-side component is not Direction A rescue;
- both sides have independent applicability/failure boundaries;
- the result is still standalone and does not require router/portfolio/regime
  logic.

If a future two-sided concept requires dynamic switching between long and short
modules, it becomes a router/regime topic and is out of current scope.

---

## 4. Ex-ante Applicability / Failure Boundary

### 4.1 Potential Applicable States

Potential applicable states are concept-level only:

- closed 4h bearish structure;
- breakdown from support or range;
- lower-high / lower-low continuation;
- downside expansion with multi-bar follow-through;
- failed rally that does not invalidate bearish structure.

These are inspect candidates, not frozen rules.

### 4.2 Potential Failure States

Failure states must be defined before any future Level 3:

| Failure state | Ex-ante idea |
| --- | --- |
| Short squeeze | Rapid reclaim / reversal risk after bearish entry state; likely needs closed OHLCV proxy unless funding/OI data is separately authorized |
| Breakdown failure | Price breaks structure but quickly re-enters prior range or invalidates bearish state |
| Capitulation late-entry | Entry occurs after a large downside move where follow-through edge may be exhausted |
| Low-volatility chop | Repeated small breakdowns and recoveries without directional lifecycle |
| Relief-rally reversal | Failed-rally concept becomes true trend reversal |

### 4.3 No-trade / Invalidation States

Future frozen spec must pre-register:

- what invalidates bearish lifecycle;
- whether a failed breakdown blocks entry or exits;
- whether a squeeze-risk state blocks entry or only classifies evidence;
- whether late capitulation bars are excluded, and why the exclusion is not
  post-hoc.

If these cannot be defined from closed OHLCV before the run, the candidate
must be downgraded to `PAUSE_UNCLEAR_BOUNDARY` or `BACKLOG_DATA_DEPENDENT`.

### 4.4 Funding/OI Dependency Boundary

OHLCV may be enough to define a simple downside lifecycle candidate. Funding,
OI, liquidation, and long/short ratio are not required for SSD-001.

They become required only if the basic mechanism depends on:

- crowding;
- leverage build-up;
- liquidation cascade;
- squeeze probability;
- perp funding carry as a primary signal.

If those are required for mechanism definition, the candidate must move to
backlog rather than forcing an OHLCV-only experiment.

---

## 5. Current Data Needs

| Data question | Inspect answer |
| --- | --- |
| Is current 4h OHLCV enough for Level 1/2 inspect? | Yes |
| Is current 4h OHLCV enough for a future frozen spec? | Possibly, if the mechanism is breakdown/structure/expansion based and does not require crowding/liquidation |
| Is real funding required now? | No; it is a caveat for interpretation unless funding becomes a signal |
| Is OI required now? | No; future dependency only |
| Is liquidation data required now? | No; future dependency only |
| Is long/short ratio required now? | No; future dependency only |
| Is a new data pipeline authorized? | No |
| If new data is needed for the basic mechanism, what happens? | Backlog; do not proceed in this task |

Funding note:

Existing research often uses constant funding approximation rather than real
historical funding. A future short-side Level 3 plan must explicitly state
funding treatment and caveat interpretation. This does not block Level 1/2
concept inspect.

---

## 6. Future Frozen Baseline Draft

This is a draft checklist only. It does not authorize execution.

If a future Owner-approved Level 3 is requested, the plan must pre-register:

| Area | Must define |
| --- | --- |
| Direction scope | Short-only by default; two-sided only with separate Owner approval and no Direction A rescue |
| Parent timeframe | 4h primary; no 1h/15m entry timing |
| Entry lifecycle concept | One frozen concept: downside lifecycle, failed rally continuation, breakdown continuation, lower-high/lower-low structure, or downside expansion |
| Invalidation condition | What closed-bar state invalidates the bearish thesis |
| Exit lifecycle | Trend/lifecycle exit or invalidation exit; no optimized TP/SL geometry |
| Cost model | Same conservative research cost model used by MTC/CPM comparisons |
| Funding treatment | Constant approximation or real funding status must be stated; caveat if real funding absent |
| Same-bar policy | Explicit next-bar / same-bar handling; no signal-close lookahead |
| MTM DD | Must report MTM drawdown, not only realized drawdown |
| Fragility | Top-1, top-3, top-5 removal; top winner contribution |
| Year-by-year | PnL, PF, trade count, winner count, MaxDD, year concentration |
| Trade quality | MFE, MAE, giveback, average holding time |
| Squeeze diagnostics | Failed breakdown count, squeeze/reclaim behavior, adverse expansion after entry |
| Overlap | Signal overlap with Direction A and prior modules |
| Family drift | Must prove no CPM/D/15m pullback-entry drift |
| Failure closure | State exactly what a failed run closes |

No concrete parameters are selected in SSD-001.

---

## 7. Risks And Stop Conditions

Stop or downgrade if:

1. The candidate is only Direction A mirrored to short.
2. The candidate needs parameter search to be understandable.
3. Funding/OI/liquidation is required to define the basic mechanism.
4. The idea becomes pullback, failed-rally value-zone entry, or retracement
   shorting.
5. The idea needs 1h/15m entry timing.
6. Squeeze and failed-breakdown risk cannot be described before testing.
7. Capitulation late-entry risk cannot be described before testing.
8. Failure would generate variants instead of closing a hypothesis.
9. It requires runtime/profile/risk/backtester-core changes.
10. It requires router, portfolio, or regime-engine logic.
11. It is framed as runtime or small-live candidate.

Downgrade rules:

| Issue | Classification |
| --- | --- |
| Mechanical Direction A mirror | `REJECT_AS_MIRROR_OR_UNCLEAR` |
| Basic mechanism requires funding/OI/liquidation | `BACKLOG_DATA_DEPENDENT` |
| OHLCV concept exists but failure boundary unclear | `PAUSE_UNCLEAR_BOUNDARY` |
| Clear OHLCV concept, no parameters, no old-family drift | `RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN` |
| Mature Level 2 plan later accepted and Owner separately approves | `RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER` |

---

## 8. Recommendation

Final classification:

> **RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN**

Interpretation:

- Continue short-side research.
- Keep the next step Level 2 docs-only.
- Default to short-side-only, not two-sided.
- Do not request immediate Level 3 from SSD-001.
- Do not write a strategy script or run a backtest.

Reason:

- The direction is structurally different enough from CPM/D/15m pullback-entry
  to justify a frozen-plan draft.
- Current 4h OHLCV is enough to continue concept work.
- Funding/OI/liquidation are useful future caveats but not required for the
  basic OHLCV downside lifecycle inspect.
- The largest risk is Direction A mirror drift; the next plan must explicitly
  stop if that happens.

Recommended next document:

> **SSD-002 - Short-side Directional Lifecycle Frozen Experiment Plan
> (Level 2 docs-only).**

SSD-002 should freeze one concept candidate for possible future Owner Level 3
review. It must still not run anything.

---

## 9. Explicit Prohibitions

SSD-001 does not authorize:

- backtests;
- strategy scripts;
- research adapters;
- parameter sweeps;
- runtime/profile/risk/backtester-core changes;
- new data pipelines;
- Level 3 research runs;
- small-live approval;
- router / portfolio / regime-engine design;
- reopening pullback-continuation family;
- Direction A rescue;
- Direction C rescue;
- CPM rescue or CPM-MOD-003;
- Direction D rescue or variants;
- 15m pullback-entry;
- treating SSD as a runtime candidate.

---

## 10. Owner Summary

### 10.1 Continue Short-side Research?

Yes. Continue at Level 2 docs-only planning depth.

### 10.2 Short-only Or Two-sided?

Use **short-side-only** first.

Two-sided is not recommended now because it risks long-side old-path pollution,
Direction A mirror behavior, and router/regime framing.

### 10.3 OHLCV And Funding/OI

Current 4h OHLCV is enough to continue inspect and draft a future frozen plan.

Funding/OI/liquidation/long-short ratio are not required for SSD-001. They are
future dependencies only if the chosen mechanism relies on crowding, squeeze,
liquidation cascade, or funding carry as a signal.

### 10.4 Biggest Risk

The biggest risk is mechanical Direction A mirror drift.

Second-order risks:

- failed rally becomes value-zone pullback entry;
- squeeze / breakdown failure cannot be defined ex-ante;
- funding/OI becomes necessary for the basic mechanism;
- future failure generates variants rather than closing the hypothesis.

### 10.5 Recommended Next Step

Recommend:

> **SSD-002 Level 2 docs-only frozen experiment plan draft.**

Do not request immediate Owner Level 3 from SSD-001.

### 10.6 Owner Level 3

No Owner Level 3 is recommended now.

Owner Level 3 would be needed only after SSD-002 freezes one short-side concept,
defines applicability/failure boundaries, stop conditions, data caveats, and
failure closure.

### 10.7 Small-Live Readiness

Small-live readiness gate remains unmet.

There is no runtime candidate and no deployable small-live strategy.

