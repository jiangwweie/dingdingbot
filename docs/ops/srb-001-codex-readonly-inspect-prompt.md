# SRB-001 — Codex Read-Only Inspect Prompt

**Task ID:** SRB-001-INSPECT
**Date:** 2026-05-09
**Type:** Level 1/2 read-only inspect request for Codex
**Source:** `docs/ops/srb-001-strategy-research-reentry-batch-1-v2.md`

---

## Instructions for Codex

You are performing a **read-only inspect** of the Strategy Research Re-entry
Batch 1 v2 brief (`docs/ops/srb-001-strategy-research-reentry-batch-1-v2.md`).

Your role is to check for conflicts, overlap risks, disguised rescue paths,
and hypothesis quality. You are NOT implementing, backtesting, building
adapters, or modifying any runtime/profile/risk/backtester-core code.

Prioritize fatal conflicts, disguised rescue risks, overlap risks, governance
violations, and required revisions. Do not summarize every source document
unless needed for a finding.

---

## Required Reading Before Inspect

Read these documents in order. Do not skip any.

**Evidence state and methodology:**

1. `docs/ops/srr-001-strategy-research-reset-evidence-state-review.md`
2. `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`
3. `docs/ops/sma-001-strategy-module-applicability-map.md`

**Direction history:**

4. `docs/ops/strategy-candidate-direction-map-v1.md`
5. `docs/ops/srd-001-strategy-research-direction-refresh.md`
6. `docs/ops/srd-002-non-pullback-direction-map.md`

**Key failure evidence:**

7. `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
8. `docs/ops/crypto-pullback-module-v1-2021-oos-report.md`
9. `docs/ops/cpm-mod-002-cpm1-frozen-volatility-regime-gate-diagnostic-report.md`
10. `docs/ops/vei-003-volatility-expansion-impulse-participation-level3-research-report.md`
11. `docs/ops/vei-004-archive-and-direction-map-update.md`
12. `docs/ops/ssd-003-short-side-breakdown-continuation-level3-research-report.md`
13. `docs/ops/mtc-006-direction-d-structured-pullback-frozen-baseline-research-report.md`

**Direction A evidence:**

14. `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`
15. `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
16. `docs/ops/direction-a-phase1-btc-eth-aggregate-diagnostic.md`

**Current state:**

17. `docs/ops/observation-research-reset-reconciliation-snapshot-2026-05-09.md`
18. `docs/ops/project-roadmap-v2.md`

**The brief under review:**

19. `docs/ops/srb-001-strategy-research-reentry-batch-1-v2.md`

---

## Inspect Questions

Answer each question separately and explicitly. Provide evidence references
(document name + section) for each answer.

### Q1. Disguised Rescue Check

Is HTPA-1 a disguised rescue of Direction A, CPM-1, or any other paused/
rejected module?

Check specifically:
- Does HTPA-1's regime hypothesis inherit Direction A's Donchian/EMA
  parameters?
- Does HTPA-1's entry signal replicate Direction A's structure-break entry
  under a different name?
- Does HTPA-1's "overextension avoidance" replicate CPM-MOD-002's ATR
  percentile gate under a different name?
- If HTPA-1 converges on the same trades as Direction A, what is the
  information gain?
- Does the brief require future accepted-trade overlap, valid-state bar
  overlap, top-winner overlap, and shared profit episode attribution against
  Direction A before Phase 1/2?
- Does the brief avoid setting numeric overlap thresholds during inspect?

Expected answer format:
```
Rescue risk: [LOW / MODERATE / HIGH]
Evidence: [references]
Mitigation: [what SRB-001 does or should do to prevent collapse]
```

### Q2. Historical Evidence Conflict Check

Does HTPA-1's hypothesis conflict with any established negative evidence?

Check specifically:
- CPM-1's 2021 failure: does HTPA-1's regime hypothesis correctly predict
  that 2021 May–Jul is invalid? Or does it rely on features that CPM-1
  already tried (EMA slope, trend direction)?
- Direction D's rejection: does HTPA-1 avoid the same failure mode (cost/
  churn, value-zone fitting)?
- VEI-003's overlap echo: if HTPA-1 captures the same trend moves as
  Direction A, is it providing new information or repeating the echo?
- SSD-003's rejection: is the short-side parking lot position consistent
  with SSD-003's closure terms?

Expected answer format:
```
Conflict found: [YES / NO]
If YES: [specific conflict + evidence reference]
If NO: [why the hypothesis avoids the conflict]
```

### Q3. Regime Hypothesis Quality Check

Is the regime hypothesis in SRB-001 §2.5 adequate for a pre-observable
applicability boundary?

Check against SRR-002 §2.1 requirements:
- Is it computable before the trade decision? (§2.1.1)
- Is it not selected after seeing winning/losing years? (§2.1.2)
- Does it partition into non-empty valid and invalid states? (§2.1.8)
- Does the invalid state contain enough bars? (§2.1.8)
- Are the features plausible regime discriminators, or are they just
  trend-entry indicators relabeled as regime indicators?

Expected answer format:
```
Quality: [ADEQUATE / NEEDS_IMPROVEMENT / INADEQUATE]
Missing elements: [list]
Post-hoc risk: [LOW / MODERATE / HIGH]
Recommendation: [what to fix before Phase 1]
```

### Q4. "Should Earn / Should Lose" Scenario Check

Are the scenarios in SRB-001 §2.6 adequate?

Check specifically:
- Are the "should earn" periods genuinely favorable for the stated
  hypothesis, or are they cherry-picked?
- Are the "should lose" periods genuinely unfavorable, or are they
  trivially obvious (e.g., "should lose in bear market" is too easy)?
- Is 2021 Q1 a fair "should earn" test? CPM-1 failed 2021 overall,
  but was Q1 specifically a clean trend? Or did it have whipsaw episodes?
- Is 2023 represented? 2023 was a problem year for CPM-1 and
  CPM-MOD-002. HTPA-1 should state a pre-empirical stance on 2023.
- Does the brief explicitly state whether 2023 is invalid, mixed, or
  partially valid before empirical work?
- Are vague conditional periods, such as "if a clean trend existed", removed
  or converted into concrete pre-observable scenario rationales?
- Are the kill switches binding enough? Can they be gamed by adjusting
  the regime classifier to pass?

Expected answer format:
```
Scenarios: [ADEQUATE / NEEDS_IMPROVEMENT]
Missing periods: [list]
Kill switch quality: [STRONG / MODERATE / WEAK]
Recommendation: [what to add or modify]
```

### Q5. SRR-002 Compliance Gap Check

Does SRB-001 satisfy or plan to satisfy all SRR-002 standards?

Check the compliance table in SRB-001 §7 against:
- SRR-002 §2 (pre-observable applicability boundary)
- SRR-002 §3 (independent alpha vs overlap echo)
- SRR-002 §4 (sparse trend fragility)
- SRR-002 §5 (conditional module evidence)
- SRR-002 §6 (extra-data dependency)
- SRR-002 §7 (Level 3 admission gate — all 10 requirements)

Expected answer format:
```
Gaps found: [list of gaps with SRR-002 section references]
Blocking gaps: [which must be resolved before Phase 1]
Non-blocking gaps: [which can be resolved during Phase 1/2]
```

### Q6. Anti-Collapse Guard Adequacy

Are the anti-collapse guards in SRB-001 §2.4 sufficient to prevent HTPA-1
from becoming "Direction A + filter"?

Check specifically:
- Is the prohibition on reusing Direction A's parameters enforceable?
- Is the requirement for per-regime evaluation sufficient?
- What would it look like if HTPA-1 collapsed into Direction A, and would
  the guards detect it?
- Does the brief require a future pre-declared overlap / shared-episode
  attribution method without setting numeric thresholds during inspect?

Expected answer format:
```
Guard adequacy: [SUFFICIENT / NEEDS_STRENGTHENING]
Missing guard: [what to add]
Detection mechanism: [how collapse would be detected]
```

### Q7. Closed Path Violation Check

Does SRB-001 violate any explicit closure from SRR-001 §7, SRD-001 §3,
or SRR-002 §10?

Check the full prohibition lists in those sections. Flag any potential
violation, even marginal.

Expected answer format:
```
Violations: [NONE / list of potential violations]
Marginal risks: [areas that are close to violation but not crossing]
```

### Q8. Research Sequence Risk Check

Is the proposed research sequence (Phase 0–4) in SRB-001 §6 viable?

Check specifically:
- Is Phase 1 (regime classifier plausibility) doable with current data and
  tools, without building new infrastructure?
- Is the "visual plausibility" check in Phase 1 rigorous enough, or is it
  susceptible to confirmation bias?
- Does the brief prohibit visual plausibility from adjusting thresholds,
  windows, feature families, coverage rules, scenario definitions, or
  valid/invalid labels?
- Are the stop points binding?
- Is there a risk that Phase 1 drifts into an implicit backtest?

Expected answer format:
```
Sequence viability: [VIABLE / NEEDS_ADJUSTMENT]
Phase 1 rigor: [ADEQUATE / NEEDS_IMPROVEMENT]
Drift risk: [LOW / MODERATE / HIGH]
Recommendation: [what to strengthen]
```

---

## Inspect Output Format

Do not create or modify files during inspect. Return the inspect report in
chat using the title:

```
# SRB-001 — Codex Read-Only Inspect Report
```

If Owner later wants to persist it, the suggested future path is:

```
docs/ops/srb-001-codex-readonly-inspect-report.md
```

The chat report should:
- Answer all 8 questions with the requested format.
- Include a summary table of findings.
- Include a final recommendation: PROCEED / PROCEED_WITH_MODIFICATIONS /
  PAUSE / REJECT.
- If PROCEED_WITH_MODIFICATIONS, list specific modifications required
  before Phase 1.

---

## Inspect Constraints

This inspect is:
- Read-only. No file creation or modification, no code, no backtest, no
  adapter, no script.
- Docs-only. No data pipeline, no feature store, no runtime change.
- Non-promotional. A positive inspect does not authorize Phase 1. Owner
  approval is still required.
- Non-rescue. The inspect must not propose rescuing any closed module.

This inspect is NOT:
- A backtest plan.
- A Level 3 authorization.
- A strategy promotion review.
- A runtime readiness review.
- A small-live admission review.

---

## Boundary Reminder

After completing the inspect, Codex should return:

- Files read (list).
- Questions answered (8/8 or note which could not be answered and why).
- Summary finding.
- Final recommendation with conditions.
- Any out-of-scope needs discovered.

Owner reviews the inspect report before deciding whether Phase 1 proceeds.
