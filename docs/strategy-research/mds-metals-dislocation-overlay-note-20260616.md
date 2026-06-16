# MDS-001 Metals Dislocation Overlay Note

Status: ACTIVE_RESEARCH_OVERLAY_NOTE
Last updated: 2026-06-16

## Scope

`MDS-001` is a PMR-adjacent overlay note for metals dislocation and session
mismatch semantics.

It is not a StrategyGroup handoff, not a runtime registration, not a
FinalGate input, not an Operation Layer input, not an order authority, not a
live profile, and not an order-sizing default.

## Role

`MDS-001` preserves metal-market context that can help interpret or filter
other strategy families. It should not be promoted as a standalone strategy
until it has a repeatable activation/disable pair and a stronger 1x/2x replay.

The current role is:

1. PMR short/weakness context when XAG/XPT/XPD relative breakdown appears.
2. PMR session-mismatch context when regular/off-hours/weekend behavior differs.
3. TEQ support tag only when overlap evidence remains positive and selective.
4. NLPD disable tag only when PMR-state overlap is negative for continuation.

## Current Decision

| Field | Decision |
| --- | --- |
| Strategy id | `MDS-001` |
| Semantic name | Metals Dislocation Session Mismatch |
| Current status | `overlay_candidate` |
| Default mode | `observe_only` |
| Handoff state | No handoff pack |
| Runtime state | Not registered |
| Primary use | Overlay / context / disable-support vocabulary |
| Execution authority | None |

## Evidence Summary

| Evidence | Result | Interpretation |
| --- | --- | --- |
| PMR metal dislocation refresh | `pmr_metal_relative_breakdown_short_72h` has `61.335549%` full 2x, `74.904336%` best-30d 2x, `52.642224%` best-90d 2x, and `0` 2x liquidation-proxy events. | Useful short/weakness overlay; below standalone right-tail gate. |
| Broad metal long momentum | `pmr_metal_momentum_long_72h` has full 2x `-91.450658%` and best-90d 2x `-62.702420%`. | Blocks broad metal-long claim. |
| Metal relative spread replay | Relative metal rules do not create promotion-ready right-tail rows. | Keep as negative evidence and PMR role-split vocabulary. |
| Expanded PMR universe | PMR has `0` 1x/2x right-tail gate rows; PMR short has 5x observation rows led by XAG. | High-leverage language stays observation-only. |
| Session transfer | `pmr_regular_breakdown_short_72h` has best-90d 2x `123.235308%` but severe drawdown. | PMR regular-session short remains P1 drawdown-unresolved support. |
| Stop-risk replay | `pmr_regular_xag_only` with 4% stop has full 2x `91.979564%`, best-90d 2x `71.098173%`, and 2x drawdown `-30.494652%`. | Stop improves drawdown but loses 100%+ best-90d gate. |

## Overlay Semantics

| Overlay State | Meaning | Allowed Use | Blocked Use |
| --- | --- | --- | --- |
| `metal_dislocation_event_state` | XAG/XPT/XPD relative weakness or role-specific metal divergence. | PMR short/weakness context. | Standalone activation. |
| `broad_metal_long_negative_state` | Broad metal-long momentum remains negative. | Disable broad metal-long claims. | Short claim by itself. |
| `pmr_regular_session_breakdown_state` | Regular-session PMR breakdown has right-tail windows but drawdown remains high. | P1 support and watchlist label. | Armed observation by itself. |
| `xag_dominance_state` | PMR evidence is XAG-led rather than broad basket. | Concentration disclosure and target-specific overlay. | Broad PMR basket claim. |
| `teq_pmr_support_state` | PMR overlap can support a small TEQ sample. | Support tag only. | TEQ activation or universal filter. |
| `nlpd_pmr_disable_state` | PMR state is negative for NLPD continuation labels in overlapping 2026 evidence. | Candidate disable tag for NLPD. | Universal event-study blocker. |
| `session_mismatch_state` | Regular, off-hours, and weekend behavior differ materially. | Session policy and gap/fill blocker. | Treat all sessions as equivalent. |

## RequiredFacts

| RequiredFact | Missing Behavior | Reason |
| --- | --- | --- |
| `instrument_type` | `BLOCK_STANDALONE_CLAIM` | Separate gold tokens, precious-metal perps, and copper context. |
| `metal_role_split_state` | `BLOCK_STANDALONE_CLAIM` | Long trend, short weakness, hedge, and overlay roles must not be mixed. |
| `xag_dominance_state` | `BLOCK_BROAD_BASKET_CLAIM` | Current useful PMR evidence is XAG-led. |
| `commodity_session_gap_state` | `BLOCK_PROMOTION` | Metal perps trade through sessions that do not match underlying market structure cleanly. |
| `mark_deviation_bound_state` | `BLOCK_LEVERED_INTERPRETATION` | Mark/last divergence can downshift XAG/XPD/XPT windows. |
| `funding_rate_window` | `BLOCK_LEVERED_INTERPRETATION` | Funding can change short/long overlay economics. |
| `spread_fill_state` | `BLOCK_PROMOTION` | Metals overlays are sensitive to fill and spread. |
| `overlay_target_pairing_coverage_state` | `BLOCK_TARGET_FILTER_CLAIM` | Historical BTPC/DCB/THR pairing is absent because PMR coverage begins in 2026. |
| `target_specific_overlay_effect_state` | `BLOCK_TARGET_FILTER_CLAIM` | Overlay effects differ between TEQ and NLPD. |
| `real_margin_model_state` | `BLOCK_LEVERED_INTERPRETATION` | 3x/5x rows are research observation only. |

## Main-Control Handoff Position

`MDS-001` should not be handed to main control as a StrategyGroup yet.

If main control consumes it later, the first shape should be a non-executing
overlay vocabulary:

```json
{
  "strategy_group_id": "MDS-001",
  "status": "overlay_context_only",
  "decision": "no_candidate",
  "allowed_use": [
    "pmr_context_tag",
    "teq_support_tag",
    "nlpd_disable_tag",
    "session_mismatch_warning"
  ],
  "blocked_use": [
    "standalone_strategy_group",
    "armed_observation",
    "finalgate_input",
    "order_authority"
  ]
}
```

## Revival Condition

Advance `MDS-001` only if future evidence creates a stable standalone
activation/disable pair, improves the PMR regular-session drawdown problem, or
proves a target-specific overlay effect with enough coverage for the target
strategy family.
