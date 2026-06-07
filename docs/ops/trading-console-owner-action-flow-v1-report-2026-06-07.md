# Trading Console Owner Action Flow v1 Report - 2026-06-07

## Verdict

PASS_WITH_CONSTRAINT.

Trading Console Action Entry was advanced into a read-only Owner Action Flow
surface. The flow now carries Owner market input, candidate selection, risk
disclosure, authorization draft readiness, final-gate readiness, disabled action
state, and post-action evidence summary in one Owner-facing read model.

No live action was started. No authorization, execution intent, order, review,
audit event, runtime start, or PG mutation is created by this work.

## Scope Delivered

- Added `GET /api/trading-console/owner-action-flow` as a GET-only superset of
  `action-entry-readiness`.
- Added `data.owner_action_flow` with structured steps:
  `market_input`, `candidate_selection`, `risk_disclosure`,
  `authorization_draft`, `final_gate`, `action_state`, and
  `post_action_evidence`.
- Updated the Trading Console `/action-entry` page to consume
  `owner-action-flow` and render the action-flow steps in the current Console
  card/badge style.
- Updated candidate selection to use backend `required_owner_scope` from
  action-entry payload contracts instead of hard-coded Trend-only scope.
- Advanced Mean Reversion from static proposal to a complete non-action proposal
  template:
  - carrier: `MR-001-live-readonly-v0`
  - symbol: `ETH/USDT:USDT`
  - side: `long`
  - quantity: `0.01`
  - max notional: `20`
  - leverage: `1`
  - max attempts: `1`
  - protection mode: `single_tp_plus_sl`
  - review requirement: `post_action_review_required`

## Candidate State

| Family | Carrier | State | Action registry | Frontend action |
| --- | --- | --- | --- | --- |
| Trend | `TF-001-live-readonly-v0` | `valid_blocked_final_gate` | supported | disabled |
| Mean Reversion | `MR-001-live-readonly-v0` | `proposal_non_action` | unsupported | disabled |
| Volatility Expansion | `VB-001-live-readonly-v0` | `proposal_non_action` | unsupported | disabled |

Mean Reversion is intentionally still not actionable. Its complete scope is a
proposal contract for Owner review and later bridge work, not execution
permission.

## Safety Proof

- Trading Console API additions are GET-only.
- `include_exchange=false` remains the default for these read models.
- No Trading Console POST/action route was added.
- No live execute/order/cancel/flatten/retry path was added.
- No auto-execution or runtime-control enablement was added.
- All Action Entry / Owner Action Flow action flags remain false unless a future
  backend official path returns explicit actionable state.
- Mean Reversion and Volatility Expansion remain unsupported by the current
  action registry.

## Blocker Records

No active blocker remains for Owner Action Flow v1 authenticated browser smoke.
Owner opened an authenticated Operator browser session and the deployed
`/action-entry` page was verified in Chrome:

- login indicator: `登录：jiangwei`
- `Owner Action Flow` visible
- read-only/live-readonly header visible
- Trend, Volatility Expansion, and Mean Reversion candidate cards visible
- Mean Reversion proposal rendered with `MR-001-live-readonly-v0`,
  `ETH/USDT:USDT`, `long`, quantity `0.01`, max notional `20`, leverage `1`,
  and `single_tp_plus_sl`
- bounded live execute action remained disabled in proposal-only state
- no enabled execute, authorization-create, cancel, flatten, or retry action was
  present
- post-action evidence summary was visible

## Verification

Local verification performed:

- `python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py`
- `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py`
- `npm run lint`
- `npm run build`
- `python3 -m alembic heads`
- `git diff --check`

## Deployment State

Deployment status is recorded separately in the final task report. This document
records the local product/API work and safety semantics.
