## BRF2 Owner Trial Policy Scope V0

- Status: `brf2_owner_trial_policy_scope_recorded`
- Generated: `2026-06-29T11:30:58.789253+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json`
- StrategyGroup: `BRF2-001`
- Trial identity: `BRF2_CONTROLLED_SHORT_TRIAL_V0`
- Policy recorded: `是`
- Owner policy scope missing: `否`
- Actionable now: `否`
- Real order authority: `否`

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
- It does not set actionable_now or real_order_authority.
- FinalGate and Operation Layer remain required at action time.
- The 5x value is a scenario, not unconditional order authority.
