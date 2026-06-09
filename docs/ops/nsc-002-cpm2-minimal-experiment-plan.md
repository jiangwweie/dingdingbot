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

# NSC-002 — CPM-2 Minimal Experiment Plan Draft

**Date:** 2026-05-06
**Status:** Proposed / Experiment Plan Only
**Scope:** Docs-only plan draft
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is an experiment plan draft only. It does not authorize running experiments, implementing strategy code, changing runtime profiles, changing risk rules, changing the backtester/research engine, or making any promotion decision.

Allowed future execution must be separately Owner-approved.

Allowed files for this task:

- `docs/ops/**`
- `archive/**` inspect-only
- `reports/**` inspect-only

Forbidden files and areas:

- `src/**`
- `configs/**`
- `tests/**`
- `migrations/**`
- runtime profiles
- strategy implementation
- risk rules
- backtester / research engine

Current state remains unchanged:

- CPM-1 frozen baseline promotion path is paused.
- CPM-1 must not be rescued through parameter tuning.
- The project has no deployable small-live strategy candidate.
- Small-live readiness gate remains unmet until a new candidate module passes an Owner-approved minimum evidence gate.

---

## 1. Purpose

NSC-001 selected the next candidate direction as CPM-2: ETH 1h pullback-continuation with a different entry confirmation mechanism.

Recommended order from NSC-001:

1. Candidate A — One-Bar Continuation Reclaim.
2. Candidate B — Donchian-Location Pullback Confirmation.
3. Candidate C — Two-Candle Pullback-End Pattern, reserve only.

NSC-002 converts Candidate A and Candidate B into a minimal experiment plan. Candidate C is not part of the first experiment round unless both A and B are rejected or paused.

---

## 2. Shared Experiment Contract

### 2.1 Baseline Comparator

Every candidate must be compared against CPM-1 frozen baseline, not against a modified rescue baseline.

CPM-1 frozen reference:

| Dimension | Frozen Reference |
| --- | --- |
| Asset | `ETH/USDT:USDT` |
| Primary timeframe | `1h` |
| MTF timeframe | `4h` |
| Direction | LONG-only |
| Trigger family | CPM-1 Pinbar lower-wick confirmation |
| Trend context | EMA50 primary + 4h EMA60 confirmation |
| Exit structure | Existing CPM-1 frozen exit structure for the selected official comparator run |
| Runtime impact | None |

### 2.2 Required Data Windows

Use the same windows for Candidate A and Candidate B:

| Window | Role |
| --- | --- |
| 2021 full year | Primary negative OOS reference / primary OOS failure reference; must explain CPM-1 signal-level failure |
| 2022 full year | Primary unfavorable-regime / cost-and-whipsaw OOS window |
| 2023 full year | Known in-sample failure / weak follow-through reference |
| 2024 full year | Known positive reference; must not be destroyed |
| 2025 full year | Known positive reference; must not be destroyed |

No additional years may be added in the first pass unless the Owner explicitly approves a revised plan. Adding years after seeing first-pass results is treated as a new plan, not an ad hoc rescue.

### 2.3 Cost Model

Use the CPM-1 official OOS report cost model as the SSOT unless an Owner-approved experiment plan explicitly supersedes it. The future experiment report must record the exact fee, entry slippage, TP slippage, funding setting, and funding approximation values it used, so the report does not conflict with prior BNB9 / 0.04% / 0.0405% research-note variants.

| Cost Item | Required Setting |
| --- | --- |
| Fee | Use CPM-1 official OOS report SSOT; record exact value |
| Entry slippage | Use CPM-1 official OOS report SSOT; record exact value |
| TP slippage | Use CPM-1 official OOS report SSOT; record exact value |
| Funding | Use CPM-1 official OOS report SSOT; record exact enabled/disabled state and approximation value |
| Cost accounting | Report gross PnL before costs and net PnL after fees/slippage/funding |

Any result where net PnL improves but gross expectancy does not improve must be classified as cost/trade-count compression, not strategy validation.

### 2.4 Same-Bar Policy

Use the CPM-1 OOS policy:

- Pessimistic same-bar ordering.
- SL before TP before entry when conflicts are possible.
- Any same-bar conflict count must be reported.

### 2.5 Required Metrics

Each candidate report must include:

| Metric Group | Required Metrics |
| --- | --- |
| PnL | total PnL, gross PnL before costs, net PnL, monthly PnL |
| Expectancy | expectancy per position, profit factor, average win, average loss, win/loss ratio |
| Hit behavior | win rate, TP1 hit count, TP2 hit count, SL-only count, TP1-then-SL count |
| Risk | max drawdown, largest loss cluster, consecutive loss count, loss-cluster period |
| Trade quality | positions, trade legs, trade count by month, average hold time |
| Cost | fees, slippage, funding, total cost drag, cost as percentage of gross PnL/loss |
| Candidate-specific | fired setups, accepted entries, rejected setups, rejection reason counts |
| Continuation | MFE/MAE 24h after candidate entry where available |

### 2.6 Minimum Trade Count Floor

Minimum interpretable floor:

- Primary OOS combined floor: at least 60 closed positions across 2021+2022.
- Per-year soft floor: at least 25 closed positions in 2021 and at least 20 closed positions in 2022.
- Reference-period floor: at least 80 closed positions across 2023+2024+2025.

If a candidate falls below the floor, it cannot pass. It may only be classified as `PAUSE_THIN_SAMPLE` if the trade reduction itself is mechanically expected from the frozen rule.

### 2.7 Anti-Overfit Rules

Applies to both Candidate A and Candidate B:

- One frozen rule definition per candidate before results are inspected.
- One explicitly allowed sensitivity check per candidate.
- No parameter search, grid search, Optuna, multi-threshold sweep, or rescue rerun.
- No adding filters after seeing failure.
- No changing exit, risk sizing, MTF, direction, asset, timeframe, or runtime profile.
- No treating trade-count reduction as proof of edge.
- No selecting the best year-specific variant.
- No mixing Candidate A and Candidate B in first-round evidence.
- No promotion conclusion from first-round experiment evidence.

### 2.8 Failure Classification Output Format

Every experiment report must end with this classification block:

```markdown
## Failure / Evidence Classification

| Field | Value |
| --- | --- |
| Candidate | A or B |
| Frozen rule hash / description | ... |
| Classification | PASS_MIN_EVIDENCE / PAUSE_THIN_SAMPLE / PAUSE_MIXED_EVIDENCE / REJECT_NO_EXPECTANCY / REJECT_TRADE_DELETION_ONLY / REJECT_OVERFIT_RISK / REJECT_FAMILY_DRIFT |
| Primary reason | ... |
| 2021 failure addressed? | Yes / No / Mixed |
| 2022 behavior acceptable? | Yes / No / Mixed |
| 2024/2025 preservation acceptable? | Yes / No / Mixed |
| Gross expectancy improved? | Yes / No |
| Loss clusters improved? | Yes / No |
| Trade count floor met? | Yes / No |
| Runtime/profile/risk change implied? | No |
| Promotion conclusion | None |
```

---

## 3. Candidate A — One-Bar Continuation Reclaim

### 3.1 Strategy Hypothesis

CPM-1 lower-wick confirmation is too weak because it enters before continuation has actually restarted. Candidate A treats the pullback marker as a setup only and requires one subsequent 1h candle to confirm continuation.

If the pullback is truly ending, price should reclaim local structure quickly. If the lower wick is a fake rebound inside a deeper correction, the reclaim should fail and no entry should occur.

### 3.2 Frozen Rule Definition

First-round Candidate A rule:

1. Use the same CPM-1 setup context: ETH 1h, LONG-only, EMA50 primary context, 4h EMA60 confirmation, same frozen CPM-1 Pinbar setup marker.
2. When a CPM-1 Pinbar setup marker appears, do not enter immediately.
3. Inspect only the next fully closed 1h candle.
4. Accept the setup only if the next candle closes above the Pinbar setup candle high.
5. If the next candle does not close above the setup candle high, reject the setup.
6. If accepted, enter using the same next-entry convention defined by the experiment harness for delayed confirmation.
7. The report must record the confirmation candle timestamp, entry timestamp, entry bar, and entry price convention.
8. The report must prove the confirmation decision and fill decision use only the setup candle, the fully closed confirmation candle, and the defined entry bar, with no future candle access.
9. Do not alter stop, take-profit, risk sizing, MTF, direction, or cost assumptions.

This definition intentionally chooses one reclaim rule. Candidate A must not become a combination search across multiple reclaim variants.

### 3.3 Allowed Sensitivity Check

Allowed one-time sensitivity check:

- Compare `next candle close > setup candle high` against `next candle high > setup candle high AND next candle close > setup candle close`.

This check is diagnostic only. The main result remains the frozen rule above. If the sensitivity variant performs better, it cannot be promoted directly; it requires a new Owner-approved plan.

Not allowed:

- Multi-candle wait windows.
- EMA reclaim variants.
- Pivot reclaim variants.
- Combining several reclaim definitions.
- Selecting per-year reclaim logic.

### 3.4 Required Data Windows

Use the shared windows:

- 2021 full year.
- 2022 full year.
- 2023 full year.
- 2024 full year.
- 2025 full year.

### 3.5 Cost Model

Use the shared CPM-1 official OOS report cost-model SSOT. The report must record exact fee, entry slippage, TP slippage, funding enabled/disabled state, and funding approximation values. Report gross and net metrics separately.

### 3.6 Same-Bar Policy

Use pessimistic same-bar policy. Report any same-bar conflicts, especially delayed-confirmation entries that enter and hit stop/target inside the same bar.

### 3.7 Required Metrics

Use all shared required metrics, plus Candidate A-specific:

- Pinbar setup markers detected.
- Reclaim confirmations accepted.
- Reclaim failures rejected.
- Acceptance rate by year and by month.
- Delay from setup marker to entry.
- Confirmation candle timestamp, entry timestamp, entry bar, and entry price convention.
- Proof that confirmation and fill decisions do not use future candles.
- MFE/MAE from confirmed entry, not from original setup marker.
- Counterfactual CPM-1 result for rejected setups where available.

### 3.8 Minimum Trade Count Floor

Candidate A must meet the shared floor:

- At least 60 closed positions across 2021+2022.
- At least 25 closed positions in 2021.
- At least 20 closed positions in 2022.
- At least 80 closed positions across 2023+2024+2025.

If the reclaim rule rejects too many setups, classify as `PAUSE_THIN_SAMPLE` or `REJECT_TRADE_DELETION_ONLY`, depending on expectancy evidence.

### 3.9 Pass / Pause / Reject Gates

Pass minimum evidence only if all are true:

- 2021 gross expectancy improves versus CPM-1, not just net PnL.
- 2021 largest loss cluster or total clustered loss materially improves.
- 2021 net PnL improves after costs.
- 2022 does not become materially worse in max drawdown or loss clustering.
- 2024+2025 combined net PnL retention is at least 70% of CPM-1 frozen reference, unless gross expectancy improves enough to justify a separate Owner review. This is only a minimum protection line for continued evidence review; it is not a promotion criterion and does not make the candidate small-live ready.
- Trade count floor is met.
- Improvement source is explained as better continuation confirmation, not just fewer trades.

Pause if any are true:

- 2021 improves but 2024/2025 are materially damaged.
- Evidence is mixed across gross expectancy, clusters, and net PnL.
- Trade count is below floor but accepted trades show materially better expectancy.
- Sensitivity check contradicts frozen rule enough to require re-planning.

Reject if any are true:

- Gross expectancy does not improve.
- Improvement is mostly cost reduction from fewer trades.
- Loss clusters remain structurally similar.
- Trade count drops below floor with no strong expectancy improvement.
- The rule misses good-year winners in the same pattern as the rejected 0.382 limit-entry proxy.
- The experiment drifts into reclaim-rule search.

### 3.10 Anti-Overfit Rules

Candidate A-specific overfit controls:

- The reclaim rule is frozen before execution.
- No adding an EMA/pivot/range filter after result review.
- No optimizing wait length.
- No alternate entry price selection after result review.
- No changing Pinbar geometry.
- No combining Candidate A with Candidate B in first-round results.

---

## 4. Candidate B — Donchian-Location Pullback Confirmation

### 4.1 Strategy Hypothesis

CPM-1 fails when a lower-wick setup appears in a toxic local range location where the apparent pullback end is structurally fragile. Candidate B tests whether local Donchian location can serve as a structural confirmation that the pullback is ending in a survivable continuation zone.

Candidate B is not Donchian breakout, and it is not an E4 hard filter revival. It must be tested as CPM-2 structural confirmation inside the ETH 1h pullback-continuation family.

### 4.2 Frozen Rule Definition

First-round Candidate B rule:

1. Use the same CPM-1 setup context: ETH 1h, LONG-only, EMA50 primary context, 4h EMA60 confirmation, same frozen CPM-1 Pinbar setup marker.
2. Compute Donchian 20 high from the previous 20 fully closed 1h candles, excluding the current setup candle.
3. Compute distance:

```text
distance_to_donchian_high = (setup_close - previous_20_bar_donchian_high) / previous_20_bar_donchian_high
```

4. Accept the setup only if `distance_to_donchian_high >= -0.016809`.
5. Reject the setup if `distance_to_donchian_high < -0.016809`.
6. Enter using the same CPM-1 timing convention for accepted setups.
7. Do not alter stop, take-profit, risk sizing, MTF, direction, or cost assumptions.

The threshold is carried as a structural-location boundary from NSC-001 / historical inspect evidence, not as a parameter to tune. Before any execution, the future experiment plan/report must cite the exact provenance for `-0.016809`. If provenance cannot be confirmed, Candidate B must be classified as paused before execution. The threshold may not be replaced, rounded, swept, or temporarily adjusted.

### 4.3 Allowed Sensitivity Check

Allowed one-time sensitivity check:

- Compare Donchian lookback `20` against lookback `30` using the same threshold semantics, only to test whether the structural-location idea is brittle to the local range horizon.

This check is diagnostic only. It may not be used to select the better variant for promotion. If lookback `30` looks materially better, it requires a new Owner-approved plan.

Not allowed:

- Threshold sweep.
- Combining multiple Donchian thresholds.
- Adding EMA slope, volatility, or recent-return toxic filters.
- Reusing M1/M1b/M1c as pass evidence without fresh CPM-2 experiment evidence.
- Recasting Candidate B as Donchian breakout.

### 4.4 Required Data Windows

Use the shared windows:

- 2021 full year.
- 2022 full year.
- 2023 full year.
- 2024 full year.
- 2025 full year.

Warmup handling:

- First 20 1h candles cannot produce Donchian confirmation.
- Warmup-rejected setups must be counted separately as `insufficient_history`, not mixed with structural rejections.

### 4.5 Cost Model

Use the shared CPM-1 official OOS report cost-model SSOT. The report must record exact fee, entry slippage, TP slippage, funding enabled/disabled state, and funding approximation values. Report gross and net metrics separately.

### 4.6 Same-Bar Policy

Use pessimistic same-bar policy. Report same-bar conflicts and confirm Donchian calculation excludes the setup candle and any future candle.

### 4.7 Required Metrics

Use all shared required metrics, plus Candidate B-specific:

- Pinbar setup markers detected.
- Donchian-location confirmations accepted.
- Donchian-location rejections.
- `insufficient_history` count.
- Distribution of `distance_to_donchian_high` for accepted and rejected setups.
- Rejected setup counterfactual gross/net PnL where available.
- Accepted vs rejected expectancy, not just accepted net PnL.
- Anti-lookahead confirmation: previous-20-bar high excludes setup candle.

### 4.8 Minimum Trade Count Floor

Candidate B must meet the shared floor:

- At least 60 closed positions across 2021+2022.
- At least 25 closed positions in 2021.
- At least 20 closed positions in 2022.
- At least 80 closed positions across 2023+2024+2025.

If Candidate B mostly deletes trades and leaves too few accepted entries, it cannot pass.

### 4.9 Pass / Pause / Reject Gates

Pass minimum evidence only if all are true:

- 2021 gross expectancy improves versus CPM-1.
- 2021 loss clusters materially improve.
- Rejected 2021 setups are net toxic on counterfactual gross PnL.
- Accepted setups have better expectancy than rejected setups.
- 2022 does not become materially worse in max drawdown or loss clustering.
- 2024+2025 combined net PnL retention is at least 70% of CPM-1 frozen reference, unless gross expectancy evidence supports separate Owner review. This is only a minimum protection line for continued evidence review; it is not a promotion criterion and does not make the candidate small-live ready.
- Trade count floor is met.
- Improvement is attributable to structural confirmation, not generic E4 trade deletion.

Pause if any are true:

- Rejected setups are toxic in 2021 but not in 2022/2023 references.
- Accepted-vs-rejected expectancy separation is weak but loss clusters improve.
- Lookback sensitivity materially changes the conclusion.
- `-0.016809` threshold provenance cannot be confirmed from NSC-001 / historical inspect evidence before execution.
- Trade count is near the floor and evidence needs Owner judgment.

Reject if any are true:

- Gross expectancy does not improve.
- Accepted-vs-rejected separation is absent.
- Rejected setups are not net toxic.
- Improvement is explained only by fewer trades or lower costs.
- The rule behaves like a hard filter revival rather than a CPM-2 structural confirmation.
- The experiment drifts into threshold search or filter stacking.
- The rule becomes Donchian breakout or trend-following.

### 4.10 Anti-Overfit Rules

Candidate B-specific overfit controls:

- Threshold is frozen at `-0.016809` for first-round evidence.
- `-0.016809` must be provenance-confirmed before execution; otherwise Candidate B pauses.
- No threshold tuning.
- No combining with Candidate A.
- No adding E1/E2/E3 toxic-state filters from prior M-series reports.
- No treating prior M1/M1b/M1c pass status as CPM-2 pass status.
- No changing Donchian from structural confirmation to entry trigger.

---

## 5. Candidate C Reserve

Candidate C — Two-Candle Pullback-End Pattern — is not part of the first-round minimal experiment plan.

Candidate C may enter a later plan only if:

- Candidate A is rejected or paused.
- Candidate B is rejected or paused.
- Owner approves a new plan.
- The new plan prevents drift into standalone Engulfing, dense candlestick triggers, or filter stacking.

Candidate C's first question, if opened later, must be signal density and full PnL conversion. It must not repeat the H5a/H5b pattern where reach rate looked healthy but full PnL failed.

---

## 6. First-Round Sequencing

Recommended order:

1. Candidate A frozen rule.
2. Candidate A allowed sensitivity check.
3. Candidate B frozen rule.
4. Candidate B allowed sensitivity check.
5. Compare classifications, but do not combine candidates.

Reasoning:

- Candidate A most directly tests whether lower-wick confirmation is too early.
- Candidate B tests structural location without reviving E4 as a hard filter.
- Candidate C remains reserve because standalone two-candle / Engulfing evidence already carries high density and PnL-conversion risk.

---

## 7. Required Final Report Shape

Each future experiment report must include:

1. Frozen rule description.
2. Evidence provenance.
3. Data coverage and warmup handling.
4. Cost model and same-bar policy.
5. Year-by-year comparison against CPM-1.
6. Gross vs net decomposition.
7. Loss-cluster analysis.
8. Accepted/rejected setup analysis.
9. Sensitivity check, clearly marked non-decisive.
10. Failure / evidence classification block.
11. Explicit statement: no runtime/profile/risk/promotion change.

---

## 8. Readiness Statement

This plan does not make CPM-2 a strategy candidate. It only defines the minimum evidence needed for a later Owner-approved experiment.

Small-live readiness gate remains unmet until:

1. Owner approves the experiment execution plan.
2. A candidate runs under frozen rules.
3. The candidate passes minimum evidence gates.
4. Failure classification is reviewed.
5. A separate Owner decision advances the candidate.

No promotion conclusion is made here.
