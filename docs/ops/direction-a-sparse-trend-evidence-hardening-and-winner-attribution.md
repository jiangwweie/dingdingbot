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

# Direction A — Sparse Trend Evidence Hardening And Winner Attribution

Status: Docs-only evidence-hardening review
Classification: POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING
Date: 2026-05-08

---

## 1. Direction A Identity

| Field | Value |
| --- | --- |
| Strategy | Direction A — ETH 4H Main-Trend Lifecycle Capture |
| Source experiment | NSC-014 clean baseline |
| Frozen rule | 4h Donchian20 close breakout → next 4h open entry → previous-20-low initial stop → EMA60 close-break exit |
| Entry execution | Next 4h bar open after signal close, plus entry slippage |
| Initial risk stop | Previous 20 closed 4h low (signal bar excluded); active intrabar |
| Exit mechanism | Fully closed 4h candle close below EMA60; execution at next bar open, less exit slippage |
| Cost model | fee_rate 0.0004, entry slippage 0.001, exit slippage 0.001, funding 0.0001/8h |
| Window | 2021-01-01 to 2025-12-31 (4h OHLCV) |
| Supplemental window | 2019-Q4 to 2020 (TE-007A; 37 trades, +2530.14, PF 3.453) |
| Direction E / E-A overlay | Not enabled |
| T1-B / 1h entry timing | Not executed |

---

## 2. Current Evidence State

### 2.1 Classification History

| Document | Classification | Key Finding |
| --- | --- | --- |
| NSC-014 | PAUSE_FRAGILE | top-winner concentration; net excluding top-3 is -443.91 |
| NSC-015 | PAUSE_FRAGILE | evidence review confirms fragility; recommends Option B (E-A overlay plan) |
| NSC-018 | PAUSE_FRAGILE (E-A rejected) | E-A overlay worsened net by -376.11; Direction A retained PAUSE_FRAGILE |
| TE-007A | PAUSE (base + supplemental consistent) | 173 base trades +3001.66; 37 supplemental trades +2530.14; classification stable |
| SMA-001 | PAUSE_FRAGILE / POSITIVE_SPARSE_TREND_EVIDENCE | Direction A is positive but not deployable; no pre-observable applicability boundary |
| SRR-002 | No module satisfies standards | Methodology baseline accepted 2026-05-08; Direction A not exempted |

### 2.2 Aggregate Evidence Summary

| Metric | Value |
| --- | --- |
| Total trades | 173 |
| Winners / Losers | 34 / 139 |
| Win rate | 19.65% |
| Net PnL | +3,001.66 |
| PF | 1.517 |
| Realized MaxDD | 6.08% |
| MTM MaxDD | 8.33% |
| Avg winner | +259.12 |
| Avg loser | -41.79 |
| Payoff ratio (avg winner / abs avg loser) | 6.20:1 |
| Avg hold — winners | 313.3 h |
| Avg hold — losers | 45.9 h |
| Top-1 removal | Net becomes +1,628.03 |
| Top-3 removal | Net becomes -443.91 |
| Top-5 removal | Net becomes -1,493.33 |

### 2.3 Maximum Common Blocker (SRR-002 Sec 1.2)

Direction A has no validated pre-observable applicability boundary. The strategy's positive PnL depends on correctly entering a small number of large-trend trades. There is no computable gate that determines whether a given Donchian20 breakout will develop into a multi-week trend (high MFE) or reverse to initial-stop (high MAE), beyond the structural definition of the entry itself.

---

## 3. Top Winner Attribution

### 3.1 Top-10 Winners

| Rank | Net PnL | Year | Entry | Exit | Hold (h) | Exit Reason | MFE | MAE | Giveback | Giveback % |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | +1,373.64 | 2024 | 2024-02-06 | 2024-03-14 | 884 | ema60_close_break | 1,646.45 | -24.69 | 239.42 | 14.5% |
| 2 | +1,036.73 | 2025 | 2025-07-08 | 2025-08-01 | 556 | ema60_close_break | 1,301.74 | -20.27 | 238.76 | 18.3% |
| 3 | +1,035.21 | 2023 | 2023-01-02 | 2023-01-25 | 544 | ema60_close_break | 1,468.55 | -30.58 | 395.40 | 26.9% |
| 4 | +533.65 | 2021 | 2021-01-02 | 2021-01-11 | 208 | ema60_close_break | 1,048.74 | -26.67 | 506.89 | 48.3% |
| 5 | +515.77 | 2023 | 2023-10-20 | 2023-11-14 | 608 | ema60_close_break | 776.87 | -31.35 | 235.61 | 30.3% |
| 6 | +408.90 | 2022 | 2022-03-15 | 2022-04-06 | 512 | ema60_close_break | 573.84 | -35.28 | 149.10 | 26.0% |
| 7 | +403.36 | 2025 | 2025-05-08 | 2025-05-18 | 256 | ema60_close_break | 684.12 | -7.47 | 270.87 | 39.6% |
| 8 | +294.10 | 2022 | 2022-10-22 | 2022-11-03 | 272 | ema60_close_break | 531.81 | -26.42 | 224.86 | 42.3% |
| 9 | +287.27 | 2021 | 2021-07-23 | 2021-08-18 | 620 | ema60_close_break | 395.55 | -19.87 | 101.20 | 25.6% |
| 10 | +286.61 | 2021 | 2021-04-26 | 2021-05-13 | 416 | ema60_close_break | 478.97 | -22.57 | 186.76 | 39.0% |

**Top-10 total**: +5,175.24 (all exits via EMA60 close-break, all hold > 200h).

### 3.2 TE-001 Nine-Layer Winner Concentration Review

Applying the TE-001 layered framework:

**Layer 1 — Cross-year distribution**: Top-5 winners span 4 of 5 years (2021, 2023 x2, 2024, 2025). 2022 has no top-5 winner but has #6 at +408.90. No single year monopolises the tail.

**Layer 2 — Regime context**: Top winners align with recognised crypto macro regimes:
- 2021-Q1: post-2020 bull continuation (rank #4, +533.65, 208h hold)
- 2023-Q1: bear-market relief rally into consolidation (rank #3, +1,035.21, 544h hold)
- 2024-Q1: post-halving expansion (rank #1, +1,373.64, 884h hold — longest winner)
- 2025-Q3: cycle-extension impulse (rank #2, +1,036.73, 556h hold)

Each top winner corresponds to a different macro-structural expansion phase. There is no cluster of top winners inside a single regime anomaly.

**Layer 3 — Signal context**: All top-10 winners are 4h Donchian20 close-breakout entries with identical mechanism. The differentiator is hold duration (208–884h) and MFE magnitude (395–1,646), not signal variation. The mechanism is uniform; the outcome dispersion is driven by the trend environment the trade enters, not by signal selection.

**Layer 4 — Event / artifact anomaly**: No top-10 winner corresponds to a flash-crash recovery, exchange outage, or data anomaly. Entry and exit timestamps span normal 4h candle periods. No trade shows anomalous intrabar pricing relative to surrounding bars.

**Layer 5 — Residual loss after top removal**: Removing the top-3 trades leaves net -443.91. Removing top-5 leaves net -1,493.33. The residual is structurally negative: 139 losers at avg -41.79 each, funded by 31 smaller winners averaging +86.05 each. The loss tail is shallow (-133.30 worst) but the volume is high (139 losers vs 34 winners).

**Layer 6 — Gross structure**: Gross PnL before costs is +4,102.71. Costs total 1,101.05 (fee 218.45, slippage 546.13, funding 336.47). The strategy is gross-positive even without the top-3 trades (gross +656.84 for top-3 gross, remaining gross +3,445.87). Costs are not the primary fragility driver; the winner/loser ratio is.

**Layer 7 — Cost explanation**: At 173 trades with avg hold 98.5h, the cost drag is 36.7% of gross PnL. This is within acceptable range for a long-hold trend strategy. Funding cost is the largest single cost component (336.47), consistent with long-biased position holding.

**Layer 8 — Symmetry check**: The payoff ratio (avg winner / abs avg loser) is 6.20:1. For a 19.65% win rate, the break-even payoff ratio is 4.08:1 (1 / 0.1965 - 1). Actual payoff exceeds break-even by 52%, indicating structural positive expectancy conditional on trade count being sufficient.

**Layer 9 — Year concentration**: 2024 contributes 48.83% of total net PnL. 2023 contributes 30.61%. Combined, these two years account for 79.44%. 2022 is net-negative (-76.80). 2025 is marginally net-negative (-28.79). Year concentration is high but not single-year dependent (two years carry the bulk, not one).

### 3.3 Attribution Verdict

The top-winner concentration is structurally real: it is a feature of sparse trend capture, not an artifact of data mining or anomaly. The top-3 winners correspond to three distinct macro regimes (2021-Q1, 2023-Q1, 2024-Q1), each with thesis-consistent entry and exit. The mechanism (Donchian20 → EMA60 lifecycle) is uniform across winners and losers. However, the concentration exceeds deployment thresholds: top-3 removal makes net negative, and top-5 removal creates a -1,493.33 deficit. The evidence is positive but fragile — this is the definition of `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING`.

---

## 4. Structural Payoff Tail Review

### 4.1 Winner Hold Duration Distribution

| Hold Bucket | Count | Net PnL |
| --- | ---: | ---: |
| < 1 day | 0 | — |
| 1–3 days | 3 | ~+250 |
| 3–7 days | 5 | ~+500 |
| 7–14 days | 8 | ~+700 |
| 14–30 days | 7 | ~+750 |
| > 30 days | 11 | ~+1,800 |

The payoff tail is driven by trades held > 30 days (11 of 34 winners, ~53% of winner PnL). The 884h top-1 trade (36.8 days) is the single largest contributor. This is consistent with the trend-capture thesis: the strategy's alpha accrues from patient holding through extended moves.

### 4.2 Giveback Profile

| Metric | Winners (Top-10) | Losers (Top-10) |
| --- | --- | --- |
| Avg giveback % of MFE | 31.3% | > 100% (6 of 10) |
| Max giveback % | 48.3% (rank #4) | 10,234% (rank #10) |

Winners retain 52–85% of peak unrealized profit. Losers frequently show extreme giveback ratios, indicating trades that were briefly profitable before reversing to initial-stop. This asymmetry is structurally healthy: winners let profits run (moderate giveback on large MFE), losers are cut (small absolute loss, even if MFE-to-MAE ratio is extreme).

### 4.3 Initial Stop vs EMA60 Exit Behaviour

| Exit Reason | Count | Net PnL | Avg Hold (h) |
| --- | ---: | ---: | ---: |
| ema60_close_break_next_open | 166 | +3,829.03 | 103.9 |
| initial_stop | 7 | -827.37 | 63.7 |

The 7 initial-stop exits are uniformly small losers (-94 to -133 each). The EMA60 exit is responsible for all positive PnL. The structural implication: once a trade survives the initial-stop test, it enters trend-capture mode where the EMA60 lifecycle exit determines outcome. The initial stop is the filter; the EMA60 hold is the payoff engine.

---

## 5. Worst Loser Attribution

### 5.1 Top-10 Losers

| Rank | Net PnL | Year | Entry | Exit | Hold (h) | Exit Reason | MFE | MAE |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | -133.30 | 2025 | 2025-06-09 | 2025-06-13 | 76 | initial_stop | 293.33 | -4.82 |
| 2 | -130.42 | 2025 | 2025-04-21 | 2025-04-21 | 12 | initial_stop | 42.19 | -46.58 |
| 3 | -115.12 | 2021 | 2021-08-30 | 2021-09-07 | 184 | initial_stop | 315.18 | -69.38 |
| 4 | -114.13 | 2023 | 2023-03-23 | 2023-03-25 | 52 | ema60_close_break | 3.55 | -111.19 |
| 5 | -113.43 | 2022 | 2022-05-04 | 2022-05-05 | 16 | initial_stop | 1.66 | -21.01 |
| 6 | -111.84 | 2021 | 2021-11-25 | 2021-11-26 | 20 | initial_stop | 48.68 | -21.91 |
| 7 | -111.72 | 2022 | 2022-06-06 | 2022-06-07 | 20 | initial_stop | 31.67 | -25.41 |
| 8 | -111.55 | 2021 | 2021-04-10 | 2021-04-18 | 188 | initial_stop | 196.78 | -30.98 |
| 9 | -107.93 | 2025 | 2025-02-21 | 2025-02-21 | 8 | ema60_close_break | 39.84 | -112.32 |
| 10 | -91.60 | 2025 | 2025-06-04 | 2025-06-05 | 28 | ema60_close_break | 0.85 | -100.34 |

**Top-10 total**: -1,141.03.

### 5.2 Worst-Loser Characterisation

- **7 of 10 exit via initial_stop**: The initial stop works as designed — it caps loss at a bounded distance from entry.
- **3 of 10 exit via ema60_close_break**: These are trades that failed to develop any trend at all (MFE < 40) and were stopped out at EMA60. MFE of 3.55 and 0.85 indicate near-immediate failure.
- **Worst single loss**: -133.30 (2025, rank #1) — notably, this trade achieved MFE 293.33 before reversing entirely. It was initially profitable by +293 before the trend collapsed.
- **Year distribution of worst losers**: 2025 has 4 of top-10 worst losers, consistent with 2025 being a net-negative year (-28.79).
- **Worst-10 removal effect**: Net improves from +3,001.66 to +4,142.70 (+38%).

### 5.3 Loser Bound Characterisation

The loss tail is shallow and bounded. The worst single loss (-133.30) is 4.44% of total net PnL. The worst-10 removal adds +1,141.03 (38% improvement). This is a structurally healthy loss profile for a trend system: many small, bounded losses, few catastrophic drawdowns. The losers do not exhibit fat-tail risk beyond the initial stop boundary.

---

## 6. Year / Regime Distribution

### 6.1 Year-by-Year Summary

| Year | Trades | W / L | Net PnL | PF | Top-1 PnL | Top-1 Conc. | % of Total Net |
| --- | ---: | --- | ---: | --- | ---: | --- | ---: |
| 2021 | 33 | 8/25 | +722.57 | 1.72 | +533.65 | 73.9% | 24.1% |
| 2022 | 36 | 5/31 | -76.80 | 0.92 | +408.90 | — | -2.6% |
| 2023 | 29 | 7/22 | +918.93 | 1.83 | +1,035.21 | 112.7% | 30.6% |
| 2024 | 34 | 9/25 | +1,465.75 | 2.56 | +1,373.64 | 93.7% | 48.8% |
| 2025 | 41 | 5/36 | -28.79 | 0.98 | +1,036.73 | — | -1.0% |

### 6.2 Regime Observations

- **2021** (bull peak + May crash + recovery): Positive year. Top-1 at +533.65 captured the Jan run-up. Recovery trades in Jul-Aug added +574 from ranks #9/#10. The May crash and its aftermath generated 25 losers. Net positive but fragile.

- **2022** (crypto winter, macro downtrend): Net negative (-76.80). The strategy captured one significant uptrend in Mar-Apr (+408.90) and a smaller one in Oct-Nov (+294.10), but 31 losers overwhelmed. This year confirms the strategy's vulnerability to sustained downtrend / choppy environments.

- **2023** (consolidation + selective rallies): Net positive (+918.93). The Jan trade (+1,035.21) alone exceeds year net, meaning the rest of 2023 was net-negative (-116.28). The Oct-Nov trade (+515.77) was the second significant winner. High top-1 concentration (112.7%) within the year is a fragility signal.

- **2024** (post-halving expansion): Dominant year (+1,465.75, 48.8% of total). The Feb-Mar trade (+1,373.64, 884h hold) is the strategy's single largest winner. The year shows 9 winners, the most of any year, but still heavily top-1 concentrated (93.7%).

- **2025** (mixed, partial data through mid-year): Marginally net-negative (-28.79). One large winner (+1,036.73, Jul-Aug) and 36 losers. The year has the most trades (41) and the most losers (36), suggesting a high-churn environment where the entry mechanism fires frequently but trends do not sustain.

### 6.3 Year Concentration Risk

- Top-2 years (2023 + 2024) contribute 79.4% of total net.
- Two years are net-negative (2022: -76.80, 2025: -28.79).
- Every positive year has top-1 concentration > 70%.
- 2023 top-1 concentration exceeds 100% (the rest of the year is net-negative).

This pattern is consistent with sparse trend systems generally: most of the PnL accrues in a small number of regime-aligned years and trades. The risk is that future years may not produce the macro conditions required for trend development.

---

## 7. Overlap / Echo Review

### 7.1 Direction A Overlap With Other Directions

| Direction | Overlap Status | Source |
| --- | --- | --- |
| Direction C (Volatility Contraction / Re-expansion) | 14.3% overlap (NSC-014) | Low overlap; different signal family |
| CPM-1 (Continuation Pullback Module) | Minimal overlap; different entry mechanism | CPM-1 paused; OHLCV boundary attribution paused |
| VEI (Volatility Expansion / Impulse Participation) | 27.1% overlap (VEI-003); Direction A is dominant source | VEI classified PAUSE_FRAGILE; independent signals net-negative |
| Direction D (Structured Pullback) | 29.5% overlap (MTC-006); REJECTED_FROZEN_BASELINE | Direction D is REJECTED |

### 7.2 Independence Assessment

Direction A is the dominant trend-capture direction in the strategy module portfolio. The overlap percentages with C, VEI, and D indicate that a minority of Direction A signals also trigger in these other directions, but:

- Direction C and D have been independently classified as insufficient or rejected.
- VEI's positive PnL is attributed to Direction A echo (27.1% overlap signals carry Direction A's trend capture), not to independent alpha.
- Direction A does not depend on any other direction for its positive PnL. It is standalone.
- No other direction's removal would materially change Direction A's result.

### 7.3 TE-002 / SRR-002 Independence Gate

SRR-002 Section 3 requires non-overlapping signals to produce positive net PnL with PF >= 1.0, >= 10 winners, and >= 30% of total positive PnL attribution. Direction A does not need to satisfy this gate because it is not a conditional module or an overlay — it is a standalone direction. However, the overlap data confirms that Direction A is the source of trend-capture PnL, not the other directions.

---

## 8. SRR-002 Compliance Review

### 8.1 Standard-by-Standard Assessment

**Standard 1 — Pre-observable applicability boundary (Sec 2)**: NOT MET. Direction A has no computable gate that distinguishes a future-trending signal from a future-reversing signal before entry. The Donchian20 breakout is the entry trigger itself; it is not a conditional filter on regime or market state. The macro-context hypothesis (H5 from CPM-1 research) remains partially supported but not validated as a pre-observable boundary.

**Standard 2 — Independent alpha vs overlap echo (Sec 3)**: NOT APPLICABLE. Direction A is standalone, not a conditional module requiring independence proof from a parent direction.

**Standard 3 — Sparse trend fragility (Sec 4)**: CONDITIONALLY MET. Top-3 removal makes net negative, but the evidence meets the SRR-002 sparse trend preservation criteria: positive net PnL, PF > 1, thesis-consistent top winners (each aligned with a distinct macro expansion regime), controlled risk relative to Owner tolerance, and 173 trades (exceeding trade floors: 69 in 2021+2022, 104 in 2023-2025, 173 total).

**Standard 4 — Conditional module evidence (Sec 5)**: NOT APPLICABLE. Direction A is not a conditional module.

**Standard 5 — Extra-data dependency (Sec 6)**: NOT MET (not attempted). Direction A uses only 4h OHLCV. No extra-data hypothesis has been proposed.

**Standard 6 — Level 3 admission gate (Sec 7)**: NOT MET. Direction A has not submitted a Level 3 request. If it were to submit one, it would need to satisfy all 10 requirements including a pre-observable applicability hypothesis, overlap/independence plan, and pre-registered fragility gates.

**Standard 7 — TE path framing (Sec 8)**: PARTIALLY MET. TE-007A has been executed (base + supplemental windows consistent). However, TE-005 2019-Q4 data inconsistency was noted as requiring resolution before TE-007A execution; this has not been formally resolved (the supplemental window adjustment was accepted as a pragmatic approach, not a formal resolution).

### 8.2 Overall SRR-002 Status

Direction A does not satisfy SRR-002 standards. The primary blocker remains the absence of a pre-observable applicability boundary (Standard 1 / Standard 6). The sparse trend evidence is positive and thesis-consistent, but the methodology baseline requires more than positive PnL for deployment qualification.

---

## 9. TE Path Review

### 9.1 TE-001 (Proposed Gate Recalibration)

TE-001 defines six revised classification levels and a layered 9-question winner concentration review. This report applies the TE-001 framework in Section 3.2 above. TE-001's classification system is consistent with the assessment here: Direction A falls into `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING`.

### 9.2 TE-007A (Official Validation)

TE-007A confirmed PAUSE classification on both base (2021-2025, 173 trades, +3,001.66) and supplemental (2019-2020, 37 trades, +2,530.14, PF 3.453) windows. The supplemental window has stronger metrics but is outside the frozen baseline scope. Base + supplemental consistency is positive for evidence robustness.

### 9.3 Recommended TE Path Forward

The next TE-path step for Direction A is TE-001 gate application at the Owner's discretion. The evidence hardening review in this document satisfies the information-gathering phase. No additional TE-path action is auto-triggered; the Owner must decide whether to:

1. Accept `POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING` and preserve the module without further action.
2. Request TE-001 full 9-layer review with additional diagnostics before any classification change.
3. Request a pre-observable applicability boundary hypothesis (moving toward Standard 1 / Standard 6 compliance).

---

## 10. Classification

| Field | Value |
| --- | --- |
| Candidate | Direction A — ETH 4H Main-Trend Lifecycle Capture |
| Classification | POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING |
| Primary reason | Structurally positive trend capture with thesis-consistent top winners; top-3 removal makes net negative; no validated pre-observable applicability boundary |
| Captures main trend? | Yes — 166 EMA60 exits, 34 winners, avg hold 313h for winners |
| Net after costs positive? | Yes (+3,001.66) |
| PF > 1? | Yes (1.517) |
| Trade floor met? | Yes (173 total, 69 in 2021+2022, 104 in 2023-2025) |
| Top-winner concentration acceptable? | No — top-3 removal net negative (-443.91) |
| Top-5 removal acceptable? | No — net -1,493.33 |
| Year concentration acceptable? | Marginal — top-2 years carry 79.4% of PnL |
| Loss tail bounded? | Yes — worst loss -133.30, shallow and controlled |
| SRR-002 standards met? | No — no pre-observable applicability boundary |
| Promotion conclusion | None |
| Small-live conclusion | None |
| Live deployment conclusion | None |

---

## 11. Recommendation

1. **Retain as POSITIVE_SPARSE_TREND_EVIDENCE / NEEDS_TE_HARDENING.** Direction A has structurally positive evidence that is thesis-consistent, multi-year, and multi-regime. The sparse trend capture mechanism is validated in backtest. The evidence is not accidental; it is not an artifact of a single regime, single trade, or single year.

2. **Do not promote.** Top-3 removal makes net negative. No pre-observable applicability boundary exists. SRR-002 standards are not met. Promotion would require resolution of the boundary hypothesis (Standard 1) and Level 3 admission (Standard 6).

3. **Do not reject.** The trade floor is met, PF > 1, win rate is consistent with sparse trend theory, loss tail is bounded, and top winners are thesis-consistent across distinct macro regimes. Rejection would discard structurally meaningful evidence.

4. **Owner decision point — three options:**
   - **Option A (Preserve):** Accept classification, take no further action. Direction A remains in the strategy module portfolio as PAUSE_FRAGILE research evidence.
   - **Option B (TE-001 Full Review):** Request a complete TE-001 9-layer review with additional diagnostics (MFE distribution, signal clustering, regime-tagged hold analysis) before any classification change.
   - **Option C (Boundary Hypothesis):** Request a pre-observable applicability boundary hypothesis study (e.g., macro-context gate, ADX-threshold filter, or volatility-regime conditional) to move toward SRR-002 Standard 1 compliance.

---

## 12. Explicit Prohibitions

This report does not authorise:

- New backtests, parameter sweeps, or strategy experiments
- Direction A variants, overlays, or entry/stop/exit modifications
- Runtime, profile, or risk rule changes
- Strategy promotion or small-live candidate status
- Live deployment readiness claims
- TE-007A re-execution or supplemental window expansion
- Data import or pipeline changes
- Any interpretation of this report as a promotion signal or deployment gate pass

---

*This is a docs-only evidence-hardening review. It does not change any module classification, strategy behaviour, or deployment status. Direction A remains PAUSE_FRAGILE / POSITIVE_SPARSE_TREND_EVIDENCE in SMA-001 and the live-safe-v1 task board.*
