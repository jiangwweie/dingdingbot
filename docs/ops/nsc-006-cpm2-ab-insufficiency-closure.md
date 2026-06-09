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

# NSC-006 — CPM-2 A/B Insufficiency Closure & Next Direction Re-open

**Date:** 2026-05-06
**Status:** Closed / Research Proxy Insufficiency Closure
**Scope:** Docs-only closure
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document closes the current CPM-2 Candidate A/B path after NSC-005 research-only proxy evidence.

This document does not authorize:

- running experiments;
- writing strategy or adapter code;
- changing runtime profiles;
- changing risk rules;
- changing configs, migrations, tests, or production strategy implementation;
- modifying the backtester / research engine core;
- starting Candidate C;
- making any promotion, small-live, or live deployment decision.

NSC-006 is closure only. Any next candidate direction requires a separate Owner-approved inspect or planning task.

---

## 1. Decision Chain

### NSC-001 — Candidate Direction Inspect

NSC-001 inspected historical docs and selected CPM-2 as the next candidate direction:

- ETH 1h pullback-continuation;
- same broad CPM pullback structure;
- different entry confirmation mechanism;
- not a CPM-1 Pinbar parameter rescue.

NSC-001 recommended the first candidate order:

1. Candidate A — One-Bar Continuation Reclaim.
2. Candidate B — Donchian-Location Pullback Confirmation.
3. Candidate C — Two-Candle Pullback-End Pattern, reserve only.

### NSC-002 — Minimal Experiment Plan

NSC-002 froze the first-round experiment rules for Candidate A and Candidate B.

Key constraints:

- Candidate A must not become a reclaim-rule combination search.
- Candidate B must use exact `-0.016809` provenance and must not revive old inverse E4 hard-filter semantics.
- Candidate C remains reserve-only.
- Any improvement must come from expectancy or loss-cluster improvement, not simple trade deletion.
- The minimum evidence gate includes trade-count floors across 2021/2022 and 2023/2024/2025.

### NSC-003 — Execution Gate

NSC-003 stopped before experiment execution with `HARNESS_INFEASIBLE`.

Findings:

- Candidate A could not be expressed by the current immediate-bar trigger harness because it requires delayed one-bar confirmation and delayed fill convention.
- Candidate B threshold provenance was confirmed, but the existing `donchian_distance` filter direction was inverse to NSC-002 and would have revived old E4 semantics.

No Candidate A/B experiment was run in NSC-003.

### NSC-004 — Research-only Adapter Design Plan

NSC-004 designed a minimum research-only adapter path:

- standalone research script / report generator preferred;
- no runtime strategy registration;
- no runtime profile or risk-rule changes;
- no backtester / research engine core changes;
- proxy matching allowed only if clearly labeled as research-only evidence.

### NSC-005 — Standalone Proxy Execution

NSC-005 implemented and ran a standalone research-only proxy adapter under:

- `reports/nsc-005-cpm2-frozen-candidate-ab-experiment/`

Primary report:

- `reports/nsc-005-cpm2-frozen-candidate-ab-experiment/experiment_report.md`

NSC-005 feasibility and result:

| Field | Result |
| --- | --- |
| Adapter feasibility | `FEASIBLE_STANDALONE_PROXY` |
| Evidence type | Research-only proxy evidence |
| Official backtester/runtime evidence? | No |
| Promotion evidence? | No |
| Candidate A classification | `INSUFFICIENT_EVIDENCE` |
| Candidate B classification | `INSUFFICIENT_EVIDENCE` |

NSC-005 key metrics:

| Candidate | Closed Positions | Net PnL | PF | MaxDD | Classification Reason |
| --- | ---: | ---: | ---: | ---: | --- |
| Candidate A — One-Bar Continuation Reclaim | 56 | -973.0352 | 0.74997 | 0.16424 | Minimum trade count floor not met |
| Candidate B — Donchian-Location Pullback Confirmation | 135 | -5682.2921 | 0.50660 | 0.56925 | Minimum trade count floor not met |

Both candidates failed to meet the NSC-002 minimum evidence gate. The results are useful as closure evidence for the A/B path, but they must not be rewritten as official backtester evidence.

---

## 2. CPM-2 Candidate A/B Closure

Current CPM-2 Candidate A/B conclusion:

- do not enter promotion;
- do not become small-live candidates;
- do not enter runtime implementation;
- do not enter official backtester integration;
- do not continue as the current mainline.

This is not a claim that every pullback-continuation idea is invalid. It is a closure of the frozen Candidate A/B path defined by NSC-002 and executed as research-only proxy in NSC-005.

### Candidate A Closure

Candidate A attempted to replace CPM-1 immediate lower-wick entry with one-bar continuation reclaim:

```text
setup marker -> wait one fully closed 1h candle -> accept only if close > setup high -> enter next bar
```

NSC-005 showed:

- 56 closed positions;
- 2021/2022 sample was far below the NSC-002 floor;
- 2024+2025 retention versus proxy baseline was below the continued evidence review protection line;
- classification: `INSUFFICIENT_EVIDENCE`.

Candidate A is therefore closed as the current mainline. It must not be rescued by wait-length optimization, reclaim-rule variants, or combining multiple reclaim definitions.

### Candidate B Closure

Candidate B attempted to validate pullback-ending quality through previous-20-bar Donchian location:

```text
accept if distance_to_donchian_high >= -0.016809
reject if distance_to_donchian_high < -0.016809
```

NSC-005 showed:

- 135 closed positions;
- 2021/2022 sample was below the NSC-002 floor;
- net PnL remained materially negative;
- classification: `INSUFFICIENT_EVIDENCE`.

Candidate B is therefore closed as the current mainline. It must not be rescued by threshold sweep, rounding, replacement, inverse semantics, or E4 hard-filter revival.

---

## 3. Explicit Rescue Prohibitions

The following are not allowed as follow-up rescue work for CPM-2 Candidate A/B:

- Candidate A reclaim-rule sweep;
- Candidate A waiting-length optimization;
- Candidate A EMA, pivot, or range reclaim variant search;
- Candidate B threshold sweep;
- Candidate B threshold rounding;
- Candidate B threshold replacement;
- Candidate B temporary tuning;
- Candidate B inverse-semantics revival through old `donchian_distance` hard filter behavior;
- Candidate A + Candidate B combination;
- using Candidate C as an automatic fallback;
- parameter search to rescue CPM-2 A/B;
- adding filters after seeing NSC-005 results;
- changing exits, risk sizing, direction, asset, timeframe, runtime profile, or cost model to make A/B look viable;
- rewriting NSC-005 proxy evidence as official backtester/runtime evidence;
- treating trade-count compression as strategy validation.

Any attempt to revisit A or B must be a new Owner-approved research question with a new hypothesis. It must not be described as continuation of the NSC-002 frozen A/B path.

---

## 4. Candidate C Status

Candidate C remains reserve-only.

Candidate C does not automatically start because Candidate A and Candidate B were insufficient. Starting Candidate C would require a separate Owner-approved task that re-states:

- why Candidate C still belongs to pullback-continuation;
- how it avoids repeating standalone Engulfing / noisy two-candle pattern failures;
- what frozen rule would be used before results are inspected;
- what minimum evidence gate applies;
- why it is preferable to reopening the broader next-direction inspect.

Until then:

- no Candidate C experiment;
- no Candidate C adapter;
- no Candidate C runtime implementation;
- no Candidate C promotion path.

---

## 5. Current Project State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused |
| CPM-1 frozen baseline tuning rescue | Not allowed |
| CPM-2 Candidate A | `INSUFFICIENT_EVIDENCE`; closed as current mainline |
| CPM-2 Candidate B | `INSUFFICIENT_EVIDENCE`; closed as current mainline |
| Candidate C | Reserve only; not started |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |
| Runtime/profile/risk impact | None |
| Promotion conclusion | None |

The Live-safe foundation remains valuable infrastructure, but it still does not imply any strategy candidate is ready for small-live deployment.

---

## 6. Next Direction Re-open

The next step should return to Next Strategy Candidate Direction, not continue CPM-2 A/B rescue.

Recommended next direction:

1. Re-open candidate-direction inspect as NSC-007.
2. Prioritize T1-lite standalone trend-continuation inspect as the first candidate family to examine.
3. Keep scope narrow and inspect-only before any implementation or experiment authorization.

NSC-007 should inspect whether a T1-lite standalone trend-continuation candidate can be framed as a simple, deployability-conscious strategy direction without drifting into broader systems work.

Allowed conceptual boundary for NSC-007:

- standalone trend-continuation candidate direction;
- ETH-first unless Owner approves otherwise;
- simple OHLCV-derived trigger family;
- clear separation from CPM-1/CPM-2 rescue;
- no runtime/profile/risk change;
- no implementation or backtest during inspect.

Not-now for the next direction:

- portfolio;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- feature store;
- complex ML;
- tick/orderbook simulator;
- runtime strategy implementation;
- risk-rule changes;
- promotion or small-live readiness conclusion.

---

## 7. Closure Decision

NSC-006 closes CPM-2 Candidate A/B as insufficient under the NSC-002 minimum evidence gate.

This closure means:

- CPM-2 A/B are not promoted;
- CPM-2 A/B are not small-live candidates;
- CPM-2 A/B should not enter runtime implementation;
- CPM-2 A/B should not be integrated into the official backtester as current mainline;
- CPM-2 A/B should not receive rescue sweeps or parameter-tuning follow-ups.

This closure does not mean:

- a new strategy candidate has been selected;
- Candidate C is authorized;
- T1-lite is approved for experiment;
- small-live readiness is satisfied.

Recommended next task:

- **NSC-007 — Next Strategy Candidate Direction Inspect**, with T1-lite standalone trend-continuation as the first inspect priority.
