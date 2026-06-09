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

# SSD-002 - Short-side Directional Lifecycle Frozen Experiment Plan

**Task ID:** SSD-002
**Date:** 2026-05-07
**Status:** Completed / Level 2 docs-only frozen plan draft
**Authorization Level:** Level 2 - docs-only planning
**Source:** SSD-001 accepted short-side / two-sided directional lifecycle inspect
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document selects one short-side-only 4h OHLCV concept for possible future
Owner Level 3 review.

It is not:

- a backtest request;
- a strategy script or research adapter;
- parameter selection;
- parameter optimization;
- a Level 3 run;
- runtime/profile/risk/backtester-core work;
- new funding/OI/liquidation data pipeline work;
- router, portfolio, or regime-engine design;
- runtime candidate or small-live readiness review.

No experiment, runtime candidate, deployable strategy, or small-live conclusion
follows from SSD-002.

---

## 1. Selected Frozen Concept

### 1.1 Selected Concept

SSD-002 selects exactly one concept:

> **Short-side 4h breakdown continuation.**

Concept statement:

> ETH may produce short-side directional lifecycle opportunities after a closed
> 4h breakdown from an observable structure, if the breakdown represents
> downside continuation rather than a one-bar liquidation wick, failed
> breakdown, or late capitulation entry.

### 1.2 Why This Concept Was Selected

Breakdown continuation is preferred over the other SSD-001 concepts because:

| SSD-001 concept | Reason not selected as first plan |
| --- | --- |
| Downside trend lifecycle | Too broad for a first frozen plan; useful umbrella, weak closure |
| Failed rally continuation | Highest risk of drifting into retracement/value-zone short entry |
| Lower-high / lower-low structure | Plausible but swing definition may require subjective labels or parameter choices |
| Downside expansion with follow-through | Higher risk of becoming Direction C expansion rescue or threshold mining |
| Liquidation / panic leg participation | Data-dependent; needs liquidation/OI/funding/taker-flow to be credible |

Breakdown continuation is narrow enough to write stop conditions and broad
enough to remain structurally different from pullback-continuation.

### 1.3 Current Plan Classification

Current classification:

> **RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER**

Meaning:

- SSD-002 is not Owner Level 3 authorization.
- The concept is worth future Owner Level 3 review only if Owner accepts this
  docs-only frozen plan and separately authorizes execution.
- No code, adapter, backtest, or parameter work is authorized here.

---

## 2. Why This Is Not An Old Path

### 2.1 Not Direction A Mechanical Short Mirror

This plan is not "Direction A, but short" because it must be defined around
short-side breakdown lifecycle risks:

- failed breakdown back into prior structure;
- short squeeze after bearish entry state;
- late capitulation entry after an already-extended downside move;
- one-bar liquidation wick that does not become continuation;
- funding/carry caveat for short exposure.

Direction A's long-side identity is Donchian20 close breakout plus EMA60
lifecycle exit. SSD-002 does not select Donchian20, does not mirror Direction A
parameters, and does not reuse Direction A's long-side evidence as short-side
evidence.

Mandatory future overlap check:

- If future Level 3 signals are just Direction A entries mirrored to the short
  side, classify `REJECT_AS_MIRROR_OR_UNCLEAR`.

### 2.2 Not Direction C Volatility Expansion Rescue

Direction C tested contraction followed by re-expansion and paused as
`INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`.

SSD-002 does not rescue Direction C because:

- it does not depend on contraction;
- it does not loosen ATR-ratio;
- it does not tune re-expansion thresholds;
- expansion may be diagnostic evidence, but the selected concept is breakdown
  continuation from structure, not volatility expansion by itself.

If a future plan can only be expressed as "bearish Direction C with adjusted
thresholds," it must stop.

### 2.3 Not CPM / Direction D / 15m Pullback-Continuation

SSD-002 is not pullback-continuation because it does not ask whether a pullback
has ended.

Explicit exclusions:

- no CPM Pinbar / wick trigger;
- no 1h pullback-ending confirmation;
- no Direction D EMA60 value-zone touch;
- no EMA20 resumption confirmation;
- no failed-rally value-zone short;
- no 15m pullback-entry or risk-compression entry;
- no retracement-to-better-price thesis.

If the future plan becomes "short after a rally into a value zone," classify it
as pullback-continuation drift and stop.

### 2.4 Not Router / Regime / Portfolio

SSD-002 is one standalone research concept:

- short-only;
- ETH/USDT:USDT;
- 4h parent timeframe;
- OHLCV-only unless future Owner separately authorizes data dependency work.

It does not decide when to switch between strategies, allocate capital across
modules, combine long and short modules, or manage a portfolio.

---

## 3. Future Level 3 Frozen Requirements

If Owner later approves Level 3, the run must freeze all items below before any
execution.

### 3.1 Scope

| Field | Frozen requirement |
| --- | --- |
| Asset | ETH/USDT:USDT |
| Direction | Short-only |
| Timeframe | 4h parent / decision timeframe |
| Lower timeframe | None; no 1h or 15m entry timing |
| Data | Closed OHLCV only unless Owner separately authorizes data dependency |
| Strategy family | Non-pullback short-side directional lifecycle |

### 3.2 Entry Lifecycle State

The future Level 3 plan must define one objective 4h breakdown-continuation
entry lifecycle state.

It must define, without parameter sweep:

- what structure can break;
- what counts as a closed-bar breakdown;
- what, if any, confirms continuation after breakdown;
- how to avoid one-bar liquidation wick interpretation;
- what makes the entry a lifecycle state rather than a local short scalp.

SSD-002 does not select exact lookbacks, thresholds, indicators, or structure
parameters.

### 3.3 Invalidation Condition

The future Level 3 plan must define one closed-bar invalidation condition:

- breakdown failure back into prior structure;
- squeeze/reclaim state;
- bearish thesis invalidated by structure recovery;
- late capitulation condition if used as an entry blocker.

The invalidation condition must be observable before or at the decision point.
It must not be inferred from final trade outcome.

### 3.4 Exit Lifecycle

The future Level 3 plan must define one exit lifecycle:

- lifecycle invalidation exit; or
- trend-structure exit; or
- pre-registered protective exit.

It must not:

- optimize TP/SL geometry;
- introduce fixed short-R local scalp exits as the profit source;
- add trailing / BE variants after results;
- select among multiple exits after seeing performance.

### 3.5 Same-bar / Next-bar Policy

The future Level 3 plan must explicitly state:

- signal bar must be fully closed;
- entry convention must avoid signal-close lookahead;
- next-bar or same-bar handling must be predeclared;
- if same-bar conflicts can occur, pessimistic conflict handling and conflict
  counts must be reported.

### 3.6 Cost Model

The future Level 3 plan must use the same conservative research cost model used
for current MTC / CPM comparisons unless Owner separately approves a global
research cost-model update.

It must report:

- fees;
- slippage;
- funding cost;
- gross vs net;
- total cost drag as a share of gross PnL/loss.

No cost relaxation is allowed.

### 3.7 Funding Treatment Caveat

Funding is not a signal in this plan.

Future Level 3 must state:

- whether funding uses the current constant approximation;
- whether real historical funding exists;
- how missing real funding affects short-side interpretation;
- whether funding exposure is large enough to caveat evidence.

If the mechanism cannot be defined without actual funding, OI, liquidation, or
long/short data, classify `BACKLOG_DATA_DEPENDENT` before running.

### 3.8 Required Metrics And Diagnostics

Future Level 3 must report at minimum:

| Area | Required output |
| --- | --- |
| Overall | net PnL, PF, win rate, trade count, winner count |
| Drawdown | realized MaxDD and MTM MaxDD |
| Fragility | top-1, top-3, top-5 removal; top winner contribution |
| Year-by-year | yearly PnL, PF, trade count, winner count, DD, year concentration |
| Trade quality | MFE, MAE, giveback, average holding time |
| Breakdown diagnostics | failed-breakdown count, reclaim behavior, continuation vs failure attribution |
| Squeeze diagnostics | adverse expansion after entry, squeeze/reclaim cluster, short-side invalidation attribution |
| Late capitulation | entries after extended downside moves; whether winners/losers cluster there |
| Costs | fees, slippage, funding, total cost drag |
| Overlap | Direction A overlap, Direction C overlap, CPM-1 overlap, Direction D overlap |
| Family drift | evidence that the result is not CPM/D/15m pullback-entry |

### 3.9 Overlap And Drift Checks

Future Level 3 must include:

- Direction A overlap: if the result is just mechanical short mirror, reject.
- Direction C overlap: if it is bearish expansion threshold rescue, reject or
  downgrade.
- CPM-1 overlap: if timing behaves like pullback-ending confirmation, reject.
- Direction D overlap: if entries depend on value-zone resumption, reject.
- 15m drift: any need for 15m entry timing stops the plan.

---

## 4. Failure Closure

If future Owner-approved Level 3 fails, the failure closes:

> **The hypothesis that ETH 4h OHLCV-only short-side breakdown continuation is
> a clean, non-pullback, standalone directional lifecycle candidate under the
> current research constraints.**

Failure must not automatically generate:

- alternate breakdown thresholds;
- support/range lookback variants;
- Direction A mirrored variants;
- bearish Direction C threshold variants;
- failed-rally value-zone entries;
- 1h/15m timing branches;
- funding/OI rescue;
- router / portfolio / regime proposals.

Allowed post-failure action:

- archive result;
- update strategy applicability map;
- decide whether the entire short-side immediate path is paused or whether a
  different non-pullback bucket deserves docs-only inspect.

---

## 5. Downgrade / Stop Conditions

### 5.1 Pre-Level 3 Downgrades

| Condition | Required classification |
| --- | --- |
| Concept can only be defined by mirroring Direction A | `REJECT_AS_MIRROR_OR_UNCLEAR` |
| Basic mechanism requires funding/OI/liquidation data | `BACKLOG_DATA_DEPENDENT` |
| OHLCV concept exists but squeeze / failed breakdown / late capitulation boundaries are unclear | `PAUSE_UNCLEAR_BOUNDARY` |
| Concept boundary is clear but not yet executed | `RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER` |

### 5.2 Stop Conditions During Future Planning

Stop if future planning requires:

- parameter search;
- multiple breakdown definitions;
- two-sided logic;
- Direction A/C/CPM/D rescue;
- 1h/15m entry timing;
- pullback or value-zone short entry;
- funding/OI/liquidation data pipeline;
- runtime/profile/risk/backtester-core changes;
- router, portfolio, or regime-engine logic.

### 5.3 Stop Conditions During Future Level 3

If Level 3 is later approved, stop/downgrade if:

- trade count or winner count is too low to interpret;
- net/PF/DD fail clearly;
- top-1/top-3/top-5 removal shows severe fragility;
- year concentration is not explainable;
- MTM DD is unacceptable;
- cost drag overwhelms gross edge;
- same-bar/signal-close semantics are unclear;
- squeeze or failed-breakdown diagnostics cannot be produced;
- result depends on post-hoc no-trade conditions.

---

## 6. Current Recommendation

Current classification:

> **RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER**

This means:

- the selected concept is worth future Owner Level 3 review;
- no Level 3 is approved by SSD-002;
- no experiment can start from this document;
- Owner must separately approve Level 3 with a frozen spec before execution.

Recommended next action:

> Owner review of SSD-002. If accepted, Owner may decide whether to authorize a
> separate SSD-003 Level 3 research-only frozen run.

SSD-003, if ever authorized, must be a single frozen run and must not include
parameter search or alternate variants.

---

## 7. Explicit Prohibitions

SSD-002 does not authorize:

- backtests;
- strategy scripts;
- research adapters;
- parameter choices or parameter sweeps;
- two-sided module definition;
- Direction A rescue;
- Direction C rescue;
- CPM rescue or CPM-MOD-003;
- Direction D rescue or variants;
- 1h entry timing;
- 15m entry timing;
- 15m pullback-entry;
- funding/OI/liquidation data pipeline;
- runtime/profile/risk/backtester-core changes;
- Level 3 execution;
- small-live approval;
- router / portfolio / regime-engine design;
- runtime candidate interpretation.

---

## 8. Owner Summary

### 8.1 Recommended Frozen Concept

Recommended frozen concept:

> **Short-side 4h breakdown continuation.**

It is selected as the first short-side concept because it is narrower than the
general downside lifecycle idea, less pullback-prone than failed rally
continuation, less subjective than lower-high/lower-low structure, and less
likely than pure downside expansion to become Direction C rescue.

### 8.2 Worth Future Owner Level 3 Review?

Yes, but only later and only by separate Owner authorization.

Current classification:

> **RECOMMEND_OWNER_LEVEL_3_REQUEST_LATER**

SSD-002 itself does not approve Level 3.

### 8.3 Biggest Risk

The biggest risk is mechanical Direction A mirror drift.

Other major risks:

- failed-breakdown and squeeze boundaries are not clean enough;
- late capitulation entries dominate;
- concept drifts into failed-rally value-zone shorting;
- funding/OI/liquidation becomes necessary to define the mechanism.

### 8.4 Failure Closure

If future Level 3 fails, it closes:

> ETH 4h OHLCV-only short-side breakdown continuation as a clean immediate
> non-pullback standalone candidate under current constraints.

It must not spawn parameter variants, 1h/15m timing branches, funding/OI rescue,
or pullback-continuation variants.

### 8.5 Small-Live Readiness

Small-live readiness gate remains unmet.

There is no runtime candidate and no deployable small-live strategy.

