---
title: TOKYO_RUNTIME_DEPLOYMENT_CONTRACT
status: CURRENT
authority: docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md
last_verified: 2026-07-12
---

# Tokyo Runtime Deployment Contract

## Purpose

This contract defines the accepted deployment boundary for the Tokyo runtime.

It exists to keep deployment boring, reproducible, and separate from trading
authority. A Tokyo deployment may update server release files, symlinks, systemd
units, and runtime code. It must not create order authority, bypass execution
gates, mutate credentials, or change live risk scope.

## Core Rule

```text
Local controls deployment over SSH.
Tokyo acquires code through an approved pull/export path.
Release/symlink/systemd is the deployment boundary.
Postdeploy readonly verification proves the deployed head and runtime health.
```

Deployment is an operations workflow. It is not FinalGate, Operation Layer, live
profile selection, strategy policy, order sizing, or exchange write authority.

## Control And Code Planes

| Plane | Required behavior |
| --- | --- |
| Local control plane | The local operator or agent may use SSH to enter Tokyo and run bounded deploy commands |
| Server code acquisition plane | Tokyo must use an approved non-interactive git fetch/export path or an explicitly scoped archive upload path |
| Runtime apply plane | Deploy creates a release directory, updates the current symlink, restarts allowed systemd units, and writes deploy evidence |
| Verification plane | Postdeploy checks are readonly against runtime head, service health, monitor state, and forbidden effects |

Local SSH access to Tokyo does not imply that Tokyo should store a GitHub SSH
private key. If the server does not have a Git SSH key, deployment must not use
`git@...` remotes on Tokyo. Use an approved HTTPS/token/deploy-credential pull
path, or a controlled local archive upload path when the task explicitly allows
that fallback.

## Allowed Deployment Transports

| Transport | Status | Rule |
| --- | --- | --- |
| Git-based Tokyo fetch/export | Preferred | Tokyo fetches the requested commit/branch through an approved non-interactive remote and exports it into a release directory |
| Local archive upload | Conditional fallback | Allowed only when explicitly scoped by the task or deploy script; archive content must come from the intended local git tree |
| Direct manual file copy | Forbidden | Do not hand-copy individual source files into the active runtime tree |
| Server-side ad hoc edits | Forbidden | Do not patch production files manually on Tokyo as a deployment substitute |

## Predeploy Checklist

Before deploy apply, the deployment operator must know:

| Check | Required answer |
| --- | --- |
| Branch and commit | Local branch, local HEAD, remote branch, and target commit are explicit |
| Worktree state | Dirty tree is explained; unrelated local changes are not bundled silently |
| Test state | Required focused tests, validators, and `git diff --check` result are recorded |
| Output scope | Generated runtime/deploy evidence is not committed unless explicitly named |
| Authority scan | No FinalGate bypass, Operation Layer bypass, exchange write, order creation, credential mutation, live profile mutation, or sizing mutation |
| PG cutover scope | If the deploy changes PG runtime authority, schema, seed, runtime readers, ticket path, old-source removal, and rollback/fail-closed behavior are explicit |
| Deploy reason | Stage-worthy fix, deployable milestone, fresh-signal unblock, safety regression repair, or explicit Owner request |

## Apply Boundary

Deploy apply may:

- create a new release directory;
- fetch or export the target code;
- update a release symlink;
- install or refresh allowed systemd service/timer files;
- restart allowed runtime/backend/monitor units;
- write deploy session evidence and postdeploy snapshots.

Deploy apply must not:

- call FinalGate;
- call Operation Layer submit;
- call exchange write APIs;
- create orders;
- withdraw or transfer funds;
- mutate secrets or credentials;
- mutate live profiles;
- mutate order-sizing defaults;
- expand selected StrategyGroup, symbol, side, leverage, notional, or exposure
  scope;
- treat deploy success as `live_submit_ready`.

If a deploy includes PG cutover, deploy apply may run bounded migration and seed
commands only when the task explicitly scopes them. It must not import old
fresh signals, old action-time lanes, old packets, generated timestamps, replay
opportunities, or output artifacts as current live state.

## Repeated Deploy Capability Interlock

An already-enabled **ticket lifecycle mutation capability** is a valid deployed
pre-state, not proof that a repeat deployment is unsafe. It must nevertheless
be quiesced before new code is switched into the production timer path.

The controlled repeat-deploy sequence is:

```text
target release exported
-> read-only pre-switch check accepts enabled or disabled capability
-> reject active real lifecycle / critical command / domain hold /
   unprotected real attempt
-> stop watcher, monitor, lifecycle, and backend units
-> repeat the same safety check under quiescence
-> disable lifecycle capability in PG current state
-> migrate / seed / validate
-> switch release and run postdeploy checks while capability is disabled
-> mechanically certify and re-enable capability
-> run one no-active, zero-exchange-write lifecycle invocation
-> restore timers
```

`--deploy-quiescence` is valid only for the read-only pre-switch and post-stop
safety checks. It deliberately does not certify account-mode freshness; that
fact is refreshed and required by phase-two enablement after the release
switch. The mode does not enable capability, authorize exchange mutation,
bypass phase-two certification, or weaken any active-risk blocker.

The verifier keeps one success status, `phase_two_ready`, and exposes
`mode=deploy_quiescence|phase_two_enablement` as an orthogonal field. Process
success is derived from an empty blocker set, not from a second mode-specific
success enum.

If quiesce or migration fails before the symlink switch, deployment must restore
the prior enabled/disabled capability state and restart the previous release's
allowed services. If phase-two recertification fails after the switch, the new
release remains fail-closed with lifecycle capability disabled until the
official certification path succeeds or the release is rolled back.

## Postdeploy Acceptance

A deploy is accepted only when postdeploy readonly verification records:

| Evidence | Required result |
| --- | --- |
| Runtime head | Deployed head matches the expected commit |
| Service health | Required services are running or explicitly classified |
| Runtime status | Runtime is healthy, waiting, or clearly unavailable with blocker class |
| Monitor path | Tokyo server-side monitor path remains the production monitor owner |
| PG migration version | PG schema and seed versions match the expected cutover version when the deploy includes PG changes |
| PG source mode | Production runtime readers use PG current state; repo MD/JSON/output fallback is disabled |
| Runtime bootstrap | Current coverage, account facts, active position, open orders, balance, service health, and monitor run were refreshed from real Tokyo/runtime sources |
| Ticket handoff | FinalGate rejects missing `ticket_id`; Operation Layer rejects missing `ticket_id + finalgate_pass_id` when the deploy touches this path |
| Old-source removal | Candidate Pool, Daily Table, Goal Status, server monitor, forensics, and gate preconditions do not use old JSON/MD/output as production authority |
| Forbidden effects | FinalGate, Operation Layer, exchange write, order creation, withdrawal, transfer, credential mutation, live profile mutation, and sizing mutation are false |
| Owner state | Any Owner-facing notification is justified by the server monitor contract |

Postdeploy verification may report `live_ready=false`. That is not a deployment
failure by itself. Deployment proves code and runtime health, not market signal
availability or live-submit permission.

## Evidence And Commit Rules

Deploy/session artifacts are volatile evidence by default.

| Artifact type | Git treatment |
| --- | --- |
| Deploy dry-run/apply JSON | Local evidence unless explicitly named |
| Postdeploy runtime snapshot | Local evidence unless explicitly named |
| Server monitor latest output | Runtime/read-model evidence, not routine commit material |
| Source code, tests, docs, migrations | Commit normally when part of the task |

Do not create a second commit only to include deploy evidence unless the task
explicitly requires an evidence commit. Avoid creating a state where local HEAD
differs from the deployed HEAD solely because postdeploy evidence files were
generated after deploy.

## Rollback

Rollback must restore runtime software state without expanding trading
authority.

| Failure | Required behavior |
| --- | --- |
| Deployed head mismatch | Stop, keep or restore previous release, and report mismatch |
| Service restart failure | Restore previous release or leave service stopped with explicit blocker |
| Runtime health regression | Roll back release or classify degraded state; do not continue toward live submit |
| Monitor failure | Keep trading authority unchanged; classify monitor/runtime data gap |
| Deploy transport failure | Stop before symlink switch when possible |
| PG current state unavailable | Stop ticket, FinalGate, and submit progression; forward-fix PG state rather than falling back to old files |
| PG migration/seed failure | Keep or restore previous release, mark runtime unavailable or fail closed, and do not import current state from old output JSON |

Rollback must not use manual production edits as the normal recovery method.
Rollback must not restore old repo MD/JSON/output authority after PG cutover.

## Report Format

Every deployment summary must include:

| Field | Meaning |
| --- | --- |
| `interaction_level` | Local only, Tokyo read-only, or Tokyo deploy apply |
| `remote_interaction_count` | Count or bounded estimate of remote commands/sessions |
| `server_files_mutated` | Whether release/symlink/systemd/runtime files changed |
| `target_commit` | Commit intended for deployment |
| `deployed_head` | Commit proven after deploy |
| `transport` | Git fetch/export or explicit archive upload |
| `postdeploy_status` | Accepted, degraded, failed, or rolled back |
| `approaches_real_order` | Must be false unless the task is explicitly an action-time live-submit task |
| `forbidden_effects` | FinalGate, Operation Layer, exchange write, order creation, withdrawal, transfer, secrets, profile, and sizing mutation booleans |
| `remaining_blocker` | Market wait, runtime gap, policy gap, safety stop, or none |

## Skill Relationship

A future deployment skill may automate this checklist. The skill must read this
contract first and must not redefine deployment authority. If a skill conflicts
with this document, this document wins.

## Authority Boundary

This contract does not authorize:

- real-order submission;
- FinalGate bypass;
- Operation Layer bypass;
- exchange write;
- order creation;
- withdrawal or transfer;
- credential mutation;
- live profile mutation;
- order-sizing mutation;
- strategy scope expansion;
- stale-fact execution;
- missing-protection execution;
- duplicate submit;
- conflicting active position or open-order submit.

It defines only how Tokyo runtime software is deployed and verified.
