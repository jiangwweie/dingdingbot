# CPM-BULL-SEG-001 — Read-only Bull Segment Evidence

## 0. Boundary

This report is read-only evidence extraction.

- No new backtest was run.
- No adapter was run.
- No experiment was run.
- No parameter change was made.
- No exit rewrite or hypothetical exit calculation was made.
- No runtime, profile, or risk change was made.
- No strategy-edge claim is made.
- No paper, testnet, or live approval is made.
- No Claude task card was created.

Method: existing CPM-1 result artifacts were sliced by the five pre-declared UTC windows using position `entry_time`. Position-level PnL is therefore assigned to the segment where the signal/entry occurred, even if the position exited after the segment boundary. This is a signal-window read, not a segment-level account-equity reconstruction.

## 1. Data Sources Found

Primary local artifacts found and used:

- `reports/oos_runs/cpm1_2021_oos/result.json`
- `reports/oos_runs/cpm1_2022_oos/result.json`
- `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-2022-oos-report.md`
- `docs/ops/crypto-pullback-module-v1-scope-note.md`
- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/strategy-direction-pivot-2026-05-09.md`

Additional existing CPM-1 baseline diagnostic artifacts found and used with lower evidence strength:

- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2023_result.json`
- `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_2024_result.json`
- `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md`

Data availability notes:

- Official `reports/oos_runs` result JSON files were found for 2021 and 2022 only.
- No official `reports/oos_runs` CPM-1 OOS `result.json` was found for 2023, 2024, or 2025.
- Segment C/D/E therefore use CPM-MOD-002 baseline diagnostic result JSON, not official OOS artifacts.
- `result.json` files under `reports/oos_runs` are described by the OOS reports as local-only / gitignored artifacts; they are available in this workspace.

## 2. Fixed Segment Definitions

| Segment | Window |
|---|---|
| A: 2021 Q1 | 2021-01-01 00:00:00 UTC to 2021-03-31 23:59:59 UTC |
| B: 2021 Jan-Apr | 2021-01-01 00:00:00 UTC to 2021-04-30 23:59:59 UTC |
| C: 2023 Q4 | 2023-10-01 00:00:00 UTC to 2023-12-31 23:59:59 UTC |
| D: 2024 Q1 | 2024-01-01 00:00:00 UTC to 2024-03-31 23:59:59 UTC |
| E: 2024 Q4 | 2024-10-01 00:00:00 UTC to 2024-12-31 23:59:59 UTC |

## 3. Segment Results

Position-level metrics are sliced from existing `positions[]`. Exit mix is sliced from existing `close_events[]` for the selected positions. "Close-event legs" is not identical to top-level `total_trades`; it is the available segment-level close-event count.

| Segment | Source | Evidence strength | Positions | Close-event legs | Position PnL (USDT) | Top-level PnL | Wins | Losses | Win rate | Largest loss cluster | TP1 hit | TP2 | TP1 then SL | SL-only |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---:|
| A: 2021 Q1 | 2021 official OOS JSON | High | 24 | 35 | -459.92 | Unavailable for segment; full-year 2021 = -2,153.76 | 5 | 19 | 20.8% | 9 losses, -536.81, 2021-02-20 to 2021-03-28 | 11 | 5 | 6 | 13 |
| B: 2021 Jan-Apr | 2021 official OOS JSON | High | 39 | 59 | -320.14 | Unavailable for segment; full-year 2021 = -2,153.76 | 9 | 30 | 23.1% | 9 losses, -536.81, 2021-02-20 to 2021-03-28 | 20 | 9 | 11 | 19 |
| C: 2023 Q4 | CPM-MOD-002 baseline diagnostic JSON | Low / secondary | 1 | 1 | -84.82 | Unavailable for segment; full-year diagnostic 2023 = -785.24 | 0 | 1 | 0.0% | 1 loss, -84.82, 2023-11-26 | 0 | 0 | 0 | 1 |
| D: 2024 Q1 | CPM-MOD-002 baseline diagnostic JSON | Low / secondary | 7 | 12 | +589.47 | Unavailable for segment; full-year diagnostic 2024 = +850.61 | 5 | 2 | 71.4% | 2 losses, -186.06, 2024-02-11 to 2024-02-12 | 5 | 5 | 0 | 2 |
| E: 2024 Q4 | CPM-MOD-002 baseline diagnostic JSON | Low / secondary | 3 | 5 | +121.29 | Unavailable for segment; full-year diagnostic 2024 = +850.61 | 1 | 2 | 33.3% | 2 losses, -60.93, 2024-10-14 to 2024-10-20 | 2 | 1 | 1 | 1 |

Cost caveats:

- Segment-level position PnL does not fully reconcile to top-level account PnL because account-level fees, funding, slippage, and accounting adjustments are not embedded one-for-one in `positions[].realized_pnl`.
- 2021 official OOS full-year top-level costs: fees 519.97, slippage 1,040.85, funding 19.10 USDT.
- 2023 diagnostic full-year top-level costs: fees 124.93, slippage 268.83, funding 24.19 USDT.
- 2024 diagnostic full-year top-level costs: fees 308.42, slippage 520.61, funding 26.39 USDT.
- No segment-level top-level PnL or segment-level cost allocation was available without reconstructing account equity; this report does not reconstruct it.

## 4. Segment-by-Segment Read

### Segment A: 2021 Q1

Read: negative.

Evidence strength: high, because the segment uses the official 2021 OOS `result.json`.

Evidence:

- 24 positions.
- Position-level PnL -459.92 USDT.
- 5 wins, 19 losses, 20.8% position win rate.
- Largest loss cluster: 9 consecutive non-positive positions, -536.81 USDT, from 2021-02-20 to 2021-03-28.
- 11 positions hit TP1 and 5 reached TP2, but 13 were SL-only and the net segment was still negative.

Caveats:

- PnL is position-level, not segment-level account PnL.
- Positions are assigned by entry time.
- Costs are only available at full-year top level.

### Segment B: 2021 Jan-Apr

Read: negative.

Evidence strength: high, because the segment uses the official 2021 OOS `result.json`.

Evidence:

- 39 positions, which is enough to avoid treating the result as merely a tiny sample.
- Position-level PnL -320.14 USDT.
- 9 wins, 30 losses, 23.1% position win rate.
- April improves the Q1 result but does not make Jan-Apr positive.
- Largest loss cluster remains the 2021-02-20 to 2021-03-28 cluster.
- 20 positions hit TP1 and 9 reached TP2, but 19 were SL-only.

Caveats:

- PnL is position-level, not segment-level account PnL.
- Costs are only available at full-year top level.

### Segment C: 2023 Q4

Read: negative but too thin to carry much weight.

Evidence strength: low / secondary, because no official 2023 OOS result artifact was found. This uses CPM-MOD-002 baseline diagnostic JSON.

Evidence:

- 1 position.
- Position-level PnL -84.82 USDT.
- 0 wins, 1 loss.
- SL-only.

Caveats:

- One position is too thin for a robust segment conclusion.
- The source is a research diagnostic baseline artifact, not official OOS.
- The result weakens the specific 2023 Q4 bull-segment read, but cannot by itself reject the thesis.

### Segment D: 2024 Q1

Read: positive.

Evidence strength: low / secondary, because no official 2024 OOS result artifact was found. This uses CPM-MOD-002 baseline diagnostic JSON.

Evidence:

- 7 positions.
- Position-level PnL +589.47 USDT.
- 5 wins, 2 losses, 71.4% position win rate.
- 5 TP1 hits and 5 TP2 completions.
- Largest loss cluster: 2 losses, -186.06 USDT.

Caveats:

- Seven positions is positive but thin.
- One position entered in Q1 can exit after Q1; this report assigns PnL by entry time.
- The source is a research diagnostic baseline artifact, not official OOS.

### Segment E: 2024 Q4

Read: positive but very thin.

Evidence strength: low / secondary, because no official 2024 OOS result artifact was found. This uses CPM-MOD-002 baseline diagnostic JSON.

Evidence:

- 3 positions.
- Position-level PnL +121.29 USDT.
- 1 win, 2 losses, 33.3% position win rate.
- 2 TP1 hits, 1 TP2 completion, 1 TP1-then-SL, 1 SL-only.

Caveats:

- Three positions is too thin to support a strong conclusion.
- The positive result appears driven by a small number of trades.
- The source is a research diagnostic baseline artifact, not official OOS.

## 5. Human-Gated CPM Thesis Read

Overall read: WEAK / INCONCLUSIVE, leaning weak.

Answers to required questions:

1. Is CPM-1 positive in each pre-declared bull segment?
   - A 2021 Q1: no.
   - B 2021 Jan-Apr: no.
   - C 2023 Q4: no, but only 1 position.
   - D 2024 Q1: yes, but only 7 positions and secondary source.
   - E 2024 Q4: yes, but only 3 positions and secondary source.

2. Are positive segments driven by enough trades, or too thin?
   - 2024 Q1 is positive but thin at 7 positions.
   - 2024 Q4 is positive but very thin at 3 positions.
   - These are supportive observations, not robust validation.

3. Does 2021 Q1 / Jan-Apr support or weaken the human-gated CPM thesis?
   - It weakens the thesis materially.
   - These are the strongest evidence segments because they use official OOS trade-level data.
   - Both pre-declared 2021 bull windows are negative, and Jan-Apr has 39 positions.

4. Does 2023 Q4 / 2024 Q1 support or weaken the thesis?
   - Combined read is inconclusive.
   - 2023 Q4 is negative but has only 1 position.
   - 2024 Q1 is positive but has only 7 positions and uses a diagnostic baseline artifact.
   - The pair does not provide strong enough evidence to offset 2021.

5. Does 2024 Q4 support or weaken the thesis?
   - It mildly supports the thesis directionally, but the evidence is very thin.
   - Three positions cannot establish segment-level signal quality.

6. Is CPM-1 signal quality good enough to justify exit-logic investigation?
   - Weak / conditional at best.
   - There is positive 2024 segment evidence, but it is thin and secondary.
   - The official 2021 bull-segment evidence is negative with enough trades to matter.

7. Or should CPM-1 be parked even under human-gated architecture?
   - The read-only evidence does not support moving directly into LLM engineering, runtime control, paper, testnet, or live work.
   - A narrow exit-logic investigation can be justified only if the Owner accepts it as a bounded diagnostic on why 2024-style winners worked and why 2021 bull-window trades failed. It should not be framed as CPM-1 validation.

Thesis classification: WEAK / INCONCLUSIVE.

Reason: the strongest OOS bull-window evidence is negative; the positive evidence exists only in thin 2024 slices from secondary diagnostic artifacts.

## 6. Should Exit Logic Investigation Proceed?

Choice: WEAK / CONDITIONAL.

Why:

- YES is too strong because the official 2021 bull-window evidence is negative in both fixed windows.
- NO is also slightly too strong because 2024 Q1 and 2024 Q4 are positive, and CPM-MOD-002 plus the scope/failure docs indicate CPM-1 may work in a narrower 2024-style sub-regime.
- Any exit investigation must remain bounded and diagnostic:
  - explain whether positive 2024 trades had unrealized continuation that current exits failed to capture;
  - compare against 2021 bull-window failures as a falsification check;
  - avoid parameter search, hypothetical new exits as claims, or runtime implications.

The next step is not LLM implementation and not paper/testnet/live. The only defensible next work is a small read-only / diagnostic exit-quality investigation, if the Owner wants to spend that effort despite weak evidence.

## 7. What Not To Infer

- No strategy edge is proven.
- No live readiness is implied.
- No paper or testnet approval is implied.
- No runtime change is implied.
- No profile or risk change is implied.
- No parameter change is implied.
- No exit logic change is implied.
- No LLM layer implementation approval is implied.
- No claim is made that human-gated CPM is viable.
- No claim is made that the 2024 thin positive slices will repeat.

