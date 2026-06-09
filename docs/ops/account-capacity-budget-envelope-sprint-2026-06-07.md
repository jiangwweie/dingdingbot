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

# Account Capacity and BudgetEnvelope Recommendation Sprint - 2026-06-07

## Goal

Build a standard read-only sizing recommendation layer:

`Account Facts -> Account Capacity -> Risk Tier -> BudgetEnvelope -> ActionCandidate sizing -> Owner confirmation`

The layer reduces manual `qty/max_notional` entry pressure, but it does not
grant permission to trade and does not enable auto-execution.

## Budget Model

`AccountCapacity` is derived from Trading Console read models:

- account equity;
- available balance;
- margin facts;
- current exposure notional;
- open-order notional;
- conservative max usable notional;
- freshness;
- source;
- `BlockerRecord` entries when facts are missing, stale, or no headroom exists.

`RiskTier` supports:

- `tiny`;
- `small`;
- `custom`.

Default tiers are conservative and never assume full account balance is
available. `BudgetEnvelope` caps usable budget by account capacity and risk
tier, and emits:

- `total_budget`;
- `max_notional_per_action`;
- `max_daily_loss`;
- `max_active_positions`;
- `max_attempts`;
- `max_leverage`;
- `allowed_symbols`;
- `allowed_sides`;
- `review_requirement`;
- Owner confirmation requirement.

## Trading Console Output

New read-only endpoint:

- `GET /api/trading-console/budget-recommendation`

The endpoint exposes account capacity, risk tier, budget envelope, examples,
missing facts, warnings, blockers, and a no-action guarantee. It accepts
`include_exchange=false` by default, and only reads exchange/account facts when
called with `include_exchange=true` through the existing Trading Console
read-only path.

Existing read-only outputs now include budget recommendation context:

- `GET /api/trading-console/action-entry-readiness`
- `GET /api/trading-console/owner-action-flow`

`GenericActionSpec` and Trading Console candidate output are enriched in the
read-model payload with `budget_envelope_ref`, `recommended_max_notional`, and
Owner-confirmation-required sizing metadata. Backend action state remains
disabled.

## Examples

The recommendation output includes dry-run-only examples for:

- Trend / SOL: `TF-001-live-readonly-v0`, `SOL/USDT:USDT`, long.
- Mean reversion / ETH: `MR-001-live-readonly-v0`, `ETH/USDT:USDT`, long.
- Volatility proposal: `VB-001-live-readonly-v0`, `ETH/USDT:USDT`, long.

All examples are recommendation payloads only. They do not create
authorization, execution intent, order, runtime start, PG mutation, or exchange
write action.

## Degraded Path

If account facts are missing or stale, the endpoint returns degraded output and
records blocker records such as:

- `BUDGET-ACCOUNT-CAPACITY-ACCOUNT-FACTS`
- `BUDGET-ACCOUNT-CAPACITY-FRESHNESS`
- `BUDGET-ACCOUNT-CAPACITY-NO-HEADROOM`

The degraded path still returns contracts, examples, warnings, and Owner
confirmation requirements. Suggested notional is withheld when capacity cannot
be computed.

## Safety Proof

- Trading Console namespace remains GET-only and operator-authenticated.
- `include_exchange=false` remains the default.
- The new layer does not expose POST/DELETE action endpoints.
- `BudgetEnvelope` explicitly sets `not_authorization=true`,
  `not_execution_permission=true`, `grants_trading_permission=false`,
  `may_execute_live=false`, and `frontend_action_enabled=false`.
- `no_action_guarantee` remains false for order placement, runtime start,
  auto-execution, and PG mutation.
- Missing Owner confirmation, stale/unreadable account facts, exposure
  conflict, TP/SL unavailable, recording unavailable, and runtime/env/credential
  guard failures remain hard blockers for live action.

## Validation

Validation run:

- `pytest -q tests/unit/test_trading_console_readmodels.py`
- `python3 -m compileall -q src tests/unit/test_trading_console_readmodels.py`
- `python3 -m alembic heads`
- `git diff --check`
- targeted secret-pattern scan over changed sprint files

Result:

- Trading Console read-model tests: `20 passed`
- compileall: pass
- Alembic heads: `042 (head)`
- diff whitespace: pass
- secret scan: false positives only in existing auth-test strings and an
  existing API-key permission method name; no new credential material added
