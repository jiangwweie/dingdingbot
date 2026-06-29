## StrategyGroup Portfolio Board v0

- Status: `portfolio_board_ready`
- Portfolio rows: `10`
- P0 state: `waiting_for_market`
- Signal Observation state: `review_needed`
- Runtime Owner intervention required: 否
- Live permission change: 否
- Output: `/Users/jiangwei/Documents/final-system-refactor-20260623/output/runtime-monitor/latest-strategygroup-portfolio-board.json`

## Portfolio Rows

| StrategyGroup | Tier | Evidence stage | Opportunities | Cost-after result | Strategy review checkpoint |
| --- | --- | --- | ---: | --- | --- |
| `MPG-001` | `L4` | `trial_waiting` | 0 | none | `build_mpg_member_role_controls_v2_without_live_scope_expansion` |
| `BRF-001` | `L1` | `promote_review` | 7 | 4h:3/6+1p, 12h:3/5+2p, 24h:3/4+3p | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `BTPC-001` | `L2` | `revise` | 0 | none | `BTPC-001_classifier_fact_source_revision_review` |
| `LSR-001` | `L1` | `revise` | 2 | 4h:2/2+0p, 12h:2/2+0p, 24h:2/2+0p | `LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | `unknown` | `revise` | 17 | 4h:10/15+2p, 12h:9/13+4p, 24h:10/12+5p | `open_mi_identity_overlap_symbol_concentration_review` |
| `CPM-RO-001` | `unknown` | `revise` | 18 | 4h:9/18+0p, 12h:11/18+0p, 24h:13/17+1p | `open_cpm_ro_semantic_source_merge_quality_review` |
| `FBS-001` | `L3` | `coverage_visibility_review` | 0 | none | `run_fbs_derivatives_fact_coverage_visibility_review` |
| `SOR-001` | `L3` | `coverage_visibility_review` | 0 | none | `run_sor_session_no_action_visibility_review` |
| `VCB-001` | `L1` | `observe` | 2 | 4h:2/2+0p, 12h:1/1+1p, 24h:1/1+1p | `run_vcb_false_breakout_classifier_review` |
| `RBR-001` | `L1` | `park` | 9 | 4h:5/8+1p, 12h:5/8+1p, 24h:5/7+2p | `keep_parked_until_material_new_edge_evidence` |

## Engineering Continuation Queue

| StrategyGroup | Stage | Review checkpoint | Evidence gaps |
| --- | --- | --- | --- |
| `MPG-001` | `trial_waiting` | `build_mpg_member_role_controls_v2_without_live_scope_expansion` | no_recent_forward_outcome_events_in_capture_audit, real_fresh_signal_absent_for_p0_live_lane |
| `BRF-001` | `promote_review` | `BRF-001_forward_outcome_and_requiredfacts_review` | would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, would_enter_forward_outcome_pending:4h |
| `BTPC-001` | `revise` | `BTPC-001_classifier_fact_source_revision_review` | no_action_or_classifier_attribution_needs_closure |
| `LSR-001` | `revise` | `LSR-001_classifier_fact_source_revision_review` | no_action_or_classifier_attribution_needs_closure |
| `MI-001` | `revise` | `open_mi_identity_overlap_symbol_concentration_review` | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, would_enter_forward_outcome_pending:4h |
| `CPM-RO-001` | `revise` | `open_cpm_ro_semantic_source_merge_quality_review` | registry_identity_or_registry_row_missing, execution_tier_not_in_policy_or_registry, would_enter_forward_outcome_pending:24h |
| `FBS-001` | `coverage_visibility_review` | `run_fbs_derivatives_fact_coverage_visibility_review` | no_recent_forward_outcome_events_in_capture_audit, coverage_visibility_or_routing_needs_closure |
| `SOR-001` | `coverage_visibility_review` | `run_sor_session_no_action_visibility_review` | no_recent_forward_outcome_events_in_capture_audit, coverage_visibility_or_routing_needs_closure |
| `VCB-001` | `observe` | `run_vcb_false_breakout_classifier_review` | would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h |
| `RBR-001` | `park` | `keep_parked_until_material_new_edge_evidence` | would_enter_forward_outcome_pending:12h, would_enter_forward_outcome_pending:24h, would_enter_forward_outcome_pending:4h |

## Boundary

- 该看板只做本地 review-only 策略组合治理。
- 不授权真实下单、registry admission、tier policy、live profile、order sizing、FinalGate 或 Operation Layer。
