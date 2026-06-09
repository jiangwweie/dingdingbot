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

# Crypto Pullback Module v1 Stabilization Plan

**Date:** 2026-05-06
**Status:** Superseded for promotion movement / Planning artifact
**Scope:** Baseline Strategy Module Stabilization

This document is a governance plan. It is not an implementation task, not an
experiment request, not a parameter optimization plan, and not runtime
promotion approval.

---

## 1. Status

CPM-1 stabilization was drafted in planning status. After the 2021 and 2022 OOS
runs and CPM-OOS-FAILURE-CLASSIFY-001, the current baseline is frozen and
paused. CPM-1 is not a Small-live Candidate, and the promotion path is stopped
unless Owner explicitly opens a new bounded research or reclassification task.

This plan exists to prevent the next phase from being misread as:

- Strategy parameter tuning.
- Large-scale parameter search.
- New strategy creation.
- Multi-asset or multi-strategy expansion.
- Regime-system implementation.
- Runtime profile promotion.
- Live-safe expansion.

The current status is: **paused after OOS gate failure**.

Accepted caveats:

- Current in-sample evidence remains mainly 2023-2025, but OOS evidence now
  includes negative 2021 and 2022 runs.
- 2021 OOS is classified as favorable-regime signal-level failure.
- 2022 OOS is negative in a bear year and does not provide profit-hypothesis
  support.
- Historical documents use mixed naming such as "Pinbar baseline".
- Historical reports use mixed cost, funding, and MaxDD semantics.
- Code and profile identifiers may still use `pinbar` as a trigger or legacy
  identifier.

---

## 2. Source of Truth

Current source-of-truth documents:

| Document | Role |
| --- | --- |
| `docs/ops/crypto-pullback-module-v1-scope-note.md` | CPM-1 module identity SSOT. Defines what CPM-1 is and is not. |
| `docs/ops/crypto-pullback-module-v1-evidence-interpretation-note.md` | CPM-1 evidence interpretation SSOT. Defines how historical research evidence should be read. |
| `docs/ops/project-roadmap-v2.md` | Current active-track and scope boundary authority. |

This plan does not replace those documents. It only defines the stabilization
route under their constraints.

---

## 3. Module Definition

Current CPM-1 identity:

| Dimension | Current Definition |
| --- | --- |
| Asset | `ETH/USDT:USDT` |
| Timeframe | `1h` |
| Higher timeframe confirmation | `4h` |
| Direction | `LONG-only` |
| Module type | Trend-pullback-continuation |
| Trigger | Pinbar / lower-wick rejection |
| Trend filter | EMA50 + `min_distance_pct=0.005` |
| MTF filter | 4h EMA60 |
| Exit | TP1 1.0R 50%, TP2 3.5R 50%, BE off, trailing off |
| Portfolio role | Single crypto pullback module, not the system-wide strategy |

Naming rule:

- `Crypto Pullback Module v1` / `CPM-1` is the module identity.
- `Pinbar` is the entry trigger and legacy code/research identifier.
- Code and profiles may still use `pinbar`; that does not redefine the module.

---

## 4. Stabilization Goal

CPM-1 stabilization is not a return-improvement track.

The goals are:

1. Clarify what CPM-1 earns from.
2. Clarify what CPM-1 loses to.
3. Define applicable market boundaries.
4. Define invalid market boundaries.
5. Establish evidence quality requirements.
6. Prevent research outputs from automatically changing runtime.
7. Decide whether CPM-1 deserves further OOS validation or longer observation.

Stabilization should produce clearer boundaries, not hidden strategy mutation.

---

## 5. Earnings Hypothesis

CPM-1 earns from:

- An existing uptrend.
- A short-term pullback within that uptrend.
- Lower-wick rejection that suggests the pullback may be ending.
- 4h trend confirmation remaining valid.
- Continuation after the pullback.

CPM-1 is not:

- A trend-start strategy.
- A pure reversal strategy.
- A breakout strategy.
- A formal liquidity-sweep strategy.
- A volatility-breakout strategy.

The lower wick can be interpreted as price rejection. Current evidence does
not support a stronger liquidity-sweep definition because CPM-1 does not use
order book, open interest, funding, liquidation, or other liquidity-sweep
evidence.

---

## 6. Failure Hypothesis

Main failure sources:

- Pullback turns into reversal.
- Fake rebound / no follow-through.
- High volatility noise.
- Overheating / near Donchian high / high 72h return.
- Weak continuation / chop.
- Over-trend / parabolic state.

2023-style failure likely indicates regime mismatch / applicable-boundary
cost. It must not be treated by default as a parameter problem.

---

## 7. Evidence Interpretation Rules

Evidence must be interpreted under the evidence SSOT.

Rules:

1. Official evidence takes precedence over proxy evidence.
2. Full-window evidence takes precedence over single-year evidence.
3. Single-year evidence can identify a boundary, but must not define the
   strategy alone.
4. Same-bar policy must be stated.
5. BNB9 or mixed historical cost model must be stated.
6. Funding usage must be stated when relevant.
7. MaxDD must be interpreted with correct report semantics.
8. Rescue experiments are boundary evidence, not automatic runtime candidates.
9. Research output must never directly mutate runtime config.

If evidence conflicts, the conflict should be documented rather than resolved
by tuning runtime parameters.

---

## 8. Stabilization Questions

The following are owner decision points. They are not approved tasks.

1. Does owner accept 2023-style failure as CPM-1 boundary cost?
2. Should 2022 OOS become a stabilization gate?
3. Should current CPM-1 parameter profile be frozen for a review period?
4. Should E4 / Donchian-distance style factors remain research labels only,
   not runtime hard filters?
5. What are CPM-1 promotion / rejection criteria?
6. Should CPM-1 stabilization be scheduled independently from Live-safe
   observation?
7. Should an evidence matrix be produced as a documentation artifact?
8. Should Claude Code only assist with evidence extraction under a Codex
   template?

---

## 9. Candidate Stabilization Tracks

### A. Evidence Matrix

Purpose:

- Keep research evidence traceable and readable.
- Index official/proxy status, cost model, data window, same-bar policy,
  funding assumptions, MaxDD caveats, and runtime impact.

It must not:

- Promote research findings to runtime.
- Define new strategy rules.
- Treat proxy findings as official validation.

Suitable ownership:

- Claude Code may extract evidence under a Codex template.
- Codex reviews and owns interpretation.

### B. 2022 OOS Gate Inspect Plan

Purpose:

- Decide whether 2022 OOS should become a stabilization gate.
- Define how an OOS run would be interpreted if owner approves it later.

Why it mattered at draft time:

- Evidence was mainly 2023-2025 in-sample.
- 2022 was the strongest known OOS candidate before the later 2022 and 2021
  OOS runs. This section is historical and is superseded by the current Pause
  status above.

It must not:

- Become a tuning loop.
- Trigger parameter search.
- Modify runtime or research engine.

Requires owner approval before running anything.

### C. Promotion / Rejection Criteria Draft

Purpose:

- Define what evidence completeness means before CPM-1 can be promoted,
  paused, rejected, or kept under observation.

Potential criteria dimensions:

- Evidence completeness.
- OOS requirement.
- Drawdown interpretation.
- Market-boundary clarity.
- Runtime observation separation.
- Research/runtime isolation.

Requires owner decision. This plan does not approve any criteria.

---

## 10. Not-Now List

The following are out of scope for CPM-1 stabilization planning:

- No parameter change.
- No E4 hard filter.
- No SHORT runtime.
- No ETH 15m / 4h expansion.
- No BTC/SOL migration.
- No multi-strategy.
- No multi-asset.
- No Portfolio.
- No Regime system.
- No complex ML.
- No full simulator.
- No tick/orderbook replay.
- No large parameter search.
- No tuning to rescue 2023.
- No automatic research-to-runtime promotion.
- No live-safe change.
- No runtime profile change.
- No backtester change.
- No frontend change.
- No research engine change.
- No new strategy creation.

---

## 11. Governance Rules

1. Every candidate must start with inspect + plan.
2. Experiments require owner approval.
3. Runtime profile changes require a separate owner decision.
4. Research labels are not runtime filters.
5. Documentation evidence is not promotion approval.
6. This stabilization plan does not authorize implementation.
7. Claude Code may work only from bounded task cards with allowed and
   forbidden files.
8. Codex owns architecture and strategy-module governance decisions.

---

## 12. Proposed Next Step

Owner may choose one of the following next steps:

1. Commit the CPM-1 SSOT and stabilization plan documents.
2. Create an evidence matrix extraction task for Claude Code.
3. Create a 2022 OOS gate inspect plan.
4. Create a promotion / rejection criteria draft.
5. Pause after documentation consolidation.

No next step is approved by this document.

---

## 13. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial stabilization plan created | Codex |
