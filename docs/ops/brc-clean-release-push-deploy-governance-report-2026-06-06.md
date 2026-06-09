> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# BRC Clean Release, Push, And Deploy Governance Report

Date: 2026-06-06

## Verdict

PASS_WITH_CONSTRAINT

The BNB and Trend/SOL post-close baseline is push-ready from the local
repository. BNB/SOL live exposure was reconfirmed as flat from both exchange
and PG evidence. Tokyo service is healthy and remains `live_ready=false`.

Deployment is not restart-ready yet. The active process still runs from the
older release directory, `app/current` points to a different dirty release tree,
and attempts to create a clean backend release artifact over the current SSH
file-transfer path stalled. No symlink change, service restart, push, or live
action was performed.

## Local Version State

This inventory was captured before committing this report. The session final
output records the post-report commit and tag state.

- branch: `dev`
- HEAD: `777b2056 docs(brc): record post-close release governance`
- branch status: `dev...origin/dev [ahead 19]`
- worktree before this report: clean
- HEAD tag: `brc-post-close-release-governance-20260606-r0`
- Alembic head: `042 (head)`

### Commits Ahead Of Origin

| Commit | Scope | Subject |
| --- | --- | --- |
| `56801d4a` | Trading Console | `feat(trading-console): add strategy family admission state` |
| `c1e25331` | Trading Console | `docs(trading-console): add gate2 frontend handoff package` |
| `973f4110` | Trading Console | `docs(trading-console): add runtime-bound acceptance evidence` |
| `fc1036b0` | Repo hygiene | `chore(repo): ignore local readonly env files` |
| `09d56a80` | Trend bridge | `feat(brc): add scoped trend action carrier bridge` |
| `e10a2eec` | Trend bridge | `test(brc): prove trend exact-scope bridge fail-closed` |
| `54b264d1` | Trend bridge | `fix(brc): resolve trend scoped clearance bridge` |
| `2ff7a748` | StrategyFamily standard | `feat(brc): add strategy family action candidate standard` |
| `93a09b82` | GenericActionSpec | `feat(brc): add generic action spec entry readiness` |
| `6493a94c` | Generic final gate | `feat(brc): add generic final gate live action chain` |
| `7adfef9d` | Generic final gate | `fix(brc): structure generic probe guard blockers` |
| `07f6793e` | Server readiness | `fix(brc): preserve structured execute blockers` |
| `b9cf59ce` | Server readiness | `fix(brc): separate final gate execute permission mode` |
| `a067ce95` | Server readiness | `fix(brc): expose owner gateway init blockers` |
| `bda6c1fa` | Server readiness | `fix(brc): add server credential preflight readiness` |
| `8c6ddb9a` | Server readiness | `fix(brc): support scoped gks safety clearance` |
| `210353b3` | Trend/SOL governance | `docs(brc): record trend sol live action governance` |
| `4a2819ce` | Trend/SOL closure | `docs(brc): record trend sol full chain closure` |
| `777b2056` | Post-close governance | `docs(brc): record post-close release governance` |

### Tag State

Already on remote:

- `brc-trading-console-bnb-close-20260604-r0`
- `brc-trading-console-bnb-close-20260604-r1`

Local-only tags to push with this baseline:

- `brc-trend-action-bridge-20260604-r0 -> 09d56a80`
- `brc-trend-sol-live-governance-20260606-r0 -> 210353b3`
- `brc-trend-sol-full-closure-20260606-r0 -> 4a2819ce`
- `brc-post-close-release-governance-20260606-r0 -> 777b2056`
- `brc-clean-release-push-deploy-governance-20260606-r0 -> this report commit`

## Push Package

Push recommendation:

1. Push branch `dev`, including the 19 local commits listed above.
2. Push the five local-only Trend/SOL/governance tags.
3. Do not push `reports/`, `.env*`, credentials, screenshots, build outputs,
   server overlay files, or temporary release artifacts.

Push was not performed.

## Tokyo Release And Runtime State

Service:

- unit: `brc-owner-console-backend.service`
- status: active
- PID: `1123809`
- active process cwd:
  `/home/ubuntu/brc-deploy/releases/trading-console-v03-20260604145733`
- service `WorkingDirectory`: `/home/ubuntu/brc-deploy/app/current`
- service hard env:
  - `BRC_EXECUTION_PERMISSION_MAX=read_only`
  - `RUNTIME_CONTROL_API_ENABLED=false`
  - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`

Health:

```json
{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

Release pointers:

- `app/current`:
  `/home/ubuntu/brc-deploy/releases/trend-sol-governance-8c6ddb9a-202606061415`
- active process source:
  `/home/ubuntu/brc-deploy/releases/trading-console-v03-20260604145733`
- `app/current` git HEAD: `0a94553`
- `app/current` tree: dirty with tracked modifications and untracked overlay
  files.
- active process release tree: also dirty with the same overlay pattern.

Release artifact repair attempt:

- full `git archive HEAD` transfer was stopped after it exceeded the safe
  wait window.
- minimal backend archive was locally verified at 5.4 MB and generated in
  0.03s, but both SSH pipe transfer and `scp` transfer stalled.
- all partial `brc-post-close-governance-777b2056-*` release directories and
  temporary tar files were removed.
- `app/current` was not repointed.
- service was not restarted.

## No-Exposure Evidence

Fresh Tokyo read-only evidence:

- server:
  `/home/ubuntu/brc-deploy/reports/brc-clean-release-governance-20260606/no-exposure-readonly.json`
- local copy:
  `reports/brc-clean-release-governance-20260606/no-exposure-readonly.json`
- evidence file is ignored by git through `reports/`.

| Symbol | Exchange Positions | Exchange Open Orders | Exchange Stop Orders | PG Open Orders | PG Active Positions |
| --- | ---: | ---: | ---: | ---: | ---: |
| `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |

Evidence warnings: none.

## Blocker Records

### BR-CLEAN-RELEASE-ACTIVE-PROCESS-DRIFT-20260606

- stage: release runtime alignment
- path: Tokyo systemd process cwd vs `app/current`
- evidence: active PID `1123809` runs from
  `trading-console-v03-20260604145733`, while `app/current` points to
  `trend-sol-governance-8c6ddb9a-202606061415`
- severity: medium
- bridge: leave the healthy process running; do not restart into a dirty target
- retry_condition: deploy a clean release target, repoint `app/current`, then
  run a planned restart and health/API smoke checks

### BR-CLEAN-RELEASE-DIRTY-SERVER-TREE-20260606

- stage: release source governance
- path: Tokyo release directories
- evidence: both inspected release trees show tracked modifications and
  untracked overlay files
- severity: medium
- bridge: treat local git commits as canonical source; do not classify server
  overlay as versioned truth
- retry_condition: push canonical commits/tags, deploy from a clean checkout or
  verified archive, and archive/remove overlay files in a maintenance window

### BR-CLEAN-RELEASE-ARTIFACT-TRANSFER-20260606

- stage: clean release artifact creation
- path: local-to-Tokyo archive transfer
- evidence: full archive, minimal SSH pipe archive, and minimal `scp` transfer
  stalled; local minimal archive generation itself was fast and 5.4 MB
- severity: medium
- bridge: stop artifact repair, remove partial release directories and temp
  tars, leave service untouched
- retry_condition: use a stable transport path after push, such as server-side
  `git fetch` from origin, a compressed artifact uploaded outside the stalled
  SSH stream, or a maintenance-window rsync with progress and timeout controls

## Deployment Recommendation

Push-ready: yes, with the branch and four local-only tags listed above.

Restart-ready: no. Do not restart the Tokyo service until a clean release
target exists and can be verified before restart.

Safe deploy sequence:

1. Push `dev` and the four local-only tags.
2. On Tokyo, create a clean release from the pushed commit/tag rather than the
   dirty overlay.
3. Run static checks in the clean release:
   - `python3 -m compileall -q src`
   - `python3 -m alembic heads`
4. Repoint `app/current` to the clean release.
5. Restart `brc-owner-console-backend.service` in a planned maintenance window.
6. Verify:
   - `/api/health`
   - `runtime_bound=true`
   - `live_ready=false`
   - BNB/SOL exchange and PG no-exposure snapshot remains zero
   - no unintended action route or auto-execution is enabled

## Checks Run

- `git status --short --branch`: clean, `dev...origin/dev [ahead 19]`
- `git diff --check`: passed
- `python3 -m alembic heads`: `042 (head)`
- Tokyo service health: passed
- Tokyo current/process source inspection: completed
- Tokyo dirty tree inspection: completed
- BNB/SOL exchange and PG no-exposure read: passed
- evidence ignore check: passed

No pytest was run because this task changed governance documentation and
release evidence only; no runtime code was modified.

## Safety Proof

- No new strategy action was started.
- No order was placed.
- No cancel, replace, flatten, retry protection, or auto-execution was
  performed.
- No PG mutation was performed.
- No service restart was performed.
- No `app/current` symlink change was performed.
- No credentials or secret values were printed or committed.
- No push was performed.
