# Entry Promotion Operability Design

## Objective

Make the deployed Policy v4 runtime permanently capable of official Entry
promotion after its short-lived Certification Batch expires, without replacing
active StrategyUniverses or disabling Lifecycle/Reconciliation exchange-command
authority.

## Verified Problem

The deployed runtime is flat, exact, fenced and internally healthy, but
`promote_entry.py` is blocked because:

1. the completed release Certification Batch expired while all seven current
   instrument certifications remained fresh and eligible; and
2. `certify_readonly.py` requires `exchange_commands=false` for pre-promotion,
   although compatible upgrade intentionally preserves that capability for
   safety workers.

## Design

### Promotion authority

Pre-promotion authority is defined by all of the following:

- exact runtime commit, schema, Registry, Seed and Policy semantics;
- Policy `new_entry_submit_enabled=false`;
- Entry service inactive/disabled and the write fence present;
- exact Active StrategyUniverse manifest and a current completed Certification
  Batch;
- flat internal and exchange state, zero Incident and zero unresolved Command;
- `exchange_commands` is a current boolean capability. It may already be true
  because it covers safety commands, not only ENTRY.

`arm-acceptance` remains the only operation that changes Policy to permit new
ENTRY. The Entry service still starts while fenced, postflight repeats, and the
fence is removed last.

### Active-manifest Certification Batch refresh

Add one server-local operation that:

1. locks no lifecycle row and performs no exchange mutation;
2. validates the exact six Active Universe current pointers, expected Event
   identities and the seven-member manifest;
3. validates exact runtime, Policy and Seed identity;
4. creates or reuses one release-scoped Certification Batch for the current
   Active manifest;
5. leaves every Universe version and runtime scope unchanged;
6. lets the existing Reconciliation worker certify the seven Batch members;
7. waits boundedly for `completed` or returns a precise blocker/timeout.

The operation belongs in `bootstrap_strategy_universes.py` as an explicit
`--refresh-active-certification-batch-only` mode so certification-batch
construction remains single-sourced.

## Failure Handling

- Wrong identity, non-exact Active manifest, Warming Universe, blocker, timeout,
  Incident, unresolved Command or exchange contradiction leaves Entry fenced.
- Promotion failure restores the write fence and disables/stops Entry.
- No manual SQL, direct Binance mutation, Policy edit or Universe replacement is
  permitted.

## Verification

- RED/GREEN tests cover capability already true before promotion.
- PostgreSQL tests prove Batch refresh creates no Universe or scope row.
- Tests prove expired Batch is replaced by a current exact Batch and retry is
  idempotent.
- Full release certification precedes deployment.
- Tokyo postflight proves Entry active/enabled, fence absent, Policy armed,
  identity exact, safety workers stable and internal/external state flat.

## Alternatives Rejected

- Disabling `exchange_commands` before promotion would remove shared safety
  authority and mis-model the capability.
- Re-running six-Universe bootstrap would create needless historical versions
  only to renew a time-bound Batch.
- Directly calling `arm-acceptance` would bypass the official promotion gate.

