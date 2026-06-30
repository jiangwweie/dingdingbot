## StrategyGroup Trial Asset Admission Proposal

- Status: `trial_asset_admission_proposal_ready`
- Generated: `2026-06-30T01:54:23.961603+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json`
- StrategyGroup: `BRF2-001`
- Current stage: `tiny_live_intake_candidate`
- Proposed stage: `admitted_trial_asset`
- Owner policy required: `否`
- Owner policy recorded: `是`
- Next checkpoint: `close_brf2_required_facts_mapping_for_armed_observation`

## Owner Policy Fields

| Field | Value |
| --- | --- |
| `capital_scope` | `{'allocation_mode': 'full_available_isolated_subaccount', 'amount_source': 'action_time_exchange_available_balance', 'currency': 'USDT', 'loss_capable': True, 'type': 'isolated_subaccount_full_allocation'}` |
| `max_notional` | `{'balance_source': 'action_time_exchange_available_balance', 'basis': 'controlled subaccount dynamic allocation x leverage scenario', 'calculation': 'action_time_exchange_available_balance * leverage_scenario', 'currency': 'USDT', 'final_authority': 'runtime_profile_and_action_time_exchange_facts'}` |
| `valid_until` | `one_review_cycle` |
| `slippage_limit` | `action_time_runtime_fact_required` |
| `trial_identity` | `BRF2_CONTROLLED_SHORT_TRIAL_V0` |
| `symbol_scope` | `brf2_research_supported_symbols_only` |
| `side_scope` | `['short']` |
| `leverage_scenario` | `5x_scenario_not_authority` |
| `attempt_cap` | `3` |
| `loss_unit` | `{'balance_source': 'action_time_exchange_available_balance', 'basis': 'controlled subaccount dynamic allocation / attempt cap', 'calculation': 'action_time_exchange_available_balance / attempt_cap', 'currency': 'USDT'}` |

## Boundary

- This proposal is not applied to registry or tier policy.
- It does not mutate live profile or order sizing.
- It does not call FinalGate, Operation Layer, or exchange write.
