# MDS-001 Target Pairing Boundary

Status: P1_OVERLAY_TARGET_PAIRING_BOUNDARY_READY
Last updated: 2026-06-16

## Scope

`MDS-001` is a research-only target-pairing boundary for metals dislocation,
PMR overlap, and session-mismatch semantics.

It is not a StrategyGroup handoff, not runtime registration, not FinalGate
input, not Operation Layer input, not exchange-write authority, not live-profile
authority, not leverage authority, and not an order-sizing default.

## Known Objective

`MDS-001` exists to prevent PMR / metal-dislocation evidence from becoming an
ambiguous universal filter. It should remain a target-specific overlay semantic
lane until evidence proves a standalone activation/disable pair.

The current useful shape is:

1. `NLPD-001` continuation labels may receive a PMR-derived disable tag.
2. `TEQ-001` momentum labels may receive a PMR-derived support tag.
3. `BTPC-001`, `DCB-001`, `THR-001`, and older 2024-2025 candidates have
   insufficient PMR overlap for any policy claim.
4. PMR / MDS standalone short remains blocked by drawdown, sample length,
   session, fill, mark/funding, product, and margin facts.

## Current Decision

| Field | Decision |
| --- | --- |
| Strategy id | `MDS-001` |
| Semantic name | Metals Dislocation Session Mismatch |
| Current status | `overlay_candidate` |
| Default mode | `observe_only` |
| Handoff state | No handoff pack |
| Runtime state | Not registered |
| Primary use | Target-specific overlay vocabulary |
| Candidate-prepare state | Blocked by research semantics |
| Execution authority | None |

## Target Pairing Policy

| Target | Evidence State | Allowed Use | Blocked Use |
| --- | --- | --- | --- |
| `NLPD-001` | PMR overlap is negative for continuation labels; non-PMR continuation improves materially in the event-study sample. | `nlpd_pmr_disable_tag` for continuation research. | Universal event blocker or executable short/fade claim. |
| `TEQ-001` | PMR-overlap TEQ events remain positive, while non-PMR TEQ events are also positive. | `teq_pmr_support_tag` and Strategy Picker context. | TEQ activation, TEQ disable filter, or universal long filter. |
| `BTPC-001` | Historical 2024-2025 window has no direct PMR coverage in current evidence. | `coverage_missing_no_policy`. | Derivatives or short-side filter claim. |
| `DCB-001` | Direct overlap sample is too small for an overlay decision. | `coverage_missing_no_policy`. | Breakout filter claim. |
| `THR-001` | Historical 2024-2025 window has no direct PMR coverage in current evidence. | `coverage_missing_no_policy`. | Theme-rotation filter claim. |
| `PMR-001` | XAG-led short/weakness evidence is useful but not standalone right-tail. | PMR context, XAG dominance disclosure, role split. | Standalone armed observation. |

## Evidence Boundary

| Evidence | Current Result | Boundary |
| --- | --- | --- |
| `pmr_overlay_target_pairing` | `NLPD-001` pairing coverage is `76.895307%`; PMR-overlap continuation is near-wipeout while non-PMR continuation is positive. | NLPD disable tag is allowed as research semantics. |
| `pmr_overlay_target_pairing` | `TEQ-001` PMR-overlap events are positive, but non-PMR events are also positive. | TEQ support tag only; no activation or disable gate. |
| `pmr_overlay_target_pairing` | `BTPC-001` and `THR-001` have `0.000000%` direct PMR overlap. | No historical PMR policy. |
| `pmr_overlay_target_pairing` | `DCB-001` direct overlap is `2.424242%`. | Sample too small; no filter claim. |
| `pmr_target_specific_overlay_classifier` | NLPD policy result is `promote_disable_fact_for_nlpd_continuation_research`. | Disable tag may be proposed as `nlpd_pmr_disable_state`. |
| `pmr_target_specific_overlay_classifier` | TEQ policy result is `keep_pmr_support_tag_not_filter`. | Support tag may be proposed as `teq_pmr_support_state`. |
| `pmr_metal_relative_spread_replay` | Simple metal-relative rules do not create promotion-ready right-tail rows. | Preserve as negative/revival vocabulary. |
| `pmr_metal_dislocation_refresh` | `pmr_metal_relative_breakdown_short_72h` is positive but below standalone right-tail gate. | Keep PMR/MDS short-weakness overlay, not standalone strategy. |

## Overlay States

| Overlay State | Meaning | Missing Behavior |
| --- | --- | --- |
| `mds_overlay_role_state` | Classifies MDS as context, disable tag, support tag, or standalone blocked. | `observe_only_no_candidate` |
| `mds_target_pairing_state` | States whether the target has enough direct PMR/MDS overlap. | `no_overlay_policy` |
| `mds_target_policy_state` | Target-specific policy such as NLPD disable or TEQ support. | `no_overlay_policy` |
| `historical_pmr_coverage_state` | Whether PMR/MDS coverage exists for older 2024-2025 candidates. | `coverage_missing_no_policy` |
| `mds_pmr_state_freshness` | Whether PMR/MDS state is recent enough for an overlay tag. | `no_overlay_tag` |
| `mds_session_mismatch_state` | Regular/off-hours/weekend and commodity-session mismatch state. | `observe_only` |
| `mds_xag_dominance_state` | Whether evidence is XAG-led rather than broad metal basket. | `block_broad_basket_claim` |
| `mds_spread_fill_state` | Spread, depth, and next-open fill suitability for metal products. | `block_promotion` |
| `mds_margin_model_state` | Exchange margin and liquidation model for metal perps. | `block_leverage_promotion` |

## Sample Overlay Packet

```json
{
  "strategy_group_id": "MDS-001",
  "version": "2026-06-16-r0",
  "status": "overlay_context_only",
  "decision": "no_candidate",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false,
  "overlay_role": "target_specific_context",
  "allowed_use": [
    "nlpd_pmr_disable_tag",
    "teq_pmr_support_tag",
    "pmr_context_tag",
    "session_mismatch_warning"
  ],
  "blocked_use": [
    "standalone_strategy_group",
    "armed_observation",
    "universal_filter",
    "finalgate_input",
    "order_authority"
  ],
  "target_policy": {
    "NLPD-001": "disable_tag_for_continuation_research",
    "TEQ-001": "support_tag_only",
    "BTPC-001": "coverage_missing_no_policy",
    "DCB-001": "sample_too_small_no_policy",
    "THR-001": "coverage_missing_no_policy"
  },
  "non_execution_flags": [
    "not_runtime_registration",
    "not_finalgate_input",
    "not_order_authority"
  ]
}
```

## Promotion Boundary

`MDS-001` must not become a standalone handoff until all of the following are
true:

1. A stable activation/disable pair is defined from signal-time facts.
2. Target-pairing coverage is enough for each target strategy family.
3. Session, product, mark/funding, spread/fill, and margin facts are attached.
4. XAG dominance is either accepted as target-specific or reduced by broader
   metal-basket evidence.
5. Standalone 1x/2x replay improves beyond overlay/support evidence.
6. Sample signal, no-signal, stale, and conflict packets exist with no-execution
   flags.

## Research Conclusion

`MDS-001` remains valuable as a semantic overlay, not as a StrategyGroup
handoff. It should be kept in the Strategy Cabinet as `overlay_candidate`.
The next evidence work is target-specific coverage expansion, PMR-state
freshness definition, and session/fill/margin fact capture for metal products.
