# Trading Console Read-Model Sprint Safety Blocker

Date: 2026-06-03

Mode: read-only safety inspection and backend read-model preparation. No
runtime start, order placement, cancel, replace, flatten, recovery action,
credential change, profile change, PG mutation, migration, commit, or push was
performed.

## Goal

Implement or safely prepare the Trading Console backend read-model foundation
under `/api/trading-console/*`, using `交易控制台后端依赖同步单 v0.1` as the
dependency source, without touching real execution actions.

## Start Safety Evidence

Tokyo deployment facts observed read-only:

- Host API: `GET http://127.0.0.1:18080/api/health`
- Response: `{"status":"ok","service":"brc_operator_console","runtime_bound":false,"live_ready":false}`
- Tokyo checkout short SHA: `0a94553`
- Tokyo tag at HEAD: `brc-bnb-prelive-20260601-r38`
- Tokyo PG Alembic: `041`

Tokyo PG BNB facts observed read-only:

- `orders` has two BNB open protection rows:
  - `SL` order `3b43781d-d81b-4288-b1ed-511b41b41f18`,
    exchange order `4000001470395922`, parent
    `26e76738-2513-4cfb-9227-3c5d248f3125`, `filled_qty=0E-18`
  - `TP1` order `b6e8456f-bc31-4945-b05f-399e39c05da9`,
    exchange order `91085295597`, parent
    `26e76738-2513-4cfb-9227-3c5d248f3125`, `filled_qty=0E-18`
- `positions` has no active BNB position rows using current deployed schema
  predicate `symbol='BNB/USDT:USDT' and is_closed=0`.
- `execution_intents` has no unfinished BNB intents.
- Latest BNB authorizations are consumed. The latest observed authorization is
  `auth-fc17cf5bbb0c42bbbcc231af5413faa0`, with:
  - `live_authorized=true`
  - `live_ready=false`
  - `order_permission_granted=false`
  - `execution_permission_granted=false`
  - `execution_intent_created=false`
  - `order_created=false`
  - `auto_execution_enabled=false`
  - `consumed=true`
- Optional Tokyo PG tables are absent in this deployment:
  - `execution_recovery_tasks`: absent
  - `order_audit_logs`: absent

Tokyo exchange facts observed read-only through the deployed exchange gateway:

- BNB exchange positions: `[]`
- BNB normal exchange open orders: `[]`
- BNB stop/conditional open orders:
  - exchange order `4000001470395922`
  - symbol `BNB/USDT:USDT`
  - type `market`
  - side `sell`
  - status `open`
  - amount `0.01`
  - stopPrice `625.92`
  - reduceOnly `True`
  - positionSide `LONG`

## Blocking Condition

The task input said the current live state at sprint start should be BNB long
`0.01` with TP open and SL open, and required a stop if TP/SL/manual exit
occurred.

Current evidence contradicts that baseline:

- Exchange no longer shows a BNB position.
- Exchange no longer shows the BNB TP normal open order.
- Exchange still shows the BNB reduce-only SL conditional order.
- PG still shows both TP and SL open, but PG active BNB position is empty.

This is an unresolved post-live final-review / orphan-protection state, not a
normal read-model implementation baseline. The sprint is stopped before
implementation of live-connected read models because continuing would risk
normalizing stale or mismatched protected-state facts into the Trading Console.

## Read-Model Contract Preparation

The following namespace remains the prepared target. All endpoints are read-only
and must return explicit freshness and degradation fields.

### `GET /api/trading-console/dashboard-state`

Required response semantics:

- `environment`: profile, trading env, testnet flag, runtime_bound, live_ready
- `guards`: GKS state, startup guard state, missing-service status
- `account_snapshot_summary`: equity, wallet balance, available margin,
  unrealized PnL, or `not_available`
- `positions`: exchange and PG position summaries
- `orders`: exchange open orders, PG open orders, open intents
- `consistency`: PG/exchange consistency, mismatch counts, blockers
- `authorization`: active/consumed/actionable/blocking summary
- `freshness`: `last_updated_at`, `exchange_snapshot_at`,
  `freshness_status`, `exchange_error`

Current blocker for implementation:

- Live BNB protected-state baseline changed; endpoint would need to classify
  current state as `degraded` / `orphan_protection_order` / `manual_review_required`
  before being safe to expose as the console home source.

### `GET /api/trading-console/account-risk`

Required response semantics:

- Full-account exchange positions where read-only exchange access is available.
- PG positions where schema is available.
- Balances, margin facts, PnL fields where available.
- Protection ownership summary.
- `unknown`, `degraded`, and `not_available` states for missing or stale data.

Current blockers:

- Tokyo deployed `positions` schema differs from local current ORM assumptions
  (`current_qty`/legacy fields rather than local richer model columns).
- Exchange position read currently returns no BNB position while PG open
  protection orders remain.

### `GET /api/trading-console/order-ledger`

Required response semantics:

- PG order rows plus read-only exchange open orders.
- Entry/TP/SL grouping via `parent_order_id` and `oco_group_id`.
- Classification: `pg_only`, `exchange_only`, `matched`, `mismatch`,
  `unknown_unmanaged`, `orphan_protection`.
- Explicit `filled_qty` and `average_exec_price` when stored.

Current blockers:

- Current Tokyo state contains PG `TP1` open but no corresponding exchange
  normal open order.
- Current Tokyo state contains exchange conditional SL and PG SL, but no active
  exchange/PG position.
- `client_order_id` is not stored and must remain `not_available` unless a
  separate schema migration is approved.

### `GET /api/trading-console/protection-health`

Required response semantics:

- `protected`, `partially_protected`, `unprotected`, `unknown`, or `orphaned`.
- Findings from existing protection-health logic where available.
- No retry, cancel, replace, or recovery action.

Current blocker:

- The current live state should classify as orphaned or degraded, but the
  production recovery/action response must not be guessed by a new endpoint
  before post-live final review is handled.

### `GET /api/trading-console/recovery-exception-state`

Required response semantics:

- Recovery tasks if repository/table exists.
- Reconciliation mismatch summary.
- Ghost/orphan/unmanaged order visibility.
- Manual-action-required flags.
- No live recovery action.

Current blockers:

- Tokyo `execution_recovery_tasks` table is absent.
- Recovery task fields must return `not_available` rather than imply no tasks.

### `GET /api/trading-console/authorization-state`

Required response semantics:

- Active/consumed/actionable/blocking state.
- Scope summary: carrier, strategy family, symbol, side, cap, max notional,
  environment/profile if stored.
- Void/cancel action slot documented as future-only.

Current observed state:

- Latest BNB authorization is consumed and non-actionable.
- Permission flags remain false.
- `live_ready=false`.

### `GET /api/trading-console/execution-control-state`

Required response semantics:

- Final hard-gate summary and per-gate status where available.
- Blockers, warnings, unknowns.
- Safe execution preview metadata only if already available.
- No execute wrapper in this sprint.

Current blocker:

- Current live state must block execution due missing fresh authorization and
  unresolved PG/exchange protection mismatch.

### `GET /api/trading-console/review-state`

Required response semantics:

- Current and historical review records.
- Entry/protection/review chain.
- Existing realized PnL, average fill, and filled quantity where stored.
- `fee`, `funding`, and `slippage` as `not_available` unless stored.

Current blockers:

- Review data may exist, but the current post-live state changed after the
  prior protected-position baseline and needs final-review classification before
  a current-state read model can be treated as complete.

### `GET /api/trading-console/audit-chain`

Required query keys:

- `authorization_id`
- `intent_id`
- `order_id`
- `exchange_order_id`

Required response semantics:

- Aggregate authorization -> intent -> order -> TP/SL -> position -> review ->
  audit events.
- Mask or omit unsafe raw payloads.
- Return `not_available` for absent optional audit logs.

Current blockers:

- Tokyo `order_audit_logs` table is absent.
- `execution_recovery_tasks` table is absent.
- Endpoint must not treat absent optional audit/recovery tables as clean state.

## Existing Source Mapping

Safe existing sources identified for future implementation:

- `src/interfaces/api_brc_console.py`: current BRC console composition point.
- `src/interfaces/api.py`: mounted FastAPI composition root and runtime globals.
- `src/infrastructure/pg_order_repository.py`: PG order reads including open
  orders, symbol queries, order chain, OCO group, filled quantity, average exec
  price.
- `src/infrastructure/pg_position_repository.py`: PG active/list position reads,
  subject to deployed schema drift.
- `src/infrastructure/pg_execution_intent_repository.py`: unfinished/list
  intent reads and authorization linkage.
- `src/infrastructure/pg_execution_recovery_repository.py`: recovery reads
  where table exists.
- `src/infrastructure/order_audit_repository.py`: order audit reads where table
  exists.
- `src/application/protection_health_monitor.py`: reason-code vocabulary and
  protection-health grouping semantics; current monitor is an internal consumer,
  not yet a read API.
- `src/infrastructure/exchange_gateway.py`: read-only `fetch_positions` and
  `fetch_open_orders`; mutation methods must not be called by the read models.

## Deferred Action APIs

The following action APIs were intentionally not implemented:

- Execute live trial.
- Cancel order.
- Replace order.
- Flatten position.
- Retry protection order.
- Resolve recovery task.
- Void/cancel live authorization.
- Start runtime.
- Enable auto execution.
- Credential/API-key update.

## Commands Run

Local:

- `git status --short --branch`

Tokyo read-only:

- `git rev-parse --short HEAD`
- `git tag --points-at HEAD`
- `curl -sS http://127.0.0.1:18080/api/health`
- PG read-only selects for Alembic version, BNB open orders, BNB active
  positions, unfinished BNB intents, latest BNB authorizations, optional table
  existence.
- Exchange read-only calls through `ExchangeGateway.initialize`,
  `fetch_positions('BNB/USDT:USDT')`,
  `fetch_open_orders('BNB/USDT:USDT')`, and
  `fetch_open_orders('BNB/USDT:USDT', params={'stop': True})`.

## Safety Proof

- No new live order was placed.
- No order was canceled, replaced, or flattened.
- No recovery action was run.
- No runtime was started.
- No profile, credential, API key, authorization permission, or auto-execution
  setting was changed.
- No PG write, schema migration, commit, or push was performed.
- The only exchange access was read-only position and open-order inspection.

## Continuation Recheck

The same safety blocker was rechecked again during the active goal continuation
on 2026-06-03.

Read-only evidence remained unchanged:

- Tokyo checkout short SHA: `0a94553`
- Tokyo tag at HEAD: `brc-bnb-prelive-20260601-r38`
- Tokyo API health:
  `{"status":"ok","service":"brc_operator_console","runtime_bound":false,"live_ready":false}`
- Tokyo PG Alembic: `041`
- Tokyo PG BNB open orders still include:
  - PG `SL` order `3b43781d-d81b-4288-b1ed-511b41b41f18`,
    exchange order `4000001470395922`, status `OPEN`,
    parent `26e76738-2513-4cfb-9227-3c5d248f3125`,
    `filled_qty=0E-18`
  - PG `TP1` order `b6e8456f-bc31-4945-b05f-399e39c05da9`,
    exchange order `91085295597`, status `OPEN`,
    parent `26e76738-2513-4cfb-9227-3c5d248f3125`,
    `filled_qty=0E-18`
- Tokyo PG active BNB positions: `[]`
- Tokyo PG unfinished BNB execution intents: `[]`
- Latest BNB authorization remains consumed and non-actionable:
  `auth-fc17cf5bbb0c42bbbcc231af5413faa0`,
  `live_ready=false`, `order_permission_granted=false`,
  `execution_permission_granted=false`, `auto_execution_enabled=false`,
  `consumed=true`
- Tokyo exchange BNB positions: `[]`
- Tokyo exchange BNB normal open orders: `[]`
- Tokyo exchange BNB stop open orders still include exchange order
  `4000001470395922`, amount `0.01`, stopPrice `625.92`,
  `reduceOnly=True`, `positionSide=LONG`

Conclusion:

- The blocking condition is stable across repeated read-only checks.
- Completing `/api/trading-console/*` live read models now requires Owner or
  main-controller handling of the post-live final-review / orphan-protection
  state first.
- Continuing implementation without that external-state change would make the
  requested Trading Console foundation less safe, because the current live
  state is not the task's stated protected-position baseline.
