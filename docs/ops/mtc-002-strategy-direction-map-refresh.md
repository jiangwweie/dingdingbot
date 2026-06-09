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

# Strategy Direction Map Refresh v2

**Task ID:** MTC-002
**Date:** 2026-05-07
**Status:** Proposed / Direction Map Refresh
**Scope:** Baseline Strategy Module Stabilization — direction map refresh
**Supersedes:** `strategy-candidate-direction-map-v1.md` (SCDM-001, 2026-05-06)

This document is a research roadmap refresh. It is not experiment
authorization, runtime promotion approval, parameter tuning approval, live
enablement approval, backtest execution request, or a defense of any
specific direction.

**No code, no backtest, no adapter, no runtime change, no profile change, no
risk-rule change, no promotion conclusion, and no small-live conclusion
follows from this document.**

---

## 0. Boundary

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

Inspected material:

- `docs/ops/strategy-candidate-direction-map-v1.md`
- `docs/ops/mtc-001-main-trend-capture-fragility-evaluation-framework-v0.md`
- `docs/ops/nsc-007-next-strategy-candidate-direction-inspect.md`
- `docs/ops/nsc-011-4h-main-trend-lifecycle-capture-direction-inspect.md`
- `docs/ops/nsc-012-trend-failure-false-breakout-avoidance-companion-inspect.md`
- `docs/ops/nsc-013-direction-a-4h-main-trend-lifecycle-clean-baseline-minimal-experiment-plan.md`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `docs/ops/nsc-016-ea-post-entry-early-exit-overlay-minimal-experiment-plan.md`
- `docs/ops/nsc-018-ea-rejection-direction-a-next-decision-closure-review.md`
- `docs/ops/nsc-019-direction-b-4h-trend-1h-entry-timing-minimal-experiment-plan.md`
- `docs/ops/te-001-sparse-trend-edge-evidence-review.md`
- `docs/ops/te-007a-direction-a-official-validation-task-card.md`
- `docs/ops/project-roadmap-v2.md`

---

## 1. Why This Refresh Exists

Direction Map v1 (SCDM-001, 2026-05-06) established a candidate direction
pool and recommended Direction A as P0 with Direction E as companion.

Since then, the research chain produced:

- NSC-014 / TE-007A: Direction A clean baseline = `PAUSE_FRAGILE`.
- NSC-017 / NSC-018: E-A overlay = `REJECT_OVERFILTERS`.
- NSC-020 / TE-001: Direction B-D1 = `MIXED_PARTIAL`, top-3 still negative.
- MTC-001: A formal fragility evaluation framework for sparse-trend strategies.

The Owner has decided:

1. Pause Direction A. Do not reopen, rescue, or re-tune.
2. Do not execute TE-006B (2019-Q4 supplemental validation).
3. Return to Strategy Direction Map.
4. Find a new Main Trend Capture direction.
5. Adopt MTC-001 as the default fragility framework for all future directions.

This refresh updates the direction map to reflect these decisions and
re-evaluate all candidates under MTC-001.

---

## 2. What The Research Chain Taught

### 2.1 Direction A: Real Signal, Structural Fragility

Direction A (4h Donchian20 breakout + EMA60 close-break exit) is not noise.
It produced:

- 172 closed positions.
- Net +2332 after costs. PF 1.42.
- Payoff ratio ~6x.
- Moderate drawdown (realized 6.08%, MTM 8.33%).
- Multi-day trend holds.

But the signal is structurally fragile:

- Top-3 removal = -935 (negative).
- 2023+2024 carry most of the net.
- Winner cluster is narrow.
- E-A overlay test confirmed: the losing side cannot be managed without
  cutting the payoff tail.
- B-D1 entry timing improved marginally but did not resolve the core
  fragility.

Under MTC-001, Direction A classifies as `PAUSE_FRAGILE`. The primary
fragility gate (top-3 net excluding > 0) is not met. Year-by-year
concentration (2023/2024 dominant) is flagged. Winner attribution supports
structural trend capture, but the cluster is too narrow for deployment.

**Lesson: The 4h Donchian20 + EMA60 combination on ETH has a real trend
signal, but the signal may be inherently concentrated for this asset /
timeframe / parameter family. Incremental rule edits (overlays, entry
timing) tested so far cannot resolve this concentration without also
damaging the payoff source.**

### 2.2 Direction E / E-A: Overlay Path Blocked

E-A was the lowest-freedom Direction E overlay. It tested a one-bar
close-back early exit. Result:

- 27 of 33 triggered trades improved.
- But 3 worsened trades lost -1449.
- E-A cut two baseline top-5 signal timestamps.
- Net, gross, PF, drawdown, and fragility all worsened.

Under MTC-001, E-A classifies as `REJECT`. The overlay reduced many small
losers but destroyed part of the winner cluster that funds the strategy.

**Lesson: For sparse-trend strategies, the winner cluster is the profit
engine. Post-entry early-exit rules that are intuitively sensible
(false-breakout avoidance) can damage the payoff tail more than they save
on the losing side. Direction E as an overlay family is structurally risky
for sparse-trend strategies.**

### 2.3 Direction B-D1: Marginal Improvement, Same Fragility

B-D1 added 1h first-window follow-through confirmation to the 4h
Donchian20 entry. Result:

- Net +2441 vs Direction A +2332 (marginal improvement).
- PF 1.45 vs 1.42 (marginal).
- Drawdown slightly better.
- Top-3 excluding: -744 vs -935 (better but still negative).
- Entry price, entry-to-stop distance, and average loser were actually
  worse than baseline.

Under MTC-001, B-D1 classifies as `PAUSE_FRAGILE`. It preserved the
baseline winner cluster and slightly improved top-3 removal, but did not
cross the threshold.

**Lesson: Entry timing refinement within the same 4h Donchian20 framework
produces marginal improvements at best. The core fragility is likely a
property of the breakout mechanism and the asset's trend structure, not
a property of entry timing.**

### 2.4 Combined Readout

The research chain tested three approaches to improving Direction A:

| Approach | Result | Fragility Impact |
|----------|--------|-----------------|
| Overlay (E-A) | REJECT | Worsened — cut winners |
| Entry timing (B-D1) | PAUSE_FRAGILE | Marginal — same fragility shape |
| Exit redesign | Not tested (EMA60 was already a structural change from T1-A's ATR trailing) | — |

The consistent pattern: incremental modifications to the 4h Donchian20
framework cannot cross the top-3 fragility gate. This suggests the
fragility is a structural property of this particular entry/exit/asset
combination, not a parameter or timing problem.

---

## 3. MTC-001 Framework Adoption

This refresh formally adopts MTC-001 as the default fragility evaluation
framework for all Main Trend Capture direction experiments.

**Default classification gates (from MTC-001 Section 5):**

| Classification | Gate |
|---------------|------|
| INSUFFICIENT_EVIDENCE | Trade count floors not met, winner count < 15, backtest window < 3 years |
| REJECT | Top-1 < 0, net PnL < 0, PF < 1.0, single year > 80% of net, or overlay worsens fragility with no alternative path |
| PAUSE_FRAGILE | Top-1 > 0 but top-3 < 0; real signal but not robust |
| RESEARCH_PASS | Top-3 > 0, top-5 near 0 or positive, 2+ years positive, no year > 60% of net, PF > 1.1 |
| RUNTIME_CANDIDATE | RESEARCH_PASS + OOS validation + Owner approval |

**Application rule:** Every future experiment plan must pre-register these
gates. Deviations require explicit Owner approval in the experiment plan.

---

## 4. Updated Direction Status

### 4.1 Direction A — 4h Main Trend Lifecycle Capture (Donchian20 + EMA60)

| Field | Value |
|-------|-------|
| Status | **PAUSE — Do not reopen** |
| MTC-001 classification | PAUSE_FRAGILE |
| Evidence | NSC-014, TE-007A |
| Key metrics | 172 trades, net +2332, PF 1.42, top-3 excl -935 |
| Why paused | Top-3 fragility gate not met; incremental modifications (E-A, B-D1) cannot resolve |
| Allowed next | None. Direction A frozen variant is closed for research. |
| Not allowed | Parameter rescue, overlay search, 1h entry search, exit redesign, Donchian/EMA sweep |

Direction A is preserved as positive-but-fragile evidence. It proves the 4h
Main Trend Lifecycle thesis has signal on ETH. It does not prove the
Donchian20 + EMA60 variant is deployable.

This document does not reclassify Direction A. It remains PAUSE_FRAGILE.
No rescue, continuation, or modification is authorized.

### 4.2 Direction B — 4h Trend + 1h Entry Timing

| Field | Value |
|-------|-------|
| Status | **Reserve — Not executed** |
| MTC-001 classification | Not applicable (B-D1 tested as PAUSE_FRAGILE; B overall untested beyond D1) |
| Evidence | NSC-019 plan, NSC-020 / TE-001 B-D1 result |
| Why reserve | B-D1 showed marginal improvement but same fragility shape; further 1h family search blocked by Owner decision |
| Allowed next | None in current cycle |
| Not allowed | D2/D3/D4 family search, new 1h entry rules, CPM-style pullback entry |

Direction B remains a valid direction concept (4h qualification + 1h timing)
but the current research chain has shown that entry timing refinement within
the Donchian20 framework does not cross the fragility gate.

If a future direction re-opens the 4h+1h question with a fundamentally
different 4h entry mechanism (not Donchian20), Direction B's structural
design (4h qualification, 1h timing) could apply. But that would be a new
direction, not a continuation of the current B.

### 4.3 Direction C — Volatility Contraction / Re-expansion

| Field | Value |
|-------|-------|
| Status | **Candidate — Available for inspect** |
| MTC-001 classification | Not yet evaluated |
| Evidence | None (direction-level concept only) |
| Strategy hypothesis | Within an established 4h trend, volatility contracts before the next impulse. Enter on breakout from contraction, in trend direction. |
| What it addresses | Direction A's false-breakout problem — contraction may filter noise and improve signal quality |
| May reduce top-winner fragility? | Possibly — fewer but higher-quality signals could have better winner distribution |
| Primary risk | Very low signal count; may not meet MTC-001 trade count floors |
| New data needed | No |
| Allowed next | Docs-only inspect (Level 1) |

Direction C is the strongest available candidate for a new direction inspect
because:

- It uses a multi-candle pattern (contraction) instead of a single-bar
  breakout, which is structurally different from Donchian20.
- It targets the same trend continuation profit source but with a different
  entry trigger.
- The contraction filter may reduce false signals, potentially reducing the
  number of losing trades that create fragility.
- It does not require new data or infrastructure.

The primary risk is sample size: contraction-then-expansion events are
infrequent on 4h ETH. If trade count floors cannot be met, the direction
must be classified INSUFFICIENT_EVIDENCE and paused.

### 4.4 Direction D — Non-Pinbar Structured Pullback / Value-Zone Entry

| Field | Value |
|-------|-------|
| Status | **Candidate — Available for inspect** |
| MTC-001 classification | Not yet evaluated |
| Evidence | None (direction-level concept only) |
| Strategy hypothesis | Use zone-based pullback entry (EMA zone, structure level) within a 4h trend instead of pure breakout entry |
| What it addresses | Direction A's entry-price problem — zone entry may improve entry location and reduce initial risk |
| May reduce top-winner fragility? | Possibly — better entry price could reduce average loser and improve payoff ratio; but does not directly address winner-cluster concentration |
| Primary risk | Overfit risk from zone definitions; may drift toward CPM-style pullback entry |
| New data needed | No |
| Allowed next | Docs-only inspect (Level 1) |

Direction D is an alternative entry mechanism. It tests whether pullback
entry to a value zone within an established trend outperforms pure breakout
entry.

Key caution: Direction D must not become CPM-style pullback-continuation.
The value zone must be defined within a 4h trend context, not as a
standalone 1h pullback pattern. If the zone definition is too loose, the
direction drifts toward CPM and must be reclassified or rejected.

### 4.5 Direction E — Trend Failure / False Breakout Avoidance

| Field | Value |
|-------|-------|
| Status | **Closed as overlay family — not reopened** |
| MTC-001 classification | E-A: REJECT_OVERFILTERS |
| Evidence | NSC-012 inspect, NSC-016 plan, NSC-017 result, NSC-018 closure |
| Why closed | E-A (the lowest-freedom variant) cut winners and worsened fragility; higher-freedom variants (E-B through E-F) carry more overfit risk |
| Allowed next | None as overlay on Donchian20-based directions |

Direction E as an overlay family is closed for the current research cycle.

Reasoning: The Sparse Trend Edge Principle (MTC-001 Section 7) established
that the winner cluster is the profit engine. E-A proved that even the
simplest post-entry false-breakout exit damages that engine. Higher-freedom
E variants (overextension filter, volatility spike filter, weak follow-through)
carry more parameter freedom and higher overfit risk. Testing them against
the same Direction A baseline would be a search, not an experiment.

If a future direction uses a fundamentally different entry mechanism
(not Donchian20 breakout), Direction E concepts could be re-evaluated
for that specific direction. That would require a new docs-only inspect.

### 4.6 Direction F — Funding / OI / Crowding-Aware Filter

| Field | Value |
|-------|-------|
| Status | **Backlog — Requires new data pipeline** |
| MTC-001 classification | Not applicable (filter, not strategy) |
| Evidence | None |
| What it addresses | Loss avoidance during crowded trend setups |
| Primary risk | High validation cost (new data pipeline needed); risk of becoming a regime system |
| New data needed | **Yes** — funding rate, open interest, long/short ratio |
| Allowed next | None until data pipeline exists |

Direction F is not actionable in the current cycle. It requires infrastructure
work (data ingestion) that is outside the strategy research scope.

Direction F is preserved as a future capability-pool item. It should be
revisited after a baseline trend strategy has RESEARCH_PASS evidence and
the data pipeline is available.

### 4.7 Direction G — Range / Consolidation Module

| Field | Value |
|-------|-------|
| Status | **Not current mainline — Preserve for completeness** |
| Alignment with Owner thesis | Low — Owner's thesis is trend capture, not range trading |
| Allowed next | None in current cycle |

Direction G is not aligned with the current Main Trend Capture direction. It
is preserved in the pool for completeness but is not a candidate for
current research.

---

## 5. What The Fragility Pattern Means

### 5.1 The Core Problem

Direction A, E-A, and B-D1 all point to the same structural issue:

**The 4h Donchian20 breakout mechanism on ETH produces a real but narrow
trend signal. The signal's positive expectancy depends on a small cluster
of large winners. Incremental modifications tested so far cannot widen
this cluster without also damaging it.**

This is not a parameter problem. It is not an entry timing problem. It is
not an overlay problem. It may be a property of the entry mechanism itself.

### 5.2 Why New Directions Must Be Structurally Different

The research chain has exhausted the incremental-modification path for the
Donchian20 framework:

- Parameter tuning is prohibited (sparse trend profit principle #7).
- Overlay testing (E-A) damaged the payoff tail.
- Entry timing (B-D1) produced marginal improvement.
- Exit redesign is not tested separately, but EMA60 was already a
  structural change from T1-A's ATR trailing.

A new direction that crosses the MTC-001 fragility gates is likely to need
a structurally different entry mechanism — one that produces a different
signal distribution, not just a modified version of the same signal.

### 5.3 What "Structurally Different" Means

A structurally different entry mechanism would:

- Use a different signal source (not Donchian breakout).
- Produce a different trade distribution (not the same 172 trades with
  minor timing changes).
- Have a different winner-cluster shape (potentially wider, potentially
  different trades).

It would still:

- Target the same 4h main trend lifecycle profit source.
- Use the same cost model SSOT.
- Be evaluated under the same MTC-001 gates.
- Remain standalone (no portfolio, regime, multi-strategy, multi-asset).

---

## 6. Updated Candidate Priority Ranking

### Available For Inspect (Level 1)

| Rank | Direction | Why | MTC-001 Fragility Hypothesis | Key Risk |
|------|-----------|-----|------------------------------|----------|
| **1** | **C: Volatility Contraction / Re-expansion** | Structurally different entry (multi-candle pattern vs single-bar breakout); targets same trend continuation; may filter noise | Contraction filter may produce fewer but higher-quality signals with wider winner distribution | Sample size may be too low for MTC-001 trade count floors |
| **2** | **D: Structured Pullback / Value-Zone Entry** | Different entry mechanism (zone-based vs breakout); may improve entry price and reduce initial risk | Better entry price could improve payoff ratio and reduce average loser | Zone definitions may drift toward CPM; must guard against pullback-continuation rescue |

### Reserve (Not Current Cycle)

| Direction | Why Reserve | Reactivation Condition |
|-----------|------------|----------------------|
| B: 4h + 1h Entry Timing | B-D1 showed marginal improvement only; 1h family search blocked | New 4h entry mechanism (not Donchian20) with B's structural design (4h qualification + 1h timing) |

### Paused / Closed (Not Reopened)

| Direction | Status | Reason |
|-----------|--------|--------|
| A: Donchian20 + EMA60 | PAUSE — Do not reopen | PAUSE_FRAGILE; incremental path exhausted |
| E: Overlay family | Closed | E-A REJECT; higher-freedom variants carry more risk |

### Backlog (Requires Infrastructure)

| Direction | Status | Blocker |
|-----------|--------|---------|
| F: Funding/OI filter | Backlog | New data pipeline required |

### Not Current Mainline

| Direction | Status | Reason |
|-----------|--------|--------|
| G: Range module | Not current mainline | Not aligned with trend capture thesis |

---

## 7. Closed Directions Consolidated

| Direction | ID | Classification | Key Evidence | Date |
|-----------|----|---------------|--------------|------|
| CPM-1 (1h Pinbar pullback) | CPM-1 | Paused — OOS failure | 2021 OOS -21.54%, 2022 OOS -9.72% | 2026-05-06 |
| CPM-2 A (one-bar reclaim) | NSC-005 | INSUFFICIENT_EVIDENCE | 56 trades, -973 net | 2026-05-06 |
| CPM-2 B (Donchian-location pullback) | NSC-005 | INSUFFICIENT_EVIDENCE | 135 trades, -5682 net | 2026-05-06 |
| T1-A (4h ATR trailing) | NSC-009/010 | INSUFFICIENT_EVIDENCE_THIN_SAMPLE | Top-1 = 98.47% of net | 2026-05-06 |
| Direction A (Donchian20 + EMA60) | NSC-014/TE-007A | PAUSE_FRAGILE | Top-3 excl -935 | 2026-05-07 |
| E-A (one-bar early exit) | NSC-017/018 | REJECT_OVERFILTERS | Cut winners, worsened fragility | 2026-05-06 |
| B-D1 (1h follow-through) | NSC-020/TE-001 | MIXED_PARTIAL → PAUSE_FRAGILE | Top-3 excl -744 | 2026-05-07 |

---

## 8. Recommended Next Steps

### 8.1 Immediate Next: Direction C Inspect

The recommended next task is a docs-only inspect for Direction C
(Volatility Contraction / Re-expansion).

This inspect should:

- Define what "volatility contraction" means on 4h ETH (frozen definition,
  not a parameter family).
- Assess expected signal count: how many contraction-then-expansion events
  occurred in 2021-2025?
- Determine whether MTC-001 trade count floors can plausibly be met.
- Define the frozen entry rule: contraction condition, breakout direction
  filter, entry timing.
- Define the exit rule: should it inherit EMA60 close-break from Direction A,
  or is a different exit hypothesis needed?
- Pre-register MTC-001 fragility gates.
- Explicitly prohibit: parameter sweep, contraction definition search,
  multiple contraction metrics, regime system drift.

If the inspect concludes that signal count is too low for MTC-001 floors,
Direction C should be classified INSUFFICIENT_EVIDENCE and paused. The next
step would then be Direction D inspect.

### 8.2 Second Priority: Direction D Inspect

If Direction C is INSUFFICIENT_EVIDENCE, or in parallel if Owner approves:

- Define what "value zone" means on 4h ETH (frozen zone definition).
- Define the trend qualification mechanism (must be 4h-based, not 1h).
- Define the entry confirmation (must not be Pinbar or CPM-style).
- Define the exit rule.
- Pre-register MTC-001 fragility gates.
- Explicitly prohibit: zone definition search, Fibonacci ratio sweep,
  EMA zone sweep, CPM-style pullback rescue.

### 8.3 Task Card Recommendation

If Owner approves Direction C as next priority:

- **MTC-003**: Docs-only inspect for Direction C. Scope: define frozen
  contraction condition, assess signal count feasibility, specify entry/exit
  rules, pre-register MTC-001 gates. No experiment, no code, no backtest.

If Owner approves Direction D in parallel or as alternative:

- **MTC-004**: Docs-only inspect for Direction D. Scope: define frozen
  zone entry, specify trend qualification, specify entry/exit rules,
  pre-register MTC-001 gates. No experiment, no code, no backtest.

### 8.4 Small-Live Readiness Gate

**Small-live readiness gate remains unmet.** No candidate has passed minimum
fragility gates. This document does not change that status.

---

## 9. Not-Now List (Consolidated)

### Strategy Research Prohibitions

- No CPM-1 rescue.
- No CPM-2 A/B rescue.
- No Candidate C auto-start.
- No T1-A parameter rescue.
- No Direction A rescue, continuation, or modification.
- No Direction A Donchian / EMA / stop lookback sweep.
- No Direction E overlay experiments.
- No E-A rescue (buffers, waiting periods, partial exits, other variants).
- No Direction B D2/D3/D4 1h family search.
- No new 1h entry rules.
- No overlay stacking.
- No after-the-fact selection of best result.
- No parameter sweep of any kind.
- No cost / funding / slippage relaxation.

### Infrastructure Prohibitions

- No portfolio engine.
- No regime system.
- No multi-strategy runtime.
- No multi-asset expansion.
- No full data feature store.
- No complex ML.
- No tick / orderbook simulator.

### Runtime / Deployment Prohibitions

- No runtime/profile/risk changes.
- No production strategy implementation.
- No backtester / research engine core changes.
- No promotion conclusion.
- No small-live conclusion.
- No live deployment advice.

---

## 10. Owner Decision Required

The following decisions require explicit Owner input before the next task
card can proceed:

### Decision 1: Direction C Priority

Should Direction C (Volatility Contraction / Re-expansion) be the next
inspect priority?

**Recommendation:** Yes. Direction C is the strongest available candidate
because it uses a structurally different entry mechanism (multi-candle
contraction vs single-bar breakout) that targets the same trend
continuation profit source. The primary risk is sample size.

### Decision 2: Direction D In Parallel

Should Direction D inspect proceed in parallel with Direction C, or wait
for Direction C's result?

**Recommendation:** Wait. If Direction C meets MTC-001 trade count floors,
it takes priority. If Direction C is INSUFFICIENT_EVIDENCE, Direction D
becomes the next inspect.

### Decision 3: Direction A Evidence Preservation

Direction A remains PAUSE_FRAGILE. Should the existing NSC-014 / TE-007A
evidence be preserved as-is, or should any additional documentation be
added?

**Recommendation:** Preserve as-is. No additional documentation needed.

---

## 11. Explicit Non-Goals

- This document does not reclassify Direction A.
- This document does not approve any promotion.
- This document does not authorize any experiment.
- This document does not authorize any runtime or profile change.
- This document does not reduce the evidence bar.
- This document does not override Owner judgment.
- This document does not rescue any closed or paused direction.
- This document does not establish a new direction — that requires a
  separate docs-only inspect.

---

## 12. Relationship To Existing Governance

| Document | Relationship |
|----------|-------------|
| `project-roadmap-v2.md` | High-level scope authority; this map stays within Baseline Strategy Module Stabilization track |
| `strategy-candidate-direction-map-v1.md` | Superseded by this refresh; v1 directions preserved where status unchanged |
| `mtc-001-fragility-evaluation-framework.md` | Adopted as default fragility framework; all future experiments must pre-register MTC-001 gates |
| `live-safe-v1-program.md` | No live-safe code, runtime, or risk-rule changes |
| `agent-working-rules.md` | Claude task card rules apply |
| `codex-claude-handoff-template.md` | Any future implementation requires a Codex-issued task card |

---

## 13. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Strategy Direction Map Refresh v2 (MTC-002) | Claude |
