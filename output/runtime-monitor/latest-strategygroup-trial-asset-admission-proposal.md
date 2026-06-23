## StrategyGroup Trial Asset Admission Proposal

- Status: `trial_asset_admission_proposal_ready`
- Generated: `2026-06-23T02:06:27.544764+00:00`
- Output JSON: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json`
- StrategyGroup: `BRF2-001`
- Current stage: `tiny_live_intake_candidate`
- Proposed stage: `trial_asset_admission_candidate`
- Owner policy required: `是`
- Next action: `record_owner_trial_scope_policy`
- Real order authority: `否`

## Owner Policy Fields

| Field | Value |
| --- | --- |
| `capital_scope` | `owner_policy_required` |
| `max_notional` | `owner_policy_required` |
| `valid_until` | `owner_policy_required` |
| `slippage_limit` | `owner_policy_required` |
| `trial_identity` | `owner_policy_required` |
| `symbol_scope` | `['owner_policy_required']` |
| `side_scope` | `['short']` |
| `leverage_scenario` | `owner_policy_required` |
| `attempt_cap` | `3` |
| `loss_unit` | `1` |

## Boundary

- This proposal is not applied to registry or tier policy.
- It does not mutate live profile or order sizing.
- It does not call FinalGate, Operation Layer, or exchange write.
