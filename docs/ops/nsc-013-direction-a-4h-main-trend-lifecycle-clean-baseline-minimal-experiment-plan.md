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

# NSC-013 — Direction A 4h Main Trend Lifecycle Clean Baseline Minimal Experiment Plan

**Task ID:** NSC-013
**Date:** 2026-05-06
**Status:** Proposed / Experiment Plan Only
**Scope:** Docs-only minimal experiment plan
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a proposed experiment plan only. It does not authorize
running experiments, writing code, creating adapters, implementing strategies,
changing runtime profiles, changing risk rules, modifying backtester /
research engine core, making promotion conclusions, making small-live
conclusions, or giving live deployment advice.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, or `migrations/`.

Allowed scope for this task:

- `docs/ops/**`
- `reports/**` inspect-only
- `archive/**` inspect-only

Forbidden scope:

- `src/**`
- `configs/**`
- `tests/**`
- `migrations/**`
- runtime profiles
- production strategy implementation
- risk rules
- backtester / research engine core

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`; top-winner fragility failed |
| T1-B | Reserve-only; not executed |
| Direction A | NSC-011 conclusion: `PROCEED_TO_EXPERIMENT_PLAN` |
| Direction E | NSC-012 conclusion: companion research; defer to optional overlay / second pass |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. Purpose

Direction A is the current P0 main strategy research direction from Strategy
Candidate Direction Map v1.

The clean baseline experiment has three goals:

1. Verify whether 4h main trend lifecycle capture has standalone edge.
2. Isolate the structural difference between EMA60 close-break exit and
   T1-A's ATR trailing exit.
3. Establish a clean Direction A baseline before adding companion overlays,
   1h entry timing, portfolio, regime, or multi-strategy logic.

This plan explicitly does not test:

- Direction E overlay;
- E-A one-bar false-breakout early exit;
- 1h entry timing;
- T1-B;
- portfolio / regime / multi-strategy;
- Donchian / ATR / EMA / lookback parameter sweep.

---

## 3. Strategy Hypothesis

> ETH 4h main trends can be captured by entering after a structural breakout
> and exiting when the 4h trend lifecycle weakens, represented by a fully
> closed 4h candle close below EMA60. The strategy accepts sparse profits,
> low win rate, profit giveback, and rare large winners, provided the edge is
> not fully dependent on one anomalous year or a handful of top winners.

Direction A differs from CPM and T1-A:

| Dimension | CPM | T1-A frozen rule | Direction A clean baseline |
| --- | --- | --- | --- |
| Primary timeframe | 1h | 4h | 4h |
| Profit source | Pullback-continuation local segment | 4h breakout trend capture | 4h main trend lifecycle |
| Entry family | Pinbar / pullback confirmation | Donchian20 breakout | Donchian20 breakout |
| Exit family | Fixed TP/SL / CPM geometry | 1.5R activation + 3x ATR14 trailing | EMA60 close-break trend-lifecycle exit |
| Current purpose | Paused | Paused evidence source | New clean baseline plan |

Direction A is not:

- CPM-1 rescue;
- CPM-2 rescue;
- T1-A parameter rescue;
- CPM fixed-TP modification;
- CPM 4h Pinbar migration;
- T1 + CPM-1 portfolio leg;
- multi-strategy runtime pre-work;
- regime-system pre-work.

---

## 4. Frozen Clean Baseline Rule

The first-round clean baseline is frozen as a single rule family.

### 4.1 Entry

| Field | Frozen Definition |
| --- | --- |
| Entry family | 4h Donchian breakout / continuation entry |
| Donchian lookback | `N = 20` closed 4h bars |
| Signal | Fully closed 4h signal candle close > previous 20 closed 4h high |
| Signal bar in window? | Excluded |
| Entry execution | Next 4h bar open after signal close |
| Entry slippage | Frozen cost model from Section 8 |
| Same-bar entry | Not allowed |

N=20 is inherited from T1-A as a known baseline source. It is not claimed to
be optimal. No Donchian N sweep is allowed.

### 4.2 Initial Risk Stop

| Field | Frozen Definition |
| --- | --- |
| Initial stop family | Previous N closed 4h structure low / Donchian low |
| Lookback | Same `N = 20` closed 4h bars as the entry window |
| Signal bar in stop window? | Excluded |
| Stop execution | Stop / risk exit under predeclared next-bar or stop convention in the adapter report |
| Stop status | Must remain active throughout the trade |

The initial stop is mandatory. The clean baseline must not rely only on EMA60
exit, because EMA60 is a lifecycle exit, not a hard initial risk boundary.

No initial stop lookback sweep is allowed.

### 4.3 Trend-lifecycle Exit

| Field | Frozen Definition |
| --- | --- |
| Exit family | 4h EMA60 close-break trend-lifecycle exit |
| EMA period | `EMA60` on 4h closes |
| Exit trigger | Fully closed 4h candle close below EMA60 |
| Intrabar EMA touch | Does not trigger exit |
| Exit execution | Next 4h bar open after exit trigger close, with frozen exit slippage |
| Exit trigger bar | The closed 4h bar whose close is below EMA60 |
| Exit execution bar | The next 4h bar after trigger |

EMA60 is inherited from NSC-011 as the first-round trend-lifecycle exit
hypothesis. It is not claimed to be optimal. No EMA period sweep is allowed.

### 4.4 Exit Priority / Same-bar Conflicts

The execution task must predeclare exact same-bar ordering before running.
Minimum requirement:

- signal decisions use fully closed candles only;
- entry occurs after the signal, at the next eligible 4h open;
- intrabar EMA60 touches are ignored;
- if a risk stop and EMA60 close-break are both relevant in the same 4h bar,
  the report must use a pessimistic and fully documented ordering;
- no exit decision may use future candles.

If the harness cannot express these timing rules without modifying forbidden
runtime/profile/risk/backtester core paths, classify as `HARNESS_INFEASIBLE`.

---

## 5. Optional Overlay Boundary

NSC-012 identified E-A one-bar post-entry close-back-below-breakout-level
early exit as the only low-freedom optional overlay candidate.

For NSC-013 clean baseline:

- E-A is recorded only as an optional future overlay.
- E-A is not enabled in the clean baseline.
- Direction E overlay is not tested.
- Baseline vs E-A must not be compared after the fact to select the better
  result.
- If E-A is ever enabled, it requires a separate Owner-approved task card.

Future E-A rule, if separately approved, must remain post-entry early exit,
not pre-entry filtering, because the close-back candle is not known at entry
time.

---

## 6. 1h Boundary

This clean baseline uses no 1h data.

1h may later be used for Direction B / entry timing research, but not in this
plan.

Forbidden in NSC-013:

- 1h pullback entry;
- 1h reclaim entry;
- 1h local structure;
- 1h confirmation search;
- 1h as primary decision layer;
- CPM-style 1h pullback repair.

Adding 1h would confound the clean test of 4h main trend lifecycle capture.

---

## 7. Data Windows

Use the same ETH 4h windows unless the execution gate discovers a documented
data availability issue before running:

| Window | Role |
| --- | --- |
| 2021 full year | CPM-1 primary OOS failure reference / bull-year trend reference |
| 2022 full year | Bear / whipsaw reference |
| 2023 full year | CPM weak-follow-through reference; T1-A positive reference |
| 2024 full year | Positive reference; must not be explained only by one top winner |
| 2025 full year | Recent reference; T1-A negative year despite positive 2023/2024 |

No additional years, assets, directions, or timeframes may be added after
seeing results without a new Owner-approved plan.

---

## 8. Cost Model

Use CPM-1 official OOS report cost model as the SSOT, matching the NSC-008 /
NSC-009 research convention unless a later Owner-approved execution gate
freezes a more precise value before running.

The NSC-014 report must record exact values for:

- fee rate;
- entry slippage rate;
- stop / risk exit slippage rate;
- EMA60 close-break exit slippage rate;
- funding enabled / disabled state;
- funding rate approximation;
- whether fees/slippage apply to entry, risk stop exit, EMA exit, force close,
  and any end-of-window close.

No result may be interpreted positively if it depends on relaxing cost,
funding, fee, or slippage assumptions.

---

## 9. Required Execution And Anti-lookahead Proof

Any future execution report must prove:

- Donchian high/low windows use only prior closed 4h bars and exclude the
  signal bar;
- signal candle is fully closed before entry decision;
- entry happens at the next 4h bar open after signal close;
- EMA60 is computed only from closed 4h bars available at the trigger time;
- EMA60 exit is based on fully closed 4h close below EMA60, not intrabar touch;
- exit execution happens after the close-break trigger, using the documented
  next-bar convention;
- initial stop is active and does not use future bars;
- same-bar conflicts use a pessimistic documented ordering;
- cross-year indicators are computed over continuous data where required, not
  reset in a way that creates artificial yearly artifacts.

---

## 10. Required Report Outputs

Any NSC-014 execution report must include:

- harness / adapter feasibility;
- exact cost model;
- same-bar / next-bar convention;
- anti-lookahead proof;
- closed positions count;
- gross PnL before costs;
- net PnL after costs;
- PF;
- win rate;
- realized MaxDD;
- MTM MaxDD;
- MFE / MAE;
- maximum giveback;
- average / median / max hold duration;
- hold duration distribution;
- funding cost and funding intervals;
- year-by-year results;
- 2021/2022 behavior explanation;
- 2023/2024/2025 behavior explanation;
- top 1 / top 3 / top 5 winner concentration;
- net excluding top 1 / top 3 / top 5;
- trade count floor result;
- final classification.

Year-by-year results must include at minimum:

- closed positions count;
- gross PnL before costs;
- net PnL after costs;
- PF;
- win rate;
- average win / average loss;
- realized MaxDD;
- MTM MaxDD;
- MFE / MAE summary;
- max giveback;
- average / median hold duration;
- funding exposure;
- top-winner concentration.

---

## 11. Trade Count Floors

Direction A is 4h-based, so the floors are lower than CPM-style 1h modules
but must still support interpretable evidence.

Frozen NSC-013 floors:

| Metric | Minimum |
| --- | ---: |
| 2021+2022 closed positions | 15 |
| 2023+2024+2025 closed positions | 40 |
| 2021-2025 total closed positions | 55 |

If any floor is not met, classify as
`INSUFFICIENT_EVIDENCE_THIN_SAMPLE`, even if net PnL is positive.

These floors are not promotion criteria. They are minimum evidence
interpretability gates.

---

## 12. Fragility And Sparse Trend Gates

Owner accepts sparse trend profits, low win rate, and meaningful giveback.
This plan therefore must not reject a candidate simply because it is lumpy.

Accepted trend properties:

- low win rate can be acceptable;
- sparse profits can be acceptable;
- some profit giveback can be acceptable;
- large winners can contribute a high share of profits.

Not accepted:

- one anomalous year fully supports the conclusion;
- top winners fully support the conclusion;
- positive net comes only from cost relaxation;
- a filter or exit removes most large trend winners;
- a parameter sweep rescues a failed frozen rule.

Minimum fragility interpretation:

- If top 1 removal makes full-window net negative, classify no better than
  `PAUSE_FRAGILE`.
- If top 3 winners exceed 100% of total net and net excluding top 3 is
  negative, classify no better than `PAUSE_FRAGILE`.
- If the result is positive only because of one year, classify no better than
  `PAUSE_FRAGILE` or `INSUFFICIENT_EVIDENCE`, depending on sample shape.
- PASS requires positive net after costs, interpretable year-by-year behavior,
  trade floors met, and concentration not fully controlling the conclusion.

---

## 13. Classification Gates

Every future report must end with one of the following classifications.

| Classification | Meaning |
| --- | --- |
| `PASS_MIN_EVIDENCE` | Minimum evidence gate met; eligible for evidence review only |
| `PAUSE_FRAGILE` | Net/gross evidence exists, but concentration, top-winner removal, or one-year dependency is not acceptable |
| `INSUFFICIENT_EVIDENCE_THIN_SAMPLE` | Trade count floor not met |
| `REJECT` | Gross expectancy fails, net after cost is negative, or cross-year behavior is not explainable |
| `HARNESS_INFEASIBLE` | Frozen baseline cannot be executed without forbidden modifications |

PASS does not mean:

- promotion;
- small-live candidate;
- runtime implementation approval;
- official backtester integration approval;
- live deployment.

Suggested classification table:

```markdown
## Failure / Evidence Classification

| Field | Value |
| --- | --- |
| Candidate | Direction A clean baseline |
| Frozen rule hash / description | 4h Donchian20 breakout, next 4h open entry, previous-20 low initial stop, EMA60 close-break exit |
| Classification | PASS_MIN_EVIDENCE / PAUSE_FRAGILE / INSUFFICIENT_EVIDENCE_THIN_SAMPLE / REJECT / HARNESS_INFEASIBLE |
| Primary reason | ... |
| Captures main trend? | Yes / No / Mixed |
| Gross expectancy improved? | Yes / No |
| Net after costs positive? | Yes / No |
| MTM drawdown acceptable for evidence review? | Yes / No / Mixed |
| Top-winner concentration acceptable? | Yes / No / Mixed |
| Trade count floor met? | Yes / No |
| 2021/2022 behavior explainable? | Yes / No / Mixed |
| 2023/2024/2025 behavior explainable? | Yes / No / Mixed |
| Runtime/profile/risk change implied? | No |
| Promotion conclusion | None |
| Small-live conclusion | None |
| Live deployment conclusion | None |
```

---

## 14. NSC-014 Execution Gate Requirements

NSC-014 requires a separate Owner-approved task card.

If approved, NSC-014 may only be a minimal experiment execution gate:

1. Inspect whether current research/backtest harness can express the frozen
   clean baseline without modifying forbidden files.
2. If expressing the baseline requires runtime/profile/risk/production
   strategy/backtester core changes, stop and report `HARNESS_INFEASIBLE`.
3. If it can be executed by read-only use of existing harness or a standalone
   research-only adapter under `reports/**`, run the frozen baseline only.
4. Output research-only evidence and artifacts under a dedicated
   `reports/nsc-014-*` directory.

NSC-014 must not:

- implement runtime strategy;
- modify production code;
- modify config/profile/risk;
- modify backtester/research engine core;
- enable Direction E;
- run T1-B;
- run parameter sweeps;
- provide promotion or small-live conclusions.

---

## 15. Not-now List

The following are explicitly not authorized:

- continuing CPM-1 rescue;
- continuing CPM-2 A/B rescue;
- automatically starting Candidate C;
- T1-A parameter rescue;
- Donchian / ATR / EMA / lookback sweep;
- Donchian N sweep;
- EMA period sweep;
- initial stop lookback sweep;
- Direction E overlay;
- E-A optional overlay execution;
- T1-B / 1h entry timing;
- 1h pullback / reclaim / local structure;
- T1 + CPM-1 portfolio combination;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- full data feature store;
- complex ML;
- tick / orderbook simulator;
- cost/funding/slippage relaxation;
- runtime/profile/risk changes;
- backtester/research engine core changes;
- promotion conclusion;
- small-live conclusion;
- live deployment advice.

---

## 16. Final Boundary

This file is not experiment authorization.

It only defines the proposed clean baseline plan for Direction A:

- 4h Donchian20 breakout entry;
- next 4h open entry convention;
- previous-20 closed 4h low initial stop;
- fully closed 4h candle close below EMA60 exit trigger;
- next 4h open exit convention;
- no 1h;
- no Direction E overlay;
- no parameter sweep.

Any future result can only enter evidence review. It cannot by itself become
promotion evidence, small-live candidate evidence, runtime implementation
approval, or live deployment advice.

Current project still has no deployable small-live strategy candidate.
Small-live readiness gate remains unmet.

---

## 17. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial Direction A clean baseline minimal experiment plan | Codex |
