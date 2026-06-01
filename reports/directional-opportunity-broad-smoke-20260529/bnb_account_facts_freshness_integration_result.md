# BNB Account Facts Freshness Integration Result

## 1. Summary

Integrated safe account-facts freshness into the BNB testnet rehearsal preflight collector and Strategy Trial Readiness Framework.

This remains readiness-only. No testnet order, live order, `ExecutionIntent`, runtime execution, leverage change, transfer, withdrawal, credential mutation, or automatic execution was performed or enabled.

## 2. What Changed

- `TrialPreflightFact` now supports explicit account-facts states including `stale`, `unavailable`, and `required_before_rehearsal`.
- The BNB preflight collector evaluates account facts with timestamp/freshness, equity availability, available-margin availability, source, and read-only evidence.
- `GET /api/brc/strategy-trial-readiness/v1` now wires account facts via the existing cached `AccountSnapshot` read path.
- Readiness blockers now include concrete account-facts blockers:
  - `account_facts_required_before_rehearsal`
  - `account_facts_stale`
  - `account_facts_unavailable`
  - `account_equity_unavailable`
  - `available_margin_unavailable`
- Owner Console types include per-fact `blockers[]` so account-facts details can be rendered without hiding missing equity or margin.

## 3. Account Facts Source Chosen

Source: existing runtime cached `AccountSnapshot` summary through `_cached_account_equity_snapshot(...)`.

Why this source:

- It is already used by the read-only BRC account facts surface.
- It does not fetch balances in this endpoint.
- It does not call `place_order`, `cancel_order`, transfer, withdrawal, leverage, or execution paths.
- It exposes freshness from snapshot timestamp and can truthfully represent unavailable or stale facts.

No private account API was called by this task. No credentials were created or modified.

## 4. Available / Unavailable Facts

When a fresh cached snapshot is present:

- `account_facts` status becomes `clear`.
- `equity_available=true`.
- `available_margin_available=true`.
- timestamp and age seconds are exposed in evidence.
- readiness can advance to `testnet_rehearsal_ready_pending_owner_authorization` if all other safety facts are clear.

When no safe snapshot is present:

- `account_facts` status becomes `unavailable`.
- blockers include `account_facts_unavailable`, `account_equity_unavailable`, and `available_margin_unavailable`.
- readiness remains `testnet_rehearsal_not_ready_with_explicit_blockers`.

When the snapshot is stale:

- `account_facts` status becomes `stale`.
- blocker includes `account_facts_stale`.
- readiness remains blocked.

## 5. Current Readiness Verdict

Framework behavior:

- Clear account facts + clear safety facts + missing Owner testnet authorization:
  - `testnet_rehearsal_ready_pending_owner_authorization`
- Missing/stale/unavailable account facts:
  - `testnet_rehearsal_not_ready_with_explicit_blockers`

The system remains `live_ready=false` and `auto_execution_ready=false`.

## 6. Files Changed

- `src/application/strategy_trial_preflight_facts.py`
- `src/application/strategy_trial_readiness.py`
- `src/interfaces/api_brc_console.py`
- `gemimi-web-front/src/services/api.ts`
- `gemimi-web-front/src/pages/brc/OwnerConsoleV2.test.tsx`
- `tests/unit/test_strategy_trial_readiness.py`
- `tests/unit/test_brc_console_api_surface.py`

## 7. Safety Proof

| item | result |
| --- | --- |
| testnet order | no |
| live order | no |
| order cancellation | no |
| `ExecutionIntent` created | no |
| execution permission granted | no |
| runtime execution started | no |
| automatic execution enabled | no |
| leverage modified | no |
| transfer/withdrawal | no |
| credential/API key mutation | no |
| observation-to-order shortcut | no |
| `exchange_gateway` modified | no |

## 8. Tests / Validation

- `python3 -m compileall -q src scripts` passed.
- `python3 -m pytest -q tests/unit/test_strategy_trial_readiness.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py` passed: 50 passed, 1 existing SQLAlchemy resource warning.
- `cd gemimi-web-front && npm run lint` passed.
- `cd gemimi-web-front && npx vitest run` passed: 7 files, 12 tests.
- `cd gemimi-web-front && npm run build` passed.

## 9. Next Step

Run an Owner-authorized testnet readiness API check in a process with fresh cached account snapshot, GKS clear, startup guard armed, clean reconciliation, and no BNB position/open orders.
