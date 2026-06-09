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

# Trading Console Read-Model Sprint Report

Date: 2026-06-04

Mode: read-only backend aggregation. No live order, cancel, replace, flatten,
protection retry, runtime start, auto-execution grant, or PG state mutation was
performed.

## Dependency Source

- Source reference used: `docs/product/交易控制台后端依赖同步单 v0.1`.
- Ops dependency copy prepared:
  `docs/ops/trading-console-backend-dependency-sync-v0.1.md`.

## Objects Processed

- `dashboard_state`
- `account_risk`
- `order_ledger`
- `protection_health`
- `recovery_exception_state`
- `authorization_state`
- `execution_control_state`
- `review_state`
- `audit_chain`
- `carrier_availability`
- `signal_marker_feed`
- `api_classification`

## Backend Outputs

Implemented read-only namespace:

- `GET /api/trading-console/dashboard-state`
- `GET /api/trading-console/account-risk`
- `GET /api/trading-console/order-ledger`
- `GET /api/trading-console/protection-health`
- `GET /api/trading-console/recovery-exception-state`
- `GET /api/trading-console/authorization-state`
- `GET /api/trading-console/execution-control-state`
- `GET /api/trading-console/review-state`
- `GET /api/trading-console/audit-chain`
- `GET /api/trading-console/carrier-availability`
- `GET /api/trading-console/signal-marker-feed`
- `GET /api/trading-console/api-classification`

Contract draft:

- `docs/ops/trading-console-read-model-api-contract-v0.1.md`

## Aggregation Evidence

Unit evidence covers:

- operator-auth requirement for the Trading Console namespace
- GET-only Trading Console route registration
- default non-live-connected mode with no exchange or account snapshot calls
- orphan protection classification as warning, not a stop condition
- exchange-flat plus PG-open-protection drift represented as blocked/orphaned
  without exposing action APIs
- consumed authorization blocking execution-control while staying read-only
- untracked fee/funding/slippage/fill-detail fields represented as
  `not_available`
- audit-chain IDs exposed with raw payloads masked or omitted
- all Trading Console read-model endpoints returning the shared envelope
- existing BRC console readiness surface remaining compatible with cached
  account snapshot facts
- `api_brc_console.py` fallback facts do not bypass unsafe live-environment
  hard gates

Commands:

```bash
python3 -m compileall -q src scripts tests/unit/test_trading_console_readmodels.py
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py
python3 -m pytest -q tests/unit/test_brc_console_api_surface.py
python3 -m pytest -q tests/unit/test_owner_trial_flow.py -k "bnb_final_gate or final_gate_fallback"
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py tests/unit/test_brc_console_api_surface.py
git diff --check
```

Results:

- `tests/unit/test_trading_console_readmodels.py`: 10 passed
- `tests/unit/test_brc_console_api_surface.py`: 33 passed
- `tests/unit/test_owner_trial_flow.py -k "bnb_final_gate or final_gate_fallback"`:
  11 passed
- compileall: passed
- diff check: passed

## Warnings And Gaps

- BNB TP/SL open orders, orphan protection, stale data, and PG/exchange drift
  are warnings/degraded read-model facts and do not stop aggregation.
- Missing recovery/audit services or optional tables are reported as
  `unavailable`, not as clean state.
- No fills table is available in v1.
- Stored `client_order_id`, fees, funding, and slippage are unavailable unless
  already present in injected repositories/services.
- `include_exchange=false` is the default and does not call exchange or account
  snapshot readers. `include_exchange=true` is limited to read-only exchange
  methods exposed by the configured gateway.

## Safety Proof

- API router methods are `GET` only.
- Shared response envelope includes `live_ready=false`.
- Shared `no_action_guarantee` records false for order placement, cancel,
  replace, flatten, protection retry, runtime start, auto-execution grant, and
  PG mutation.
- Tests assert the default path does not call exchange read methods.
- Tests assert fallback/local facts cannot turn an unsafe live environment into
  an executable final gate.
- No runtime start, no live order action, and no protection retry path was added.
