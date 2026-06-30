## Runtime Replay Lab

- 当前阶段: signal_observation_replay_ready
- 当前检查点: Use replay/synthetic rehearsal while P0 waits for a real fresh signal.
- Owner 介入: 否
- 服务器修改: 否
- 接近真实订单: 否
- Exchange write: 否

## Coverage

- StrategyGroup: MPG-001
- Replay samples: 8
- L2 shadow replay samples: 5
- L1 observe replay samples: 15
- Post-submit simulator cases: 7
- Cost review skeleton: present
- Synthetic fixtures: active_position_conflict, allocated_profile_boundary_mismatch, fresh_signal_pass, missing_required_facts, no_signal, open_order_conflict, protection_missing, stale_signal
- Freqtrade: future sidecar research adapter only

## StrategyGroup Replay Review

| StrategyGroup | Layer | Samples | Review signals | Quiet / no-action | Revise | Boundary |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| MPG-001 | L4 replay baseline | 8 | 6 | 1 | 6 | dry-run only; live order still requires real fresh signal and official chain |
| BTPC-001 | L2 shadow | 5 | 2 | 1 | 3 | shadow evidence only; no Operation Layer |
| BRF-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |
| VCB-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |
| LSR-001 | L1 observe | 5 | 2 | 1 | 3 | observe-only; no prepare chain |

## Checks

- blocked_fixtures_do_not_reach_operation_layer: 是
- brf001_l1_cases_do_not_reach_prepare_or_operation_layer: 是
- brf001_l1_observe_replay_cases_present: 是
- brf001_l1_would_enter_review_shape_present: 是
- btpc001_l2_blocked_cases_do_not_reach_operation_layer: 是
- btpc001_l2_shadow_replay_cases_present: 是
- btpc001_l2_would_enter_review_shape_present: 是
- cost_review_skeleton_present: 是
- external_framework_sidecar_only: 是
- fresh_pass_reaches_prepare_chain: 是
- lsr001_l1_cases_do_not_reach_prepare_or_operation_layer: 是
- lsr001_l1_observe_replay_cases_present: 是
- lsr001_l1_would_enter_review_shape_present: 是
- mpg001_replay_corpus_cases_present: 是
- mpg001_replay_sample_present: 是
- no_replay_or_synthetic_signal_has_live_authority: 是
- post_submit_simulator_cases_present: 是
- post_submit_simulator_non_executing: 是
- replay_report_owner_readable: 是
- synthetic_fixture_cases_present: 是
- vcb001_l1_cases_do_not_reach_prepare_or_operation_layer: 是
- vcb001_l1_observe_replay_cases_present: 是
- vcb001_l1_would_enter_review_shape_present: 是

## Safety

- Replay / synthetic signals are not live market signals.
- This report does not authorize FinalGate, Operation Layer, exchange write, or real orders.
