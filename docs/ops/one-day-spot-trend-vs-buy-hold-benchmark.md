# 1D Spot Trend Timing vs Buy-and-Hold Benchmark Diagnostic

## 1. Boundary

This is an exploratory benchmark diagnostic only. It compares spot-style buy-and-hold and one frozen 1D trend timing rule using local data. It does not authorize Direction A changes, replacing 4h Direction A, runtime use, small-live use, portfolio implementation, capital allocation, parameter optimization, CPM reopening, or strategy rescue.

## 2. Inputs Inspected

- `docs/ops/direction-a-risk-control-return-frontier.md`
- `docs/ops/direction-a-p2-risk-shape-diagnostic.md`
- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `data/v3_dev.db`

## 3. Data Coverage

No spot-symbol OHLCV was found for BTC/USDT, ETH/USDT, or SOL/USDT. Local daily OHLCV exists for `BTC/USDT:USDT`, `ETH/USDT:USDT`, and `SOL/USDT:USDT`; this report is therefore labeled `PERP_PROXY_FOR_SPOT`. Funding is excluded to approximate spot trend timing, but the proxy limitation remains.

| asset | classification | bars | missing daily bars | duplicates | anomalies | earliest | latest |
|---|---|---:|---:|---:|---:|---|---|
| BTC | `1D_PERP_PROXY_READY` | 1826 | 0 | 0 | 0 | 2021-01-01 | 2025-12-31 |
| ETH | `1D_PERP_PROXY_READY` | 1826 | 0 | 0 | 0 | 2021-01-01 | 2025-12-31 |
| SOL | `1D_PERP_PROXY_READY` | 1821 | 5 | 0 | 0 | 2021-01-01 | 2025-12-31 |

## 4. Buy-and-Hold Methodology

Buy-and-hold buys at the first valid daily open in 2021-2025, applies 0.1% fee and 0.1% entry slippage, holds through the final valid daily close, then applies 0.1% exit slippage and 0.1% fee. The primary basket is equal initial allocation across BTC, ETH, and SOL with no rebalance.

## 5. 1D Spot Trend Methodology

The frozen rule is daily close above the highest close of the prior 20 closed daily bars, entry at next daily open, previous-20-day low initial stop with the signal day excluded, and exit after a fully closed daily candle closes below EMA60 with execution at the next daily open. It is long-only, no leverage, no funding, no parameter variants, and no asset-specific changes.

## 6. Asset-Level Buy-and-Hold Results

| asset | cumulative return | CAGR | MaxDD | net 30000U | net 3000U | worst year | Calmar |
|---|---:|---:|---:|---:|---:|---|---:|
| BTC | 2.014 | 0.247 | 0.767 | 60428.85 | 6042.88 | 2022 -32234.64 | 0.322 |
| ETH | 3.013 | 0.320 | 0.794 | 90399.60 | 9039.96 | 2022 -104255.32 | 0.404 |
| SOL | 81.492 | 1.423 | 0.963 | 2444755.92 | 244475.59 | 2022 -3365236.47 | 1.478 |

## 7. Asset-Level 1D Trend Timing Results

| asset | trades | win rate | cumulative return | CAGR | MaxDD | PF | net 30000U | time in market | class |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| BTC | 41 | 0.341 | 2.168 | 0.259 | 0.475 | 2.044 | 65033.52 | 0.476 | `1D_SPOT_TREND_OUTPERFORMS_BUY_HOLD` |
| ETH | 40 | 0.300 | 0.612 | 0.100 | 0.679 | 1.384 | 18373.96 | 0.440 | `1D_SPOT_TREND_NOT_BETTER_THAN_BUY_HOLD` |
| SOL | 33 | 0.364 | 154.403 | 1.751 | 0.696 | 3.964 | 4632097.70 | 0.436 | `1D_SPOT_TREND_OUTPERFORMS_BUY_HOLD` |

## 8. Equal-Weight Basket Comparison

| basket | cumulative return | CAGR | MaxDD | net 30000U | net 3000U | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| Buy-and-hold equal-weight | 28.840 | 0.972 | 0.973 | 865194.79 | 86519.48 | 0.999 |
| 1D trend equal-weight | 52.395 | 1.216 | 0.960 | 1571835.06 | 157183.51 | 1.266 |

The optional max-2 concurrent exposure version is included only as exploratory context and is not the primary benchmark. It uses deterministic BTC > ETH > SOL priority and does not authorize a portfolio rule.

## 9. Drawdown And Bear-Market Protection

Buy-and-hold keeps 100% exposure and therefore carries the full crypto bear-market drawdown. The 1D trend rule materially reduces time in market and can reduce drawdown when it exits sustained downtrends, but the tradeoff is missed rebound exposure and stop/EMA churn after false breakouts. See `buy_and_hold_results.json` and `one_day_trend_results.json` for worst month, quarter, year, and drawdown duration.

## 10. Upside Capture And Missed Rally Review

Trend timing does not automatically dominate buy-and-hold because it only participates after 20-day breakout confirmation and exits after EMA60 weakness. It may avoid major bear-market exposure but can miss early rally legs and can re-enter after part of the move has already occurred. The asset classifications reflect this risk/return tradeoff rather than only lower drawdown.

## 11. Comparison Against 4h Direction A

| asset | 4h trades | 4h net | 4h PF | 4h DD | 1D trend trades | 1D trend PF | 1D trend DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 159 | 2517.17 | 1.477 | 0.099 | 41 | 2.044 | 0.475 |
| ETH | 173 | 3001.66 | 1.517 | 0.061 | 40 | 1.384 | 0.679 |
| SOL | 158 | 4018.80 | 1.790 | 0.045 | 33 | 3.964 | 0.696 |

The 1D benchmark is operationally simpler than 4h Direction A: fewer checks, no funding model, no intraday 4h execution loop, and fewer trades. It is better framed as a benchmark or separate research line, not as an automatic replacement for Direction A.

## 12. Capital-Efficiency Interpretation

For the Owner question, buy-and-hold is the simplest way to capture crypto beta but demands tolerance for full bear-market drawdown. 1D trend timing may improve capital efficiency if it preserves enough upside while reducing drawdown and time in market. The benchmark result should be judged on CAGR/MaxDD and Calmar, not on raw return alone. The 3000U sleeve fields are included for small-capital intuition, not allocation advice.

Direct answers:

1. Why not simply buy spot and hold? Buy-and-hold is simpler, but in this 2021-2025 proxy window it carries near full-cycle crypto drawdown, especially for SOL and the equal-weight basket.
2. Does 1D spot trend timing outperform buy-and-hold on a risk-adjusted basis? BTC and SOL do; ETH does not. The equal-weight basket has better CAGR/Calmar than buy-and-hold, but still has severe drawdown and top-winner concentration.
3. Does 1D spot trend timing meaningfully reduce MaxDD? It meaningfully reduces BTC and SOL asset-level MaxDD, but the equal-weight basket still has very high drawdown, so the basket-level answer is only partially yes.
4. Does 1D spot trend timing give up too much upside? ETH gives up too much upside. BTC and SOL do not in this window, but SOL's result is highly path-dependent and uses perp proxy data.
5. Is 1D spot trend timing simpler and more suitable than 4h Direction A? It is operationally simpler, lower frequency, and removes funding, but it is not automatically more suitable because drawdown and concentration remain large.
6. Is the result strong enough to open a separate research line? Yes, as docs-only research. It is not strong enough to authorize runtime, small-live, or replacement of Direction A.
7. Should this affect the Direction A 4h small-live design path? No. It should be treated as a separate benchmark/research line unless the Owner later authorizes a roadmap review.

## 13. Classification

- BTC: `1D_SPOT_TREND_OUTPERFORMS_BUY_HOLD`
- ETH: `1D_SPOT_TREND_NOT_BETTER_THAN_BUY_HOLD`
- SOL: `1D_SPOT_TREND_OUTPERFORMS_BUY_HOLD`
- Basket: `1D_SPOT_BASKET_STRONG_BENCHMARK`
- Relationship to 4h Direction A: `1D_SPOT_MAY_BE_SIMPLER_ALTERNATIVE`

## 14. Recommendation

Recommendation: **B. Open separate docs-only 1D spot trend research line**. This recommendation does not authorize runtime, small-live, replacing Direction A, capital allocation, or parameter work.

## 15. Explicit Prohibitions

- Direction A changes;
- replacing 4h Direction A;
- 1D spot runtime;
- small-live;
- capital allocation;
- parameter optimization;
- portfolio implementation;
- additional variants;
- CPM reopening;
- strategy rescue;

## 16. Owner Summary

This diagnostic directly addresses the buy-and-hold question with a spot-style daily benchmark. Because only perp-symbol OHLCV was available locally, the result is a `PERP_PROXY_FOR_SPOT` benchmark with funding removed. The result can inform whether a separate 1D spot trend research line is worth review, but it does not change Direction A 4h state or its small-live design path.

1D spot trend timing vs buy-and-hold benchmark is diagnostic only. It does not authorize Direction A changes, replacing 4h Direction A, 1D spot runtime use, small-live use, capital allocation, parameter optimization, portfolio implementation, CPM reopening, or strategy rescue. Any future empirical work or execution requires separate Owner approval and must satisfy SRR-002.
