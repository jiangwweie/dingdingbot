# Tokyo Runtime Governance Controlled Deployment Runbook - 2026-06-10

Status: PRE_DEPLOYMENT_RUNBOOK

This runbook converts the read-only Tokyo facts into a controlled deployment
sequence for the local runtime-governance branch. It is not deployment
authorization, not live-submit authorization, and not an instruction to place
orders.

## Scope

Target branch:

- `codex/sprint6-console-runtime-integration`

Current local deployment candidate at the time this runbook was written:

- `83f563f6 docs(ops): record tokyo deployment readiness facts`

Current Tokyo baseline from the read-only fact check:

- deployed app symlink: `/home/ubuntu/brc-deploy/app/current`
- deployed release: `brc-jit-lifecycle-audit-415d3985-20260608`
- deployed HEAD: `415d398509872cb25bf969319e29732764f9615b`
- latest deployed migration file: `044_create_live_lifecycle_reviews`
- local latest migration file: `064_add_runtime_profile_proposal_snapshot`
- backend health: `status=ok`, `runtime_bound=true`, `live_ready=false`

## Non-Negotiable Invariants

- Do not place real orders during deployment.
- Do not call `OrderLifecycle` as part of deployment.
- Do not enable a real submit adapter as part of deployment.
- Do not change exchange credentials as part of deployment.
- Do not change live runtime profiles or real-funds sizing defaults as part of
  deployment.
- Keep `RUNTIME_CONTROL_API_ENABLED=false` unless a separate Owner-approved
  runtime-control task explicitly changes it.
- Keep `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false` for the prelive live-read
  deployment.
- Keep Trading Console / BRC Console wording honest: deployed runtime
  governance is not automatic order authority.

## Local Preflight

Run from the local worktree:

```bash
/opt/homebrew/bin/python3 scripts/prepare_tokyo_runtime_governance_release.py --json
```

The output must show:

- `ready_for_packaging=true`;
- deployed head is an ancestor of local `HEAD`;
- migration count is at least `64`;
- latest migration is
  `2026-06-10-064_add_runtime_profile_proposal_snapshot.py`;
- no tracked secret-candidate files;
- no tracked worktree changes.

Untracked local artifacts such as `.playwright-cli/` are allowed only because
the release artifact is produced from `git archive HEAD`, not from the raw
working directory. They must not be described as integrated capability.

If a local release artifact is needed:

```bash
/opt/homebrew/bin/python3 scripts/prepare_tokyo_runtime_governance_release.py \
  --json \
  --write-artifacts
```

This creates a local archive and manifest under
`output/tokyo-runtime-governance-release/`. It still does not deploy.

## Remote Preflight

Read-only checks before any remote mutation:

```bash
ssh tokyo 'cd ~/brc-deploy/app/current && git rev-parse HEAD && git status --short --branch'
ssh tokyo 'curl -fsS http://127.0.0.1:18080/api/health'
ssh tokyo 'ps -eo pid,ppid,user,comm,args | egrep "(python -m src.main|postgres|docker)" | grep -v egrep'
```

Expected:

- backend health remains OK;
- current deployed HEAD still matches the baseline or any newer known
  controlled deployment;
- no unknown remote drift is present in `app/current`;
- runtime remains `live_ready=false` before deployment.

## Database Safety

Before applying migrations:

1. Create a database backup using the existing remote backup path, or an
   equivalent PG-native backup command.
2. Record the backup filename in a deployment evidence note.
3. Inspect the migration path from deployed `044` to local `064`.
4. Run migration planning in a staging/dry-run context when available.
5. Apply migrations only after the release artifact and rollback target are
   known.

The migration jump includes runtime governance tables and audit records. Treat
it as a controlled deployment stage, not as a casual restart.

## Release Procedure Shape

The deployment should use a clean release directory:

```text
/home/ubuntu/brc-deploy/releases/<release-name>
```

Then update:

```text
/home/ubuntu/brc-deploy/app/current -> <release-name>
```

The release should preserve the existing environment posture:

```text
APP_ENV=prelive
TRADING_ENV=live
EXCHANGE_TESTNET=false
RUNTIME_CONTROL_API_ENABLED=false
RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false
BRC_LLM_ENABLED=false
```

Restart should be a deliberate backend restart with immediate health checks.
Do not rely on a dirty release tree or an unknown long-running process.

## Post-Deployment Smoke

Minimum backend checks:

```bash
curl -fsS http://127.0.0.1:18080/api/health
curl -fsS http://127.0.0.1:18080/api/trading-console/strategy-runtimes?limit=1
curl -fsS http://127.0.0.1:18080/api/trading-console/strategy-runtime-profile-proposals?strategy_family_id=CPM-RO-001\&strategy_family_version_id=CPM-RO-001-v0\&symbol=BNB/USDT:USDT\&side=long
```

Minimum console checks:

- Owner login still works.
- `/runtime` renders.
- `/strategy` renders reference observation candidates.
- dark / light theme toggle still updates `data-theme`.
- non-executing shadow-plan POST remains explicit and narrow.
- generic Trading Console POSTs remain blocked unless explicitly allowlisted.

Minimum safety checks:

- health still reports `live_ready=false`;
- promotion gates still block missing first-real-submit confirmations;
- runtime control remains disabled;
- no order was created during deployment;
- no exchange write was called during deployment.

## Rollback Shape

Rollback must be release-symlink based when possible:

1. Stop the newly started backend process.
2. Restore `app/current` to the previous release directory.
3. Restart backend.
4. Verify `/api/health`.
5. Record whether migrations require forward-fix handling. Do not blindly
   downgrade database schema unless a migration-specific rollback plan exists.

## Evidence To Record

Record these in a deployment evidence note after the deployment:

- local commit deployed;
- remote release path;
- previous release path;
- migration head before and after;
- backup file path;
- backend PID before and after;
- health response after restart;
- Trading Console smoke result;
- safety invariants:
  - `live_ready=false`;
  - runtime control disabled;
  - no order created;
  - no exchange write called.

