# Trading Console Gate 2 Frontend Contract Acceptance Report

Date: 2026-06-04

Scope: Gate 2 frontend handoff for `/api/trading-console/*` read-model
contracts.

Decision: **PASS_WITH_CONSTRAINT**.

Frontend documentation may start for the read-only Trading Console. The
constraints in this report must be carried into the product documentation, API
integration documentation, UI/page specification, and AI Studio read-only
frontend prompt package.

## Handoff Package

- `docs/ops/trading-console-gate2-frontend-contract-acceptance-checklist-v0.1.md`
- `docs/ops/trading-console-gate2-frontend-contract-acceptance-report-2026-06-04.md`
- `docs/ops/trading-console-read-model-api-contract-v0.1.md`
- `docs/ops/trading-console-read-model-sprint-report-2026-06-04.md`
- `docs/ops/trading-console-backend-dependency-sync-v0.1.md`

## Repository Facts Verified

- Branch: `dev`
- Backend read-model commit: `51d8a6da feat(trading-console): add read-only read models and safety coverage`
- Trading Console namespace: `/api/trading-console/*`
- Route inventory: 12 Trading Console routes, all `GET`
- `include_exchange=false`: default
- `include_exchange=true`: read-only account snapshot, positions, and open-order reads only
- Alembic head: `041`
- Push/deploy status: not pushed, not deployed by this handoff task

## Gate 2 Acceptance Matrix

| # | Gate 2 item | Result | Evidence / constraint |
| --- | --- | --- | --- |
| 1 | `/api/trading-console/*` read-model namespace mounted and stable | PASS | `api_trading_console.py` is mounted from `api.py`; route inventory shows 12 endpoints. |
| 2 | All read models remain GET-only | PASS | All Trading Console routes are `GET`; `test_trading_console_router_is_get_only` covers this. |
| 3 | Default `include_exchange=false` does not call exchange | PASS | `_dependencies()` only reads account snapshot when `include_exchange=True`; test asserts no exchange/account calls on default dashboard. |
| 4 | `include_exchange=true` only calls read-only exchange methods | PASS | Implementation uses `get_account_snapshot`, `fetch_positions`, and `fetch_open_orders`; no write methods are called. |
| 5 | Shared envelope fields frozen | PASS | All endpoints return `TradingConsoleReadModelResponse`: `read_model`, `generated_at_ms`, `source`, `freshness_status`, `warnings`, `blockers`, `unavailable`, `data`, `no_action_guarantee`, `live_ready=false`. |
| 6 | `freshness_status` semantics frozen | PASS_WITH_CONSTRAINT | Contract defines `fresh`, `warning`, `degraded`, and `not_live_connected`; frontend must not display `not_live_connected` as account-safe. |
| 7 | `warnings / blockers / unavailable` semantics frozen | PASS_WITH_CONSTRAINT | Warnings are non-blocking risks; blockers are hard read-model gates; unavailable is missing source and must not be treated as clean. |
| 8 | `no_action_guarantee` is frontend safety constraint | PASS | Envelope fixes all action booleans to false; tests assert this across all endpoints. |
| 9 | P0 pages have read-model endpoints | PASS | Dashboard, account risk, order ledger, protection, recovery, authorization, execution-control, review, audit, and carrier availability have endpoints. |
| 10 | Order ledger classification semantics frozen | PASS | Contract lists `matched`, `pg_unchecked`, `pg_only`, `exchange_only`, `mismatch`, `orphan_protection`, `unknown`; tests cover orphan protection. |
| 11 | Protection state enum semantics frozen | PASS_WITH_CONSTRAINT | `protected`, `partially_protected`, `unprotected`, `unknown`, `orphaned` exist; frontend must show orphaned/degraded as non-executable. |
| 12 | Recovery deferred action semantics frozen | PASS | Recovery model exposes `deferred_actions`; no retry/cancel/flatten action API is exposed. |
| 13 | Authorization lifecycle semantics frozen | PASS_WITH_CONSTRAINT | `is_actionable`, `is_consumed`, `is_expired`, `is_cancelled`, `scope_match`, and future slots exist; `scope_match=not_checked` must not be shown as pass. |
| 14 | Execution-control is not an execute endpoint | PASS | `execution_preview.status=not_available`, `deferred_execute_endpoint=true`; action absence test covers execute route absence. |
| 15 | Review cost/fill gaps are explicit | PASS | Fills table, fee, fee asset, funding, and slippage are `not_available`; tests cover unavailable cost fields. |
| 16 | Audit raw payload policy fixed | PASS | `raw_payload_policy=masked_or_omitted`; tests check no `api_key`, `secret`, or `totp` leakage. |
| 17 | Carrier Shelf v1 BNB scope accepted | PASS_WITH_CONSTRAINT | V1 reports the current BNB-first carrier surface only; frontend docs must not present this as final multi-carrier shelf. |
| 18 | Signal marker feed is not P0 blocker | DEFERRED | Feed exists for later chart work; TradingView/lightweight-charts integration is outside Gate 2. |
| 19 | Old APIs are not Trading Console truth source | PASS | Contract marks `/api/brc/*`, `/api/runtime/*`, and `/api/dev/testnet/brc/*` as internal/legacy/dev-testnet for frontend purposes. |
| 20 | Sample data is not a truth source | PASS | `api_classification` and contract mark sample data as not allowed/not used for Trading Console truth. |

No Gate 2 item is classified as `BLOCKED`.

## Frontend Constraints To Carry Forward

- The Gate 2 frontend may use only `/api/trading-console/*` for Trading Console
  facts.
- The Gate 2 frontend must not call `/api/brc/*`, `/api/runtime/*`, or
  `/api/dev/testnet/brc/*` as Trading Console truth sources.
- No execute, cancel, replace, flatten, retry-protection, runtime-start, or
  auto-execution UI may be enabled.
- `deferred_actions`, `future_action_slots`, and `deferred_execute_endpoint`
  are disabled/unavailable states only.
- `not_live_connected` means exchange reads were not requested; it is not an
  account safety verdict.
- `unavailable` and `unknown` must not be displayed as clean.
- `not_available` fields must be shown as unavailable and must not be estimated
  by the frontend.
- BNB-first Carrier Shelf is a v1 scope constraint, not final product
  structure.
- Signal marker feed can be documented as a future chart/feed input, not as a
  Gate 2 P0 chart requirement.

## Document Cross-Check

- API contract is aligned with the checklist after adding Gate 2 frontend
  constraints.
- Sprint report is aligned with current verification counts: Trading Console
  tests `10 passed`, BNB final-gate/fallback subset `11 passed`.
- Backend dependency sync remains aligned: all read-model objects are mapped to
  `/api/trading-console/*`; action APIs remain deferred/out of scope.

## Verification Commands

```bash
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py
python3 -m pytest -q tests/unit/test_brc_console_api_surface.py
python3 -m pytest -q tests/unit/test_owner_trial_flow.py -k "bnb_final_gate or final_gate_fallback"
python3 -m alembic heads
git diff --check
```

Results:

- Trading Console read-model tests: 10 passed
- BRC console API surface tests: 33 passed
- BNB final-gate/fallback subset: 11 passed
- Alembic heads: `041 (head)`
- Diff check: passed

## Safety Proof

- This handoff task added/updated documentation only.
- No backend feature was added.
- No frontend implementation was added.
- No PG migration was created or run.
- No live order, cancel, replace, flatten, retry protection, runtime start,
  auto-execution grant, credential/API-key change, push, or Tokyo deploy was
  performed.

## Final Result

Gate 2 result: **PASS_WITH_CONSTRAINT**.

The frontend window may start formal read-only Trading Console documentation
and AI Studio planning, provided it carries forward all constraints listed
above.
