# Tokyo Runtime Governance Controlled Deployment Runbook - 2026-06-10

Status: PRE_DEPLOYMENT_RUNBOOK

This runbook converts the read-only Tokyo facts into a controlled deployment
sequence for the local runtime-governance branch. It is not deployment
authorization, not live-submit authorization, and not an instruction to place
orders.

## Scope

Target branch:

- `release/tokyo-runtime-governance-20260610`

Current local deployment candidate must be taken from
`scripts/prepare_tokyo_runtime_governance_release.py --json` immediately before
packaging or deployment. This runbook intentionally does not pin a local
candidate commit, because every runbook edit creates a newer HEAD. The
generated manifest and deploy plan are the deployment candidate facts.

Current Tokyo baseline from the read-only fact check:

- deployed app symlink: `/home/ubuntu/brc-deploy/app/current`
- deployed release:
  `brc-runtime-governance-ae9b209e-20260610T061250Z`
- deployed HEAD: `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- latest deployed migration file:
  `064_add_runtime_profile_proposal_snapshot`
- local latest migration file:
  `069_allow_adapter_registration_failure_results`
- backend health: `status=ok`, `runtime_bound=true`, `live_ready=false`

Local release-prep for the next code-bearing candidate should report:

- `ready_for_packaging=true`
- deployed head is an ancestor of local `HEAD`
- local migration count `69`
- latest local migration
  `2026-06-10-069_allow_adapter_registration_failure_results.py`
- no tracked secret-candidate files
- only warning:
  `untracked_files_exist_and_are_not_in_git_archive` for `.playwright-cli/`

Last local migration-gap audit for `064 -> 069` reported:

- `ready_for_controlled_migration_preflight=true`
- chain length `5`, first revision `065`, last revision `069`
- no `data_destructive_upgrade_ops`
- warnings:
  - `non_additive_schema_ops_present`
- review items:
  - revision `065` relaxes `strategy_runtime_instances` check constraints so an
    explicitly authorized runtime can leave shadow-only flags;
  - revision `066` adds `order_lifecycle_adapter_enabled=false` and permits the
    controlled-submit audit status `order_lifecycle_adapter_disabled`;
  - revision `067` allows local `Order(status=CREATED)` registration through
    the historical orders status check;
  - revision `068` adds the runtime OrderLifecycle adapter-result table whose
    unique `authorization_id` is the persistent duplicate-submit lock;
  - revision `069` lets adapter-result rows record fail-closed local
    registration failures for partial entry/protection registration review.

Last Tokyo read-only probe for the same stage reported:

- `ready_for_controlled_deploy_preflight=true`
- no blockers
- warning: `remote_release_identity_from_manifest_without_git_status`
- current deployed HEAD `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- current deployed migration count `64`
- backend health `status=ok`, `runtime_bound=true`, `live_ready=false`

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
- migration count is at least `69`;
- latest migration is
  `2026-06-10-069_allow_adapter_registration_failure_results.py`;
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

The release archive is produced with `git archive`, so the extracted release
tree does not contain `.git`. During remote deployment, copy the generated
`release-readiness-manifest.json` into the release root as:

```text
.brc-release-manifest.json
```

Post-deployment probes must use git identity when `.git` is present and release
manifest identity when the release was built from an archive.

For follow-up deployments, prefer the git-based path. The local target commit
must first be pushed to the selected remote branch, and that commit must be the
remote branch HEAD. This avoids uploading a full local archive on every stage
while preserving the same backup, migration, restart, and postdeploy gates.

Generate the owner-gated git command plan:

```bash
/opt/homebrew/bin/python3 scripts/plan_tokyo_runtime_governance_git_deploy.py \
  --json \
  --repo-url <git-repository-url> \
  --git-ref <remote-branch-name> \
  --target-commit <commit-to-deploy> \
  --release-name <remote-release-name> \
  --previous-release <current-remote-release-path> \
  --expected-deployed-head <current-remote-head> \
  --expected-remote-migration-count <current-remote-migration-count> \
  --expected-remote-latest-migration <current-remote-latest-migration>
```

The plan is not authorization and must not be treated as execution. It should
show `ready_for_owner_authorized_remote_deploy=true`, contain no `scp`
command, and print the explicit remote mutation confirmation phrase before any
remote git fetch/export, backup, migration, symlink switch, or restart.

Then build the consolidated git Owner decision packet:

```bash
/opt/homebrew/bin/python3 scripts/build_tokyo_runtime_governance_git_owner_deploy_packet.py \
  --json \
  --repo-url <git-repository-url> \
  --git-ref <remote-branch-name> \
  --target-commit <commit-to-deploy> \
  --release-name <remote-release-name> \
  --previous-release <current-remote-release-path> \
  --expected-deployed-head <current-remote-head> \
  --expected-remote-migration-count <current-remote-migration-count> \
  --expected-remote-latest-migration <current-remote-latest-migration> \
  > <owner-git-deploy-decision-packet.json>
```

This packet aggregates release readiness, git deploy plan, executor dry-run,
Tokyo read-only probe, and the pre-live runtime submit packet. It must report
`ready_for_owner_git_deploy_decision=true` before applying the deployment. That
status does not authorize live runtime enablement, real submit, OrderLifecycle
adapter enablement, or exchange order placement.

Once Owner explicitly approves the remote mutation stage, execute the same
git-based plan:

```bash
/opt/homebrew/bin/python3 scripts/execute_tokyo_runtime_governance_git_deploy.py \
  --json \
  --repo-url <git-repository-url> \
  --git-ref <remote-branch-name> \
  --target-commit <commit-to-deploy> \
  --release-name <remote-release-name> \
  --previous-release <current-remote-release-path> \
  --expected-deployed-head <current-remote-head> \
  --expected-remote-migration-count <current-remote-migration-count> \
  --expected-remote-latest-migration <current-remote-latest-migration> \
  --owner-deploy-packet-path <owner-git-deploy-decision-packet.json> \
  --apply \
  --confirmation-phrase OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Without `--apply`, the exact confirmation phrase, and a ready git owner deploy
decision packet for the same repo / ref / HEAD, this executor remains blocked
or dry-run and must not mutate Tokyo.

The archive path remains available as a fallback when Tokyo cannot fetch the
repository. For fallback archive deployment, generate the owner-gated command
plan:

```bash
/opt/homebrew/bin/python3 scripts/plan_tokyo_runtime_governance_deploy.py \
  --json \
  --archive-path <local-release-archive.tar.gz> \
  --manifest-path <release-readiness-manifest.json> \
  --release-name <remote-release-name>
```

The archive plan is not authorization and must not be treated as execution. It
should show `ready_for_owner_authorized_remote_deploy=true` and print the
explicit remote mutation confirmation phrase before any upload, backup,
migration, symlink switch, or restart.

Then build the consolidated Owner decision packet:

```bash
/opt/homebrew/bin/python3 scripts/build_tokyo_runtime_governance_owner_deploy_packet.py \
  --json \
  --archive-path <local-release-archive.tar.gz> \
  --manifest-path <release-readiness-manifest.json> \
  --release-name <remote-release-name> \
  > <owner-deploy-decision-packet.json>
```

This packet aggregates release readiness, archive deploy plan, executor dry-run,
Tokyo read-only probe, and the pre-live runtime submit packet. It must report
`ready_for_owner_deploy_decision=true` before asking the Owner to approve the
deploy apply step. That status does not authorize live runtime enablement,
real submit, OrderLifecycle adapter enablement, or exchange order placement.

Once Owner explicitly approves the remote mutation stage, the same plan can be
executed through the apply-gated executor:

```bash
/opt/homebrew/bin/python3 scripts/execute_tokyo_runtime_governance_deploy.py \
  --json \
  --archive-path <local-release-archive.tar.gz> \
  --manifest-path <release-readiness-manifest.json> \
  --release-name <remote-release-name> \
  --owner-deploy-packet-path <owner-deploy-decision-packet.json> \
  --apply \
  --confirmation-phrase OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Without `--apply`, the exact confirmation phrase, and a ready archive owner
deploy decision packet for the same archive / manifest / HEAD, this executor remains
blocked or dry-run and must not mutate Tokyo. With all three, it is a remote
deployment, backup, migration, symlink, and service-control action; do not run
it as a background convenience command.

The executor's backend health smoke must wait for bounded readiness after
`systemctl start`, not only check `systemctl is-active`. A release can be active
before the HTTP listener is ready. The planned health smoke waits up to 30
seconds for `/api/health` before failing.

For a follow-up deployment after a newer runtime-governance release is already
on Tokyo, pass the current remote baseline explicitly to the plan, owner packet,
and apply executor:

```text
--previous-release <current remote release path>
--expected-deployed-head <current remote deployed head>
--expected-remote-migration-count <current remote migration count>
--expected-remote-latest-migration <current remote latest migration filename>
```

The default values remain the original `ae9b209e` / migration `064` predeploy
baseline and are not correct for continuous deploys after the first controlled
runtime-governance refresh.

## Remote Preflight

Read-only checks before any remote mutation:

```bash
./scripts/probe_tokyo_runtime_governance_readonly.py --json
```

If the script is unavailable, use the equivalent raw read-only checks:

```bash
ssh tokyo 'cd ~/brc-deploy/app/current && git rev-parse HEAD && git status --short --branch'
ssh tokyo 'curl -fsS http://127.0.0.1:18080/api/health'
ssh tokyo 'ps -eo pid,ppid,user,comm,args | egrep "(python -m src.main|postgres|docker)" | grep -v -E "(grep|egrep)"'
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
3. Inspect the migration path from deployed `064` to local `069`.
4. Run migration planning in a staging/dry-run context when available.
5. Apply migrations only after the release artifact and rollback target are
   known.

The migration jump includes runtime governance tables and audit records. Treat
it as a controlled deployment stage, not as a casual restart.

Local static audit command:

```bash
/opt/homebrew/bin/python3 scripts/audit_tokyo_runtime_governance_migration_gap.py --json
```

The output must show:

- `ready_for_controlled_migration_preflight=true`;
- chain length `5` for `065 -> 069`;
- no `data_destructive_upgrade_ops`.

The output is allowed to warn about non-additive / data-touching review items,
but those warnings require concrete deployment handling:

- backend writes must be stopped or quiesced while migrations run;
- a remote PG backup must be captured first;
- revision `065` relaxes runtime shadow-only constraints only after explicit
  live-runtime enablement authorization is proven;
- revision `066` adds the OrderLifecycle-adapter disabled submit status and
  must not be interpreted as enabling the real adapter;
- revision `067` only permits local `Order(status=CREATED)` persistence;
- revision `068` only adds the persistent adapter-result duplicate-submit lock;
- revision `069` only allows fail-closed adapter registration failure results.

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

For the default git-based deployment path, the planned order is:

1. Run local and remote read-only preflights.
2. Fetch the pushed branch head on Tokyo.
3. Export the target commit from the remote git checkout into a new clean
   release directory and write `.brc-release-manifest.json`.
4. Stop `brc-owner-console-backend.service` with non-interactive sudo to quiesce
   backend writes.
5. Create the PG backup.
6. Run `compileall`, `alembic heads`, and `alembic upgrade head` from the new
   release tree with `live-readonly.env`.
7. Repoint `app/current`.
8. Start the backend service.
9. Run health, post-deploy readonly probe, and console/API smokes.

For archive fallback, replace steps 2-3 with upload of the local archive and
manifest, then extraction into the clean release directory.

## Post-Deployment Smoke

Minimum backend checks:

```bash
curl -fsS http://127.0.0.1:18080/api/health
curl -fsS http://127.0.0.1:18080/api/trading-console/strategy-runtimes?limit=1
curl -fsS http://127.0.0.1:18080/api/trading-console/strategy-runtime-profile-proposals?strategy_family_id=CPM-RO-001\&strategy_family_version_id=CPM-RO-001-v0\&symbol=BNB/USDT:USDT\&side=long
```

Preferred post-deployment read-only verifier:

```bash
/opt/homebrew/bin/python3 scripts/verify_tokyo_runtime_governance_postdeploy.py \
  --json \
  --expected-current-head <deployed-commit>
```

This verifier checks release identity, migration-file state, health invariants,
key runtime-governance read endpoints, auth gates for runtime submit /
registration draft / controlled-submit endpoints, and that generic Trading
Console POSTs remain blocked. It uses `include_exchange=false` for Trading
Console checks.

Preferred post-deployment acceptance packet:

```bash
/opt/homebrew/bin/python3 scripts/build_tokyo_runtime_governance_postdeploy_acceptance_packet.py \
  --json \
  --expected-current-head <deployed-commit>
```

This packet must report `postdeploy_acceptance_ready=true`. It proves the
deployed release reached the expected HEAD and schema while first real runtime
submit remains blocked. It is not live-submit authorization.

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
