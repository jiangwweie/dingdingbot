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

# Trading Console Gate 2 Frontend Contract Evidence Report

Date: 2026-06-04

> [!IMPORTANT]
> 2026-06-08 scope note:
> This is historical evidence for the Gate 2 read-model frontend contract. It
> does not define the current Trading Console product as read-only. Current
> product authority is `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`.

Scope: `/api/trading-console/*` read-model frontend-contract acceptance.

Decision: Gate 2 can pass for read-only frontend documentation and AI Studio
planning, with the v1 constraints below frozen in the frontend contract.

## Source Checklist

- Saved checklist:
  `docs/ops/trading-console-gate2-frontend-contract-acceptance-checklist-v0.1.md`
- API contract checked:
  `docs/ops/trading-console-read-model-api-contract-v0.1.md`

## Verification Summary

| Gate 2 condition | Result | Evidence |
| --- | --- | --- |
| `/api/trading-console/*` namespace mounted and stable | Pass | App route inventory exposes 12 Trading Console routes. |
| All read models are GET-only | Pass | `api_trading_console.py` contains only `@router.get`; unit test `test_trading_console_router_is_get_only`. |
| Default `include_exchange=false` does not call exchange | Pass | `_dependencies()` reads account snapshot only under `include_exchange`; unit test `test_trading_console_default_does_not_call_exchange`. |
| `include_exchange=true` is read-only | Pass | Implementation only calls `get_account_snapshot`, `fetch_positions`, and `fetch_open_orders`; fake write methods are guarded in tests. |
| Shared envelope fields stable | Pass | All endpoints return `TradingConsoleReadModelResponse`; unit test checks all endpoint envelopes. |
| `freshness_status` semantics stable | Pass | Contract defines `fresh`, `warning`, `degraded`, `not_live_connected`; response logic maps unavailable/warnings/exchange omission explicitly. |
| `warnings / blockers / unavailable` semantics stable | Pass | Warnings model orphan/stale/drift; blockers model hard read-model gates; unavailable records missing sources. |
| `no_action_guarantee` usable as frontend safety constraint | Pass | Envelope fixes all action booleans to false; unit tests assert them across endpoints. |
| P0 pages have endpoints | Pass | Dashboard, account risk, order ledger, protection health, recovery, authorization, execution control, review, audit, carrier availability all have read models. |
| Order classification semantics stable | Pass | `matched`, `pg_unchecked`, `pg_only`, `exchange_only`, `mismatch`, `orphan_protection`, `unknown` documented and implemented. |
| Protection state enum stable | Pass | `protected`, `partially_protected`, `unprotected`, `unknown`, `orphaned` documented and implemented. |
| Recovery deferred action semantics stable | Pass | Recovery read model exposes deferred actions only; no action API was added. |
| Authorization state semantics stable | Pass with v1 constraints | `is_actionable`, `is_consumed`, `is_expired`, `is_cancelled`, `scope_match`, and future slots are present; `scope_match=not_checked` must not display as pass. |
| Execution-control has no real execute | Pass | `execution_preview.status=not_available`, `deferred_execute_endpoint=true`; action absence test confirms no Trading Console execute route. |
| Review unavailable cost fields explicit | Pass | `fee`, `fee_asset`, `funding`, `slippage`, and fills table are `not_available`; unit test covers this. |
| Audit raw payload policy stable | Pass | `raw_payload_policy=masked_or_omitted`; unit test checks no `api_key`, `secret`, or `totp` leakage. |
| Carrier Shelf BNB v1 scope accepted | Pass with v1 constraint | Contract now states Carrier Shelf v1 is the current BNB-first carrier surface, not the final multi-carrier shelf. |
| Signal marker feed does not block P0 | Pass | Feed exists; chart adapter records backend-feed-only and lightweight charts not ready. |
| Old APIs isolated | Pass | `api_classification` and contract mark `/api/brc/*`, `/api/runtime/*`, and dev/testnet APIs as internal/legacy for frontend purposes. |
| Sample data excluded as truth source | Pass | `sample_data_policy=not_allowed_as_trading_console_truth_source` / `not_used` documented. |

## API Contract Consistency

The API contract is consistent with the Gate 2 checklist after adding the Gate 2
frontend constraints section:

- Trading Console facts must come from `/api/trading-console/*`.
- `not_live_connected` is not a safety verdict.
- `unavailable` is not clean.
- Deferred action slots are disabled/unavailable UI states only.
- Carrier Shelf BNB scope is accepted for v1 documentation only.
- Signal marker feed is a later chart-integration input, not a Gate 2 P0 chart
  requirement.

## Test Coverage Check

Covered by `tests/unit/test_trading_console_readmodels.py`:

- operator auth required
- router GET-only
- action APIs absent
- default `include_exchange=false`
- read-only `include_exchange=true` orphan-protection aggregation
- protected/orphan/degraded state does not expose actions
- consumed authorization blocks execution-control
- untracked cost fields are `not_available`
- audit raw payload masking
- all endpoints return the shared no-action envelope

## Verification Commands

```bash
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py
git diff --check
```

Results:

- Trading Console tests: 10 passed
- Diff check: passed

## Safety Proof

- No backend feature was added in this Gate 2 pass.
- No action API was added.
- No execute, cancel, flatten, or retry-protection code path was changed.
- No PG migration was created or run.
- No push, Tokyo deploy, or frontend change was performed.

## Gate 2 Result

Gate 2 is passable for read-only frontend documentation and AI Studio planning.

The frontend contract must preserve these v1 constraints:

- no real execution controls
- no old action API calls
- disabled/deferred action states only
- explicit display of `not_live_connected`, `unavailable`, and `not_available`
- BNB-first Carrier Shelf as v1 scope, not final product structure
