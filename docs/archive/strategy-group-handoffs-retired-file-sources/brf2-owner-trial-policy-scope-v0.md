## BRF2 Owner Trial Policy Scope V0

- Status: `brf2_owner_trial_policy_scope_recorded`
- Generated: `2026-06-29T11:49:48.383084+00:00`
- Output JSON: `/Users/jiangwei/Documents/final-system-refactor-staging-20260629-lean-v2/docs/current/strategy-group-handoffs/brf2-owner-trial-policy-scope-v0.json`
- StrategyGroup: `BRF2-001`
- Trial identity: `BRF2_CONTROLLED_SHORT_TRIAL_V0`
- Policy recorded: `是`
- Owner policy scope missing: `否`

## Scope

| Field | Value |
| --- | --- |
| Capital scope | `full_available_isolated_subaccount from action_time_exchange_available_balance (USDT)` |
| Loss capable | `是` |
| Side scope | `short` |
| Symbol scope | `brf2_research_supported_symbols_only` |
| Leverage scenario | `5x_scenario_not_authority` |
| Max notional | `action_time_exchange_available_balance * leverage_scenario (controlled subaccount dynamic allocation x leverage scenario)` |
| Attempt cap | `3` |
| Loss unit | `action_time_exchange_available_balance / attempt_cap (controlled subaccount dynamic allocation / attempt cap)` |
| Daily loss cap units | `1` |
| Max consecutive losses | `2` |
| Valid until | `one_review_cycle` |

## Boundary

- This record is Owner policy only.
- It does not call FinalGate, Operation Layer, exchange write, or order placement.
- Tradeability Decision and Runtime Safety State remain required before action time.
- The 5x value is a scenario, not unconditional order authority.
