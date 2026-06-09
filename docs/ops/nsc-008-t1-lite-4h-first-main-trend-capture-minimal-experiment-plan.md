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

# NSC-008 — T1-lite 4h-first Main Trend Capture Minimal Experiment Plan

**Date:** 2026-05-06
**Status:** Proposed / Experiment Plan Only
**Scope:** Docs-only experiment plan draft
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a proposed experiment plan only. It does not authorize running experiments, implementing strategies, changing runtime profiles, changing risk rules, modifying backtester / research engine core, or making any promotion, small-live, or live deployment decision.

Allowed scope for this task:

- `docs/ops/**`
- `archive/**` inspect-only
- `reports/**` inspect-only

Forbidden scope:

- `src/**`
- `configs/**`
- `tests/**`
- `migrations/**`
- runtime profiles
- production strategy implementation
- risk rules
- backtester / research engine core

Not allowed under this plan:

- backtests or experiment execution;
- strategy implementation;
- runtime/profile/risk changes;
- parameter sweep;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- feature store;
- complex ML;
- CPM-1 rescue;
- CPM-2 A/B rescue;
- Candidate C automatic fallback;
- T1 + CPM-1 portfolio combination.

Current state remains unchanged:

- CPM-1 remains paused and is not a small-live candidate.
- CPM-2 Candidate A/B are closed as research proxy insufficient.
- Candidate C remains reserve-only.
- The project has no deployable small-live strategy candidate.
- Small-live readiness gate remains unmet until a new candidate module passes an Owner-approved minimum evidence gate and later operational review.

---

## 1. Purpose

NSC-007 concluded that T1-lite standalone trend-continuation is the highest-priority next candidate direction and should proceed to a separate experiment plan.

Owner's current hypothesis:

> 顺大逆小，但不应只吃回调后的那一段，而应抓主要的一段大趋势。

Owner's 4h-first judgment:

> 1h 周期可以继续，但趋势周期越大可信度越高，因此 4h 交易值得探索。

This plan therefore treats T1-lite as a **4h-first standalone main-trend capture candidate**.

T1-lite is not:

- CPM-1 rescue;
- CPM-2 rescue;
- CPM fixed-TP modification;
- CPM 4h Pinbar migration;
- CPM-1 + T1 portfolio leg;
- multi-strategy runtime pre-work;
- regime-system pre-work.

---

## 2. T1-lite Versus CPM

| Dimension | CPM | T1-lite |
| --- | --- | --- |
| Module identity | ETH 1h pullback-continuation segment module | 4h-first main-trend capture / trend lifecycle module |
| Primary profit source | Pullback ends, then local continuation reaches fixed TP geometry | Main trend segment extends and trailing exit captures the larger move |
| Primary timeframe | 1h with 4h confirmation | 4h first; 1h only optional for later entry refinement |
| Entry intent | Reversal / reclaim after local pullback | Continuation after major trend confirmation, or entry timing inside qualified major trend |
| Exit intent | Fixed short-R TP structure | ATR trailing, structure trailing, or trend invalidation |
| Failure tolerance | Local false pullback-end confirmation | Whipsaw and rare-winner concentration |
| Runtime interpretation | Existing CPM family | New standalone candidate family |

Old CPM 4h Pinbar is not the current direction:

- historical notes classify ETH 4h Pinbar as too thin, around 17 trades/year or otherwise statistically weak;
- the current plan is about 4h main-trend capture, not moving CPM candlestick geometry to 4h;
- T1-lite must not become "CPM but with 4h Pinbar and trailing."

---

## 3. Shared Experiment Contract

### 3.1 Candidate Order

First-round priority:

1. **T1-A — Pure 4h Main-trend Capture**.
2. **T1-B — 4h Major Trend Qualification + 1h Pullback/Reclaim Entry**, reserve / second candidate.

T1-A should run first if NSC-009 is later approved. It directly tests whether the 4h main-trend capture idea has standalone edge.

T1-B should not be run in the same first gate unless Owner explicitly approves it, because it opens more rule freedom and risks drifting back toward CPM-style pullback repair.

### 3.2 Data Windows

Use the same windows for all first-pass T1-lite evidence:

| Window | Role |
| --- | --- |
| 2021 full year | Primary OOS failure reference from CPM-1; bull-year stress for trend lifecycle |
| 2022 full year | Bear / whipsaw reference; tests LONG-only trend-following cost of being wrong |
| 2023 full year | CPM weak-follow-through reference; historically positive in corrected T1-R |
| 2024 full year | Positive reference; must not be explained only by one trend |
| 2025 full year | Positive / continuation reference; must preserve evidence after costs |

No additional years, assets, directions, or timeframes may be added after seeing results without a new Owner-approved plan.

### 3.3 Cost Model Source

Use CPM-1 official OOS report cost model as the SSOT unless a future Owner-approved execution task explicitly freezes a more precise T1-specific cost model before execution.

The experiment report must record exact values for:

- fee rate;
- entry slippage;
- trailing / stop exit slippage;
- funding enabled/disabled state;
- funding approximation value;
- whether costs are applied on entry, partial exit, final exit, and stop/trailing exit.

Any improvement caused only by lower turnover or cost compression, without gross expectancy or loss-cluster improvement, must not be treated as strategy validation.

### 3.4 Same-bar / Next-bar Policy

Required policy:

- Signal decisions use only fully closed bars.
- Entry must occur on the next eligible bar open after the signal decision.
- No same-bar entry based on a signal bar close.
- Stop/trailing conflicts in the same bar must use pessimistic ordering.
- If the harness cannot express next-bar entry and anti-lookahead timing, classify as `HARNESS_INFEASIBLE`.

The experiment report must explicitly prove that signal detection, entry fill, ATR/trailing updates, and stop checks do not use future candles.

### 3.5 MTM Drawdown Requirement

T1-lite evidence must report mark-to-market drawdown, not only realized drawdown.

Required:

- realized MaxDD;
- MTM MaxDD;
- year-by-year MTM MaxDD;
- worst open-position adverse excursion;
- whether a large trend trade creates hidden interim drawdown before exit.

Realized-only drawdown is insufficient because T1-R audit showed original drawdown was understated without MTM tracking.

### 3.6 Fragility Gate

Trend-following can naturally depend on rare winners, but T1-lite cannot be interpreted without concentration reporting.

The report must include:

- top 1 winner as percentage of total net PnL;
- top 3 winners as percentage of total net PnL;
- net PnL excluding top 1 winner;
- net PnL excluding top 3 winners;
- year-by-year winner concentration;
- whether the strategy remains interpretable after removing top winners.

Minimum gate:

- If top 1 winner contributes more than 50% of total net PnL, classify no better than `PAUSE_FRAGILE`.
- If top 3 winners exceed 100% of total net PnL and net PnL excluding top 3 is negative, classify no better than `PAUSE_FRAGILE` unless Owner pre-accepts rare-winner dependence in a later evidence review.
- If positive evidence exists only because of one year or one trade cluster, classify as `INSUFFICIENT_EVIDENCE` or `PAUSE_FRAGILE`, not pass.

### 3.7 Minimum Trade Count Floor

Because T1-lite is lower-frequency than CPM, the floor should be lower than CPM-2 but still interpretable.

Minimum first-pass floor:

- at least 20 closed positions across 2021+2022 combined;
- at least 60 closed positions across 2023+2024+2025 combined;
- at least 80 closed positions across 2021+2025 combined.

If T1-A falls below this floor, classify as `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`, even if PnL is positive.

For T1-B, the same floor applies unless a later plan freezes a different floor before execution.

### 3.8 Year-by-year Requirements

The report must include:

- closed positions count by year;
- gross PnL before costs by year;
- net PnL after costs by year;
- PF by year;
- win rate by year;
- average win / average loss by year;
- MTM MaxDD by year;
- top-winner concentration by year;
- average and median hold duration by year;
- funding exposure by year.

Minimum pass shape:

- 2023/2024/2025 combined must be net positive after costs.
- At least two of 2023/2024/2025 should be net positive after costs.
- 2021/2022 combined loss must be bounded and explainable by trend-following whipsaw, not uncontrolled drawdown.
- No single year may be the only reason the full-window result is positive without triggering `PAUSE_FRAGILE`.

### 3.9 Hold Duration / Funding Exposure

T1-lite is designed to hold longer than CPM when the main trend continues. The report must therefore include:

- average hold duration;
- median hold duration;
- max hold duration;
- distribution of holds by `<1 day`, `1-3 days`, `3-7 days`, `7-14 days`, `>14 days`;
- funding intervals held;
- funding cost by year and as percentage of gross PnL;
- longest exposure period and its MTM drawdown.

Long hold duration is not a failure by itself. It becomes a pause/reject reason if funding, MTM drawdown, or operational exposure makes the evidence non-interpretable or outside the intended low-frequency lifecycle profile.

### 3.10 Classification Format

Every future experiment report must end with:

```markdown
## Failure / Evidence Classification

| Field | Value |
| --- | --- |
| Candidate | T1-A or T1-B |
| Frozen rule hash / description | ... |
| Classification | PASS_MIN_EVIDENCE / PAUSE_FRAGILE / PAUSE_MIXED_EVIDENCE / REJECT_NO_EXPECTANCY / REJECT_LOCAL_SEGMENT_ONLY / REJECT_FAMILY_DRIFT / INSUFFICIENT_EVIDENCE_THIN_SAMPLE / HARNESS_INFEASIBLE |
| Primary reason | ... |
| Captures main trend? | Yes / No / Mixed |
| Gross expectancy improved? | Yes / No |
| Net after costs positive? | Yes / No |
| MTM drawdown acceptable for evidence review? | Yes / No / Mixed |
| Top-winner concentration acceptable? | Yes / No / Mixed |
| Trade count floor met? | Yes / No |
| 2021/2022 behavior explainable? | Yes / No / Mixed |
| 2023/2024/2025 behavior acceptable? | Yes / No / Mixed |
| Runtime/profile/risk change implied? | No |
| Promotion conclusion | None |
```

---

## 4. T1-A — Pure 4h Main-trend Capture

### 4.1 Strategy Hypothesis

T1-A tests whether ETH 4h main-trend continuation has standalone edge when entry waits for a major trend confirmation and exit lets the trend lifecycle run.

Hypothesis:

> 4h Donchian-style continuation entry plus 4h trailing exit can capture the main segment of ETH trends better than CPM-style fixed short-R pullback exits, while remaining low-frequency and interpretable.

### 4.2 Entry Rule Family

First-round family:

- 4h Donchian-style breakout / continuation.
- Signal bar is a fully closed 4h candle.
- Donchian high / structure high uses previous bars only and excludes the signal bar.
- Entry occurs on the next 4h bar open after signal confirmation.

The future NSC-009 task must freeze one exact rule before execution. Recommended frozen shape:

```text
signal_high = max(previous 20 closed 4h highs)
accept LONG signal if signal_bar.close > signal_high
entry = next 4h bar open with frozen entry slippage
```

Not allowed:

- Donchian lookback sweep;
- ATR multiplier sweep;
- mixing breakout, EMA cross, and pivot rules in one run;
- adding 1h filters after seeing results;
- switching to 1h because 4h is thin.

### 4.3 Exit Rule Family

Exit must aim to capture the main trend segment, not short local TP geometry.

Allowed first-round family:

- 4h ATR trailing exit;
- 4h structure trailing exit;
- 4h trend invalidation exit.

The future NSC-009 task must freeze one exact exit before execution. Recommended frozen shape:

```text
initial_stop = previous 20-bar 4h structure low
trailing_activation = fixed R threshold chosen before execution
trailing_stop = watermark_high - fixed ATR multiple using 4h ATR
stop only ratchets upward for LONG
```

This plan does not approve choosing the best of several exit variants. One exit must be frozen before running.

### 4.4 Required Data

Required:

- ETH/USDT:USDT 4h OHLCV for 2021-2025;
- 4h ATR inputs;
- fee/slippage/funding cost settings from the frozen cost model;
- enough pre-window warmup bars for Donchian and ATR.

Not required for first pass:

- 1h candles;
- orderbook/tick data;
- funding alpha features;
- OI/spread/volume feature store;
- multi-asset data.

### 4.5 Main-trend Versus Local Segment

T1-A is intended to capture main trend segments.

Evidence must show:

- winners are not dominated by tiny local moves;
- average/median hold duration is consistent with trend lifecycle capture;
- trailing exits, not fixed short TP, drive the main profit capture;
- large winners are explainable as trend lifecycle capture and not lookahead artifacts.

Reject if the result only captures short local breakout pops and exits quickly without main-trend participation.

### 4.6 Anti-lookahead Requirements

Must prove:

- Donchian/structure high excludes the signal bar;
- signal uses only fully closed 4h candle data;
- ATR for signal/trailing uses only available closed candles;
- entry occurs on next 4h bar open, never the signal bar open;
- trailing update order is pessimistic: check existing stop first, then update trailing stop from the closed bar;
- cross-year warmup does not reset indicators in a way that creates artificial signals.

### 4.7 Same-bar / Next-bar Convention

Required:

- Signal: closed 4h bar.
- Entry: next 4h bar open.
- Stop/trailing: pessimistic same-bar handling.
- If signal bar is the last available bar and no next entry bar exists, record `REJECT_NO_ENTRY_BAR`.

### 4.8 Gates

T1-A must satisfy the shared gates in Section 3.

Additional T1-A pause/reject conditions:

- `PAUSE_FRAGILE` if top-winner concentration is excessive.
- `REJECT_LOCAL_SEGMENT_ONLY` if exits show only short local pop capture.
- `REJECT_FAMILY_DRIFT` if the experiment adds CPM-style pullback / Pinbar conditions.
- `HARNESS_INFEASIBLE` if no non-invasive harness path can express next-bar 4h breakout entry and trailing exit without core changes.

---

## 5. T1-B — 4h Major Trend Qualification + 1h Pullback/Reclaim Entry

### 5.1 Strategy Hypothesis

T1-B tests whether 1h can improve entry timing inside a qualified 4h major trend without turning T1-lite back into CPM-style pullback repair.

Hypothesis:

> 4h defines the main trend lifecycle; 1h only improves entry location after a 4h trend is qualified. The profit source remains the 4h main trend, captured through trailing exit, not a short local rebound segment.

### 5.2 Entry Rule Family

Two-stage family:

1. 4h major trend qualification.
2. 1h pullback/reclaim entry inside the qualified 4h trend.

The future task must freeze exact rules before execution. A valid shape would be:

```text
4h trend qualified by prior closed 4h structure / Donchian / EMA trend condition
1h entry waits for pullback and reclaim within the qualified 4h trend
entry occurs on next eligible 1h bar open after 1h confirmation
```

1h is allowed only for entry timing.

1h must not become:

- CPM-1 Pinbar rescue;
- CPM-2 reclaim rescue;
- lower-wick confirmation variant;
- local fixed-TP segment strategy;
- parameterized pullback filter search.

### 5.3 Exit Rule Family

Exit must remain trend-lifecycle oriented:

- 4h ATR trailing;
- 4h structure trailing;
- 1h execution of a 4h-derived trailing stop if needed for fill convention;
- trend invalidation based on 4h structure.

Reject if T1-B uses fixed short-R TP as the primary profit source.

### 5.4 Required Data

Required:

- ETH/USDT:USDT 4h OHLCV for trend qualification and trailing;
- ETH/USDT:USDT 1h OHLCV for entry timing only;
- 4h ATR or structure inputs;
- exact cost model values;
- sufficient warmup for both 4h and 1h indicators.

No new external data is required for first-pass planning.

### 5.5 Main-trend Versus Local Segment

T1-B must prove that the 4h trend remains the profit source.

Required report checks:

- entry-to-exit hold duration;
- percentage of exits caused by trailing / trend invalidation versus short local exit;
- MFE/MAE measured against 4h trend lifecycle;
- whether winners continue after the 1h reclaim or only capture a local bounce;
- whether 1h entry reduces adverse entry without truncating trend winners.

If T1-B behaves like CPM-2 with a different exit label, classify as `REJECT_FAMILY_DRIFT`.

### 5.6 Anti-lookahead Requirements

Must prove:

- 4h trend qualification uses only fully closed 4h bars available before 1h entry decision;
- 1h confirmation uses only fully closed 1h bars;
- entry uses next eligible 1h bar open after confirmation;
- 4h trailing state does not use future 4h candles;
- no future 1h candles are used to choose the entry variant.

### 5.7 Same-bar / Next-bar Convention

Required:

- 4h qualification is evaluated only after 4h close.
- 1h entry confirmation is evaluated only after 1h close.
- Entry occurs on next eligible 1h bar open.
- Stop/trailing conflicts use pessimistic ordering.

### 5.8 Gates

T1-B must satisfy shared gates in Section 3, plus:

- must show that 1h entry improves entry quality without converting the strategy into local segment capture;
- must not depend on combining several 1h reclaim/pullback rules;
- must not start until T1-A is planned and either executed or explicitly paused/rejected by Owner.

Recommended current status:

| Field | Value |
| --- | --- |
| Candidate | T1-B |
| First-round status | Reserve / second candidate |
| Reason | More rule freedom; higher family-drift risk |
| Earliest next step | Separate Owner-approved plan or explicit inclusion after T1-A decision |

---

## 6. Historical Evidence Interpretation Boundary

### 6.1 T1 Original / T1-R

Historical T1 evidence can inform candidate selection but cannot be promoted directly.

Rules:

- Original T1 4h Donchian results had same-bar entry lookahead contamination and cannot be used as positive validation.
- T1-R corrected result can be used as a source for T1-A direction.
- T1-R corrected result is positive but fragile.
- T1-R corrected result must not be treated as T1-lite standalone validation.
- Any future experiment must re-run under a frozen plan with anti-lookahead, MTM drawdown, funding exposure, and fragility reporting.

Required caveat in future reports:

```text
Historical T1-R is direction evidence only. It is not T1-lite validation, not promotion evidence, and not small-live readiness evidence.
```

### 6.2 C1/C2 Portfolio Proxy

C1/C2 evidence may be cited only as a warning:

- T1 can be fragile because top winners dominate returns.
- Correlation / diversification may look useful but cannot validate standalone edge.
- Official-parity portfolio checks showed fragility became more severe under different accounting.

C1/C2 must not be used to:

- claim T1-lite standalone is validated;
- justify a portfolio engine;
- justify T1 + CPM-1 combination;
- launch capital allocation search;
- revive CPM-1 as a portfolio base.

### 6.3 Old CPM 4h Pinbar

Old CPM 4h Pinbar evidence is outside this plan:

- historical notes show 4h Pinbar had too few trades for reliable interpretation;
- it belongs to CPM candlestick geometry migration, not T1-lite main-trend capture;
- it should not be used as an argument against 4h trend lifecycle testing, because T1-lite's entry/exit family is different.

---

## 7. Harness Feasibility Gate For NSC-009

If Owner later approves NSC-009, it must start with a harness feasibility gate.

NSC-009 may proceed only if Candidate T1-A can be expressed without:

- modifying runtime profiles;
- modifying risk rules;
- registering production strategy implementation;
- changing `src/**` production/backtester core semantics;
- creating portfolio/regime/multi-strategy infrastructure.

If current harness cannot express the frozen rule:

1. stop immediately;
2. classify as `HARNESS_INFEASIBLE`;
3. output a feasibility gap report;
4. do not modify the engine or implement runtime strategy.

NSC-009, if approved, is a minimal experiment execution gate only. It is not runtime implementation and not live-readiness work.

---

## 8. Pass / Pause / Reject Summary

### T1-A

| Outcome | Condition |
| --- | --- |
| `PASS_MIN_EVIDENCE` | Meets trade floor, net/gross evidence, year-by-year shape, MTM drawdown, funding exposure, and fragility gates without family drift |
| `PAUSE_FRAGILE` | Positive but dominated by top 1/top 3 winners or one year |
| `PAUSE_MIXED_EVIDENCE` | Some years strong, but 2021/2022 or 2024/2025 behavior is ambiguous |
| `REJECT_NO_EXPECTANCY` | Gross and net expectancy fail after costs |
| `REJECT_LOCAL_SEGMENT_ONLY` | Captures local breakout pops but not main trend lifecycle |
| `REJECT_FAMILY_DRIFT` | Becomes CPM rescue, CPM 4h Pinbar, or portfolio/regime dependency |
| `INSUFFICIENT_EVIDENCE_THIN_SAMPLE` | Trade count floor not met |
| `HARNESS_INFEASIBLE` | Cannot execute frozen rule without forbidden implementation/core changes |

### T1-B

| Outcome | Condition |
| --- | --- |
| `PASS_MIN_EVIDENCE` | Only possible after separate Owner-approved execution; must prove 1h is entry timing only and 4h trend remains profit source |
| `PAUSE_FRAGILE` | Positive but dominated by top winners |
| `PAUSE_MIXED_EVIDENCE` | 1h entry helps some years but damages trend capture in others |
| `REJECT_NO_EXPECTANCY` | Gross and net expectancy fail |
| `REJECT_LOCAL_SEGMENT_ONLY` | Becomes a 1h local segment strategy |
| `REJECT_FAMILY_DRIFT` | Becomes CPM-1/CPM-2 rescue or multi-rule reclaim search |
| `INSUFFICIENT_EVIDENCE_THIN_SAMPLE` | Trade count floor not met |
| `HARNESS_INFEASIBLE` | Cannot execute without forbidden changes |

---

## 9. Recommended First-round Priority

| Priority | Candidate | Recommendation | Reason |
| --- | --- | --- | --- |
| 1 | T1-A — Pure 4h main-trend capture | First-round plan/execution candidate | Directly validates whether 4h main-trend capture has standalone edge |
| 2 | T1-B — 4h qualification + 1h entry timing | Reserve / second candidate | Higher rule freedom; risks drifting back into CPM-style pullback repair |

First-round NSC-009, if approved, should execute T1-A only unless Owner explicitly expands scope before execution.

---

## 10. Final Boundary

This plan recommends preparing for a separate Owner-approved NSC-009 minimal experiment execution gate for T1-A.

This plan does not:

- authorize NSC-009 automatically;
- authorize runtime implementation;
- make T1-lite a small-live candidate;
- make any promotion conclusion;
- revive CPM-1;
- rescue CPM-2 A/B;
- start Candidate C;
- start portfolio, regime, multi-strategy, multi-asset, feature-store, or ML work.

Any future experiment result may enter evidence review only. It does not represent promotion, small-live candidate status, or live deployment readiness.

Small-live readiness gate remains unmet.
