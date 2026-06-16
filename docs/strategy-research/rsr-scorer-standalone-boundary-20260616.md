# RSR-001 Scorer Versus Standalone Boundary

Status: P1_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document hardens `RSR-001` by separating relative-strength scoring from
standalone StrategyGroup activation.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`RSR-001` should remain an observe-only TEQ support scorer until decay,
session/fill, product, mark/funding, and real margin facts improve.

The value of RSR is not "buy the top-ranked symbol." The value is a
closed-candle leadership score that can help TEQ interpretation, Strategy Picker
display, and later classifier design.

## Evidence Boundary

| Evidence | Result | Allowed Use | Forbidden Use |
| --- | ---: | --- | --- |
| `teq_rsr_72h_top4_hold72__baseline` | Full 2x `334.274599%`; best-30d 2x `892.836220%`; DD 2x `-72.703589%`; second-half 2x `-44.265320%`. | Right-tail support and ranking vocabulary. | Standalone armed observation. |
| `teq_rsr_72h_strict_top2_hold72__index_confirmed` | Full 2x `146.393744%`; best-30d 2x `330.020006%`; DD 2x `-50.994691%`; second-half 2x `-27.303456%`. | Cleaner scorer candidate for TEQ support. | Promotion while second-half decay remains unresolved. |
| `teq_rsr_120h_top4_hold120` | Full 2x `-80.027481%`; best-30d 2x `-5.895943%`. | Negative evidence against longer-lookback rotation. | Revival or broad RSR activation. |
| 5x stress rows | Proxy wipeout appears in broad and strict rows. | Leverage stress vocabulary. | Live leverage promotion. |

## Scorer Versus Standalone Split

| RSR Role | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `rsr_teq_support_scorer` | RSR ranks TEQ-like symbols and explains leadership context. | Allowed as observe-only support annotation. |
| `rsr_strategy_picker_rank_hint` | RSR can help display which TEQ symbols are leading. | Allowed for UI/scorer context, not execution authority. |
| `rsr_decay_classifier_candidate` | Strict top2 index-confirmed lane is a future classifier candidate. | Keep as P1 research; require decay and session/fill facts. |
| `rsr_standalone_activation_blocked` | RSR alone cannot prepare a candidate. | Block candidate prepare when no primary TEQ/other strategy signal exists. |
| `rsr_longer_lookback_blocked` | 120h lookback is negative evidence. | Block broad longer-lookback RSR revival. |
| `rsr_high_leverage_blocked` | 3x/5x are stress-only; 5x includes wipeout risk. | Block leverage promotion. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `rsr_role_state` | Distinguishes support scorer, picker rank hint, classifier candidate, or standalone blocked. | `observe_only` |
| `rsr_primary_strategy_binding_state` | Names the primary strategy RSR supports, usually `TEQ-001`. | `no_support_annotation` |
| `rsr_standalone_block_state` | Confirms RSR is not the primary activation source. | `block_candidate_prepare` |
| `rsr_decay_classifier_state` | Captures second-half decay and current classifier quality. | `observe_only` |
| `rsr_index_reference_state` | QQQ/SPY reference mapping and freshness. | `no_score` |
| `rsr_rank_priority_state` | Signal-time rank priority and capital-slot competition state. | `no_score` |
| `rsr_longer_lookback_negative_state` | Blocks 120h broad rotation revival. | `block_broad_rsr` |
| `rsr_high_leverage_block_state` | Blocks 3x/5x promotion. | `block_leverage_promotion` |

## Sample Scorer Packet

```json
{
  "strategy_group_id": "RSR-001",
  "version": "2026-06-16-scorer-boundary-r0",
  "status": "observe_only_relative_strength_scorer_ready",
  "symbol": "COINUSDT",
  "direction": "long",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false,
  "role": "rsr_teq_support_scorer",
  "primary_strategy_binding": "TEQ-001",
  "required_facts_state": {
    "rsr_role_state": "support_scorer",
    "rsr_primary_strategy_binding_state": "TEQ-001",
    "rsr_standalone_block_state": "present",
    "rsr_decay_classifier_state": "second_half_decay_unresolved",
    "rsr_index_reference_state": "required",
    "rsr_rank_priority_state": "present",
    "rsr_high_leverage_block_state": "5x_disabled"
  },
  "main_control_hint": "support_annotation_only_no_candidate_prepare",
  "reason": "RSR ranks TEQ-like leadership but remains blocked as standalone activation by second-half decay and missing session/fill/product/margin facts."
}
```

## Research Conclusion

`RSR-001` should stay alive because it gives the system a simple, interpretable
leadership lens for equity-like symbols. Its current handoff posture is:

```text
score TEQ-like symbols
support TEQ interpretation
help Strategy Picker ranking language
block standalone candidate prepare
block longer-lookback broad rotation
block high leverage
continue decay classifier research
```

This keeps the useful relative-strength semantics while preventing a ranking
tool from becoming an accidental execution strategy.
