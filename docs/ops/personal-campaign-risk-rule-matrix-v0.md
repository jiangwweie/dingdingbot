> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Personal Campaign Risk Rule Matrix v0

Last updated: 2026-05-25

Status: Design matrix / local sandbox only

Runtime effect: none

Trading permission effect: none

Default state: disabled by default

## Purpose

This matrix defines the minimum risk rules for the Personal Leveraged Campaign
local sandbox. It exists to prevent risk from becoming a one-time pre-filter.

Risk must be enforced at three boundaries:

1. order plan generation;
2. position lifecycle;
3. campaign lifecycle and profit protection control.

This matrix does not authorize runtime, paper, testnet, tiny-live, live,
exchange API access, real account access, real orders, transfers, withdrawals,
leverage advice, or sizing advice.

## Order-Plan Rules

| Rule ID | Boundary | Input | Allow Condition | Reject Reason | Required Output |
|---|---|---|---|---|---|
| `FEATURE-001` | Feature snapshot | `FeatureSnapshot` | `input_scope=closed_or_prior_inputs_only` and no LLM/account/exchange state | model validation error | Reject before contract evaluation. |
| `FEATURE-002` | Feature/contract binding | `FeatureSnapshot.strategy_contract_id` | Matches `StrategyContract.strategy_contract_id` | `feature_snapshot_strategy_mismatch` | Reject `TradeIntent`. |
| `ORDER-001` | Intent gate | `TradeIntent` | `decision=allow` and `action=enter` | `intent_rejected:*`, `unsupported_intent_action:*` | Reject before any simulated receipt. |
| `ORDER-002` | Campaign status | `CampaignState` | Campaign is `armed` and not `paused` or `hard_locked` | `campaign_paused`, `campaign_hard_locked` | Reject plan. |
| `ORDER-003` | Loss lock | `CampaignState` | `loss_lock=false` | `campaign_loss_lock` | Reject plan. |
| `ORDER-004` | Per-order loss cap | `SandboxOrderRequest.max_loss`, `CampaignRiskCaps.max_order_loss` | Requested max loss is less than or equal to owner cap | `order_loss_cap_exceeded` | Reject plan. |
| `ORDER-005` | Notional cap | `SandboxOrderRequest.notional`, `CampaignRiskCaps.max_notional` | Requested notional is less than or equal to owner cap | `order_notional_cap_exceeded` | Reject plan. |
| `ORDER-006` | Leverage cap | `SandboxOrderRequest.leverage`, `CampaignRiskCaps.max_leverage` | Requested leverage is less than or equal to owner cap | `order_leverage_cap_exceeded` | Reject plan. |
| `ORDER-007` | Campaign loss cap | `CampaignState.total_pnl`, `CampaignRiskCaps.max_campaign_loss` | Campaign loss has not reached owner cap | `campaign_loss_cap_reached` | Reject plan. |
| `ORDER-008` | Protection requirements | Allowed `RiskOrderPlan` | Protective stop, position lifecycle monitor, and campaign loss lock are listed | `allowed_plan_missing_required_protections` | Invariant fail if missing. |

## Position-Lifecycle Rules

| Rule ID | Boundary | Input | Allow / Action Condition | Violation / Action | Required Output |
|---|---|---|---|---|---|
| `POSITION-001` | Blocked receipt | `ExecutionReceipt.status=blocked` | No position exists | `receipt_blocked_no_position` | `PositionLifecycleState=no_position`. |
| `POSITION-002` | Protection presence | Simulated accepted receipt | Protection is present | `position_protection_missing` | Require close and campaign hard-lock. |
| `POSITION-003` | Campaign loss cap | Updated PnL | Total PnL greater than negative campaign loss cap | `campaign_loss_cap_reached` | Require reduce/close, set loss lock, hard-lock campaign. |
| `POSITION-004` | Profit protection | Updated PnL | Total PnL below profit-protect threshold | `profit_protect_threshold_reached` | Require reduce, set `profit_protect_active=true`. |
| `POSITION-005` | Normal protected open | Accepted receipt with protection and no threshold breach | Position remains protected | `allow:position_open_protected` | `PositionLifecycleState=open_protected`. |

## Campaign And Profit-Protection Rules

| Rule ID | Boundary | Input | Allow / Action Condition | Blocked State | Required Output |
|---|---|---|---|---|---|
| `CAMPAIGN-001` | Human arm gate | `HumanArmDecision=arm` | Strategy id matches surfaced `ModeAdvice` | `reject:strategy_contract_mismatch` | Campaign becomes `armed` only on matching arm. |
| `CAMPAIGN-002` | Human pause/reject | `HumanArmDecision=pause/reject` | Owner does not arm session | `pause:human_*` | Campaign becomes `paused`. |
| `CAMPAIGN-003` | Hard lock consistency | `PositionLifecycleState.hard_lock_required=true` | Campaign status must be `hard_locked` | `hard_lock_requirement_without_campaign_lock` | Invariant fail if inconsistent. |
| `PROFIT-001` | Profit protection | Updated PnL | Profit-protect threshold reached | `profit_protect_threshold_reached` | Set `profit_protect_active=true`. |
| `PROFIT-002` | Reduce/close requirement | `CampaignState.profit_protect_active=true` | Position lifecycle requires reduce or close | `profit_protect_without_reduce_or_close_requirement` | Invariant fail if missing. |
| `PROFIT-003` | Withdrawal exclusion | Any campaign state | System does not create withdrawal object, amount, schedule, or automation | `withdrawal_path_introduced` | Out of scope; Owner handles withdrawal outside system. |

## Current Sandbox Coverage

| Scenario | Covered Rules |
|---|---|
| `allow_open_protected` | `FEATURE-001`, `FEATURE-002`, `ORDER-001` through `ORDER-008`, `POSITION-005`, `CAMPAIGN-001`. |
| `reject_contract_invalidated` | `FEATURE-001`, strategy invalidation before order planning, `ORDER-001`. |
| `reject_order_caps` | `FEATURE-001`, `FEATURE-002`, `ORDER-004`, `ORDER-005`, `ORDER-006`. |
| `pause_blocks_session` | `FEATURE-001`, `CAMPAIGN-002`, `ORDER-001`, `ORDER-002`. |
| `hard_lock_missing_protection` | `FEATURE-001`, `FEATURE-002`, `POSITION-002`, `CAMPAIGN-003`. |
| `profit_protect_reduce` | `FEATURE-001`, `FEATURE-002`, `POSITION-004`, `PROFIT-001`, `PROFIT-002`, `PROFIT-003`. |

## Open Gaps

These are intentionally not implemented in the local sandbox yet:

- real order lifecycle state machine;
- demo portfolio persistence;
- read-only exchange sync;
- paper/testnet/live/tiny-live permission states;
- withdrawal instruction / confirmation flow, because withdrawal is
  Owner-external and out of scope;
- multi-strategy or multi-asset campaign routing.

Any of these requires a separate promotion review before implementation.
