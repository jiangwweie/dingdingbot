# CPM-1 Favorable-Regime Attribution Review

**Task ID:** CPM-1-FAVORABLE-REGIME-ATTRIBUTION-REVIEW  
**Date:** 2026-05-08  
**Status:** Completed / docs-only attribution review  
**Scope:** Report-only review of CPM-1 as a conditional pullback-continuation research object  
**Affects Runtime Automatically:** No

---

## 0. Boundary

This review is not CPM rescue, not parameter tuning, not a strategy variant, not a runtime readiness review, and not a small-live admission review.

No backtest, research adapter, strategy script, parameter sweep, CPM rule change, CPM-MOD-003, E4 hard or soft experiment, TP/SL change, Pinbar variant, lower-timeframe timing rescue, funding/OI/liquidation rescue, runtime/profile/risk/backtester-core change, router, portfolio allocator, or regime engine is authorized by this report.

This review uses existing documents and artifacts only. Where artifacts are missing, the gap is reported rather than filled by new empirical work.

---

## 1. Source Inventory Inspected

Primary current docs inspected:

| Source | Role in this review |
| --- | --- |
| `docs/ops/crypto-pullback-module-v1-scope-note.md` | CPM-1 identity, frozen baseline, 2023/2024/2025 headline evidence |
| `docs/ops/crypto-pullback-module-v1-evidence-interpretation-note.md` | Evidence hierarchy, caveats, source registry |
| `docs/ops/crypto-pullback-module-v1-2021-oos-report.md` | 2021 OOS metrics and loss structure |
| `docs/ops/crypto-pullback-module-v1-2022-oos-report.md` | 2022 OOS metrics and cost structure |
| `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md` | 2021/2022 failure classification |
| `docs/ops/cpm-mod-001-cpm1-applicability-dynamic-enablement-inspect.md` | Conditional enablement framing and unresolved questions |
| `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md` | Frozen ATR-percentile diagnostic and attribution |
| `docs/ops/crypto-pullback-module-v1-promotion-rejection-criteria.md` | Promotion/pause/rejection governance |
| `docs/ops/sma-001-strategy-module-applicability-map.md` | Current strategy map and CPM-1 classification |
| `docs/ops/srr-001-strategy-research-reset-evidence-state-review.md` | Evidence-state reset and no-runtime-candidate baseline |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Accepted methodology and applicability-boundary standard |

Additional artifacts inspected:

| Source | Role |
| --- | --- |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/summary.json` | Year-by-year baseline/gated metrics, fragility, aggregate MFE/MAE/giveback |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2021_result.json` through `baseline_2025_result.json` | Existing per-year position and close-event artifacts |
| `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-29-eth-baseline-strategy-research-review-for-external-quant.md` | Archived official headline 2023/2024/2025 review |
| `archive/2026-04-29-pre-live-safe-replan/docs/planning/2023-failure-attribution-report.md` | 2023 failure attribution |
| `archive/2026-04-29-pre-live-safe-replan/docs/planning/2026-04-28-eth-baseline-2023-rescue-research-closure.md` | H0-H3a rescue closure |
| `archive/2026-04-29-pre-live-safe-replan/artifacts/reports/research/strategy_ecology_m0_2026-04-28.json` | Existing ecology feature summaries |

Artifact caveat:

- Dedicated CPM-1 2024/2025 trade-level reports with per-trade market context, ATR percentile, Donchian distance, MFE, MAE, and event labels were not found.
- CPM-MOD-002 JSON artifacts contain positions, close events, and aggregate trade-quality metrics. They do not contain per-position MFE/MAE/giveback or per-position pre-entry feature rows.
- Therefore, top-winner attribution below is partial and artifact-bounded.

---

## 2. CPM-1 Identity

CPM-1 is Crypto Pullback Module v1:

| Dimension | Identity |
| --- | --- |
| Asset | ETH/USDT:USDT perpetual |
| Primary timeframe | 1h |
| Confirmation timeframe | 4h |
| Direction | LONG-only |
| Core thesis | Enter a pullback-ending moment inside an established uptrend and capture continuation |
| 1h role | Primary decision timeframe; Pinbar trigger identifies the possible end of the pullback |
| 4h role | Higher-timeframe trend confirmation through 4h EMA60 rising |
| Trend context | EMA50 with minimum distance on 1h plus 4h MTF confirmation |
| Exit geometry | TP1 1.0R 50%, TP2 3.5R 50%, SL at -1.0R, OCO, BE off, trailing off |

Pinbar is only the entry trigger. The strategy identity is not "Pinbar as a standalone pattern"; it is ETH 1h trend-pullback continuation with 4h confirmation. Pinbar supplies candle geometry for the pullback-ending moment, but the module's edge depends on the broader state: trend exists, pullback is a discount rather than reversal, and post-entry continuation is strong enough to reach TP1/TP2.

---

## 3. Positive Evidence

### 3.1 Archived Official Headline Evidence

The current CPM scope note and evidence interpretation note preserve the archived official headline performance:

| Year | PnL | Win rate | Sharpe | MaxDD | Read |
| --- | ---: | ---: | ---: | ---: | --- |
| 2024 | +8,501 USDT | 32.3% | 1.91 | 17.39% | Favorable-market evidence |
| 2025 | +4,490 USDT | 31.7% | 2.01 | 11.56% | Favorable-market evidence |
| 2026 Q1 | +777 USDT | Not found | Not found | Not found | Small forward/testnet sample; caveated |

Correct classification:

> 2024/2025 are favorable-market / applicable-market evidence, not deployment evidence.

They show that CPM-1 can work in some market states. They do not satisfy SRR-002 validated applicability-boundary requirements, do not overcome 2021/2022 OOS failure, and do not reopen small-live candidacy.

### 3.2 CPM-MOD-002 Baseline Artifacts

CPM-MOD-002 uses independent yearly fixed-balance diagnostic runs, so its PnL scale differs from the archived official headline series. It is still useful for attribution because it exposes positions, close events, fragility, and aggregate MFE/MAE/giveback.

| Year | Net PnL | PF | Win rate | Trades / winners | MTM MaxDD | Fragility read |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2024 | +850.61 | 1.96 | 59.09% | 44 / 26 | 5.02% | Top-5 removal still positive but only +72.37 position-level PnL |
| 2025 | +200.10 | 1.28 | 41.46% | 41 / 17 | 4.81% | Top-3 removal turns negative: -203.14 position-level PnL |

The favorable-year evidence is positive but not clean enough for deployment interpretation. 2024 is the stronger favorable-year artifact because it survives top-3 and top-5 removal. 2025 remains more fragile because top-3 removal turns negative.

### 3.3 Top-Winner Concentration

From CPM-MOD-002:

| Year | Top winner | Gross winner PnL | Top winner / gross wins | Top-3 removal | Top-5 removal |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | +182.23 | +1,978.01 | 9.21% | +426.87 | +72.37 |
| 2025 | +175.34 | +1,459.88 | 12.01% | -203.14 | -547.43 |

Top-1 concentration is not the main problem. The unresolved issue is dependence on a small group of favorable-year winners, especially in 2025.

---

## 4. Negative and Unresolved Evidence

### 4.1 2021 OOS Failure

| Metric | Value |
| --- | ---: |
| Total PnL | -2,153.76 USDT |
| Total return | -21.54% |
| MaxDD | 22.18% |
| Win rate | 29.5% |
| PF | 0.466 |
| Positions | 74 |
| Winning months | 3 / 12 |
| Gross PnL before costs | -573.84 USDT |
| Total cost drag | 1,579.93 USDT |
| Largest loss cluster | 16 consecutive losses, -1,079.84 USDT, Aug-Oct 2021 |

2021 is the most serious negative evidence because it was a bull year, yet CPM-1 lost money and had negative gross edge before costs. This is classified as favorable-regime profit hypothesis failure plus loss concentration.

### 4.2 2022 OOS Failure

| Metric | Value |
| --- | ---: |
| Total PnL | -971.71 USDT |
| Total return | -9.72% |
| MaxDD | 10.48% |
| Win rate | 31.1% |
| PF | 0.624 |
| Positions | 51 |
| Winning months | 0 / 12 |
| Estimated gross PnL before costs | +80.51 USDT |
| Estimated total cost drag | ~1,052.22 USDT |

2022 supports the bear-year failure hypothesis. It is more cost-dominated than 2021: the gross edge was marginally positive, but fees/slippage/funding consumed it.

### 4.3 2023 Failure / Unresolved Boundary

Archived official evidence reports:

| Year | PnL | Win rate | Sharpe | MaxDD |
| --- | ---: | ---: | ---: | ---: |
| 2023 | -3,924 USDT | 16.1% | -2.63 | 49.19% |

The 2023 failure attribution reports lower follow-through, higher SL event share, shorter holding duration, and weak continuation after entry. H0-H3a rescue research closed the parameter-rescue path: EMA coarse gates, SHORT mirror, Fibonacci limit entry, dynamic risk geometry, and pre-entry feature filtering all failed or imposed unacceptable 2024/2025 damage.

The unresolved issue is that CPM-MOD-002 did not explain 2023. Its ATR-percentile gate disabled 170.96 days of 2023 market time, but disabled zero actual baseline CPM-1 trades.

### 4.4 Why CPM-1 Is Still Not Runtime or Small-Live

CPM-1 remains non-runtime and non-small-live because:

- 2021 OOS directly challenges the favorable-regime profit hypothesis.
- 2022 OOS is negative.
- 2023 remains an unresolved failure boundary.
- CPM-MOD-002 explains only a narrow 2021-style high-volatility damage cluster.
- Favorable-year evidence remains partly concentrated and in-sample.
- SRR-002 requires a validated pre-observable applicability boundary; CPM-1 does not have one.
- Existing evidence does not satisfy promotion criteria for coherent profit/failure hypothesis under current governance.

---

## 5. 2024/2025 Top-Winner Attribution

### 5.1 Artifact Limitations

Available:

- Entry timestamp, exit timestamp, holding duration, entry price, exit price, final exit reason, position-level realized PnL.
- Close events for TP1/TP2/SL where present.
- Aggregate yearly MFE/MAE/giveback from CPM-MOD-002.

Unavailable per top winner:

- Per-position MFE, MAE, and giveback.
- Per-position ATR percentile, realized volatility, 4h EMA slope, 1h pullback-state features, 72h/7d return, Donchian distance.
- Event-driven labels, news labels, or data-artifact labels.

Therefore, this section performs position-level attribution only where artifacts allow and treats market-context conclusions as incomplete.

### 5.2 2024 Top Winners from Existing CPM-MOD-002 Baseline Positions

| Rank | Position | Entry UTC | Exit UTC | Hold | Net PnL | Close-event read | Thesis fit read |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | `pos_da6c1071` | 2024-10-12 09:00 | 2024-10-25 23:00 | 326h | +182.23 | TP1 and TP2 close events present | Fits continuation mechanically; long hold after pullback signal |
| 2 | `pos_c335a330` | 2024-09-26 12:00 | 2024-09-30 02:00 | 86h | +180.77 | TP1 and TP2 close events present | Fits continuation mechanically; multi-day continuation |
| 3 | `pos_64e4fb64` | 2024-04-08 04:00 | 2024-04-12 17:00 | 109h | +179.42 | TP1 and TP2 close events present | Fits continuation mechanically; multi-day continuation |
| 4 | `pos_60617280` | 2024-09-19 02:00 | 2024-10-02 19:00 | 329h | +178.04 | Detailed close-event subset not inspected beyond top 3 | Likely continuation, but per-trade feature context missing |
| 5 | `pos_aeb535aa` | 2024-02-25 05:00 | 2024-04-13 19:00 | 1,166h | +176.46 | Detailed close-event subset not inspected beyond top 3 | Long lifecycle; thesis fit plausible but context missing |

2024 aggregate trade quality:

| Metric | Value |
| --- | ---: |
| Avg MFE | 876.16 |
| Avg MAE | -172.48 |
| Avg giveback | 844.90 |
| Winner avg MFE | 1,990.29 |
| Winner avg MAE | -269.56 |
| Winner avg giveback | 1,838.13 |

Interpretation: 2024 winners are consistent with the CPM pullback-continuation lifecycle at the artifact level: they hit continuation targets and the year retains positive PnL after top-5 removal. However, the large average giveback means this should not be interpreted as an exit-quality validation.

No existing artifact proves the top winners were event-driven. No existing artifact proves they were data-artifact-driven. The correct read is "not flagged by inspected artifacts," not "ruled out."

### 5.3 2025 Top Winners from Existing CPM-MOD-002 Baseline Positions

| Rank | Position | Entry UTC | Exit UTC | Hold | Net PnL | Close-event read | Thesis fit read |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | `pos_df74549a` | 2025-04-22 20:00 | 2025-04-22 21:00 | 1h | +175.34 | TP1 and TP2 close events in same hour | Continuation target hit, but very short hold; event/artifact ambiguity remains unclassified |
| 2 | `pos_eb90b5f1` | 2025-10-03 09:00 | 2025-10-07 23:00 | 110h | +175.15 | TP1 and TP2 close events present | Fits continuation mechanically |
| 3 | `pos_8199b51e` | 2025-05-08 12:00 | 2025-05-08 15:00 | 3h | +174.70 | TP1 and TP2 close events present | Continuation target hit, but short hold; context needed |
| 4 | `pos_eb98808d` | 2025-10-01 21:00 | 2025-10-09 15:00 | 186h | +173.32 | Detailed close-event subset not inspected beyond selected top rows | Fits continuation mechanically, context missing |
| 5 | `pos_2daf2e9f` | 2025-03-22 06:00 | 2025-03-28 04:00 | 142h | +170.98 | Detailed close-event subset not inspected beyond selected top rows | Fits continuation mechanically, context missing |

2025 aggregate trade quality:

| Metric | Value |
| --- | ---: |
| Avg MFE | 179.14 |
| Avg MAE | -120.09 |
| Avg giveback | 169.39 |
| Winner avg MFE | 466.12 |
| Winner avg MAE | -140.33 |
| Winner avg giveback | 303.91 |

Interpretation: 2025 has several mechanically thesis-consistent TP2 winners, but the year is fragile: removing the top 3 winners turns position-level PnL negative. The short-duration top winners should be treated as requiring future docs-only artifact review if trade context artifacts are later found. They are not enough to downgrade CPM-1 by themselves, but they weaken confidence relative to 2024.

---

## 6. Good vs Bad Regimes

### 6.1 Existing Feature Evidence

From M0 ecology and CPM-MOD-001:

| Feature | Existing read |
| --- | --- |
| ATR percentile | 2023 around 0.625 vs 2024/2025 around 0.531 in CPM-MOD-001; volatility is the cleanest year-level clue |
| Realized volatility | High realized volatility is associated with worse CPM-1 outcomes in M0 |
| 4h EMA slope | Strong trade-level diagnostic, but poor year-level separator; 2023 slope was not higher than 2024/2025 |
| Recent 72h return | Strong trade-level diagnostic; high recent return is adverse; year-level separation is weak |
| Donchian distance | Strong risk-state clue; E4 failed as hard gate under official validation because it over-filtered |
| Price near highs | Existing docs classify near-Donchian-top / recent-high state as adverse |
| Pullback depth | Existing artifacts do not provide a clean per-trade pullback-depth attribution |
| Post-entry continuation | 2023 had weak continuation, high SL share, and much shorter average final holding duration than 2024/2025 |
| Cost drag | 2021 and 2022 OOS both had large cost drag; 2021 gross edge was already negative, 2022 was cost-dominated |
| Trade density | 2021 produced more entries and larger losses than 2022; MOD-002 2023 had only 20 trades and 5 winners |

### 6.2 Good-Regime Read

2024/2025 favorable states appear to share:

- Moderate or lower volatility at CPM entry times.
- 4h trend confirmation sufficient for continuation.
- Pullback signals that continue far enough to reach TP1/TP2.
- Better TP event distribution than 2023 in archived attribution.
- Lower drawdown in favorable-year artifacts.

This is compatible with "gentle, low-volatility uptrend continuation," but it is not a validated pre-observable boundary.

### 6.3 Bad-Regime Read

2021/2023 failure states include different failure modes:

- 2021: nominal bull year, but high-slope/high-volatility sub-regimes, aggressive corrections, EMA lag, and clustered losses. CPM-MOD-002 partially removed high-volatility 2021 damage.
- 2022: bear-market LONG-only failure with cost-dominated net loss.
- 2023: weak continuation and high SL share, but the frozen ATR-percentile gate did not intersect actual CPM-1 entries.

The key distinction is that 2021 is partly volatility-explained, while 2023 remains boundary-unexplained.

---

## 7. CPM-MOD-002 Interpretation

CPM-MOD-002 tested one frozen module-level volatility gate:

- Feature: 1h ATR14 rolling percentile over prior 90 days.
- Threshold: disable CPM-1 when rolling ATR percentile > 0.60.
- Semantics: module-level no-new-entry gate; existing positions continue under baseline lifecycle.

Results:

| Year | Baseline PnL | Gated PnL | Delta | Disabled baseline trades |
| --- | ---: | ---: | ---: | ---: |
| 2021 | -1,992.49 | -1,059.11 | +933.37 | 37 |
| 2022 | -763.72 | -763.72 | 0.00 | 0 |
| 2023 | -785.24 | -785.24 | 0.00 | 0 |
| 2024 | +850.61 | +850.61 | 0.00 | 0 |
| 2025 | +200.10 | +200.10 | 0.00 | 0 |

What it explains about 2021:

- It identifies and avoids a net-negative 2021 high-volatility trade cluster.
- It reduces 2021 MTM MaxDD from 22.18% to 10.59%.
- It supports a narrow "high-volatility can damage CPM-1" hypothesis.

Why it preserves 2024/2025:

- It disabled many high-volatility market periods in 2024/2025 but disabled zero actual CPM-1 baseline entries.
- Therefore, preservation is real in the artifact, but it is not proof that all favorable 2024/2025 entries are structurally valid under a complete boundary.

Why it does not explain 2023:

- It disabled 170.96 days in 2023 but zero actual CPM-1 entries.
- 2023 losses occurred outside the frozen ATR > 0.60 entry-disable condition.
- The 2023 invalid state is therefore not captured by this single volatility boundary.

Classification of CPM-MOD-002 evidence:

| Possible classification | Read |
| --- | --- |
| Validated boundary | No |
| Partial hypothesis | Yes |
| Post-hoc evidence | Yes; SRR-002 post-hoc penalty applies because the boundary was motivated after year-level results were known |
| Insufficient evidence | Insufficient for dynamic enablement; sufficient only to preserve a narrow research clue |

Required framing:

> CPM-MOD-002 strengthens a narrow volatility-damage hypothesis but does not validate CPM-1 dynamic enablement.

---

## 8. Applicability Questions Remaining

Open questions that remain research questions only:

1. Is CPM-1 valid only in moderate-trend / moderate-volatility continuation regimes?
2. Is high ATR the main invalid state, or only a 2021-style invalid state?
3. Why does 2023 fail if the ATR-percentile gate does not exclude its actual CPM-1 entries?
4. Does CPM-1 require trend slope, volatility, and price-location conditions together rather than any single feature?
5. Are 2024/2025 winners structurally related to pullback continuation, or are they partly trend beta / overlap with broader ETH directional moves?
6. Can valid and invalid states be described before the trade without selecting years after seeing performance?
7. Are short-hold 2025 top winners normal continuation captures, event-driven moves, or bar-level artifacts?
8. Does favorable-year top-N fragility, especially 2025 top-3 removal, imply pause-fragile rather than conditional-edge preservation?
9. Is the 2021 failure fully explainable by volatility, or are there non-volatility hostile states inside bull markets?
10. Can CPM-1's "gentle uptrend" condition be described in a way that satisfies SRR-002 without creating a post-hoc no-trade gate?

No new rule is proposed here. These are applicability-boundary questions, not gates.

---

## 9. Classification

Final classification:

`CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`

Rationale:

- 2024/2025 favorable-market evidence is positive and mostly thesis-consistent at the artifact level.
- 2024 survives top-5 removal in CPM-MOD-002 attribution.
- CPM-MOD-002 preserves 2024/2025 while improving one 2021 damage cluster.
- Negative evidence is too serious for runtime or small-live: 2021 OOS, 2022 OOS, unresolved 2023, and 2025 fragility.
- There is no validated pre-observable applicability boundary under SRR-002.
- The inspected artifacts do not show that 2024/2025 gains are purely accidental, event-driven, or data-artifact-driven, but they also do not prove a validated structural boundary.

This classification preserves CPM-1 as research evidence only. It does not reopen CPM-1 as a candidate.

Downgrade triggers for future docs-only review, if existing artifacts later support them:

- Top 2024/2025 winners are shown to be data artifacts.
- Top 2024/2025 winners are shown to be unrelated event windfalls rather than pullback continuation.
- A full trade-level attribution shows favorable-year gains are trend beta with no CPM-specific pullback contribution.
- 2025-style top-N fragility dominates after consistent artifact normalization.

---

## 10. Explicit Prohibitions

This task does not authorize:

- CPM-1 parameter changes.
- CPM-MOD-003.
- CPM-2.
- E4 hard gate.
- E4 soft label experiment.
- Pinbar variants.
- TP/SL changes.
- 15m or 1h timing rescue.
- Funding/OI/liquidation rescue.
- Router work.
- Regime-engine work.
- Portfolio work.
- Runtime interpretation.
- Small-live interpretation.
- Any empirical run without separate Owner approval.

---

## 11. Owner Summary

Is CPM-1 worth preserving?

Yes, as a conditional edge / applicability-boundary research object only. It is not worth preserving as a runtime candidate or small-live candidate.

Is 2024/2025 evidence structurally meaningful?

Partially. The evidence is structurally meaningful enough to preserve because the favorable-year winners generally fit the pullback-continuation lifecycle and 2024 survives top-N fragility better than many rejected candidates. It is not structurally complete because 2021 and 2023 show that "uptrend + pullback + Pinbar + 4h confirmation" is not a sufficient applicability boundary.

Strongest positive evidence:

- Archived official 2024/2025 performance: +8,501 / +4,490 USDT with Sharpe around 1.9-2.0.
- CPM-MOD-002 preserved 2024/2025 entirely while improving 2021 by +933.37.
- 2024 CPM-MOD-002 attribution remains positive after top-5 removal.

Strongest negative evidence:

- 2021 OOS lost -2,153.76 USDT in a bull year with negative gross edge before costs.
- 2022 OOS was negative and cost-dominated.
- 2023 remains unexplained by CPM-MOD-002 and had severe archived MaxDD.
- 2025 turns negative after top-3 winner removal in CPM-MOD-002 attribution.

Exact applicability questions still open:

- What pre-observable state separates valid gentle continuation from invalid correction/reversal?
- Why did 2023 entries occur outside the ATR > 0.60 invalid state yet still fail?
- Are volatility, slope, and price-location jointly required?
- Are favorable-year top winners CPM-specific or broad trend beta?
- Can a boundary be stated before the trade and survive SRR-002 without post-hoc fitting?

What should not be done next:

- Do not tune CPM-1.
- Do not add another gate.
- Do not run CPM-MOD-003.
- Do not test E4 hard/soft labels.
- Do not build CPM-2, lower-timeframe rescue, funding/OI rescue, router, portfolio, or regime infrastructure from this review.
- Do not reinterpret 2024/2025 as deployment evidence.

Next legitimate docs-only step, if Owner wants one:

- A no-run artifact audit that normalizes existing CPM-1 trade artifacts across archived official runs and CPM-MOD-002 diagnostics, specifically to reconcile metric scales, locate any missing 2024/2025 trade-level feature rows, and document whether top-winner market context can be recovered without executing new backtests.

CPM-1 remains non-runtime and non-small-live. This review preserves or downgrades research evidence only. Any future empirical run requires separate Owner approval and must satisfy SRR-002.
