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

# SRD-001 - Strategy Research Direction Refresh

**Task ID:** SRD-001
**Date:** 2026-05-07
**Status:** Completed / Docs-only direction refresh
**Authorization Level:** Level 1/2 - docs-only
**Scope:** Strategy research direction refresh after SMA-003
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document refreshes the strategy research direction after CPM-MOD-002,
MTC-006, SMA-003, and LTF-002.

It is not:

- a backtest request;
- strategy script or adapter authorization;
- parameter optimization;
- Level 3 research authorization;
- runtime/profile/risk/backtester-core work;
- new data pipeline authorization;
- strategy router, portfolio, or regime-engine design;
- runtime candidate or small-live readiness review.

No runtime candidate, deployable small-live strategy, profile change, strategy
enablement, risk-rule change, or live/canary conclusion follows from this
document.

Current binding state:

- No runtime candidate.
- No deployable small-live strategy.
- Small-live readiness gate remains unmet.
- Pullback-continuation empirical experiments are paused.

---

## 1. Current Research State Review

### 1.1 Why Pullback-Continuation Is Lower Priority

The pullback-continuation family now has three layers of negative or incomplete
evidence:

| Object | Current read | Family implication |
| --- | --- | --- |
| CPM-1 | Paused; 2024/2025 favorable-market evidence exists, but 2021/2023 remain critical counter-evidence | Existing pullback module has no validated applicability boundary |
| CPM-MOD-002 | Clean frozen ATR-percentile gate avoided part of 2021 high-volatility damage and preserved 2024/2025 | Narrow 2021-style volatility-damage hypothesis strengthened, but not full dynamic enablement |
| Direction D / MTC-006 | `REJECTED_FROZEN_BASELINE`; 417 trades / 66 winners, net -262.57, PF 0.985, realized MaxDD 26.22%, MTM MaxDD 29.78%, severe top-N failure | A structurally different 4h pullback-continuation mechanism still failed after costs, DD, and fragility |

This is no longer a "sample too thin" problem for the family. Direction D had
enough trades and winners. The blocker is evidence quality and lack of a clean,
pre-observable applicability boundary.

### 1.2 What CPM-MOD-002 Changed

CPM-MOD-002 changed the CPM-1 evidence state in a narrow way:

- It proved a single pre-registered OHLCV volatility gate can avoid part of
  2021-style high-volatility damage.
- It preserved 2024/2025 under that one frozen gate.
- It did not worsen overall top-N fragility.

CPM-MOD-002 did not change:

- It did not identify the 2023 failure boundary.
- It did not validate CPM-1 as a runtime candidate.
- It did not authorize CPM-MOD-003, a second volatility threshold, realized
  volatility substitution, composite scores, E4 labels, sizing treatment, or a
  router.
- It did not prove the pullback-continuation family can be enabled and disabled
  safely in general.

### 1.3 Why MTC-006 Rejects Direction D

MTC-006 is strong enough to reject Direction D because the failure survived the
main ambiguity checks:

- It was a clean frozen Level 3 research-only run.
- It had enough sample: 417 closed trades and 66 winners.
- It was not a Direction A variant by stop rule: Direction A overlap was
  29.50%.
- It did not show clear CPM drift, so the rejection is not merely "CPM in
  disguise."
- It still failed net/PF/DD/top-N: net PnL -262.57, PF 0.985, realized MaxDD
  26.22%, MTM MaxDD 29.78%, top-1 removal -3021.88, top-3 removal -5788.16,
  and top-5 removal -7331.08.

Direction D solved Direction C's trade-count problem but produced worse
evidence quality. That is a real rejection, not a reason to search zone widths,
EMA periods, confirmation variants, or 15m timing.

### 1.4 Why Old Paths Must Stay Closed

The next research direction should not continue:

- CPM rescue, because CPM-MOD-002 only strengthened a narrow 2021 volatility
  damage hypothesis and left 2023 unexplained.
- Direction D variants, because MTC-006 rejected the frozen baseline after
  enough trades/winners.
- 15m pullback-entry, because LTF-002 freezes 15m as execution timing under a
  frozen 4h thesis, not as a new pullback strategy mainline.
- Direction A/C rescue, because Direction A is `PAUSE_FRAGILE` and Direction C
  is `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`.
- 1h entry rule search, D2/D3/D4, and overlay stacking, because prior evidence
  shows marginal improvement or fragility without solving the applicability
  boundary blocker.

---

## 2. New Candidate Direction Buckets

### 2.1 Summary Table

| Bucket | Profit source | Expected market condition | Failure mode | Required data | Is current OHLCV enough? | Future data dependency | Thin-core conflict? | Current classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1. Non-pullback directional map | Directional asymmetry from trend state, impulse state, and lifecycle state without pullback entry | Clearly directional 4h market with measurable persistence or one-sided downside/upside pressure | Recreates Direction A under new names; too abstract to close a hypothesis | Existing 4h OHLCV docs and evidence | Yes for inspect | None | Low if docs-only | **Immediate inspect** |
| B2. Short-side / two-sided directional module | Downside trend participation or asymmetric short lifecycle capture | Bear legs, failed rallies, breakdown continuation, downside volatility expansion | Short-side overtrading in chop; funding/cost caveats; mirror-copy of long rules | 4h OHLCV; cost/funding caveat | Yes for inspect; real funding better later | Real funding optional future caveat, not current blocker | Low if standalone research-only | **Immediate inspect** |
| B3. Volatility expansion / impulse participation | Participation in impulse moves after range expansion, not pullback continuation | Compression break or sudden expansion with follow-through potential | Becomes Direction C threshold rescue or Donchian20 breakout rescue; false impulses | 4h OHLCV: range, ATR, close location, volume if available | Yes | None for first inspect | Low if not parameterized | **Candidate inspect** |
| B4. Trend persistence without value-zone pullback | Continuation after persistent closes, higher-high / higher-low structure, or trend-strength persistence | Mature but not overextended directional markets | Enters too late; year concentration; top-winner fragility | 4h OHLCV | Yes | None | Low-Moderate; risk of Direction A variant | **Candidate inspect, after B1** |
| B5. Trend exhaustion avoidance / validity gate | Avoiding trades when trend state is extended, toxic, or near failure | Extended or unstable directional markets where entries are prone to reversal | Post-hoc no-trade gate; kills rare winners; becomes overlay stacking | 4h OHLCV for simple gate; funding/OI if crowding gate | OHLCV enough only for simple inspect | Funding/OI if crowding-based | Moderate; can become regime engine | **Backlog unless tied to a frozen module** |
| B6. Range / mean-reversion module | Range support/resistance mean reversion; chop-period carry | Sideways, bounded, low directional persistence markets | Boundary fitting; stop runs; conflicts with trend thesis; high overfit | OHLCV for range definition | Yes for inspect | Spread/orderbook useful later, not current | Moderate; new strategy family | **Backlog / optional inspect** |
| B7. Funding/OI-informed module | Crowding, leverage, or funding-pressure asymmetry | Perp-specific crowded trend, squeeze, or liquidation-prone state | Requires new data; becomes regime engine; threshold fitting | Funding history, OI, possibly long/short and liquidation data | No | Yes: future data dependency | High under current scope | **Backlog, not current** |
| B8. Cross-timeframe execution-only auxiliary | Entry/execution improvement under a frozen parent thesis | Parent 4h thesis is already active and frozen | Drifts into 15m mainline or pullback-entry rescue | 15m/1h OHLCV plus parent signal definition | Yes for docs-only role work | No new pipeline | Low only if role-bound | **Docs-only backlog** |

### 2.2 Bucket Notes

**B1. Non-pullback directional map** is the safest first step because it is a
map, not an experiment. It should define which non-pullback profit sources are
structurally distinct from Direction A, Direction C, CPM-1, Direction D, and
15m pullback-entry before any Level 3 request exists.

**B2. Short-side / two-sided directional module** has the highest structural
difference from the failed pullback-continuation family. It asks whether ETH
downside regimes contain cleaner directional lifecycle evidence than long-only
pullback or long-only breakout variants. It must not become a symmetric copy of
Direction A with short/long labels flipped; it needs its own failure hypothesis.

**B3. Volatility expansion / impulse participation** may be worth inspect if it
is framed as impulse participation, not Direction C threshold rescue and not
Donchian20 rescue. The inspect must define what makes an impulse different from
ordinary breakout continuation.

**B4. Trend persistence without value-zone pullback** is a candidate only if it
uses persistence or structure state rather than value-zone pullback. It must
avoid becoming Direction D without the word "pullback."

**B5. Trend exhaustion avoidance / validity gate** is dangerous as a standalone
direction. A no-trade gate is useful only if the toxic state is specified before
the run and tied to a frozen module. Otherwise it becomes post-hoc fitting.

**B6. Range / mean-reversion** is structurally different and could be inspected
later, but it is a new strategy family and conflicts more with the current
trend-research thesis. It is not rejected, but it should not outrank B1/B2.

**B7. Funding/OI-informed module** is conceptually attractive for crypto, but
current scope does not authorize a new data pipeline. It belongs in backlog
until Owner separately approves data capability work.

**B8. Cross-timeframe execution-only auxiliary** preserves LTF-002. It cannot
be used to make 15m an independent mainline or to rescue Direction D.

---

## 3. Explicitly Closed Old Paths

SRD-001 explicitly does not reopen:

- Direction A parameter rescue;
- Direction A Donchian/EMA/exit micro-variants;
- Direction C ATR-ratio rescue;
- Direction C re-expansion threshold rescue;
- CPM rescue;
- CPM-MOD-003;
- second CPM volatility threshold;
- CPM realized-volatility replacement experiment;
- CPM composite M0 score, E4 label, or sizing treatment;
- Direction D zone search;
- Direction D EMA search;
- Direction D confirmation search;
- Direction D 15m entry-timing rescue;
- 15m pullback-entry rescue;
- pullback-continuation family new trigger branches;
- overlay stacking;
- 1h entry rule search;
- B-D2 / B-D3 / B-D4;
- strategy router;
- portfolio engine;
- regime engine;
- runtime/profile/risk/backtester-core modification.

If a future proposal is best described as "same family, new trigger," it should
be rejected or backloged before Level 3.

---

## 4. Applicability Hypotheses By Bucket

| Bucket | Applicable market ex-ante? | Failure market ex-ante? | If not identifiable | Post-hoc gate risk | If future failure occurs, closes or weakens |
| --- | --- | --- | --- | --- | --- |
| B1. Non-pullback directional map | Inspect should define observable trend/impulse/lifecycle states before choosing a module | Inspect should define chop, failed trend, and no-edge states | Reject specific sub-bucket; do not proceed to Level 3 | Low while docs-only; high if it jumps straight to filters | Closes the assumption that a non-pullback direction can be specified cleanly from current evidence |
| B2. Short-side / two-sided directional module | Potentially: 4h downtrend, breakdown, lower-high structure, downside expansion | Potentially: low-volatility chop, violent short squeezes, relief rallies | Backlog if short-specific boundary cannot be defined before testing | Moderate if short filters are added after seeing squeeze losses | Closes the hypothesis that short/downside lifecycle capture is a structurally distinct near-term candidate |
| B3. Volatility expansion / impulse participation | Potentially: pre-defined expansion/impulse state from closed OHLCV | Potentially: failed impulse, expansion into exhaustion, chop spikes | Backlog or reject if "impulse" cannot be separated from Donchian/Direction C rescue | High if thresholds are chosen after result | Closes the hypothesis that impulse participation is distinct from Direction C and Direction A |
| B4. Trend persistence without value-zone pullback | Potentially: consecutive persistence, trend-strength, structure-state measures | Potentially: mature exhaustion, late entries, low follow-through | Reject if it collapses into Direction A variant or D-like continuation | Moderate | Closes the hypothesis that persistence state improves trend lifecycle evidence without pullback logic |
| B5. Trend exhaustion avoidance / validity gate | Only if toxic state is pre-registered and computed before entry | Only if the gate also predicts when not to disable | Backlog; no standalone gate until paired with frozen module | Very high | Closes the specific toxic-state hypothesis, not the whole parent module |
| B6. Range / mean-reversion | Potentially: bounded range, low directional persistence, repeated support/resistance reactions | Potentially: breakout/trend transition, range expansion, one-sided volatility | Backlog if range definition is subjective | High | Closes the hypothesis that OHLCV-defined ranges are researchable without orderbook/spread data |
| B7. Funding/OI-informed module | Yes in principle, but not with current data | Yes in principle: crowded funding/OI extremes can be specified | Backlog until data exists | High if threshold-mined | Closes nothing now; future failure would close a data-dependent crowding hypothesis |
| B8. Cross-timeframe execution-only auxiliary | Only under a frozen parent 4h thesis | Parent thesis inactive, conflict with 15m signal, high churn/cost | Backlog until parent thesis exists | High if it becomes entry rescue | Closes whether lower-timeframe execution improves a frozen parent, not whether 15m is a strategy |

Applicability boundary rule:

> A candidate should not request Level 3 unless both its applicable market and
> failure market can be described from information available before the trade.

If the only visible path is "run it, then find the no-trade years," the
candidate should stay backlog or be rejected.

---

## 5. Level 1/2 To Level 3 Upgrade Gate

A future candidate is worth Owner Level 3 only if it satisfies all of the
following before the run:

1. Mechanism structure is clear enough to write a frozen spec without searching.
2. It is structurally different from Direction A, Direction C, CPM-1,
   Direction D, and 15m pullback-entry.
3. It does not depend on parameter search, threshold sweep, or multi-version
   comparison.
4. It uses current OHLCV, or any new data requirement is explicitly declared
   and separately authorized before strategy research.
5. Applicability and failure boundaries are pre-observable.
6. Stop conditions are explicit: trade/winner floors, top-N fragility,
   year concentration, MTM drawdown, cost sensitivity, family drift, and
   post-hoc gate risk.
7. The run can produce enough information gain to change the map.
8. Failure closes or materially weakens one named hypothesis rather than
   generating new trigger branches.
9. It does not require runtime/profile/risk/backtester-core changes.
10. It cannot be interpreted as runtime or small-live approval.

Level 3 should be denied when:

- the candidate is a renamed pullback-continuation trigger;
- the candidate requires a router, portfolio engine, or regime engine to make
  sense;
- the candidate needs 15m to rescue an already rejected 4h idea;
- the result would obviously lead to "try one more threshold."

---

## 6. Recommended Next-Step Ordering

### 6.1 Ranking

| Rank | Next step | Why | Authorization | Output | If it fails |
| --- | --- | --- | --- | --- | --- |
| 1 | Non-pullback direction map | Prevents jumping from failed pullback evidence into another vaguely defined trigger | Level 1/2 docs-only | Map of structurally distinct non-pullback candidates and rejection criteria | Closes near-term strategy research until a clearer mechanism appears |
| 2 | Short-side / two-sided directional inspect | Most structurally different near-term OHLCV candidate; tests long-only bias without new data pipeline | Level 1/2 docs-only | Inspect spec only; no backtest | Closes short/downside lifecycle as immediate candidate if boundary is unclear |
| 3 | Volatility expansion / impulse participation inspect | Potentially distinct from pullback and Direction A if impulse is defined cleanly | Level 1/2 docs-only | Inspect spec only; no thresholds or run | Backlog if it becomes C threshold rescue or Donchian rescue |
| 4 | Range / mean-reversion inspect | Different profit source, but higher overfit and weaker alignment with trend thesis | Level 1/2 docs-only optional | Inspect only | Backlog/reject if range definition is subjective |
| 5 | Funding/OI data dependency inspect | Useful later for crowding/exhaustion, but requires new data pipeline | Level 1/2 docs-only dependency note only | Data dependency map | Remains backlog without Owner data authorization |
| 6 | Pause empirical strategy experiments | Avoids branch generation while live-safe foundation continues | Level 1/2 decision | No strategy experiment | Preserves evidence integrity |

### 6.2 First Recommendation

First recommended direction:

> **SRD-002 / Non-Pullback Direction Map, with short-side / two-sided
> directional module as the first concrete inspect target.**

Rationale:

- It avoids pullback-continuation rescue paths.
- It does not require funding/OI/orderbook/spread data for the first inspect.
- It is structurally different from CPM-1, Direction D, and 15m pullback-entry.
- It can be kept Level 1/2 docs-only.
- It can close a useful hypothesis before any Level 3 request: whether
  short/downside directional lifecycle capture is clean enough to specify.

Second candidate:

> **Volatility expansion / impulse participation inspect**, only if it can be
> defined without becoming Direction C threshold rescue or Donchian20 rescue.

Backlog candidates:

- Range / mean-reversion module inspect.
- Funding/OI-informed module and data dependency inspect.
- Cross-timeframe execution-only auxiliary work.

Reject / do-not-start:

- CPM-MOD-003.
- Direction D follow-up.
- 15m pullback-entry.
- Any pullback-continuation trigger branch.
- Direction A/C parameter rescue.
- Overlay stacking and 1h entry rule search.

---

## 7. Small-Live Readiness

Current readiness remains unchanged:

- There is no runtime candidate.
- There is no deployable small-live strategy.
- Live-safe foundation does not mean strategy ready.
- CPM-MOD-002's 2021 improvement does not create small-live permission.
- MTC-006 Direction D rejection keeps the pullback-continuation family below
  upgrade priority.
- Any new direction must pass future Owner-approved evidence gates before it
  can even enter a readiness discussion.

No candidate in SRD-001 is a runtime candidate.

---

## 8. Owner Summary

### 8.1 Continue Strategy Research?

Yes, but only in docs-only inspect mode for now. The correct conclusion is not
"strategy research has no hope." The correct conclusion is:

> **There is no short-term deployable candidate, and the next research step
> must leave the pullback-continuation family rather than rescue it.**

### 8.2 Recommended New Direction Order

| Rank | Direction | Classification |
| --- | --- | --- |
| 1 | Non-pullback direction map | Immediate Level 1/2 docs-only |
| 2 | Short-side / two-sided directional inspect | First concrete Level 1/2 inspect target |
| 3 | Volatility expansion / impulse participation inspect | Candidate inspect if structurally distinct |
| 4 | Range / mean-reversion inspect | Backlog / optional inspect |
| 5 | Funding/OI-informed module | Backlog; future data dependency |
| 6 | Cross-timeframe execution-only auxiliary | Docs-only backlog; not 15m mainline |

### 8.3 First Recommendation And Reason

First recommendation:

> **Run a Level 1/2 docs-only non-pullback direction map, then prioritize
> short-side / two-sided directional inspect as the first concrete candidate.**

Reason:

- Pullback-continuation has no upgradeable candidate after CPM-MOD-002 and
  MTC-006.
- Short/downside directional lifecycle is structurally different from CPM/D.
- Existing OHLCV is enough for inspect.
- The inspect can define stop conditions and applicability boundaries before
  any Level 3 request.

### 8.4 Reject / Backlog

Reject or do not start:

- Direction A rescue;
- Direction C rescue;
- CPM rescue / CPM-MOD-003;
- Direction D variants;
- 15m pullback-entry rescue;
- pullback-continuation new trigger branches;
- overlay stacking;
- 1h entry rule search;
- D2/D3/D4;
- router / portfolio / regime engine.

Backlog:

- Funding/OI-informed module until data dependency is separately authorized.
- Range / mean-reversion until a clean range boundary can be specified.
- Cross-timeframe execution-only auxiliary until a parent 4h thesis exists.

### 8.5 Owner Level 3

No Owner Level 3 is recommended from SRD-001.

Owner Level 3 would be needed only after a future Level 1/2 inspect produces:

- a frozen mechanism;
- a pre-observable applicability boundary;
- clear stop conditions;
- no dependency on parameter search or new unauthorized data;
- a statement of what failure would close.

### 8.6 Prohibitions

Do not run backtests, write strategy scripts, sweep parameters, modify
runtime/profile/risk/backtester core, introduce a new data pipeline, start
Level 3, approve small-live, design router/portfolio/regime systems, or treat
any SRD-001 bucket as a runtime candidate.

### 8.7 Small-Live Gate

Small-live readiness gate remains unmet.

There is still no runtime candidate and no deployable small-live strategy.

