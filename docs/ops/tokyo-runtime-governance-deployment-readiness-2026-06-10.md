# Tokyo Runtime Governance Deployment Readiness - 2026-06-10

Status: READ_ONLY_FACT_CHECK

This note records the read-only Tokyo deployment facts collected after the
Sprint 6 / strategy-runtime local integration work. It is evidence for
deployment sequencing only; it is not a deploy, migration, live-submit
authorization, or exchange action.

## Local Baseline Checked

- Local worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Local branch: `codex/sprint6-console-runtime-integration`
- Local HEAD: `1e0b78393b8798c6a303b9dcb8b4f1828c90bb7a`
- Local untracked files: `.playwright-cli/` only
- Local migration files: 64
- Latest local migrations include:
  - `2026-06-09-057_create_runtime_execution_protection_plans.py`
  - `2026-06-09-058_create_runtime_order_lifecycle_handoff_drafts.py`
  - `2026-06-09-059_create_owner_capital_adjustments.py`
  - `2026-06-09-060_add_position_runtime_audit_ids.py`
  - `2026-06-10-061_create_owner_capital_baseline_snapshots.py`
  - `2026-06-10-062_align_positions_orm_runtime_readmodel.py`
  - `2026-06-10-063_create_strategy_runtime_promotion_confirmations.py`
  - `2026-06-10-064_add_runtime_profile_proposal_snapshot.py`

## Tokyo Facts Checked

- Host: `VM-0-11-ubuntu`
- User: `ubuntu`
- Deployment root: `/home/ubuntu/brc-deploy`
- Current app symlink:
  - `/home/ubuntu/brc-deploy/app/current`
  - points to `/home/ubuntu/brc-deploy/releases/brc-jit-lifecycle-audit-415d3985-20260608`
- Current deployed HEAD: `415d398509872cb25bf969319e29732764f9615b`
- Current deployed commit subject: `feat(brc): add just-in-time lifecycle audit`
- Current release is detached HEAD with no branch name.
- Local current branch contains deployed commit `415d3985` as an ancestor.
- Local current branch is 92 commits ahead of the deployed commit.
- Tokyo release migration files: 44
- Latest Tokyo release migrations include:
  - `2026-06-03-037_create_protection_price_plans.py`
  - `2026-06-03-038_add_order_reduce_only_audit.py`
  - `2026-06-03-039_add_order_oco_group_audit.py`
  - `2026-06-03-040_align_orders_pg_numeric_types.py`
  - `2026-06-03-041_add_order_exchange_reduce_only_audit.py`
  - `2026-06-04-042_align_pg_signals_runtime_schema.py`
  - `2026-06-08-043_add_budget_revoke_audit.py`
  - `2026-06-08-044_create_live_lifecycle_reviews.py`

## Runtime Facts Checked

- Running backend process:
  - `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python -m src.main`
- Backend health endpoint:
  - `GET http://127.0.0.1:18080/api/health`
  - returned `200`
  - body included `status=ok`, `service=brc_operator_console`,
    `runtime_bound=true`, `live_ready=false`
- Docker daemon exists, but the `ubuntu` user cannot inspect Docker containers
  without elevated permission.
- A Docker Postgres process is running and the backend had an idle connection
  to `brc_prelive_dryrun` during the read-only check.
- User-level systemd does not manage the backend service.

## Environment Posture Checked

Sensitive values were not copied into this report.

`live-readonly.env` declares:

- `APP_ENV=prelive`
- `TRADING_ENV=live`
- `EXCHANGE_TESTNET=false`
- `CORE_EXECUTION_INTENT_BACKEND=postgres`
- `CORE_ORDER_BACKEND=postgres`
- `CORE_POSITION_BACKEND=postgres`
- `BRC_EXECUTION_PERMISSION_MAX=order_allowed`
- `RUNTIME_CONTROL_API_ENABLED=false`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`
- `BRC_LLM_ENABLED=false`
- `BACKEND_PORT=18080`
- `API_HOST=127.0.0.1`

Interpretation:

- Tokyo has a live/prelive exchange-read environment with real credential
  material configured.
- Runtime control and test-signal injection are disabled.
- Health is good, but the current deployed code is far behind the local
  runtime-governance integration branch.

## Deployment Tooling Facts

Remote scripts present under `/home/ubuntu/brc-deploy/scripts`:

- `backup_pg.sh`
- `health_check.sh`
- `reset_owner_console_auth.sh`
- `set_live_readonly_secrets.sh`

No read-only evidence of a clean release/deploy script was found in
`/home/ubuntu/brc-deploy/scripts`.

The current deployment appears to use:

- release directories under `/home/ubuntu/brc-deploy/releases`;
- `app/current` symlink switching;
- a shared virtualenv under `/home/ubuntu/brc-deploy/venvs`;
- a long-running Python backend process.

## Readiness Conclusion

Tokyo is not deployment-current for the local Sprint 6 / Sprint 7 / strategy
runtime governance work.

The next Tokyo deployment should be treated as a separate controlled deployment
stage because it must cover:

- clean release artifact creation from the current local branch or pushed commit;
- dependency install / virtualenv compatibility;
- Alembic migration planning from Tokyo release `044` to local head `064`;
- database backup before migration;
- backend restart method;
- post-restart health smoke;
- Trading Console smoke;
- confirmation that runtime control and real submit adapters remain disabled
  unless separately authorized.

This check did not:

- push code;
- create a remote release;
- run migrations;
- restart services;
- modify remote files;
- create ExecutionIntent records;
- create orders;
- call OrderLifecycle;
- call exchange write APIs.

