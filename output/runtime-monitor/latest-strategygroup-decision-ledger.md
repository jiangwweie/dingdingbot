# StrategyGroup Decision Ledger

## Summary

- Status: `decision_ledger_ready`
- Current rows: `12`
- High-priority no-action groups: `4`
- No-action attribution rows: `4`
- Role review rows: `1`
- Research intake groups: `2`
- Single main product: `true`
- Real order authority: `false`
- L4 scope change: `false`

## Current Decisions

| StrategyGroup | Tier | Type | Decision | Scope | Next |
| --- | --- | --- | --- | --- | --- |
| `BRF-001` | `L1` | `would_enter` | `promote` | `trial_admission` | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `BRF2-001` | `unknown` | `research_intake` | `promote` | `intake_only` | `BRF2-001_paper_observation_admission_packet` |
| `BTPC-001` | `L2` | `no_action` | `revise` | `not_applicable` | `BTPC-001_classifier_fact_source_revision_review` |
| `CPM-RO-001` | `unknown` | `would_enter` | `revise` | `not_applicable` | `CPM-RO-001_registry_identity_review` |
| `FBS-001` | `L3` | `no_action` | `keep_observing` | `not_applicable` | `FBS-001_no_action_visibility_and_routing_audit` |
| `LSR-001` | `L1` | `would_enter` | `revise` | `not_applicable` | `LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | `unknown` | `would_enter` | `revise` | `not_applicable` | `MI-001_registry_identity_review` |
| `MPG-001` | `L4` | `no_action` | `keep_observing` | `not_applicable` | `MPG-001_no_action_visibility_and_routing_audit` |
| `RBR-001` | `L1` | `no_action` | `park` | `not_applicable` | `park_until_material_new_edge_evidence` |
| `RBR2-001` | `unknown` | `research_intake` | `keep_observing` | `not_applicable` | `RBR2-001_role_only_range_detector_classifier_merge_note` |
| `SOR-001` | `L3` | `no_action` | `keep_observing` | `not_applicable` | `SOR-001_no_action_visibility_and_routing_audit` |
| `VCB-001` | `L1` | `no_action` | `keep_observing` | `not_applicable` | `VCB-001_continue_observe_only` |

## Observation Layer

| Layer | Value |
| --- | --- |
| P0 | `waiting_for_executable_fresh_signal` |
| P0.5 | `observation_active` |
| Broader would-enter | `1` |
| High-priority no-action | `4` |
| Latest observe-only would-enter | `RBR-001` / `ADA/USDT:USDT` / `short` |

## Role Review

| Source | Linked Intake | Decision | Next |
| --- | --- | --- | --- |
| `RBR-001` | `RBR2-001` | `review_range_detector_role_not_live_candidate` | `RBR_RBR2_role_review_range_detector_classifier_merge_note` |

## No-Action Attribution

| StrategyGroup | Symbol | Class | Next |
| --- | --- | --- | --- |
| `BRF-001` | `BTC/USDT:USDT` | `market_structure_or_path_risk` | `BRF-001_market_structure_and_path_risk_review` |
| `BTPC-001` | `AVAX/USDT:USDT` | `fact_source_or_freshness` | `BTPC-001_freshness_and_fact_source_mapping` |
| `LSR-001` | `XRP/USDT:USDT` | `side_specific_rewrite` | `LSR-001_side_specific_rewrite_review` |
| `VCB-001` | `LINK/USDT:USDT` | `classifier_or_threshold` | `VCB-001_classifier_threshold_review` |

## Tier Review

| StrategyGroup | Tier | Tier Review | Basis |
| --- | --- | --- | --- |
| `BRF-001` | `L1` | `promote_candidate_for_review` | `promote` |
| `BRF2-001` | `unknown` | `promote_candidate_for_review` | `promote` |
| `BTPC-001` | `L2` | `revise_before_tier_change` | `revise` |
| `CPM-RO-001` | `unknown` | `revise_before_tier_change` | `revise` |
| `FBS-001` | `L3` | `keep_current_tier` | `keep_observing` |
| `LSR-001` | `L1` | `revise_before_tier_change` | `revise` |
| `MI-001` | `unknown` | `revise_before_tier_change` | `revise` |
| `MPG-001` | `L4` | `keep_current_tier` | `keep_observing` |
| `RBR-001` | `L1` | `park` | `park` |
| `RBR2-001` | `unknown` | `keep_current_tier` | `keep_observing` |
| `SOR-001` | `L3` | `keep_current_tier` | `keep_observing` |
| `VCB-001` | `L1` | `keep_current_tier` | `keep_observing` |

## Next

- `execute_or_verify_top_revision_checkpoints_without_live_authority_expansion`
