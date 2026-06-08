# BRC Owner Console Current State

Last validated: 2026-05-27

> [!IMPORTANT]
> 2026-06-08 scope note:
> This is a 2026-05-27 implementation-state snapshot. Its `live_execution`
> forbidden/unavailable wording is superseded as a current product boundary by
> `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`. Current live
> actions still require exact authorization, FinalGate, Operation Layer,
> protection, and Review; this note remains historical implementation context.

This document records the current BRC Owner Console operating surface after the
Operation Layer, account facts read model, fixed testnet rehearsal
operationization, emergency runtime stop, and emergency flatten dry-run slices.

## Authorization Model

The Operation Layer is the authorization source for Owner Console operations.

Readiness is not authorization. `/api/brc/readiness` can summarize state,
action cards, risk posture, and next steps, but it does not grant execution
authority.

The frontend is not authorization. It displays backend capability and preflight
decisions and submits Owner confirmation where required.

LLM and workflow carriers are not authorization. They may explain, summarize, or
carry an internal fixed rehearsal run, but they cannot directly execute Owner
operations or bypass Operation confirmation.

## Current Capability Matrix

| operation_type | Status | Execution behavior |
| --- | --- | --- |
| `switch_playbook` | executable | Operation preflight plus one-time Owner confirmation. Does not place orders, reset attempts, reset PnL, or reset loss lock. |
| `start_review` | executable/noop | Operation-backed review packet read/start boundary. If no mutation is available, result is a noop. |
| `write_review_decision` | executable | Operation-backed review decision write, with review and audit refs. |
| `run_fixed_testnet_rehearsal` | executable when adapter is wired | Operation-authorized fixed ETH/BTC testnet rehearsal. Workflow id, if present, is an internal carrier ref only. |
| `enter_observe` | executable when runtime adapter is wired | Runtime transition to observe. Does not place orders, close positions, or cancel orders. |
| `enter_pause` | executable when runtime adapter is wired | Runtime transition to paused. Stops new strategy actions only through the adapter. Does not flatten or cancel orders. |
| `enter_strategy_or_monitor` | noop monitor carrier | Degrades to monitor carrier. Does not enable unrestricted auto trading or direct order execution. |
| `pause_new_entries` | unavailable | No Operation-backed cutoff adapter is enabled. |
| `emergency_flatten` | dry-run-only | Operation-backed flatten dry-run plan generation and dry-run record confirmation. Actual cancel, close, order, flatten, live, withdrawal, and transfer execution remain unavailable. |
| `emergency_stop_runtime` | executable when stop adapter is wired | Operation-backed runtime stop only. It does not flatten positions, cancel orders, close positions, place orders, or clean account exposure. If the stop adapter is missing, it remains planning-only/unavailable. |
| `live_execution` | forbidden | No live/mainnet execution path is exposed. |
| `unrestricted_order_execution` | forbidden | No arbitrary trading path is exposed. |
| `arbitrary_symbol_order` | forbidden | No arbitrary symbol path is exposed. |
| `arbitrary_side_size_order` | forbidden | No arbitrary side/size path is exposed. |
| `arbitrary_strategy_router` | forbidden | No generic strategy router path is exposed. |
| `withdrawal` | forbidden | No withdrawal path is exposed. |
| `transfer` | forbidden | No transfer path is exposed. |
| `llm_direct_execution` | forbidden | LLM cannot execute or authorize operations. |

## TF-001 Carrier Validation

`TF-001` is currently modeled as a BRC `carrier_validation_only` playbook. It is
available for Operation-backed `switch_playbook` selection so the Owner Console
can validate the third-stage flow:

`select playbook -> confirm -> monitor -> pause -> stop -> review`

This is governance-chain validation only. It is not alpha proof, profitability
evidence, strategy-pool construction, controlled-testnet execution authority,
live readiness, withdrawal/transfer authority, or arbitrary trading authority.

Repeatable local smoke:

```bash
python3 scripts/brc_owner_console_smoke.py \
  --mode tf001-carrier-full-chain \
  --output /tmp/brc-tf001-carrier-full-chain.json
```

Expected smoke result: `completed=true`, campaign playbook `TF-001`, monitor
carrier `noop`, runtime stop executed without flatten/cancel/close/order
behavior, and review decision recorded with audit/review refs.

## Account Facts Semantics

`GET /api/brc/account/facts` is a read-only BRC-scoped account facts API. It is
not a generic exchange terminal.

`source` values:

- `local_pg`: local BRC position/order repositories only.
- `exchange_testnet`: bounded read-only testnet exchange data only.
- `mixed`: local PG plus exchange testnet read are both available.
- `exchange_live`: modeled but forbidden in the current Owner Console.
- `unavailable`: no safe account fact source is available.

`truth_level` values:

- `summary`: local summary only, not complete exchange account truth.
- `exchange_read`: exchange testnet read only.
- `reconciled`: local PG and exchange testnet sources were compared.
- `unavailable`: account facts are unavailable and state-changing operations
  must fail closed.

`reconciliation_status.status` values:

- `clean`: checked sources had no detected mismatch.
- `mismatch`: local and exchange facts disagree, or unmanaged exchange exposure
  was detected.
- `unknown`: sources are insufficient for a clean reconciliation verdict.
- `not_available`: reconciliation cannot run because a required source is
  missing.

Unknown or unmanaged exchange orders/positions block medium and high risk
operations.

Current account facts also expose read-only evidence metadata:

- `evidence_refs`: stable refs for the generated account facts and
  reconciliation snapshot;
- `checked_sources`: sources included in the reconciliation verdict;
- `source_snapshots`: per-source availability and count summary;
- `reconciliation_checked_at_ms`: timestamp for the reconciliation evidence;
- `mismatch_count`: number of reconciliation mismatches;
- `unknown_unmanaged_counts`: counts of unknown/unmanaged orders and positions.

These fields are evidence and audit aids only. They do not expose write
capability, generic exchange terminal behavior, or complete exchange account
truth.

## Migration Notes

The project migration runner is Alembic (`alembic.ini`, `migrations/`). The BRC
Operation Layer ledger migration is revision `017`, after `016`.

The current local SQLite development database may contain historical tables
without an `alembic_version` row. In that case, running `alembic upgrade head`
from revision base can fail on pre-existing tables such as `orders`. For that
kind of legacy development database, first establish the correct baseline stamp
for already-present schema, then apply `017`.

Validated migration path:

```text
stamp existing development schema to 016
upgrade 016 -> 017
verify brc_operations, brc_preflight_snapshots, brc_execution_results
```

Safe helper for the current legacy SQLite dev DB:

```bash
python3 scripts/brc_dev_migration_smoke.py \
  --source-db data/v3_dev.db \
  --work-db /tmp/brc_operation_migration_dev_copy.db
```

This command copies `data/v3_dev.db`, stamps the copy to `016` only when the
copy has no `alembic_version`, upgrades the copy to `head`, and verifies the
Operation Layer tables. It is intentionally non-destructive and refuses to use
the source DB as the work DB.

For a new empty development DB, do not use a legacy stamp. Run the normal
Alembic chain from base:

```bash
python3 scripts/brc_dev_migration_smoke.py \
  --fresh \
  --work-db /tmp/brc_operation_migration_fresh.db
```

or, for an actual managed database after choosing the target intentionally:

```bash
PYTHONPATH=. alembic upgrade head
```

Only apply `stamp 016 -> upgrade head` to a known legacy development database
whose schema already matches the pre-Operation Layer state. Take a backup first.
Do not run direct `alembic upgrade head` against an unversioned historical
SQLite DB that already contains tables such as `orders`; it can collide with
historical table creation.

Rollback note: downgrading `017` drops the three Operation Layer ledger tables
and their indexes. Do not downgrade a database that contains operation audit
evidence unless that evidence has been explicitly archived.

If the Operation repository cannot initialize because the DB is unavailable or
the `017` tables are missing, state-changing Owner Console operations must
fail closed. The standalone API should not silently fall back to an in-memory
authorization ledger.

## Dev Smoke Paths

Standalone API smoke:

```bash
python3 -m uvicorn src.interfaces.api:app --host 127.0.0.1 --port 8765
python3 scripts/brc_owner_console_smoke.py \
  --mode http \
  --base-url http://127.0.0.1:8765
```

This covers:

- `GET /api/brc/readiness`
- `GET /api/brc/operations/capabilities`
- `GET /api/brc/account/facts`
- `POST /api/brc/operations/preflight` for `switch_playbook`
- `POST /api/brc/operations/{operation_id}/cancel`
- wrong confirmation phrase against the same operation
- `GET /api/brc/operations/{operation_id}`
- `GET /api/brc/operations`

The helper signs a short-lived local operator session from `.env` /
`.env.local`; it does not print the cookie or secrets.

Runtime-bound switch-playbook smoke:

```bash
python3 scripts/brc_owner_console_smoke.py --mode runtime-bound-test
```

This uses the bounded in-memory Operation service test context with BRC campaign,
account facts, audit, and operation repository services bound. It proves that
`switch_playbook` can preflight and confirm successfully when required services
exist, without starting live/mainnet, generic trading, emergency flatten actual execution/stop,
or fixed testnet rehearsal execution.

Frontend smoke/build path:

```bash
cd gemimi-web-front
VITE_API_PROXY_TARGET=http://127.0.0.1:8765 npm run dev -- --host 127.0.0.1 --port 8766
npm run lint
npm run build
```

Use the dev server for browser smoke of Command Center, Markets & Orders, Fixed
Testnet Rehearsal, Review / Evidence, and unsupported action surfaces.

## Composition Notes

`src.interfaces.api:app` is a standalone local API composition. It can expose
the BRC Owner Console routers, auth, and read surfaces, but it may not have the
runtime-bound BRC campaign service, position/order repositories, exchange
read-model adapters, fixed rehearsal dependencies, or operation repository
available in the same way as a fully bound runtime context.

Expected standalone behavior:

- readiness loads in degraded local-console mode;
- account facts can return `source=unavailable` and
  `truth_level=unavailable`;
- state-changing operation preflights block when account facts, campaign, audit,
  or operation repository dependencies are missing;
- no missing-service condition should become an implicit allow.

Expected runtime-bound behavior:

- BRC campaign service, account facts source, audit writer, and Operation
  repository are bound explicitly;
- `switch_playbook` can pass preflight and execute in the bounded context when
  safety gates pass;
- Operation result refs are returned from the ledger and can feed Recent
  Operation Results.

Runtime-bound evidence smoke:

```bash
python3 scripts/brc_owner_console_smoke.py \
  --mode runtime-bound-evidence \
  --output /tmp/brc-owner-console-evidence.json
```

This emits a local JSON evidence packet covering:

- operation capabilities;
- account facts source/truth/reconciliation evidence summary;
- `switch_playbook` preflight and confirm with operation/preflight/idempotency
  binding;
- operation get/list refs;
- emergency stop runtime preflight/result envelope without flatten/cancel/close
  semantics;
- emergency flatten dry-run record only.

The output path should be outside the repo or otherwise ignored. Do not commit
local evidence packets unless a task explicitly requests a sanitized artifact.

Do not use the smoke helpers to run actual fixed testnet rehearsal or
Operation-backed runtime stop by default. The runtime-bound evidence mode may
persist an emergency flatten dry-run record, but it must not execute actual
flatten. Do not run live/mainnet, actual flatten, order cancel, close position,
withdrawal, transfer, arbitrary trading, or LLM direct execution from these
paths.

## Current API Surface

Current BRC Owner Console APIs include:

- `GET /api/brc/readiness`
- `GET /api/brc/account/facts`
- `GET /api/brc/operations/capabilities`
- `POST /api/brc/operations/preflight`
- `POST /api/brc/operations/{operation_id}/confirm`
- `POST /api/brc/operations/{operation_id}/cancel`
- `GET /api/brc/operations/{operation_id}`
- `GET /api/brc/operations`
- existing BRC campaign, audit, review, evidence, and fixed rehearsal read paths

The API surface does not include arbitrary order placement, order cancel, close
position, actual flatten, generic runtime stop, live/mainnet execution,
withdrawal, transfer, or LLM direct execution endpoints. Runtime stop is only
available through `emergency_stop_runtime` Operation preflight and Owner
confirmation when the backend stop adapter is explicitly wired. Flatten is only
available as `emergency_flatten` dry-run plan persistence; candidate rows are
not executable order requests.

## Frontend Pages

- Command Center: displays readiness, operation capabilities, account facts,
  Operation Preflight, dry-run flatten, and planning-only/unavailable emergency
  controls.
- Markets & Orders: displays BRC-scoped account facts with source,
  truth_level, reconciliation status, limitations, and unmanaged exposure.
- Fixed Testnet Rehearsal: uses Operation Preflight as the Owner authorization
  path. Internal workflow ids are technical refs only.
- Review / Evidence: displays review and evidence refs where available.
- Unsupported or forbidden actions remain unavailable, forbidden, or design
  surface and must not be presented as executable.

## Safety Boundary

The current Owner Console is not a live system. It does not authorize real live,
mainnet, withdrawal, transfer, arbitrary trading, arbitrary symbols, arbitrary
side/size, generic exchange terminal behavior, or LLM direct execution.

## Next Roadmap

Current commit-ready scope ends at local/testnet Owner Console governance,
Operation authorization, read-only account facts, runtime stop, and flatten
dry-run records.

Next work should stay explicit and separately authorized:

- complete `BRC-R5-001A` runtime-bound smoke evidence hardening before treating
  the console as a long-running runtime console;
- use `BRC-R5-001B` to plan TF-001 as a carrier validation only, not alpha proof
  or live readiness;
- complete `BRC-R5-001C` account facts reconciliation evidence hardening without
  exposing a generic exchange terminal;
- keep any future actual flatten, order cancel, close position, or live/mainnet
  capability behind a separate design, safety review, migration, and Owner
  authorization task.
