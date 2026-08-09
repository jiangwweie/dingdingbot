# Owner Control Plane Implementation Plan

## Goal

Implement, review, and deploy the approved single-Owner control plane without
creating a second trading chain or disturbing existing Nginx routes.

## Invariants

1. PostgreSQL is the sole control authority.
2. The Control API never loads Binance credentials and never submits exchange
   orders.
3. StrategyGroup pause and global ENTRY pause affect only new ENTRY admission.
4. Existing Tickets continue protection, exit, reconciliation, settlement, and
   review.
5. Flatten-all first pauses global ENTRY, freezes the server-selected active
   Ticket set, and is consumed by the certified Lifecycle Worker.
6. Every exchange mutation remains a durable Kernel Exchange Command.
7. First deployment is stopped, flat, forward-only revision
   `0004_owner_control_plane`.

## Delivery Sequence

### 1. Schema and domain contract

- Add the unbranched `0004_owner_control_plane` migration.
- Add immutable Strategy control, Owner Authorization, and Control Operation
  models.
- Seed explicit enabled StrategyGroup control rows for current groups.
- Add bounded indexes and exact state constraints.

### 2. Application and persistence

- Add StrategyGroup pause/resume and global ENTRY pause/resume transitions.
- Add flatten preview and two-stage submit semantics.
- Add exact, bounded repository operations and optimistic versions.
- Add Entry checks before action facts, before Ticket commit, and immediately
  before ENTRY dispatch.
- Add Lifecycle consumption of pending flatten operations.
- Project completion only after terminal Ticket, flat position, cleared orders,
  released authorities, settlement, review, and no unresolved incident/command.

### 3. HTTP security

- Add control routes under `/api/owner/v1/controls`.
- Require current Session for pause and TOTP step-up for resume/flatten.
- Validate exact Origin, Host, JSON content type, expected version, snapshot
  digest, confirmation text, and idempotency key.
- Keep secret inputs out of persisted payloads and logs.

### 4. Owner Console

- Add the fifth navigation item and `/controls` route.
- Add compact configured/effective state, current operation, bounded event
  history, and isolated danger zone.
- Add control summary to Overview without dangerous buttons.
- Preserve manual refresh only and Binance-style dark System B.
- Build for `/trading/` with Router basename `/trading`.

### 5. Deployment assets

- Use an independent Owner Console release directory and Unix socket.
- Add root-owned systemd credential sources with `LoadCredential=`.
- Add only exact `/trading/` and `/api/owner/v1/` Nginx locations.
- Snapshot the current Nginx configuration, run `nginx -t`, reload only after
  exact-path verification, and verify all pre-existing routes afterward.

### 6. Focused verification

- Run RED/GREEN tests for control models, transitions, Entry checks,
  flatten/Lifecycle idempotency, HTTP authentication, and Controls UI.
- Run proportional Trading Kernel regression, Ruff, Mypy, frontend typecheck,
  build, and focused Playwright browser acceptance.
- Perform a findings-first diff review and fix all P0/P1 findings.

### 7. Production execution

- Refresh current commit, schema, PostgreSQL, systemd, Nginx, and exchange
  readonly facts.
- Establish the required flat deployment window through the current certified
  controlled-exit path if exposure remains.
- Verify external flatness, no residual orders, terminal Tickets, released
  budget/domain, settlement/review, zero open incident, and zero unresolved
  command.
- Deploy revision `0004`, Kernel, internal Owner API, then the static Console.
- Pause `SOR-001` through the new StrategyGroup control API and leave global
  ENTRY paused after flatten-all.

## Acceptance Evidence

- Exact deployed commit and schema revision.
- Four Kernel workers active with no restart growth.
- Owner API active only on its Unix socket and within its resource slice.
- Existing Nginx gateway and exact legacy paths unchanged and healthy.
- `SOR-001` configured paused and effectively unable to create new ENTRY.
- Exchange account flat with no residual orders.
- All formerly active Tickets terminal with budget/domain released,
  reconciliation matched, settlement and review complete.
- Zero open Incident and zero unresolved/outcome-unknown Command.
