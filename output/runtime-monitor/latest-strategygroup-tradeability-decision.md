## StrategyGroup Tradeability Decision

- Status: `tradeability_decision_ready`
- Generated: `2026-06-30T02:35:56.730727+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-tradeability-decision.json`
- Decision rows: `13`
- Tradable now: `0`
- Top blocker: `BRF2-001` / `not_tradable_market_wait` / `fresh_brf2_short_signal_absent`
- Next action: `continue_brf2_armed_observation_until_fresh_signal`

## Decision Rows

| StrategyGroup | Stage | Decision | First Blocker | Owner | Next Action | After |
| --- | --- | --- | --- | --- | --- | --- |
| `MPG-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_executable_signal_absent` | `market` | `continue_armed_observation_until_fresh_signal` | `live_submit_ready` |
| `BRF2-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_brf2_short_signal_absent` | `market` | `continue_brf2_armed_observation_until_fresh_signal` | `live_submit_ready` |
| `RBR-001` | `observe_only_would_enter` | `not_tradable_strategy_quality` | `rbr_loss_boundary_not_expressible_for_mainline` | `strategy_review` | `park_rbr_until_material_new_edge_or_loss_boundary_evidence` | `parked_not_mainline_blocker` |
| `RBR2-001` | `role_only_intake_candidate` | `not_tradable_strategy_quality` | `role_only_or_classifier_asset_not_trial_candidate` | `strategy_review` | `complete_role_merge_or_classifier_review` | `classifier_or_role_support_asset` |
| `BTPC-001` | `trial_asset_admission_candidate` | `not_tradable_facts` | `required_facts_or_classifier_mapping_unclosed` | `engineering` | `close_requiredfacts_classifier_and_replay_mapping` | `armed_observation` |
| `LSR-001` | `trial_asset_admission_candidate` | `not_tradable_facts` | `required_facts_or_classifier_mapping_unclosed` | `engineering` | `close_requiredfacts_classifier_and_replay_mapping` | `armed_observation` |
| `BRF-001` | `trial_asset_admission_candidate` | `not_tradable_facts` | `required_facts_or_classifier_mapping_unclosed` | `engineering` | `close_requiredfacts_classifier_and_replay_mapping` | `armed_observation` |
| `MI-001` | `trial_asset_admission_candidate` | `not_tradable_asset_admission` | `strategy_group_not_admitted_as_final_trial_asset` | `engineering` | `build_trial_asset_admission_proposal` | `trial_asset_admission_candidate` |
| `CPM-RO-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_cpm_long_signal_absent` | `market` | `continue_cpm_long_armed_observation_until_reclaim_signal` | `live_submit_ready` |
| `FBS-001` | `admitted_trial_asset` | `not_tradable_strategy_quality` | `experiment_worthiness_or_loss_envelope_unclosed` | `strategy_review` | `complete_experiment_worthiness_and_loss_envelope_review` | `trial_asset_admission_candidate` |
| `PMR-001` | `admitted_trial_asset` | `not_tradable_strategy_quality` | `experiment_worthiness_or_loss_envelope_unclosed` | `strategy_review` | `complete_experiment_worthiness_and_loss_envelope_review` | `trial_asset_admission_candidate` |
| `SOR-001` | `armed_observation` | `not_tradable_market_wait` | `fresh_session_range_signal_absent` | `market` | `continue_armed_observation` | `live_submit_ready` |
| `TEQ-001` | `admitted_trial_asset` | `not_tradable_strategy_quality` | `experiment_worthiness_or_loss_envelope_unclosed` | `strategy_review` | `complete_experiment_worthiness_and_loss_envelope_review` | `trial_asset_admission_candidate` |

## Boundary

- Tradeability Decision is a read model only.
- It does not call FinalGate, Operation Layer, or exchange write.
- Runtime Safety State remains the live-submit safety source; Execution Attempt remains the lifecycle entry object.
