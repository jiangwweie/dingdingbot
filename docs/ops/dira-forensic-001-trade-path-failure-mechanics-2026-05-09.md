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

# DIRA-FORENSIC-001 — Direction A Trade-Path / Failure Mechanics

## 0. Boundary

This is a read-only forensic diagnostic.

- No backtest was run.
- No adapter was run.
- No experiment was run.
- No parameter change was made.
- No entry or exit rule was changed.
- No exit rewrite was tested.
- No hypothetical strategy PnL was calculated.
- No threshold sweep was run.
- No runtime, profile, or risk change was made.
- No strategy code or backtester core was modified.
- No paper, testnet, live, small-live, or runtime approval is made.
- No strategy validation claim is made.
- No Claude task card was created.

All cluster and path reads below are descriptive summaries of already generated trade artifacts. They are not new trading rules.

## 1. Data / Artifacts Read

Docs read:

- `docs/ops/signal-refresh-001-direction-a-human-gated-candidate-review-2026-05-09.md`
- `docs/ops/strategy-direction-pivot-2026-05-09.md`
- `docs/ops/direction-a-btc-eth-phase1-owner-review-2026-05-09.md`
- `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md`
- `docs/ops/direction-a-phase1-btc-eth-aggregate-diagnostic.md`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `docs/ops/direction-a-p2-risk-shape-diagnostic.md`
- `docs/ops/direction-a-risk-control-return-frontier.md`
- `docs/ops/direction-a-same-risk-capital-efficiency-comparison.md`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `docs/ops/nsc-018-ea-rejection-direction-a-next-decision-closure-review.md`
- `docs/ops/vei-003-volatility-expansion-impulse-participation-level3-research-report.md`

Trade/result artifacts read:

- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/summary.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_result.json`
- `reports/te-007a-direction-a-official-validation-rerun-20260507/summary.json`
- `reports/direction-a-sparse-trend-evidence-hardening/top_winner_attribution_summary.md`
- `reports/direction-a-p1-edge-source-attribution/random_entry_control.md`

## 2. Trade Data Availability

Available trade-level artifacts:

| Asset | Artifact | Window | Trades | Fields available |
|---|---|---:|---:|---|
| ETH | `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl` | 2021-01-01 to 2025-12-31 | 173 | entry/exit timestamps, signal timestamp, entry/exit raw and executed prices, initial stop, exit reason, net/gross PnL, fees, slippage, funding, MFE, MAE, max giveback, hold hours, year |
| BTC | `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.jsonl` | 2021-01-01 to 2025-12-31 | 159 | same practical field set as ETH |
| SOL | `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.jsonl` | 2021-01-01 to 2025-12-31 with documented 2022 data gaps | 158 | same practical field set as ETH |

Also available:

- TE-007A rerun summary includes ETH base and supplemental window metrics.
- Top-winner attribution summary includes ETH top winners/losers, MFE/MAE, giveback, top-N removal, and exit reason distribution.
- BTC+ETH aggregate docs provide combined year-level and top-N summaries.

Missing or caveated:

- Exact BTC+ETH portfolio-level equity timing is not fully reconstructible from standalone docs alone without additional portfolio simulation. This report does not reconstruct it.
- A1/A3 risk-shaped trade count and time-in-market remain inconsistent across docs/artifacts: 490 and about 38% in Phase 1 docs versus 373 and 52.26% in risk frontier JSON.
- No new candle path reconstruction was performed. MFE/MAE/giveback were read from existing trade artifacts.

## 3. Year / Regime Loss Concentration

BTC+ETH year totals from existing ETH and BTC trade artifacts:

| Year | Trades | Winners / losers | Net PnL | Read |
|---|---:|---:|---:|---|
| 2021 | 66 | 16 / 50 | +1,015.92 | Positive but still many losing trades |
| 2022 | 67 | 10 / 57 | -898.56 | Main negative bear/chop year |
| 2023 | 59 | 16 / 43 | +3,326.86 | Strong positive; still contains loss clusters |
| 2024 | 65 | 18 / 47 | +2,384.81 | Strong positive; still contains post-winner loss clusters |
| 2025 | 75 | 14 / 61 | -310.21 | Negative / churn year |

Per-asset year pattern:

| Asset | Positive years | Negative years |
|---|---|---|
| ETH | 2021, 2023, 2024 | 2022, 2025 |
| BTC | 2021, 2023, 2024 | 2022, 2025 |
| SOL | 2021, 2023, 2024 | 2022, 2025 |

Answer to concentration questions:

- Yes, 2022 and 2025 are the main negative periods across BTC+ETH and across all three inspected assets.
- Yes, 2021, 2023, and 2024 are the main positive periods.
- The broad year-level pattern is human-gating-friendly in theory: obvious bear/chop periods would be good candidates for OFF decisions.
- However, losses are not confined to negative years. Positive years also contain large loss clusters between or after major winners.
- Therefore human ON/OFF could plausibly help, but it cannot simply turn on for "bull years" and expect the loss clusters to disappear.

## 4. False Breakout / Re-entry Cluster Read

Cluster lens used for this read:

- Consecutive losing trades by asset in entry order.
- Also a descriptive loss-only cluster view: losing trades separated by <=30 calendar days, reset by a winner.
- This is a reporting lens only, not a proposed rule.

### ETH clusters

Largest consecutive losing streaks:

| Count | PnL | Period | Years |
|---:|---:|---|---|
| 14 | -682.25 | 2024-12-12 to 2025-04-21 | 2024-2025 |
| 14 | -410.92 | 2022-07-28 to 2022-10-14 | 2022 |
| 9 | -400.19 | 2024-03-25 to 2024-05-16 | 2024 |
| 9 | -370.35 | 2023-06-30 to 2023-10-16 | 2023 |
| 9 | -290.14 | 2025-10-20 to 2025-12-29 | 2025 |

Worst descriptive loss-only clusters:

| Count | PnL | Period | Years |
|---:|---:|---|---|
| 14 | -682.25 | 2024-12-12 to 2025-04-21 | 2024-2025 |
| 8 | -573.56 | 2025-05-22 to 2025-07-04 | 2025 |
| 14 | -410.92 | 2022-07-28 to 2022-10-14 | 2022 |
| 9 | -400.19 | 2024-03-25 to 2024-05-16 | 2024 |
| 9 | -370.35 | 2023-06-30 to 2023-10-16 | 2023 |

### BTC clusters

Largest consecutive losing streaks:

| Count | PnL | Period | Years |
|---:|---:|---|---|
| 11 | -606.48 | 2023-07-10 to 2023-09-27 | 2023 |
| 11 | -288.61 | 2021-04-26 to 2021-07-12 | 2021 |
| 10 | -563.75 | 2025-10-21 to 2025-12-29 | 2025 |
| 9 | -395.76 | 2022-04-19 to 2022-07-11 | 2022 |
| 8 | -245.87 | 2021-11-15 to 2022-01-26 | 2021-2022 |

Worst descriptive loss-only clusters:

| Count | PnL | Period | Years |
|---:|---:|---|---|
| 11 | -606.48 | 2023-07-10 to 2023-09-27 | 2023 |
| 10 | -563.75 | 2025-10-21 to 2025-12-29 | 2025 |
| 9 | -395.76 | 2022-04-19 to 2022-07-11 | 2022 |
| 6 | -342.32 | 2025-02-20 to 2025-04-03 | 2025 |
| 4 | -312.89 | 2024-11-29 to 2025-01-07 | 2024-2025 |

### SOL context

SOL is not current Phase 1, but it confirms the same broad failure shape:

| Count | PnL | Period | Years |
|---:|---:|---|---|
| 10 | -484.58 | 2025-10-20 to 2025-12-29 | 2025 |
| 7 | -442.01 | 2025-02-09 to 2025-04-02 | 2025 |
| 7 | -354.59 | 2023-01-29 to 2023-03-30 | 2023 |
| 7 | -287.25 | 2022-07-28 to 2022-10-07 | 2022 |

### Cluster interpretation

Direction A losses are meaningfully clustered. The clusters look like repeated breakout attempts that fail before the next major trend leg, especially in:

- 2022 bear/chop periods.
- 2025 churn periods.
- Mid-2023 and post-Q1 2024 pauses inside otherwise positive years.

Human gating plausibility:

- A human ON/OFF process could plausibly avoid some 2022 and late-2025 clusters if the operator correctly identifies broad bear/chop conditions.
- It is less clear that a human could avoid BTC 2023 Jul-Sep, ETH 2023 Jun-Oct, or ETH 2024 Mar-May ex ante without also risking missing the next major trend leg.
- The worst failure mode is psychological: turning off after a loss cluster may protect capital, but it may also miss the next sparse winner if the operator is late to re-enable.

## 5. Top Winner / Payoff Tail Read

### ETH top winners

| Rank | Period | Hold | Net PnL | MFE | MAE | Giveback | Exit |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | 2024-02-06 to 2024-03-14 | 884h | +1,373.64 | +1,646.45 | -24.69 | 239.42 | EMA60 close-break |
| 2 | 2025-07-08 to 2025-08-01 | 556h | +1,036.73 | +1,301.74 | -20.27 | 238.76 | EMA60 close-break |
| 3 | 2023-01-02 to 2023-01-25 | 544h | +1,035.21 | +1,468.55 | -30.58 | 395.40 | EMA60 close-break |
| 4 | 2021-01-02 to 2021-01-11 | 208h | +533.65 | +1,048.74 | -26.67 | 506.89 | EMA60 close-break |
| 5 | 2023-10-20 to 2023-11-14 | 608h | +515.77 | +776.87 | -31.35 | 235.61 | EMA60 close-break |

### BTC top winners

| Rank | Period | Hold | Net PnL | MFE | MAE | Giveback | Exit |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | 2023-10-16 to 2023-11-14 | 716h | +1,303.82 | +1,889.96 | -7.39 | 531.36 | EMA60 close-break |
| 2 | 2023-01-09 to 2023-02-05 | 664h | +1,138.30 | +1,411.64 | -5.21 | 234.17 | EMA60 close-break |
| 3 | 2024-02-26 to 2024-03-15 | 420h | +762.97 | +1,072.27 | -4.85 | 286.60 | EMA60 close-break |
| 4 | 2024-02-07 to 2024-02-24 | 388h | +549.44 | +763.34 | -0.01 | 186.44 | EMA60 close-break |
| 5 | 2021-02-02 to 2021-02-23 | 488h | +428.06 | +613.41 | -10.71 | 176.10 | EMA60 close-break |

Top-winner implications:

- Top winners are multi-week lifecycle holds, typically 208h to 884h in ETH and 388h to 716h in BTC.
- All listed top winners exit through `ema60_close_break_next_open`.
- Winners tolerate meaningful giveback but still retain most of their peak MFE. Existing ETH top-winner docs show top-10 winner giveback ratios from 14.5% to 48.3%, retaining roughly 52%-85% of peak unrealized profit.
- The EMA60 lifecycle exit appears central to preserving payoff tails.
- NSC-018 / E-A is decisive context: a naive early-exit overlay improved many weak trades but worsened total net, PF, win rate, drawdown, and top-N fragility because it cut major winners.

## 6. Exit Timing Read

Classification: **PAYOFF_ENGINE**.

Direction A's exit is best understood as the payoff engine, not as a clearly too-early or too-late defect.

Evidence:

- ETH top-10 winners all exit through EMA60 close-break.
- ETH EMA60 close-break exits are 166 trades and +3,829.03 net PnL; initial-stop exits are 7 trades and -827.37 net PnL.
- BTC EMA60 close-break exits are 152 trades and +3,310.26 net PnL; initial-stop exits are 7 trades and -793.09 net PnL.
- SOL shows the same pattern: EMA60 exits +4,680.36; initial stops -661.56.
- Tested early-exit overlay E-A was rejected because it overfiltered and damaged the sparse payoff tail.

Is exit-quality diagnostic justified?

Answer: **WEAK_CONDITIONAL**, but not as an exit rewrite search.

The exact forensic question should be:

> In existing Direction A trades, which realized loss clusters are caused by repeated failed breakouts after trend exhaustion, and which realized winners require uninterrupted EMA60 lifecycle holding to preserve the payoff tail?

It should not ask:

- What alternate exit would improve PnL?
- Which EMA period is better?
- Which threshold avoids the clusters?
- How to rewrite the strategy?

The current evidence argues that naive earlier exits are dangerous. If future exit-quality work is authorized, it should be a path and failure-mechanics audit, not an alternate-exit test.

## 7. Human-Gated Plausibility

Answer: **WEAK**.

What human gating might improve:

- Avoid obvious bear/chop stretches like much of 2022 and late-2025.
- Avoid turning Direction A on during periods where repeated false breakouts are already visible.
- Add macro/news/funding/sentiment context that OHLCV-only Direction A does not have.
- Let LLM briefing support Owner judgment by summarizing risk events and arguing against confirmation bias.

What human gating cannot fix:

- It cannot remove top-winner dependence.
- It cannot identify every false breakout before the trade.
- It cannot guarantee re-entry after a loss cluster before the next large winner.
- It cannot transform Direction A into a validated pre-observable applicability-boundary system.
- It cannot prove that future bull windows will contain the same Direction A payoff-tail episodes.

Are bad periods obvious enough ex ante?

- Some are plausibly obvious: 2022 broad bear/chop and late-2025 deterioration.
- Some are not obviously avoidable: BTC 2023 Jul-Sep loss cluster, ETH 2023 Jun-Oct loss cluster, and ETH 2024 Mar-May post-winner cluster occur inside otherwise positive years.

Human gating risk:

- The main risk is psychological/timing error: turning off after pain and failing to turn back on before sparse trend winners.
- LLM briefing can support the decision process, but it must not replace Owner judgment or become automatic runtime control.

## 8. Candidate Status

Status: **REMAIN_WEAK_BEST_AVAILABLE**.

Reasoning:

- Forensic review strengthens the understanding of Direction A failure mechanics, but does not upgrade validation status.
- Direction A remains better supported than CPM-1 for human-gated execution-signal consideration.
- The payoff-tail mechanism is coherent: many small failed breakouts are paid for by rare multi-week trend holds.
- But the top-winner dependence, loss clusters inside positive years, and lack of pre-observable applicability boundary remain unresolved.

Not upgraded because:

- No new validation evidence was produced.
- No human-gating decision process has been tested.
- No paper/testnet/live or runtime candidate exists.
- No pre-observable boundary exists.

## 9. Recommended Next Step

Recommended next step: **HUMAN_GATING_DECISION_PROCESS_DRAFT_NEXT**.

Why:

- This forensic read suggests the central unresolved question is not "which exit should replace EMA60?" but "when would the Owner turn Direction A on/off without damaging access to sparse payoff tails?"
- A docs-only human-gating decision-process draft can define what evidence the Owner would review, what warnings matter, what would trigger hesitation, and how to avoid turning off after losses and missing the next major trend.
- This should remain a decision-process draft only. It must not implement runtime control, LLM automation, or order behavior.

Secondary option:

- A later exit/path forensic diagnostic remains **WEAK_CONDITIONAL** if explicitly authorized, but it should be narrower than "exit improvement": it should inspect path mechanics around loss clusters and payoff-tail preservation using existing trades.

## 10. What Not To Infer

- No live readiness.
- No paper/testnet approval.
- No runtime activation.
- No parameter approval.
- No exit logic change.
- No LLM implementation approval.
- No human on/off runtime control approval.
- No small-live approval.
- No claim that Direction A beats spot in the future bull window.
- No claim that Direction A is validated.
- No claim that human gating can reliably remove bad periods.

