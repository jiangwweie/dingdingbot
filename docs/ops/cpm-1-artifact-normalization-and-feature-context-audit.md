# CPM-1 Artifact Normalization And Feature-Context Audit

**Task ID:** CPM-1-ARTIFACT-NORMALIZATION-FEATURE-CONTEXT-AUDIT  
**Date:** 2026-05-08  
**Status:** Completed / no-run artifact audit  
**Scope:** Existing-artifact audit only  
**Affects Runtime Automatically:** No

---

## 0. Boundary

This audit is no-run and artifact-only. It does not execute a backtest, create a research adapter, modify code, import data, mutate a database, tune CPM-1, propose a gate, or change strategy/runtime interpretation.

This audit determines what existing artifacts can and cannot support for future CPM-1 applicability-boundary research.

---

## 1. Required Inputs Inspected

The requested current documents were inspected:

- `docs/ops/cpm-1-favorable-regime-attribution-review.md`
- `docs/ops/crypto-pullback-module-v1-scope-note.md`
- `docs/ops/crypto-pullback-module-v1-evidence-interpretation-note.md`
- `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/cpm-mod-001-cpm1-applicability-dynamic-enablement-inspect.md`
- `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`

The requested current result artifacts were inspected:

- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/summary.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2021_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2022_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2023_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2024_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2025_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/gate_state_sample.json`
- `reports/oos_runs/cpm1_2021_oos/result.json`
- `reports/oos_runs/cpm1_2021_oos/metadata.json`
- `reports/oos_runs/cpm1_2022_oos/result.json`
- `reports/oos_runs/cpm1_2022_oos/metadata.json`

Relevant archived CPM-1 artifacts were inspected where found:

- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-29-eth-baseline-strategy-research-review-for-external-quant.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2023-failure-attribution-report.md`
- `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-eth-baseline-2023-rescue-research-closure.md`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/strategy_ecology_m0_2026-04-28.json`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/eth_baseline_oos_check_2026-04-28.json`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/pinbar_toxic_state_m1_2026-04-28.json`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/pinbar_toxic_state_m1b_parity_2026-04-28.json`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/p0_pinbar_e4_official_validation_2026-04-29.json`
- `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research_runs/*/result.json`

---

## 2. Artifact Inventory

### 2.1 Current Markdown Evidence

| Artifact | Type | Years | Identity | Trade rows | Feature rows | MFE/MAE/giveback | Close events | Event/artifact labels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `docs/ops/cpm-1-favorable-regime-attribution-review.md` | Markdown report | 2021-2025 | Docs-only attribution | Summarized only | No | Aggregate only via cited MOD-002 | Summarized only | No |
| `docs/ops/crypto-pullback-module-v1-scope-note.md` | Markdown SSOT | 2023-2026 refs | CPM-1 frozen baseline | No | No | No | No | No |
| `docs/ops/crypto-pullback-module-v1-evidence-interpretation-note.md` | Markdown evidence index | 2021-2026 | Evidence registry | No | Aggregate ecology refs | No | No | No |
| `docs/ops/crypto-pullback-module-v1-2021-oos-report.md` | Markdown OOS report | 2021 | Official OOS report | Monthly/cluster summaries | No | No | Exit-class summary | No |
| `docs/ops/crypto-pullback-module-v1-2022-oos-report.md` | Markdown OOS report | 2022 | Official OOS report | Monthly/cluster summaries | No | No | Exit-class summary | No |
| `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md` | Markdown RCA | 2021-2022 plus refs | Failure classification | Summarized clusters | No | No | Summary only | No |
| `docs/ops/cpm-mod-001-cpm1-applicability-dynamic-enablement-inspect.md` | Markdown inspect | 2021-2025 | Dynamic enablement inspect | No | Aggregate feature comparisons | No | No | No |
| `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md` | Markdown Level 3 report | 2021-2025 | Frozen ATR gate diagnostic | Summarized | ATR gate summary | Aggregate yearly | Summary only | No |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Markdown methodology | All current research | Methodology baseline | No | No | No | No | No |

### 2.2 Current JSON Artifacts

| Artifact | Type | Years | Identity | Trade rows | Feature rows | MFE/MAE/giveback | Close events | Event/artifact labels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `reports/oos_runs/cpm1_2021_oos/result.json` | JSON result | 2021 | OOS v3_pms | Yes: `positions[]` | No | No per-position; no aggregate MFE/MAE found | Yes: `close_events[]` | No |
| `reports/oos_runs/cpm1_2021_oos/metadata.json` | JSON metadata | 2021 | OOS run metadata | No | No | No | No | No |
| `reports/oos_runs/cpm1_2022_oos/result.json` | JSON result | 2022 | OOS v3_pms | Yes: `positions[]` | No | No per-position; no aggregate MFE/MAE found | Yes: `close_events[]` | No |
| `reports/oos_runs/cpm1_2022_oos/metadata.json` | JSON metadata | 2022 | OOS run metadata | No | No | No | No | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/summary.json` | JSON summary | 2021-2025 | CPM-MOD-002 diagnostic | Top-10 winners only; year metrics | Partial: top-10 `gate_percentile` only | Aggregate yearly MFE/MAE/giveback | No raw events | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2021_result.json` | JSON result | 2021 | MOD-002 baseline | Yes | No | No per-position | Yes | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2022_result.json` | JSON result | 2022 | MOD-002 baseline | Yes | No | No per-position | Yes | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2023_result.json` | JSON result | 2023 | MOD-002 baseline | Yes | No | No per-position | Yes | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2024_result.json` | JSON result | 2024 | MOD-002 baseline | Yes | No | No per-position | Yes | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2025_result.json` | JSON result | 2025 | MOD-002 baseline | Yes | No | No per-position | Yes | No |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/gate_state_sample.json` | JSON map | 2020+ hourly sample | MOD-002 ATR gate state | No | Partial: timestamp -> ATR / percentile / enabled | No | No | No |

Schema note for CPM-MOD-002 result JSON:

- `positions[]` fields: `position_id`, `signal_id`, `symbol`, `direction`, `entry_time`, `entry_price`, `exit_time`, `exit_price`, `exit_reason`, `realized_pnl`.
- `close_events[]` fields: `position_id`, `order_id`, `event_type`, `event_category`, `close_time`, `close_price`, `close_qty`, `close_pnl`, `close_fee`, `exit_reason`.
- `signal_attributions[]` exists but contains scoring components, not pre-entry market-state features such as ATR percentile, Donchian distance, or EMA slope.

### 2.3 Archived Research Artifacts

| Artifact | Type | Years | Identity | Trade rows | Feature rows | MFE/MAE/giveback | Close events | Event/artifact labels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `strategy_ecology_m0_2026-04-28.json` | JSON ecology summary | 2021-2025 | M0 proxy ecology | No raw rows | Aggregate winners/losers, yearly means, feature buckets | No | No | No |
| `eth_baseline_oos_check_2026-04-28.json` | JSON summary | 2022-2026 refs | Archived baseline/OOS check | No raw rows | No per-entry rows | No | No | No |
| `pinbar_toxic_state_m1_2026-04-28.json` | JSON research summary | 2023-2025 | Toxic-state proxy | No raw rows | Aggregate filter experiment summaries | No | No | No |
| `pinbar_toxic_state_m1b_parity_2026-04-28.json` | JSON research summary | 2023-2025 | M1b parity | No raw rows | Aggregate filter experiment summaries | No | No | No |
| `p0_pinbar_e4_official_validation_2026-04-29.json` | JSON research summary | 2023-2025 | E4 official validation | No raw rows | Aggregate yearly E0/E4 | No | No | No |
| `archive/.../research_runs/*/result.json` | JSON result files | Mostly 2025 windows | Archived pinbar research runs | Yes | No | No per-position | Yes | No |
| `2026-04-29-eth-baseline-strategy-research-review-for-external-quant.md` | Markdown report | 2023-2025 plus refs | Archived official headline review | No raw rows | Aggregate ecology refs | Some aggregate references | Summary only | No |
| `2023-failure-attribution-report.md` | Markdown report | 2023-2025 | Archived 2023 failure report | Monthly/year summaries | No raw rows | Aggregate holding/follow-through references | Event-share summary | No |
| `2026-04-28-eth-baseline-2023-rescue-research-closure.md` | Markdown closure | 2023-2025 | H0-H3a closure | No raw rows | Aggregate feature conclusions | Aggregate MFE/MAE references | No | No |

Important missing artifact:

- No dedicated official CPM-1 2024/2025 trade-level feature report was found.
- No artifact was found that combines `position_id` with ATR percentile, realized volatility, EMA slope, Donchian distance, pullback depth, MFE, MAE, giveback, and event labels in one table.

---

## 3. Metric Scale Reconciliation

### 3.1 Main Metric Families

| Source family | Years | PnL scale | Primary use | Comparability |
| --- | --- | --- | --- | --- |
| Archived official headline docs | 2023-2025, 2026 Q1 refs | Larger archived official research scale | Official headline interpretation | Comparable within archived official family only |
| CPM-MOD-002 yearly baseline JSONs | 2021-2025 | Independent yearly fixed-balance diagnostic runs | Artifact attribution, positions, close events, fragility | Comparable within MOD-002 family only |
| 2021/2022 OOS JSONs | 2021-2022 | OOS v3_pms fixed baseline | OOS evidence and failure classification | Comparable between 2021 and 2022 OOS, with 2022 slippage reporting caveat |
| Archived ecology/M1/P0 artifacts | 2021-2025 / 2023-2025 depending artifact | Proxy or official research-specific scale | Feature and filter interpretation | Not directly comparable to MOD-002 or OOS without same run semantics |

### 3.2 Directly Comparable Metrics

Within the same artifact family:

- PnL is comparable within archived official headline years.
- PnL is comparable within CPM-MOD-002 independent yearly runs.
- PnL is comparable between 2021 and 2022 OOS reports after respecting the 2022 slippage-reporting caveat.
- Trade count, winner count, PF, win rate, fees, slippage, funding, and MaxDD are comparable within CPM-MOD-002.
- Position schemas and close-event schemas are consistent across CPM-MOD-002 baseline year files and OOS result files.

Across artifact families:

- Directional conclusions can be compared: positive vs negative, trade availability, whether a year is fragile.
- Raw PnL magnitude should not be compared across archived official vs CPM-MOD-002 vs OOS families.
- Win rate can be compared only after checking whether it is trade-leg-level or position-level. Some docs warn that `total_trades` can include entry/partial-exit legs, while `positions[]` counts closed positions.
- MaxDD can be compared only within the same report semantics. MOD-002 distinguishes MTM MaxDD and realized closed-trade MaxDD; archived reports may use different MaxDD semantics.

### 3.3 Non-Comparable or Caveated Metrics

| Metric | Caveat |
| --- | --- |
| PnL | Archived official 2024/2025 PnL and MOD-002 2024/2025 PnL differ in scale because MOD-002 uses independent yearly fixed-balance diagnostic runs. Do not normalize by multiplying unless the exact sizing/risk semantics are reconstructed from source artifacts. |
| MaxDD | MOD-002 reports MTM MaxDD and realized closed-trade MaxDD. Archived docs may use official equity-curve MaxDD. OOS docs also include report semantics caveats. |
| Top-N fragility | MOD-002 fragility is position-level PnL sequencing, not official-equity-level fragility. It should not be treated as identical to archived official top-N stress unless raw official positions are available. |
| Trade count | `total_trades` may count trade legs; `positions[]` counts positions. Use positions for top-winner attribution unless a report explicitly defines trade-leg semantics. |
| Slippage | 2022 OOS `total_slippage_cost=0` is a legacy reporting artifact; the report provides an estimated slippage reconciliation. 2021 OOS has corrected slippage tracking. |
| Ecology feature effects | M0 is aggregate/proxy feature attribution. It does not provide per-position feature rows for exact joins. |

### 3.4 Normalization Decision

No new normalized PnL series is created in this audit.

Reason: raw fields needed to reconstruct a single consistent official-equity series across archived official headline, CPM-MOD-002, OOS, and proxy artifacts are not present in one consistent schema. Creating a normalized series would require assumptions about sizing, compounding, cost model, and report semantics that are outside this no-run audit.

---

## 4. Trade-Level Context Availability

### 4.1 Field Availability For 2024/2025 Top Winners

This table applies to the top winners identified in the prior attribution review, using current MOD-002 artifacts.

| Field | Availability | Evidence / limitation |
| --- | --- | --- |
| Entry timestamp | `AVAILABLE` | `positions[].entry_time`; top-10 summary also has `entry_time_iso` |
| Exit timestamp | `AVAILABLE` | `positions[].exit_time`; top-10 summary also has `exit_time_iso` |
| Holding duration | `DERIVABLE_ONLY_WITH_NEW_COMPUTATION` | Can be computed from entry/exit timestamps; prior review already did limited derivation |
| Entry price | `AVAILABLE` | `positions[].entry_price` |
| Exit price | `AVAILABLE` | `positions[].exit_price` |
| Close-event sequence | `AVAILABLE` | `close_events[]` keyed by `position_id`; requires ordering by `close_time` |
| TP1 / TP2 / SL events | `AVAILABLE` | `close_events[].event_type` |
| Net PnL | `AVAILABLE` | `positions[].realized_pnl` |
| MFE | `PARTIALLY_AVAILABLE` | Aggregate yearly MFE only in `summary.json`; not per top winner |
| MAE | `PARTIALLY_AVAILABLE` | Aggregate yearly MAE only; not per top winner |
| Giveback | `PARTIALLY_AVAILABLE` | Aggregate yearly giveback only; not per top winner |
| ATR percentile at entry | `PARTIALLY_AVAILABLE` | Top-10 winners in `summary.json` include `gate_percentile`; all-trade join may be possible from `gate_state_sample.json` but would require a separate read-only extraction |
| Realized volatility at entry | `NOT_AVAILABLE` | Present only in M0 aggregate feature summaries, not per trade |
| 4h EMA slope at entry | `NOT_AVAILABLE` | Present only in M0 aggregate/year/bucket summaries, not per trade |
| 1h EMA/trend state at entry | `NOT_AVAILABLE` | Baseline implies filters passed; exact EMA distance/slope is absent |
| Recent 72h return | `NOT_AVAILABLE` | M0 aggregate only; no per-position rows |
| Recent 7d return | `NOT_AVAILABLE` | Not found in inspected CPM artifacts |
| Donchian distance / recent-high distance | `NOT_AVAILABLE` | M0 aggregate/bucket only; E4 summaries are aggregate only |
| Pullback depth | `NOT_AVAILABLE` | No inspected artifact records pullback depth per trade |
| Event / news / data artifact label | `NOT_AVAILABLE` | No event/news/data-artifact annotation artifact found |

### 4.2 Top-Winner ATR Percentile Recovery

CPM-MOD-002 `summary.json` includes `baseline_top_10_winners` with:

- `position_id`
- `signal_id`
- `entry_time_iso`
- `signal_time_estimated_iso`
- `exit_time_iso`
- `realized_pnl`
- `year`
- `disabled_by_gate`
- `gate_percentile`

This means ATR gate percentile is available for the top-10 winners only. It is not embedded in the raw `positions[]` rows.

Observed examples:

| Winner | Year | Entry UTC | PnL | Gate percentile |
| --- | ---: | --- | ---: | ---: |
| `pos_da6c1071` | 2024 | 2024-10-12 09:00 | +182.23 | 0.0148 |
| `pos_c335a330` | 2024 | 2024-09-26 12:00 | +180.77 | 0.1426 |
| `pos_64e4fb64` | 2024 | 2024-04-08 04:00 | +179.42 | 0.4324 |
| `pos_60617280` | 2024 | 2024-09-19 02:00 | +178.04 | 0.5505 |
| `pos_aeb535aa` | 2024 | 2024-02-25 05:00 | +176.46 | 0.5796 |
| `pos_df74549a` | 2025 | 2025-04-22 20:00 | +175.34 | 0.3468 |
| `pos_eb90b5f1` | 2025 | 2025-10-03 09:00 | +175.15 | 0.4713 |
| `pos_8199b51e` | 2025 | 2025-05-08 12:00 | +174.70 | 0.4958 |

Read: top winners were below the frozen 0.60 disable threshold. This supports the MOD-002 statement that top winners were preserved. It does not explain Donchian distance, slope, realized volatility, pullback quality, or event context.

### 4.3 Fields Requiring New Backtest Or Adapter

The following require either raw candle-feature extraction or a new empirical artifact. They are not recoverable from the current position/close-event rows alone:

- Per-position MFE / MAE / giveback.
- 4h EMA slope at entry.
- 1h EMA slope / distance at entry.
- Realized volatility at entry.
- Recent 72h / 7d return at entry.
- Donchian distance at entry.
- Pullback depth at entry.
- Event/news labels.
- Data-artifact labels.

A future read-only feature extraction task could be possible without strategy execution if it uses existing timestamps and existing OHLCV data, but that is not performed or authorized here.

---

## 5. 2024 vs 2025 Evidence Quality

| Dimension | 2024 | 2025 | Stronger |
| --- | --- | --- | --- |
| MOD-002 net PnL | +850.61 | +200.10 | 2024 |
| MOD-002 PF | 1.96 | 1.28 | 2024 |
| MOD-002 trade / winner count | 44 / 26 | 41 / 17 | 2024 |
| MOD-002 MTM MaxDD | 5.02% | 4.81% | Similar |
| Top-1 removal | Positive | Positive | Both |
| Top-3 removal | +426.87 | -203.14 | 2024 |
| Top-5 removal | +72.37 | -547.43 | 2024 |
| Aggregate MFE/MAE/giveback | Available | Available | Equal availability |
| Per-trade feature context | Missing except top-10 gate percentile | Missing except top-10 gate percentile | Equal limitation |
| Top-winner ambiguity | Moderate | Higher due short-hold TP2 winners | 2024 |

2024 is stronger evidence than 2025.

Reasons:

- Better net PnL, PF, trade count, and winner count in MOD-002.
- Survives top-3 and top-5 removal.
- Top winners are mostly multi-day holds that mechanically resemble pullback continuation.

2025 is weaker:

- Top-3 removal turns negative.
- Two top winners have very short holds: 1h and 3h.
- Existing artifacts can verify TP1/TP2 events for those short holds, but cannot classify whether they were normal continuation, event-driven, or bar-level artifacts.

2025 should be downgraded relative to 2024 in evidence strength, but not rejected from research evidence solely on artifact limitations.

---

## 6. 2023 Failure Context Availability

### 6.1 Available 2023 Context

From MOD-002 `baseline_2023_result.json` and `summary.json`:

| Field | Availability | Evidence |
| --- | --- | --- |
| Entry timestamps | `AVAILABLE` | `positions[]` |
| Trade outcomes | `AVAILABLE` | `positions[].realized_pnl`, `exit_reason` |
| Close events | `AVAILABLE` | 15 SL, 4 TP1, 3 TP2 close events in MOD-002 baseline |
| Hold duration | `DERIVABLE_ONLY_WITH_NEW_COMPUTATION` | Entry/exit timestamps available |
| SL share / TP share | `AVAILABLE` | Derivable from close events; summary/report already states event counts |
| Aggregate MFE/MAE/giveback | `AVAILABLE` | MOD-002 `baseline_trade_quality` |
| Post-entry continuation behavior | `PARTIALLY_AVAILABLE` | Aggregate MFE/MAE/giveback and close-event distribution only |
| Feature comparison vs 2024/2025 | `PARTIALLY_AVAILABLE` | M0 aggregate/year means, not exact MOD-002 per-entry rows |

2023 MOD-002 baseline trade quality:

| Metric | Value |
| --- | ---: |
| Trade count / winners | 20 / 5 |
| PF | 0.42 |
| MTM MaxDD | 11.04% |
| Avg MFE | 80.48 |
| Avg MAE | -114.13 |
| Avg giveback | 119.74 |
| Winner avg MFE | 343.60 |
| Winner avg MAE | -133.47 |
| Winner avg giveback | 176.25 |

### 6.2 Missing 2023 Context

The current artifacts do not provide per-entry:

- ATR percentile for every 2023 trade.
- Whether each 2023 trade was enabled/disabled by the gate at the exact entry signal time.
- Realized volatility at entry.
- 4h EMA slope at entry.
- 1h EMA/trend distance at entry.
- Recent 72h / 7d return.
- Donchian distance or distance to recent high.
- Pullback depth.
- Event/news/data-artifact labels.

CPM-MOD-002 reports that the ATR gate disabled 170.96 days of 2023 market time but disabled zero actual CPM-1 baseline trades. Existing artifacts are enough to state this fact. They are not enough to explain feature-by-feature why those losing entries occurred outside the disabled state.

### 6.3 2023 Recovery Assessment

2023 failure context is partially recoverable:

- Position and close-event behavior is available.
- Aggregate continuation quality is available.
- Aggregate M0 feature context exists.
- Exact per-entry feature state is missing.

Therefore, existing artifacts can support a docs-only statement that "2023 was not captured by the ATR gate," but cannot support a feature-level boundary explanation of the 2023 failure.

---

## 7. Adequacy For Future Applicability-Boundary Inspect

Classification:

`ARTIFACTS_PARTIALLY_SUFFICIENT_NEED_FEATURE_CONTEXT_RECOVERY`

Reasoning:

| Requirement | Current status |
| --- | --- |
| Compare 2024/2025 favorable entries | Partial: positions, close events, top-10 ATR gate percentile, aggregate MFE/MAE/giveback |
| Compare 2021 damage cluster | Partial: OOS positions/close events and MOD-002 disabled-trade summary; per-entry features missing |
| Compare 2023 unresolved failure entries | Partial: positions/close events and aggregate MFE/MAE/giveback; per-entry features missing |
| Volatility comparison | Partial: top-10 gate percentile and aggregate/year M0; all-entry ATR percentile requires read-only extraction |
| Trend slope comparison | Insufficient: only aggregate M0, no per-entry rows |
| Price location comparison | Insufficient: only aggregate/bucket M0 and E4 summaries |
| Pullback depth comparison | Insufficient: no per-entry pullback-depth artifact found |
| Post-entry continuation comparison | Partial: aggregate MFE/MAE/giveback and close-event distribution |

Existing artifacts are enough for an artifact-aware docs-only inspect, but not enough for a feature-level applicability-boundary inspect that satisfies SRR-002. A future boundary inspect would need feature-context recovery or Owner-approved empirical work.

---

## 8. No-Run Recovery Options

Allowed no-run or docs-only options:

1. Locate missing archived official CPM-1 2024/2025 trade-level artifacts, if they exist outside the inspected paths.
2. Create a docs-only artifact map that links each known CPM-1 result family to its schema, years, cost model, and comparability status.
3. Recover already-existing feature rows if they are hidden in archived artifacts not found by current filename search.
4. Use `gate_state_sample.json` as an existing artifact source to map ATR gate percentile to known position signal timestamps in a future read-only extraction task, if Owner approves.
5. Ask Owner whether to authorize a future read-only feature-context extraction task keyed by existing `position_id` / `signal_id` / timestamp rows.

Not allowed by this audit:

- Immediate backtest.
- CPM-MOD-003.
- New gate.
- Parameter search.
- Runtime changes.
- New research adapter or strategy script.

---

## 9. Audit Classification

Audit result:

`ARTIFACT_CONTEXT_PARTIAL`

CPM-1 classification:

Unchanged: `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`.

Why unchanged:

- The audit found no evidence that favorable-year artifacts are unreliable.
- It confirmed that 2024 evidence is stronger than 2025.
- It confirmed that trade-level feature context is missing, so CPM-1 cannot be upgraded.
- It did not find enough negative artifact evidence to downgrade CPM-1 to reject.

---

## 10. Explicit Prohibitions

This audit does not authorize:

- backtests;
- strategy scripts;
- research adapters;
- parameter sweeps;
- CPM-MOD-003;
- CPM-2;
- E4 experiments;
- Pinbar variants;
- TP/SL changes;
- lower-timeframe timing rescue;
- funding/OI/liquidation rescue;
- router/regime/portfolio work;
- runtime interpretation;
- small-live interpretation.

---

## 11. Owner Summary

Are CPM-1 artifacts sufficient to study applicability further?

Partially. They are sufficient for an artifact-aware docs-only review, but not sufficient for a true feature-level applicability-boundary inspect under SRR-002.

Can 2024/2025 top-winner context be recovered?

Partially. Entry/exit, prices, PnL, close-event sequence, TP/SL events, and top-10 ATR gate percentile are recoverable. Per-position MFE/MAE/giveback, Donchian distance, slope, realized volatility, pullback depth, and event/data labels are not available.

Can 2023 failure context be recovered?

Partially. Position outcomes, close events, aggregate trade quality, and the fact that the ATR gate disabled zero baseline trades are recoverable. The per-entry feature explanation for why 2023 losing entries fell outside the ATR gate is not recoverable from current artifacts.

Is 2024 stronger evidence than 2025?

Yes. 2024 has stronger MOD-002 PnL, PF, winner count, and top-N survival. 2025 is more fragile because top-3 removal turns negative and some top winners are short-hold trades with unresolved event/artifact ambiguity.

Does CPM-1 classification remain unchanged?

Yes. CPM-1 remains `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`.

What should not be done next?

Do not run a backtest, create CPM-MOD-003, add a gate, tune CPM-1, create CPM-2, test E4, change TP/SL, use lower-timeframe rescue, add funding/OI/liquidation rescue, build router/regime/portfolio infrastructure, or infer runtime/small-live readiness.

Next legitimate docs-only step:

Create a compact CPM-1 artifact map that records artifact families, schemas, metric semantics, and missing fields, or ask Owner whether to authorize a future read-only feature-context extraction task. The latter would still not authorize strategy execution or a new gate.

CPM-1 remains non-runtime and non-small-live. This audit does not authorize any empirical run, parameter change, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
