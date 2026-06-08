# MR/ETH Review Ledger and Budgeted Autonomy v0 Design - 2026-06-08

## Scope

This note covers the post-action review ledger foundation for the current
Owner-bounded MR/ETH live action and the design-only Budgeted Autonomy v0
contract. It does not authorize a new strategy action, enable auto-execution,
change Tokyo deployment, restart services, or broaden symbol/side/leverage
scope.

## Current MR/ETH State

Read-only Tokyo evidence collected after the bounded live action showed:

- Authorization: `auth-64bf02c9d63b407ab03f0d79e273755f`.
- Carrier: `MR-001-live-readonly-v0`.
- Scope: `ETH/USDT:USDT`, long, `0.014`, max notional `25`, leverage `1`.
- Exchange position: `0.014` ETH long, entry `1682.57`.
- Exchange TP: reduce-only sell limit `0.014` at `1699.39`, open.
- Exchange SL: reduce-only stop-market sell `0.014` at `1665.74`, open.
- PG evidence: one position, two open protection orders, one completed
  execution intent, one execution result.
- BNB/SOL/BTC: no exchange positions, no regular/stop open orders, no PG
  positions/orders/intents.

The position is protected-open, not closed. No cleanup action is warranted while
the position is still open and both protection orders are present.

## Review Ledger v0

The ledger is embedded in existing read models and execution result summaries.
It is a review surface, not an execution surface.

Fields:

- `ledger_version`
- `authorization_id`
- `carrier_id`
- `symbol`
- `side`
- `lifecycle_status`
- `entry`
- `exit`
- `realized_pnl`
- `unrealized_pnl`
- `costs.fees`
- `costs.funding`
- `costs.slippage`
- `costs.total_cost`
- `holding_time`
- `tp_sl_result`
- `strategy_outcome`
- `review_decision`
- `warnings`
- `hard_blockers`

Cost and PnL policy:

- Realized PnL is unavailable until a close/exit fill is recorded.
- Unrealized PnL requires exchange mark/position evidence and is unavailable in
  default read-only PG-only execution-state views.
- Fees, funding, and slippage may be `not_available`.
- Missing fees, funding, or slippage are warnings, not hard blockers.
- Review decisions are constrained to `promote`, `revise`, or `park`; they do
  not change runtime state by themselves.

## Budgeted Autonomy v0

Budgeted Autonomy v0 is design-only. It is a future authorization layer above
BudgetEnvelope and below FinalGate. It must never be treated as direct trade
permission.

Required authorization fields:

- `budget_authorization_id`
- `owner_id`
- `allowed_carriers`
- `allowed_symbols`
- `allowed_sides`
- `per_action_max_notional`
- `daily_loss_cap`
- `max_active_positions`
- `max_attempts`
- `max_leverage`
- `valid_from_ms`
- `valid_until_ms`
- `review_requirement`
- `protection_mode`
- `pause_state`
- `revoke_state`
- `stop_conditions`
- `audit_refs`

Stop conditions:

- daily loss cap reached;
- max active positions reached;
- max attempts reached;
- any position lacks TP/SL;
- stale account facts;
- stale market rules;
- FinalGate blocker;
- GKS active without exact scoped clearance;
- startup guard not armed or not scoped;
- exchange credential preflight failure;
- reconciliation drift;
- Owner pause or revoke;
- review overdue after a prior action;
- cost ledger missing beyond an Owner-approved tolerance window.

Hard non-enablement constraints:

- `auto_execution_enabled=false`.
- `live_ready=false`.
- `order_permission_granted=false`.
- `execution_permission_granted=false`.
- no new broad action API;
- no runtime start;
- no budgetless execution;
- no symbol/side/leverage expansion outside explicit Owner scope;
- FinalGate remains authoritative and can veto every action.

## Candidate Flow

1. BudgetEnvelope recommends notional and risk bounds.
2. Owner creates a Budgeted Autonomy authorization with exact carrier, symbol,
   side, notional, leverage, protection, review, and stop limits.
3. System validates account facts, market rules, active positions, attempts,
   loss cap, review state, and protection state.
4. For each candidate action, system recomputes quantity from notional and
   market rules.
5. FinalGate runs for the exact candidate action.
6. If and only if all gates pass in a future separately authorized sprint, a
   bounded action may use the official execution service.

## Safety Proof

- This design does not alter Tokyo.
- This design does not create authorization, execution intent, order, runtime
  start, or exchange write action.
- Ledger fields are read-model/review evidence only.
- Budgeted Autonomy v0 is a contract proposal only; implementation must remain
  disabled until a separate Owner-approved live-safety task enables a traceable
  official path.
