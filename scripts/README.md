# Scripts Reset

Historical scripts were archived on 2026-04-29 to reduce research and migration noise.

Archived material:
- `docs/history-archive-2026-06-15-pre-governance.tar.gz`
- Git history before commit `878dcb99`

Only reintroduce scripts here when they serve the new baseline directly.

## Static Risk Classification

Before running or delegating any script in this directory, classify it as a
static source artifact first. The classifier lives at:

- `src/application/script_risk_classifier.py`

The classifier reads script text only. It must not import or execute the target
script. Unknown scripts fail closed as `unknown_review_required`.

Risk levels:

- `read_only`: declared read-only or research-only material.
- `review_required`: exchange-read, credential-sensitive, or live-scope
  preflight material.
- `mutation_restricted`: database, runtime-control, config, or safety-state
  mutation material.
- `exchange_write_restricted`: exchange-write or controlled testnet execution
  material.
- `live_action_restricted`: live-scope exchange-write material.
- `unknown_review_required`: no recognized safety or risk contract.

Script comments such as "dry-run", "read-only", or "Owner-approved" are useful
classification evidence, but they do not authorize execution. Real live trading
or real-funds order placement still requires a separate explicit Owner
authorization for the exact action.

## Runtime Safety Seeding

- `seed_gks_state.py`: creates or updates the single PG Global Kill Switch row.
  It defaults to `active=True`, so seeding does not accidentally allow new
  entries. Use `--inactive` only for non-live/testnet smoke after explicit Owner
  approval and with the startup trading guard/manual arm process still in place.

## Tokyo Runtime Governance Release Preparation

- `prepare_tokyo_runtime_governance_release.py`: local read-only / dry-run
  release readiness manifest for the Tokyo runtime-governance deployment stage.
  It inspects local git, migration, deployed-head ancestry, untracked files, and
  tracked secret-candidate path names. It does not SSH, deploy, run migrations,
  restart services, read secrets, create execution records, create orders, call
  OrderLifecycle, or call exchange APIs. Use `--write-artifacts` only when a
  local `git archive` and manifest are needed for a controlled deployment
  package.

- `probe_tokyo_runtime_governance_readonly.py`: remote read-only fact probe for
  the Tokyo runtime-governance deployment stage. It uses SSH to inspect the
  current release symlink, current release git head/status, migration-file
  count/latest file, `/api/health`, and a bounded process snapshot. It does not
  source env files, read secrets, write remote files, deploy, run migrations,
  restart services, create execution records, create orders, call
  OrderLifecycle, or call exchange APIs. Because it references live-scope
  readiness facts such as `live_ready`, classify and review it before running.

- `audit_tokyo_runtime_governance_migration_gap.py`: local static migration-gap
  audit for the Tokyo runtime-governance deployment stage. It parses local
  Alembic migration files between deployed revision `044` and local revision
  `064`, summarizes upgrade operations, and highlights review items such as
  data-touching updates, non-additive schema operations, and not-null columns
  added to existing tables. It does not connect to a database, SSH, deploy, run
  migrations, restart services, read secrets, create execution records, create
  orders, call OrderLifecycle, or call exchange APIs.

- `verify_tokyo_runtime_governance_postdeploy.py`: remote read-only
  post-deploy verifier. It checks release identity, migration-file state,
  health invariants, key runtime-governance read endpoints, and that a generic
  Trading Console POST remains blocked. Trading Console checks force
  `include_exchange=false`. It does not write remote files, source env files,
  read secrets, connect directly to PG, run migrations, restart services, create
  execution records, create orders, call OrderLifecycle, or call exchange APIs.

- `execute_tokyo_runtime_governance_git_deploy.py`: apply-gated deployment
  executor for the git-based deploy plan. Its default behavior is dry-run only
  and executes no commands. When applied, Tokyo fetches the pushed git commit,
  exports it into a release directory, runs migrations, switches `app/current`,
  and restarts services. It does not create release archive uploads, deploy
  backup dumps, report JSON files, execution records, orders, OrderLifecycle
  calls, or exchange API calls.
