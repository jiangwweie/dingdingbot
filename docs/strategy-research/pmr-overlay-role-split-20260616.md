# PMR-001 Overlay Role Split

Status: P0_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document splits `PMR-001` into explicit overlay roles so main control does
not interpret precious-metal evidence as a broad standalone trading strategy.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`PMR-001` should remain an observe-only precious-metal regime overlay until
session, fill, mark, funding, and real margin facts are stronger.

The valuable part of PMR is not "trade metals whenever they move." The valuable
part is target-specific context:

1. Disable weak continuation labels when PMR state is historically toxic.
2. Support TEQ context when PMR overlap is historically positive.
3. Preserve XAG-led regular-session short windows as a watchlist lane.
4. Keep metals dislocation and session mismatch as context facts.
5. Block standalone broad-metal promotion for now.

## Role Split

| PMR Role Branch | Runtime Meaning | Evidence Basis | Main-Control Behavior |
| --- | --- | --- | --- |
| `pmr_disable_overlay_for_nlpd` | PMR state can disable or downshift `NLPD-001` continuation research. | `NLPD-001` PMR-state paired events: `213`; PMR-state 2x result: `-99.992487%`. No-PMR allowed events: `64`; allowed 2x result: `113.983438%`. | Allow as an observe-only disable tag for NLPD research; not an independent PMR signal. |
| `pmr_teq_support_tag` | PMR state can annotate TEQ context when overlap remains positive. | TEQ PMR-support events: `15`; support 2x result: `263.186030%`. All TEQ events: `52`; all 2x result: `4274.532339%`. | Use as support tag only; do not use PMR to activate or filter TEQ without TEQ's own facts. |
| `pmr_regular_xag_short_watchlist` | XAG-led regular-session weakness can be observed as a short watchlist lane. | `pmr_regular_breakdown_short_72h`: full 2x `31.047168%`, best-90d 2x `123.235308%`, 2x drawdown about `-70.763112%`. `pmr_regular_volume_confirmed`: best-90d 2x `141.806297%`, 2x drawdown `-69.210756%`. | Observe-only watchlist. Do not prepare candidates without role, session, mark, fill, and margin facts. |
| `pmr_metal_dislocation_context` | Metals dislocation can describe relative weakness or session mismatch. | `pmr_metal_relative_breakdown_short_72h`: full 2x `61.335549%`, best-90d 2x `52.642224%`. Broad metal-long evidence is negative. | Context fact for PMR/MDS; not a standalone action. |
| `pmr_gold_token_context_only` | XAUT/PAXG-like symbols are product/context references, not return evidence. | Current PMR packet treats gold-token evidence as context-only. | Keep as context-only unless current product, liquidity, and executable-side facts improve. |
| `pmr_standalone_short_blocked` | PMR is not promoted as a standalone short StrategyGroup. | PMR has `0` 1x/2x right-tail gate rows in the broad packet and remains XAG-concentrated. | Block standalone promotion. |
| `pmr_broad_long_blocked` | Broad metal-long momentum should not be treated as a live candidate. | Broad metal long momentum full 2x result: `-91.450658%`. | Block broad long claims and use as negative evidence. |

## Main-Control Interpretation

| Condition | Allowed Interpretation | Forbidden Interpretation |
| --- | --- | --- |
| PMR overlaps NLPD and PMR state is toxic. | NLPD disable/downshift context. | PMR standalone short signal. |
| PMR overlaps TEQ and TEQ has its own fresh signal. | TEQ support annotation. | PMR activation signal for TEQ. |
| XAG-led regular-session weakness appears. | PMR observe-only watchlist. | Candidate prepare without complete session, mark, fill, and margin facts. |
| Broad metal-long branch appears. | Negative evidence / blocker. | Long-side metal momentum activation. |
| Gold-token symbol is present. | Product context. | Executable long/short evidence. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `pmr_role_branch_state` | Identifies whether the PMR observation is disable, support, short-watchlist, context-only, or blocked. | `observe_only_no_candidate` |
| `pmr_target_overlay_policy_state` | Maps PMR state to the target strategy it modifies, such as NLPD or TEQ. | `block_overlay_application` |
| `nlpd_pmr_disable_state` | NLPD-specific PMR disable/downshift condition. | `no_disable_tag` |
| `teq_pmr_support_state` | TEQ-specific PMR support annotation. | `no_support_tag` |
| `pmr_standalone_short_block_state` | Explicit block for standalone PMR short promotion. | `block_candidate_prepare` |
| `pmr_broad_long_negative_state` | Explicit block for broad metal-long promotion. | `block_long_claim` |
| `pmr_regular_xag_short_watch_state` | XAG-led regular-session short watchlist state. | `no_signal` |
| `stop_vs_right_tail_tradeoff_state` | Documents that stop-risk variants reduce drawdown but have not restored a robust 100%+ 90d right-tail lane. | `observe_only` |

## Sample Context Packet

```json
{
  "strategy_group_id": "PMR-001",
  "version": "2026-06-16-role-split-r0",
  "status": "overlay_context_only",
  "symbol": "XAGUSDT",
  "side": "short_context",
  "role_branch": "pmr_regular_xag_short_watchlist",
  "freshness_window_seconds": 1800,
  "required_facts_state": {
    "pmr_role_branch_state": "present",
    "commodity_session_gap_state": "required_before_candidate",
    "mark_deviation_bound_state": "required_before_candidate",
    "fill_gap_slippage_state": "missing",
    "real_margin_model_state": "missing"
  },
  "main_control_hint": "observe_only_no_candidate_prepare",
  "reason": "PMR short evidence has right-tail windows but unresolved drawdown, XAG concentration, fill, session, and margin facts."
}
```

## Research Conclusion

`PMR-001` is useful, but its useful shape is an overlay and branch classifier.
The correct handoff posture is:

```text
observe PMR
annotate target strategies
disable toxic overlaps
support positive overlaps
watch XAG-led short windows
block standalone broad-metal promotion
```

This keeps PMR alive in the strategy cabinet without letting a narrow
XAG-concentrated research edge become an over-broad execution candidate.
