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

# SRB-001 — Strategy Research Re-entry Batch 1 v2

**Task ID:** SRB-001
**Date:** 2026-05-09
**Status:** Owner draft / Pending Codex read-only inspect
**Authorization Level:** Level 1/2 — docs-only
**Source:** Owner methodology reassessment after SRR-001, SRR-002, SCDM-001, SRD-001/002, CPM-1 OOS failure chain, VEI-003 overlap echo closure, SSD-003 rejection, Direction D rejection
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a strategy research re-entry brief. It defines the
methodology shift, top candidate hypothesis, parking-lot items, and a Codex
inspect request.

It is not:

- a backtest request;
- a parameter search;
- a Level 3 research authorization;
- a strategy script or adapter;
- a runtime/profile/risk/backtester-core change;
- a strategy promotion or small-live admission review;
- a rescue of any paused or rejected module;
- a router, portfolio, or regime engine design.

Binding current state:

- There is no runtime candidate.
- There is no deployable small-live strategy.
- The small-live readiness gate remains unmet.
- SRR-002 is the accepted methodology baseline.
- All SRR-002 prohibitions remain in force.

---

## 1. Core Methodology Shift

### 1.1 From Entry-Signal-First to Regime-Hypothesis-First

The single most important change in this re-entry batch.

**Previous approach (CPM-1 through VEI-003):**

```
Design entry signal → Backtest → Evaluate equity curve → OOS → Fail → Change signal or add filter
```

This approach produced six frozen baselines (CPM-1, Direction A, C, D,
SSD-003, VEI-003). All found some signal structure. None produced a validated
pre-observable applicability boundary. The maximum common blocker (SRR-001
§8.2) was not "which entry next" but "when to trade vs when not to trade."

**New approach:**

```
Write regime hypothesis (valid / invalid market states)
  → Verify regime classification has intuitive validity on historical data
    → Within valid regime, test one frozen entry signal
      → Evaluate per-regime, not aggregate
        → If signal fails in "should-earn" regime, hypothesis is dead
```

### 1.2 What This Means Concretely

Before any entry signal is frozen, the following must be defined:

1. **Valid-state hypothesis:** A named, pre-observable market state where the
   strategy is expected to earn. Must be computable from information at time t.

2. **Invalid-state hypothesis:** Named market states where the strategy is
   expected to lose or should not trade. Must also be pre-observable.

3. **"Should earn / should lose" scenarios:** At least two historical periods
   for each, identified before any empirical check on the entry signal.

4. **Kill switch:** If the entry signal is net negative in the "should earn"
   periods, the hypothesis is dead. No parameter rescue. No filter addition.

### 1.3 Why This Is Not SRR-002 Option A (Applicability Boundary Research)

SRR-002 Option A proposed: "Do not search for a new entry. Identify whether
existing fragile positives have pre-observable valid and invalid states."

SRB-001 is adjacent but distinct:

- SRR-002 Option A would retroactively study Direction A/C/CPM-1 evidence to
  find boundaries. That carries high post-hoc fitting risk (SRR-002 §2.2).
- SRB-001 proposes writing the regime hypothesis first, then evaluating a
  signal inside that regime. The regime is the primary hypothesis; the entry
  is secondary.
- SRB-001 does not rescue Direction A, C, or CPM-1. It does not reuse their
  parameters, thresholds, or exit rules. If the top candidate happens to
  capture some of the same trend moves as Direction A, that is expected
  (both target ETH trends), but the research object is the regime boundary,
  not the entry signal.

### 1.4 Relationship to Existing Evidence

This methodology shift is supported by, not contradicted by, existing evidence:

| Evidence source | What it supports |
| --- | --- |
| CPM-1 2021 OOS failure | Entry-first without regime boundary → catastrophic in "should earn" bull year. 46/74 SL-only, 16-11-9 loss streaks. Root cause: EMA50 lag in mid-year correction and post-ATH distribution. Regime blindness, not signal weakness. |
| CPM-MOD-002 ATR gate | A single volatility gate improved 2021 by +933, cut MTM DD from 22% to 10.6%. Evidence that regime awareness has value. But post-hoc and incomplete (2023 unchanged). |
| VEI-003 overlap echo | Bar-level impulse detection found signals but zero independent alpha. Suggests the "when" matters more than the "what" for ETH mid-frequency. |
| Direction A sparse trend evidence | Positive net, PF 1.42, 172 trades, thesis-consistent top winners. But top-3 removal negative, year concentration. The trend signal exists; the deployment blocker is applicability boundary. |
| M0 ecology proxy model | Found loss-predictive features: ema_4h_slope, recent_72h_return, realized_volatility_24h, distance_to_donchian_20_high. These are regime-adjacent features, not entry features. |

---

## 2. Top Candidate: Higher-Timeframe Trend Persistence with Overextension Avoidance

### 2.1 Name and Abbreviation

**HTPA-1:** Higher-Timeframe Trend Persistence with Overextension Avoidance

### 2.2 Edge Claim (Strategy Hypothesis)

```
Edge Claim:
  When ETH is in a confirmed higher-timeframe (daily or 4h) uptrend
  that is NOT overextended (not post-parabolic, not post-ATH distribution,
  not in high-volatility chop),
  participating in trend continuation (not pullback low-buy, not breakout chase)
  with a trend-structure exit
  should produce positive expected value.

The edge source is:
  Crypto trends persist longer than random because of reflexive momentum,
  narrative cycles, and retail participation cascades. But this persistence
  is regime-dependent: it breaks down in distribution, post-ATH reversals,
  and high-volatility chop where the same momentum signals produce whipsaws.

The strategy earns by:
  Staying in valid trends longer than the median participant,
  not by timing entries precisely.
```

### 2.3 How HTPA-1 Differs from Existing Directions

| Dimension | HTPA-1 | Direction A | CPM-1 | Direction D |
| --- | --- | --- | --- | --- |
| Primary research object | Regime boundary (valid vs invalid trend state) | Entry signal (Donchian/EMA structure break) | Entry signal (1h pinbar after pullback) | Entry signal (value-zone pullback resumption) |
| Entry philosophy | Participate in persistence, not time the entry | Enter on structure break | Enter on pullback reversal pattern | Enter on zone touch + confirmation |
| Overextension handling | Explicit non-trade condition (defined before entry) | Not addressed | Not addressed (EMA50 lag was the failure mode) | Not addressed |
| Exit philosophy | Trend-structure break (to be specified) | EMA60 close-break | Fixed TP/SL | Trend structure / time |
| Regime hypothesis | Written before any signal test | Not written; boundary was sought post-hoc | Not written; ATR gate was post-hoc | Not written |
| Key risk | Collapses into Direction A with added filter | — | — | — |

### 2.4 Anti-Collapse Guard

HTPA-1's biggest risk is collapsing into "Direction A + overextension filter."
To prevent this:

1. **The regime hypothesis must be written and evaluated independently of any
   entry signal.** The regime classifier should be assessed on whether it
   correctly identifies valid/invalid trend states, not on whether it improves
   a specific entry's PnL.

2. **The entry signal must be simple and secondary.** If the regime is valid,
   entry should be near-trivial (e.g., "enter on next 4h close in trend
   direction"). If the regime does all the work and the entry is trivial,
   that's a feature, not a bug.

3. **Direction A's specific parameters (Donchian 20, EMA60 close-break) must
   not be reused.** HTPA-1 may use similar indicator families (EMAs, ATR) but
   must not inherit Direction A's frozen spec. If HTPA-1 converges on
   identical parameters, that should be noted but is not automatically invalid
   — the difference is the research sequence (regime first vs entry first).

4. **Evaluation must report per-regime results.** If HTPA-1's valid-state
   results look identical to Direction A on the same bars, that is a collapse
   signal and must be disclosed.

5. **Any future Phase 1/2 must pre-declare Direction A collapse detection.**
   The method must check accepted-trade overlap, valid-state bar overlap,
   top-winner overlap, shared profit episode attribution, and whether HTPA-1
   provides new regime information beyond re-labeling Direction A episodes.
   No numeric overlap threshold is set in this brief.

HTPA-1 must demonstrate information gain beyond Direction A. If future
valid-state trades, top winners, or profit episodes are mainly the same
Direction A episodes, the result must be classified as collapse / old-path echo
unless the regime classifier contributes independently pre-observable
information.

### 2.5 Regime Hypothesis (Pre-Registration)

The following regime hypothesis is stated before any empirical check:

**Valid state (should trade):**
- ETH daily or 4h trend is up, using a pre-specified major-EMA slope family
  whose exact definition is not set in this document.
- Trend is not overextended, using placeholder feature families such as ATR
  percentile and distance from a major EMA. No actual percentile, distance, or
  ATR-multiple threshold is set here.
- Not in post-ATH distribution, using placeholder feature families such as
  recent ATH window and drawdown from ATH. No actual lookback window or
  drawdown threshold is set here.
- Recent market whipsaw proxy is below threshold, computed only from closed
  OHLCV bars. Examples may include EMA-cross frequency, directional
  efficiency, false-break frequency, or range expansion without net progress.
  This must not use strategy PnL, trade outcomes, or post-entry information.

**Invalid state (should NOT trade):**
- High-volatility chop: elevated ATR percentile family AND flat or reversing
  major-EMA slope family, with exact thresholds deferred.
- Post-ATH distribution: price is within a pre-specified recent-ATH window and
  has declined by a pre-specified amount, with exact thresholds deferred.
- Overextended trend: distance from a major EMA is elevated enough to imply a
  parabolic or mean-reversion-prone state, with exact thresholds deferred.
- Ranging/trendless: major-EMA slope and directional persistence families
  indicate no meaningful directional persistence, with exact thresholds
  deferred.

**Important:** The specific thresholds are placeholders. Codex read-only
inspect must NOT set thresholds. Codex may only assess whether the proposed
feature families are plausible regime discriminators and whether prior evidence
makes them post-hoc contaminated. If Owner later approves a separate Phase 1, a
frozen regime-classifier spec must define thresholds before any data check.

### 2.5a Post-Hoc Contamination Disclosure

HTPA-1's feature families are partially motivated by prior CPM-1, M0 ecology,
Direction A, and broader reset evidence. This does not invalidate the brief,
but it raises post-hoc contamination risk.

Any future Phase 1 proposal must disclose:

- which feature families came from prior failure analysis;
- which feature families are independently motivated by the HTPA-1 edge claim;
- which prior evidence could make a feature family contaminated;
- how the frozen classifier spec avoids selecting thresholds, windows, or
  labels after seeing historical partitions.

Codex read-only inspect may assess whether feature families are plausible
regime discriminators and whether they are contaminated by prior evidence.
Thresholds, windows, coverage rules, and labels must be frozen separately
before any data application.

### 2.6 "Should Earn / Should Lose" Scenarios

Defined before any empirical check:

**Should earn:**

| Period | Why |
| --- | --- |
| 2021 Q1 candidate, caveated | Important should-earn candidate because ETH had strong trend persistence. Not unambiguously clean: CPM-1 2021 evidence shows stress pockets and later Q1/Q2 loss clustering. Future scenario treatment may need a pre-specified sub-period split, such as Jan–early Feb vs late Feb–Mar, but no data check is authorized now. |
| 2023 Q4 – 2024 Q1 | ETH recovery trend from ~$1,600 to ~$4,000. Clear directional persistence with moderate volatility. |

**Mandatory mixed-regime challenge:**

| Period | Why |
| --- | --- |
| 2023 | 2023 is not optional. CPM-MOD-002 did not improve 2023, while Direction A evidence around 2023 may be positive but concentrated / fragile. HTPA-1 must state before any empirical check whether 2023 should be invalid, mixed, or partially valid. If HTPA-1 cannot classify 2023 coherently, Phase 1 should not proceed. |

**Scenario quality rule:**

A should-earn scenario must be pre-specified as a concrete historical period
with a concrete regime rationale. Vague conditional scenarios are not
acceptable. If 2024 Q4 – 2025 Q1 is retained in a future revision, the brief
must state the exact reason it is hypothesized to be valid using only
pre-observable market-state logic. No data check is authorized now.

**Should lose (expected, not a failure):**

| Period | Why |
| --- | --- |
| 2021 May–Jul (mid-year correction) | Post-ATH distribution, high-volatility chop. HTPA-1's invalid-state filter should prevent most entries here. If it trades and loses, that's a regime failure. |
| 2022 H1 (bear market) | Downtrend. Long-only strategy should be flat or have minimal exposure. Small losses from false trend signals are acceptable. |
| 2022 H2 – 2023 H1 (range/chop) | Trendless, low directional persistence. Should not trade much. |

**Kill switches:**

| Condition | Conclusion |
| --- | --- |
| Net negative in 2021 Q1 (Jan–Apr) in valid-state trades | Regime hypothesis does not identify valid trends → dead |
| Net negative in 2023 Q4 – 2024 Q1 in valid-state trades | Same |
| Positive only because of one single trade | Top-1 fragility → same as Direction A, not a new result |
| Valid-state trade count falls below the pre-specified minimum in a separately approved Phase 2 spec | Regime filter is too restrictive, insufficient sample → dead |

### 2.7 What Success Looks Like

HTPA-1 succeeds if:

1. The regime classifier produces valid/invalid partitions that have intuitive
   market-state meaning (not just "good years vs bad years").
2. Valid-state trades have positive net PnL, PF > 1.0, and survive top-3
   removal.
3. Invalid-state trades are either not taken or are net negative (confirming
   the regime boundary is real).
4. The valid-state result is not a subset of Direction A's existing wins
   (overlap accounting per SRR-002 §3).
5. The "should earn" periods are net positive, the "should lose" periods are
   flat or mildly negative.

### 2.8 What Failure Closes

If HTPA-1 fails:

- It closes the hypothesis that pre-observable OHLCV regime boundaries can
  meaningfully partition ETH trend states for mid-frequency trading.
- It does NOT close all future trend research (higher timeframes, different
  assets, or non-OHLCV data might still work).
- It does NOT authorize a rescue variant (HTPA-2 with different thresholds).
  Any follow-up requires a new Owner-approved Level 1/2 inspect.

---

## 3. Short-Side Position: Parking Lot / Boundary Challenge Only

### 3.1 Current Status

Short-side research is not in the current batch. The immediate priority is
establishing a valid regime-hypothesis framework on the long side.

No short-side active research is authorized in Batch 1.

### 3.2 What Is NOT Concluded

- CPM-1 short mirror failure does NOT prove all short-side strategies lack
  edge. It proves that mirroring a long-side pullback-continuation signal
  for shorts does not work.
- SSD-003 rejection (ETH 4h OHLCV-only short-side breakdown continuation)
  closes one specific mechanism, not all short-side research.

### 3.3 Future Short-Side Framing

If short-side research reopens, it should be framed as:

- **Resistance Rejection / Failed Breakout Short** — not pinbar short, not
  CPM mirror, not breakdown continuation.
- The hypothesis would be: "Failed breakouts at structural resistance produce
  short-duration, high-probability short opportunities."
- This requires its own Level 1/2 inspect, its own regime hypothesis, and its
  own failure closure statement, all under separate Owner approval and its own
  brief.
- The regime framework developed for HTPA-1 (valid/invalid state
  partitioning) should be reusable for short-side research.

### 3.4 Natural Bridge

If HTPA-1's regime classifier successfully identifies "invalid-for-long"
states, some of those states may be natural candidates for short-side
research. The mapping would be:

```
HTPA-1 invalid state "post-ATH distribution" → potential short-side valid state
HTPA-1 invalid state "overextended trend" → potential short-side valid state
```

This is a future research bridge, not a current authorization.

---

## 4. Funding / OI Position: Future Qualifier Only

### 4.1 Current Decision

Funding/OI data is not introduced in this batch. The core problem is research
methodology and regime hypothesis, not data variable insufficiency.

No Funding/OI data pipeline is authorized or needed for this batch.

### 4.2 Rationale

| Reason to defer | Detail |
| --- | --- |
| Core problem is methodology | SRR-001/002 identify the blocker as missing applicability boundary, not missing data |
| Data quality risk | Funding/OI data pre-2020 is unreliable; historical depth varies by exchange |
| Complexity vs clarity | Adding variables before the OHLCV regime hypothesis is tested makes it harder to attribute edge |
| Post-hoc rescue risk | "Maybe funding would fix it" is exactly the rescue narrative SRR-002 §6.3 warns against |

### 4.3 Conditions for Future Introduction

Funding/OI may become legitimate as a future qualifier only (per SRR-002 §6.2)
when:

1. HTPA-1's OHLCV regime hypothesis has been tested and the specific failure
   mode is "continuation vs exhaustion ambiguity that OHLCV cannot resolve."
2. A named hypothesis states exactly how funding/OI would resolve that
   ambiguity (e.g., "extreme positive funding > X% identifies crowded longs
   that precede reversals").
3. The hypothesis is stated before examining funding/OI's empirical
   relationship with HTPA-1's outcomes.

### 4.4 Low-Risk Transition Path

If HTPA-1 establishes a valid OHLCV regime, funding rate could be proposed in
a separate future brief as a single "noise filter" (extreme funding → do not
trade). That would require separate Owner approval and a separate data-pipeline
decision. It must not be framed as "maybe funding fixes it" rescue logic.

---

## 5. Closed Paths (Inherited from SRR-001/SRD-001)

SRB-001 inherits all closures from SRR-001 §7 and SRD-001 §3. Specifically:

- No CPM rescue or CPM-MOD-003.
- No Direction A parameter rescue.
- No Direction C threshold rescue.
- No Direction D variants.
- No SSD-003 variants.
- No VEI variants.
- No 15m pullback-entry rescue.
- No 1h entry rule search.
- No overlay stacking.
- No pullback-continuation new trigger branches.
- No router / portfolio / regime engine.
- No runtime/profile/risk/backtester-core changes.

---

## 6. Possible Future Research Sequence — Not Authorized

Only Phase 0 Codex read-only inspect is requested now. Each later phase
requires separate Owner approval. A positive inspect does not authorize Phase
1, classifier construction, data checks, backtests, adapter runs, or Level 3
research.

### 6.1 Possible Future Phases

| Phase | Focus | Duration estimate | Output |
| --- | --- | --- | --- |
| Phase 0 (current) | Codex read-only inspect of this brief | 1 session | Chat-only inspect report: conflicts, overlap risks, hypothesis quality |
| Phase 1 (future only, not authorized) | Regime hypothesis specification before any data check; any later historical plausibility check requires separate approval | 2–3 sessions | Frozen regime classifier spec before data application; visual plausibility only if separately approved |
| Phase 2 | Single frozen entry signal within valid regime | 2–3 sessions | Frozen entry + exit spec; Level 3 admission check (SRR-002 §7) |
| Phase 3 | Level 3 frozen baseline run (if admitted) | 1–2 sessions | Evidence report with per-regime attribution |
| Phase 4 | Owner review and classification | 1 session | Classification decision; next step |

### 6.2 Phase 1 Detail

Phase 1 is future-only. It may be proposed only after Owner reviews the Codex
inspect, and it is not part of this task. It does NOT begin inside the inspect
and does NOT involve backtesting a strategy.

If separately approved, Phase 1 should begin with a frozen regime-classifier
spec, not immediate data application. That spec must define the feature
families, exact thresholds, lookback windows, invalid-state rules, stop
conditions, and overlap checks before any historical partition is inspected.

Any visual plausibility check requires separate Owner approval. No threshold
adjustment is allowed after seeing historical partitions.

Possible future Phase 1 work would involve:

1. Define 2–3 quantifiable market states using simple OHLCV-derived features
   (EMA slope, ATR percentile, distance-to-EMA, recent return), with all
   thresholds frozen before any data check.
2. Only if separately approved, apply the frozen classifier to 2020–2025 ETH
   4h data.
3. Only if separately approved, visually inspect: does the classifier label
   2021 Q1 as "valid"? Does it label 2021 May–Jul as "invalid"? Does it label
   2022 H1 as "invalid"?
4. If the classifier's partitions have no intuitive market-state meaning
   (e.g., it labels random periods), the regime hypothesis is too weak and
   Phase 2 should not start.
5. The classifier must already be frozen before visual plausibility. Passing a
   visual check does not authorize Phase 2.

Visual plausibility cannot adjust thresholds, windows, feature families,
coverage rules, scenario definitions, or valid/invalid labels. It can only
reject a frozen spec as implausible or pass it to the next separately approved
stage.

### 6.3 Explicit Stop Points

| After phase | Stop if |
| --- | --- |
| Phase 0 | Codex inspect finds fatal conflict with existing evidence or identifies this as a disguised rescue |
| Phase 1 | Regime classifier has no intuitive plausibility; or valid/invalid partitions violate pre-specified coverage bounds from the separately approved Phase 1 spec |
| Phase 2 | Entry signal is not structurally distinct from Direction A's frozen spec; or Level 3 admission gate (SRR-002 §7) is not satisfied |
| Phase 3 | Kill switches triggered (§2.6); or valid-state results collapse onto Direction A's existing win set |

---

## 7. SRR-002 Compliance Check

SRB-001 is aligned with SRR-002 directionally, but SRR-002 §2, §3, §4, §5,
and §7 are not yet satisfied. They can only be satisfied by future separately
approved artifacts: a frozen classifier spec, overlap plan, fragility plan,
conditional evidence plan, and Level 3 admission package.

| SRR-002 Standard | HTPA-1 Status |
| --- | --- |
| Pre-observable applicability boundary (§2) | Not satisfied. Regime hypothesis is stated before empirical check, but thresholds, windows, labels, and coverage rules must be frozen in a separately approved Phase 1 spec before any data check |
| Not post-hoc selected (§2.2) | Not satisfied. Regime features are motivated by CPM-1 failure analysis and M0 ecology; future Phase 1 must disclose contamination and freeze thresholds before data application |
| Independent alpha vs overlap echo (§3) | Not satisfied. Direction A overlap and shared-episode attribution plan must be pre-declared before any Phase 1/2 work |
| Sparse trend fragility (§4) | Not satisfied. Future valid-state fragility plan must pre-register top-N and concentration handling before Level 3 admission |
| Conditional module evidence (§5) | Not satisfied. HTPA-1 is explicitly conditional, but valid/invalid partitions and evidence plan are future-only |
| Extra-data dependency (§6) | OHLCV-only; no extra data in this batch |
| Level 3 admission gate (§7) | Not satisfied. Must satisfy all 10 requirements in a separately approved Level 3 admission package before Phase 3 |

---

## 8. Codex Inspect Request

See companion document:
`docs/ops/srb-001-codex-readonly-inspect-prompt.md`

---

## 9. Owner Summary

### 9.1 What This Document Does

- Defines the methodology shift from entry-signal-first to
  regime-hypothesis-first.
- Proposes HTPA-1 as the top candidate with explicit regime hypothesis,
  "should earn / should lose" scenarios, kill switches, and anti-collapse
  guards.
- Parks short-side as future boundary challenge, not current work.
- Defers funding/OI to future qualifier role.
- Inherits all SRR-001/SRD-001 closures.
- Requests Codex read-only inspect before any empirical work.

### 9.2 What This Document Does Not Do

- It does not authorize any backtest, script, adapter, or data pipeline.
- It does not rescue any paused or rejected module.
- It does not produce a runtime or small-live candidate.
- It does not relax any SRR-002 gate.
- It does not implement or authorize a regime classifier.
- It does not authorize Phase 1, classifier construction, data checks,
  visual plausibility checks, backtests, adapter runs, or Level 3 research.
- It does not authorize threshold setting.
- It does not authorize runtime/profile/risk/parameter changes.
- It does not authorize Claude task cards.
- It does not authorize paper, testnet, live, or small-live trading.

### 9.3 Owner Decision Required

1. **Approve or modify** the HTPA-1 hypothesis and regime features in §2.5.
2. **Approve or modify** the "should earn / should lose" scenarios in §2.6.
3. **Review** the Codex read-only inspect before deciding whether any separate
   Phase 1 proposal should be considered.

---

## 10. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-09 | Initial SRB-001 draft | Owner + Claude strategy consultation |
