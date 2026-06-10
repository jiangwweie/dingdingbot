# Tokyo Runtime Governance Owner Deploy Authorization Packet - 2026-06-10

Status: OWNER_DECISION_PACKET

This packet is a concise authorization aid for the Tokyo controlled deployment
gate. It is not deployment authorization by itself, not live-submit
authorization, not exchange authorization, and not withdrawal/transfer
authorization.

## 1. Candidate Verified Before This Packet

Verified deployment candidate:

- branch: `codex/sprint6-console-runtime-integration`
- candidate commit: `daa13fb4af14d6a419888e531bda60b566673579`
- candidate archive:
  `output/tokyo-runtime-governance-release/brc-runtime-governance-daa13fb4-20260610T053122Z/brc-runtime-governance-daa13fb4-20260610T053122Z.tar.gz`
- candidate manifest:
  `output/tokyo-runtime-governance-release/brc-runtime-governance-daa13fb4-20260610T053122Z/release-readiness-manifest.json`

This document is an authorization packet created after that candidate was
verified. If the Owner wants this packet included in the deployed release
artifact, regenerate `prepare -> plan -> executor dry-run` for the then-current
HEAD before applying deployment.

## 2. Verified Dry-Run Facts

Release preparation for `daa13fb4` reported:

```text
status=ready_for_local_packaging
ready_for_packaging=true
tracked_dirty=false
migration_count=64
latest_migration=2026-06-10-064_add_runtime_profile_proposal_snapshot.py
deployed_head_is_ancestor=true
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
commands_planned=18
commands_executed=0
blockers=[]
```

Tokyo read-only probe reported:

```text
status=ready_for_controlled_deploy_preflight
blockers=[]
warnings=[]
current_head=415d398509872cb25bf969319e29732764f9615b
migration_count=44
latest_migration=2026-06-08-044_create_live_lifecycle_reviews.py
health.status=ok
health.runtime_bound=true
health.live_ready=false
```

## 3. What Deploy Apply Would Do

If explicitly authorized and applied, the deployment executor would run the
owner-gated plan phases:

1. Local release and migration-gap preflight.
2. Remote read-only preflight.
3. Upload archive and manifest to Tokyo.
4. Extract into a new release directory.
5. Stop the backend service to quiesce writes.
6. Create a PG backup with `pg_dump`.
7. Run remote compile and Alembic `upgrade head` from migration `044` to `064`.
8. Switch `app/current` symlink to the new release.
9. Restart the backend service.
10. Run health, read-only deployment probe, and postdeploy verifier.

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

