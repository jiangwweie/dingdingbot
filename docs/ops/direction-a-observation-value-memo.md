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

# Direction A Observation Value Memo

**Status:** Docs-only research / Owner decision memo
**Date:** 2026-05-08
**Classification:** `OBSERVATION_VALUE_JUSTIFIED_BUT_REQUIRES_CAPITAL_EFFICIENCY_COMPARISON`
**Recommendation:** B. Continue design, but require capital-efficiency comparison before any execution decision
**Affects Runtime Automatically:** No

---

## 1. Executive Conclusion

**Does 4h Direction A still deserve continued docs-only small-live design work?**
Yes. The evidence base remains the strongest in the repo, and the conservative risk frontier shows a usable observation range.

**Is it currently worth an observation sleeve?**
Conditionally yes, under conservative sizing only (Group A scenarios). Not under moderate or aggressive sizing.

**Strongest reason to continue:**
Direction A is the only strategy in the repo with positive cross-asset sparse trend evidence across ETH/BTC/SOL, partial entry alpha attribution, smart beta timing classification, and a documented conservative risk frontier. No other candidate has this evidence stack.

**Strongest reason to pause:**
The conservative return is modest (net 4,324-9,377 on 30k research capital, 2.6%-5.9% MaxDD over 5 years), and a proper same-risk comparison against buy-and-hold and 1D spot trend benchmarks has not yet been done. Until that comparison exists, the Owner cannot judge whether the observation complexity is justified versus simply holding spot.

**Evidence still missing:**
1. Same-risk comparison: 4h Direction A (conservative) vs buy-and-hold vs 1D spot trend, on comparable capital and drawdown terms.
2. BTC+ETH-only aggregate numbers (Phase 1 candidate without SOL).
3. 1D spot trend IS/OOS temporal robustness.
4. 1D spot trend ex-SOL decomposition.

**Classification:** `B. CONTINUE_BUT_REQUIRE_CAPITAL_EFFICIENCY_COMPARISON`

---

## 2. Evidence Base Inspected

### Direction A Evidence

| File | Status | Key Classification |
|---|---|---|
| `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md` | Complete | `CROSS_ASSET_SUPPORTS_MECHANISM` |
| `docs/ops/direction-a-p0-evidence-strength-diagnostics.md` | Complete | `P0_EVIDENCE_STRENGTH_INCONCLUSIVE` |
| `docs/ops/direction-a-p1-edge-source-attribution.md` | Complete | `P1_MIXED_EDGE_SOURCE` |
| `docs/ops/direction-a-p2-risk-shape-diagnostic.md` | Complete | `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME` |
| `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md` | Complete | `POSITIVE_SPARSE_TREND_EVIDENCE` |
| `docs/ops/direction-a-small-live-design-plan.md` | Complete | `SMALL_LIVE_DESIGN_NEEDS_RUNTIME_CHECKLIST` |

### Risk Frontier Evidence

| File | Status | Key Classification |
|---|---|---|
| `docs/ops/direction-a-risk-control-return-frontier.md` | Complete | `RETURN_FRONTIER_SHOWS_USABLE_CONSERVATIVE_RANGE` |

### 1h Compressed Closed Evidence

| File | Status | Key Classification |
|---|---|---|
| `docs/ops/direction-a-1h-compressed-sandbox-diagnostic.md` | Archived | `1H_COMPRESSED_VARIANT_PARTIAL_BUT_WEAK` |

Interpretation: ETH/BTC failed, SOL weak positive. Archived. No follow-up. Not part of mainline.

### 1D Spot / Benchmark Evidence

| File | Status | Key Classification |
|---|---|---|
| `docs/ops/one-day-spot-trend-vs-buy-hold-benchmark.md` | Complete | BTC/SOL outperform buy-and-hold; ETH does not |

### Missing or Insufficient Comparison Evidence

| Missing Artifact | Status | Required Diagnostic |
|---|---|---|
| BTC+ETH-only aggregate (ex-SOL) numbers | **Missing** | Docs-only: Direction A Phase 1 BTC+ETH basket metrics |
| Same-risk comparison (4h DA vs buy-and-hold vs 1D spot) | **Missing** | Docs-only: capital-efficiency comparison at matched risk |
| 1D spot IS/OOS temporal robustness | **Missing** | Docs-only: IS 2021-2023, OOS 2024-2025 |
| 1D spot ex-SOL decomposition | **Missing** | Docs-only: BTC+ETH vs BTC+ETH+SOL basket |

---

## 3. 4h Direction A Current Research State

### ETH Baseline
- 173 trades, 34 winners, net +3,001.66, PF 1.517, payoff 6.20:1
- Win rate 19.65%, realized MaxDD 6.08%, MTM MaxDD 8.33%
- Top-3 removal: negative (-443.91); top-5 removal: negative (-1,493.33)
- Year concentration: 2024 48.8%, 2023 30.6%

### BTC Baseline
- 159 trades, 40 winners, net +2,517.17, PF 1.477, payoff 4.39:1
- Win rate 25.16%, realized MaxDD 9.95%, MTM MaxDD 11.32%
- Top-3 removal: negative (-687.93); top-5 removal: negative (-1,665.43)
- Year concentration: 2023 = 95.7% of total net

### SOL Baseline
- 158 trades, 44 winners, net +4,018.80, PF 1.790, payoff 4.64:1
- Win rate 27.85%, realized MaxDD 4.49%, MTM MaxDD 6.44%
- Top-3 removal: positive (+380.21); top-5 removal: negative (-369.78)
- Year concentration: 2023 = 70.5% of total net

### Cross-Asset Mechanism Support
- All three assets show the same sparse trend signature: low win rate (19-28%), high payoff ratio (>4:1), concentrated winners, positive net PnL under realistic costs.
- Consistent regime behavior: 2023 strongest for all three; 2022 and 2025 negative for BTC and SOL.
- The frozen Donchian20 -> EMA60 mechanism transfers across ETH/BTC/SOL.

### P0 Evidence Strength
- Classification: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`
- Winner overlap: `WINNER_EVIDENCE_PARTIALLY_SHARED` -- top-5 winners partially synchronize around crypto-wide trend windows (2023-Q1, 2023-Q4, 2024-Q1)
- Effective independent observations: ~3.5 asset-adjusted (loose), not 15 raw top-5
- Bootstrap PF: supportive at trade level (pooled p_pf_gt_1 = 0.993), but year-level BTC pf_p5 = 0.749 exposes regime risk
- Top-3/top-5 removal probabilities remain weak

### P1 Edge-Source Attribution
- Classification: `P1_MIXED_EDGE_SOURCE`
- Random-entry control: all three assets `ENTRY_ALPHA_PARTIAL` -- Donchian20 contributes but not decisively
- Buy-and-hold decomposition: all three assets `SMART_BETA_TIMING` -- EMA60 lifecycle exit and crypto beta timing are material contributors
- Time in market: ~38-39% across all assets

### P2 Risk Shape
- Classification: `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`
- Conservative risk shaping (low fixed-risk, vol-normalized, max-2 exposure cap) improves tolerability
- Top-winner dependence and shared crypto-wide episode concentration remain

### Risk-Control Return Frontier
- Conservative Group A: net 4,324-9,377 on 30k, MaxDD 2.6%-5.9%, PF 1.61-1.75
- Moderate Group B: net 8,563-18,755, MaxDD 6.1%-11.5%, PF 1.60-1.66
- Aggressive Group C: net 26,038-53,696, MaxDD 13.1%-21.0% -- `NOT_ELIGIBLE_FOR_SMALL_LIVE_DEFAULT`

### 1h Compressed Sandbox Closure
- Status: `1H_COMPRESSED_VARIANT_PARTIAL_BUT_WEAK`
- ETH/BTC failed; SOL weak positive
- Archived; no follow-up; not part of mainline

### Explicit State
- Positive evidence exists across ETH/BTC/SOL.
- Evidence is sparse: effective independent observations ~3.5, not 15.
- Top-winner dependence remains: all three assets fail top-5 removal.
- Asset winners are partially shared across crypto-wide regimes.
- PF confidence is not robust enough for deployment (year-level BTC pf_p5 = 0.749).
- Direction A is smart beta / trend lifecycle timing, not pure independent alpha.

---

## 4. Phase 1 Candidate: BTC+ETH Only

### Why BTC+ETH Is Cleaner Than BTC+ETH+SOL for Phase 1

1. **SOL is high-beta.** SOL's buy-and-hold MaxDD is 96.3%. SOL's 1D trend MaxDD is 69.6%. SOL dominates via mega-trend episodes (top-1 winner +2,273.99 = 56.6% of SOL net). Including SOL in Phase 1 risks turning the observation into a SOL trend bet.

2. **BTC+ETH reduces high-beta dominance.** P2 vol-normalized sizing reduces SOL PnL share from 32.1% (fixed-risk 0.50%) to 24.1%. But in Phase 1, excluding SOL entirely is simpler and eliminates the risk.

3. **BTC+ETH preserves the mechanism.** Both BTC and ETH show positive net PnL, PF > 1, and thesis-consistent top winners under the identical frozen rule. The mechanism evidence does not depend on SOL.

### What Is Lost by Excluding SOL

- SOL has the highest PF (1.790) and lowest MaxDD (4.49% realized) of the three assets.
- SOL is the only asset that passes top-3 removal (+380.21).
- Excluding SOL reduces total basket net PnL and removes the strongest individual asset result.
- SOL's positive evidence strengthens the cross-asset mechanism claim.

### Whether BTC+ETH Is Enough for Observation Value

**Unknown from existing artifacts.** The existing P2 and risk-frontier diagnostics used ETH+BTC+SOL baskets. No aggregate BTC+ETH-only (ex-SOL) basket numbers exist in the repo. This is a **required docs-only diagnostic** before Phase 1 can be finalized.

### Whether BTC+ETH Is Too Low-Return Under Conservative Sizing

Conceptually, if the 3-asset conservative basket (A5_fixed_050_max2) produces net 9,377 on 30k with 5.9% MaxDD, a BTC+ETH-only basket would produce less. Whether that residual is enough for observation value depends on the actual numbers, which do not yet exist.

**Required diagnostic:** Direction A Phase 1 BTC+ETH aggregate basket metrics under the same conservative scenarios (A1, A4, A5).

---

## 5. SOL Treatment

### SOL Has Positive Evidence
- Net +4,018.80, PF 1.790, payoff 4.64:1
- Passes top-3 removal (+380.21)
- Lowest MaxDD of all three assets (4.49% realized, 6.44% MTM)
- `SOL_POSITIVE_SPARSE_TREND_EVIDENCE`

### SOL May Dominate via High Beta / Mega-Trend Behavior
- Top-1 winner contributes 56.6% of SOL net PnL
- SOL buy-and-hold cumulative return: 81.492 (vs BTC 2.014, ETH 3.013)
- SOL 2023 alone contributes 70.5% of total SOL net
- SOL ecosystem revival rally (Oct-Nov 2023) produced +2,273.99 -- a single mega-trend episode

### SOL Is Phase 2 Optional Only
- Phase 1: BTC+ETH only
- SOL enabled only after successful rehearsal and only with low vol-normalized sizing plus strict SOL risk share cap (<=25% of open risk)

### SOL Requires Low Vol-Normalized Sizing
- P2 shows vol-normalized low target reduces SOL PnL share from 32.1% to 24.1%
- SOL risk share <= 25% of open risk is the design cap

### SOL Cannot Be Used to Justify Phase 1 Observation
- Phase 1 observation value must be assessed on BTC+ETH alone
- SOL's positive evidence strengthens the mechanism claim but does not justify Phase 1 inclusion

### SOL Cannot Be Allowed to Turn the Basket into a SOL Trend Bet
- Without sizing controls, SOL would dominate the basket via high-beta mega-trend episodes
- The observation must test the mechanism, not bet on SOL

---

## 6. Conservative Sizing and Risk Frontier Interpretation

### Which Tiers Support Small-Live Design

**Group A (Conservative) -- supports observation design:**

| scenario | net (30k) | ret | dd | pf | SOL_abs | class |
|---|---|---|---|---|---|---|
| A1_low_vol_norm_max2 | 4,324 | 0.144 | 2.6% | 1.752 | 0.0 | CONSERVATIVE |
| A4_fixed_025_max2 | 4,689 | 0.156 | 3.1% | 1.613 | 0.104 | CONSERVATIVE |
| A5_fixed_050_max2 | 9,378 | 0.313 | 5.9% | 1.613 | 0.104 | CONSERVATIVE |
| A3_hybrid_050_vol_adj_max2 | 8,649 | 0.288 | 5.1% | 1.752 | 0.0 | CONSERVATIVE |

**Group B (Moderate) -- research only, not recommended for observation default:**

| scenario | net (30k) | ret | dd | pf | SOL_abs | class |
|---|---|---|---|---|---|---|
| B2_fixed_100_max2 | 18,755 | 0.625 | 10.8% | 1.613 | 0.104 | MODERATE |
| B1_fixed_050_max3 | 13,424 | 0.447 | 7.4% | 1.659 | 0.406 | MODERATE |

**Group C (Aggressive) -- explicitly not recommended:**

| scenario | net (30k) | ret | dd | pf | SOL_abs | class |
|---|---|---|---|---|---|---|
| C3_fixed_200_max3 | 53,696 | 1.79 | 21.0% | 1.659 | 0.406 | AGGRESSIVE |

### Why Conservative Sizing Matters
- The Owner's capital context is ~3wU. A 21% drawdown on 30k = 6,300U -- devastating at this scale.
- Conservative scenarios keep MaxDD under 6%, which is tolerable for observation.
- Sparse trend systems can spend long periods losing; conservative sizing preserves psychological tolerance.

### Why Historical Max Return Tiers Cannot Be Used for Execution
- C3_fixed_200_max3 produces 53,696 net but with 21% MaxDD -- same sparse trend payoff amplified by leverage/aggressive sizing.
- High-return scenarios amplify the same concentrated winner structure; they do not solve top-5 fragility.
- Risk-control tuning can overfit just like strategy parameter tuning.

### Why Leverage / Aggressive Risk Is Not Approved
- Leverage amplifies correlated drawdowns during crypto-wide trend reversals.
- The mechanism is regime-dependent (2022, 2025 negative); leverage magnifies bear-market damage.
- No leverage is the default design stance.

### Why Max Return Is Not the Decision Objective
- The observation objective is to test operational integrity and mechanism behavior, not to maximize PnL.
- A few trades cannot validate a sparse trend system.
- Success = execution integrity, risk cap compliance, reconciliation reliability.

### Whether Conservative Risk Shape Still Leaves Enough Observation Value

**On 30k research capital:**
- A5_fixed_050_max2: net 9,378, MaxDD 5.9%, PF 1.613
- A1_low_vol_norm_max2: net 4,324, MaxDD 2.6%, PF 1.752

**On observation sleeves:**

| Sleeve | A1 net_U | A1 maxDD_U | A5 net_U | A5 maxDD_U | tolerable |
|---|---|---|---|---|---|
| 1500U (5%) | 216 | 39 | 469 | 88 | Both yes |
| 3000U (10%) | 432 | 78 | 938 | 176 | Both yes |
| 4500U (15%) | 649 | 117 | 1,407 | 264 | Both yes |

The 1500U sleeve under A1 produces ~216U historical net with ~39U max drawdown. This is modest but survivable. The question is whether the learning value justifies the operational complexity -- which requires the capital-efficiency comparison.

---

## 7. Capital Efficiency Question

### Owner's Core Question
If conservative 4h Direction A return is low, why not buy spot?

### Available Comparison Data

| Approach | net (30k) | MaxDD | PF | time_in_mkt | trades |
|---|---|---|---|---|---|
| **4h Direction A conservative (A5)** | 9,378 | 5.9% | 1.613 | ~38% | 490 |
| **4h Direction A conservative (A1)** | 4,324 | 2.6% | 1.752 | ~38% | 490 |
| **Buy-and-hold BTC** | 60,429 | 76.7% | -- | 100% | 1 |
| **Buy-and-hold ETH** | 90,400 | 79.4% | -- | 100% | 1 |
| **Buy-and-hold SOL** | 2,444,756 | 96.3% | -- | 100% | 1 |
| **Buy-and-hold equal-weight** | 865,195 | 97.3% | -- | 100% | 1 |
| **1D trend BTC** | 65,034 | 47.5% | 2.044 | 47.6% | 41 |
| **1D trend ETH** | 18,374 | 67.9% | 1.384 | 44.0% | 40 |
| **1D trend SOL** | 4,632,098 | 69.6% | 3.964 | 43.6% | 33 |
| **1D trend equal-weight** | 1,571,835 | 96.0% | -- | ~45% | 114 |

### Interpretation

**Why not buy spot?**
- Buy-and-hold is simpler but carries near-full crypto drawdown: BTC 76.7%, ETH 79.4%, SOL 96.3%.
- At 3wU, a 76.7% drawdown = ~23,000U loss. This is not tolerable for observation.
- Buy-and-hold has no risk management; you absorb the full bear market.

**Why not 1D spot trend?**
- 1D trend timing reduces BTC MaxDD from 76.7% to 47.5% and SOL from 96.3% to 69.6%.
- 1D trend BTC PF 2.044 is higher than 4h Direction A's 1.477.
- But 1D trend MaxDD is still 47-70% -- far higher than 4h Direction A's 5.9% under conservative sizing.
- 1D trend basket MaxDD is 96.0% -- essentially no drawdown improvement over buy-and-hold at basket level.
- 1D trend is not execution-ready: no IS/OOS validation, no ex-SOL decomposition, SOL concentration risk.

**What 4h Direction A offers that spot does not:**
- Materially lower drawdown: 5.9% vs 47-97%.
- Lower time in market: ~38% vs 100% (buy-and-hold) or ~45% (1D trend).
- Active risk management: initial stop, EMA60 exit, exposure caps.
- The tradeoff is lower absolute return and higher operational complexity.

**What is still missing:**
- A proper same-risk comparison where 4h Direction A, buy-and-hold, and 1D spot trend are compared on the same capital allocation terms.
- BTC+ETH-only 4h Direction A numbers (ex-SOL).
- 1D spot trend IS/OOS and ex-SOL decomposition.

---

## 8. Observation Sleeve Projection

For the Owner's total capital reference around 3wU:

### 5% Sleeve: ~1500U

| Scenario | net_U | maxDD_U | worst_month_U | largest_loss_U | tolerable |
|---|---|---|---|---|---|
| A1_low_vol_norm_max2 | 216 | 39 | -14 | -4 | Yes |
| A5_fixed_050_max2 | 469 | 88 | -33 | -8 | Yes |

### 10% Sleeve: ~3000U (Owner review required)

| Scenario | net_U | maxDD_U | worst_month_U | largest_loss_U | tolerable |
|---|---|---|---|---|---|
| A1_low_vol_norm_max2 | 432 | 78 | -29 | -8 | Yes |
| A5_fixed_050_max2 | 938 | 176 | -66 | -16 | Yes |

### 15% Sleeve: ~4500U (not recommended at start)

| Scenario | net_U | maxDD_U | worst_month_U | largest_loss_U | tolerable |
|---|---|---|---|---|---|
| A1_low_vol_norm_max2 | 649 | 117 | -43 | -12 | Yes |
| A5_fixed_050_max2 | 1,407 | 264 | -99 | -24 | Yes |

### Design Parameters
- Default risk per trade: 0.25% of sleeve
- Post-rehearsal risk per trade: 0.50% of sleeve (Owner approval required)
- No leverage by default
- Max concurrent positions: 2
- Correlated crypto exposure treated as one sleeve
- SOL risk share <= 25% of open risk (Phase 2 only)

This is a projection for decision-making only. It does not authorize capital allocation, execution, or live trading.

---

## 9. What Would Make Direction A Worth Observing

Continued design remains rational if:

1. **Risk-shaped drawdown materially lower than buy-and-hold.** Confirmed: 5.9% vs 76-97%. This is the strongest argument for Direction A over spot.
2. **Capital usage / time-in-market lower than buy-and-hold.** Confirmed: ~38% vs 100%.
3. **BTC+ETH evidence remains positive enough without SOL.** Unknown -- requires the ex-SOL diagnostic.
4. **Top-winner dependence acceptable for sparse trend.** Partially: all three fail top-5 removal, but the sparse trend acceptance band tolerates this under SRR-002 Section 4.4.
5. **Operational rehearsal can be no-order / low-risk.** Yes: the design plan specifies paper/live-safe rehearsal first.
6. **Observation cost is small relative to potential learning value.** Yes: at 1500U sleeve, worst-case maxDD is 39U under A1. The learning value (execution integrity, reconciliation, kill-switch testing) is high relative to capital risk.

---

## 10. What Would Make Direction A Not Worth Observing

Pause conditions:

1. **BTC+ETH evidence becomes too weak without SOL.** If the ex-SOL diagnostic shows BTC+ETH aggregate is marginal or negative under conservative sizing, the mechanism may depend too heavily on SOL.
2. **Conservative risk shape reduces return to trivial value.** If A1 net on a 1500U sleeve is ~216U over 5 years (~43U/year), the observation may not justify operational complexity.
3. **1D spot trend dominates at same or lower drawdown.** If a future 1D spot diagnostic shows comparable drawdown to 4h Direction A with higher return, the simpler approach wins.
4. **Buy-and-hold dominates on return/DD/time-in-market after fair comparison.** Unlikely given the 76-97% drawdown, but must be checked formally.
5. **Top-N dependence becomes too extreme.** If future evidence shows the mechanism cannot survive without 2023-type mega-episodes, observation value decreases.
6. **Observation requires too much runtime engineering.** If the cost of building observation infrastructure exceeds the learning value, pause.
7. **Observation cannot be separated from live-order risk.** If the rehearsal cannot be done without real orders, the risk increases.

---

## 11. Relationship to 1D Spot Trend

### How 1D Spot Should Be Used
- As a **benchmark / capital-efficiency comparison**, not as a replacement for the 4h Direction A mainline.
- Not execution-ready: high MaxDD (47-70% asset-level, 96% basket), SOL concentration, no IS/OOS validation.
- Requires IS/OOS temporal robustness and ex-SOL decomposition before strong conclusions.
- Universe definition + data coverage audit must come before expanded universe testing.

### What 1D Spot Shows
- BTC and SOL outperform buy-and-hold on risk-adjusted basis (CAGR/Calmar).
- ETH does not outperform buy-and-hold under 1D trend timing.
- 1D trend reduces time-in-market to ~44-48% and materially reduces asset-level MaxDD for BTC and SOL.
- But basket-level MaxDD (96%) is essentially unchanged from buy-and-hold (97%).

### Should Direction A Design Wait for 1D Spot Robustness?
**No.** Direction A design should continue in parallel as docs-only. The two serve different purposes:
- Direction A: active risk-managed trend timing with documented conservative frontier.
- 1D spot: passive benchmark / capital-efficiency reference line.

They are complements, not substitutes.

---

## 12. Current Recommended Research Priority

1. **Direction A Observation Value Memo conclusion** -- this document
2. **1D Spot Universe Definition + Data Coverage Audit** -- before any expanded 1D testing
3. **1D Spot IS/OOS + ex-SOL decomposition** -- robustness validation
4. **Same-risk comparison: Buy-and-Hold vs 1D Spot vs 4h Direction A** -- the missing capital-efficiency comparison
5. **Direction A small-live design continuation / pause decision** -- after items 2-4

---

## 13. Things Not To Do

Do not:
- Reopen CPM
- Continue 1h compressed sandbox
- Optimize Direction A parameters
- Change Donchian / EMA / stop / exit rules
- Add leverage experiments
- Treat SOL as Phase 1
- Use aggressive risk frontier for execution
- Create runtime strategy
- Create paper engine
- Create portfolio/router/regime infrastructure
- Activate live/testnet
- Allocate capital
- Create Claude implementation tasks

---

## 14. Final Recommendation

### Recommended Next Memo or Diagnostic

**Next:** Direction A Phase 1 BTC+ETH Aggregate Diagnostic (docs-only).
Purpose: produce BTC+ETH-only basket numbers under the same conservative scenarios (A1, A4, A5) so the Owner can assess Phase 1 observation value without SOL.

**After that:** Same-Risk Capital-Efficiency Comparison (docs-only).
Purpose: compare 4h Direction A (conservative), buy-and-hold, and 1D spot trend on matched capital terms, including MaxDD, CAGR, Calmar, time-in-market, and operational complexity.

### Whether Owner Decision Is Required Now

**Yes.** This memo classifies Direction A as `B. CONTINUE_BUT_REQUIRE_CAPITAL_EFFICIENCY_COMPARISON`. The Owner should decide:
1. Whether to authorize the BTC+ETH aggregate diagnostic.
2. Whether to authorize the same-risk comparison diagnostic.
3. Whether the current evidence stack is sufficient to continue design, or whether to pause until benchmarks are complete.

### Whether Codex Should Proceed to Any Docs-Only Next Step

Only if the Owner authorizes the next diagnostic. Codex should not proceed automatically.

### Whether Anything Should Be Paused

Nothing needs to be paused beyond the existing prohibitions. Direction A remains `NON_RUNTIME`. 1D spot remains docs-only research. The 1h compressed sandbox remains archived.

---

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-08 | Initial Direction A observation value memo | Codex |
