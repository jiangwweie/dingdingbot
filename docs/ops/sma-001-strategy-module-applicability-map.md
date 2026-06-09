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

# SMA-001 - Strategy Module Applicability Map

**Task ID:** SMA-001
**Date:** 2026-05-07
**Status:** Completed / Docs-only applicability map; updated by SMA-003 with MTC-006 Direction D rejection; updated by SSD-004 with SSD-003 short-side rejection; updated by DIRA-EH-001 with Direction A evidence hardening reclassification; updated by DIRA-XA-003 with Direction A cross-asset frozen diagnostic; updated by DIRA-P0-PLAN with P0/P1/P2 evidence diagnostics roadmap; updated by DIRA-P1 with edge-source attribution result; updated after P1 to make P2 risk-shape diagnostics the next eligible stage
**Authorization Level:** Level 1/2 - docs-only
**Source:** SR-001 Owner-accepted research-route review; CPM-MOD-002 accepted frozen diagnostic evidence; MTC-006 accepted Direction D frozen baseline evidence; SSD-003 accepted short-side frozen baseline evidence
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document maps current strategy modules and candidate layers by mechanism,
applicability hypothesis, failure boundary, evidence state, family
relationship, and Level 3 readiness.

It is not:

- a new strategy experiment;
- backtest authorization;
- research script or adapter authorization;
- parameter optimization;
- runtime/profile/risk/backtester-core work;
- small-live readiness review;
- strategy router, portfolio, or regime-engine design;
- new data pipeline authorization.

No runtime candidate, deployable small-live strategy, live profile change,
strategy enablement, or risk-rule change follows from this map.

SR-001's current blocker remains binding:

> No module has a validated, pre-observable applicability boundary that
> survives enough trades, enough winners, top-winner fragility, year
> concentration, and realistic costs.

---

## 1. Map Summary

| Object | Current classification | Role | Family | Next allowed action |
| --- | --- | --- | --- | --- |
| Direction A | `CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME` | Strongest current strategy research asset; cross-asset smart-beta trend timing with partial entry alpha; non-runtime | Main Trend Capture / breakout + lifecycle beta timing | P2 risk-shape diagnostics eligible with separate Owner approval; no variants, overlays, timing rescue, parameter changes, runtime, small-live, or portfolio implementation |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` | Paused candidate module | Main Trend Capture / volatility-state | No threshold loosening; use as map evidence |
| CPM-1 | `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT / OHLCV_BOUNDARY_ATTRIBUTION_PAUSED`; OHLCV boundary attribution paused; evidence preserved | Existing pullback module, frozen | Pullback-continuation | No CPM follow-up; preserve attribution evidence; no further OHLCV feature mining without explicit Owner decision |
| Direction D | `REJECTED_FROZEN_BASELINE` | Rejected pullback-continuation evidence | Pullback-continuation MTC variant | Archive MTC-006; no parameter/zone/EMA/confirmation/15m rescue |
| Short-side breakdown continuation | `REJECTED_FROZEN_BASELINE` | Rejected non-pullback short-side evidence | Short-side / two-sided directional | Archive SSD-003; no variants/lookbacks/mirror/OI/rescue |
| VEI (volatility expansion / impulse participation) | `PAUSE_FRAGILE` | Paused non-pullback bar-level impulse evidence; independent signals negative | Non-pullback / impulse capture | Preserve as evidence; no variants |
| 15m / sub-1h auxiliary layer | Candidate - inspect-only lower-timeframe execution layer, not immediate mainline | Candidate auxiliary layer | Execution timing only by default; pullback-entry belongs to pullback-continuation | Role/caveat docs only; no 15m pullback-entry Level 3 |

Current small-live state:

- No runtime candidate.
- No deployable small-live strategy.
- Small-live readiness gate remains unmet.

---

## 2. Module Identity

### 2.1 Direction A

| Dimension | Current identity |
| --- | --- |
| Profit source | Sparse 4h main-trend lifecycle capture; few large trend winners pay for many small losses |
| Entry mechanism | 4h Donchian20 close breakout; next 4h open entry |
| Exit / lifecycle assumption | EMA60 close-break trend lifecycle exit; next 4h open after closed-bar trigger |
| Timeframe role | 4h is sole decision timeframe |
| Pullback-continuation family? | No. Breakout / trend-lifecycle family |
| Strategy role | Strongest current strategy research asset; cross-asset validated (ETH + BTC + SOL); pause-fragile; non-runtime |
| Current action | Do not reopen parameters, overlays, exits, or entry micro-variants; no portfolio/router/regime work; no additional asset diagnostics without Owner approval |

### 2.2 Direction C

| Dimension | Current identity |
| --- | --- |
| Profit source | Trend continuation after volatility contraction and bullish re-expansion |
| Entry mechanism | 4h trend context plus avg_range(6)/avg_range(20) contraction and bullish range re-expansion |
| Exit / lifecycle assumption | Inherits Direction A EMA60 close-break lifecycle exit |
| Timeframe role | 4h primary |
| Pullback-continuation family? | No. Volatility-state / contraction-expansion MTC variant |
| Strategy role | Paused candidate module; structurally distinct but insufficient evidence |
| Current action | Do not loosen ATR ratio, run sensitivity, add no-trade gate, or sweep thresholds |

### 2.3 CPM-1

| Dimension | Current identity |
| --- | --- |
| Profit source | Trend-pullback continuation in gentle, low-volatility ETH uptrends |
| Entry mechanism | ETH 1h Pinbar pullback-ending trigger under EMA50 + 4h EMA60 trend confirmation |
| Exit / lifecycle assumption | Fixed TP1/TP2 R-multiple geometry with OCO; not open-ended trend lifecycle |
| Timeframe role | 1h primary, 4h MTF confirmation |
| Pullback-continuation family? | Yes. Baseline failure case for this family |
| Strategy role | Existing frozen module; paused after OOS failure; not small-live |
| Current action | OHLCV boundary attribution paused. No CPM-MOD-003, CPM-2, gate variants, or further OHLCV feature mining. H5 macro evidence preserved. Future work limited to Owner-approved paths only: Option A (pause, current default) or Option C (docs-only extra-data inspect, reserved not authorized). |

### 2.4 Direction D

| Dimension | Current identity |
| --- | --- |
| Profit source | Trend continuation after structured 4h value-zone pullback and resumption |
| Entry mechanism | 4h EMA60 value-zone touch + EMA20 resumption confirmation |
| Exit / lifecycle assumption | EMA60 close-break trend lifecycle exit |
| Timeframe role | 4h primary |
| Pullback-continuation family? | Yes. Structurally different from CPM-1 but same broad family question |
| Strategy role | Rejected frozen-baseline evidence after MTC-006 |
| Current action | Do not continue parameters, zone variants, EMA variants, confirmation variants, or 15m entry timing rescue |

### 2.5 15m / Sub-1h Auxiliary Layer

| Dimension | Current identity |
| --- | --- |
| Profit source | Not defined yet; possible entry/execution improvement under a higher-timeframe thesis |
| Entry mechanism | Not defined; must be role-defined before any empirical work |
| Exit / lifecycle assumption | Should inherit 4h thesis if used as auxiliary layer; cannot define lifecycle by default |
| Timeframe role | Candidate lower-timeframe layer; not immediate primary decision timeframe |
| Pullback-continuation family? | Only if used as pullback-entry. Execution timing alone is not necessarily pullback-continuation |
| Strategy role | Candidate - inspect-only lower-timeframe layer, not immediate mainline |
| Current action | LTF-002 freezes default role as execution timing under frozen 4h thesis; no 15m pullback-entry experiment |

### 2.6 Short-Side Breakdown Continuation

| Dimension | Current identity |
| --- | --- |
| Profit source | Short-only downside lifecycle capture after confirmed closed-bar support breakdown and continuation confirmation |
| Entry mechanism | Confirmed swing-low support breakdown + next-bar continuation confirmation + next 4h open entry |
| Exit / lifecycle assumption | Squeeze/reclaim invalidation exit + protective stop at breakdown/confirmation bar high |
| Timeframe role | 4h sole decision timeframe |
| Pullback-continuation family? | No. Short-side breakdown lifecycle family |
| Strategy role | Rejected frozen-baseline evidence after SSD-003 |
| Current action | Do not continue variants, alternate lookbacks, mirror variants, bearish C rescue, failed-rally value-zone short, 1h/15m timing, funding/OI rescue, or router/portfolio/regime proposals |

### 2.7 VEI (Volatility Expansion / Impulse Participation)

| Dimension | Current identity |
| --- | --- |
| Profit source | Bar-level impulse continuation: range expansion + close-location + follow-through confirmation |
| Entry mechanism | 4h impulse bar (range > 1.5×SMA20, close-location ≥ 0.75) + next-bar follow-through confirmation (close > impulse close) + EMA60 trend filter; entry at open of bar T+2 |
| Exit / lifecycle assumption | 5-bar fixed max hold + 2×ATR14 initial protective stop; NOT EMA60 lifecycle exit |
| Timeframe role | 4h sole decision timeframe |
| Pullback-continuation family? | No. Non-pullback bar-level impulse capture family |
| Strategy role | Paused non-pullback evidence; PAUSE_FRAGILE; independent signals negative |
| Current action | Do not continue expansion/lookback/CLV/EMA/holding/ATR variants; do not rescue via Direction A/C; no 1h/15m timing; no funding/OI rescue |

---

## 3. Applicability Hypotheses

### 3.1 Applicability By Object

| Object | Expected effective market | Ex-ante observable? | Required features | Future data dependency? |
| --- | --- | --- | --- | --- |
| Direction A | Crypto-wide sustained directional 4h trends where Donchian20 breakout continuation can run for multi-day holds; validated across ETH, BTC, and SOL | Partially — cross-asset evidence supports mechanism, but no pre-observable boundary; 2023 year concentration unexplained | 4h Donchian high/low, EMA60, trend persistence, breakout frequency, realized volatility/chop diagnostics | No funding/OI/orderbook required for current scope |
| Direction C | Established 4h uptrend with real compression before the next impulse | Partially | 4h EMA60, range ratio, re-expansion magnitude, bullish close, volatility/chop state | No funding/OI/orderbook required |
| CPM-1 | Gentle, low-volatility uptrends with moderate slope, shallow pullbacks, price not near recent highs; non-hostile 1D/3D macro context may be required | Partially strengthened but incomplete; OHLCV boundary attribution paused | Rolling ATR percentile partially explains 2021 high-vol only; H5 macro context partially explains 2022 (1D multi-dimensional separation confirmed); 2023 continuation failure remains unresolved under OHLCV; no SRR-002-compliant pre-observable applicability boundary; no further OHLCV feature mining without explicit Owner decision | No new data for current evidence; funding/OI/orderbook are future only (Option C reserved) |
| Direction D | 4h uptrend where pullbacks to EMA60 value zone resolve into continuation rather than reversal | Tested and rejected for frozen EMA60/EMA20 baseline | MTC-006 used 4h EMA60/EMA20, zone touch, resumption close, lifecycle exit; no further feature search authorized | No funding/OI/orderbook required or authorized |
| Short-side breakdown continuation | Bearish 4h structure with confirmed support breakdown, continuation confirmation, and downside follow-through | Tested and rejected for frozen OHLCV-only baseline | SSD-003 used confirmed swing-low support, closed-bar breakdown, continuation confirmation, squeeze/stop exit; no further feature search authorized | No funding/OI/orderbook required or authorized; funding was cost caveat only |
| VEI (volatility expansion / impulse participation) | Sudden 4h range expansion with directional close-location control and follow-through confirmation; bar-level energy detection | Tested and weak at Level 3: overlap gates passed (27.1% A, 2.5% C) but independent signals net negative; no clean pre-observable boundary | VEI-003 used 1.5×SMA20 expansion, 0.75 CLV, EMA60 trend, 5-bar hold, 2×ATR14 stop; no further feature search authorized | No funding/OI/orderbook required or authorized |
| 15m auxiliary layer | Higher-timeframe thesis active, where 15m can improve execution timing under frozen 4h thesis | Role frozen only for execution timing; not Level 3 ready | 15m data quality, 4h parent signal context, local execution timing, spread/slippage sensitivity, intrabar conflict counts | No new pipeline authorized; data caveats must be handled before empirical work |

### 3.2 Funding / OI / Orderbook Boundary

None of the five mapped objects currently requires funding, open interest, or
orderbook as a prerequisite for its next docs-only step.

If a future hypothesis requires funding/OI/orderbook to identify crowded or
toxic market states, that must be marked as a future data dependency. It must
not be introduced by SMA-001 and must not become a hidden data-pipeline task.

---

## 4. Failure Boundary Hypotheses

### 4.1 Failure By Object

| Object | Expected failure state | Existing support | Post-hoc fitting risk | Downgrade rule if boundary is not ex-ante |
| --- | --- | --- | --- | --- |
| Direction A | Choppy or failed-trend years; breakout signals without enough payoff tail; regime-dependent performance confirmed across ETH/BTC/SOL | Supported by 2022/2025 weakness and top-winner fragility across all three assets; 2023 dominance is regime-dependent pattern | High if adding filters after seeing losing periods | Preserve as `PAUSE_FRAGILE`; no rescue variants; cross-asset evidence strengthens but does not authorize runtime |
| Direction C | Bear/chop or compression events that fail quickly; too few winners to support evaluation | Supported by thin sample, worse MAE/giveback, worse top concentration | High if ATR ratio is loosened after result | Keep `INSUFFICIENT_EVIDENCE`; no threshold rescue |
| CPM-1 | High-volatility, high-slope, surge, near-Donchian-top, reversal-within-uptrend states (2021); hostile macro downtrend context (2022); continuation failure in non-hostile context (2023) | 2021: CPM-MOD-002 ATR gate partially addresses. 2022: H5 macro context partially explains (1D multi-dimensional separation, caveated 3D). 2023: unexplained under OHLCV — no credible pre-observable proxy found. Top-5 winners enter hostile macro context (contradiction). | Very high if any new gate, threshold, feature, macro filter, or composite is fit after closeout | OHLCV boundary attribution paused; evidence preserved; no CPM follow-up authorized without explicit Owner decision |
| Direction D | EMA lag during corrections; value-zone touch becomes churn / falling-knife or weak bounce entry; cost drag overwhelms gross edge | Supported by MTC-006: 417 trades / 66 winners, net -262.57, PF 0.985, MTM DD 29.78%, top-N failure | Very high if zone/EMA/confirmation/15m timing is adjusted after rejection | `REJECTED_FROZEN_BASELINE`; no Direction D rescue |
| Short-side breakdown continuation | Squeeze/reclaim invalidation, failed breakdowns, capitulation timing, funding cost drag, single-winner fragility | Supported by SSD-003: 23 trades / 1 winner, net -1699.88, PF 0.317, realized DD 24.88%, MTM DD 26.98%, 2021 strongly negative, 2022-2024 no trades, extreme top-winner fragility | Very high if breakdown thresholds, support lookbacks, or timing are adjusted after rejection | `REJECTED_FROZEN_BASELINE`; no SSD-003 rescue |
| VEI (volatility expansion / impulse participation) | Independent signals unprofitable; all positive PnL from Direction A overlap echo; top-winner fragility; high cost drag | Supported by VEI-003: 118 trades / 56 winners, net +630.49, PF 1.21, but independent signals net -329.02 PF 0.86, top-3 removal -286.85, cost drag 60.2%, 88% time-exit | Very high if expansion/lookback/CLV/EMA/hold/ATR variants are attempted after PAUSE_FRAGILE | `PAUSE_FRAGILE`; no VEI variants or rescue |
| 15m auxiliary layer | Noise, cost drag, false breakouts, same-bar ambiguity, overfit microstructure | CPM-1 15m direct migration had too many trades and poor quality; broader 15m untested | Very high if 15m is used to rescue failed higher-timeframe results | Keep as inspect-only candidate; require data QA + role definition before Level 3 |

### 4.2 Boundary Principle

An applicability boundary is usable only if it is:

- described before execution;
- computable from information available before the decision;
- evaluated with realistic costs;
- robust to trade count, winner count, and top-N removal;
- able to explain both valid and invalid periods without selecting only the
  years that already look good.

If a module's failure boundary cannot be identified ex-ante, the module should
be downgraded to `PAUSE_FRAGILE`, `INSUFFICIENT_EVIDENCE`, or `REJECT_BY_FAMILY`
depending on evidence strength and family drift.

---

## 5. Current Evidence State

### 5.1 Evidence Matrix

| Object | Positive evidence | Negative evidence | Trade / winner count | Top-winner fragility | Year concentration | MFE / MAE / giveback | MTM DD | Overlap / drift | Current classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direction A | ETH: 173 trades, 34 winners, net +3,001.66, PF 1.517, payoff 6.20:1, win rate 19.65%, loss tail bounded (worst -133.30); BTC cross-asset: 159 trades, 40 winners, net +2,517.17, PF 1.477, payoff 4.39:1, win rate 25.16%; SOL cross-asset: 158 trades, 44 winners, net +4,018.80, PF 1.790, payoff 4.64:1, win rate 27.85%; mechanism transfers across all three assets; P1 shows partial Donchian20 entry alpha plus smart-beta trend timing | P0 evidence strength inconclusive: partially shared winner episodes and PF CI uncertainty; BTC top-3 removal NEGATIVE (−687.93); SOL top-5 removal NEGATIVE (−369.78); all three assets fail top-5 removal; no validated pre-observable applicability boundary; SRR-002 not met; 2023 year concentration extreme (BTC 95.7%, SOL 70.5%) | BTC 159 / SOL 158 / ETH 173 trades; all meet trade floors | BTC top-3 removal negative; SOL passes top-3 (+380.21) but fails top-5; ETH top-3 negative; universal top-5 failure across all assets | 2023 dominates all assets; P0 shows shared crypto-wide episodes; P1 shows smart beta timing rather than pure alpha | BTC avg winner 194.82 / avg loser −44.33; SOL avg winner 206.89 / avg loser −44.60; both high payoff ratios | BTC MTM DD 11.32%; SOL MTM DD 6.44% | Standalone trend timing; VEI overlap 27.1% is echo not independent alpha; 14.3% Direction C overlap | `CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME` |
| Direction C | Structurally distinct from A; low overlap; net +2039.29; PF 1.405 | Thin sample; 10 winners; worse top concentration; worse MTM DD; worse MAE/giveback | 63 trades; 10 winners | Top-1 82.25% of net; top-3 -2471.12; top-5 -3861.04 | 3 positive years but carried by few trades; 2021 48.2% of net | Known: MFE +2326.26, MAE -248.27, max giveback 720.15 | Known: 15.01% | 14.3% signal overlap with A; not pullback drift | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE` |
| CPM-1 | 2024/2025 applicable-market evidence preserved; CPM-MOD-002 ATR gate improved 2021; H5 macro context partially explains 2022 (1D multi-dimensional separation: d1_dist_ema200 gap 31.96, d1_ema50_above_ema200 gap 74.8pp, d1_ema200_slope_20d gap 7.54) | 2023 continuation failure unexplained (MFE 4.26 vs 406); top-5 winners enter hostile macro context (contradiction); 3D EMA200 warmup-limited (20.2% of 2022); no pre-observable boundary satisfies SRR-002 | 329 positions total; CPM-MOD-002 255→208 trades; 2024 44/26, 2025 41/17 | Favorable-year top-N fragility remains; 2024/2025 top-5 in hostile macro context | 2024 +8501; 2025 +4490; 2021 -2154; 2022 -972; 2023 -3924 | 2023 continuation-dominated: MFE 4.26 vs 406 (2024) | CPM-MOD-002: 2021 MTM MaxDD 22.18% → 10.59% | OHLCV boundary attribution paused; no SRR-002-compliant boundary; evidence preserved | `OHLCV_BOUNDARY_ATTRIBUTION_PAUSED`; `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT` |
| Direction D | Mechanism is structurally distinct from CPM-1 and not a Direction A variant; MTC-006 had enough trades/winners | MTC-006 rejected: net -262.57, PF 0.985, win rate 15.83%, realized DD 26.22%, MTM DD 29.78%; no clean applicability boundary | 417 trades; 66 winners | Severe: top-1 removal -3021.88; top-3 -5788.16; top-5 -7331.08 | 2024 strong positive, but 2022/2025 severe negative; no stable boundary | Avg MFE 127.05, avg MAE -48.07, avg giveback 115.56; cost/churn dominate | MTM DD 29.78% | Direction A overlap 29.50%; `NO_CLEAR_CPM_DRIFT`; still fails as pullback-continuation after costs/DD/top-N | `REJECTED_FROZEN_BASELINE` |
| Short-side breakdown continuation | Structurally distinct from A/C/CPM/D; 0% overlap with Direction A; 0% overlap with Direction C; clean OHLCV-only frozen run completed | SSD-003 rejected: net -1699.88, PF 0.317, win rate 4.35%, realized DD 24.88%, MTM DD 26.98%; one winner; no clean applicability boundary | 23 trades; 1 winner | Extreme: top-1 removal -2488.50; top winner 100% of gross | 2021 strongly negative; 2022-2024 no trades; 2025 single-winner concentrated | Avg MFE 232.78, avg MAE -70.49, avg giveback 263.28; giveback exceeds MFE | MTM DD 26.98% | Direction A overlap 0.00%; Direction C overlap 0.00%; CPM/D overlap 4.35% each; not pullback drift; rejected on own evidence | `REJECTED_FROZEN_BASELINE` |
| VEI (volatility expansion / impulse participation) | Overlap gates passed (A 27.1%, C 2.5%); net +630.49; PF 1.21; trade/winner floors met; 2022-2025 positive; follow-through filters 49% false starts | Independent signals net -329.02 PF 0.86; all positive PnL from Direction A overlap echo; top-3 removal -286.85; 88% time-exit; cost drag 60.2% | 118 trades; 56 winners | Top-1 +237 net excl.; top-3 -286.85 | 2021 negative (-70.09); 2022-2025 positive but modest | Avg MFE +76.10, avg MAE -50.31, avg giveback +62.67 | MTM DD 4.91% | Direction A 27.1%; Direction C 2.5%; D 18.6%; CPM 4.2%; SSD 0.8%; independent signals negative | `PAUSE_FRAGILE` |
| 15m auxiliary layer | May support execution timing under frozen 4h thesis; LTF-002 role frozen for execution timing only | CPM-1 15m direct migration had too many trades and poor quality; Direction D rejection blocks using 15m timing as pullback rescue | Not run for current auxiliary role | Not known; requires stricter top-N | Not known | Not known | Not known | Pullback-entry version belongs to pullback-continuation family and cannot bypass CPM/D history | Candidate - inspect-only execution layer; not Level 3 ready |

### 5.2 Evidence Interpretation

Direction A is now the strongest current strategy research asset, supported by
positive cross-asset sparse trend evidence across ETH, BTC, and SOL. After P1,
it should be framed as `CROSS_ASSET_SMART_BETA_TREND_TIMING /
POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`, not as pure
breakout alpha. The frozen Donchian20 → EMA60 4h lifecycle mechanism transfers
beyond ETH — this is not an ETH-specific artifact. DIRA-EH-001 confirms ETH: 173 trades, 34
winners, net +3,001.66, PF 1.517, payoff ratio 6.20:1. DIRA-XA-003 confirms
BTC: 159 trades, 40 winners, net +2,517.17, PF 1.477; SOL: 158 trades, 44
winners, net +4,018.80, PF 1.790. All three assets pass the SRR-002 sparse
trend acceptance band. Top winners are thesis-consistent and span four+
macro regimes across all assets. The mechanism appears to capture crypto-wide
structural 4h trend lifecycle payoff.

However, critical blockers remain. All three assets fail top-5 removal — this
is a universal fragility pattern. 2023 dominates BTC and SOL results (BTC
95.7%, SOL 70.5%) — extreme year concentration. No validated pre-observable
applicability boundary exists (SRR-002 not met). Direction A is reclassified
from `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING / NON_RUNTIME` to
`POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`.
Cross-asset positive evidence strengthens research confidence but does not
authorize runtime, small-live, portfolio construction, or further empirical
work. Direction A is standalone trend capture; not a CPM rescue and not a
pullback-continuation module.

The current Direction A research question has shifted. The question is no
longer simply "does it work on ETH?" Cross-asset frozen diagnostics support
the mechanism across ETH/BTC/SOL, so the next research questions are:

1. Are cross-asset winners independent or synchronized?
2. How statistically reliable is PF around 1.5?
3. Is the edge in breakout entry, EMA60 exit, beta timing, or risk shape?

External quant feedback is incorporated as advisory input into a staged
diagnostic roadmap, not as authorization for a vol targeting or portfolio
route. P0 evidence-strength diagnostics must be completed before any P1/P2
work. P2 vol targeting is risk-shape diagnosis only; it is not deployment
planning and must not be interpreted as small-live readiness.

DIRA-P1 edge-source attribution classifies Direction A as
`P1_MIXED_EDGE_SOURCE`: random-entry controls support only partial Donchian20
entry alpha across ETH/BTC/SOL, while buy-and-hold / time-in-market
decomposition classifies all three assets as `SMART_BETA_TIMING`. The edge is
best read as a mixture of breakout selection, EMA60 lifecycle management, and
crypto beta timing. P0 remains inconclusive because winner episodes are
partially shared and PF confidence has material uncertainty. This does not
create a pre-observable applicability boundary and does not change non-runtime
status.

The next valid research question is risk shape: can a small-capital,
mid/low-frequency implementation around the Owner's approximate 3wU capital
context use conservative sizing to make the mechanism tolerable after
accounting for slippage, funding, correlated losses, exposure concentration,
and drawdown tolerance? P2 risk-shape diagnostics are eligible only with
separate Owner approval. P2 does not imply runtime or small-live readiness and
must not be treated as portfolio/router implementation.

DIRA-P2 risk-shape diagnostics classify Direction A as
`P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`. Conservative fixed-risk,
vol-normalized sizing, and exposure caps improve tolerability directionally,
but shared-episode concentration and top-winner dependence remain. Future path
classification is `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN`, which authorizes
nothing by itself; it only means a future docs-only design plan may be proposed
after separate Owner approval. Direction A remains non-runtime and non-small-live.

Direction C proves structural differentiation is possible, but also proves that
lower overlap alone is not enough. A distinct signal set with too few winners
and worse concentration remains insufficient.

CPM-1 proves a module may have applicable-market evidence without deployment
permission. CPM-MOD-002 addresses 2021 high-volatility damage; H5 macro context
partially explains 2022 (multi-dimensional 1D separation confirmed, 3D
warmup-caveated). But 2023 continuation failure remains unexplained under OHLCV
— the dominant failure mode is invisible before entry. No pre-observable
applicability boundary satisfies SRR-002. OHLCV boundary attribution is now
paused. CPM-1 remains non-runtime and non-small-live. Future CPM work is
limited to Owner-approved paths: Option A (pause, current default) or Option C
(docs-only extra-data inspect, reserved not authorized). No further OHLCV
feature mining is authorized.

Direction D is now a result, not a candidate question. MTC-006 shows that the
EMA60 value-zone / EMA20 resumption mechanism is structurally distinct but
empirically rejected: enough trades and winners, yet negative net, PF below 1,
high DD, and severe top-N fragility. This lowers the priority of the
pullback-continuation family.

15m remains a candidate auxiliary layer only for execution timing under a
frozen 4h thesis. It must not be used to rescue Direction D or reopen pullback
entry under a lower-timeframe label.

Short-side 4h breakdown continuation is now a rejected frozen baseline, not a
candidate question. SSD-003 shows that the OHLCV-only confirmed-swing-low
breakdown + continuation confirmation mechanism was structurally distinct from
all prior modules (0% Direction A/C overlap) but empirically rejected: net
PnL -1699.88, PF 0.317, 23 trades, 1 winner, and extreme top-winner fragility.
2021 was strongly negative, 2022-2024 had no trades, and 2025 depended entirely
on one winner. The rejection is not because of family drift; it is a pure
evidence-quality failure of the specific frozen concept.

VEI (volatility expansion / impulse participation) is now a paused frozen
baseline, not a candidate question. VEI-003 shows that bar-level impulse
detection (range expansion + close-location + follow-through) is structurally
distinct from Direction A (27.1% overlap) and Direction C (2.5% overlap) — the
overlap gates passed. But the 85 independent signals (no Direction A/C overlap)
are net negative (-329.02, PF 0.86). All positive PnL comes from the 33
signals that overlap with Direction A (+959.51). VEI's bar-level energy
detection is an echo of Direction A's trend capture, not an independent profit
source. Top-3 winner removal turns system negative (-286.85). The mechanism
is distinct; the profit source is not.

---

## 6. Family Management

### 6.1 Family Assignments

| Family | Members | Management rule |
| --- | --- | --- |
| Main Trend Capture / breakout | Direction A, B-D1 comparator | Preserve evidence; no micro-variants |
| Main Trend Capture / volatility-state | Direction C | Preserve as structurally distinct but paused |
| Non-pullback / impulse capture | VEI (volatility expansion / impulse participation) | Preserve as PAUSE_FRAGILE; no variants |
| Short-side / two-sided directional | Rejected short-side breakdown continuation (SSD-003) | Archived; no rescue; future short-side work requires new direction refresh |
| Pullback-continuation | CPM-1, rejected Direction D, any future 15m pullback-entry role | Lower priority; no upgradeable candidate currently |
| Lower-timeframe auxiliary | 15m execution-timing layer under frozen 4h thesis | Candidate docs-only layer; not a pullback rescue path |

### 6.2 Mandatory Family Rules

- CPM-1, Direction D, and any future 15m pullback-entry concept belong to the
  broad pullback-continuation family.
- Direction D is not identical to CPM-1 and did not show clear CPM drift, but
  its MTC-006 rejection still counts against the family because it failed as a
  pullback-continuation mechanism after costs/DD/top-N.
- 15m execution timing is not automatically pullback-continuation; 15m
  pullback-entry is.
- Direction C and Direction A are structurally different, proven by 14.3%
  overlap, but C is paused because evidence is thin and concentration worsened.
- Short-side breakdown continuation is a rejected frozen baseline with its own
  independent evidence failure (0% Direction A/C overlap). It does not belong to
  the pullback-continuation family, the Main Trend Capture family, or any other
  existing family. Future short-side work must be re-proposed through a new
  Owner-approved direction refresh.
- VEI is a PAUSE_FRAGILE non-pullback bar-level impulse concept. It belongs to
  its own family (non-pullback / impulse capture). It is not a Direction A
  variant (overlap 27.1%) or Direction C variant (overlap 2.5%), but its
  independent signals are net negative. Future VEI variants are prohibited.
  Future impulse-participation work requires a new Owner-approved direction
  refresh with a clearly different mechanism.
- Direction A/B-D1 should not continue through D2/D3/D4, overlays, or entry
  micro-variants.

### 6.3 Conditional Priority Changes

CPM-MOD-002 does not close the pullback-continuation family, but it only
partially strengthens a narrow 2021 high-volatility damage hypothesis. It does
not validate CPM-1 dynamic enablement.

MTC-006 materially lowers pullback-continuation priority. Direction D was a
clean frozen Level 3 run with enough sample, no A-variant stop, and no clear
CPM drift. It still failed net/PF/DD/top-N. The family currently has no
upgradeable candidate.

Any future pullback-continuation direction must first show a clearly different
mechanism and a pre-observable applicability boundary before Level 3 is even
requested. It must not be a Direction D parameter, zone, EMA, confirmation, or
15m timing rescue.

If 15m pullback-entry later shows the same poor signal quality as CPM-1 15m
direct migration or the same churn/cost fragility as Direction D, it should
reinforce family pause. It should not trigger a new lower-timeframe branch.

---

## 7. 15m / Sub-1h Candidate Layer

SMA-001 preserves SR-001 and LTF-002's 15m classification:

> **Candidate - inspect-only lower-timeframe execution layer, not immediate
> mainline.**

LTF-002 freezes the default 15m role as:

> **Execution timing under a frozen 4h parent thesis.**

Current rules:

- No 15m backtest.
- No 15m strategy script.
- No backtester modification.
- No runtime/profile/risk modification.
- No 15m experiment.
- No 15m pullback-entry Level 3.
- No 15m entry-timing rescue for Direction D.
- No immediate 15m mainline.
- No new data pipeline.

If 15m advances at all, the first step is:

1. data QA on existing 15m ETH data;
2. inspect-only role definition;
3. 4h+15m relationship definition.

Preferred 15m role order:

| Role | Current fit |
| --- | --- |
| Execution timing under 4h thesis | Best conceptual fit |
| 4h main trend + 15m precision entry | Not current default; would need new Owner approval |
| Risk compression / smaller-stop entry | Plausible but high churn/stop-out risk |
| Independent strategy main timeframe | Not current-stage mainline |

The old CPM-1 ETH 15m evidence rejects direct CPM-1 15m migration. It does not
reject all possible 15m auxiliary-layer research. MTC-006 additionally rejects
using 15m entry timing as a Direction D rescue path.

---

## 8. Next Candidate Ordering

| Rank | Candidate next step | Information gain | Main risk | Authorization | If it fails, closes or weakens |
| --- | --- | --- | --- | --- | --- |
| 1 | Pause pullback-continuation empirical experiments | Prevents rescue branches after CPM partial evidence and Direction D rejection | Slower pullback-family progress | Level 1/2 decision | Preserves rejected/paused evidence state |
| 2 | Strategy Research Direction Refresh | Searches for non-pullback / non-continuation mechanisms at inspect level | May find no viable mechanism | Level 1/2 docs-only inspect | Could redirect research away from exhausted families |
| 3 | Other non-pullback direction inspect | May escape pullback-continuation family limits | Unknown mechanism; needs clean inspect | Level 1/2 inspect first | Depends on future mechanism |
| 4 | 15m execution-timing docs-only maintenance | Keeps LTF-002 role/caveat boundaries clear without empirical work | Can tempt premature 15m entry rescue | Level 1/2 docs-only if no backtest/script | Closes nothing empirically |
| 5 | Pause all experiments | Prevents overfit branch generation | Slower empirical progress | Level 1/2 decision | Preserves evidence state while avoiding bad tests |

Recommended order:

1. Pause pullback-continuation empirical experiments.
2. Do not start CPM-MOD-003, Direction D follow-up, or 15m pullback-entry.
3. If Owner wants new research optionality, run a Strategy Research Direction
   Refresh or a non-pullback / non-continuation inspect.
4. Keep 15m only as docs-only execution-timing auxiliary maintenance unless a
   future parent-thesis task is separately authorized.
5. Keep small-live gate closed.

---

## 9. Level 3 Admission Review

### 9.1 Candidate Review Table

| Candidate | Mechanism clear? | Non-parameter-search? | Ex-ante applicability hypothesis? | Stop conditions? | Information gain? | Closes hypothesis rather than spawning branch? | Current Level 3 state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CPM-MOD-002 | Completed: one ATR-percentile gate on frozen CPM-1 | Yes; clean frozen diagnostic completed | Partially supported: 2021 high-volatility loss cluster; unsupported: 2023 boundary | No stop condition violated | High historical value; no immediate runtime value | Strengthened narrow hypothesis but did not validate full CPM enablement | Completed; no CPM-MOD-003 authorized |
| Direction D | Completed: EMA60 value-zone + EMA20 resumption baseline | Yes; clean frozen Level 3 research-only run completed | Not supported by MTC-006; no clean ex-ante boundary identified | No CPM drift or A-variant stop, but failed net/PF/DD/top-N | High historical value; no continuation value | Closed the frozen Direction D baseline rather than spawning a rescue branch | `REJECTED_FROZEN_BASELINE`; no follow-up authorized |
| Short-side breakdown continuation | Completed: confirmed swing-low support breakdown + continuation confirmation + squeeze/stop exit | Yes; clean frozen Level 3 research-only run completed | Not supported by SSD-003; no clean ex-ante boundary; 2021 negative, 2022-2024 no trades, 2025 single-winner | No family drift (0% A/C overlap), but failed net/PF/DD/top-N/winner count | High historical value; closed the frozen short-side concept | Closed the frozen short-side breakdown baseline; not a rescue branch generator | `REJECTED_FROZEN_BASELINE`; no follow-up authorized |
| VEI (volatility expansion / impulse participation) | Completed: 1.5×SMA20 expansion + 0.75 CLV + follow-through + EMA60 trend + 5-bar hold + 2×ATR14 stop | Yes; clean frozen Level 3 research-only run completed | Overlap gates passed (A 27.1%, C 2.5%) but independent signals net negative; no independent alpha proven | No old-path drift by overlap gate, but profit comes from Direction A echo; top-3 removal -286.85 | High information gain: proved mechanism distinctness but not independent alpha | Closed the bar-level impulse distinctness hypothesis as PAUSE_FRAGILE; not a rescue branch generator | `PAUSE_FRAGILE`; no follow-up authorized |
| 15m empirical layer | Role frozen only as execution timing under frozen 4h thesis | No empirical pullback-entry role authorized | Not yet for empirical work | Data caveats, role drift, cost/slippage, intrabar, top-N, parent-thesis alignment | Unknown | Not yet; pullback-entry would risk branch generation after CPM/D failures | Not admissible; no 15m pullback-entry Level 3 |
| Direction A variants | Mechanism known | No; would be micro-variant rescue | No new clean hypothesis | Existing fragility stop already hit | Low | No; likely branch generation | Not admissible |
| Direction C threshold adjustment | Mechanism known | No; would be post-result sensitivity | No clean pre-result hypothesis | Existing thin evidence stop hit | Low | No; likely parameter rescue | Not admissible |

### 9.2 Admission Rules

Future Level 3 requires:

- clear mechanism structure;
- one frozen diagnostic or baseline;
- no parameter search;
- pre-observable applicability hypothesis;
- explicit stop conditions;
- no post-hoc no-trade gate;
- no runtime/profile/risk/backtester-core change;
- enough information gain to change future routing;
- a closure statement explaining what failure will close or weaken.

If failure would only create a new branch, the candidate is not Level 3
admissible.

---

## 10. Explicit Non-Authorization

SMA-001 does not authorize:

- backtests;
- research scripts or adapters;
- parameter sweeps;
- runtime/profile/risk/backtester-core changes;
- small-live approval;
- strategy promotion;
- strategy router, portfolio engine, or regime engine;
- new data pipelines;
- CPM rescue or CPM-MOD-003;
- a second CPM volatility threshold;
- realized-volatility replacement experiment;
- composite M0 score;
- E4 soft or hard label;
- position sizing treatment;
- Direction D parameter rescue;
- Direction D zone, EMA, or confirmation search;
- Direction D 15m entry-timing rescue;
- pullback-family router;
- 15m experiments;
- 15m pullback-entry Level 3;
- interpreting CPM-MOD-002 as small-live readiness;
- interpreting MTC-006 or any positive window as small-live readiness;
- interpreting any mapped object as a runtime candidate;
- SSD-003 variants;
- short-side breakdown threshold or support lookback rescue;
- bearish Direction A mirror variants;
- bearish Direction C rescue;
- failed-rally value-zone short;
- short-side 1h/15m timing rescue;
- short-side funding/OI rescue;
- interpreting SSD-003 rejection as permanent short-side closure;
- VEI variants (expansion threshold, lookback, CLV, EMA, holding period, ATR multiplier);
- VEI Direction A rescue;
- VEI Direction C rescue;
- VEI pullback-entry rescue;
- VEI 1h/15m timing rescue;
- VEI funding/OI rescue;
- interpreting VEI PAUSE_FRAGILE as a runtime candidate or small-live readiness signal;
- CPM-1 changes (code, config, parameters);
- CPM-MOD-003 or any new CPM gate variant;
- CPM-2 or any CPM direction extension;
- any new CPM backtest, empirical diagnostic, or parameter sweep;
- CPM threshold optimization or ATR sweep;
- CPM runtime use or small-live;
- CPM strategy rescue or lower-timeframe rescue;
- CPM extra-data rescue without named hypothesis satisfying SRR-002 Sec 6;
- CPM CVD/order-flow data work;
- CPM router/regime/portfolio work;
- interpreting OHLCV boundary attribution pause as deployment readiness.

---

## 11. Owner Summary

### 11.1 Current Classifications

| Object | Classification |
| --- | --- |
| Direction A | `CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`; strongest current research asset; cross-asset validated (ETH + BTC + SOL); partial entry alpha plus smart beta timing; P2 risk-shape diagnostics eligible with separate Owner approval; no variants, overlays, timing rescue, parameter changes, runtime, small-live, or portfolio implementation |
| Direction C | `INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE`; paused |
| CPM-1 | `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT / OHLCV_BOUNDARY_ATTRIBUTION_PAUSED`; OHLCV boundary attribution paused; evidence preserved; no runtime/small-live; no further OHLCV feature mining |
| Direction D | `REJECTED_FROZEN_BASELINE`; MTC-006 clean frozen Level 3 run rejected |
| Short-side breakdown continuation | `REJECTED_FROZEN_BASELINE`; SSD-003 clean frozen Level 3 run rejected |
| VEI (volatility expansion / impulse participation) | `PAUSE_FRAGILE`; VEI-003 clean frozen Level 3 run completed; independent signals negative; all positive PnL from Direction A echo |
| 15m / sub-1h auxiliary layer | Candidate - inspect-only execution layer under frozen 4h thesis; not pullback-entry Level 3; not immediate mainline |

### 11.2 CPM-MOD-002 Evidence Update

CPM-MOD-002 changed:

- CPM-1 is no longer merely an unverified dynamic-enablement idea. It has one
  clean frozen diagnostic showing that an ex-ante ATR percentile gate can avoid
  part of a 2021 high-volatility loss cluster.
- The 2021 damage hypothesis is narrower and better supported: PnL improved
  -1992.49 -> -1059.11 and MTM MaxDD improved 22.18% -> 10.59%.
- 2024/2025 preservation risk was reduced for this one frozen gate because no
  2024/2025 baseline trades were disabled.

CPM-MOD-002 did not change:

- It did not identify the 2023 failure boundary.
- It did not validate CPM-1 as a runtime candidate.
- It did not satisfy small-live readiness.
- It did not prove pullback-continuation modules can be safely enabled and
  disabled in general.
- It did not raise Direction D to automatic Level 3.

### 11.2b CPM OHLCV Boundary Closeout (CPM-CLOSE-001)

CPM-CLOSE-001 changed:

- CPM-1 OHLCV boundary attribution is now paused, not merely strengthened-but-incomplete.
- The full 12-step attribution chain has been consolidated: favorable regime review, artifact audit, MOD-001, MOD-002, ABI-001, FCX-001, CPA-001, CMC-001, H5RA-001, and SRR-002 methodology upgrade.
- H5 macro context provides one robust partial axis: multi-dimensional 1D separation for 2022 (d1_dist_ema200 gap 31.96, d1_ema50_above_ema200 gap 74.8pp, d1_ema200_slope_20d gap 7.54) with partial 2021 mod-ATR support.
- 3D EMA200 separation is warmup-caveated (20.2% of 2022; 0% of 2021).
- Severe contradictions: 2024 top-5 and 2025 top-5 winners enter in hostile macro context; 2023 non-hostile context but 83.3% lose.
- 2023 continuation failure remains the dominant unexplained mode (MFE 4.26 vs 406; no credible pre-observable proxy found under OHLCV).
- No SRR-002-compliant pre-observable applicability boundary exists.
- All 17 research lines are closed (CPM-MOD-003, CPM-2, ATR sweep, bar range gate, CHOP, Hurst, H3 composite, 3D/1D EMA200 gate, H5 empirical diagnostic, E4, Pinbar variants, TP/SL, 15m rescue, router, portfolio, extra-data rescue).
- Owner decision: Option A recommended (pause and preserve evidence); Option C reserved (docs-only extra-data inspect, not authorized).

CPM-CLOSE-001 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not permanently close CPM-1 research; a new Owner-approved path could reopen.
- It did not authorize CPM-1 changes, gates, backtests, diagnostics, parameter sweeps, runtime use, small-live, strategy rescue, or extra-data work.
- It did not authorize creating an extra-data task card.

### 11.3 MTC-006 Evidence Update

MTC-006 changed:

- Direction D is no longer a candidate waiting for Level 3. It is a completed,
  clean frozen baseline result with final classification `REJECT`.
- The failure was not a thin-sample failure: MTC-006 produced 417 closed trades
  and 66 winners.
- The failure was evidence-quality failure: net PnL -262.57, PF 0.985, win
  rate 15.83%, realized MaxDD 26.22%, MTM MaxDD 29.78%, top-1 removal
  -3021.88, top-3 removal -5788.16, and top-5 removal -7331.08.
- Direction D is not a Direction A variant by stop rule: Direction A overlap
  was 29.50%.
- Direction D did not show clear CPM drift, but it still failed as a
  pullback-continuation mechanism after costs, drawdown, and top-N fragility.
- Pullback-continuation family priority is now lower, and the family has no
  upgradeable candidate.

MTC-006 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not identify a clean ex-ante applicability boundary for Direction D.
- It did not authorize Direction D parameter rescue, zone search, EMA search,
  confirmation search, or 15m entry timing rescue.
- It did not authorize 15m pullback-entry as a workaround.

### 11.4 SSD-003 Evidence Update

SSD-003 changed:

- Short-side breakdown continuation is no longer a candidate waiting for
  inspect. It is a completed, clean frozen Level 3 result with final
  classification `REJECTED_FROZEN_BASELINE`.
- The failure was not because of family drift: Direction A overlap was 0%,
  Direction C overlap was 0%, CPM-1 and Direction D overlap were each 4.35% of
  SSD trades. The mechanism was structurally distinct.
- The failure was evidence-quality failure: net PnL -1699.88, PF 0.317,
  win rate 4.35%, 23 trades, 1 winner, realized MaxDD 24.88%, MTM MaxDD 26.98%.
- 2021 was strongly negative (16 trades, zero winners, -2067.59 net).
- 2022-2024 had no closed trades at all.
- 2025 had one winner producing +367.71; not an independent favorable-year base.
- The non-pullback direction queue's first-rank short-side inspect is now closed
  for the specific breakdown-continuation mechanism.

SSD-003 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not permanently close all possible future short-side research; a new
  Owner-approved Level 1/2 direction refresh with a clearly different mechanism
  could reopen the space.
- It did not authorize SSD-003 variants, alternate lookbacks, bearish A/C
  mirror, failed-rally value-zone short, 1h/15m timing rescue, or funding/OI
  rescue.

### 11.5 VEI-003 Evidence Update

VEI-003 changed:

- VEI is no longer an active Rank 1 non-pullback candidate. It is a completed,
  clean frozen Level 3 result with final classification `PAUSE_FRAGILE`.
- The overlap gates passed: Direction A 27.1% (< 50%), Direction C 2.5%
  (< 50%). The mechanism is structurally distinct from both.
- But the 85 independent signals (no Direction A or C overlap) are net
  negative: -329.02, PF 0.86.
- All positive PnL (+630.49) comes from the 33 signals overlapping Direction A
  (+959.51). VEI's bar-level impulse detection is an echo of Direction A's
  trend capture, not an independent profit source.
- Top-3 winner removal turns system negative (-286.85).
- 118 trades, 56 winners — floors met. 2022-2025 all positive. But
  independent alpha is not demonstrated.
- The non-pullback immediate candidate queue (SRD-002 Ranks 1 and 2) is now
  exhausted: Rank 1 VEI is PAUSE_FRAGILE, Rank 2 short-side is
  REJECTED_FROZEN_BASELINE.

VEI-003 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not permanently close all possible future impulse-participation
  research; a new Owner-approved Level 1/2 direction refresh with a clearly
  different mechanism could reopen the space.
- It did not authorize VEI variants (expansion threshold, lookback, CLV, EMA,
  holding period, ATR multiplier), Direction A/C rescue, 1h/15m timing rescue,
  funding/OI rescue, or router/portfolio/regime proposals.

### 11.5b Direction A Evidence Hardening (DIRA-EH-001)

DIRA-EH-001 changed:

- Direction A is reclassified from `PAUSE_FRAGILE` to
  `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING / NON_RUNTIME`.
- 173 trades, 34 winners, net +3,001.66, PF 1.517, payoff ratio 6.20:1.
- Top winners are thesis-consistent and span four distinct macro regimes
  (2021-Q1, 2023-Q1, 2024-Q1, 2025-Q3). No single year or event monopolises
  the tail.
- Loss tail is shallow and bounded: worst single loss -133.30.
- 166 EMA60 exits (+3,829.03) / 7 initial stops (-827.37); the EMA60 lifecycle
  exit is the profit engine.
- TE-001 nine-layer winner concentration review applied. Structurally positive
  evidence confirmed; not accidental or data-mined.
- Top-3 removal net negative (-443.91); top-5 removal -1,493.33. Negative
  top-N removal remains deployment blocker.
- No validated pre-observable applicability boundary. SRR-002 standards not met.
- Direction A is standalone trend capture; not a CPM rescue and not a
  pullback-continuation module. VEI's positive PnL is an echo of Direction A
  (27.1% overlap), not independent alpha.
- Preserve Direction A as the cleanest current sparse trend evidence asset.
- No Direction A variants, overlays, timing rescue, or parameter changes are
  authorized.

Owner decision note:

- **Option A — Preserve** (recommended): Direction A remains positive sparse
  trend evidence; no further immediate research task.
- Option B / TE full review is not auto-triggered. Requires separate Owner
  approval.
- Option C / applicability-boundary study is not auto-triggered. Requires
  separate Owner approval and SRR-002 compliance.
- Any future empirical work requires separate Owner approval and SRR-002
  compliance.

DIRA-EH-001 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not authorize Direction A variants, overlays, timing rescue, parameter
  changes, empirical runs, TE execution, runtime use, small-live use, or
  strategy rescue.

### 11.5c Direction A Cross-Asset Frozen Diagnostic (DIRA-XA-003)

DIRA-XA-003 changed:

- Direction A is reclassified from `POSITIVE_SPARSE_TREND_EVIDENCE /
  NEEDS_TE_HARDENING / NON_RUNTIME` to
  `POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`.
- Direction A now has positive cross-asset sparse trend evidence across ETH,
  BTC, and SOL. The frozen Donchian20 → EMA60 mechanism transfers beyond ETH.
- Direction A is now the strongest current strategy research asset.

**Cross-asset summary table:**

| Asset | Trades | Winners | Net PnL | PF | Payoff Ratio | Top-N Fragility | Classification |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| ETH/USDT:USDT | 173 | 34 | +3,001.66 | 1.517 | 6.20:1 | Top-3 negative; Top-5 negative | POSITIVE_SPARSE_TREND_EVIDENCE |
| BTC/USDT:USDT | 159 | 40 | +2,517.17 | 1.477 | 4.39:1 | Top-3 NEGATIVE (−687.93); Top-5 NEGATIVE | BTC_POSITIVE_SPARSE_TREND_EVIDENCE |
| SOL/USDT:USDT | 158 | 44 | +4,018.80 | 1.790 | 4.64:1 | Top-3 POSITIVE (+380.21); Top-5 NEGATIVE | SOL_POSITIVE_SPARSE_TREND_EVIDENCE |

**Key observations:**

- All three assets pass the SRR-002 sparse trend acceptance band.
- All three assets fail top-5 removal — universal fragility pattern.
- SOL passes top-3 removal (+380.21); ETH and BTC fail top-3 removal.
- 2023 is the strongest year for all three assets — regime-dependent pattern.
- 2022 and 2025 are negative for both BTC and SOL — consistent.
- BTC has highest year concentration (2023 = 95.7% of total net).
- SOL has lowest MaxDD (4.49% realized, 6.44% MTM).
- No data artifacts identified in top winners across any asset.

**Current Owner interpretation:**

- Recommended current action: Preserve Direction A as positive cross-asset
  sparse trend evidence. Do not promote. Do not run further diagnostics
  immediately.
- Cross-asset evidence strengthens research confidence but does not solve
  SRR-002 Standard 1 (pre-observable applicability boundary).
- Year concentration (2023 dominance) must be explicitly noted.
- Any future empirical work requires separate Owner approval.

DIRA-XA-003 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not validate a pre-observable applicability boundary.
- It did not authorize Direction A variants, parameter optimization,
  additional asset backtests, runtime use, small-live use, TE execution,
  CPM reopening, portfolio work, router work, regime gate research, or
  strategy rescue.

**Completion:** Direction A is archived as positive cross-asset sparse trend
evidence, pause-fragile and non-runtime. This update does not authorize
Direction A changes, further diagnostics, parameter optimization, portfolio
work, runtime use, small-live use, TE execution, CPM reopening, or strategy
rescue.

### 11.5d Direction A P0/P1/P2 Diagnostic Roadmap (DIRA-P0-PLAN)

DIRA-P0-PLAN changed:

- Direction A is explicitly recorded as the strongest current strategy research
  asset, while remaining `PAUSE_FRAGILE / NON_RUNTIME`.
- External quant feedback is incorporated into Direction A as staged evidence
  diagnostics, not as strategy redesign.
- The staged roadmap is:
  - **P0 - Evidence Strength:** immediate next stage after Owner approval.
    Purpose: effective independent observation count, winner episode overlap,
    and PF confidence / uncertainty. Authorized P0 diagnostics are winner
    timing overlap and bootstrap PF CI only.
  - **P1 - Edge Source Attribution:** blocked until P0. Purpose: entry alpha vs
    exit management and alpha vs beta timing. Planned diagnostics are random
    entry + EMA60 exit control and buy-and-hold / time-in-market
    decomposition.
  - **P2 - Risk Shape:** reserved. Purpose: risk normalization study only,
    with no deployment implication and no portfolio construction. Planned
    diagnostics are vol targeting risk-shape diagnosis and MFE / loser
    characterization.
- The research question now centers on whether ETH/BTC/SOL winners are
  independent or synchronized, how reliable PF around 1.5 is, and whether the
  evidence comes from breakout entry, EMA60 exit, beta timing, or risk shape.

DIRA-P0-PLAN did not change:

- It did not authorize more assets, Direction A variants, parameter
  optimization, regime gates, vol targeting implementation, portfolio/router
  work, runtime, small-live, TE execution, CPM reopening, extra-data work, or
  strategy rescue.
- It did not authorize P1 or P2 execution. P1 remains `BLOCKED_BY_P0`; P2
  remains `RESERVED`.
- It did not reinterpret P2 vol targeting as deployment planning or small-live
  readiness.

### 11.5e Direction A P1 Edge-Source Attribution (DIRA-P1)

DIRA-P1 changed:

- Owner authorized P1 attribution-only diagnostics after P0:
  random entry + EMA60 exit control and buy-and-hold / time-in-market
  decomposition.
- Random-entry control results classify ETH, BTC, and SOL as
  `ENTRY_ALPHA_PARTIAL`. Direction A generally outperforms matched random
  entries, but not decisively enough across all assets to isolate pure
  Donchian20 entry alpha.
- Buy-and-hold / time-in-market decomposition classifies ETH, BTC, and SOL as
  `SMART_BETA_TIMING`. Direction A is not simple full buy-and-hold exposure,
  but crypto beta timing and EMA60 lifecycle management explain a material
  share of the result.
- Combined P1 classification: `P1_MIXED_EDGE_SOURCE`.
- Recommendation: Owner decision required.

DIRA-P1 did not change:

- It did not create a runtime candidate.
- It did not satisfy small-live readiness.
- It did not validate a pre-observable applicability boundary.
- It did not authorize P2 automatically.
- It did not authorize Direction A changes, variants, parameter optimization,
  additional assets, portfolio/router work, vol targeting, runtime use,
  small-live use, TE execution, CPM reopening, or strategy rescue.

### 11.5f Direction A Roadmap After P1

Post-P1 roadmap update changed:

- Direction A current classification is updated to
  `CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE /
  PAUSE_FRAGILE / NON_RUNTIME`.
- Direction A should no longer be framed as pure breakout alpha. Donchian20
  entry contributes partial alpha, but the broader mechanism is trend beta
  timing plus EMA60 lifecycle exposure management.
- Completed stages are now cross-asset frozen diagnostic, P0 evidence strength
  diagnostics, and P1 edge-source attribution.
- The next eligible stage is P2 risk-shape diagnostics, subject to separate
  Owner approval.
- P2's valid research question is whether a small-capital, mid/low-frequency
  context can use conservative sizing to make the mechanism tolerable after
  accounting for slippage, funding, correlated losses, exposure concentration,
  and drawdown tolerance.

Post-P1 roadmap update did not change:

- It did not authorize P2 execution by itself.
- It did not authorize runtime, small-live, portfolio implementation,
  router/regime engine, parameter optimization, more assets, TE execution,
  CPM reopening, or strategy rescue.
- It did not imply runtime or small-live readiness.

### 11.5g Direction A P2 Risk-Shape Diagnostic (DIRA-P2)

DIRA-P2 changed:

- Owner authorized empirical risk-shape diagnostics using existing
  ETH/BTC/SOL Direction A trades only.
- Scenarios evaluated existing baseline, equal-capital basket, fixed-risk
  sizing at 0.25% / 0.50% / 1.00% of total research capital, 20-day
  realized-vol normalized sizing, max concurrent exposure caps, and asset risk
  contribution caps.
- P2 classification: `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`.
- Future path classification: `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN`.
- Recommendation: proceed only to a docs-only small-live design plan if the
  Owner separately authorizes it.
- Key read: conservative risk shaping improves tolerability, especially lower
  fixed-risk / vol-normalized sizing and max-2 exposure cap, but top-winner
  dependence and shared crypto-wide episode concentration remain.

DIRA-P2 did not change:

- It did not create a runtime candidate.
- It did not authorize small-live.
- It did not authorize portfolio implementation.
- It did not validate a pre-observable applicability boundary.
- It did not authorize Direction A changes, variants, parameter optimization,
  TE execution, CPM reopening, or strategy rescue.

### 11.6 Recommended Next Step

Recommended next step:

1. Use SMA-001/SMA-004 as the current routing map.
2. Pause pullback-continuation empirical experiments. CPM-1 OHLCV boundary
   attribution is now paused with evidence preserved.
3. Do not start CPM-MOD-003, CPM-2, Direction D follow-up, or 15m
   pullback-entry.
4. Do not derive VEI variants or promote backlog candidates without fresh
   inspect.
5. If Owner wants new research optionality, prefer a Strategy Research Reset /
   Direction Refresh that starts from the full evidence state (Direction A
   POSITIVE_SPARSE_TREND_EVIDENCE / NON_RUNTIME, Direction C
   INSUFFICIENT_EVIDENCE, Direction D REJECTED, SSD-003 REJECTED, VEI
   PAUSE_FRAGILE, CPM-1 OHLCV paused).
6. CPM-1 future work limited to Owner-approved paths: Option A (pause, current
   default) or Option C (docs-only extra-data inspect, reserved not authorized).
   Do not create an extra-data task card without explicit Owner approval.
7. Keep 15m only as docs-only execution-timing auxiliary maintenance unless a
   future parent-thesis task is separately authorized.
8. Keep small-live gate closed.

### 11.7 Recommendation Reason

VEI-003 changed the non-pullback direction queue from "VEI active Rank 1" to
"queue exhausted." Both non-pullback immediate candidates have been inspected:
VEI is PAUSE_FRAGILE (independent signals negative), and short-side is
REJECTED_FROZEN_BASELINE (one winner, negative net). No immediate non-pullback
candidate remains.

The correct next step, if strategy research continues, is a Strategy Research
Reset or Direction Refresh. This reset should ask whether the hypothesis space
itself needs reframing — whether the current OHLCV-only 4h framework has
exhausted its ability to produce a module with a validated, pre-observable
applicability boundary. It should not be a continuation of VEI or a promotion
of backlog candidates without fresh inspect.

### 11.8 Owner Level 3

Owner Level 3 is required for:

- any CPM follow-up after CPM-MOD-002;
- any 15m empirical research run;
- any future pullback-continuation idea, and only after it proves a clearly
  different mechanism plus a pre-observable applicability boundary at inspect
  level;
- any future non-pullback direction, and only after a new Level 1/2 direction
  refresh produces a clearly different mechanism.

Owner Level 3 is not required for:

- this map;
- docs-only 15m execution-timing role/caveat maintenance, if no backtest or
  script is run;
- docs-only Strategy Research Reset / Direction Refresh.

This update does not recommend immediate Level 3. No direction has a current
Level 3-eligible candidate. CPM follow-up is paused. 15m pullback-entry is
not admissible. VEI is PAUSE_FRAGILE with no follow-up authorized.

### 11.9 Prohibitions

Do not run backtests, write scripts, sweep parameters, modify runtime/profile/
risk/backtester core, approve small-live, design router/portfolio/regime
systems, introduce a data pipeline, start CPM-MOD-003, test another volatility
threshold, replace ATR with realized volatility, add composite M0/E4/sizing
treatments, rescue CPM, rescue Direction D, search Direction D zone/EMA/
confirmation variants, use 15m entry timing to rescue Direction D, start a
pullback-family router, start 15m pullback-entry, start 15m experiments from
this document, start SSD-003 variants, rescue short-side breakdown continuation
through alternate lookbacks, bearish A/C mirror, failed-rally value-zone short,
1h/15m timing, or funding/OI rescue from this document, start VEI variants
(expansion threshold, lookback, CLV, EMA, holding period, ATR multiplier),
rescue VEI through Direction A/C, use 1h/15m timing to rescue VEI, use
funding/OI to rescue VEI, or interpret VEI PAUSE_FRAGILE as runtime/small-live
readiness. Do not interpret Direction A cross-asset positive evidence as runtime
readiness, small-live readiness, promotion eligibility, or portfolio construction
authorization. Do not run additional asset diagnostics, parameter optimization,
regime gate research, router work, portfolio work, or strategy rescue without
separate Owner approval. Do not interpret POSITIVE_CROSS_ASSET_SPARSE_TREND_
EVIDENCE as deployment gate pass. Do not create Direction A variants, Direction
A overlays, Direction A entry/stop/exit micro-variants, Direction A E-A overlay
rescue, Direction A timing rescue, or Direction A parameter changes. CPM-1
OHLCV boundary attribution pause does not authorize CPM-1 changes, CPM-MOD-003,
CPM-2, new CPM gates, CPM empirical diagnostics, CPM backtests, CPM parameter
sweeps, CPM threshold optimization, CPM runtime use, CPM small-live, CPM
strategy rescue, CPM extra-data work without named hypothesis satisfying
SRR-002 Sec 6, CPM CVD/order-flow work, CPM router/regime/portfolio work, or
interpreting pause as deployment readiness.

### 11.10 CPM-1 Future Option Note

Future CPM work is limited to Owner-approved paths only:

- **Option A:** Pause and preserve evidence — current default. OHLCV boundary
  attribution is paused. Research evidence is preserved. No empirical work.
- **Option C:** Docs-only extra-data dependency inspect — reserved, not
  authorized. Would require named hypothesis satisfying SRR-002 Sec 6 before
  any empirical work.

Do not create an extra-data task card in this update.

### 11.9 Small-Live Readiness

Small-live readiness gate is still unmet.

There is no runtime candidate and no deployable small-live strategy.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial SMA-001 strategy module applicability map | Codex |
| 2026-05-07 | SMA-002 update: archived CPM-MOD-002 evidence; CPM-1 changed to partially strengthened but incomplete applicability hypothesis; CPM follow-up paused by default | Codex |
| 2026-05-07 | SMA-003 update: archived MTC-006 Direction D rejection; lowered pullback-continuation family priority; blocked Direction D and 15m pullback-entry rescue paths | Codex |
| 2026-05-07 | SSD-004 update: archived SSD-003 short-side breakdown continuation rejection; added short-side family row; blocked all SSD-003 rescue paths; updated non-pullback direction queue | Claude |
| 2026-05-08 | CPM-CLOSE-001 update: CPM-1 OHLCV boundary attribution paused; CPM-1 classification updated to OHLCV_BOUNDARY_ATTRIBUTION_PAUSED; H5 macro evidence preserved; 2023 continuation failure remains unexplained; no further OHLCV feature mining authorized; future work limited to Owner-approved Option A (pause) or Option C (reserved extra-data inspect) | Claude |
| 2026-05-08 | DIRA-EH-001 update: Direction A reclassified to POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING / NON_RUNTIME; evidence matrix updated with full trade metrics and 9-layer winner concentration review; Owner decision note added (Option A preserve recommended); prohibitions updated for Direction A variants/overlays/empirical runs; preserved as cleanest sparse trend evidence asset | Claude |
| 2026-05-08 | DIRA-XA-003 update: Direction A reclassified to POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME; cross-asset frozen diagnostic completed (BTC +2,517.17 PF 1.477, SOL +4,018.80 PF 1.790); mechanism transfers across ETH/BTC/SOL; evidence matrix updated with cross-asset metrics; cross-asset summary table added; 2023 year concentration noted; prohibitions updated for portfolio/router/regime work; Direction A is now strongest current research asset | Claude |
| 2026-05-08 | DIRA-P0-PLAN update: Direction A P0/P1/P2 diagnostic roadmap recorded. P0 evidence-strength diagnostics are winner timing overlap and bootstrap PF CI. P1 edge-source attribution remains blocked by P0. P2 risk-shape diagnostics remain reserved and non-deployment. No Direction A changes, variants, parameter optimization, portfolio work, runtime, small-live, TE execution, CPM reopening, or strategy rescue authorized | Codex |
| 2026-05-08 | DIRA-P1 update: Direction A P1 edge-source attribution completed after Owner authorization. Random-entry controls classify ETH/BTC/SOL as ENTRY_ALPHA_PARTIAL. Buy-and-hold / time-in-market decomposition classifies ETH/BTC/SOL as SMART_BETA_TIMING. Combined P1 classification: P1_MIXED_EDGE_SOURCE; recommendation Owner decision required. No P2, portfolio, vol targeting, runtime, small-live, TE, CPM reopening, or strategy rescue authorized | Codex |
| 2026-05-08 | Direction A post-P1 roadmap update: classification updated to CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME. Direction A is no longer framed as pure breakout alpha. P2 risk-shape diagnostics are the next eligible Owner-approved stage. Runtime, small-live, portfolio implementation, router/regime engine, parameter optimization, more assets, TE execution, CPM reopening, and strategy rescue remain blocked | Codex |
| 2026-05-08 | DIRA-P2 update: Direction A P2 risk-shape diagnostic completed after Owner authorization. Classification: P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME. Future path: ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN, docs-only and not automatic. Conservative risk shaping improves tolerability but shared-episode concentration remains. No Direction A changes, portfolio implementation, runtime, small-live, TE execution, CPM reopening, or strategy rescue authorized | Codex |
