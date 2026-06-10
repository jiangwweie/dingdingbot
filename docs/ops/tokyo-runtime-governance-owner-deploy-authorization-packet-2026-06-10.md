# Tokyo Runtime Governance Owner Deploy Authorization Packet - 2026-06-10

Status: OWNER_DECISION_PACKET

This packet is a concise authorization aid for the Tokyo controlled deployment
gate. It is not deployment authorization by itself, not live-submit
authorization, not exchange authorization, and not withdrawal/transfer
authorization.

## 1. Candidate Verified Before This Packet

Current verified deployment candidate must be read from the generated
`release-readiness-manifest.json` and the deploy plan immediately before
deployment. This tracked packet intentionally does not pin a local candidate
commit or archive path, because editing the packet would itself create a newer
HEAD.

Before applying deployment, regenerate `prepare -> git deploy plan -> git
executor dry-run` for the then-current HEAD and use those outputs as the
candidate facts. The target commit must first be pushed and must match the
selected remote branch HEAD.

Preferred machine-generated packet:

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

The packet must report:

```text
status=ready_for_owner_git_deploy_decision
ready_for_owner_git_deploy_decision=true
```

This status means only that the Owner may decide whether to authorize the
Tokyo deploy apply step. It is not first-real-submit authorization.
The deploy executor must receive that same packet through
`--owner-deploy-packet-path` before `--apply` can proceed.

Archive-based `build_tokyo_runtime_governance_owner_deploy_packet.py` remains
available only as fallback when Tokyo cannot fetch the git repository.

## 2. Verified Dry-Run Facts

Latest expected release-preparation facts for the current stage:

```text
status=ready_for_local_packaging
ready_for_packaging=true
tracked_dirty=false
migration_count=69
latest_migration=2026-06-10-069_allow_adapter_registration_failure_results.py
deployed_head_is_ancestor=true
commits_ahead_of_deployed=<computed from manifest>
```

Deployment plan reported:

```text
status=ready_for_owner_authorized_remote_deploy_plan
ready_for_owner_authorized_remote_deploy=true
blockers=[]
warnings=[]
remote_mutation_requires_confirmation_phrase=OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Executor dry-run reported:

```text
status=dry_run_ready
commands_planned=20
commands_executed=0
blockers=[]
```

Tokyo read-only probe reported:

```text
status=ready_for_controlled_deploy_preflight
blockers=[]
warnings=[remote_release_identity_from_manifest_without_git_status]
current_head=ae9b209e33cd287273491f2e93dfdff3b6a814fd
migration_count=64
latest_migration=2026-06-10-064_add_runtime_profile_proposal_snapshot.py
health.status=ok
health.runtime_bound=true
health.live_ready=false
```

## 3. What Deploy Apply Would Do

If explicitly authorized and applied, the deployment executor would run the
owner-gated plan phases:

1. Local release and migration-gap preflight.
2. Remote read-only preflight.
3. Fetch the pushed branch head on Tokyo.
4. Export the target commit into a new release directory and write the manifest.
5. Stop the backend service to quiesce writes.
6. Create a PG backup with `pg_dump`.
7. Run remote compile and Alembic `upgrade head`.
8. Switch `app/current` symlink to the new release.
9. Restart the backend service.
10. Run health, read-only deployment probe, and postdeploy verifier, including
    auth-gated runtime submit / registration draft / controlled-submit API
    smoke checks.

## 4. What Deploy Apply Must Not Do

Deployment must not:

- place real orders;
- cancel, close, or replace orders;
- call `OwnerBoundedExecution`;
- call `OrderLifecycle`;
- call exchange write APIs;
- create executable submit authority;
- change live runtime profile or real-funds sizing defaults;
- initiate withdrawal, transfer, or fund movement;
- enable automatic strategy execution.

Deployment only moves the runtime-governance code and schema to Tokyo and then
verifies non-executing readiness.

## 5. Required Owner Authorization Text

The deployment executor requires this exact confirmation phrase:

```text
OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

The Owner should use that phrase only if approving remote upload, backup,
migration, symlink switch, service restart, and postdeploy smoke for the
current verified candidate or for a regenerated current-HEAD candidate.

## 6. Boundary After Successful Deploy

Even if deployment succeeds:

- runtime submit remains disabled / not implemented for real order placement;
- the first real runtime submit remains a separate Owner gate;
- CPM / BRF / BTPC / LSR / RBR / VCB remain reference or candidate semantics,
  not proven-alpha production strategies;
- bounded losses are acceptable only inside confirmed runtime boundaries;
- system failure remains runaway behavior, boundary breach, unauditable orders,
  duplicate submits, missing trusted facts, missing protection, or unauthorized
  exchange writes.
