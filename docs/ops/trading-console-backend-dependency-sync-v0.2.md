# Trading Console Backend Dependency Sync v0.2

Date: 2026-06-04

Scope: frontend Gate 2 read-model integration verification.

## Summary

During authenticated frontend and server verification, all
`/api/trading-console/*` read-model endpoints returned HTTP 200. One backend
contract-shape gap was observed in the degraded/no-owner-service authorization
path and fixed.

Follow-up server runtime probes and the later production runtime-bound switch
resolved the full-runtime binding dependencies:

- a SQLite config schema initialization parser issue, fixed in code;
- a live PG `signals` schema mismatch, fixed by controlled Alembic revision
  `042`;
- a live runtime profile selection/seed gap, resolved by Owner-approved
  `prelive_bnb_readonly_runtime` metadata seed and production runtime-bound
  health verification.

Current open dependencies are not read-model availability blockers. They are:

- the absence of Trading Console-scoped action contracts for cancel, replace,
  flatten, retry protection, runtime control, and auto-execution;
- protection-health grouping should separate current-scope active protection
  from historical BNB rows.

## Dependency Items

### TC-BE-DEP-002-01: `authorization-state` should always include `future_action_slots`

Status: CLOSED

Endpoint:

- `GET /api/trading-console/authorization-state`

Observed:

- In the current degraded path where `owner_trial_flow_service` is unavailable,
  the response `data` includes `carrier_id`, `status`, `is_actionable`, and
  `blocking_reason`.
- The response `data` does not include `future_action_slots`.

Expected:

- The endpoint contract lists `future_action_slots` as a `data` field.
- The field should be present in all branches, including `unknown`,
  `not_available`, and service-unavailable states.
- Safe value examples:
  - `{}`
  - `{ "void_authorization": "deferred_not_implemented", "cancel_authorization": "deferred_not_implemented" }`

Resolution:

- `authorization-state` now returns `future_action_slots` in all read-model
  branches:
  - owner trial flow service unavailable;
  - authorization read failure;
  - no active authorization;
  - active authorization present.
- The field remains a disabled/deferred read-model slot only. No action API,
  mutation endpoint, or authorization write path was added.

Frontend impact:

- Current frontend handles the field as optional and remains safe.
- The missing field prevents strict contract completeness for the degraded path.

Safety:

- This is read-model shape only.
- Do not add action endpoints.
- Do not enable authorization mutation.
- Do not change execute/cancel/flatten/retry protection behavior.

Evidence:

- Authenticated proxy verification returned HTTP 200 for
  `/api/trading-console/authorization-state`.
- Server-side authenticated verification on 2026-06-04 returned
  `has_future_action_slots=true` for
  `/api/trading-console/authorization-state`.
- Targeted read-model tests cover the degraded owner-service-unavailable path.

Validation:

- `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
  - 11 passed
- `python3 -m py_compile src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py src/interfaces/api.py`
  - passed
- Server API white-list verification:
  - 12 Trading Console GET endpoints returned 200.
  - POST probes returned 405.
  - `no_action_guarantee` action flags remained false.

## Non-Issues

No remaining read-only backend contract gaps were found for:

- `dashboard-state`
- `account-risk`
- `order-ledger`
- `protection-health`
- `recovery-exception-state`
- `execution-control-state`
- `review-state`
- `audit-chain`
- `carrier-availability`
- `signal-marker-feed`
- `api-classification`

## Frontend Workaround

The frontend normalizes absent `future_action_slots` to an empty disabled-slot
list and does not expose any action button.

### TC-BE-DEP-002-02: full runtime startup must create SQLite config tables from `config_tables.sql`

Status: CLOSED

Observed:

- A server-side full-runtime read-only probe using `src.main` on an isolated
  port failed before API binding with:
  - `no such table: system_configs`
- The release had `data/v3_dev.db`, but it was an empty SQLite file.
- `ConfigManager._create_tables()` split `config_tables.sql` on semicolons and
  skipped any statement whose trimmed text started with `--`.
- Because each schema block starts with comments before `CREATE TABLE`, the
  full `CREATE TABLE` statement was skipped.

Resolution:

- `ConfigManager._create_tables()` now strips pure comment lines before
  splitting statements.
- A temporary local SQLite DB initialization verified required config tables
  are created, including `system_configs`, `risk_configs`, `strategies`,
  `symbols`, and `exchange_configs`.

Safety:

- This is config metadata initialization only.
- No PG business state was changed by the code fix.
- Before the server runtime probe, the server SQLite DB was backed up to:
  `/home/ubuntu/brc-deploy/backups/v3_dev-before-runtime-probe-20260604-1526.db`

Validation:

- Temporary `ConfigManager(db_path=<tmp>)` initialization created 9 config tables.
- `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
  - 11 passed
- `python3 -m py_compile src/application/config_manager.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py src/interfaces/api.py`
  - passed

### TC-BE-DEP-002-03: full runtime PG signal schema must align with PG signal ORM

Status: CLOSED

Observed:

- After TC-BE-DEP-002-02 was fixed, a second server-side full-runtime read-only
  probe using `src.main` on isolated port `18082` progressed past SQLite config
  initialization but failed before API binding with:
  - `column "signal_id" referenced in foreign key constraint does not exist`
- PG introspection showed current live PG has signal-related columns on:
  - `orders.signal_id`
  - `positions.signal_id`
  - `execution_intents.signal_id`
  - historical/research signal tables
- PG introspection did not show `signals.signal_id`.
- Current `PGSignalORM` expects:
  - `signals.id` as integer identity primary key
  - `signals.signal_id` as unique string identifier
  - `signal_take_profits.signal_id` foreign-keyed to `signals.signal_id`
- Historical migration `2026-05-03-003_create_signals_accounts_tables.py`
  created `signals.id` as a string primary key and did not create
  `signals.signal_id`.

Expected:

- Full runtime startup must either:
  - run against a migrated PG `signals` schema matching `PGSignalORM`; or
  - use a compatibility repository/ORM path for the legacy `signals` schema.

Resolution:

- Added Alembic revision `042`
  (`migrations/versions/2026-06-04-042_align_pg_signals_runtime_schema.py`).
- The migration refuses automatic conversion if legacy `signals` or
  `backtest_reports` rows exist.
- For the inspected Tokyo PG state, both tables were empty; the migration
  recreated runtime-shaped `signals`, `signal_take_profits`, and
  `signal_attempts` schema.
- Tokyo Alembic head now reports `042`.

Frontend impact:

- No impact on the deployed API-only Trading Console frontend.
- This item no longer blocks full runtime startup.

Safety:

- Pre-migration schema/count evidence was saved to:
  `/home/ubuntu/brc-deploy/backups/trading-console-pg-signals-pre-042-20260604-1537.json`
- The migration was schema-only for empty legacy signal tables.
- No live order, cancel, flatten, replace, retry protection, or auto-execution
  was executed during the probe or migration.

Evidence:

- Server full-runtime read-only probe:
  - `BACKEND_PORT=18082`
  - `BRC_EXECUTION_PERMISSION_MAX=read_only`
  - `RUNTIME_CONTROL_API_ENABLED=false`
  - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`
  - result: health endpoint did not become ready
  - failure marker: `column "signal_id" referenced in foreign key constraint does not exist`
- Post-migration PG introspection:
  - `alembic_version=042`
  - `signals.signal_id` exists
  - `signal_take_profits` exists
  - `signal_attempts` exists
  - all three runtime signal tables had count `0` at verification time.

### TC-BE-DEP-002-04: full runtime live profile selection must be explicitly resolved

Status: CLOSED_WITH_READONLY_RUNTIME_BOUND_CONSTRAINT

Observed:

- After TC-BE-DEP-002-03 was fixed, a third server-side full-runtime read-only
  probe using `src.main` on isolated port `18082` progressed past PG signal
  initialization but failed before API binding with:
  - `Fatal startup error: [F-003] Runtime config resolution failed: runtime profile not found: sim1_eth_runtime`
- `src.main` still defaults to `RUNTIME_PROFILE=sim1_eth_runtime` when no
  runtime profile selector is provided.
- Production/live validation rejects `RUNTIME_PROFILE` as a live-like env
  selector because live execution scope must come from PG-backed Owner
  authorization, not from an environment variable.
- Tokyo PG `runtime_profiles` table exists but has no active profile rows
  available for full-runtime startup.

Resolution applied:

- `RuntimeConfigResolver.resolve_startup()` now separates startup profile
  resolution from ad hoc `RUNTIME_PROFILE` fallback behavior.
- In production/live-like environments, startup without an explicit profile now
  requires an active PG `runtime_profiles` row.
- The non-live legacy default fallback to `sim1_eth_runtime` is preserved for
  local/test compatibility.
- `src.main` now calls `resolve_startup(profile_name=os.environ.get("RUNTIME_PROFILE"))`
  instead of unconditionally defaulting to `sim1_eth_runtime`.

Current verified state:

- Tokyo PG `runtime_profiles` schema is present and runtime-shaped:
  - columns: `name`, `description`, `profile_payload`, `is_active`,
    `is_readonly`, `created_at`, `updated_at`, `version`;
  - primary key: `runtime_profiles_pkey` on `name`;
  - indexes: `idx_runtime_profiles_active`,
    `idx_runtime_profiles_updated_at`.
- Owner-approved seed created exactly one active PG runtime profile:
  `prelive_bnb_readonly_runtime`.
- The seeded profile is read-only and scoped to `BNB/USDT:USDT`, `LONG`,
  `1x`, fixed cap `0.01` BNB / `20` USDT. It does not grant generic live
  order permission or auto-execution.
- Production now runs the full `src.main` backend and `/api/health` returns
  `runtime_bound=true`, `live_ready=false`.
- Service environment still preserves the read-only guard:
  `BRC_EXECUTION_PERMISSION_MAX=read_only`,
  `RUNTIME_CONTROL_API_ENABLED=false`, and
  `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`.

Evidence:

- Runtime-bound preflight audit:
  `docs/ops/trading-console-runtime-bound-preflight-audit-2026-06-04.md`.
- Runtime profile seed/runbook:
  `docs/ops/trading-console-runtime-bound-transition-runbook-2026-06-04.md`.
- Production health evidence is recorded in:
  `reports/trading-console-server-deploy-acceptance-2026-06-04/trading-console-current-live-state-v13-20260604.json`.

### TC-BE-DEP-002-05: full action API surface remains deferred behind read-only deployment guards

Status: RESOLVED_LOCALLY_2026-06-04

Observed:

- Production backend is runtime-bound and returns `/api/health.runtime_bound=true`.
- Production still returns `/api/health.live_ready=false`.
- Service environment still includes:
  - `BRC_EXECUTION_PERMISSION_MAX=read_only`
  - `RUNTIME_CONTROL_API_ENABLED=false`
  - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`
- The deployed Trading Console frontend authenticated browser scan found no
  enabled real action controls for execute, cancel, flatten, retry protection,
  or related live actions.
- The frontend still presents action slots as disabled/future, which is safe but
  does not satisfy a full action-enabled product gate.

Expected for full action-enabled Gate:

- Backend must expose explicit, scoped action APIs for any enabled frontend
  action:
  - execute;
  - cancel;
  - replace;
  - flatten;
  - retry protection;
  - runtime start / runtime control;
  - auto-execution grant, if still in scope.
- Each action API must define:
  - exact Owner authorization model;
  - symbol/side/leverage/notional boundary;
  - idempotency and max-attempt behavior;
  - preflight gate requirements;
  - audit record contract;
  - post-action read-model state transition.
- Frontend must keep action controls disabled until the backend returns an
  actionable state with a concrete action endpoint and scope.

Current evidence:

- Production OpenAPI audit:
  `reports/trading-console-server-deploy-acceptance-2026-06-04/action-surface-audit-v14-20260604.json`.
- The OpenAPI audit found `trading_console_has_non_get_action=false`.
- The OpenAPI audit found
  `cancel_flatten_replace_retry_trading_console_present=false`.
- The only confirmed live execute-like endpoint is outside the Trading Console
  namespace:
  `POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute`.
- `POST /api/brc/operations/{operation_id}/cancel` exists, but that endpoint
  cancels a BRC operation lifecycle record, not an exchange order.
- `reports/trading-console-server-deploy-acceptance-2026-06-04-v13-auth/browser-validation-v05-logged-in-cdp.json`
  has `enabled_real_action_pass=true`.
- `reports/trading-console-server-deploy-acceptance-2026-06-04/trading-console-current-live-state-v13-20260604.json`
  shows `execution-control-state.hard_gate.status=blocked` with
  `authorization_actionable=block`.
- The only executed live action in the current acceptance sequence was the
  separately Owner-authorized one-shot BNB execute:
  `auth-b6678a34a93c44d49849c09d995d98bd`,
  `BNB/USDT:USDT LONG`, `0.01`, `1x`, max `20` USDT, max attempts `1`.

Action readiness matrix:

| Action | Current exposed endpoint | Existing lower-level primitive | Current status | Required before frontend enablement |
| --- | --- | --- | --- | --- |
| Execute | `/api/brc/owner-trial-flow/authorizations/{authorization_id}/execute` | `OwnerBoundedExecutionService` + `ExchangeGateway.place_order` | PASS_WITH_CONSTRAINT for the consumed one-shot BNB authorization only | New unconsumed Owner authorization, scoped Trading Console action contract, idempotency, pre/post audit, and no generic reuse of the consumed auth |
| Cancel exchange order | None under `/api/trading-console/*` | `ExchangeGateway.cancel_order`; repository batch delete has unsafe delete semantics; `OrderLifecycleService.cancel_order` is local state only | DEFERRED | Dedicated Owner-scoped cancel endpoint, exchange-order target validation, local/exchange reconciliation, audit, and no PG delete semantics |
| Replace order | None | No Trading Console-level primitive confirmed | DEFERRED | Define cancel+new or amend semantics, scope, idempotency, partial-fill handling, audit, and protection ownership rules |
| Flatten position | None | BRC `emergency_flatten` operation is dry-run only and explicitly does not cancel orders or close positions | DEFERRED | Dedicated live flatten design, exact scope, close/cancel ordering, final gate, unmanaged exposure policy, and Owner confirmation |
| Retry protection | None | Protection planning exists for owner-bounded execute; no retry action endpoint confirmed | DEFERRED | Current-scope protection diagnosis, retry idempotency, orphan handling, order collision checks, audit, and Owner confirmation |
| Runtime start/control | None under Trading Console; runtime control env disabled | Runtime is already process-bound, but control API is disabled | DEFERRED | Separate runtime-control authorization, environment guard changes, and startup/shutdown audit contract |
| Auto-execution grant | None | No enabled grant path; `live_ready=false` | BLOCKED | Separate Owner architecture decision; current task must not enable this |

Safety:

- Do not infer generic action permission from the one-shot BNB execute.
- Do not enable frontend action buttons from read-model placeholders.
- Do not expose broad action APIs without a new explicit Owner authorization
  and backend action contract.

### TC-BE-DEP-002-06: protection-health should separate current-scope protection from historical BNB rows

Status: OPEN

Observed:

- Pre-close current live scope was already flat by TP fill, with residual SL
  protection still open:
  - Entry `d791fbde-8498-4d3c-953f-0060b5f3a018`, exchange `91128701174`,
    `FILLED`, qty `0.01`, avg `592.06`;
  - TP `9f7ad378-16ef-4161-86e1-f94ba79d5ef0`, exchange `91128701434`,
    `FILLED`, qty `0.01`, avg `597.98`;
  - SL `c9a4faae-eaa5-45d1-9606-bb3181e5c644`, exchange
    `4000001479555379`, `OPEN`, residual protection.
- Post-close current scope has no active PG or exchange position and no active
  PG or exchange open order.
- `GET /api/trading-console/protection-health?include_exchange=true` now
  returns `tp_count=0`, `sl_count=0`, `current_scope_active_protection=[]`,
  `historical_protection_orders` containing closed historical BNB rows, and
  `orphan_protection_orders=[]`.
- The same read model keeps compatibility `protection_orders`, but primary
  Owner-facing counts are current-scope active counts only.

Expected:

- The read model should expose either:
  - a current-scope protection collection separate from historical rows; or
  - enough structured classification for the frontend adapter to distinguish
    active current protection from history without deriving from raw IDs.
- The Owner-facing protection page should emphasize current active protection
  first and keep historical protection rows out of the primary count/card.

Frontend impact:

- Protection Health now shows current active protection first and keeps
  historical rows inside a collapsed `历史保护记录` section.
- Aggregate TP/SL counts are no longer inflated by historical BNB rows.

Evidence:

- `reports/trading-console-server-deploy-acceptance-2026-06-04/trading-console-protection-health-v12-20260604.json`
- `reports/trading-console-server-deploy-acceptance-2026-06-04/trading-console-current-live-state-v13-20260604.json`
- `reports/trading-console-bnb-close-2026-06-04/post-close-trading-console-snapshot.json`
- `reports/trading-console-bnb-close-2026-06-04/screenshots/protection.png`
- `tests/unit/test_trading_console_readmodels.py::test_protection_health_counts_current_scope_active_protection_only`

Safety:

- This is read-model grouping/contract work only.
- The separate Owner-authorized BNB closeout run canceled only the residual
  current-scope SL protection after confirming the BNB position was already
  flat; this dependency item did not add broad action APIs or frontend action
  controls.
