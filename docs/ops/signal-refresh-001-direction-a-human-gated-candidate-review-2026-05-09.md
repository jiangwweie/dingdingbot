# SIGNAL-REFRESH-001 — Direction A Human-Gated Candidate Review

## 0. Boundary

This is a read-only evidence review.

- No backtest was run.
- No adapter was run.
- No experiment was run.
- No parameter change was made.
- No entry or exit rule was created.
- No runtime, profile, or risk change was made.
- No strategy code or backtester core was modified.
- No paper, testnet, live, small-live, or runtime activation is approved.
- No human on/off runtime control is approved.
- No LLM implementation is approved.
- No strategy edge is claimed beyond existing documented evidence.
- No Claude task card was created.

## 1. Data / Docs Read

Primary docs read:

- `docs/ops/strategy-direction-pivot-2026-05-09.md`
- `docs/ops/cpm-bull-segment-readonly-evidence-2026-05-09.md`
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
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/project-control-board.md`

Artifacts read:

- `reports/te-007a-direction-a-official-validation-rerun-20260507/summary.json`
- `reports/direction-a-risk-control-return-frontier/risk_control_return_frontier.json`

Artifact caveats:

- Direction A trade-level artifacts exist locally, but this review did not reprocess trade files or compute new metrics.
- The current control docs report unresolved A1/A3 metric conflicts: Phase 1 docs cite 490 trades and about 38% time in market, while risk frontier JSON cites 373 trades and 52.26% time in market for A1/A3. This report preserves the conflict and does not infer a corrected value.

## 2. Direction A Identity

Direction A is a 4h main-trend lifecycle capture signal.

| Dimension | Direction A identity from existing docs |
|---|---|
| Primary assets | ETH/USDT:USDT baseline; BTC/USDT:USDT and SOL/USDT:USDT cross-asset diagnostics exist. Current Phase 1 focus is BTC+ETH only. |
| Timeframe | 4h OHLCV. |
| Direction | Long-only trend participation. No short-side Direction A path is active. |
| Entry | Donchian20 close breakout: fully closed 4h candle close above the previous 20 closed 4h high / channel. |
| Entry execution | Next 4h bar open after signal close, plus 0.1% entry slippage. |
| Initial stop | Previous 20 closed 4h low, signal bar excluded; fixed initial stop, no trailing. |
| Exit | Fully closed 4h candle close below EMA60. |
| Exit execution | Next 4h bar open after EMA60 close-break, less 0.1% exit slippage. |
| Cost model | fee_rate 0.0004, entry slippage 0.001, exit slippage 0.001, funding 0.0001 per 8h. |
| Same-bar policy | Initial stop checked before same-bar EMA close-break trigger; intrabar EMA touch ignored. |
| Conceptual type | Donchian/EMA trend-following / smart-beta trend timing. |
| BTC+ETH aggregation | Yes. BTC+ETH Phase 1 docs aggregate ETH and BTC evidence and exclude SOL from current mainline. |

Direction A is not a CPM pullback signal. It is a breakout/lifecycle trend signal: enter on confirmed 4h range breakout, stay in while EMA60 lifecycle remains intact, exit after a closed-bar EMA60 break.

## 3. Existing Evidence Summary

### ETH baseline / TE-007A

ETH Direction A base window evidence:

| Metric | Value |
|---|---:|
| Window | 2021-01-01 to 2025-12-31 |
| Trades | 173 |
| Winners / losers | 34 / 139 |
| Win rate | 19.65% |
| Net PnL | +3,001.66 |
| Gross PnL before costs | +4,102.71 |
| Profit factor | 1.517 |
| Realized MaxDD | 6.08% |
| MTM MaxDD | 8.33% |
| Avg winner / avg loser payoff ratio | 6.20:1 |
| Top-1 removal | +1,628.03 |
| Top-3 removal | -443.91 |
| Top-5 removal | -1,493.33 |
| Classification | PAUSE / PAUSE_FRAGILE |

TE-007A supplemental window:

- 2020 supplemental: 37 trades, +2,530.14 PnL, PF 3.453.
- Supplemental window is documented as broadly consistent with the base direction.
- Final TE-007A classification remains PAUSE because top-3 removal drops net PnL below zero.

### Cross-asset frozen diagnostic

| Asset | Trades | Winners / losers | Win rate | Net PnL | PF | Realized MaxDD | MTM MaxDD | Read |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ETH | 173 | 34 / 139 | 19.65% | +3,001.66 | 1.517 | 6.08% | 8.33% | Positive sparse trend evidence |
| BTC | 159 | 40 / 119 | 25.16% | +2,517.17 | 1.477 | 9.95% | 11.32% | Positive but fragile |
| SOL | 158 | 44 / 114 | 27.85% | +4,018.80 | 1.790 | 4.49% | 6.44% | Positive but high-beta contamination risk |

Current strategy refresh focus is BTC+ETH, not SOL.

### BTC+ETH Phase 1 aggregate

| Metric | BTC+ETH value |
|---|---:|
| Trades | 332 |
| Winners / losers | 74 / 258 |
| Win rate | 22.29% |
| Net PnL | +5,518.83 |
| Profit factor | 1.50 |
| ETH contribution | +3,001.66, 54.4% of BTC+ETH net |
| BTC contribution | +2,517.17, 45.6% of BTC+ETH net |
| Time in market | about 38.5% in Phase 1 doc |

Year-by-year BTC+ETH:

| Year | BTC net | ETH net | Combined net | Read |
|---|---:|---:|---:|---|
| 2021 | +293.35 | +722.57 | +1,015.92 | Both positive |
| 2022 | -821.76 | -76.80 | -898.56 | Bear/chop vulnerability |
| 2023 | +2,407.94 | +918.93 | +3,326.87 | Primary positive year |
| 2024 | +919.06 | +1,465.75 | +2,384.81 | Strong positive year |
| 2025 | -281.43 | -28.79 | -310.22 | Vulnerability / cost-chop year |

The Owner-stated "BTC+ETH PF 1.752" is repo-confirmed, but it applies to conservative risk-shaped A1/A3 scenarios, not the unshaped BTC+ETH baseline. Existing docs record:

| Scenario | Net on 30k | Return | MaxDD | PF | Top-5 after removal | 2023 contribution |
|---|---:|---:|---:|---:|---:|---:|
| A1 low vol-normalized + max 2 | +4,324.46 | 14.4% | 2.6% | 1.752 | +297.71 | +2,677.88 |
| A3 hybrid 0.50% vol-adjusted + max 2 | +8,648.92 | 28.8% | 5.1% | 1.752 | +595.42 | +5,355.77 |

Caveat: A1/A3 trade count and time-in-market differ across docs/artifacts. Phase 1 docs cite 490 trades and about 38% time in market; risk frontier JSON cites 373 trades and 52.26% time in market. This needs reconciliation before any stable observation template.

### Evidence quality classifications

- Current Direction A consolidated state: `CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`.
- P0: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`.
- P1: `P1_MIXED_EDGE_SOURCE`.
- P2: `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`.
- Current roadmap/control board: docs-only / shadow-no-order observation object, not runtime, paper, testnet, live, or small-live.

## 4. Bull-Cycle Suitability Read

Direction A is more aligned with the Owner's 2-3 year bull-cycle objective than CPM-1, but it remains weak as a validated execution signal.

Positive suitability evidence:

- It directly targets major trend legs through Donchian20 breakout and EMA60 lifecycle hold.
- ETH top winners include 2021-Q1, 2023-Q1, 2023-Q4, 2024-Q1, and 2025-Q3 trend episodes.
- BTC and ETH are both positive under the same frozen 4h mechanism.
- BTC+ETH combined years 2021, 2023, and 2024 are positive, while CPM-BULL-SEG-001 found CPM-1 negative in 2021 Q1 and 2021 Jan-Apr.
- Existing docs classify Direction A as smart-beta trend timing rather than pure entry alpha; this fits a human-gated bull-cycle architecture better than a local pullback pattern.

Material limitations:

- Direction A has no validated pre-observable applicability boundary under SRR-002.
- It is still regime-blind if run mechanically across all periods: 2022 and 2025 are negative for BTC+ETH.
- Top-winner and shared-episode concentration remain binding. BTC+ETH unshaped top-3 and top-5 removal are negative.
- P0 winner overlap shows effective independent evidence is much lower than raw trade count.
- Existing same-risk comparisons support capital efficiency under historical assumptions, but do not prove future bull-window edge.

Late entry / early exit / re-entry:

- Late entry is structurally present: a Donchian20 breakout waits for a 20-bar high/close breakout, so it will not catch early trend starts.
- Early exit is plausible but not proven as a fixable leak. EMA60 closed-bar exit allows multi-week holds and preserves the payoff tail better than tested E-A early exit. NSC-018 showed a simple early-exit overlay worsened performance by cutting major winners.
- Re-entry / false-breakout cost is a major leak in the broad sense: the system has low win rate, many small losses, and negative 2022/2025 periods. However, the loss tail is shallow and the payoff ratio is high; the problem is repeated small failed entries while waiting for rare trend legs, not catastrophic loss.

Overall bull-cycle read:

- Direction A appears better than CPM-1 for capturing major BTC/ETH bull-cycle swing legs.
- It is not validated for live use.
- It is the best-supported existing execution-signal candidate found in this review, but still PAUSE_FRAGILE.

## 5. Direction A vs CPM-1

CPM reference: `docs/ops/cpm-bull-segment-readonly-evidence-2026-05-09.md`.

| Dimension | CPM-1 | Direction A | Read |
|---|---|---|---|
| Core signal | 1h ETH pullback-continuation pinbar with EMA50 + 4h EMA60 confirmation | 4h Donchian20 breakout with EMA60 lifecycle exit | Direction A is more directly trend-leg oriented. |
| Assets in current evidence | ETH only for official OOS; 2023/2024 segment evidence uses diagnostic artifacts | ETH, BTC, SOL cross-asset diagnostics; current Phase 1 is BTC+ETH | Direction A has broader mechanism evidence. |
| Bull-segment evidence | 2021 Q1 -459.92, 2021 Jan-Apr -320.14; strongest fixed bull evidence negative | 2021 BTC+ETH +1,015.92; 2023 +3,326.87; 2024 +2,384.81 | Direction A is materially stronger in documented bull/recovery periods. |
| Trade count | CPM bull slices: 24, 39, 1, 7, 3 positions by fixed segment | ETH 173, BTC 159, BTC+ETH 332 unshaped; A1/A3 count unresolved 490 vs 373 | Direction A has larger evidence base. |
| Win/loss profile | CPM 2021 Q1 20.8% position WR; Jan-Apr 23.1%; 2024 positives thin | BTC+ETH 22.29% unshaped WR; ETH 19.65%, BTC 25.16% | Both low-win-rate, but Direction A has high payoff ratio and positive aggregate. |
| Exit/re-entry weakness | CPM exit quality questionable; 2024 positives too thin; 2021 bull windows negative | Many small losses, sparse winners; E-A early exit rejected because it cuts winners | Direction A's weakness is known and more trend-system-consistent. |
| Regime blindness | CPM failed official 2021 bull windows, so not only regime blindness | Direction A loses in 2022/2025 if always on | Human gating may help Direction A more plausibly than CPM, but cannot fix no-boundary by itself. |
| Top-winner dependence | CPM 2024 positives thin; no robust fixed-window positive evidence | Strong top-winner dependence; BTC+ETH top-3/top-5 removal negative unshaped | Direction A has real fragility, but also real positive trend episodes. |
| Signal interpretability | Pullback pinbar in trend, but 2021 bull failures weaken signal story | Donchian breakout + EMA lifecycle is simple and interpretable | Direction A is easier for human ON/OFF regime judgment to reason about. |
| VEI / overlap context | CPM overlap with VEI minimal | VEI positive PnL comes from Direction A overlap; independent VEI signals negative | Direction A appears to be the dominant trend-capture source among reviewed OHLCV signals. |
| Human-gated suitability | Weak after CPM-BULL-SEG-001 | Weak but better-supported | Direction A is more suitable than CPM-1 as candidate, not as validated runtime signal. |

## 6. Known Weaknesses / Failure Modes

1. Top-winner fragility: material.
   - ETH top-3 removal is negative.
   - BTC+ETH unshaped top-3 removal is -1,131.84 and top-5 removal is -3,158.76.
   - A1/A3 risk shaping improves top-5 residual, but does not remove shared-episode dependence.

2. Year concentration: material.
   - BTC+ETH 2023 contributes 60.3% of total net.
   - 2023 + 2024 contribute more than 100% of total BTC+ETH net because 2022 and 2025 are negative.
   - A1/A3 remain positive excluding 2023, but 2022 and late-2025 remain stress periods.

3. False breakout / re-entry cost: material.
   - ETH has 34 winners and 139 losers.
   - BTC+ETH has 74 winners and 258 losers.
   - The system accepts many failed breakouts while waiting for sparse payoff episodes.

4. Late entry: structural.
   - Donchian20 breakout requires a new 20-bar breakout on 4h, so early trend legs are missed by design.

5. Early exit / winner giveback: mixed.
   - EMA60 exit preserves multi-week winners and is the payoff engine.
   - Winner giveback exists but tested early-exit overlay E-A worsened results by cutting top winners.
   - This argues against naive early-exit fixes.

6. Re-entry leak: plausible and important.
   - Low win rate and repeated losers imply churn during non-trending regimes.
   - Existing docs emphasize 2022 and 2025 vulnerability and consecutive loser risk.

7. VEI overlap / echo: important.
   - VEI's independent non-Direction-A signals were negative.
   - The positive VEI result came from Direction A-overlap signals.
   - This strengthens Direction A as the dominant existing trend-capture evidence source, but also shows that several OHLCV ideas are echoing the same trend episodes rather than adding independent edge.

8. Human gating uncertainty: unresolved.
   - Human gating might avoid obvious bear/chop periods.
   - Human gating cannot guarantee avoidance of false breakouts or identify the rare winning trend legs before they happen.
   - No LLM/human decision quality evidence exists yet.

## 7. Human-Gated Architecture Fit

Answer: **WEAK**.

Direction A becomes more attractive under human-gated use than under fully automated all-period evaluation, but the evidence does not support a YES.

What human gating might improve:

- Avoid running the signal in obvious bear/chop periods similar to 2022 and some 2025 conditions.
- Align activation with the Owner's goal: major BTC/ETH bull-cycle swing participation, not all-weather performance.
- Use LLM-assisted briefings to structure macro/news/funding/sentiment context while leaving ON/OFF decisions to the Owner.
- Reduce the pressure to build a fully automated OHLCV regime classifier, which current docs have paused.

What human gating cannot fix:

- It does not create a validated pre-observable boundary.
- It does not remove top-winner dependence.
- It does not prove that the next human-judged bull window will contain Direction A-style payoff episodes.
- It does not solve false breakout cost inside a bull regime.
- It does not authorize runtime control, LLM implementation, paper, testnet, or live.

Before paper/testnet/live, still required:

- Explicit Owner decision on whether Direction A remains the human-gated candidate after reviewing this weak-but-best-available evidence.
- Reconciliation of A1/A3 trade count and time-in-market metrics before any stable observation reporting template.
- A bounded, approved observation or diagnostic plan, still no-order unless separately authorized.
- Evidence that human/LLM briefings are useful for ON/OFF decisions without replacing Owner judgment.

## 8. Exit-Quality Diagnostic Read

Answer: **WEAK_CONDITIONAL**.

Existing evidence suggests an exit-quality diagnostic is more justified for Direction A than for CPM-1, because Direction A has stronger positive sparse trend evidence and a clearer trend-lifecycle payoff engine. But it should remain forensic only.

Evidence suggesting the diagnostic may be useful:

- Direction A's known leak is not catastrophic loss; it is many failed entries/re-entries while waiting for sparse payoff tails.
- Some losers had meaningful MFE before reversing, indicating possible lifecycle/giveback questions.
- The system's profitability depends on preserving long winners; understanding winner path and exit timing is useful.
- A naive early-exit overlay was already rejected, which narrows the diagnostic question: the goal is not to cut early, but to understand when exits/re-entries damage the trend-capture objective.

Evidence limiting the case:

- EMA60 exit is also the payoff engine; early-exit changes can easily destroy the strategy.
- Existing E-A overlay improved many weak trades but worsened the whole system by cutting a few major winners.
- No parameter or exit rewrite should be inferred from this review.

A bounded diagnostic, if separately authorized, should inspect existing trade data only:

- Top winners: entry timing, MFE path, EMA60 exit timing, giveback, whether exits were too early relative to subsequent trend continuation.
- Worst false breakouts: MFE before failure, initial stop vs EMA60 exit, time-to-failure, repeat entries after failed breakouts.
- Re-entry clusters: whether repeated entries occur during chop and whether a human ON/OFF layer could plausibly have avoided them.
- 2022/2025 vulnerability periods versus 2021/2023/2024 winners.
- BTC vs ETH symmetry of the same behaviors.

## 9. Candidate Verdict

Verdict: **DIRECTION_A_WEAK_BUT_BEST_AVAILABLE**.

Why:

- Direction A is better supported than CPM-1 for human-gated bull-cycle execution-signal consideration.
- It has positive BTC+ETH evidence, positive cross-asset evidence, and a simple trend-leg thesis aligned with the Owner's objective.
- The repo-confirmed A1/A3 conservative scenarios show PF 1.752 and low historical drawdown bands, though with metric reconciliation caveats.
- VEI evidence suggests Direction A is the dominant OHLCV trend-capture source among reviewed candidates.

Why not `DIRECTION_A_PRIMARY_CANDIDATE`:

- It remains PAUSE_FRAGILE / NON_RUNTIME.
- No pre-observable applicability boundary exists.
- BTC+ETH top-3/top-5 removal is negative in the unshaped aggregate.
- 2023/2024 carry more than 100% of total BTC+ETH net.
- Human-gated architecture has not been validated.
- Current roadmap/control board still says no runtime candidate and no small-live candidate.

## 10. What Not To Infer

- No live readiness.
- No paper/testnet approval.
- No runtime activation.
- No parameter approval.
- No entry or exit logic change.
- No risk/profile/runtime change.
- No LLM implementation approval.
- No human on/off runtime control approval.
- No small-live approval.
- No claim that Direction A beats spot in the Owner's future bull window.
- No claim that Direction A is validated for the next 2-3 year bull cycle.
- No claim that human gating can reliably remove Direction A's bad periods.

