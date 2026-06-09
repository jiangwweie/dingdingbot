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

# Direction A BTC+ETH Phase 1 Observation Design Consolidation

**Status:** Docs-only Owner review summary  
**Date:** 2026-05-09  
**Scope:** 4h Direction A BTC+ETH Phase 1 observation design only  
**Runtime impact:** None  

---

## 1. Executive Summary

Direction A remains classified as:

`CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`

The current BTC+ETH Phase 1 evidence supports continued docs-only observation design, but not execution. The main case is not high historical return. The case is that conservative risk shaping produces a low drawdown observation envelope while preserving positive sparse trend evidence across BTC and ETH under the same frozen 4h Direction A rule.

Current consolidated evidence:

- BTC+ETH unshaped aggregate is positive: +5,518.83 net, PF 1.50, 332 trades, 74 winners.
- BTC and ETH both individually contribute; ETH contributes 54.4% of BTC+ETH net and BTC contributes 45.6%.
- P0 remains inconclusive: winner episodes are partially shared, PF confidence is inconclusive, and effective top-5 observations are far below raw trade count.
- P1 shows mixed edge source: Donchian20 entry has partial alpha, while the broader mechanism is smart-beta trend timing and EMA60 lifecycle exposure management.
- P2 and the risk frontier show conservative risk shaping improves tolerability but does not remove shared-episode and top-winner dependence.
- Same-risk comparison supports continued docs-only design: at matched MaxDD, Direction A A1/A3 compares favorably to buy-and-hold and 1D spot benchmarks, while using materially lower drawdown.

Observation sleeve projection remains conservative:

- A1 on 1500U sleeve: historical net +216.22U, MaxDD 39.00U.
- A1 on 3000U sleeve: historical net +432.45U, MaxDD 78.01U.
- A3 on 1500U sleeve: historical net +432.45U, MaxDD 76.27U.
- A3 on 3000U sleeve: historical net +864.89U, MaxDD 152.54U.

Remaining risks are material:

- BTC+ETH top-3 and top-5 removal are negative in the unshaped aggregate.
- 2023 and 2024 carry more than 100% of total BTC+ETH net; 2022 and 2025 are negative.
- P0 winner overlap implies the evidence count is closer to a few shared crypto-wide episodes than to independent trade count.
- Conservative return is modest; the observation value is mainly operational learning, discipline, and shadow/no-order process validation.

This summary does not authorize runtime, small-live, paper execution, live execution, or capital allocation.

---

## 2. Sources Inspected

| Source | Status | Use |
|---|---|---|
| `docs/ops/direction-a-observation-value-memo.md` | Present | Observation rationale, sleeve projections, missing diagnostic history |
| `docs/ops/direction-a-phase1-btc-eth-aggregate-diagnostic.md` | Present | BTC+ETH aggregate, A1/A3 Phase 1 interpretation, year/top-N tables |
| `docs/ops/direction-a-same-risk-capital-efficiency-comparison.md` | Present | Matched MaxDD comparison vs buy-and-hold and 1D spot |
| `docs/ops/direction-a-small-live-design-plan.md` | Present | Historical sizing and exposure references only; superseded by current no-order constraint for active planning |
| `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md` | Present | ETH/BTC/SOL frozen evidence context |
| `docs/ops/direction-a-risk-control-return-frontier.md` | Present | A1/A3 risk frontier summary |
| `reports/direction-a-risk-control-return-frontier/risk_control_return_frontier.json` | Present | A1/A3 top-N, drawdown, 2023, worst-month details |
| `reports/direction-a-risk-control-return-frontier/small_capital_projection.json` | Present | 1500U / 3000U projections |
| `reports/direction-a-p0-evidence-strength-diagnostics/p0_summary.json` | Present | P0 classifications and effective observation count |
| `reports/direction-a-p1-edge-source-attribution/p1_summary.json` | Present | P1 classifications |
| `reports/direction-a-p2-risk-shape-diagnostic/p2_summary.json` | Present | P2 classification |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Present | Deployment and sparse trend evidence boundaries |
| `docs/ops/sma-001-strategy-module-applicability-map.md` | Present | Current non-runtime classification |

No new backtest was run. No runtime, strategy, risk profile, paper, testnet, live, portfolio, or router file was modified.

---

## 3. BTC+ETH Phase 1 Baseline And Risk-Shaped Scenarios

### Baseline Aggregate

| Metric | BTC+ETH Phase 1 baseline | Notes |
|---|---:|---|
| Trades | 332 | ETH 173 + BTC 159 |
| Winners | 74 | ETH 34 + BTC 40 |
| Losers | 258 | ETH 139 + BTC 119 |
| Win rate | 22.29% | Sparse trend profile |
| Net PnL | +5,518.83 | ETH +3,001.66; BTC +2,517.17 |
| PF | 1.50 | Recomputed from documented ETH/BTC gross win/loss |
| Realized MaxDD | Not exactly computable from standalone asset docs | Needs portfolio-level equity curve timing |
| Time in market | ~38.5% | From Phase 1 aggregate diagnostic |

Interpretation: BTC+ETH does not depend on SOL to remain positive. It is still a sparse trend / smart-beta timing mechanism, not a pure breakout-alpha strategy.

### Conservative Risk-Shaped Scenarios

| Scenario | Net on 30k | Return | MaxDD | PF | Top-5 after removal | 2023 contribution | Max concurrent | Class |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1 low vol-normalized + max 2 | +4,324.46 | 14.4% | 2.60% | 1.752 | +297.71 | +2,677.88 | 2 | Conservative observation candidate |
| A3 hybrid 0.50% vol-adjusted + max 2 | +8,648.92 | 28.8% | 5.08% | 1.752 | +595.42 | +5,355.77 | 2 | Conservative observation candidate |

A1 is the default conservative observation shape. A3 is a higher-risk Owner-review band. Both remain docs-only design references.

### Source Reconciliation Note

There is a source mismatch that should be resolved before any shadow/no-order rehearsal spec is finalized:

| Field | Phase 1 doc | Risk frontier JSON | Interpretation |
|---|---:|---:|---|
| A1/A3 trade count | 490 | 373 | Likely different scenario accounting or accepted-trade counting; not reconciled here |
| A1/A3 time in market | ~38% | 52.26% | Likely different portfolio exposure definition; not reconciled here |

This consolidation does not infer a corrected value. It records both as an artifact reconciliation gap.

---

## 4. Top-Winner Analysis

### Unshaped BTC+ETH Aggregate

| Metric | BTC | ETH | BTC+ETH combined |
|---|---:|---:|---:|
| Top-1 winner PnL | +1,303.82 | +1,373.64 | +2,677.46 |
| Top-3 winner PnL | +3,205.09 | +3,445.58 | +6,650.67 |
| Top-5 winner PnL | +4,182.60 | +4,494.99 | +8,677.59 |
| Top-1 as % of net | 51.8% | 45.8% | 48.5% |
| Top-3 as % of net | 127.3% | 114.8% | 120.5% |
| Top-5 as % of net | 166.2% | 149.8% | 157.2% |

### Top-N Removal

| Removal test | BTC+ETH result | Interpretation |
|---|---:|---|
| Net after top-1 removal | +2,841.37 | Still positive |
| Net after top-3 removal | -1,131.84 | Fails sparse trend fragility check for deployment/small-live readiness |
| Net after top-5 removal | -3,158.76 | Fails; payoff remains concentrated |

### Risk-Shaped A1/A3 Top-N Fragility

| Scenario | Top-1 contribution | Top-3 contribution | Top-5 contribution | Net after top-1 | Net after top-3 | Net after top-5 |
|---|---:|---:|---:|---:|---:|---:|
| A1 | +929.82 | +2,744.25 | +4,026.75 | +3,394.65 | +1,580.21 | +297.71 |
| A3 | +1,859.63 | +5,488.50 | +8,053.51 | +6,789.29 | +3,160.42 | +595.42 |

Risk shaping improves the top-5 residual for A1/A3, but it does not eliminate the core sparse-trend issue: the historical return is still heavily driven by a small set of shared crypto-wide trend episodes.

P0 classification remains binding:

- Winner overlap: `WINNER_EVIDENCE_PARTIALLY_SHARED`.
- P0 evidence strength: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`.
- Raw top-5 winners across ETH/BTC/SOL: 15.
- Loose unique top-5 episodes: 6.
- Asset-adjusted loose effective observations: 3.5.

For BTC+ETH Phase 1, the effective independent observation count is lower than raw BTC+ETH top-winner count and should be treated conservatively.

---

## 5. Yearly Contribution And Fragility

### BTC+ETH Baseline Year Contribution

| Year | BTC net | ETH net | Combined net | Combined % of total | Fragility read |
|---|---:|---:|---:|---:|---|
| 2021 | +293.35 | +722.57 | +1,015.92 | 18.4% | Both positive; ETH carries |
| 2022 | -821.76 | -76.80 | -898.56 | -16.3% | Vulnerability year; bear/chop damage |
| 2023 | +2,407.94 | +918.93 | +3,326.87 | 60.3% | Primary positive year; shared regime dependence |
| 2024 | +919.06 | +1,465.75 | +2,384.81 | 43.2% | Strong positive year; ETH carries |
| 2025 | -281.43 | -28.79 | -310.22 | -5.6% | Vulnerability year; cost/chop drag |

2022 and 2025 expose the main Phase 1 vulnerability: the mechanism can keep taking sparse breakout/lifecycle exposure without enough payoff tail. This weakness appears in both BTC and ETH, so it is not an asset-specific anomaly.

### Risk-Shaped Scenario Year Stress

| Scenario | 2023 contribution | Result excluding 2023 | Worst year | Worst month | Consecutive losers |
|---|---:|---:|---|---|---:|
| A1 | +2,677.88 | +1,646.58 | 2022: -511.45 | 2025-12: -287.37 | 20 |
| A3 | +5,355.77 | +3,293.16 | 2022: -1,022.89 | 2025-12: -574.75 | 20 |

A1/A3 remain positive excluding 2023, but 2022 and late-2025 still matter for Owner tolerance. A shadow/no-order rehearsal should therefore track losing streaks, missed exits, and data/execution mismatches rather than judging success by PnL.

---

## 6. Observation Sleeve Projection

Source: `reports/direction-a-risk-control-return-frontier/small_capital_projection.json`.

| Sleeve | Scenario | Historical net | MaxDD | Worst month | Largest single loss | Tolerable in source |
|---:|---|---:|---:|---:|---:|---|
| 1500U | A1 | +216.22U | 39.00U | -14.37U | -3.91U | Yes |
| 1500U | A3 | +432.45U | 76.27U | -28.74U | -7.81U | Yes |
| 3000U | A1 | +432.45U | 78.01U | -28.74U | -7.81U | Yes |
| 3000U | A3 | +864.89U | 152.54U | -57.47U | -15.63U | Yes |

Design interpretation:

- 1500U A1 is the cleanest observation sleeve reference: small historical net, very small historical MaxDD, and high emphasis on operational learning.
- 3000U A1 or 1500U A3 are similar historical net bands but differ in sleeve size and risk-per-trade posture.
- A3 should not be treated as default execution sizing. It is an Owner-review band after a successful shadow/no-order rehearsal design and separate approval.
- The historical projections are not expected returns and do not authorize capital allocation.

Historical sizing and exposure references retained for shadow/no-order tracking:

- Phase 1 symbols: BTC/USDT:USDT and ETH/USDT:USDT only.
- Default virtual risk reference: 0.25% of sleeve.
- Upper virtual review band: 0.50% of sleeve, Owner review required before even using it as a shadow metric.
- Max concurrent virtual positions to track: 2.
- Max virtual total open initial risk to track: 1.0% of sleeve default; 1.5% hard design cap as an alert threshold.
- No leverage assumption in virtual exposure logs.
- Shadow/no-order observation design first; no paper, testnet, live, or direct
  execution.

These are observation metrics only. They must not be wired into runtime sizing,
orders, exchange connectivity, paper trading, or execution code.

---

## 7. Shadow/No-Order Observation Scope

Shadow/no-order observation means the project may record what would have been
observed under BTC+ETH Phase 1 rules, but must not submit, simulate, route, or
execute orders.

Required observation dimensions:

| Dimension | What to track | Why it matters |
|---|---|---|
| Signal state | Candidate signal, invalidated signal, skipped signal, no signal | Measures process discipline without execution |
| Rule-match audit | Which frozen Direction A conditions matched or failed | Prevents discretionary reinterpretation |
| Virtual exposure | Virtual open/flat state, virtual initial risk, virtual aggregate risk | Reveals exposure clustering without capital allocation |
| Fragility | Top-winner dependence, shared episode dependence, consecutive loser count | Keeps SRR-002 sparse-trend caveats visible |
| Year-specific vulnerability | 2022-style bear/chop damage, 2025-style cost/chop drag, 2023/2024 dependence | Prevents over-reading favorable years |
| Data/process anomaly | Missing/stale bars, duplicate bars, delayed data, manual pauses | Separates observation failures from strategy evidence |
| Review stop conditions | Minimum observation window, anomaly threshold, unresolved reconciliation gap | Keeps the observation bounded |

Prohibited under this scope:

- paper/testnet/live execution;
- exchange/API activation;
- portfolio/router logic;
- SOL Phase 2;
- CPM, short-side, or other strategy inclusion;
- Direction A parameter or risk-profile changes;
- strategy code changes or runtime module changes.

---

## 8. Knowledge Gaps And Missing / Conflicting Artifacts

| Gap | Status | Owner relevance |
|---|---|---|
| A1/A3 trade count mismatch | Phase 1 doc says 490; frontier JSON says 373 | Must reconcile before rehearsal metric definitions |
| A1/A3 time-in-market mismatch | Phase 1 doc says ~38%; frontier JSON says 52.26% | Must define whether TIM means asset-level, portfolio active, or aggregate exposure |
| BTC+ETH portfolio MaxDD baseline | Not exactly computable from standalone docs | Needed only if Owner wants unshaped baseline portfolio curve |
| MTM drawdown for A1/A3 | Not available from risk frontier trade-level simulation | Shadow rehearsal should specify whether MTM is required |
| Extreme regime evidence | 2021-2025 only; no validated pre-observable applicability boundary | SRR-002 remains unmet |
| OOS robustness | P0/P1/P2 are historical diagnostics, not live/OOS proof | No promotion or runtime implication |
| Top-winner dependence | A1/A3 pass top-5 residual, but P0 shared-episode caveat remains | Owner must decide if observation value offsets fragility |
| Shadow/no-order operational checklist | Design plan exists, but no specific shadow rehearsal task card/spec exists | Next docs-only step if Owner approves |
| Exact no-order observation reconciliation requirements | Not specified at implementation detail level | Needed before any shadow/no-order observation planning |

Missing artifact interpretation: no missing source blocks this consolidation, but several fields require reconciliation before a precise shadow/no-order rehearsal design can be written.

---

## 9. Owner Decision Frame

The decision is not whether Direction A is live-ready. It is not.

The decision is whether the evidence stack justifies a future docs-only shadow/no-order rehearsal design plan for BTC+ETH Phase 1.

Arguments for continuing to shadow rehearsal design planning:

- BTC+ETH Phase 1 aggregate is positive without high-beta discretionary expansion.
- A1/A3 conservative risk shapes are positive and drawdown-contained.
- Same-risk comparison says Direction A has better matched-MaxDD capital efficiency than buy-and-hold and 1D spot references.
- Observation sleeve loss projections are small relative to the Owner's capital context.
- Shadow/no-order rehearsal would test operational discipline without orders or capital allocation.

Arguments for pausing:

- P0 evidence strength remains inconclusive.
- Unshaped BTC+ETH top-3/top-5 removal fails.
- 2023/2024 concentration and 2022/2025 weakness are material.
- Conservative expected learning value may be high, but conservative historical return is modest.
- Source mismatch on trade count/time-in-market should be resolved before rehearsal metrics are finalized.

Recommended next Owner decision:

**Authorize or decline a docs-only BTC+ETH Phase 1 shadow/no-order rehearsal design plan.**

If authorized, that future plan should define only:

- BTC+ETH signal shadowing schedule;
- no-order event logging;
- rule-match audit;
- skipped-signal and hypothetical-fill logging;
- drawdown and exposure monitoring definitions;
- artifact reconciliation requirements for A1/A3 trade count and time-in-market;
- stop conditions for ending the rehearsal;
- review criteria after 3-6 months or after a minimum signal count.

It must not include runtime activation, paper orders, exchange connectivity, live orders, capital allocation, strategy changes, SOL, CPM, other strategies, shorts, router logic, or portfolio implementation.

---

## 10. Explicit Non-Authorization

This consolidation does not authorize:

- runtime activation;
- paper trading;
- testnet trading;
- live trading;
- small-live execution;
- exchange/API activation;
- capital allocation;
- Direction A parameter changes;
- Direction A variants;
- strategy code changes;
- risk profile changes;
- portfolio/router/multi-strategy implementation;
- CPM or any other strategy combination;
- short-side research;
- high-beta discretionary watchlists;
- TE execution;
- CPM reopening;
- strategy rescue.

Direction A BTC+ETH Phase 1 observation design consolidation is docs-only. No runtime, small-live, paper/testnet/live execution, exchange/API activation, capital allocation, strategy changes, risk profile changes, portfolio/router implementation, CPM combination, SOL expansion, short-side work, TE execution, CPM reopening, or strategy rescue is authorized. Any shadow/no-order rehearsal design requires separate Owner approval and must satisfy SRR-002 and live-safe operational gates.
