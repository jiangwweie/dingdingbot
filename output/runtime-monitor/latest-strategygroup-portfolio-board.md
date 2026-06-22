## StrategyGroup Portfolio Board v0

- Status: `portfolio_board_ready`
- Portfolio rows: `10`
- P0 state: `waiting_for_market`
- P0.5 state: `review_needed`
- Runtime Owner intervention required: 否
- Live permission change: 否
- Output: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-portfolio-board.json`

## Portfolio Rows

| StrategyGroup | Tier | Evidence stage | Opportunities | Cost-after result | Next system action |
| --- | --- | --- | ---: | --- | --- |
| `MPG-001` | `L4` | `trial_waiting` | 0 | none | `MPG-001_no_action_visibility_and_routing_audit` |
| `BRF-001` | `L1` | `promote_review` | 1 | 4h:0/0+1p, 12h:0/0+1p, 24h:0/0+1p | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `BTPC-001` | `L2` | `revise` | 0 | none | `BTPC-001_classifier_fact_source_revision_review` |
| `LSR-001` | `L1` | `revise` | 2 | 4h:2/2+0p, 12h:2/2+0p, 24h:1/1+1p | `LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | `unknown` | `identity_review` | 23 | 4h:17/23+0p, 12h:21/23+0p, 24h:22/23+0p | `MI-001_registry_identity_review` |
| `CPM-RO-001` | `unknown` | `identity_review` | 18 | 4h:13/18+0p, 12h:13/16+2p, 24h:13/16+2p | `CPM-RO-001_registry_identity_review` |
| `FBS-001` | `L3` | `coverage_visibility_review` | 0 | none | `FBS-001_no_action_visibility_and_routing_audit` |
| `SOR-001` | `L3` | `coverage_visibility_review` | 0 | none | `SOR-001_no_action_visibility_and_routing_audit` |
| `VCB-001` | `L1` | `observe` | 2 | 4h:2/2+0p, 12h:2/2+0p, 24h:2/2+0p | `VCB-001_continue_observe_only` |
| `RBR-001` | `L1` | `park` | 6 | 4h:5/6+0p, 12h:6/6+0p, 24h:6/6+0p | `park_until_material_new_edge_evidence` |

## Engineering Continuation Queue

| StrategyGroup | Stage | Next action | Evidence gaps |
| --- | --- | --- | --- |
| `MPG-001` | `trial_waiting` | `MPG-001_no_action_visibility_and_routing_audit` | no_recent_forward_outcome_events_in_capture_audit, real_fresh_signal_absent_for_p0_live_lane |
| `BRF-001` | `promote_review` | `BRF-001_forward_outcome_and_requiredfacts_review` | would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, would_enter_forward_outcome_pending:4h, promote_review_forward_positive_not_completed |
| `BTPC-001` | `revise` | `BTPC-001_classifier_fact_source_revision_review` | no_action_or_classifier_attribution_needs_closure |
| `LSR-001` | `revise` | `LSR-001_classifier_fact_source_revision_review` | would_enter_forward_outcome_pending:24h, no_action_or_classifier_attribution_needs_closure |
| `MI-001` | `identity_review` | `MI-001_registry_identity_review` | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, formal_candidate_vs_sub_capability_vs_observe_asset_unresolved |
| `CPM-RO-001` | `identity_review` | `CPM-RO-001_registry_identity_review` | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, formal_candidate_vs_sub_capability_vs_observe_asset_unresolved |
| `FBS-001` | `coverage_visibility_review` | `FBS-001_no_action_visibility_and_routing_audit` | no_recent_forward_outcome_events_in_capture_audit, coverage_visibility_or_routing_needs_closure |
| `SOR-001` | `coverage_visibility_review` | `SOR-001_no_action_visibility_and_routing_audit` | no_recent_forward_outcome_events_in_capture_audit, coverage_visibility_or_routing_needs_closure |
| `VCB-001` | `observe` | `VCB-001_continue_observe_only` | none |

## Boundary

- 该看板只做本地 review-only 策略组合治理。
- 不授权真实下单、registry admission、tier policy、live profile、order sizing、FinalGate 或 Operation Layer。
