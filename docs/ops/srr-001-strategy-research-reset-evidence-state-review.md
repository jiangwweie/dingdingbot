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

# SRR-001 - Strategy Research Reset / Evidence-State Review

**Task ID:** SRR-001
**Date:** 2026-05-07
**Status:** Completed / Level 1-2 docs-only evidence-state review
**Authorization Level:** Level 1/2 docs-only review
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a strategy research reset and evidence-state review.

It is not:

- a new strategy experiment;
- a direction task card;
- a backtest;
- a parameter search;
- a runtime or small-live admission review;
- a research adapter, strategy script, router, portfolio, or regime-engine plan.

No backtest, script, adapter, parameter sweep, data pipeline, runtime/profile/
risk/backtester-core change, strategy promotion, small-live interpretation, or
automatic backlog promotion is authorized by SRR-001.

Binding current state:

- There is no runtime candidate.
- There is no deployable small-live strategy.
- The small-live readiness gate remains unmet.
- Live-safe foundation work remains valuable but does not imply strategy
  readiness.
- Current strategy research must focus on module validity and applicability
  boundaries, not runtime activation.

Primary docs inspected:

- `docs/ops/sr-001-strategy-research-reality-check.md`
- `docs/ops/sma-001-strategy-module-applicability-map.md`
- `docs/ops/srd-001-strategy-research-direction-refresh.md`
- `docs/ops/srd-002-non-pullback-direction-map.md`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `docs/ops/mtc-004-direction-c-frozen-baseline-research-report.md`
- `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md`
- `docs/ops/mtc-006-direction-d-structured-pullback-frozen-baseline-research-report.md`
- `docs/ops/ssd-003-short-side-breakdown-continuation-level3-research-report.md`
- `docs/ops/vei-003-volatility-expansion-impulse-participation-level3-research-report.md`
- `docs/ops/vei-004-archive-and-direction-map-update.md`
- `docs/ops/ltf-002-15m-role-freeze-data-caveat-handling-plan.md`
- `docs/ops/project-roadmap-v2.md`

---

## 1. Evidence State Review

### 1.1 Direction-Level Evidence Matrix

| Direction | Classification | Positive evidence | Negative evidence | Hypothesis closed or weakened | Automatic follow-up? | Runtime / small-live candidate? |
| --- | --- | --- | --- | --- | --- | --- |
| Direction A | `PAUSE_FRAGILE` | 4h trend-lifecycle signal is real enough to be non-empty: 172 closed positions, net +2332.51, PF 1.4227, 33 winners, moderate MTM DD 8.33%, average winner about 6x average loser | Top-3 removal -935.73, top-5 removal -1812.81, 2023/2024 carry most of net, 2022/2025 weak, research-only proxy evidence | Weakens the hypothesis that ETH 4h Donchian/EMA trend lifecycle is directly deployable as a standalone module under current fragility gates | No. Preserve as evidence; no Donchian/EMA/exit/overlay/1h rescue | No |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` | Structurally distinct from A with only 14.3% overlap; net +2039.29, PF 1.405; 3 positive years; contraction/re-expansion winners are explainable | 63 trades, 10 winners, 2021+2022 floor missed by 1 trade, top-1 is 82.25% of net, top-3 removal -2471.12, top-5 removal -3861.04, MTM DD 15.01% | Weakens the hypothesis that the frozen 4h contraction/re-expansion module provides enough independent evidence at current threshold | No. No threshold loosening or ATR-ratio rescue | No |
| CPM-1 / CPM-MOD-002 | Paused; `HYPOTHESIS_STRENGTHENED_REQUIRES_FURTHER_VALIDATION` for one narrow gate; incomplete applicability boundary | 2024/2025 positive evidence preserved; CPM-MOD-002 frozen ATR percentile gate improved 2021 by +933.37 and cut 2021 MTM DD 22.18% to 10.59%; top 10 baseline winners preserved | CPM-1 2021 OOS was negative in a favorable bull year; 2022 negative; 2023 boundary unchanged by CPM-MOD-002; overall PF still below 1 after gate; favorable-year top-N fragility remains | Closes CPM-1 as deployable candidate; weakens broad pullback-continuation profit hypothesis; partially supports only a narrow high-volatility 2021 damage boundary | No. No CPM rescue, no CPM-MOD-003, no second threshold, no feature replacement by default | No |
| Direction D | `REJECTED_FROZEN_BASELINE` | Mechanism was structurally distinct from CPM-1 and not an A variant; sample was sufficient: 417 trades, 66 winners; some real trend-lifecycle winners | Net -262.57, PF 0.985, MTM DD 29.78%, realized DD 26.22%, top-1 removal -3021.88, top-3 removal -5788.16, top-5 removal -7331.08, severe cost/churn | Closes the frozen 4h EMA60 value-zone / EMA20 resumption pullback-continuation baseline; lowers pullback-continuation family priority | No. No zone/EMA/confirmation/15m rescue | No |
| SSD-003 | `REJECTED_FROZEN_BASELINE` | Structurally distinct short-side OHLCV-only run; 0% overlap with Direction A/C; no pullback drift | Net -1699.88, PF 0.317, 23 trades, 1 winner, 2021 strongly negative, 2022-2024 no trades, 2025 single-winner positive, MTM DD 26.98%, funding/cost drag high | Closes ETH 4h OHLCV-only short-side breakdown continuation as a clean non-pullback standalone candidate under current constraints | No. Future short-side work needs a new Level 1/2 refresh with a different mechanism | No |
| VEI-003 | `PAUSE_FRAGILE` | 118 trades, 56 winners, net +630.49, PF 1.21, MTM DD 4.91%; overlap gates passed: A 27.1%, C 2.5%; follow-through filters 49% false starts; 2022-2025 positive | Independent no-A/C signals net -329.02, PF 0.86; all positive PnL comes from A-overlap echo; top-3 removal -286.85; 88% time-exit; cost drag 60.2% of gross | Weakens the hypothesis that bar-level OHLCV impulse detection is an independent profit source; confirms distinct signal set but not distinct alpha | No. No VEI variants, no timing/data rescue | No |
| 15m / sub-1h auxiliary | `ROLE_FROZEN`; `DATA_AVAILABLE_WITH_CAVEATS`; `NOT_LEVEL_3_READY` | Existing 2021-2025 15m data exists with full coverage; role can be bounded as execution timing under frozen 4h parent thesis | Zero-volume bars and 15m-to-1h/4h aggregation caveats; no parent 4h thesis frozen; old CPM-1 direct 15m migration warned of poor quality; lower timeframe raises cost/noise/overfit risk | Closes direct assumption that 15m availability implies immediate 15m strategy path; preserves only auxiliary execution-timing possibility | No. Docs-only role/caveat maintenance only | No |
| Pullback-continuation family | Lower priority / no upgradeable candidate | CPM-1 2024/2025 and CPM-MOD-002 show narrow conditional evidence can exist; Direction D was not merely CPM clone | CPM-1 failed OOS; 2023 boundary unresolved; Direction D rejected with enough sample; 15m pullback-entry would be family rescue | Weakens the family-level hypothesis that ETH pullback-ending continuation can produce a standalone small-live candidate under current evidence gates | No. Future family work needs a clearly different mechanism and ex-ante boundary before any Level 3 request | No |
| Non-pullback queue | Immediate queue exhausted | VEI and SSD provided high information-gain results; mechanisms were structurally distinct | VEI paused because independent signals negative; SSD rejected; ranks 3-7 remain backlog and should not auto-promote | Closes the current SRD-002 immediate non-pullback queue, not all future non-pullback research | No. Requires fresh Level 1/2 reset / refresh | No |

### 1.2 Evidence Interpretation

The accumulated evidence does not say "ETH has no trend signal." Direction A,
Direction C, Direction D, and VEI all found real trend or impulse captures in
some form.

The evidence says something narrower and more important:

> Under ETH / OHLCV-only / 4h or 1h / single standalone module / strict
> fragility gates, no tested or inspected module has produced a validated,
> pre-observable applicability boundary that can support runtime or small-live
> interpretation.

The strongest positive evidence is still Direction A's sparse main-trend
capture and CPM-1's conditional 2024/2025-like pullback evidence. The strongest
negative evidence is that every attempt to make those positives deployable runs
into concentration, unstable years, cost drag, independent-signal failure, or
post-hoc gate risk.

---

## 2. Common Failure Pattern

The recurring blockers are consistent across families:

| Failure pattern | Where observed | Interpretation |
| --- | --- | --- |
| Top-winner fragility | Direction A, Direction C, Direction D, VEI, SSD | Sparse trend winners are expected, but current conclusions do not survive top-3/top-5 removal often enough |
| Top-3/top-5 removal turns negative | A, C, D, VEI | Positive aggregate PnL depends on a narrow winner cluster |
| Year concentration | A, C, CPM-1, D, SSD | Positive evidence clusters in specific years or isolated periods without a prior enablement rule |
| Independent signal failure | VEI | Signal-set distinctness is not the same as independent alpha |
| Positive evidence depends on overlap | VEI with Direction A; A/D asymmetric overlap | Different mechanics can still monetize the same few trend moves |
| Trade or winner count insufficiency | C; SSD winner count | Positive net cannot be promoted when there are too few independent winners |
| Cost drag | CPM-1, Direction D, VEI, SSD | Gross or modest edges are consumed by fees/slippage/funding assumptions; Direction D gross positive became net negative |
| MTM DD too high | Direction C, D, SSD, CPM-1 OOS | Closed-trade metrics understate actual open-position risk |
| Applicability boundary missing | All major directions | The biggest blocker: no module can yet say before the trade when it is valid versus invalid |
| OHLCV-only continuation vs exhaustion ambiguity | CPM-1, D, VEI, SSD | Closed OHLCV often detects movement but not whether that movement is continuation, exhaustion, squeeze, or churn |
| Single frozen baseline positive but not deployable | A, C, VEI, CPM-MOD-002 partial | A positive frozen run can remain research evidence only if fragility and boundary gates fail |

The repeated shape is not random. OHLCV-only signals can identify trend,
impulse, pullback, and breakdown structures, but they have repeatedly failed to
identify whether those structures are still in a valid continuation state before
the decision.

---

## 3. Hypothesis Space Assessment

### 3.1 Which Explanation Fits Best?

| Candidate explanation | Current read | Reason |
| --- | --- | --- |
| A. Specific entry/exit rules were just poor | Partly true, insufficient | Some frozen rules were poor, especially Direction D and SSD, but the same failure modes repeat across structurally distinct rules |
| B. ETH 4h / 1h OHLCV-only single-module space is temporarily exhausted | Strongly supported for the current constraint set | A, C, CPM, D, SSD, VEI, and 15m auxiliary review have not produced a candidate; immediate non-pullback queue is exhausted |
| C. Missing pre-observable applicability gate | Strongly supported | This is the maximum blocker across SR-001, SMA-001, CPM-MOD-002, D, SSD, and VEI |
| D. Missing extra data such as funding/OI/liquidation/taker-flow | Plausible future hypothesis, not proven | These data may help distinguish crowding, squeeze, toxic state, continuation, and exhaustion, but no data task is authorized and no rescue should assume them |
| E. Standalone single-module small-live target may be too strict | Plausible Owner-level question | Evidence suggests standalone modules are fragile, but relaxing this target would affect strategy governance and should not be done automatically |
| F. Portfolio/router/regime may eventually be needed | Future capability hypothesis only | The evidence hints that conditional modules may matter, but current stage must not implement router/portfolio/regime |
| G. Research evaluation standard is too strict | Not currently supported | The standard is strict but aligned with deployment risk. Lowering it would mainly allow fragile positives to pass |
| H. Need different asset, timeframe, or strategy type | Plausible future research route | Multi-asset/cross-asset or range/mean-reversion may be worth Level 1/2 inspect, but not automatic implementation |

### 3.2 Current Judgment

The failure is not best explained by one bad entry or exit rule. It is better
explained as:

> The current ETH / OHLCV-only / 4h-or-1h / single standalone module / strict
> fragility-gate hypothesis space is stagewise exhausted for immediate
> runtime/small-live candidate discovery.

This does not mean:

- ETH has no exploitable structure;
- OHLCV-only research is permanently useless;
- all future standalone modules are impossible;
- router, portfolio, regime, or new data pipelines should be built now.

It means the next research question should move up one level:

> What evidence, methodology, applicability boundary, or data dependency would
> be required before spending another Level 3 run?

---

## 4. Research Principle Check

| Principle | Still reasonable? | Evidence-state read |
| --- | --- | --- |
| A single strategy need not work in every year | Yes | A, C, CPM, and VEI all show that year selectivity may be natural |
| Sparse returns are acceptable | Yes | Direction A validates that rare trend winners can be real |
| Low win rate and high payoff ratio are acceptable | Yes | Direction A's 19.19% win rate and high payoff ratio are coherent with trend capture |
| Focus on main trend segment capture | Yes, but incomplete | Trend capture exists, but trend-capture evidence alone has not solved applicability |
| Modules can be conditional / enabled only in valid states | Yes | This is the correct research framing after CPM-MOD-002 and SMA-001 |
| Applicability boundary must be pre-observable | Yes, more important than before | This is the dominant blocker and should not be weakened |
| Do not prematurely implement dynamic router / portfolio / regime | Yes | Current evidence is insufficient to justify infrastructure expansion |

### 4.1 Potential Principle Tensions

There are two Owner-level tensions, not automatic changes:

1. **Standalone module vs conditional module.** If every promising signal is
   conditional, the Owner may need to decide whether "standalone single-module
   small-live candidate" remains the right near-term target or whether research
   should first prove conditional validity at the module level without runtime
   switching.

2. **Strict fragility gates vs sparse trend logic.** Sparse trend systems
   naturally concentrate winners. The current gates allow that in principle but
   still block current candidates. If the Owner wants to accept more
   concentration risk, that would be a governance decision, not a research
   default.

Owner decision questions:

- Should the near-term research target remain a standalone single-module
  small-live candidate, or should Level 1/2 research explicitly study what
  evidence would be required for conditional modules without implementing
  routing?
- Should the top-3/top-5 fragility gates remain binding exactly as MTC-001, or
  should a future methodology review define a separate sparse-trend acceptance
  band for research-only evidence?

---

## 5. Possible Next Research Routes

### Option A - Continue OHLCV-only, But Shift To Applicability Boundary Research

Goal:

- Do not search for a new entry.
- Identify whether existing fragile positives have pre-observable valid and
  invalid states.

Could answer:

- Can Direction A, C, CPM-1, or VEI be explained by prior market-state features
  without selecting winning years after the fact?

Risks:

- Very high post-hoc filtering risk.
- Easy to rediscover "skip the bad years" under a technical label.

Requirements:

- Gate feature, window, and threshold must be defined before any empirical
  check.
- No threshold sweep.
- No runtime router or dynamic switch.

Current fit:

- Useful only if framed as methodology and boundary validation first, not
  immediate module rescue.

### Option B - Pause ETH OHLCV-Only Single-Module Work And Do Data-Dependency Inspect

Goal:

- Inspect whether funding, OI, liquidation, taker-flow, mark/index spread, or
  related data could plausibly solve continuation vs exhaustion, crowding,
  squeeze, or toxic-state ambiguity.

Could answer:

- Are current failures asking questions OHLCV cannot answer?
- Which exact data would be needed, for which named hypothesis?

Risks:

- Scope creep into data pipeline or feature store.
- Funding/OI rescue of failed modules without a separate inspect.

Requirements:

- Docs-only inspect.
- No ingestion, schema, adapter, or data repair.
- No claim that extra data would rescue CPM, VEI, D, SSD, A, or C.

Current fit:

- Reasonable as a follow-up inspect after methodology framing, especially
  because OHLCV-only continuation/exhaustion ambiguity is recurring.

### Option C - Re-Evaluate Multi-Asset / Cross-Asset As Research Hypothesis

Goal:

- Decide whether research should compare ETH/BTC/SOL or cross-asset context at
  Level 1/2 only.

Could answer:

- Is ETH-specific structure the blocker?
- Are similar OHLCV signals more stable on BTC or SOL?
- Could cross-asset context help define applicability?

Risks:

- Complexity increase.
- Data/cost consistency problems.
- Drift into multi-asset runtime.

Requirements:

- No runtime multi-asset implementation.
- No portfolio engine.
- No exchange profile or risk change.

Current fit:

- Plausible but not first recommendation. It broadens scope before the
  methodology problem is clarified.

### Option D - Research Methodology Upgrade

Goal:

- Improve the research framework before generating more strategy candidates.

Possible scope:

- walk-forward design;
- OOS slicing rules;
- fragility-aware scoring;
- signal overlap accounting;
- independent-winner counting;
- applicability boundary validation;
- post-hoc gate detection;
- data-dependency decision criteria.

Could answer:

- What must be true before another Level 3 run is worth spending?
- How should a conditional module be judged without building a router?
- How should overlap and independent alpha be accounted for?

Risks:

- Does not produce a strategy candidate immediately.
- Can become abstract if not tied to current evidence.

Requirements:

- Docs-only.
- No new strategy spec.
- No backtest.
- No lowering of gates without Owner decision.

Current fit:

- Strongest next step. It directly addresses the repeated blocker and prevents
  another fragile Level 3 branch.

### Option E - Pause Strategy Research And Focus On Engineering / Reporting / Observability

Goal:

- Accept that no deployable strategy exists now and continue useful system
  foundation work.

Advantages:

- Avoids overfit research churn.
- Live-safe, reporting, owner console, and observability remain useful if a
  future candidate appears.

Risks:

- No progress toward small-live candidate discovery.
- Strategy evidence gap remains open.

Requirements:

- Explicit Owner acceptance that strategy research is paused.
- No interpretation of live-safe progress as strategy readiness.

Current fit:

- Reasonable if Owner wants to stop research burn for now.

### Option F - Reopen Strategy Direction Refresh

Goal:

- Level 1/2 refresh that does not inherit VEI/SSD/D/C/A failure paths.

Could answer:

- Is there a genuinely different research family worth inspecting?
- Which backlog idea is structurally new rather than an old rescue?

Risks:

- Auto-promotes backlog ranks without enough reflection.
- Produces another Level 3 candidate too quickly.

Requirements:

- Must state how each proposed direction differs from A, C, CPM, D, SSD, VEI,
  15m pullback-entry, overlay stacking, and 1h entry timing.
- Must include closure conditions before any Level 3 request.

Current fit:

- Useful after Option D or as a narrower companion to it. Not recommended as an
  immediate jump to a new candidate queue.

---

## 6. Recommended Next Step

**Recommended path:** Option D - Research Methodology Upgrade, with an explicit
applicability-boundary validation framework. Option B data-dependency inspect
can be the next Owner decision after that framework defines what data questions
are legitimate.

**Why now:**

- The immediate non-pullback queue is exhausted.
- Pullback-continuation priority is lowered.
- Direction A/C/VEI show positive-but-fragile signals, while D/SSD reject
  frozen baselines.
- The repeated blocker is no longer "which entry next"; it is how to validate
  a module's applicability boundary without post-hoc fitting.

**What it would answer:**

- What qualifies as a pre-observable applicability boundary?
- How should independent alpha be distinguished from overlap echo?
- How should sparse trend concentration be judged without pretending rare
  winners are unacceptable?
- What makes a future Level 3 request admissible?
- When is extra data a legitimate dependency rather than a rescue narrative?

**What it must not do:**

- It must not define a new strategy entry.
- It must not run a backtest.
- It must not sweep thresholds.
- It must not select no-trade years.
- It must not implement or design router/portfolio/regime.
- It must not produce a runtime or small-live candidate.

**Required Owner decision:**

- Confirm whether the next Level 1/2 document should focus on methodology
  upgrade first, or whether Owner prefers to pause strategy research and return
  to engineering / observability work.
- Confirm whether standalone single-module small-live candidate remains the
  near-term target, or whether Level 1/2 research may define evidence standards
  for conditional modules without implementing runtime switching.

**Suggested next document name:**

`docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`

---

## 7. Explicit Prohibitions

SRR-001 explicitly prohibits:

- VEI variants;
- Direction A rescue;
- Direction C rescue;
- CPM rescue;
- CPM-MOD-003;
- Direction D variants;
- SSD variants;
- 15m entry timing rescue;
- 15m pullback-entry;
- 1h entry search;
- overlay stacking;
- funding/OI rescue without separate inspect;
- automatic data pipeline work;
- router implementation;
- portfolio implementation;
- regime implementation;
- runtime/profile/risk/backtester-core changes;
- strategy scripts;
- research adapters;
- parameter sweeps;
- backtests;
- Level 3 activation;
- small-live interpretation;
- runtime candidate interpretation;
- automatic promotion of any backlog candidate.

---

## 8. Owner Summary

### 8.1 Is The Current Strategy Space Stagewise Exhausted?

Yes, with an important qualifier.

The current constrained space is stagewise exhausted for immediate candidate
discovery:

> ETH / OHLCV-only / 4h or 1h / single standalone module / strict fragility
> gates has not produced a runtime or small-live candidate after A, C, CPM,
> D, SSD, VEI, 15m role review, pullback-continuation review, and non-pullback
> queue exhaustion.

This is not a permanent rejection of ETH, OHLCV, trend capture, or future
strategy research.

### 8.2 Maximum Common Blocker

The maximum common blocker is:

> No module has a validated, pre-observable applicability boundary that
> survives enough trades, enough winners, top-winner fragility, year
> concentration, independent-signal checks, MTM drawdown, and realistic costs.

### 8.3 Should Standalone Single-Module Small-Live Candidate Remain The Target?

For runtime promotion, yes by default. The project should not relax this
silently.

But research should ask an Owner decision question:

> Should Level 1/2 research continue to require a standalone single-module
> small-live path, or should it first define evidence standards for conditional
> modules without implementing router/portfolio/regime?

### 8.4 Recommended Level 1/2 Route

Recommended next route:

> SRR-002 Research Methodology And Applicability Boundary Upgrade.

This is docs-only and should precede any new Level 3 request.

### 8.5 Routes Not Recommended Now

Not recommended now:

- VEI variants;
- CPM/D/A/C/SSD rescue;
- 15m or 1h timing rescue;
- automatic backlog candidate promotion;
- funding/OI rescue before a data-dependency inspect;
- router / portfolio / regime implementation;
- another frozen baseline before methodology and applicability gates are
  clarified.

### 8.6 Small-Live Readiness

Small-live readiness gate remains unmet.

There is still:

- no runtime candidate;
- no deployable small-live strategy;
- no strategy module ready for promotion;
- no authorization to change runtime/profile/risk or live behavior.

