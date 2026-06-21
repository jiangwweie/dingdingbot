---
title: STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json
last_verified: 2026-06-20
---

# StrategyGroup BTPC Fact Classifier Guard Current

## Summary

- Status: `btpc_fact_classifier_guard_ready`
- StrategyGroup: `BTPC-001`
- Current decision: `revise`
- Actionable now: `false`
- Real order authority: `false`

## Source Rows

| Artifact | Status | Ready | Forbidden effects |
| --- | --- | --- | --- |
| `btpc_l2_keep_revise_fact_source_decision` | `btpc_l2_keep_revise_fact_source_decision_ready` | `True` | `none` |
| `btpc_live_derivatives_fact_source_mapping` | `btpc_live_derivatives_fact_source_mapping_ready_without_live_authority` | `True` | `none` |
| `btpc_classifier_rule_review` | `btpc_classifier_rule_review_recorded_without_live_authority` | `True` | `none` |

## Boundary

This guard preserves the BTPC revise lane. It does not promote BTPC, satisfy live RequiredFacts, call FinalGate, call Operation Layer, or authorize a real order.
