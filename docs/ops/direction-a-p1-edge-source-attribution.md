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

# Direction A P1 Edge-Source Attribution Diagnostics

**Status:** Completed / attribution diagnostics only  
**Date:** 2026-05-08  
**Classification:** `P1_MIXED_EDGE_SOURCE`  
**Recommendation:** E. Owner decision required  
**Affects Runtime Automatically:** No

---

## 1. Boundary

This report executes only the Owner-authorized Direction A P1 attribution diagnostics:

1. Random Entry + EMA60 Exit Control.
2. Buy-and-Hold / Time-in-Market Decomposition.

It is attribution-only. It does not authorize Direction A changes, parameter optimization, additional assets, portfolio construction, vol targeting, runtime use, small-live use, TE execution, CPM reopening, or strategy rescue.

## 2. Inputs Inspected

- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `reports/direction-a-p0-evidence-strength-diagnostics/p0_summary.json`
- `reports/direction-a-p0-evidence-strength-diagnostics/winner_overlap_matrix.json`
- `reports/direction-a-p0-evidence-strength-diagnostics/bootstrap_pf_ci.json`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.csv`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.csv`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`


ETH cross-asset result/trade artifacts were not present in the cross-asset diagnostic folder, so the existing NSC-014 ETH Direction A trade artifact was used. ETH Direction A was not regenerated.

## 3. Current Direction A and P0 State

Current Direction A state: `POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`.

Completed P0 state:

- Winner overlap: `WINNER_EVIDENCE_PARTIALLY_SHARED`.
- PF confidence: `PF_CONFIDENCE_INCONCLUSIVE`.
- Combined P0: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`.
- Recommendation: Owner decision required.
- Top-5 raw winners: 15; loose unique top-5 episodes: 6; asset-adjusted loose effective observations: 3.5.

P1 is therefore interpreted conservatively as edge-source attribution only.

## 4. Random Entry Control Methodology

For each asset, the control used the same local 4h OHLCV base window from 2021-01-01 to 2025-12-31. Random entries were matched to Direction A trade count by year. Each random entry used:

- next selected 4h open as entry;
- 0.1% entry slippage;
- previous-20-closed-bar low as initial stop;
- EMA60 close-break exit, next 4h open execution;
- 0.1% exit slippage;
- fee_rate 0.0004;
- funding 0.0001 per 8h;
- 1% risk sizing, capped at 2x equity exposure.

The control ran 1,000 trials per asset with fixed seeds: ETH 2026050801, BTC 2026050802, SOL 2026050803.

Limitation: random-entry trials are independent trade attribution controls. They are not portfolio/router simulations and may include overlapping hypothetical trades. This is intentional for edge-source attribution and does not imply deployable execution.

## 5. Random Entry Control Results

| asset | DA_net | rand_net_p5 | rand_net_med | rand_net_p95 | DA_net_pctile | DA_PF | rand_PF_med | DA_PF_pctile | class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 3001.66 | -2387.36 | 773.55 | 4793.46 | 0.831 | 1.517 | 1.13 | 0.828 | ENTRY_ALPHA_PARTIAL |
| BTC | 2517.17 | -3108.94 | -224.39 | 3732.49 | 0.885 | 1.477 | 0.961 | 0.883 | ENTRY_ALPHA_PARTIAL |
| SOL | 4018.8 | -1012.03 | 2461.22 | 7248.72 | 0.716 | 1.79 | 1.467 | 0.719 | ENTRY_ALPHA_PARTIAL |


## 6. Random Entry Interpretation

Per-asset classifications:

- ETH: `ENTRY_ALPHA_PARTIAL`.
- BTC: `ENTRY_ALPHA_PARTIAL`.
- SOL: `ENTRY_ALPHA_PARTIAL`.

Direction A generally outperforms random entries on net PnL and PF percentile, but not uniformly at a decisive level across all assets. This supports some Donchian20 breakout-entry contribution, while leaving room for EMA60 lifecycle management and long beta exposure to explain part of the result.

## 7. Buy-and-Hold / Time-in-Market Methodology

For each asset, the decomposition computed:

- full buy-and-hold price return over the base window;
- a $10,000 buy-and-hold PnL proxy;
- Direction A total time in market and episode count from existing trade windows;
- underlying asset return during Direction A in-market bars;
- underlying asset return during Direction A out-of-market bars;
- randomly selected time-in-market windows matched to Direction A exposure durations and episode count;
- full buy-and-hold drawdown and Direction A realized drawdown.

The buy-and-hold PnL proxy is a beta comparison tool only. It is not comparable to Direction A risk sizing as a deployment model.

## 8. Buy-and-Hold Decomposition Results

| asset | DA_net | BH_return | BH_proxy | DA_time_pct | in_mkt_ret | out_mkt_ret | matched_med_ret | DA_DD | BH_DD | class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 3001.66 | 3.029 | 30294.09 | 0.389 | 1.448 | 0.627 | 0.412 | 0.061 | 0.812 | SMART_BETA_TIMING |
| BTC | 2517.17 | 2.026 | 20263.79 | 0.384 | 0.947 | 0.535 | 0.356 | 0.099 | 0.771 | SMART_BETA_TIMING |
| SOL | 4018.8 | 81.823 | 818225.75 | 0.379 | 43.431 | 0.76 | 2.794 | 0.045 | 0.966 | SMART_BETA_TIMING |


## 9. Alpha vs Beta Interpretation

Per-asset classifications:

- ETH: `SMART_BETA_TIMING`.
- BTC: `SMART_BETA_TIMING`.
- SOL: `SMART_BETA_TIMING`.

Direction A is not merely full buy-and-hold exposure: it spends materially less than 100% of time in market and has much lower realized drawdown than full buy-and-hold. However, the decomposition also shows that crypto beta timing explains a meaningful part of the edge: the strategy is profitable when it participates in major trend windows and avoids some large drawdowns. This is stronger as smart beta timing evidence than as standalone proof of pure entry alpha.

## 10. Combined P1 Interpretation

Combined classification: `P1_MIXED_EDGE_SOURCE`.

Reasoning:

- Random-entry controls do not fully explain Direction A, but the Donchian entry contribution is not uniformly decisive across all three assets.
- EMA60 lifecycle exit management and long crypto beta timing remain material contributors.
- Time-in-market decomposition supports drawdown-controlled participation in trend regimes, not deployment readiness.
- P0 remains inconclusive, so P1 should not be used to promote Direction A or jump directly into portfolio/risk engineering.

## 11. Recommendation

E. Owner decision required

Rationale: P1 is mixed. It preserves Direction A as a research asset and clarifies that the edge is a combination of breakout selection, EMA60 trend lifecycle management, and crypto beta timing. It does not produce a sufficiently clean pre-observable boundary clue or strong enough edge-source proof to automatically proceed to P2.

## 12. Explicit Prohibitions

This report does not authorize:

- Direction A changes;
- Direction A variants;
- parameter optimization;
- additional assets;
- portfolio/router work;
- vol targeting;
- runtime;
- small-live;
- TE execution;
- CPM reopening;
- strategy rescue.

## 13. Owner Summary

P1 attribution weakens any simple story that Direction A is pure Donchian entry alpha. The evidence is mixed: random-entry controls suggest the frozen breakout entry contributes, but EMA60 lifecycle exit and smart crypto beta timing also explain a material share. Direction A remains a positive, pause-fragile, non-runtime research asset. P1 does not authorize P2, portfolio work, risk-shape engineering, runtime, or small-live.

Direction A P1 edge-source attribution does not authorize Direction A changes, variants, parameter optimization, additional assets, portfolio work, vol targeting, runtime use, small-live use, TE execution, CPM reopening, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
