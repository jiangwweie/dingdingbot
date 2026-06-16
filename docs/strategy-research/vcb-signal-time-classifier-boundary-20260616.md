# VCB-001 Signal-Time Classifier Boundary

Status: P1_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document hardens `VCB-001` by separating signal-time breakout facts from
post-entry true/false breakout labels.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`VCB-001` should remain observe-only until a signal-time classifier can
reproduce the true-breakout edge without using post-entry labels.

The key risk is subtle: `true_breakout_followthrough` has very strong replay
returns, but it is an analysis label derived from the path after entry. It must
not become a fresh signal, candidate-preparation fact, or runtime gate.

## Evidence Boundary

| Evidence | Result | Allowed Use | Forbidden Use |
| --- | ---: | --- | --- |
| `true_breakout_followthrough` | Full 1x `908.444211%`; best-90d 2x `440.884098%`. | Offline label target for classifier design. | Entry fact, fresh signal, candidate-prepare gate. |
| `false_breakout_reversal` | Full 1x `-98.261028%`. | Disable/downshift vocabulary and false-breakout risk audit. | Short/fade signal without a separate strategy. |
| `all_breakouts` | Full 1x `-77.092301%`. | Negative evidence against broad breakout mode. | Broad breakout activation. |
| `pre_entry_volume_compression` | Best-90d 2x `119.927841%`, but full 2x `-77.779542%` after cost/M2M stress. | Observe-only narrow research lane. | Promotion or armed observation. |
| `pre_entry_breakout_quality` | Best-90d 2x `89.638724%`, full 2x `-76.726571%`. | Support/negative classifier evidence. | Right-tail promotion. |
| `pre_entry_strict_breakout_quality` | True rate `8.4337%`, full 1x `-63.201725%`. | Rejected strict variant. | Revival evidence. |

## Signal-Time Versus Post-Entry Facts

| Fact Class | Examples | Main-Control Meaning |
| --- | --- | --- |
| `signal_time_allowed` | Closed prior high, compression bandwidth, relative volume, breakout candle distance, BTC/context state known before entry. | May be used for observe-only signal evaluation. |
| `post_entry_label_only` | True follow-through, false reversal, post-entry max path, post-entry reclaim. | May be used only for research labels, audit, and future classifier training. |
| `promotion_blocker` | Cost/M2M negative sequence, spread/depth missing, mark/index missing, real margin missing. | Blocks armed observation and candidate preparation. |

## Main-Control Behavior

| State | Meaning | Required Behavior |
| --- | --- | --- |
| `vcb_observe_only_breakout_candidate` | A closed-candle compression breakout candidate exists using signal-time facts. | Emit observe-only packet; candidate prepare remains false. |
| `vcb_true_breakout_label_only` | The event later became true follow-through in offline replay. | Use only in research evaluation; never as runtime signal readiness. |
| `vcb_false_breakout_risk_unbounded` | False-breakout risk is not bounded by a prefix-safe classifier. | Block armed observation and candidate preparation. |
| `vcb_pre_entry_classifier_weak` | Current pre-entry filters do not improve full-sequence behavior. | Keep observe-only. |
| `vcb_cost_m2m_negative` | Accepted lane remains negative under cost and event-slot M2M. | Block promotion and leverage escalation. |
| `vcb_broad_breakout_blocked` | Broad breakout mode is negative. | Block broad VCB mode. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `vcb_signal_time_fact_state` | Confirms the candidate uses only pre-entry closed-candle facts. | `no_signal` |
| `vcb_post_entry_label_boundary_state` | Confirms true/false labels are analysis-only. | `block_candidate_prepare` |
| `vcb_pre_entry_classifier_quality_state` | Current classifier quality, true-rate, false-rate, full curve, and window result. | `observe_only` |
| `vcb_false_breakout_disable_state` | False-breakout risk is bounded or unbounded. | `block_armed_observation` |
| `vcb_cost_m2m_state` | Cost and event-slot equity evidence for the chosen pre-entry lane. | `block_promotion` |
| `vcb_spread_depth_state` | Live-like spread/depth availability. | `block_promotion` |
| `vcb_mark_index_state` | Futures mark/index interpretation. | `block_promotion` |
| `vcb_leverage_ruin_state` | 3x/5x risk boundary. | `block_leverage_promotion` |

## Sample Observe-Only Packet

```json
{
  "strategy_group_id": "VCB-001",
  "version": "2026-06-16-signal-boundary-r0",
  "status": "observe_only_breakout_candidate_seen",
  "symbol": "XRPUSDT",
  "direction": "long",
  "candidate_prepare_allowed_by_research": false,
  "execution_allowed_by_research": false,
  "required_facts_state": {
    "vcb_signal_time_fact_state": "present",
    "vcb_post_entry_label_boundary_state": "post_entry_labels_analysis_only",
    "vcb_pre_entry_classifier_quality_state": "weak_full_curve",
    "vcb_false_breakout_disable_state": "unbounded",
    "vcb_cost_m2m_state": "negative",
    "vcb_spread_depth_state": "missing",
    "vcb_mark_index_state": "missing"
  },
  "main_control_hint": "observe_only_no_candidate_prepare",
  "reason": "Closed-candle compression breakout candidate is visible, but true-breakout follow-through remains a post-entry label and current pre-entry classifiers are not promotion-grade."
}
```

## Research Conclusion

`VCB-001` remains useful because it identifies a real right-tail structure:
rare true expansion after compression. It is not yet a tradable StrategyGroup
candidate because the current signal-time filters do not isolate that structure
well enough.

The correct handoff posture is:

```text
observe compression breakout candidates
keep true/false labels as research targets
block broad breakout mode
block candidate prepare
block leverage escalation
continue classifier redesign
```

This keeps VCB available for strategy-pool revival while preventing a hidden
future-function mistake.
